import os
import logging
import time
from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.db.base import Order
from tasks.scraper.drone_scraper import DroneScraper
from tasks.celery_tasks import process_drone_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 📌 EL CHECKPOINT SRE
CHECKPOINT_FILE = "/tmp/pedidos_curados.txt"


def get_processed_ids():
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    with open(CHECKPOINT_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())


def save_processed_id(eid):
    with open(CHECKPOINT_FILE, "a") as f:
        f.write(f"{eid}\n")


def recovery_massive_zombies(days_back=45):
    db = SessionLocal()
    drone = DroneScraper()
    processed_ids = get_processed_ids()

    limit_date = datetime.now() - timedelta(days=days_back)

    logger.info("📡 Descargando historial de 45 días...")
    all_orders = db.query(Order).filter(Order.created_at >= limit_date).all()

    # 📌 FILTRO INFALIBLE: Solo procesamos los que NO están en el archivo de texto
    pendientes = [o for o in all_orders if str(o.external_id) not in processed_ids]

    logger.info(f"🕵️‍♂️ Restan {len(pendientes)} pedidos por verificar y curar.")

    if not pendientes:
        logger.info("✨ Todos los pedidos han sido verificados. Historial al 100%.")
        return

    try:
        if drone.login():
            for i, order in enumerate(pendientes, 1):
                eid = str(order.external_id)
                logger.info(f"🚑 [{i}/{len(pendientes)}] Auditando pedido #{eid}...")

                # Reseteo de memoria cada 15 pedidos
                if i % 15 == 0:
                    logger.info("🔄 Refrescando memoria del Dron...")
                    drone.close_driver()
                    time.sleep(2)
                    drone = DroneScraper()
                    drone.login()

                success = False
                for attempt in range(2):
                    try:
                        data = drone.scrape_detail(eid, mode="full")

                        if data:
                            # Bypass Ninja de Estados
                            data["status_text"] = order.current_status
                            data["list_status"] = order.current_status

                            process_drone_data(db, data)
                            db.commit()

                            logger.info(
                                f"✅ CURADO/VERIFICADO #{eid}: {data.get('customer_name')} | {data.get('store_name')}"
                            )
                            # 📌 GUARDAMOS PROGRESO EN PIEDRA
                            save_processed_id(eid)
                            success = True
                            break
                    except Exception as e:
                        logger.warning(f"⚠️ Intento {attempt+1} falló para #{eid}: {e}")
                        db.rollback()

                        if (
                            "Connection refused" in str(e)
                            or "Max retries exceeded" in str(e)
                            or "RemoteDisconnected" in str(e)
                        ):
                            drone.close_driver()
                            time.sleep(2)
                            drone = DroneScraper()
                            drone.login()

                if not success:
                    logger.error(
                        f"❌ Abandono temporal para #{eid}. Se intentará en la próxima corrida."
                    )

            logger.info("🏆 Proceso de recuperación masiva completado.")
        else:
            logger.error("❌ El dron no pudo loguearse.")
    finally:
        drone.close_driver()
        db.close()


if __name__ == "__main__":
    recovery_massive_zombies()
