import logging
from app.db.session import SessionLocal
from app.db.base import Store
from tasks.scraper.store_scraper import StoreScraper

logging.basicConfig(level=logging.INFO)


def force_sync():
    print("🚀 Iniciando extracción de tiendas desde Legacy...")
    scraper = StoreScraper()
    stores_info = scraper.scrape_store_list()
    scraper.close_driver()

    if not stores_info:
        print("❌ El scraper no devolvió datos.")
        return

    print(f"✅ Se extrajeron {len(stores_info)} perfiles. Sincronizando BD...")
    db = SessionLocal()
    matched = 0

    for s_data in stores_info:
        # Buscamos en BD ignorando mayúsculas y espacios
        store = (
            db.query(Store)
            .filter(Store.name.ilike(f"%{s_data['name'].strip()}%"))
            .first()
        )

        if store:
            store.company_name = s_data["company_name"]
            store.name = s_data["name"]
            matched += 1
            print(f"🔗 Match: {store.name} -> Empresa: {store.company_name}")
        else:
            print(f"⚠️ NO MATCH en BD: ID={s_data['id']} | Nombre={s_data['name']}")

    db.commit()
    db.close()
    print(
        f"\n🎯 Proceso finalizado. Tiendas actualizadas: {matched}/{len(stores_info)}"
    )


if __name__ == "__main__":
    force_sync()
