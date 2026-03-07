import logging
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StoreScraper:
    def __init__(self):
        self.base_url = f"{settings.LEGACY_BASE_URL}/login/admin"
        self.driver = None

    def setup_driver(self):
        if self.driver:
            return
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-allow-origins=*")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )

        # --- INICIO NATIVO SRE ---
        self.driver = webdriver.Chrome(options=chrome_options)

        # Escudo SRE: Timeout de 30s contra desconexiones
        self.driver.set_page_load_timeout(30)
        self.driver.set_script_timeout(30)

    def scrape_store_list(self) -> list:
        """
        Escanea la lista principal de tiendas para extraer Empresa, Sucursal e ID real.
        """
        if not self.driver:
            self.setup_driver()
            self.login()

        # Usamos la URL base de los settings para mayor seguridad
        url = f"{settings.LEGACY_BASE_URL}/admin/store/list"
        stores_data = []

        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "columnSearchDatatable"))
            )

            rows = self.driver.find_elements(
                By.XPATH, "//table[@id='columnSearchDatatable']/tbody/tr"
            )
            for row in rows:
                try:
                    # 1. Empresa (Badge azul)
                    company_el = row.find_element(
                        By.XPATH, ".//span[contains(@class, 'badge-soft-info')]"
                    )
                    company_name = company_el.text.replace("...", "").strip()

                    # 2. Sucursal (Texto con title completo)
                    title_el = row.find_element(
                        By.XPATH, ".//div[contains(@class, 'text--title')]"
                    )
                    store_name = title_el.get_attribute("title").strip()

                    # 3. ID (Texto debajo del nombre)
                    id_el = row.find_element(
                        By.XPATH,
                        ".//div[contains(@class, 'font-light') and contains(text(), 'ID:')]",
                    )
                    store_id = id_el.text.replace("ID:", "").strip()

                    if store_id.isdigit():
                        stores_data.append(
                            {
                                "id": store_id,
                                "company_name": company_name,
                                "name": store_name,
                            }
                        )
                except:
                    continue

        except Exception as e:
            logger.error(f"Error scraping store list: {e}")

        return stores_data

    def login(self) -> bool:
        if not self.driver:
            self.setup_driver()
        try:
            self.driver.get(self.base_url)
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.presence_of_element_located((By.NAME, "email"))).send_keys(
                settings.GOPHARMA_EMAIL
            )
            self.driver.find_element(By.NAME, "password").send_keys(
                settings.GOPHARMA_PASSWORD
            )
            try:
                self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            except:
                self.driver.find_element(By.NAME, "password").submit()
            time.sleep(3)
            return "login" not in self.driver.current_url
        except:
            return False

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def scrape_commission(self, store_real_id: str) -> float:
        """
        Entra a la configuración de la tienda y saca el % de comisión.
        Url objetivo: .../admin/store/view/{id}/business_plan
        """
        if not self.driver:
            self.setup_driver()
            self.login()

        url = f"https://ecosistema.gopharma.com.ve/admin/store/view/{store_real_id}/business_plan"

        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # 1. Intentar sacar del input ID="comission"
            try:
                input_el = self.driver.find_element(By.ID, "comission")
                val = input_el.get_attribute("value")
                return float(val)
            except:
                pass

            # 2. Intentar sacar del texto "10 % Comisión"
            try:
                body = self.driver.find_element(By.TAG_NAME, "body").text
                match = re.search(r"(\d+(?:\.\d+)?)%\s*comisión", body, re.IGNORECASE)
                if match:
                    return float(match.group(1))
            except:
                pass

        except Exception as e:
            logger.error(f"Error scraping store {store_real_id}: {e}")

        return 0.0
