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
        if not self.driver:
            self.login()

        try:
            self.driver.get(self.LIST_URL)
            wait = WebDriverWait(self.driver, 10)

            # 1. BUSCAR POR NOMBRE
            # Usamos el nombre lo más completo posible para que el Legacy filtre bien
            search_input = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='search']")
                )
            )
            search_input.clear()
            search_input.send_keys(store_name)

            # ESPERA CRÍTICA: Esperamos a que la tabla se actualice y SOLO muestre la tienda deseada
            # Buscamos el texto del nombre dentro de la tabla
            time.sleep(4)

            # 2. IDENTIFICAR EL ID REAL (Búsqueda exacta en la fila)
            try:
                # Buscamos la fila (tr) que contiene el nombre exacto de la tienda
                # y de esa misma fila sacamos el ID
                xpath_row = f"//tr[contains(., '{store_name}')]"
                row_element = self.driver.find_element(By.XPATH, xpath_row)

                # Extraemos el ID solo de esa fila
                id_text = re.search(r"ID:(\d+)", row_element.text).group(1)
                real_legacy_id = id_text
                logger.info(
                    f"🎯 ID Correcto detectado para '{store_name}': {real_legacy_id}"
                )
            except Exception as e:
                logger.error(
                    f"❌ No se pudo encontrar la fila o el ID para: {store_name}"
                )
                return False

            # 3. LOCALIZAR EL INTERRUPTOR (App Online/Offline)
            checkbox_id = f"activeCheckbox{real_legacy_id}"
            checkbox = self.driver.find_element(By.ID, checkbox_id)

            # 4. EVALUAR ESTADO REAL (Vía Propiedad JS, más fiable que atributos)
            is_on = self.driver.execute_script(
                f"return document.getElementById('{checkbox_id}').checked;"
            )

            logger.info(
                f"Estado de {store_name} (#{real_legacy_id}): {'ON' if is_on else 'OFF'}"
            )

            # 5. ACTUAR (SOLO APAGAR)
            if not desired_status_bool and is_on:
                logger.info(f"🔌 APAGANDO App para {store_name}...")

                # Clic en el label que controla ese checkbox ID
                label = self.driver.find_element(
                    By.CSS_SELECTOR, f"label[for='{checkbox_id}']"
                )

                # Scroll hasta el elemento para que sea visible y clickeable
                self.driver.execute_script("arguments[0].scrollIntoView();", label)
                time.sleep(0.5)

                # Clic Humano
                loc = label.location
                self._super_click(label, loc["x"], loc["y"])

                # 6. CONFIRMAR ALERTA (SweetAlert)
                try:
                    confirm = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".swal2-confirm"))
                    )
                    confirm.click()
                    logger.info("✅ Confirmación aceptada.")
                    time.sleep(2)  # Esperar que el servidor procese el cambio
                except:
                    pass

                return True

            return True

        except Exception as e:
            logger.error(f"❌ Error en tienda {store_name}: {e}")
            return False
