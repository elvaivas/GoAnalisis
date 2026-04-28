import logging
import time
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

    for order in all_orders:
        c_name = getattr(order, "customer_name", "") or ""
        s_name = getattr(order, "store_name", "") or ""

        # Ignoramos si ya tiene un nombre real o si extrajimos None por error antes
        if c_name.lower() in ["desconocido", "none", ""] or s_name.lower() in [
            "desconocida",
            "none",
            "",
        ]:
            zombies.append(order)

    logger.info(
        f"🕵️‍♂️ Quedan {len(zombies)} pedidos infectados por curar en los últimos {days_back} días."
    )

    if not zombies:
        logger.info("✨ No hay nada que curar. La base de datos está limpia.")
        return

    try:
        if drone.login():
            for i, order in enumerate(zombies, 1):
                logger.info(
                    f"🚑 [{i}/{len(zombies)}] Curando pedido #{order.external_id}..."
                )

                # --- SISTEMA ANTI-CRASH AGRESIVO: Reiniciar cada 15 pedidos ---
                if i % 15 == 0:
                    logger.info(
                        "🔄 Refrescando memoria del Dron (Reinicio Seguro a los 15)..."
                    )
                    drone.close_driver()
                    time.sleep(2)  # Pausa para que el SO libere la RAM
                    drone = DroneScraper()
                    drone.login()

                success = False
                for attempt in range(2):
                    try:
                        data = drone.scrape_detail(order.external_id, mode="full")

                        # VALIDACIÓN ESTRICTA: Solo inyectamos si realmente trajimos datos buenos
                        if data and data.get("customer_name") not in [
                            "Desconocido",
                            None,
                            "None",
                        ]:

                            # BYPASS NINJA
                            data["status_text"] = order.current_status
                            data["list_status"] = order.current_status

                            process_drone_data(db, data)
                            db.commit()

                            logger.info(
                                f"✅ CURADO #{order.external_id}: {data.get('customer_name')} | {data.get('store_name')}"
                            )
                            success = True
                            break
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Intento {attempt+1} falló para #{order.external_id}: {e}"
                        )
                        db.rollback()

                        # Si Chrome explotó, forzamos un reinicio de driver antes del intento 2
                        if "Connection refused" in str(
                            e
                        ) or "Max retries exceeded" in str(e):
                            logger.warning(
                                "♻️ Forzando reinicio de emergencia del driver..."
                            )
                            drone.close_driver()
                            time.sleep(2)
                            drone = DroneScraper()
                            drone.login()

                if not success:
                    logger.error(
                        f"❌ Abandono definitivo para #{order.external_id}. Se salta al siguiente."
                    )

            logger.info("🏆 Proceso de recuperación masiva completado.")
        else:
            logger.error("❌ El dron no pudo loguearse.")
    finally:
        drone.close_driver()
        db.close()


if __name__ == "__main__":
    recovery_massive_zombies()
