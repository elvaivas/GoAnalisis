import logging
from sqlalchemy import func
from app.db.session import SessionLocal
from app.db.base import Order

# Configuración básica
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def diagnose_kpi():
    db = SessionLocal()
    print("\n🕵️‍♂️ DIAGNÓSTICO DE KPI LOCAL")
    print("============================")

    # 1. Ver si hay pedidos en general
    total_orders = db.query(Order).count()
    print(f"📦 Total Pedidos en DB: {total_orders}")

    if total_orders == 0:
        print("❌ ERROR: La base de datos está vacía. Ejecuta init_local_db.py")
        return

    # 2. Ver una muestra de 10 pedidos para ver sus datos financieros
    orders = db.query(Order).limit(10).all()

    print("\n📊 Muestra de Datos (Primeros 10):")
    print(
        f"{'ID':<10} | {'TIPO':<10} | {'TOTAL($)':<10} | {'DELIV FEE($)':<15} | {'ESTATUS':<10}"
    )
    print("-" * 70)

    count_delivery = 0
    accum_fee = 0.0

    for o in orders:
        # Lógica idéntica al servicio
        raw = o.order_type
        o_type_str = raw.value if hasattr(raw, "value") else str(raw)
        if o_type_str == "None":
            o_type_str = "Delivery"

        # Lógica de Fee
        fee_raw = o.delivery_fee
        gross_fee = o.gross_delivery_fee

        calc_fee = float(gross_fee if gross_fee and gross_fee > 0 else (fee_raw or 0.0))

        print(
            f"{o.external_id:<10} | {o_type_str:<10} | {o.total_amount:<10} | {calc_fee:<15} | {o.current_status}"
        )

        if o_type_str == "Delivery":
            count_delivery += 1
            accum_fee += calc_fee

    print("-" * 70)
    print(f"🧮 Simulación rápida:")
    print(f"   Deliveries contados: {count_delivery}")
    print(f"   Fees Acumulados: {accum_fee}")

    if count_delivery > 0:
        print(f"   👉 PROMEDIO ENVÍO: {accum_fee / count_delivery}")
    else:
        print(f"   👉 PROMEDIO ENVÍO: 0 (No hay deliveries)")

    db.close()


if __name__ == "__main__":
    diagnose_kpi()
