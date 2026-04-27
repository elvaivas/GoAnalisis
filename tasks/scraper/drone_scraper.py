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
        """
        Inicia sesión en el panel de GoPharma.
        (Actualizado con los selectores del nuevo rediseño y variables del .env)
        """
        # 1. Verificación de driver (evita fugas de memoria)
        if not self.driver:
            self.setup_driver()

        try:
            logger.info("🔐 Iniciando secuencia de Login...")

            # 2. Navegar a la ruta confirmada (usando el base_url del .env)
            self.driver.get(f"{settings.LEGACY_BASE_URL}/login/admin")

            # 3. Espera inteligente (SRE) en lugar de un sleep fijo
            wait = WebDriverWait(self.driver, 15)

            # 4. Capturar inyector de Email usando el nuevo ID
            email_input = wait.until(
                EC.presence_of_element_located((By.ID, "signinSrEmail"))
            )
            email_input.clear()
            email_input.send_keys(settings.GOPHARMA_EMAIL)  # <-- Tomado del .env

            # 5. Capturar inyector de Password usando el nuevo ID
            pass_input = self.driver.find_element(By.ID, "signupSrPassword")
            pass_input.clear()
            pass_input.send_keys(settings.GOPHARMA_PASSWORD)  # <-- Tomado del .env

            # 6. Acción de Entrar
            try:
                submit_btn = self.driver.find_element(
                    By.XPATH, "//button[@type='submit']"
                )
                submit_btn.click()
            except:
                # Fallback por si el botón está oculto por algún banner
                pass_input.submit()

            # 7. Validación: Esperamos hasta que la palabra 'login' desaparezca de la URL
            wait.until(lambda d: "login" not in d.current_url)

            logger.info("✅ Login exitoso. ¡Estamos dentro del nuevo panel!")
            return True

        except Exception as e:
            logger.error(f"❌ Error crítico en login: {e}")
            # Foto satelital automática en caso de falla para depuración futura
            if self.driver:
                try:
                    self.driver.save_screenshot("/app/static/error_login_final.png")
                except:
                    pass
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
        """Extrae los costos soportando Inglés y Español"""
        data = {}
        mapping = {
            "service_fee": ["Tarifa de servicio", "Service fee"],
            "coupon_discount": ["Cupón de descuento", "Coupon discount"],
            "tips": ["Consejos para el repartidor", "Delivery man tips"],
            "real_delivery_fee": ["Tarifa de envío", "Delivery fee"],
            "total_amount": ["Total"],
            "product_price": ["Precio de los artículos", "Items price"],
        }

        for db_key, labels in mapping.items():
            data[db_key] = 0.0
            for label in labels:
                try:
                    xpath = f"//dl[contains(@class, 'row')]//dt[contains(., '{label}')]/following-sibling::dd[1]"
                    element = self.driver.find_element(By.XPATH, xpath)
                    val = self._parse_money(element.text)
                    if val > 0:
                        data[db_key] = val
                        break  # Encontró el correcto, pasa al siguiente db_key
                except:
                    continue

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
        """Extracción SRE actualizada: Coordenadas desde DOM inputs y regex de scripts"""
        result = {}

        # 1. COORDENADAS DEL CLIENTE (Extraídas de los inputs del modal de envío)
        try:
            lat_el = self.driver.find_element(By.ID, "latitude")
            lng_el = self.driver.find_element(By.ID, "longitude")

            lat_val = lat_el.get_attribute("value")
            lng_val = lng_el.get_attribute("value")

            if lat_val and lng_val:
                result["customer_lat"] = float(lat_val)
                result["customer_lng"] = float(lng_val)
        except Exception as e:
            logger.debug(f"Mapas Cliente falló: {e}")

        # 2. COORDENADAS DE LA TIENDA (Extraídas del script de inicialización del mapa)
        try:
            page_source = self.driver.page_source
            # Expresión regular que busca la inicialización: new google.maps.LatLng(10.505..., -66.906...)
            match = re.search(
                r"new\s+google\.maps\.LatLng\(\s*([-.\d]+),\s*([-.\d]+)\)", page_source
            )
            if match:
                result["store_lat"] = float(match.group(1))
                result["store_lng"] = float(match.group(2))
        except Exception as e:
            logger.debug(f"Mapas Tienda falló: {e}")

        return result

    def _extract_basic_info(self) -> Dict[str, str]:
        """Extracción SRE anclada a URIs (Inmune a cambios de idioma)"""
        info = {}

        # 1. Estatus (Busca el bloque que diga Status)
        try:
            status_el = self.driver.find_element(
                By.XPATH,
                "//h6[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'status')]/span[contains(@class, 'badge')]",
            )
            info["status_text"] = status_el.text.strip()
        except:
            info["status_text"] = ""

        # 2. Cliente (Anclado al href)
        try:
            client_el = self.driver.find_element(
                By.XPATH,
                "//a[contains(@href, 'customer/view')]//span[contains(@class, 'text-hover-primary') or contains(@class, 'fz--14px')]",
            )
            info["customer_name"] = client_el.text.strip()
        except:
            info["customer_name"] = "Desconocido"

        # 3. Repartidor (Anclado al href)
        try:
            driver_el = self.driver.find_element(
                By.XPATH,
                "//a[contains(@href, 'delivery-man/preview')]//span[contains(@class, 'text-hover-primary') or contains(@class, 'text-body')]",
            )
            info["driver_name"] = driver_el.text.strip()
        except:
            info["driver_name"] = "N/A"

        # 4. Tienda (Anclado al href)
        try:
            store_el = self.driver.find_element(
                By.XPATH,
                "//a[contains(@href, 'store/view')]//span[contains(@class, 'text-hover-primary') or contains(@class, 'fz--14px')]",
            )
            info["store_name"] = store_el.text.strip()
        except:
            info["store_name"] = "Desconocida"

        # 5. Teléfono
        try:
            phone_el = self.driver.find_element(
                By.XPATH, "//a[starts-with(@href, 'tel:')]"
            )
            info["customer_phone"] = phone_el.text.strip()
        except:
            pass

        # 6. Fecha de creación
        try:
            date_el = self.driver.find_element(
                By.XPATH, "//i[contains(@class, 'tio-date-range')]/parent::span"
            )
            info["created_at_text"] = date_el.text.strip()
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
        """Extrae el método de pago (Bilingüe)"""
        try:
            # Estrategia A: Bilingüe
            element = self.driver.find_element(
                By.XPATH,
                "//h6[contains(., 'Método de pago') or contains(., 'Payment method')]/span[last()]",
            )
            raw_payment = element.text.strip().upper()

            if "PUNTO DE VENTA" in raw_payment:
                return "Punto de Venta"
            if "EFECTIVO" in raw_payment:
                return "Efectivo"
            if "PAGO" in raw_payment or "PMOVIL" in raw_payment:
                return "Pago Movil"
            if "ZELLE" in raw_payment:
                return "Zelle"

            return (
                element.text.strip() if element.text.strip() != ":" else "Desconocido"
            )
        except:
            return "Desconocido"

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
