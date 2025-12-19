import logging
import re
import time
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

class StoreScraper:
    def __init__(self):
        self.base_url = "https://ecosistema.gopharma.com.ve/login/admin"
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

    def scrape_commission(self, store_real_id: str) -> float:
        """
        Entra a la configuración de la tienda y saca el % de comisión.
        Url objetivo: .../admin/store/view/{id}/business_plan
        """
        if not self.driver: self.setup_driver(); self.login()
        
        url = f"https://ecosistema.gopharma.com.ve/admin/store/view/{store_real_id}/business_plan"
        
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # 1. Intentar sacar del input ID="comission"
            try:
                input_el = self.driver.find_element(By.ID, "comission")
                val = input_el.get_attribute("value")
                return float(val)
            except: pass

            # 2. Intentar sacar del texto "10 % Comisión"
            try:
                body = self.driver.find_element(By.TAG_NAME, "body").text
                match = re.search(r"(\d+(?:\.\d+)?)%\s*comisión", body, re.IGNORECASE)
                if match: return float(match.group(1))
            except: pass

        except Exception as e:
            logger.error(f"Error scraping store {store_real_id}: {e}")
        
        return 0.0
