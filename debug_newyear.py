import logging
from tasks.scraper.order_scraper import OrderScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configurar logs para verlos en consola
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_now():
    print("\n🕵️‍♂️ INICIANDO DIAGNÓSTICO DE AÑO NUEVO...\n")
    
    scraper = OrderScraper()
    if not scraper.login():
        print("❌ Error de Login.")
        return

    print("🕷️ Navegando a la lista de pedidos...")
    scraper.driver.get(scraper.orders_url)
    
    try:
        WebDriverWait(scraper.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # 1. Verificación de IDs
        print("\n--- PRUEBA 1: BUSCANDO IDs ---")
        links = scraper.driver.find_elements(By.CSS_SELECTOR, "a[href*='/admin/order/details/']")
        if links:
            print(f"✅ Se encontraron {len(links)} enlaces de detalle.")
            print(f"Ejemplo ID: {links[0].get_attribute('href')}")
        else:
            print("❌ NO SE ENCONTRARON ENLACES DE PEDIDOS. ¿Cambió el selector?")

        # 2. Verificación de Fechas (La parte crítica)
        print("\n--- PRUEBA 2: LECTURA DE FECHAS ---")
        rows = scraper.driver.find_elements(By.XPATH, "//table/tbody/tr")
        count = 0
        for row in rows:
            text = row.text
            # Filtramos filas vacías o de carrito para ver solo pedidos reales
            if "Procesado" in text or "Entregado" in text:
                print(f"\n[FILA {count+1}] Texto completo:")
                print(text)
                print("-" * 20)
                count += 1
            if count >= 3: break
            
    except Exception as e:
        print(f"💥 Error durante el diagnóstico: {e}")
    finally:
        scraper.close_driver()
        print("\n🏁 Diagnóstico finalizado.")

if __name__ == "__main__":
    debug_now()
