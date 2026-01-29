import logging
from tasks.scraper.order_scraper import OrderScraper
from tasks.celery_tasks import process_drone_data
from tasks.scraper.drone_scraper import DroneScraper
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_recovery():
    print("🚀 Iniciando recuperación de últimas 48 horas...")
    
    ls = OrderScraper()
    if not ls.login(): return

    # Leemos 10 páginas para asegurar que agarramos todo lo de ayer
    print("📄 Escaneando últimas 10 páginas...")
    items = ls.get_historical_ids(max_pages=10) 
    ls.close_driver()
    
    print(f"📦 Encontrados {len(items)} pedidos recientes. Procesando faltantes...")

    db = SessionLocal()
    drone = DroneScraper()
    if not drone.login(): return

    count = 0
    for item in items:
        eid = item['id']
        duration = item['duration']
        
        # Entramos SIEMPRE para asegurar que tenga la data correcta
        print(f"🔍 ({count+1}/{len(items)}) Verificando #{eid}...")
        data = drone.scrape_detail(eid, mode='full')
        data['duration_text'] = duration # Inyectamos duración de lista
        
        process_drone_data(db, data)
        count += 1

    drone.close_driver()
    db.close()
    print("✅ Recuperación finalizada.")

if __name__ == "__main__":
    run_recovery()
