import logging
import time
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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

    def enforce_store_status(
        self, store_name, desired_status_bool, store_external_id=None
    ):
        if not self.driver:
            self.login()

        try:
            if "/admin/store/list" not in self.driver.current_url:
                self.driver.get(self.LIST_URL)

            wait = WebDriverWait(self.driver, 10)

            # 1. BÚSQUEDA DIRECTA POR ID (Si lo tenemos, es a prueba de balas)
            real_legacy_id = None
            search_input = None

            try:
                search_input = wait.until(
                    EC.element_to_be_clickable((By.ID, "datatableSearch_"))
                )
            except:
                search_input = self.driver.find_element(
                    By.CSS_SELECTOR, "input[type='search']"
                )

            # Si la DB local tiene el ID externo (ej: "store_3"), extraemos el número
            if store_external_id:
                id_match = re.search(r"(\d+)", store_external_id)
                if id_match:
                    real_legacy_id = id_match.group(1)
                    logger.info(
                        f"🎯 Usando ID Directo desde DB para {store_name}: {real_legacy_id}"
                    )

            # 2. Si no hay ID, buscamos el nombre con BLINDAJE EXACTO
            if not real_legacy_id:
                clean_name = (
                    store_name.replace("C.A.", "")
                    .replace("S.A.", "")
                    .replace(",", "")
                    .replace(".", "")
                    .strip()
                )
                logger.info(f"🔍 Buscando nombre completo: '{clean_name}'")

                search_input.clear()
                search_input.send_keys(clean_name)
                time.sleep(1)
                search_input.send_keys(Keys.ENTER)
                time.sleep(4)

                tbody = self.driver.find_element(By.ID, "set-rows")
                rows = tbody.find_elements(By.TAG_NAME, "tr")

                for row in rows:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) > 1:
                        cell_text = cols[1].text.strip()
                        if not cell_text:
                            continue

                        # TRUCO NINJA: Extraer el nombre real oculto en el atributo 'title'
                        try:
                            title_div = cols[1].find_element(
                                By.CSS_SELECTOR, ".text--title"
                            )
                            store_name_in_table = (
                                title_div.get_attribute("title").strip().upper()
                            )
                        except:
                            # Fallback por si la farmacia tiene un nombre corto y no tiene el 'title'
                            store_name_in_table = (
                                cell_text.split("\n")[0]
                                .strip()
                                .upper()
                                .replace("...", "")
                            )

                        # VALIDACIÓN BLINDADA: Ahora comparamos contra el nombre puro del sistema
                        if (
                            store_name_in_table == store_name.upper()
                            or store_name_in_table == clean_name.upper()
                        ):
                            id_regex = re.search(r"ID\s*:\s*(\d+)", cell_text)
                            if id_regex:
                                real_legacy_id = id_regex.group(1)
                                break

            if not real_legacy_id:
                logger.warning(
                    f"⚠️ No se encontró la tienda {store_name} o había riesgo de falso positivo. Abortando."
                )
                return False

            logger.info(f"✅ ID Confirmado para '{store_name}': {real_legacy_id}")

            # 3. INTERACTUAR CON EL SWITCH
            checkbox_id = f"activeCheckbox{real_legacy_id}"

            is_on = self.driver.execute_script(
                f"return document.getElementById('{checkbox_id}') != null && document.getElementById('{checkbox_id}').checked;"
            )

            if not desired_status_bool and is_on:
                logger.info(f"🔌 APAGANDO: {store_name}...")

                label = self.driver.find_element(
                    By.CSS_SELECTOR, f"label[for='{checkbox_id}']"
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", label
                )
                time.sleep(0.5)

                clicked = self._super_click(
                    label, label.location["x"], label.location["y"]
                )
                if not clicked:
                    label.click()

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

            logger.info(f"⏹️ {store_name} ya estaba APAGADA.")
            return False

        except Exception as e:
            logger.error(f"❌ Error crítico en {store_name}: {e}")
            return False
