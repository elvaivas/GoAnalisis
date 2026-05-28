import os
import sys

# Asegura que Python reconozca los módulos 'app' y 'tasks'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
from datetime import datetime, timedelta, timezone
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
    logger.info(
        "🚀 INICIANDO RECUPERACIÓN PROFUNDA (RED DE ARRASTRE - ÚLTIMOS 15 DÍAS)..."
    )

    db = SessionLocal()
    drone = DroneScraper()

    # Rango: Desde hace 15 días hasta ahora (asegurando compatibilidad de timezone con la BD)
    start_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=15)

    # LA RED DE ARRASTRE: Atrapa todo pedido que tenga CUALQUIER indicio de haber fallado
    # durante la migración del panel (falta de relaciones, estatus corruptos, montos vacíos, etc.)
    stuck_orders = (
        db.query(Order)
        .filter(
            Order.created_at >= start_date,
            or_(
                Order.store_id == None,
                Order.customer_id == None,
                Order.order_type == "desconocido",
                Order.order_type == None,
                Order.total_amount == 0,
                Order.current_status.in_(["desconocido", "unknown", "", "error"]),
                Order.current_status == None,
            ),
        )
        .all()
    )

    logger.info(
        f"🚨 La red atrapó {len(stuck_orders)} pedidos corruptos o incompletos. Iniciando Dron..."
    )

    if not stuck_orders:
        logger.info(
            "✨ No se encontraron pedidos dañados en ese rango de fechas. Todo limpio."
        )
        db.close()
        return

    if not drone.login():
        logger.error("❌ Fallo crítico en el login del dron de GoPharma.")
        db.close()
        return

    count = 0
    errors = 0

    for order in stuck_orders:
        count += 1
        logger.info(
            f"🔍 [{count}/{len(stuck_orders)}] Re-escaneando y reparando #{order.external_id}..."
        )
        try:
            # Forzamos el modo full para que pase por los selectores reparados de React
            data = drone.scrape_detail(order.external_id, mode="full")

            # Validamos que 'data' no venga vacío
            if data:
                process_drone_data(db, data)
            else:
                logger.warning(
                    f"⚠️ El dron devolvió vacío para el pedido #{order.external_id}."
                )
                errors += 1

        except Exception as e:
            logger.error(f"⚠️ Error intentando raspar {order.external_id}: {e}")
            errors += 1

    drone.close_driver()
    db.close()

    logger.info("🏁 RECUPERACIÓN MASIVA FINALIZADA.")
    logger.info(f"✅ Pedidos reparados y conectados con éxito: {count - errors}")
    if errors > 0:
        logger.info(
            f"❌ Errores irrecuperables (posiblemente borrados del panel): {errors}"
        )


if __name__ == "__main__":
    run_recovery_desconocidos()
