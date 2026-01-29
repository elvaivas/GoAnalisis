import logging
from tasks.scraper.customer_scraper import CustomerScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO)

def debug():
    print("🕵️‍♂️ INICIANDO ESPIONAJE DE CLIENTES...")
    s = CustomerScraper()
    if not s.login(): return print("❌ Login falló")
    
    s.driver.get(s.users_url)
    WebDriverWait(s.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
    
    # Imprimir cabeceras para ver el orden
    headers = s.driver.find_elements(By.TAG_NAME, "th")
    print(f"CABECERAS: {[h.text for h in headers]}")
    
    # Imprimir primeras 5 filas completas
    rows = s.driver.find_elements(By.XPATH, "//table/tbody/tr")
    for i, row in enumerate(rows[:5]):
        cols = row.find_elements(By.TAG_NAME, "td")
        print(f"\n--- FILA {i+1} ---")
        for j, col in enumerate(cols):
            print(f"Col {j}: '{col.text}'")
            
    s.close_driver()

if __name__ == "__main__":
    debug()
