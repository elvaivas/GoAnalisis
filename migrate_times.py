import logging
import re
from datetime import datetime, timedelta
from sqlalchemy import func
from app.db.session import SessionLocal
from app.db.base import Order, OrderStatusLog

# Configuración
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


def _parse_duration_to_minutes(duration_str: str) -> float:
    if not duration_str or duration_str == "--":
        return 0.0
    try:
        minutes = 0.0
        s = duration_str.lower()
        h_match = re.search(r"(\d+)\s*(?:h|hr|hora)", s)
        if h_match:
            minutes += float(h_match.group(1)) * 60
        m_match = re.search(r"(\d+)\s*(?:m|min)", s)
        if m_match:
            minutes += float(m_match.group(1))
        return minutes
    except:
        return 0.0


def run_migration():
    db = SessionLocal()
    logger.info("🚀 INICIANDO MIGRACIÓN MASIVA DE TIEMPOS DE ENTREGA")
    logger.info("===================================================")

    # 1. Obtener todos los pedidos entregados
    orders = db.query(Order).filter(Order.current_status == "delivered").all()
    logger.info(f"📦 Analizando {len(orders)} pedidos entregados...")

    updated_count = 0

    for o in orders:
        original_val = o.delivery_time_minutes or 0.0
        new_val = 0.0

        # --- LÓGICA DE CÁLCULO BLINDADA (La misma del KPI) ---

        # A. Intentar Texto del Legacy (Prioridad 1)
        if o.duration:
            new_val = _parse_duration_to_minutes(o.duration)

        # B. Intentar Logs (Prioridad 2)
        if new_val == 0:
            # Buscar log de entrega (usando query directa para precisión)
            done_log = (
                db.query(OrderStatusLog)
                .filter(
                    OrderStatusLog.order_id == o.id,
                    OrderStatusLog.status == "delivered",
                )
                .order_by(OrderStatusLog.timestamp.desc())
                .first()
            )  # El último delivered válido

            if done_log and o.created_at:
                # Ajuste VET -> UTC
                created_utc = o.created_at + timedelta(hours=4)
                delta = (done_log.timestamp - created_utc).total_seconds() / 60.0

                # Filtro de cordura (entre 1 min y 24 horas)
                if 1.0 < delta < 1440:
                    new_val = delta

        # --- ACTUALIZACIÓN ---
        # Si el valor nuevo es válido y diferente al viejo (o el viejo era 0/None)
        if new_val > 0 and abs(new_val - original_val) > 0.1:
            o.delivery_time_minutes = round(new_val, 2)
            updated_count += 1

            if updated_count % 100 == 0:
                logger.info(f"⚡ Procesados {updated_count} cambios...")

    # Confirmación
    if updated_count > 0:
        logger.info(f"💾 Guardando {updated_count} correcciones en la Base de Datos...")
        db.commit()
        logger.info("✅ MIGRACIÓN COMPLETADA EXITOSAMENTE.")
    else:
        logger.info("✨ La base de datos ya estaba perfecta. No hubo cambios.")

    db.close()


if __name__ == "__main__":
    run_migration()
