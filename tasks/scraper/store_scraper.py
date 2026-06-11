import logging
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
from app.core.config import settings
from app.services.selectors import LOGIN_SELECTORS, ORDER_DETAIL_SELECTORS, STORE_LIST_SELECTORS

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
        
        # --- BLINDAJE EXTREMO DE MEMORIA (Copiado del Dron) ---
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.add_argument("--disable-site-isolation-trials")
        chrome_options.add_argument("--js-flags=--max-old-space-size=256")
        chrome_options.add_argument("--disable-cache")
        chrome_options.add_argument("--disk-cache-size=1")

        # --- INICIO NATIVO SRE ---
        self.driver = webdriver.Chrome(options=chrome_options)

        # Escudo SRE: Timeout de 30s contra desconexiones
        self.driver.set_page_load_timeout(30)
        self.driver.set_script_timeout(30)

    def scrape_store_list(self, max_pages: int = None) -> list:
        """
        Escanea la lista principal de tiendas para extraer Empresa, Sucursal, ID real
        y los URLs de los interruptores de apagado.
        """
        if not self.driver:
            self.setup_driver()
            self.login()

        stores_data = []
        current_page = 1

        try:
            while True:
                if max_pages and current_page > max_pages:
                    break

                url = f"{settings.LEGACY_BASE_URL}/admin/store/list?page={current_page}"
                self.driver.get(url)

                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(STORE_LIST_SELECTORS["table_body"])
                )

                # Usamos el selector centralizado e invencible para las filas
                rows = self.driver.find_elements(*STORE_LIST_SELECTORS["table_rows"])
                if not rows:
                    break

                for row in rows:
                    try:
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) < 8:
                            continue

                        # --- TU LÓGICA ORIGINAL ADAPTADA AL NUEVO DOM ---
                        # 1. Empresa (Badge)
                        try:
                            company_el = cols[1].find_element(
                                By.CSS_SELECTOR, "div.info .badge"
                            )
                            company_name = company_el.text.replace("...", "").strip()
                        except:
                            company_name = "Desconocida"

                        # 2. Sucursal (Texto con title completo)
                        try:
                            title_el = cols[1].find_element(
                                By.CSS_SELECTOR, "div.text--title"
                            )
                            store_name = title_el.get_attribute("title")
                            if (
                                not store_name
                            ):  # Fallback por si quitaron el atributo title
                                store_name = title_el.text.strip()
                        except:
                            store_name = "Desconocida"

                        # 3. ID (Texto debajo del nombre)
                        try:
                            id_el = cols[1].find_element(
                                By.XPATH,
                                ".//*[contains(@class, 'font-light') and contains(text(), 'Id:')]",
                            )
                            store_id = (
                                id_el.text.replace("Id:", "").replace("ID:", "").strip()
                            )
                        except:
                            continue  # Si no hay ID, la fila no nos sirve

                        # --- NUEVA LÓGICA: Módulo de Apagado ---
                        is_active_app = False
                        toggle_url_app = None
                        try:
                            app_toggle = cols[5].find_element(
                                By.CSS_SELECTOR, "input[type='checkbox']"
                            )
                            is_active_app = (
                                app_toggle.get_attribute("checked") is not None
                            )
                            toggle_url_app = app_toggle.get_attribute("data-url")
                        except:
                            pass

                        is_status_active = False
                        toggle_url_status = None
                        try:
                            status_toggle = cols[6].find_element(
                                By.CSS_SELECTOR, "input[type='checkbox']"
                            )
                            is_status_active = (
                                status_toggle.get_attribute("checked") is not None
                            )
                            toggle_url_status = status_toggle.get_attribute("data-url")
                        except:
                            pass

                        if store_id.isdigit():
                            stores_data.append(
                                {
                                    "id": store_id,
                                    "company_name": company_name,
                                    "name": store_name,
                                    "is_active_app": is_active_app,
                                    "app_toggle_url": toggle_url_app,
                                    "is_status_active": is_status_active,
                                    "status_toggle_url": toggle_url_status,
                                }
                            )
                    except Exception as e:
                        continue

                # Paginación
                try:
                    next_btn = self.driver.find_element(*STORE_LIST_SELECTORS["next_page_btn"])
                    parent = next_btn.find_element(By.XPATH, "./..")
                    if "disabled" in parent.get_attribute("class"):
                        break

                    self.driver.execute_script("arguments[0].click();", next_btn)
                    time.sleep(2)
                    current_page += 1
                except:
                    break

        except Exception as e:
            logger.error(f"Error scraping store list: {e}")
        finally:
            self.close_driver()

        return stores_data

    def toggle_store_status(self, toggle_url: str) -> bool:
        """
        Ejecuta la URL de cambio de estado (apagado/encendido) de forma directa.
        Requiere que la sesión esté iniciada.
        """
        if not toggle_url:
            return False

        if not self.driver:
            self.setup_driver()
            self.login()

        try:
            # Al visitar directamente el endpoint del data-url, el backend cambia el estado
            # sin necesidad de lidiar con el modal de confirmación de JavaScript.
            self.driver.get(toggle_url)
            time.sleep(1)  # Pequeña pausa para asegurar que el servidor procese
            return True
        except Exception as e:
            logger.error(f"Error al intentar cambiar estado de la tienda: {e}")
            return False

    def login(self) -> bool:
        if not self.driver:
            self.setup_driver()
        try:
            self.driver.get(self.base_url)
            wait = WebDriverWait(self.driver, 10)

            # --- CORRECCIÓN: Homologado con los selectores centralizados LOGIN_SELECTORS ---
            # Se usan los selectores importados para mantener la consistencia con el nuevo panel
            wait.until(
                EC.presence_of_element_located(LOGIN_SELECTORS["email_input"])
            ).send_keys(settings.GOPHARMA_EMAIL)

            self.driver.find_element(*LOGIN_SELECTORS["password_input"]).send_keys(
                settings.GOPHARMA_PASSWORD
            )

            try:
                self.driver.find_element(*LOGIN_SELECTORS["login_button"]).click()
            except:
                self.driver.find_element(*LOGIN_SELECTORS["password_input"]).submit()

            time.sleep(3)
            return "login" not in self.driver.current_url
        except Exception as e:
            # Añadido un log para no fallar silenciosamente en el futuro
            logger.error(f"Fallo en login del StoreScraper: {e}")
            return False

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            
        # 🛡️ ESCUDO ANTI-ZOMBIES: Limpieza a nivel de SO
        try:
            os.system("pkill -f chrome")
            os.system("pkill -f chromedriver")
        except:
            pass

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
                input_el = self.driver.find_element(
                    *ORDER_DETAIL_SELECTORS["commission_input"]
                )
                val = input_el.get_attribute("value")
                return float(val)
            except:
                pass

            # 2. Intentar sacar del texto "10 % Comisión"
            try:
                body = self.driver.find_element(By.TAG_NAME, "body").text
                match = re.search(
                    ORDER_DETAIL_SELECTORS["commission_text_pattern"],
                    body,
                    re.IGNORECASE,
                )
                if match:
                    return float(match.group(1))
            except:
                pass

        except Exception as e:
            logger.error(f"Error scraping store {store_real_id}: {e}")

        return 0.0
