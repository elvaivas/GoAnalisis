import logging
from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.db.base import Order
from tasks.scraper.drone_scraper import DroneScraper
from tasks.celery_tasks import process_drone_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def recovery_massive_zombies(days_back=45):
    db = SessionLocal()
    drone = DroneScraper()

    limit_date = datetime.now() - timedelta(days=days_back)

    # 1. Traemos TODOS los pedidos de los últimos 45 días
    logger.info("📡 Descargando historial de 45 días para auditar...")
    all_orders = db.query(Order).filter(Order.created_at >= limit_date).all()
    zombies = []

    ## 2. Filtramos con Python de forma agresiva
    for order in all_orders:
        otype = getattr(order, "order_type", "") or ""
        status = getattr(order, "current_status", "") or ""
        c_name = getattr(order, "customer_name", "") or ""
        s_name = getattr(order, "store_name", "") or ""

        if (
            otype.lower() == "desconocido"
            or otype == ""
            or status.isdigit()
            or c_name.lower() == "desconocido"
            or s_name.lower() == "desconocida"
            or s_name == ""
        ):
            zombies.append(order)

    logger.info(
        f"🕵️‍♂️ Se han detectado {len(zombies)} pedidos infectados en los últimos {days_back} días."
    )

    if not zombies:
        logger.info("✨ No hay nada que curar. La base de datos está limpia.")
        return

    # 3. Iniciamos la curación (CON REINICIO DE MOTOR)
    try:
        if drone.login():
            for i, order in enumerate(zombies, 1):
                logger.info(
                    f"🚑 [{i}/{len(zombies)}] Curando pedido #{order.external_id}..."
                )

                # --- SISTEMA ANTI-CRASH: Reiniciar navegador cada 100 pedidos ---
                if i % 100 == 0:
                    logger.info(
                        "🔄 Refrescando memoria del Dron (Reinicio de Driver)..."
                    )
                    drone.close_driver()
                    drone = DroneScraper()
                    drone.login()
                # -----------------------------------------------------------------

                try:
                    data = drone.scrape_detail(order.external_id, mode="full")
                    if data:
                        process_drone_data(db, data)
                        if i % 5 == 0:
                            db.commit()
                except Exception as e:
                    logger.error(f"❌ Error al curar #{order.external_id}: {e}")
                    db.rollback()

            db.commit()
            logger.info("🏆 Proceso de recuperación masiva completado.")
        else:
            logger.error("❌ El dron no pudo loguearse.")
    finally:
        drone.close_driver()
        db.close()


if __name__ == "__main__":
    recovery_massive_zombies()
