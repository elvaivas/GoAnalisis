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

    # 1. Buscamos órdenes con datos corruptos en el rango de tiempo
    limit_date = datetime.now() - timedelta(days=days_back)

    zombies = (
        db.query(Order)
        .filter(
            Order.created_at >= limit_date,
            (Order.customer_name == "Desconocido")
            | (Order.store_name == "Desconocida"),
        )
        .all()
    )

    logger.info(
        f"🕵️‍♂️ Se han detectado {len(zombies)} pedidos corruptos en los últimos {days_back} días."
    )

    if not zombies:
        logger.info("✨ No hay nada que curar. La base de datos está limpia.")
        return

    # 2. Iniciamos el proceso de curación
    try:
        if drone.login():
            for i, order in enumerate(zombies, 1):
                logger.info(
                    f"🚑 [{i}/{len(zombies)}] Curando pedido #{order.external_id}..."
                )
                try:
                    # Usamos el scraper que acabamos de blindar
                    data = drone.scrape_detail(order.external_id, mode="full")
                    if data:
                        process_drone_data(db, data)
                        # Commit cada 5 pedidos para no saturar la transacción
                        if i % 5 == 0:
                            db.commit()
                except Exception as e:
                    logger.error(f"❌ Error al curar #{order.external_id}: {e}")
                    db.rollback()

            db.commit()  # Commit final
            logger.info("🏆 Proceso de recuperación masiva completado.")
        else:
            logger.error("❌ El dron no pudo loguearse.")
    finally:
        drone.close_driver()
        db.close()


if __name__ == "__main__":
    recovery_massive_zombies()
