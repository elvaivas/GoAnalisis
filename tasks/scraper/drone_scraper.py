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
        import logging

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        # --- BLINDAJE EXTREMO DE MEMORIA ---
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-software-rasterizer")
        # Esta es la joya: No cargar imágenes = -60% consumo de RAM
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")

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
            logger.info("🚀 Iniciando ChromeDriver nativo (Selenium Manager)...")

            # Selenium >= 4.6 detecta tu Chrome .159 y gestiona el driver solo.
            # No necesitamos 'driver_path' ni 'os.chmod'.
            self.driver = webdriver.Chrome(options=chrome_options)

            # Escudo SRE: Timeout de 30s contra desconexiones
            self.driver.set_page_load_timeout(30)
            self.driver.set_script_timeout(30)
            logger.info("✅ Driver nativo sincronizado y listo para la misión.")

        except Exception as e:
            logger.error(f"❌ Error fatal iniciando driver nativo: {e}")
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
        """Extrae el monto manejando el nuevo formato: USD 0,72 (VED 314,09)"""
        try:
            # Buscamos el patrón USD seguido del número
            match = re.search(r"USD\s*([\d\.,]+)", text, re.IGNORECASE)
            if match:
                num_str = match.group(1).strip()
                # Si tiene punto de miles y coma decimal (Ej: 1.000,50)
                if "." in num_str and "," in num_str:
                    num_str = num_str.replace(".", "").replace(",", ".")
                # Si solo tiene coma decimal (Ej: 0,72)
                elif "," in num_str:
                    num_str = num_str.replace(",", ".")
                return float(num_str)
            return 0.0
        except:
            return 0.0

    def _extract_financials(self) -> Dict[str, float]:
        """Extrae los costos usando la nueva lista de definición <dl>"""
        data = {}
        # Mapeo exacto: Clave Base de Datos -> Texto visible en la etiqueta <dt>
        mapping = {
            "service_fee": "Tarifa de servicio",
            "coupon_discount": "Cupón de descuento",
            "tips": "Consejos para el repartidor",
            "real_delivery_fee": "Tarifa de envío",
            "total_amount": "Total",
            "product_price": "Precio de los artículos",
        }

        for db_key, label in mapping.items():
            try:
                # XPath quirúrgico: Busca el dt con la etiqueta y salta a su hermano dd
                xpath = f"//dl[contains(@class, 'row')]//dt[contains(., '{label}')]/following-sibling::dd[1]"
                element = self.driver.find_element(By.XPATH, xpath)
                data[db_key] = self._parse_money(element.text)
            except:
                data[db_key] = 0.0

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
        # 1. CLIENTE
        try:
            client_link = self.driver.find_element(
                By.XPATH,
                "//*[contains(@class, 'delivery--information-single')]//a[contains(@href, 'google.com/maps')]",
            )
            c = self._parse_href_coords(client_link.get_attribute("href"))
            if c:
                result["customer_lat"], result["customer_lng"] = c
        except:
            pass

        # 2. TIENDA
        try:
            store_link = self.driver.find_element(
                By.XPATH,
                "//h5[contains(., 'Información de la tienda')]/ancestor::div[contains(@class, 'card')]//a[contains(@href, 'google.com/maps')]",
            )
            c = self._parse_href_coords(store_link.get_attribute("href"))
            if c:
                result["store_lat"], result["store_lng"] = c
        except:
            pass

        return result

    def _extract_basic_info(self) -> Dict[str, str]:
        info = {}
        # 1. Estatus (Lo intentamos sacar de los badges)
        try:
            status_el = self.driver.find_element(
                By.XPATH, "//span[contains(@class, 'badge-soft-')]"
            )
            info["status_text"] = status_el.text.strip()
        except:
            info["status_text"] = ""

        # 2. Cliente (Busca la tarjeta por el título, luego navega al nombre)
        try:
            client_el = self.driver.find_element(
                By.XPATH,
                "//h5[contains(., 'Información del cliente')]/ancestor::div[contains(@class, 'card')]//*[contains(@class, 'text--title')]",
            )
            info["customer_name"] = client_el.text.strip()
        except:
            info["customer_name"] = "Desconocido"

        # 3. Repartidor
        try:
            driver_el = self.driver.find_element(
                By.XPATH,
                "//h5[contains(., 'repartidor') or contains(., 'Repartidor')]/ancestor::div[contains(@class, 'card')]//*[contains(@class, 'text-body') and contains(@class, 'd-block')]",
            )
            info["driver_name"] = driver_el.text.strip()
        except:
            info["driver_name"] = "N/A"

        # 4. Tienda
        try:
            store_el = self.driver.find_element(
                By.XPATH,
                "//h5[contains(., 'Información de la tienda')]/ancestor::div[contains(@class, 'card')]//*[contains(@class, 'text--title')]",
            )
            info["store_name"] = store_el.text.strip()
        except:
            info["store_name"] = "Desconocida"

        # 5. Teléfono
        try:
            phone_el = self.driver.find_element(
                By.XPATH,
                "//*[contains(@class, 'delivery--information-single')]//a[starts-with(@href, 'tel:')]",
            )
            info["customer_phone"] = phone_el.text.strip()
        except:
            pass

        # 6. Fecha de creación
        try:
            date_el = self.driver.find_element(
                By.CSS_SELECTOR, ".mt-2.d-block.d-flex, .tio-date-range"
            )
            date_text = (
                date_el.text.replace("Created at:", "")
                .replace("Fecha de creación:", "")
                .strip()
            )
            if date_text:
                info["created_at_text"] = date_text
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
        items = []
        try:
            # Apunta a la tabla principal
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table.table tbody tr")
            for row in rows:
                try:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) < 4:
                        continue

                    # 1. Nombre
                    name = cols[1].find_element(By.TAG_NAME, "strong").text.strip()

                    # 2. Cantidad y Precio (Ej: 4 x USD 0,18)
                    qty = 1
                    price = 0.0
                    info_text = cols[1].find_element(By.TAG_NAME, "h6").text
                    match = re.search(
                        r"(\d+)\s*x\s*USD\s*([\d\.,]+)", info_text, re.IGNORECASE
                    )
                    if match:
                        qty = int(match.group(1))
                        price_str = match.group(2)
                        if "," in price_str and "." not in price_str:
                            price_str = price_str.replace(",", ".")
                        elif "." in price_str and "," in price_str:
                            price_str = price_str.replace(".", "").replace(",", ".")
                        price = float(price_str)

                    # 3. Código de barras
                    barcode = cols[2].get_attribute("title") or cols[2].text.strip()

                    # 4. Total
                    total = self._parse_money(cols[3].text)

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
        except:
            pass
        return items

    def _extract_payment_info(self) -> str:
        """
        🎯 [Misión 4 SRE] Extrae el método de pago de forma blindada.
        Actualizado para el nuevo DOM (ignora los ':' y extrae el último span).
        """
        payment_method = "Desconocido"

        try:
            # Estrategia A: Búsqueda SRE por el último span del título (Recomendada)
            try:
                # Apunta directamente al <h6> que contiene 'Método de pago' y extrae su último <span>
                element = self.driver.find_element(
                    By.XPATH, "//h6[contains(., 'Método de pago')]/span[last()]"
                )
                raw_payment = element.text.strip()

                # Filtro de Normalización para Base de Datos
                if raw_payment and raw_payment != ":":
                    texto_seguro = (
                        raw_payment.upper()
                    )  # Pasamos todo a mayúsculas para buscar mejor

                    if "PUNTO DE VENTA" in texto_seguro:
                        return "Punto de Venta"
                    elif "EFECTIVO" in texto_seguro:
                        return "Efectivo"
                    elif (
                        "PAGO MOVIL" in texto_seguro
                        or "PAGO MÓVIL" in texto_seguro
                        or "PMOVIL" in texto_seguro
                    ):
                        return "Pago Movil"
                    elif "ZELLE" in texto_seguro:
                        return "Zelle"
                    else:
                        return raw_payment
            except:
                pass

            # Estrategia B: Búsqueda por Bloque de Texto (Fallback si el HTML cambia de nuevo)
            # body_text = self.driver.find_element(By.TAG_NAME, "body").text
            import re

            match = re.search(r"Método de pago\s*:\s*(.+)", body_text, re.IGNORECASE)
            if match:
                raw_payment = match.group(1).strip()
                if raw_payment and raw_payment != ":":
                    if "Punto de Venta" in raw_payment:
                        return "Punto de Venta"
                    elif "Efectivo" in raw_payment:
                        return "Efectivo"
                    elif "Pago Movil" in raw_payment or "Pago Móvil" in raw_payment:
                        return "Pago Movil"
                    elif "Zelle" in raw_payment:
                        return "Zelle"
                    else:
                        return raw_payment

        except Exception as e:
            logger.warning(f"⚠️ No se pudo extraer el método de pago: {e}")

        return payment_method

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
            # body_text = self.driver.find_element(By.TAG_NAME, "body").text

            result.update(self._extract_basic_info())
            result.update(self._extract_financials())
            result.update(self._extract_maps())

            # Productos (Siempre)
            products = self._extract_products()
            if products:
                result["items"] = products

            if "cancelado" in result.get("status_text", "").lower():
                reason = self._extract_reason_smart()
                if reason:
                    result["cancellation_reason"] = reason

            # 🎯 INYECCIÓN SRE (MISIÓN 4): Capturamos el método de pago
            result["payment_method"] = self._extract_payment_info()

        except Exception as e:
            logger.error(f"❌ Error scraping {external_id}: {e}")

        return result
