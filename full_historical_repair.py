import logging
import time
from datetime import datetime, timedelta
from sqlalchemy import or_, and_

from app.db.session import SessionLocal
from app.db.base import Order, Driver
from tasks.scraper.drone_scraper import DroneScraper
from tasks.celery_tasks import process_drone_data

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run_full_audit():
    logger.info("🦖 INICIANDO AUDITORÍA PALEONTOLÓGICA (TODA LA HISTORIA)...")
    
    db = SessionLocal()
    
    # FECHA CORTE: Ignoramos los pedidos de las últimas 24h (están vivos)
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    
    logger.info("🔍 Buscando incoherencias en la Base de Datos...")

    # --- GRUPO 1: ZOMBIES (No finalizados y viejos) ---
    zombies = db.query(Order).filter(
        Order.created_at < cutoff_time,
        Order.current_status.in_(['pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way'])
    ).all()
    
    # --- GRUPO 2: FALSOS DELIVERIES (Entregado + Delivery + Sin Chofer) ---
    # Esto corregirá todos los Pickups mal clasificados históricamente
    fake_deliveries = db.query(Order).filter(
        Order.current_status == 'delivered',
        Order.order_type == 'Delivery',
        Order.driver_id == None
    ).all()

    # --- GRUPO 3: MONTOS CERO (Datos incompletos) ---
    empty_amounts = db.query(Order).filter(
        Order.total_amount == 0,
        Order.current_status != 'canceled' # Ignoramos cancelados que pueden ser 0
    ).all()

    # Consolidar lista única de IDs para no repetir trabajo
    targets = {}
    
    for o in zombies: targets[o.external_id] = "Zombie (No cerrado)"
    for o in fake_deliveries: targets[o.external_id] = "Falso Delivery (Pickup real)"
    for o in empty_amounts: targets[o.external_id] = "Monto Cero"

    total_targets = len(targets)
    logger.info(f"📊 DIAGNÓSTICO INICIAL:")
    logger.info(f"   - Zombies encontrados: {len(zombies)}")
    logger.info(f"   - Falsos Deliveries (Pickups): {len(fake_deliveries)}")
    logger.info(f"   - Montos vacíos: {len(empty_amounts)}")
    logger.info(f"   ----------------------------------------")
    logger.info(f"   🎯 TOTAL A REPARAR: {total_targets} pedidos únicos.")

    if total_targets == 0:
        logger.info("✨ ¡El sistema está inmaculado! Nada que reparar.")
        return

    # --- EJECUCIÓN DEL DRON ---
    drone = DroneScraper()
    if not drone.login():
        logger.error("❌ Fallo crítico: No se pudo loguear el Dron.")
        return

    logger.info("🚀 Iniciando reparaciones masivas...")
    
    count = 0
    errors = 0
    
    for eid, reason in targets.items():
        count += 1
        try:
            logger.info(f"🔧 [{count}/{total_targets}] Reparando #{eid} -> Causa: {reason}")
            
            # 1. Scrape Full (Trae estatus, montos, chofer y mapa)
            data = drone.scrape_detail(eid, mode='full')
            
            # 2. Guardado Inteligente (Aplica las reglas nuevas de Pickup)
            process_drone_data(db, data)
            
            # Pequeña pausa para no tumbar el servidor de GoPharma
            # time.sleep(0.5) 
            
        except Exception as e:
            logger.error(f"⚠️ Error reparando {eid}: {e}")
            errors += 1

    drone.close_driver()
    db.close()
    
    logger.info("🏁 AUDITORÍA HISTÓRICA FINALIZADA.")
    logger.info(f"✅ Procesados: {count - errors}")
    logger.info(f"❌ Errores: {errors}")

if __name__ == "__main__":
    run_full_audit()
