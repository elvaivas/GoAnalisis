from app.db.session import SessionLocal
from app.db.base import StoreSchedule, Store
from datetime import datetime, timedelta


def debug_time_and_rules():
    db = SessionLocal()

    # 1. VERIFICAR HORA Y DÍA DEL SISTEMA
    now_utc = datetime.utcnow()
    now_vet = now_utc - timedelta(hours=4)
    current_day = now_vet.weekday()  # 0=Lunes, 5=Sábado, 6=Domingo

    print("\n🕒 DIAGNÓSTICO DE TIEMPO")
    print("========================")
    print(f"Hora UTC: {now_utc}")
    print(f"Hora VET: {now_vet}")
    print(f"Día Numérico (Python): {current_day}")

    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    print(f"Día Humano: {dias[current_day]}")

    # 2. VERIFICAR REGLAS EN DB
    print("\n📋 REGLAS GUARDADAS EN DB")
    print("========================")
    rules = db.query(StoreSchedule).all()

    if not rules:
        print("❌ LA BASE DE DATOS ESTÁ VACÍA (No hay reglas).")
    else:
        for r in rules:
            store = db.query(Store).get(r.store_id)
            store_name = store.name if store else "ID Desconocido"
            status = "✅ ACTIVA" if r.is_active else "❌ INACTIVA"
            match = "👈 ¡ES HOY!" if r.day_of_week == current_day else ""

            print(
                f"ID: {r.id} | Tienda: {store_name} | Día: {r.day_of_week} ({dias[r.day_of_week]}) | {status} {match}"
            )

    db.close()


if __name__ == "__main__":
    debug_time_and_rules()
