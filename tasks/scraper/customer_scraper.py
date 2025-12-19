import logging
import re
import time
from typing import List, Dict, Any
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CustomerScraper:
    def __init__(self):
        self.base_url = "https://ecosistema.gopharma.com.ve/login/admin"
        self.users_url = "https://ecosistema.gopharma.com.ve/admin/users/customer/list"
        self.driver = None

    def setup_driver(self):
        if self.driver: return
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-allow-origins=*")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        service = ChromeService(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

    def login(self) -> bool:
        if not self.driver: self.setup_driver()
        try:
            self.driver.get(self.base_url)
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.presence_of_element_located((By.NAME, "email"))).send_keys(settings.GOPHARMA_EMAIL)
            self.driver.find_element(By.NAME, "password").send_keys(settings.GOPHARMA_PASSWORD)
            try: self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            except: self.driver.find_element(By.NAME, "password").submit()
            time.sleep(3)
            return "login" not in self.driver.current_url
        except: return False

    def close_driver(self):
        if self.driver:
            try: self.driver.quit()
            except: pass
            self.driver = None

    def _parse_spanish_date(self, text):
        if not text: return None
        month_map = {'ene':'01','feb':'02','mar':'03','abr':'04','may':'05','jun':'06','jul':'07','ago':'08','sep':'09','oct':'10','nov':'11','dic':'12'}
        try:
            clean = text.lower().replace('.', '')
            for m, n in month_map.items():
                if m in clean: clean = clean.replace(m, n); break
            match = re.search(r'(\d{1,2})\s+(\d{2})\s+(\d{4})', clean)
            if match:
                return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", '%d %m %Y')
        except: pass
        return None

    def scrape_customers(self, max_pages: int = None) -> List[Dict]:
        """
        Si max_pages es None, recorre hasta el final de la lista.
        Si max_pages es un número (ej: 5), solo revisa esas páginas (Modo Vigilancia).
        """
        if not self.driver: self.setup_driver(); self.login()
        customers_data = []
        
        try:
            logger.info(f"👥 Scrapeando Clientes: {self.users_url}")
            self.driver.get(self.users_url)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "datatable")))

            current_page = 1
            
            while True:
                # 1. Freno de mano (Opcional)
                if max_pages and current_page > max_pages:
                    logger.info(f"🛑 Límite de vigilancia alcanzado ({max_pages} pág). Deteniendo.")
                    break

                logger.info(f"   📄 Procesando página de clientes {current_page}...")
                
                rows = self.driver.find_elements(By.XPATH, "//table[@id='datatable']/tbody/tr")
                
                for row in rows:
                    try:
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) < 7: continue
                        
                        name = cols[1].text.split('\n')[0].strip()
                        
                        phone = None
                        try:
                            phone_el = cols[3].find_element(By.XPATH, ".//a[contains(@href, 'tel:')]")
                            phone = phone_el.text.strip()
                        except: pass
                        
                        # Columna 6 (index 6) es Fecha de Ingreso
                        date_text = cols[6].text.strip()
                        joined_at = self._parse_spanish_date(date_text)

                        if name and joined_at:
                            customers_data.append({
                                "name": name,
                                "phone": phone,
                                "joined_at": joined_at
                            })
                    except: continue

                # 2. Paginación Infinita
                try:
                    next_btn = self.driver.find_element(By.XPATH, "//a[@aria-label='Next »']")
                    parent = next_btn.find_element(By.XPATH, "./..")
                    
                    # Si el botón está deshabilitado, llegamos al final REAL
                    if "disabled" in parent.get_attribute("class"):
                        logger.info("🚫 Fin de lista de clientes (Última página alcanzada).")
                        break
                    
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    time.sleep(2)
                    current_page += 1
                except: 
                    logger.info("🚫 No se encontró botón siguiente.")
                    break

        except Exception as e:
            logger.error(f"Error scraping customers: {e}")
        
        return customers_data
