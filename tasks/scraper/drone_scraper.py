import logging
import re
import time
import urllib.parse
from typing import Dict, Any, Optional, List, Tuple
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DroneScraper:
    def __init__(self):
        self.base_detail_url = "https://ecosistema.gopharma.com.ve/admin/order/details"
        self.driver = None
        self.wait_timeout = 10

    def setup_driver(self):
        if self.driver: return
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        service = ChromeService(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

    def login(self) -> bool:
        if not self.driver: self.setup_driver()
        try:
            self.driver.get("https://ecosistema.gopharma.com.ve/login/admin")
            wait = WebDriverWait(self.driver, self.wait_timeout)
            wait.until(EC.presence_of_element_located((By.NAME, "email"))).send_keys(settings.GOPHARMA_EMAIL)
            self.driver.find_element(By.NAME, "password").send_keys(settings.GOPHARMA_PASSWORD)
            try:
                self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            except:
                self.driver.find_element(By.NAME, "password").submit()
            time.sleep(3)
            return "login" not in self.driver.current_url
        except Exception as e:
            logger.error(f"❌ Drone Login error: {e}")
            return False

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except: pass
            self.driver = None

    # --- HELPERS ---
    def _parse_href_coords(self, href: str) -> Optional[Tuple[float, float]]:
        if not href: return None
        try:
            href = urllib.parse.unquote(href)
            match = re.search(r"q=loc:(-?\d+\.\d+)(?:\+|,|\s)(-?\d+\.\d+)", href)
            if match:
                return float(match.group(1)), float(match.group(2))
        except: pass
        return None

    def _extract_financials(self, body_text: str) -> Dict[str, float]:
        data = {}
        def get_val(keyword):
            try:
                pattern = re.escape(keyword) + r".*?USD\s*([\d\.]+)"
                match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
                return float(match.group(1)) if match else 0.0
            except: return 0.0
        
        data['service_fee'] = get_val("Tarifa de servicio")
        data['coupon_discount'] = get_val("Descuento del cupón")
        data['tips'] = get_val("Propinas al repartidor")
        data['real_delivery_fee'] = get_val("Tarifa de entrega")
        return data

    def _extract_reason_smart(self) -> Optional[str]:
        try:
            labels = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Motivo de cancelación') or contains(text(), 'Razón')]")
            for label in labels:
                try:
                    parent = label.find_element(By.XPATH, "./..")
                    text = parent.text.replace(label.text, "").strip().lstrip(":").strip()
                    if len(text) > 3: return text
                except: continue
        except: pass
        return None

    # ESTA ES LA FUNCIÓN QUE DABA PROBLEMAS (AHORA ALINEADA)
    def _extract_phone(self) -> Optional[str]:
        """Busca enlaces tipo tel:+58..."""
        try:
            # Buscamos cualquier enlace que empiece por tel:
            phone_link = self.driver.find_element(By.CSS_SELECTOR, "a[href^='tel:']")
            raw_phone = phone_link.get_attribute("href").replace("tel:", "")
            return raw_phone.strip()
        except: return None

    # --- SCRAPING PRINCIPAL ---
    def scrape_detail(self, external_id: str, mode: str) -> Dict[str, Any]:
        if not self.driver: self.setup_driver(); self.login()
        result = {"external_id": external_id}
        target_url = f"{self.base_detail_url}/{external_id}"
        
        try:
            self.driver.get(target_url)
            WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Finanzas (Siempre)
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            result.update(self._extract_financials(page_text))

            # Teléfono (Siempre)
            phone = self._extract_phone()
            if phone: result["customer_phone"] = phone

            if mode == 'coords':
                # --- ESTRATEGIA HÍBRIDA V6 ---
                
                # 1. TIENDA 
                try:
                    store_link = self.driver.find_element(By.CSS_SELECTOR, "a.__gap-5px[href*='maps.google.com']")
                    coords = self._parse_href_coords(store_link.get_attribute("href"))
                    if coords:
                        result["store_lat"], result["store_lng"] = coords
                except: pass

                # 2. CLIENTE - INTENTO A: Clase CSS
                client_coords = None
                try:
                    client_link = self.driver.find_element(By.CSS_SELECTOR, ".delivery--information-single a[href*='maps.google.com']")
                    client_coords = self._parse_href_coords(client_link.get_attribute("href"))
                    if client_coords: logger.info(f"📍 Cliente (CSS): {client_coords}")
                except: pass

                # 3. CLIENTE - INTENTO B: XPath Texto
                if not client_coords:
                    try:
                        client_link = self.driver.find_element(By.XPATH, "//h5[contains(., 'Información de entrega')]/ancestor::div[contains(@class, 'card')]//a[contains(@href, 'maps.google.com')]")
                        client_coords = self._parse_href_coords(client_link.get_attribute("href"))
                        if client_coords: logger.info(f"📍 Cliente (XPath): {client_coords}")
                    except: pass

                # 4. CLIENTE - INTENTO C: Fuerza Bruta
                if not client_coords:
                    try:
                        all_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='maps.google.com']")
                        all_coords = []
                        for l in all_links:
                            c = self._parse_href_coords(l.get_attribute("href"))
                            if c and c not in all_coords: all_coords.append(c)
                        
                        if len(all_coords) >= 2:
                            last = all_coords[-1]
                            if "store_lat" in result:
                                diff = abs(result["store_lat"] - last[0])
                                if diff > 0.001: 
                                    client_coords = last
                                    logger.info(f"📍 Cliente (Fallback): {client_coords}")
                            else:
                                client_coords = last
                    except: pass

                if client_coords:
                    result["customer_lat"], result["customer_lng"] = client_coords

            elif mode == 'reason':
                reason = self._extract_reason_smart()
                result["cancellation_reason"] = reason if reason else "No especificado"

        except Exception as e:
            logger.error(f"❌ Error scraping {external_id}: {e}")
        
        return result
