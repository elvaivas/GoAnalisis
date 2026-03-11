import logging
import re
import time
from typing import List, Dict, Any
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomerScraper:
    def __init__(self):
        self.base_url = f"{settings.LEGACY_BASE_URL}/login/admin"
        # Aseguramos el ordenamiento por el más reciente
        self.users_url = (
            f"{settings.LEGACY_BASE_URL}/admin/users/customer/list?order_wise=latest"
        )
        self.driver = None

    def setup_driver(self):
        if self.driver:
            return
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        # SRE: Mantenemos esto porque Docker lo necesita, pero ya subimos el /dev/shm a 2GB
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-allow-origins=*")

        # SRE: Añadimos tamaño de ventana fijo para evitar que los elementos se "escondan" en headless
        chrome_options.add_argument("--window-size=1920,1080")

        # SRE: User-Agent actualizado a la versión real de tu servidor (v145)
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.7632.159 Safari/537.36"
        )

        try:
            # INICIO NATIVO 20/20
            self.driver = webdriver.Chrome(options=chrome_options)

            # Escudo de Timeouts: 30s es el estándar de oro
            self.driver.set_page_load_timeout(30)
            self.driver.set_script_timeout(30)
            logger.info("✅ Driver de Clientes iniciado con éxito (Modo SRE).")
        except Exception as e:
            logger.error(f"❌ Error fatal iniciando ChromeDriver: {e}")
            raise e

    def login(self) -> bool:
        if not self.driver:
            self.setup_driver()
        try:
            logger.info(f"🔑 Intentando login en {self.base_url}...")
            self.driver.get(self.base_url)
            wait = WebDriverWait(
                self.driver, 15
            )  # Subimos a 15s por si el Legacy está lento

            # Buscamos el campo email
            email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
            email_field.clear()
            email_field.send_keys(settings.GOPHARMA_EMAIL)

            password_field = self.driver.find_element(By.NAME, "password")
            password_field.clear()
            password_field.send_keys(settings.GOPHARMA_PASSWORD)

            # SRE: Intento de click inteligente
            try:
                submit_btn = self.driver.find_element(
                    By.XPATH, "//button[@type='submit']"
                )
                submit_btn.click()
            except:
                password_field.submit()

            # SRE: Eliminamos time.sleep(3). En su lugar, esperamos a que el URL cambie
            # o que aparezca un elemento del Dashboard (ej: el menú lateral)
            wait.until(lambda d: "login" not in d.current_url)

            logger.info("✅ Login de Clientes exitoso.")
            return True
        except Exception as e:
            logger.error(f"❌ Fallo en el proceso de Login: {e}")
            return False

    def close_driver(self):
        if self.driver:
            try:
                logger.info("🔌 Cerrando ChromeDriver de forma segura...")
                self.driver.quit()
            except Exception as e:
                logger.warning(f"⚠️ Error al cerrar el driver: {e}")
            finally:
                self.driver = None

    def _parse_spanish_date(self, text):
        if not text:
            return None
        month_map = {
            "ene": "01",
            "feb": "02",
            "mar": "03",
            "abr": "04",
            "may": "05",
            "jun": "06",
            "jul": "07",
            "ago": "08",
            "sep": "09",
            "oct": "10",
            "nov": "11",
            "dic": "12",
            "enero": "01",
            "febrero": "02",
            "marzo": "03",
            "abril": "04",
            "mayo": "05",
            "junio": "06",
            "julio": "07",
            "agosto": "08",
            "septiembre": "09",
            "octubre": "10",
            "noviembre": "11",
            "diciembre": "12",
        }
        try:
            clean = text.lower().replace(".", "").strip()
            for m_name, m_num in month_map.items():
                if m_name in clean:
                    clean = clean.replace(m_name, m_num)
                    break

            match = re.search(r"(\d{1,2})[\s/-]+(\d{1,2})[\s/-]+(\d{4})", clean)
            if match:
                return datetime.strptime(
                    f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %m %Y"
                )
        except:
            pass
        return None

    def _correct_year_based_on_id(self, date_obj: datetime, cust_id: int) -> datetime:
        if not date_obj:
            return None

        # Corrección del Bug de Año Nuevo de Gopharma
        if date_obj.year == 2026:
            if cust_id < 100:
                return date_obj.replace(year=2023)
            elif cust_id < 2000:
                return date_obj.replace(year=2024)
            elif cust_id < 23413:
                return date_obj.replace(year=2025)
        return date_obj

    def scrape_customers(self, max_pages: int = None, days_back: int = 3) -> List[Dict]:
        if not self.driver:
            self.setup_driver()
            self.login()
        customers = []

        today = datetime.now()
        limit_date = today - timedelta(days=days_back)
        limit_date = limit_date.replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(
            f"👥 Scrapeando Clientes Nuevos (Limite: {limit_date.strftime('%d/%m/%Y')})..."
        )

        try:
            current_page = 1
            stop_scraping = False
            old_records_count = 0
            MAX_OLD_RECORDS = 15

            while not stop_scraping:
                if max_pages and current_page > max_pages:
                    break

                # Paginación directa en la URL asegurando el filtro order_wise
                url = f"{settings.LEGACY_BASE_URL}/admin/users/customer/list?order_wise=latest&page={current_page}"
                self.driver.get(url)

                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "set-rows"))
                )

                logger.info(f"   📄 Procesando página {current_page}...")

                # 👇 CAMBIO QUIRÚRGICO: Selector CSS directo a las filas de la tabla
                rows = self.driver.find_elements(By.CSS_SELECTOR, "tbody#set-rows tr")
                if not rows:
                    break

                for row in rows:
                    try:
                        # 1. ID del Cliente
                        id_text = row.find_element(
                            By.CSS_SELECTOR, "td:first-child"
                        ).text.strip()
                        if not id_text.isdigit():
                            continue
                        gopharma_id = int(id_text)

                        # 2. Nombre
                        try:
                            name_el = row.find_element(
                                By.CSS_SELECTOR, "td:nth-child(2) a:first-child"
                            )
                            name = name_el.text.strip()
                        except:
                            name = "Desconocido"

                        # 3. Teléfono
                        phone = None
                        try:
                            phone_el = row.find_element(
                                By.CSS_SELECTOR, "td:nth-child(4) a[href^='tel:']"
                            )
                            phone = (
                                phone_el.get_attribute("href")
                                .replace("tel:", "")
                                .strip()
                            )
                        except:
                            pass

                        # 4. Fecha de Ingreso
                        try:
                            date_el = row.find_element(
                                By.CSS_SELECTOR, "td:nth-child(7) label.badge"
                            )
                            raw_date = self._parse_spanish_date(date_el.text.strip())
                            final_date = self._correct_year_based_on_id(
                                raw_date, gopharma_id
                            )
                        except:
                            final_date = None

                        if final_date:
                            if final_date < limit_date:
                                old_records_count += 1
                                logger.info(
                                    f"⚠️ Registro antiguo detectado ({final_date.strftime('%d/%m/%Y')} | ID: {gopharma_id}). Racha: {old_records_count}/{MAX_OLD_RECORDS}"
                                )

                                if old_records_count >= MAX_OLD_RECORDS:
                                    logger.info(
                                        f"🛑 Límite de {MAX_OLD_RECORDS} registros antiguos consecutivos alcanzado. Deteniendo scraper."
                                    )
                                    stop_scraping = True
                                    break
                            else:
                                old_records_count = 0

                            customers.append(
                                {
                                    "id": str(gopharma_id),
                                    "name": name,
                                    "phone": phone,
                                    "joined_at": final_date,
                                }
                            )
                    except Exception as e:
                        continue

                if stop_scraping:
                    break

                # Intentamos avanzar a la siguiente página validando si el botón no está deshabilitado
                try:
                    next_btn_parent = self.driver.find_element(
                        By.XPATH, "//a[@rel='next']/parent::li"
                    )
                    if "disabled" in next_btn_parent.get_attribute("class"):
                        break
                    current_page += 1
                except:
                    break

        except Exception as e:
            logger.error(f"Error scraping customers: {e}")
        finally:
            self.close_driver()

        logger.info(f"✅ Finalizado. {len(customers)} usuarios recolectados.")
        return customers
