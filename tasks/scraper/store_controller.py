import logging
import time
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StoreControllerScraper:
    def __init__(self):
        self.BASE_URL = "https://ecosistema.gopharma.com.ve"
        self.LOGIN_URL = f"{self.BASE_URL}/login/admin"
        self.LIST_URL = f"{self.BASE_URL}/admin/store/list"
        self.driver = None

    def setup_driver(self):
        if self.driver:
            return
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(
            "--window-size=1920,1080"
        )  # Pantalla grande para ver toda la tabla
        options.add_argument("--disable-blink-features=AutomationControlled")

        try:
            driver_path = ChromeDriverManager().install()
            service = Service(executable_path=driver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
        except:
            service = Service(executable_path="/usr/bin/chromedriver")
            self.driver = webdriver.Chrome(service=service, options=options)

    def login(self):
        if not self.driver:
            self.setup_driver()
        try:
            self.driver.get(self.LOGIN_URL)
            wait = WebDriverWait(self.driver, 15)
            email = wait.until(EC.presence_of_element_located((By.NAME, "email")))
            email.clear()
            email.send_keys(settings.GOPHARMA_EMAIL)
            self.driver.find_element(By.NAME, "password").send_keys(
                settings.GOPHARMA_PASSWORD
            )

            btn = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            self.driver.execute_script("arguments[0].click();", btn)
            time.sleep(5)
            return True
        except:
            return False

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _super_click(self, element, x, y):
        """Simula presión humana sobre un elemento específico"""
        try:
            # Flutter/Web moderno necesita: Down -> Wait -> Up
            js_down = f"""
                var target = arguments[0];
                var opts = {{ bubbles: true, cancelable: true, view: window, clientX: {x}, clientY: {y}, pointerId: 1, pointerType: 'mouse', buttons: 1 }};
                target.dispatchEvent(new PointerEvent('pointerdown', opts));
                target.dispatchEvent(new MouseEvent('mousedown', opts));
            """
            self.driver.execute_script(js_down, element)
            time.sleep(0.2)
            js_up = f"""
                var target = arguments[0];
                var opts = {{ bubbles: true, cancelable: true, view: window, clientX: {x}, clientY: {y}, pointerId: 1, pointerType: 'mouse', buttons: 0 }};
                target.dispatchEvent(new PointerEvent('pointerup', opts));
                target.dispatchEvent(new MouseEvent('mouseup', opts));
                target.dispatchEvent(new MouseEvent('click', opts));
            """
            self.driver.execute_script(js_up, element)
            return True
        except:
            return False

    def enforce_store_status(self, store_name, store_external_id, desired_status_bool):
        if not self.driver: self.login()
        
        try:
            self.driver.get(self.LIST_URL)
            wait = WebDriverWait(self.driver, 10)
            
            # 1. EXTRAER EL NÚMERO DE ID DE TU DB (store_3 -> 3)
            real_id_to_find = re.search(r'\d+', store_external_id).group()

            # 2. GENERAR TÉRMINO DE BÚSQUEDA POR NOMBRE (Para que el Legacy filtre)
            clean_name = store_name.replace("C.A.", "").replace("S.A.", "").replace(",", "").replace(".", "").strip()
            search_term = clean_name.split()[0] # Usamos solo la primera palabra para que aparezca sí o sí
            
            logger.info(f"🔍 Buscando '{search_term}' en página para encontrar ID Legacy: {real_id_to_find}")
            
            search_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='search']")))
            search_input.clear()
            search_input.send_keys(search_term)
            time.sleep(4) 

            # 3. LOCALIZAR LA FILA QUE TENGA EL ID EXACTO
            # Buscamos en la tabla filtrada la fila que contenga "ID:3" o "ID: 3"
            try:
                xpath_row = f"//tr[contains(., 'ID:{real_id_to_find}') or contains(., 'ID: {real_id_to_find}')]"
                row_element = self.driver.find_element(By.XPATH, xpath_row)
                logger.info(f"🎯 Fila de la tienda #{real_id_to_find} encontrada exitosamente.")
            except:
                logger.error(f"❌ El Legacy no muestra ninguna tienda con ID: {real_id_to_find} al buscar '{search_term}'")
                return False

            # 4. LOCALIZAR EL INTERRUPTOR DENTRO DE ESA FILA
            checkbox_id = f"activeCheckbox{real_id_to_find}"
            checkbox = self.driver.find_element(By.ID, checkbox_id)

            # 5. EVALUAR ESTADO
            is_on = self.driver.execute_script(f"return document.getElementById('{checkbox_id}').checked;")
            
            # 6. ACTUAR (SOLO APAGAR)
            if not desired_status_bool and is_on:
                logger.info(f"🔌 [ACCIÓN REAL] Apagando {store_name} (#{real_id_to_find})...")
                label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{checkbox_id}']")
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", label)
                time.sleep(0.5)
                self._super_click(label, label.location['x'], label.location['y'])
                
                try:
                    confirm = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".swal2-confirm, .confirm"))
                    )
                    confirm.click()
                    time.sleep(2) 
                except: pass
                return True
            
            return False

        except Exception as e:
            logger.error(f"❌ Error en auditoría de {store_name}: {e}")
            return False