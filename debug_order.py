import sys
from tasks.scraper.drone_scraper import DroneScraper

# ID del pedido rebelde (cámbialo si es otro)
ORDER_ID = "106893" 

if len(sys.argv) > 1:
    ORDER_ID = sys.argv[1]

def diagnose():
    print(f"🕵️‍♂️ DIAGNOSTICANDO PEDIDO #{ORDER_ID}...")
    
    drone = DroneScraper()
    if not drone.login():
        print("❌ Error de Login")
        return

    try:
        # Extraemos la data CRUDA
        print("🚀 Extrayendo datos...")
        data = drone.scrape_detail(ORDER_ID, mode='full')
        
        print("\n--- RESULTADOS DEL ROBOT ---")
        print(f"ID Externo: {data.get('external_id')}")
        print(f"Texto Estatus (RAW HTML): '{data.get('status_text')}'")  # <--- ESTO ES LO IMPORTANTE
        print(f"Conductor: '{data.get('driver_name')}'")
        print(f"Monto: {data.get('total_amount')}")
        print("----------------------------\n")
        
        # Simulamos la lógica de decisión
        status_text = data.get('status_text', '').lower()
        db_status = "pending (default)"
        
        if "entregado" in status_text: db_status = "delivered"
        elif "cancelado" in status_text: db_status = "canceled"
        elif "asignado" in status_text: db_status = "driver_assigned"
        elif "camino" in status_text or "ruta" in status_text: db_status = "on_the_way"
        elif "proceso" in status_text: db_status = "processing"
        elif "confirmado" in status_text: db_status = "confirmed"
        
        print(f"⚖️ VEREDICTO DEL SISTEMA: El estatus se guardaría como: -> {db_status.upper()}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        drone.close_driver()

if __name__ == "__main__":
    diagnose()
