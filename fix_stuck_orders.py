# fix_stuck_orders.py
import logging
from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.db.base import Order
from tasks.scraper.drone_scraper import DroneScraper
from tasks.celery_tasks import process_drone_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_fix():
    db = SessionLocal()
    drone = DroneScraper()
    
    # Rango: Desde ayer a las 00:00 hasta hace 4 horas
    yesterday = datetime.utcnow() - timedelta(hours=30)
    limit_time = datetime.utcnow() - timedelta(hours=4)
    
    # Buscamos TODO lo que no esté finalizado
    stuck_orders = db.query(Order).filter(
        Order.created_at >= yesterday,
        Order.created_at <= limit_time,
        Order.current_status.in_(['pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way'])
    ).all()
    
    logger.info(f"🚨 Encontrados {len(stuck_orders)} pedidos atascados. Iniciando limpieza...")
    
    if not stuck_orders:
        return

    if not drone.login():
        logger.error("Fallo login dron")
        return

    count = 0
    for order in stuck_orders:
        count += 1
        logger.info(f"[{count}/{len(stuck_orders)}] Auditando #{order.external_id} ({order.current_status})...")
        try:
            # Modo full para traer estatus, mapa y finanzas
            data = drone.scrape_detail(order.external_id, mode='full')
            process_drone_data(db, data)
        except Exception as e:
            logger.error(f"Error en {order.external_id}: {e}")
            
    drone.close_driver()
    db.close()
    logger.info("✅ Limpieza terminada.")

if __name__ == "__main__":
    run_fix()
