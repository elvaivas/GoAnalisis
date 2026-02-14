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

            # 1. LIMPIEZA DE NOMBRE PARA BÚSQUEDA
            # Quitamos siglas y usamos las primeras 2 palabras para ser específicos pero flexibles
            clean_name = (
                store_name.replace("C.A.", "")
                .replace("S.A.", "")
                .replace(",", "")
                .replace(".", "")
                .strip()
            )
            parts = clean_name.split()

            # Si el nombre es "GRUPO FARMAYA", buscamos "FARMAYA" (la palabra más única)
            # Si es "FARMACIA MUÑOZ", buscamos "MUÑOZ"
            generics = [
                "FARMACIA",
                "FARMACIAS",
                "SUCURSAL",
                "INVERSIONES",
                "GRUPO",
                "SUCURLSAL",
            ]
            if parts[0].upper() in generics and len(parts) > 1:
                search_term = parts[1]
            else:
                search_term = parts[0]

            logger.info(f"🔍 Buscando por palabra clave: '{search_term}'...")

            search_input = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='search']")
                )
            )
            search_input.clear()
            search_input.send_keys(search_term)

            # Esperamos que la tabla termine de filtrar (Flutter/DataTables delay)
            time.sleep(5)

            # 2. IDENTIFICAR EL ID REAL (Búsqueda por coincidencia de texto)
            try:
                # Buscamos todas las filas visibles
                rows = self.driver.find_elements(
                    By.XPATH, "//tr[contains(@role, 'row')]"
                )
                real_legacy_id = None

                for row in rows:
                    row_text = row.text.upper()
                    # Si la fila contiene la palabra clave Y el nombre original (parcialmente)
                    if search_term.upper() in row_text:
                        id_match = re.search(r"ID:(\d+)", row.text)
                        if id_match:
                            real_legacy_id = id_match.group(1)
                            break

                if not real_legacy_id:
                    raise Exception(
                        f"No se encontró el patrón ID:XX en los resultados de '{search_term}'"
                    )

                logger.info(
                    f"🎯 ID Correcto detectado para '{store_name}': {real_legacy_id}"
                )
            except Exception as e:
                self.driver.save_screenshot(f"/tmp/error_{search_term}.png")
                logger.error(f"❌ Error buscando ID para {store_name}: {e}")
                return False

            # 3. LOCALIZAR EL INTERRUPTOR
            checkbox_id = f"activeCheckbox{real_legacy_id}"
            checkbox = self.driver.find_element(By.ID, checkbox_id)

            # 4. EVALUAR ESTADO REAL
            is_on = self.driver.execute_script(
                f"return document.getElementById('{checkbox_id}').checked;"
            )
            logger.info(
                f"Estado de {store_name} (#{real_legacy_id}): {'ON' if is_on else 'OFF'}"
            )

            # 5. ACTUAR (SOLO APAGAR)
            if not desired_status_bool and is_on:
                logger.info(f"🔌 [ACCIÓN REAL] Apagando {store_name}...")
                label = self.driver.find_element(
                    By.CSS_SELECTOR, f"label[for='{checkbox_id}']"
                )

                # Asegurar visibilidad
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", label
                )
                time.sleep(0.5)

                # Clic Humano
                self._super_click(label, label.location["x"], label.location["y"])

                # 6. CONFIRMAR ALERTA
                try:
                    confirm = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".swal2-confirm"))
                    )
                    confirm.click()
                    time.sleep(2)
                except:
                    pass

                return True

            logger.info(f"⏹️ {store_name} ya estaba apagada.")
            return False

        except Exception as e:
            logger.error(f"❌ Error crítico en {store_name}: {e}")
            return False
