from sqlalchemy import text
from app.db.session import SessionLocal

def check_weird_pickups():
    db = SessionLocal()
    print("🕵️‍♂️ BUSCANDO FALSOS PICKUPS (Versión Compatible Postgres)...")
    
    # CASO 1: Pickup pero TIENE un Driver asignado
    # Corrección: Usamos order_type::text para evitar error de Enum
    sql_drivers = text("""
        SELECT external_id, order_type, driver_id, distance_km 
        FROM orders 
        WHERE order_type::text = 'Pickup' AND driver_id IS NOT NULL;
    """)
    
    try:
        results_drivers = db.execute(sql_drivers).fetchall()
        print(f"\n🚨 CASO 1: Pickups que tienen ID de Chofer en DB ({len(results_drivers)}):")
        for r in results_drivers:
            print(f"   - #{r.external_id} (Dist: {r.distance_km}km) -> DriverID: {r.driver_id}")
    except Exception as e:
        print(f"Error en Caso 1: {e}")

    # CASO 2: Pickup con distancia sospechosa (> 0.5 km)
    sql_dist = text("""
        SELECT external_id, order_type, distance_km 
        FROM orders 
        WHERE order_type::text = 'Pickup' AND distance_km > 0.5;
    """)
    
    try:
        results_dist = db.execute(sql_dist).fetchall()
        print(f"\n🚨 CASO 2: Pickups con distancia larga (>0.5km) ({len(results_dist)}):")
        for r in results_dist:
            print(f"   - #{r.external_id} -> {r.distance_km} km")
    except Exception as e:
        print(f"Error en Caso 2: {e}")

    db.close()

if __name__ == "__main__":
    check_weird_pickups()
