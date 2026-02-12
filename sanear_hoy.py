import logging
from sqlalchemy import asc
from app.db.session import SessionLocal
from app.db.base import Order, OrderStatusLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def sanear_historial_completo():
    db = SessionLocal()
    print("\n🧹 INICIANDO SANEAMIENTO INTELIGENTE DE LOGS 🧹")
    print("====================================================")

    # Traemos todos los pedidos que tienen más de 1 log
    orders = db.query(Order).all()
    total_borrados = 0
    pedidos_afectados = 0

    for o in orders:
        logs = (
            db.query(OrderStatusLog)
            .filter(OrderStatusLog.order_id == o.id)
            .order_by(asc(OrderStatusLog.timestamp))
            .all()
        )

        if len(logs) <= 1:
            continue

        logs_a_borrar = []
        estados_vistos = set()
        estado_final_alcanzado = False

        for log in logs:
            estado_actual = log.status.lower().strip()

            # REGLA 1: Si ya habíamos llegado a un estado final (entregado/cancelado)
            # cualquier log que aparezca después (incluso otro entregado) es basura de re-escaneo.
            if estado_final_alcanzado:
                logs_a_borrar.append(log)
                continue

            # REGLA 2: Si este estado ya lo habíamos pasado antes (Ej: volvemos a Pending)
            # es un "rebote" del robot (falso positivo). Lo borramos.
            if estado_actual in estados_vistos:
                logs_a_borrar.append(log)
                continue

            # Si pasa las pruebas, es un log legítimo. Lo anotamos como "visto".
            estados_vistos.add(estado_actual)

            # Si este log legítimo es el final, activamos la bandera para matar todo lo que siga.
            if estado_actual in ["delivered", "canceled"]:
                estado_final_alcanzado = True

        # Ejecutamos el borrado para este pedido
        if logs_a_borrar:
            print(
                f"📦 Pedido #{o.external_id}: Borrando {len(logs_a_borrar)} logs (Rebotes/Zombies)."
            )
            for basura in logs_a_borrar:
                db.delete(basura)
            total_borrados += len(logs_a_borrar)
            pedidos_afectados += 1

    if total_borrados > 0:
        print(
            f"\n⚠️ RESUMEN: Se borrarán {total_borrados} logs en {pedidos_afectados} pedidos."
        )
        confirm = input("¿Proceder con la amputación? (s/n): ")

        if confirm.lower() == "s":
            db.commit()
            print("✅ Limpieza Quirúrgica completada.")
        else:
            db.rollback()
            print("❌ Operación cancelada. No se tocó la BD.")
    else:
        print("\n✨ La Base de Datos está inmaculada. No hay rebotes.")

    db.close()


if __name__ == "__main__":
    sanear_historial_completo()
