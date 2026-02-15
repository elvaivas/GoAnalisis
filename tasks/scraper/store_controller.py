import logging
import time
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys  # <--- IMPORTANTE: Importar Keys
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

        # Preferencias para evitar caché y errores de renderizado
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")

        try:
            driver_path = ChromeDriverManager().install()
            service = Service(executable_path=driver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
        except:
            # Fallback para servidor linux
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

            pwd = self.driver.find_element(By.NAME, "password")
            pwd.clear()
            pwd.send_keys(settings.GOPHARMA_PASSWORD)

            btn = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            self.driver.execute_script("arguments[0].click();", btn)

            # Esperar a que la URL cambie o aparezca un elemento del dashboard
            time.sleep(5)
            return True
        except Exception as e:
            logger.error(f"Login fallido: {e}")
            return False

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def _super_click(self, element, x, y):
        """Simula presión humana sobre un elemento específico"""
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

    def _find_rows_by_text(self, text_to_find):
        """Helper para encontrar filas que contengan el texto, ignorando mayúsculas"""
        # XPath mejorado: usa normalize-space para ignorar espacios extra y busca en toda la fila
        xpath_row = (
            f"//tr[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            f"'{text_to_find.lower()}')]"
        )
        return self.driver.find_elements(By.XPATH, xpath_row)

    def enforce_store_status(self, store_name, desired_status_bool):
        if not self.driver:
            self.login()

        try:
            # Ir a la lista solo si no estamos ya ahí (pequeña optimización)
            if self.LIST_URL not in self.driver.current_url:
                self.driver.get(self.LIST_URL)

            wait = WebDriverWait(self.driver, 10)
            search_input = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='search']")
                )
            )

            # 1. PREPARACIÓN DE NOMBRES
            clean_name = (
                store_name.replace("C.A.", "")
                .replace("S.A.", "")
                .replace(",", "")
                .replace(".", "")
                .strip()
            )
            words = clean_name.split()

            forbidden = [
                "EL",
                "LA",
                "LOS",
                "LAS",
                "DE",
                "DEL",
                "Y",
                "FARMACIA",
                "SUCURSAL",
                "GRUPO",
                "INVERSIONES",
                "SUCURLSAL",
                "DROGUERIA",
                "COMERCIAL",
                "CORPORACION",
            ]

            # Búsqueda inteligente (palabra clave)
            smart_search_term = next(
                (w for w in words if w.upper() not in forbidden and len(w) > 2),
                words[0],
            )

            # --- INTENTO 1: Búsqueda por palabra clave ---
            logger.info(
                f"🔍 [Intento 1] Buscando '{store_name}' usando clave: '{smart_search_term}'"
            )

            search_input.clear()
            search_input.send_keys(smart_search_term)
            # A veces el JS requiere un Enter o un pequeño delay extra
            # search_input.send_keys(Keys.ENTER)
            time.sleep(4)

            rows = self._find_rows_by_text(smart_search_term)

            # --- INTENTO 2: Fallback al nombre completo (si falló el anterior) ---
            if not rows:
                logger.warning(
                    f"⚠️ No se encontraron filas con '{smart_search_term}'. Probando nombre completo limpio: '{clean_name}'"
                )
                search_input.clear()
                # Truco: enviar caracter por caracter a veces despierta filtros JS perezosos
                # Pero enviar todo + espacio suele funcionar
                search_input.send_keys(clean_name)
                time.sleep(4)

                # Buscamos usando clean_name, o si es muy largo, la primera palabra de clean_name
                rows = self._find_rows_by_text(clean_name)

                # Si aun falla, probar con la primera palabra absoluta (aunque sea 'GRUPO')
                if not rows and len(words) > 0:
                    first_word = words[0]
                    logger.warning(
                        f"⚠️ Fallback final: Buscando por primera palabra '{first_word}'"
                    )
                    search_input.clear()
                    search_input.send_keys(first_word)
                    time.sleep(4)
                    rows = self._find_rows_by_text(first_word)

            if not rows:
                raise Exception(
                    f"No se encontró ninguna fila para {store_name} tras múltiples intentos."
                )

            # 2. IDENTIFICAR EL ID REAL
            real_legacy_id = None

            # Iteramos sobre las filas encontradas
            for row in rows:
                row_text = row.text
                # Buscamos patrón ID
                id_match = re.search(r"ID\s*:\s*(\d+)", row_text)
                if id_match:
                    # Si encontramos ID, verificamos que el nombre de la tienda tenga sentido
                    # (que contenga al menos una parte del nombre original para evitar falsos positivos de IDs similares)
                    # Convertimos todo a mayúsculas para comparar
                    if (
                        smart_search_term.upper() in row_text.upper()
                        or clean_name.upper() in row_text.upper()
                    ):
                        real_legacy_id = id_match.group(1)
                        break

                    # Si la búsqueda fue muy genérica (ej. "GRUPO"), guardamos el ID pero seguimos buscando mejor match
                    real_legacy_id = id_match.group(1)

            if not real_legacy_id:
                raise Exception(
                    "Se encontraron filas pero no se pudo extraer el ID numérico."
                )

            logger.info(f"🎯 ID Real Detectado para '{store_name}': {real_legacy_id}")

            # 3. LOCALIZAR EL INTERRUPTOR
            checkbox_id = f"activeCheckbox{real_legacy_id}"
            try:
                checkbox = self.driver.find_element(By.ID, checkbox_id)
            except:
                raise Exception(f"No se encontró el checkbox con ID {checkbox_id}")

            # 4. EVALUAR ESTADO
            is_on = self.driver.execute_script(
                f"return document.getElementById('{checkbox_id}').checked;"
            )

            # 5. ACTUAR
            if not desired_status_bool and is_on:
                logger.info(f"🔌 [ACCIÓN] Apagando {store_name}...")
                label = self.driver.find_element(
                    By.CSS_SELECTOR, f"label[for='{checkbox_id}']"
                )

                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", label
                )
                time.sleep(0.5)

                success_click = self._super_click(
                    label, label.location["x"], label.location["y"]
                )

                if not success_click:
                    # Fallback click normal si falla el super click
                    self.driver.execute_script("arguments[0].click();", label)

                # Manejo de SweetAlert (Confirmación)
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
                    # A veces no sale alerta, o ya se cerró
                    pass
                return True

            elif desired_status_bool and not is_on:
                # Lógica para encender si alguna vez la necesitas
                pass

            logger.info(f"⏹️ {store_name} ya estaba en el estado correcto (OFF).")
            return False

        except Exception as e:
            # Guardar captura de error para debug visual
            try:
                safe_name = "".join(x for x in store_name if x.isalnum())
                self.driver.save_screenshot(f"/tmp/error_{safe_name}.png")
            except:
                pass
            logger.error(f"❌ Error crítico en {store_name}: {e}")
            return False
