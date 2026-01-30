import logging
from app.db.session import SessionLocal
from tasks.scraper.order_scraper import OrderScraper
from tasks.scraper.drone_scraper import DroneScraper
from tasks.celery_tasks import process_drone_data

# Configurar logs para ver el progreso
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def poblar_base_datos_local():
    print("🌱 INICIANDO POBLADO DE BASE DE DATOS LOCAL...")
    
    # 1. Configurar Scrapers
    # NOTA: Asegúrate de tener las credenciales en tu .env local
    ls = OrderScraper()
    drone = DroneScraper()
    db = SessionLocal()

    if not ls.login():
        print("❌ Error: No se pudo loguear el OrderScraper. Revisa tu .env")
        return

    # 2. Obtener lista de pedidos (Backfill)
    # Traemos 15 páginas (~375 pedidos) para tener data suficiente para probar
    PAGINAS_A_ESCANEAR = 15
    print(f"📄 Escaneando las últimas {PAGINAS_A_ESCANEAR} páginas del Legacy...")
    
    items = ls.get_historical_ids(max_pages=PAGINAS_A_ESCANEAR)
    ls.close_driver()
    
    print(f"📦 Se encontraron {len(items)} pedidos. Iniciando extracción detallada...")

    if not drone.login():
        print("❌ Error: No se pudo loguear el Dron.")
        return

    # 3. Procesar cada pedido
    count = 0
    for item in items:
        count += 1
        eid = item['id']
        duration = item.get('duration', '')
        
        print(f"📥 [{count}/{len(items)}] Importando Pedido #{eid}...")
        
        try:
            # Extraer detalle completo (Finanzas, Mapa, Items)
            data = drone.scrape_detail(eid, mode='full')
            data['duration_text'] = duration
            
            # Guardar en Postgres Local
            process_drone_data(db, data)
            
        except Exception as e:
            print(f"⚠️ Error en {eid}: {e}")

    drone.close_driver()
    db.close()
    print("✅ ¡BASE DE DATOS LOCAL LISTA! Ya puedes desarrollar.")

if __name__ == "__main__":
    poblar_base_datos_local()