import logging
import re
import time
import urllib.parse
from typing import Dict, Any, Optional, Tuple
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
        except: return False

    def close_driver(self):
        if self.driver:
            try: self.driver.quit()
            except: pass
            self.driver = None

    # --- EXTRACTORES ---
    def _parse_money(self, text: str) -> float:
        try:
            match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)", text)
            return float(match.group(1).replace(',', '')) if match else 0.0
        except: return 0.0

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
        
        # Total Amount (Buscar "Total:" seguido de USD)
        data['total_amount'] = get_val("Total:")
        return data

    def _parse_href_coords(self, href: str) -> Optional[Tuple[float, float]]:
        if not href: return None
        try:
            href = urllib.parse.unquote(href)
            match = re.search(r"q=loc:(-?\d+\.\d+)(?:\+|,|\s)(-?\d+\.\d+)", href)
            if match: return float(match.group(1)), float(match.group(2))
        except: pass
        return None

    def _extract_maps(self) -> Dict[str, float]:
        result = {}
        try:
            # 1. CLIENTE (Contextual en tarjeta de entrega)
            try:
                client_link = self.driver.find_element(By.CSS_SELECTOR, ".delivery--information-single a[href*='maps.google.com']")
                c = self._parse_href_coords(client_link.get_attribute("href"))
                if c: result["customer_lat"], result["customer_lng"] = c
            except: pass

            # 2. TIENDA (Clase específica o posición)
            try:
                store_link = self.driver.find_element(By.CSS_SELECTOR, "a.__gap-5px[href*='maps.google.com']")
                c = self._parse_href_coords(store_link.get_attribute("href"))
                if c: result["store_lat"], result["store_lng"] = c
            except: pass
        except: pass
        return result

    def _extract_basic_info(self) -> Dict[str, str]:
        info = {}
        try:
            # Estado (Badge derecha)
            status_el = self.driver.find_element(By.XPATH, "//div[contains(@class, 'order-invoice-right')]//span[contains(@class, 'badge')]")
            info['status_text'] = status_el.text.strip()
        except: info['status_text'] = "pending"

        try: # Cliente
            el = self.driver.find_element(By.CSS_SELECTOR, ".customer--information-single .media-body span")
            info['customer_name'] = el.text.strip()
        except: info['customer_name'] = "Desconocido"

        try: # Tienda
            el = self.driver.find_element(By.CSS_SELECTOR, ".resturant--information-single .media-body span")
            info['store_name'] = el.text.strip()
        except: info['store_name'] = "Desconocida"

        try: # Repartidor
            # Buscar card que diga "Repartidor"
            el = self.driver.find_element(By.XPATH, "//h5[contains(., 'Repartidor')]/ancestor::div[@class='card-body']//span[contains(@class, 'text-body')]")
            info['driver_name'] = el.text.strip()
        except: info['driver_name'] = "N/A"
        
        try: # Teléfono Cliente
            el = self.driver.find_element(By.CSS_SELECTOR, ".delivery--information-single a[href^='tel:']")
            info['customer_phone'] = el.text.strip()
        except: pass

        # Fecha creación (Texto del header)
        try:
            header_text = self.driver.find_element(By.CLASS_NAME, "order-invoice-left").text
            date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{2}:\d{2})', header_text)
            if date_match: info['created_at_text'] = date_match.group(1)
        except: pass

        return info

    def _extract_reason_smart(self) -> Optional[str]:
        """Extrae el motivo limpiando prefijos basura con Regex."""
        try:
            # 1. Buscar en etiquetas específicas
            labels = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Motivo') or contains(text(), 'Razón') or contains(text(), 'del pedido')]")
            
            for label in labels:
                try:
                    parent = label.find_element(By.XPATH, "./..")
                    raw_text = parent.text.strip()
                    
                    # Regex: Busca "Motivo" o "del pedido", seguido opcionalmente de ":" o espacios
                    # y captura todo lo que sigue.
                    # Ej: "del pedido : Cliente no está" -> Captura "Cliente no está"
                    clean_match = re.search(r"(?:Motivo|Razón|del pedido)[\s:\-]*(.*)", raw_text, re.IGNORECASE | re.DOTALL)
                    
                    if clean_match:
                        cleaned = clean_match.group(1).strip()
                        if len(cleaned) > 2: return cleaned
                        
                except: continue
            
            # 2. Fallback: Buscar en todo el cuerpo
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            # Busca patrones comunes de Gopharma
            match = re.search(r"(?:Motivo|del pedido)[\s:\-]*(.*)", body_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
                
        except: pass
        return None

    def scrape_detail(self, external_id: str, mode: str = 'full') -> Dict[str, Any]:
        if not self.driver: self.setup_driver(); self.login()
        result = {"external_id": external_id}
        target_url = f"{self.base_detail_url}/{external_id}"
        
        try:
            self.driver.get(target_url)
            WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # 1. Información Básica
            result.update(self._extract_basic_info())
            
            # 2. Finanzas
            result.update(self._extract_financials(body_text))
            
            # 3. Mapas
            result.update(self._extract_maps())

            # 4. Motivos (si aplica)
            if "cancelado" in result.get('status_text', '').lower():
                # Lógica simplificada de búsqueda en texto
                match = re.search(r"(?:Motivo|Razón)(?:\s+de\s+cancelación)?\s*:?\s*(.*)", body_text, re.IGNORECASE)
                if match: result['cancellation_reason'] = match.group(1).split('\n')[0].strip()

        except Exception as e:
            logger.error(f"❌ Error scraping {external_id}: {e}")
        
        return result
