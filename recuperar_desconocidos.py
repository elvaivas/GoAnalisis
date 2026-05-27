import os
import sys

# Asegura que Python reconozca los módulos 'app' y 'tasks' al correr desde la terminal
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.db.base import Order
from tasks.scraper.drone_scraper import DroneScraper
from tasks.celery_tasks import process_drone_data
from sqlalchemy import or_

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def run_recovery_desconocidos():
    logger.info("🚀 INICIANDO RECUPERACIÓN DE PEDIDOS DESCONOCIDOS (ÚLTIMOS 7 DÍAS)...")

    db = SessionLocal()
    drone = DroneScraper()

    # Rango: Desde hace 7 días (jueves pasado) hasta ahora
    start_date = datetime.utcnow() - timedelta(days=7)

    # Buscamos pedidos de los últimos 7 días cuyo estado sea desconocido,
    # nulo, vacío, o cualquier texto de error que esté arrojando el scraper anterior.
    # Ajusta los strings del in_() si en tu BD dicen algo distinto a 'desconocido' o 'unknown'
    stuck_orders = (
        db.query(Order)
        .filter(
            Order.created_at >= start_date,
            or_(
                Order.current_status.in_(["desconocido", "unknown", "", "error"]),
                Order.current_status == None,
            ),
        )
        .all()
    )

    logger.info(
        f"🚨 Encontrados {len(stuck_orders)} pedidos con estatus desconocido. Iniciando Dron..."
    )

    if not stuck_orders:
        logger.info("✨ No se encontraron pedidos desconocidos en ese rango de fechas.")
        return

    if not drone.login():
        logger.error("❌ Fallo login del dron de GoPharma")
        return

    count = 0
    errors = 0

    for order in stuck_orders:
        count += 1
        logger.info(
            f"🔍 [{count}/{len(stuck_orders)}] Re-escaneando #{order.external_id}..."
        )
        try:
            # Forzamos el modo full para que pase por tus nuevos selectores
            data = drone.scrape_detail(order.external_id, mode="full")

            # Validamos que 'data' no venga vacío (None) antes de enviarlo a la BD
            if data:
                process_drone_data(db, data)
                logger.info(f"✅ Pedido #{order.external_id} actualizado con éxito.")
            else:
                logger.warning(
                    f"⚠️ El dron no encontró la información del pedido #{order.external_id}."
                )
                errors += 1

        except Exception as e:
            logger.error(f"⚠️ Error intentando raspar {order.external_id}: {e}")
            errors += 1

    drone.close_driver()
    db.close()

    logger.info("🏁 RECUPERACIÓN FINALIZADA.")
    logger.info(f"✅ Procesados exitosamente: {count - errors}")
    if errors > 0:
        logger.info(f"❌ Errores (revisar selectores): {errors}")


if __name__ == "__main__":
    run_recovery_desconocidos()
