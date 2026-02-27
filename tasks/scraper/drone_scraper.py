import logging
import re
import os
import time
import urllib.parse

# --- CORRECCIÓN: Agregados List y Dict ---
from typing import Dict, Any, Optional, Tuple, List
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService

# from webdriver_manager.chrome import ChromeDriverManager
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DroneScraper:
    def __init__(self):
        self.base_detail_url = f"{settings.LEGACY_BASE_URL}/admin/order/details"
        self.driver = None
        self.wait_timeout = 10

    def setup_driver(self):
        # Importaciones locales para no ensuciar el resto del archivo
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
        import logging

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        # Configuración de descargas
        self.download_dir = "/tmp/downloads"
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, mode=0o777)

        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "safebrowsing.enabled": True,
        }
        chrome_options.add_experimental_option("prefs", prefs)

        # --- INSTALACIÓN AUTOMÁTICA DEL DRIVER ---
        try:
            logger.info("🔧 Instalando ChromeDriver compatible...")
            # Esto descarga la versión exacta para el Chrome que tienes instalado
            driver_path = ChromeDriverManager().install()

            # Corrección de permisos (a veces baja sin permisos de ejecución)
            os.chmod(driver_path, 0o755)

            service = Service(executable_path=driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info(f"✅ Driver iniciado correctamente desde: {driver_path}")

        except Exception as e:
            logger.error(f"❌ Error fatal iniciando driver: {e}")
            raise e

        # Comandos CDP finales
        try:
            params = {"behavior": "allow", "downloadPath": self.download_dir}
            self.driver.execute_cdp_cmd("Page.setDownloadBehavior", params)
        except:
            pass

    def login(self) -> bool:
        if not self.driver:
            self.setup_driver()
        try:
            self.driver.get(f"{settings.LEGACY_BASE_URL}/login/admin")
            wait = WebDriverWait(self.driver, self.wait_timeout)
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

    # --- EXTRACTORES ---
    def _parse_money(self, text: str) -> float:
        try:
            match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)", text)
            return float(match.group(1).replace(",", "")) if match else 0.0
        except:
            return 0.0

    def _extract_financials(self, body_text: str) -> Dict[str, float]:
        data = {}

        def get_val(keyword):
            try:
                pattern = re.escape(keyword) + r".*?USD\s*([\d\.]+)"
                match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
                return float(match.group(1)) if match else 0.0
            except:
                return 0.0

        data["service_fee"] = get_val("Tarifa de servicio")
        data["coupon_discount"] = get_val("Descuento del cupón")
        data["tips"] = get_val("Propinas al repartidor")
        data["real_delivery_fee"] = get_val("Tarifa de entrega")
        data["total_amount"] = get_val("Total:")

        # Intentar extraer precio de producto
        data["product_price"] = get_val("Precio de productos")

        return data

    def _parse_href_coords(self, href: str) -> Optional[Tuple[float, float]]:
        if not href:
            return None
        try:
            href = urllib.parse.unquote(href)
            match = re.search(r"q=loc:(-?\d+\.\d+)(?:\+|,|\s)(-?\d+\.\d+)", href)
            if match:
                return float(match.group(1)), float(match.group(2))
        except:
            pass
        return None

    def _extract_maps(self) -> Dict[str, float]:
        result = {}
        try:
            # 1. CLIENTE
            try:
                client_link = self.driver.find_element(
                    By.CSS_SELECTOR,
                    ".delivery--information-single a[href*='maps.google.com']",
                )
                c = self._parse_href_coords(client_link.get_attribute("href"))
                if c:
                    result["customer_lat"], result["customer_lng"] = c
            except:
                try:
                    client_link = self.driver.find_element(
                        By.XPATH,
                        "//h5[contains(., 'Información de entrega')]/ancestor::div[contains(@class, 'card-body')]//a[contains(@href, 'maps.google.com')]",
                    )
                    c = self._parse_href_coords(client_link.get_attribute("href"))
                    if c:
                        result["customer_lat"], result["customer_lng"] = c
                except:
                    pass

            # 2. TIENDA
            try:
                store_link = self.driver.find_element(
                    By.CSS_SELECTOR, "a.__gap-5px[href*='maps.google.com']"
                )
                c = self._parse_href_coords(store_link.get_attribute("href"))
                if c:
                    result["store_lat"], result["store_lng"] = c
            except:
                pass
        except:
            pass
        return result

    def _extract_basic_info(self) -> Dict[str, str]:
        info = {}
        try:
            status_el = self.driver.find_element(
                By.XPATH,
                "//div[contains(@class, 'order-invoice-right')]//span[contains(@class, 'badge')]",
            )
            info["status_text"] = status_el.text.strip()
        except:
            info["status_text"] = "pending"

        try:
            client_el = self.driver.find_element(
                By.CSS_SELECTOR, "a[href*='/customer/view/'] .media-body"
            )
            info["customer_name"] = client_el.text.split("\n")[0].strip()
        except:
            info["customer_name"] = "Desconocido"

        try:
            driver_el = self.driver.find_element(
                By.CSS_SELECTOR, "a[href*='/delivery-man/'] .media-body span"
            )
            info["driver_name"] = driver_el.text.strip()
        except:
            info["driver_name"] = "N/A"

        try:
            store_el = self.driver.find_element(
                By.CSS_SELECTOR, "a[href*='/store/view/'] .media-body span"
            )
            info["store_name"] = store_el.text.strip()
        except:
            info["store_name"] = "Desconocida"

        try:
            el = self.driver.find_element(
                By.CSS_SELECTOR, ".delivery--information-single a[href^='tel:']"
            )
            info["customer_phone"] = el.text.strip()
        except:
            pass

        try:
            header_text = self.driver.find_element(
                By.CLASS_NAME, "order-invoice-left"
            ).text
            date_match = re.search(
                r"(\d{1,2}\s+[A-Za-z\.]+\s+\d{4}\s+\d{1,2}:\d{2})", header_text
            )
            if date_match:
                info["created_at_text"] = date_match.group(1)
        except:
            pass

        return info

    def _extract_reason_smart(self) -> Optional[str]:
        try:
            labels = self.driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'Motivo de cancelación') or contains(text(), 'Razón')]",
            )
            for label in labels:
                try:
                    parent = label.find_element(By.XPATH, "./..")
                    raw_text = parent.text
                    garbage = [
                        label.text,
                        "Motivo de cancelación",
                        "del pedido",
                        ":",
                        "-",
                    ]
                    for g in garbage:
                        raw_text = raw_text.replace(g, "")
                    clean = raw_text.strip()
                    if len(clean) > 2:
                        return clean
                except:
                    continue
        except:
            pass
        return None

    # --- NUEVO: EXTRACTOR DE PRODUCTOS ---
    def _extract_products(self) -> List[Dict]:
        """Extrae la lista de productos del detalle."""
        items = []
        try:
            # Buscar filas de la tabla de productos
            rows = self.driver.find_elements(By.XPATH, "//table/tbody/tr")

            for row in rows:
                try:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) < 3:
                        continue

                    # 1. Nombre
                    try:
                        name_el = cols[1].find_element(By.TAG_NAME, "strong")
                        name = name_el.text.strip()
                    except:
                        continue

                    # 2. Cantidad y Precio Unitario
                    qty = 1
                    price = 0.0
                    try:
                        info_text = cols[1].find_element(By.TAG_NAME, "h6").text
                        match = re.search(r"(\d+)\s*x\s*USD\s*([\d\.,]+)", info_text)
                        if match:
                            qty = int(match.group(1))
                            price = float(match.group(2).replace(",", ""))
                    except:
                        pass

                    # 3. Código de Barras
                    barcode = cols[2].get_attribute("title") or cols[2].text.strip()

                    # 4. Total Línea
                    total = 0.0
                    try:
                        total_text = cols[3].text
                        total = self._parse_money(total_text)
                    except:
                        total = price * qty

                    if name:
                        items.append(
                            {
                                "name": name,
                                "quantity": qty,
                                "unit_price": price,
                                "total_price": total,
                                "barcode": barcode,
                            }
                        )
                except:
                    continue
        except Exception as e:
            logger.error(f"Error extracting products: {e}")

        return items

    def scrape_detail(self, external_id: str, mode: str = "full") -> Dict[str, Any]:
        if not self.driver:
            self.setup_driver()
            self.login()
        result = {"external_id": external_id}
        target_url = f"{self.base_detail_url}/{external_id}"

        try:
            self.driver.get(target_url)
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            body_text = self.driver.find_element(By.TAG_NAME, "body").text

            result.update(self._extract_basic_info())
            result.update(self._extract_financials(body_text))
            result.update(self._extract_maps())

            # Productos (Siempre)
            products = self._extract_products()
            if products:
                result["items"] = products

            if "cancelado" in result.get("status_text", "").lower():
                reason = self._extract_reason_smart()
                if reason:
                    result["cancellation_reason"] = reason

        except Exception as e:
            logger.error(f"❌ Error scraping {external_id}: {e}")

        return result
