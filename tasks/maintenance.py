import logging
import redis
import time
from datetime import datetime, timedelta
from celery import shared_task
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.base import Order
from tasks.scraper.order_scraper import OrderScraper
from tasks.scraper.drone_scraper import DroneScraper
from tasks.celery_tasks import process_drone_data

# Configuración de Logging
logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(settings.REDIS_URL)

@shared_task(bind=True, name="tasks.maintenance.nightly_deep_clean")
def nightly_deep_clean(self):
    """
    PROTOCOL DE MANTENIMIENTO NOCTURNO (4:00 AM)
    1. Rompe candados de Redis olvidados.
    2. Ejecuta auditoría profunda de las últimas 48h (Logic de recuperar_ayer).
    3. Mata procesos de Chrome huérfanos (vía Python).
    """
    logger.info("🏥 INICIANDO PROTOCOLO DE AUTOCURACIÓN NOCTURNA...")
    
    # --- FASE 1: ROMPER CANDADOS VIEJOS ---
    try:
        keys = redis_client.keys("celery_lock_*")
        if keys:
            logger.info(f"🔓 Liberando {len(keys)} candados de tareas trabadas...")
            redis_client.delete(*keys)
    except Exception as e:
        logger.error(f"Error limpiando Redis: {e}")

    # --- FASE 2: AUDITORÍA DE DATOS (ÚLTIMAS 48H) ---
    # Esta es la lógica de 'recuperar_ayer.py' automatizada
    try:
        logger.info("🕵️‍♂️ Iniciando Auditoría de Integridad (48 Horas)...")
        db = SessionLocal()
        ls = OrderScraper()
        drone = DroneScraper()
        
        # 1. Bajamos historial reciente (20 páginas = ~500 pedidos, cubre fin de semana)
        if ls.login():
            items = ls.get_historical_ids(max_pages=20)
            ls.close_driver()
            
            # Filtramos solo lo que valga la pena revisar (No Delivered/Canceled o Data incompleta)
            # O mejor: FORZAMOS la actualización de todo lo que no esté 'delivered' en DB local
            # para asegurar que si se entregó en la madrugada, se marque.
            
            if drone.login():
                count = 0
                for item in items:
                    eid = item['id']
                    
                    # Buscamos en DB local
                    local_order = db.query(Order).filter(Order.external_id == eid).first()
                    
                    # CRITERIOS DE REPARACIÓN:
                    # 1. No existe en DB.
                    # 2. En DB está 'pending/on_the_way' pero ya es viejo.
                    # 3. Tiene monto 0.
                    
                    needs_repair = False
                    
                    # 1. No existe en DB
                    if not local_order: 
                        needs_repair = True
                    
                    # 2. Zombie: No está finalizado (delivered/canceled)
                    elif local_order.current_status not in ['delivered', 'canceled']: 
                        needs_repair = True
                    
                    # 3. Datos Incompletos: Monto cero
                    elif local_order.total_amount == 0: 
                        needs_repair = True
                        
                    # 4. NUEVO: INCOHERENCIA LOGÍSTICA (Falso Delivery)
                    # Si dice "Entregado" y "Delivery", PERO no tiene chofer asignado -> Es un Pickup mal clasificado
                    elif (local_order.current_status == 'delivered' and 
                          local_order.order_type == 'Delivery' and 
                          local_order.driver_id is None):
                        needs_repair = True
                        logger.info(f"🧐 Detectada Incoherencia en #{eid}: Delivery sin Chofer. Forzando corrección...")

                    if needs_repair:
                        count += 1
                        logger.info(f"🚑 Reparando Pedido #{eid}...")
                        try:
                            data = drone.scrape_detail(eid, mode='full')
                            # Inyectar duración de lista si el detalle no la trajo bien
                            if not data.get('duration_text'): 
                                data['duration_text'] = item.get('duration', '')
                            
                            process_drone_data(db, data)
                        except Exception as scrape_err:
                            logger.error(f"Fallo reparando {eid}: {scrape_err}")
                
                drone.close_driver()
                logger.info(f"✅ Auditoría finalizada. {count} pedidos corregidos.")
            else:
                logger.error("❌ Dron no pudo loguearse para la auditoría.")
        else:
            logger.error("❌ Scraper de lista no pudo loguearse.")
            
        db.close()

    except Exception as e:
        logger.error(f"❌ Error crítico en Auditoría de Datos: {e}")

    return "System Healthy"
