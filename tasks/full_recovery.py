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

    logger.info("📡 Descargando historial para auditar...")
    all_orders = db.query(Order).filter(Order.created_at >= limit_date).all()
    zombies = []

    # FILTRO ESTRICTO: Solo tomamos los que REALMENTE tienen nombres desconocidos
    for order in all_orders:
        c_name = getattr(order, "customer_name", "") or ""
        s_name = getattr(order, "store_name", "") or ""

        # Ignoramos si ya tiene un nombre real
        if (
            c_name.lower() == "desconocido"
            or s_name.lower() == "desconocida"
            or c_name == ""
        ):
            zombies.append(order)

    logger.info(
        f"🕵️‍♂️ Quedan {len(zombies)} pedidos infectados por curar en los últimos {days_back} días."
    )

    if not zombies:
        logger.info("✨ No hay nada que curar. La base de datos está limpia.")
        return

    try:
        if drone.login():
            # Bajamos el límite a 50 para reiniciar el driver antes de que se asfixie
            for i, order in enumerate(zombies, 1):
                logger.info(
                    f"🚑 [{i}/{len(zombies)}] Curando pedido #{order.external_id}..."
                )

                if i % 50 == 0:
                    logger.info(
                        "🔄 Refrescando memoria del Dron (Reinicio Seguro a los 50)..."
                    )
                    drone.close_driver()
                    drone = DroneScraper()
                    drone.login()

                # Control de reintentos individuales
                success = False
                for attempt in range(2):
                    try:
                        data = drone.scrape_detail(order.external_id, mode="full")
                        if data and data.get("customer_name") != "Desconocido":
                            # 💉 BYPASS SRE: Inyección Directa a la BD ignorando estados
                            order.customer_name = data.get(
                                "customer_name", order.customer_name
                            )
                            order.store_name = data.get("store_name", order.store_name)

                            if data.get("customer_phone"):
                                order.customer_phone = data.get("customer_phone")
                            if data.get("order_type"):
                                order.order_type = data.get("order_type")

                            db.commit()
                            logger.info(
                                f"✅ INYECCIÓN EXITOSA #{order.external_id}: {order.customer_name} | {order.store_name}"
                            )

                            success = True
                            break  # Éxito, salimos del reintento
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Intento {attempt+1} falló para #{order.external_id}: {e}"
                        )
                        db.rollback()

                if not success:
                    logger.error(
                        f"❌ Abandono: El pedido #{order.external_id} falló persistentemente. Se salta al siguiente."
                    )

            logger.info("🏆 Proceso de recuperación masiva completado.")
        else:
            logger.error("❌ El dron no pudo loguearse.")
    finally:
        drone.close_driver()
        db.close()


if __name__ == "__main__":
    recovery_massive_zombies()
