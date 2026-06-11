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
    logger.info("🦖 INICIANDO SANEAMIENTO HISTÓRICO (DESDE EL 1 DE MAYO)...")
    
    db = SessionLocal()
    
    # FECHA DE INICIO ESTRICTA: 1 de Mayo del año en curso (2026)
    start_date = datetime(2026, 5, 1)
    
    # FECHA CORTE: Ignoramos los pedidos de las últimas 24h (Dejamos que Celery los maneje en vivo)
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    
    logger.info(f"🔍 Buscando TODOS los pedidos entre {start_date.strftime('%Y-%m-%d')} y {cutoff_time.strftime('%Y-%m-%d')}...")

    # --- EXTRACCIÓN TOTAL DESDE MAYO ---
    # Al haber un descuadre reportado, forzamos la actualización de TODOS los pedidos 
    # en este rango para asegurar que los nuevos selectores extraigan todo perfectamente.
    orders_to_repair = db.query(Order).filter(
        Order.created_at >= start_date,
        Order.created_at < cutoff_time
    ).all()

    # Mapeamos los IDs. Al ser un full sweep, la razón es general.
    targets = {o.external_id: "Revisión forzada (Descuadre reportado)" for o in orders_to_repair}
    total_targets = len(targets)

    logger.info(f"📊 DIAGNÓSTICO:")
    logger.info(f"   🎯 TOTAL DE PEDIDOS A RASTREAR Y ACTUALIZAR: {total_targets}")

    if total_targets == 0:
        logger.info("✨ No hay pedidos en ese rango de fecha. Finalizando.")
        return

    # --- EJECUCIÓN DEL DRON ---
    drone = DroneScraper()
    if not drone.login():
        logger.error("❌ Fallo crítico: No se pudo loguear el Dron.")
        return

    logger.info("🚀 Iniciando saneamiento masivo...")
    
    count = 0
    errors = 0
    
    for eid, reason in targets.items():
        count += 1
        try:
            # Reducimos el ruido en consola imprimiendo progreso detallado cada 20 pedidos
            if count % 20 == 0 or count == 1 or count == total_targets:
                logger.info(f"🔧 Progreso: [{count}/{total_targets}] -> Scrapeando #{eid}")
            
            # 1. Scrape Full (Trae estatus, montos, chofer, productos, métodos de pago y mapa)
            data = drone.scrape_detail(eid, mode='full')
            
            # 2. Guardado Inteligente (Actualiza o inserta reemplazando la data vieja)
            if data and data.get("status_text"):
                process_drone_data(db, data)
            else:
                logger.warning(f"⚠️ El Dron no trajo data válida para #{eid} (Posible 404).")
                errors += 1
            
            # --- PROTECCIÓN SRE ---
            # Un barrido de miles de pedidos puede activar alarmas de DDoS o tumbar la sesión.
            # 1.5 segundos de gracia entre peticiones mantiene un buen balance de velocidad/seguridad.
            time.sleep(1.5) 
            
        except Exception as e:
            logger.error(f"⚠️ Error reparando {eid}: {e}")
            errors += 1

    drone.close_driver()
    db.close()
    
    logger.info("🏁 SANEAMIENTO HISTÓRICO FINALIZADO.")
    logger.info(f"✅ Procesados exitosamente: {count - errors}")
    logger.info(f"❌ Errores/Vacíos: {errors}")

if __name__ == "__main__":
    run_full_audit()