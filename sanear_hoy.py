import logging
from datetime import datetime, time
from app.db.session import SessionLocal
from app.db.base import Order, OrderStatusLog
from sqlalchemy import asc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_today_logs():
    db = SessionLocal()

    # --- CONFIGURACIÓN DEL RANGO: HOY ---
    # Definimos el inicio del día 12 de Febrero (Hora local servidor)
    hoy_inicio = datetime.combine(datetime.utcnow().date(), time.min)

    print(f"🛡️ INICIANDO SANEAMIENTO CONTROLADO ({hoy_inicio.date()})")
    print("======================================================")

    # 1. Buscamos solo pedidos de hoy
    orders = db.query(Order).filter(Order.created_at >= hoy_inicio).all()
    print(f"🔍 Analizando {len(orders)} pedidos realizados hoy...")

    total_deleted = 0

    for o in orders:
        # 2. Obtenemos logs de este pedido ordenados por tiempo
        logs = (
            db.query(OrderStatusLog)
            .filter(OrderStatusLog.order_id == o.id)
            .order_by(asc(OrderStatusLog.timestamp))
            .all()
        )

        if len(logs) <= 1:
            continue

        last_status = None
        to_delete_ids = []

        for log in logs:
            current_status = log.status.lower().strip()

            # Comparamos estatus con el anterior
            if current_status == last_status:
                # Es un duplicado consecutivo. Lo marcamos para borrar.
                to_delete_ids.append(log.id)
            else:
                last_status = current_status

        # 3. Ejecutar borrado para este pedido
        if to_delete_ids:
            print(
                f"✅ Pedido #{o.external_id}: Identificados {len(to_delete_ids)} duplicados."
            )
            db.query(OrderStatusLog).filter(
                OrderStatusLog.id.in_(to_delete_ids)
            ).delete(synchronize_session=False)
            total_deleted += len(to_delete_ids)

    # 4. Confirmación final
    if total_deleted > 0:
        confirm = input(
            f"\n⚠️ SE BORRARÁN {total_deleted} REGISTROS. ¿Proceder? (s/n): "
        )
        if confirm.lower() == "s":
            db.commit()
            print("\n🚀 Cambios aplicados exitosamente.")
        else:
            db.rollback()
            print("\n❌ Operación cancelada. No se movió nada.")
    else:
        print("\n✨ No se encontraron logs duplicados para hoy.")

    db.close()


if __name__ == "__main__":
    cleanup_today_logs()
