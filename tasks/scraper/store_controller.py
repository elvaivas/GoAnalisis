import logging
import time
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys  # <--- NECESARIO
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
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Opciones extra para estabilidad
        options.add_argument("--disable-gpu")
        options.add_argument("--ignore-certificate-errors")

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
            email = wait.until(EC.element_to_be_clickable((By.NAME, "email")))
            email.clear()
            email.send_keys(settings.GOPHARMA_EMAIL)

            pwd = self.driver.find_element(By.NAME, "password")
            pwd.clear()
            pwd.send_keys(settings.GOPHARMA_PASSWORD)

            btn = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            self.driver.execute_script("arguments[0].click();", btn)
            time.sleep(5)
            return True
        except Exception as e:
            logger.error(f"Error Login: {e}")
            return False

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def _super_click(self, element, x, y):
        """Simula presión humana sobre un elemento"""
        try:
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
            # Solo navegar si no estamos ya en la lista
            if "/admin/store/list" not in self.driver.current_url:
                self.driver.get(self.LIST_URL)

            wait = WebDriverWait(self.driver, 10)

            # 1. LIMPIEZA DEL NOMBRE
            clean_name = (
                store_name.replace("C.A.", "")
                .replace("S.A.", "")
                .replace(",", "")
                .replace(".", "")
                .strip()
            )
            words = clean_name.split()

            # Palabras comunes a ignorar para generar el término de búsqueda
            forbidden = [
                "EL",
                "LA",
                "LOS",
                "LAS",
                "DE",
                "DEL",
                "Y",
                "FARMACIA",
                "FARMACIAS",
                "SUCURSAL",
                "SUCURLSAL",
                "GRUPO",
                "INVERSIONES",
                "DROGUERIA",
            ]

            # Buscar palabra clave más fuerte
            search_term = next(
                (w for w in words if w.upper() not in forbidden and len(w) > 2),
                words[0],  # Si todas son prohibidas, usar la primera (ej: GRUPO)
            )

            logger.info(f"🔍 Buscando '{store_name}' con término: '{search_term}'")

            # 2. SELECCIONAR EL INPUT CORRECTO (ID ESPECÍFICO)
            # Usamos datatableSearch_ porque es el que hace la búsqueda global en el servidor
            try:
                search_input = wait.until(
                    EC.element_to_be_clickable((By.ID, "datatableSearch_"))
                )
            except:
                # Fallback por si cambian el ID
                search_input = self.driver.find_element(
                    By.CSS_SELECTOR, "input[type='search']"
                )

            search_input.clear()
            search_input.send_keys(search_term)
            time.sleep(1)
            search_input.send_keys(Keys.ENTER)  # Importante: Presionar Enter

            # Esperar a que la tabla se actualice
            time.sleep(4)

            # 3. IDENTIFICAR FILAS Y EXTRAER ID
            # Buscamos en el tbody con ID "set-rows"
            tbody = self.driver.find_element(By.ID, "set-rows")
            rows = tbody.find_elements(By.TAG_NAME, "tr")

            real_legacy_id = None

            if not rows or (len(rows) == 1 and "No data found" in rows[0].text):
                # INTENTO 2: Si falló, buscar por el nombre limpio completo (ej: "GRUPO FARMAYA")
                logger.warning(
                    f"⚠️ Falló búsqueda por '{search_term}'. Intentando nombre completo: '{clean_name}'"
                )
                search_input.clear()
                search_input.send_keys(clean_name)
                search_input.send_keys(Keys.ENTER)
                time.sleep(4)
                tbody = self.driver.find_element(By.ID, "set-rows")
                rows = tbody.find_elements(By.TAG_NAME, "tr")

            for row in rows:
                # Obtenemos todo el texto de la fila. Selenium concatena los divs.
                # En tu HTML: GRUPO FARMAYA C.A. \n ID:3
                row_text = row.text.upper()

                # Buscamos coincidencia flexible
                if search_term.upper() in row_text or clean_name.upper() in row_text:
                    # Regex para capturar el ID. En tu HTML es "ID:3" o "ID: 3"
                    id_match = re.search(r"ID\s*:\s*(\d+)", row.text)
                    if id_match:
                        real_legacy_id = id_match.group(1)
                        break

            if not real_legacy_id:
                # Último recurso: si solo hay 1 fila y buscamos algo muy específico, asumimos que es esa
                if len(rows) == 1:
                    id_match = re.search(r"ID\s*:\s*(\d+)", rows[0].text)
                    if id_match:
                        real_legacy_id = id_match.group(1)
                        logger.warning(
                            f"⚠️ Match forzado por fila única para {store_name} -> ID {real_legacy_id}"
                        )

            if not real_legacy_id:
                raise Exception(
                    f"No se encontró el ID numérico para {store_name} en la tabla."
                )

            logger.info(f"🎯 ID Real Detectado para '{store_name}': {real_legacy_id}")

            # 4. INTERACTUAR CON EL SWITCH
            # Basado en tu HTML: id="activeCheckbox3"
            checkbox_id = f"activeCheckbox{real_legacy_id}"

            # Verificar estado actual vía JS para exactitud
            is_on = self.driver.execute_script(
                f"return document.getElementById('{checkbox_id}') != null && document.getElementById('{checkbox_id}').checked;"
            )

            logger.info(
                f"Estado de {store_name} (#{real_legacy_id}): {'ON' if is_on else 'OFF'}"
            )

            # 5. EJECUTAR CAMBIO SI ES NECESARIO (Solo APAGAR según tu lógica original)
            if not desired_status_bool and is_on:
                logger.info(f"🔌 [ACCIÓN REAL] Apagando {store_name}...")

                # Buscamos el LABEL que es lo que recibe el click visualmente
                label = self.driver.find_element(
                    By.CSS_SELECTOR, f"label[for='{checkbox_id}']"
                )

                # Scroll para asegurar visibilidad
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", label
                )
                time.sleep(0.5)

                # Click potente
                clicked = self._super_click(
                    label, label.location["x"], label.location["y"]
                )
                if not clicked:
                    label.click()

                # Confirmar SweetAlert
                try:
                    confirm = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable(
                            (
                                By.CSS_SELECTOR,
                                ".swal2-confirm, .confirm, button.swal2-confirm",
                            )
                        )
                    )
                    confirm.click()
                    time.sleep(2)
                except:
                    pass
                return True

            logger.info(f"⏹️ {store_name} ya estaba en estado correcto.")
            return False

        except Exception as e:
            # Captura de pantalla para debug
            try:
                self.driver.save_screenshot(
                    f"/tmp/debug_error_{store_name.replace(' ', '_')}.png"
                )
            except:
                pass
            logger.error(f"❌ Error crítico en {store_name}: {e}")
            return False
