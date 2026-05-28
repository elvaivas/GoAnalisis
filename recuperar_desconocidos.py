import os
import sys

# Asegura que Python reconozca los módulos 'app' y 'tasks'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
from datetime import datetime, timedelta, timezone
from app.db.session import SessionLocal
from app.db.base import Order, Store, Customer
from tasks.scraper.drone_scraper import DroneScraper
from tasks.celery_tasks import process_drone_data
from sqlalchemy import or_, and_, extract

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def run_recovery_desconocidos():
    logger.info(
        "🚀 INICIANDO RECUPERACIÓN PROFUNDA (DETECCIÓN DE 404 FLASH - 15 DÍAS)..."
    )

    db = SessionLocal()
    drone = DroneScraper()

    # Rango: Últimos 15 días
    start_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=15)

    # LA RED DE ARRASTRE INTELIGENTE:
    # Hacemos JOIN con Store y Customer para ver sus nombres reales.
    stuck_orders = (
        db.query(Order)
        .outerjoin(Store, Order.store_id == Store.id)
        .outerjoin(Customer, Order.customer_id == Customer.id)
        .filter(
            Order.created_at >= start_date,
            or_(
                # 1. Falta de relaciones vitales
                Order.store_id == None,
                Order.customer_id == None,
                # 2. Relaciones a entidades fantasma
                Store.name.ilike("%desconocid%"),
                Customer.name.ilike("%desconocid%"),
                # 3. Datos numéricos en 0 que no tienen sentido
                Order.total_amount == 0,
                # 4. Estatus vacío o nulo
                Order.current_status.in_(["desconocido", "unknown", "", "error"]),
                Order.current_status == None,
                # 5. EL SÍNTOMA REINA DEL 404 FLASH: Fecha creada exactamente a las 12:00:00 AM
                and_(
                    extract("hour", Order.created_at) == 0,
                    extract("minute", Order.created_at) == 0,
                    extract("second", Order.created_at) == 0,
                ),
            ),
        )
        .all()
    )

    logger.info(
        f"🚨 La red atrapó {len(stuck_orders)} pedidos con síntomas de corrupción. Iniciando Dron..."
    )

    if not stuck_orders:
        logger.info("✨ No se encontraron pedidos dañados. Todo limpio.")
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
            f"🔍 [{count}/{len(stuck_orders)}] Re-escaneando y curando #{order.external_id}..."
        )
        try:
            # El dron ahora tiene el bucle anti-404 interno, extraerá seguro.
            data = drone.scrape_detail(order.external_id, mode="full")

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
    logger.info(f"✅ Pedidos curados y actualizados con éxito: {count - errors}")


if __name__ == "__main__":
    run_recovery_desconocidos()
