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

    def enforce_store_status(self, store_name, desired_status_bool):
        """
        store_name: Nombre de la farmacia (ej: 'INVERSIONES LENOY')
        desired_status_bool: True (Encender) / False (Apagar)
        """
        if not self.driver:
            self.login()

        try:
            self.driver.get(self.LIST_URL)
            wait = WebDriverWait(self.driver, 10)

            # 1. BUSCAR POR NOMBRE (Estrategia Flexible)
            # Usamos solo las primeras palabras para evitar errores de espacios o typos
            search_term = store_name.split()[0]
            if len(search_term) < 4 and len(store_name.split()) > 1:
                search_term = store_name.split()[0] + " " + store_name.split()[1]

            logger.info(f"🔍 Buscando '{search_term}' (Original: {store_name})...")

            search_input = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='search']")
                )
            )
            search_input.clear()
            search_input.send_keys(search_term)
            time.sleep(3)

            # 2. IDENTIFICAR EL ID REAL DESDE EL TEXTO "ID:XX"
            # Ahora buscamos el ID en CUALQUIER fila visible, asumiendo que el buscador filtró bien.
            try:
                # Buscamos cualquier elemento que contenga "ID:"
                id_elements = self.driver.find_elements(
                    By.XPATH, "//div[contains(text(), 'ID:')]"
                )

                real_legacy_id = None

                # Iteramos para encontrar el que corresponde al nombre correcto
                for el in id_elements:
                    # Subimos al padre (tr o div contenedor) para ver el nombre asociado
                    # Esta lógica depende de la estructura, pero simplificaremos:
                    # Si solo hay 1 resultado, ese es.
                    if len(id_elements) == 1:
                        real_legacy_id = re.search(r"\d+", el.text).group()
                        break

                    # Si hay varios, intentamos ver si el nombre está cerca
                    # (Esto es complejo, pero por ahora el buscador debería ser preciso)

                if not real_legacy_id and id_elements:
                    real_legacy_id = re.search(r"\d+", id_elements[0].text).group()

                if real_legacy_id:
                    logger.info(f"🎯 ID Real Detectado: {real_legacy_id}")
                else:
                    raise Exception("No se encontró texto ID:XX")

            except Exception as e:
                logger.error(f"❌ No se pudo encontrar el ID para: {store_name} ({e})")
                return False

            # 3. LOCALIZAR EL INTERRUPTOR CORRECTO
            checkbox_id = f"activeCheckbox{real_legacy_id}"
            checkbox = self.driver.find_element(By.ID, checkbox_id)

            # 4. EVALUAR ESTADO
            is_on = checkbox.get_attribute("checked") is not None
            logger.info(
                f"Estado de {store_name} (#{real_legacy_id}): {'ON' if is_on else 'OFF'}"
            )

            # 5. ACTUAR (SOLO APAGAR)
            if not desired_status_bool and is_on:
                logger.info(f"🔌 APAGANDO {store_name}...")

                label = self.driver.find_element(
                    By.CSS_SELECTOR, f"label[for='{checkbox_id}']"
                )

                # Clic Humano (Pointer Events)
                loc = label.location
                self._super_click(label, loc["x"], loc["y"])

                # Confirmar SweetAlert
                try:
                    confirm = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".swal2-confirm"))
                    )
                    confirm.click()
                    logger.info(f"✅ {store_name} apagada exitosamente.")
                except:
                    pass

                return True

            return True

        except Exception as e:
            logger.error(f"❌ Error controlando {store_name}: {e}")
            return False
