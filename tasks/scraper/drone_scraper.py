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
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-allow-origins=*")
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
            # 1. CLIENTE (Contextual)
            try:
                # Buscamos en tarjeta de entrega
                client_link = self.driver.find_element(By.CSS_SELECTOR, ".delivery--information-single a[href*='maps.google.com']")
                c = self._parse_href_coords(client_link.get_attribute("href"))
                if c: result["customer_lat"], result["customer_lng"] = c
            except: 
                # Fallback: XPath
                try:
                    client_link = self.driver.find_element(By.XPATH, "//h5[contains(., 'Información de entrega')]/ancestor::div[contains(@class, 'card-body')]//a[contains(@href, 'maps.google.com')]")
                    c = self._parse_href_coords(client_link.get_attribute("href"))
                    if c: result["customer_lat"], result["customer_lng"] = c
                except: pass

            # 2. TIENDA
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
            # Estado
            status_el = self.driver.find_element(By.XPATH, "//div[contains(@class, 'order-invoice-right')]//span[contains(@class, 'badge')]")
            info['status_text'] = status_el.text.strip()
        except: info['status_text'] = "pending"

        # --- CORRECCIÓN DEFINITIVA DE NOMBRES ---
        
        # 1. CLIENTE: Buscamos enlace que contenga 'customer/view'
        try: 
            # El nombre suele estar en un span o div dentro del enlace del cliente
            client_el = self.driver.find_element(By.CSS_SELECTOR, "a[href*='/customer/view/'] .media-body")
            # Limpiamos saltos de linea para obtener solo el nombre
            raw_text = client_el.text.split('\n')[0]
            info['customer_name'] = raw_text.strip()
        except: 
            info['customer_name'] = "Desconocido"

        # 2. REPARTIDOR: Buscamos enlace que contenga 'delivery-man'
        try: 
            driver_el = self.driver.find_element(By.CSS_SELECTOR, "a[href*='/delivery-man/'] .media-body span")
            info['driver_name'] = driver_el.text.strip()
        except: info['driver_name'] = "N/A"
        
        # 3. TIENDA: Buscamos enlace que contenga 'store/view'
        try: 
            store_el = self.driver.find_element(By.CSS_SELECTOR, "a[href*='/store/view/'] .media-body span")
            info['store_name'] = store_el.text.strip()
        except: info['store_name'] = "Desconocida"

        # 4. TELEFONO CLIENTE
        try: 
            el = self.driver.find_element(By.CSS_SELECTOR, ".delivery--information-single a[href^='tel:']")
            info['customer_phone'] = el.text.strip()
        except: pass

        # Fecha
        try:
            header_text = self.driver.find_element(By.CLASS_NAME, "order-invoice-left").text
            date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{2}:\d{2})', header_text)
            if date_match: info['created_at_text'] = date_match.group(1)
        except: pass

        return info

    def _extract_reason_smart(self) -> Optional[str]:
        try:
            labels = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Motivo de cancelación') or contains(text(), 'Razón')]")
            for label in labels:
                try:
                    parent = label.find_element(By.XPATH, "./..")
                    raw_text = parent.text
                    garbage = [label.text, "Motivo de cancelación", "del pedido", ":", "-"]
                    for g in garbage: raw_text = raw_text.replace(g, "")
                    clean = raw_text.strip()
                    if len(clean) > 2: return clean
                except: continue
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
            
            result.update(self._extract_basic_info())
            result.update(self._extract_financials(body_text))
            result.update(self._extract_maps())

            if "cancelado" in result.get('status_text', '').lower():
                reason = self._extract_reason_smart()
                if reason: result['cancellation_reason'] = reason

        except Exception as e:
            logger.error(f"❌ Error scraping {external_id}: {e}")
        
        return result
