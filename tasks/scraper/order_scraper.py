import time
import logging
import re
from typing import List, Dict, Any, Optional, Callable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderScraper:
    def __init__(self):
        self.base_url = "https://ecosistema.gopharma.com.ve/login/admin"
        self.orders_url = "https://ecosistema.gopharma.com.ve/admin/order/list/all"
        self.driver = None
        self.wait_timeout = 15

    def setup_driver(self):
        if self.driver: return
        logger.info("[Scraper] Configurando el driver de Selenium...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        service = ChromeService(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(180)

    def login(self) -> bool:
        if not self.driver: self.setup_driver()
        try:
            logger.info(f"🔐 Iniciando sesión en {self.base_url}...")
            self.driver.get(self.base_url)
            wait = WebDriverWait(self.driver, self.wait_timeout)
            wait.until(EC.presence_of_element_located((By.NAME, "email"))).clear()
            self.driver.find_element(By.NAME, "email").send_keys(settings.GOPHARMA_EMAIL)
            self.driver.find_element(By.NAME, "password").clear()
            self.driver.find_element(By.NAME, "password").send_keys(settings.GOPHARMA_PASSWORD)
            try:
                self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            except:
                self.driver.find_element(By.NAME, "password").submit()
            time.sleep(5)
            if "login" in self.driver.current_url:
                logger.error("❌ Fallo en el login.")
                return False
            logger.info("✅ Login exitoso.")
            return True
        except Exception as e:
            logger.error(f"❌ Error crítico en login: {e}")
            return False

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except: pass
            self.driver = None

    def _clean_text(self, text: str) -> str:
        if not text: return ""
        return " ".join(text.split())

    def _parse_money(self, text: str) -> float:
        if not text: return 0.0
        match = re.search(r"(\d+\.\d+)", text)
        if match: return float(match.group(1))
        return 0.0

    def _parse_duration(self, cell_element) -> Optional[str]:
        try:
            div = cell_element.find_element(By.XPATH, ".//div[contains(., 'Duración de tiempo')]")
            return " ".join(div.text.replace("Duración de tiempo:", "").strip().split())
        except NoSuchElementException:
            return None

    def scrape_orders(self, limit: int = 100, batch_callback: Callable = None) -> List[Dict[str, Any]]:
        if not self.driver: self.setup_driver(); self.login()
        
        all_orders = [] 
        batch_buffer = [] 
        
        try:
            logger.info(f"🕷️ Navegando a: {self.orders_url}")
            self.driver.get(self.orders_url)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.ID, "datatable")))

            processed = 0
            while processed < limit:
                rows = self.driver.find_elements(By.XPATH, "//table[@id='datatable']/tbody/tr")
                if not rows: break

                logger.info(f"📄 Procesando página. Filas visibles: {len(rows)}")
                
                for row in rows:
                    if processed >= limit: break
                    try:
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) < 10: continue

                        # 1. Extracción de Datos Crudos
                        id_link = cols[1].find_element(By.TAG_NAME, "a")
                        external_id = id_link.text.strip()
                        
                        # Fecha limpia
                        raw_date_text = cols[2].text.strip()
                        date_text = raw_date_text.split('\n')[0].strip()
                        duration = self._parse_duration(cols[2])

                        customer = self._clean_text(cols[3].text.split('\n')[0])
                        driver_text = self._clean_text(cols[4].text.split('\n')[0]) # Nombre del chofer
                        store = self._clean_text(cols[5].text.split('\n')[0])
                        status_text = cols[10].text.lower() # Texto del estado (ej: "entregado", "proceso")

                        # 2. DETECCIÓN INTELIGENTE DE ESTADO
                        # Verificamos si hay un chofer real asignado (No es N/A ni vacío)
                        has_driver = "N/A" not in driver_text and len(driver_text) > 2
                        
                        db_status = "pending"

                        if "entregado" in status_text: 
                            db_status = "delivered"
                        
                        elif "cancelado" in status_text or "rechazado" in status_text: 
                            db_status = "canceled"
                        
                        elif "camino" in status_text or "ruta" in status_text:
                            # Si dice "en camino", asumimos que ya salió
                            db_status = "on_the_way"
                        
                        elif "repartidor" in status_text or "asignado" in status_text or "proceso" in status_text:
                            # AQUÍ ESTÁ LA MAGIA:
                            if has_driver:
                                db_status = "driver_assigned" # Tiene nombre -> Ya se lo asignaron
                            else:
                                db_status = "processing"      # Dice N/A -> Aún cocinando/buscando
                        
                        elif "confirmado" in status_text:
                            db_status = "confirmed"
                        
                        else:
                            db_status = "pending"

                        # 3. LÓGICA DE TIPO (CORREGIDA PARA EN VIVO)
                        order_type = "Delivery" # Por defecto asumimos lo más común

                        if db_status == "canceled":
                            order_type = None # No nos interesa clasificar cancelados
                        
                        elif has_driver:
                            # Si tiene nombre de chofer, 100% es Delivery
                            order_type = "Delivery"
                        
                        else:
                            # CASO DELICADO: No hay chofer (N/A)
                            
                            # Opción A: Ya se entregó y nunca tuvo chofer -> Es Pickup real
                            if db_status == "delivered":
                                order_type = "Pickup"
                            
                            # Opción B: Está pendiente/proceso y dice N/A.
                            # ANTES: Lo marcábamos Pickup (Error).
                            # AHORA: Lo mantenemos como Delivery (esperando asignación).
                            # Solo si el texto del driver dice explícitamente "Retiro" lo cambiamos.
                            elif "retiro" in driver_text.lower() or "pickup" in driver_text.lower():
                                order_type = "Pickup"
                            else:
                                order_type = "Delivery" 

                        order_obj = {
                            "external_id": external_id,
                            "store_name": store,
                            "customer_name": customer,
                            "driver_name": driver_text,
                            "status": db_status,
                            "order_type": order_type, # <--- Dato corregido
                            "total_amount": self._parse_money(cols[9].text),
                            "delivery_fee": self._parse_money(cols[8].text),
                            "duration": duration,
                            "created_at_text": date_text
                        }
                        
                        all_orders.append(order_obj)
                        batch_buffer.append(order_obj)
                        processed += 1
                    except Exception: continue
                
                # Batch save
                if batch_callback and len(batch_buffer) >= 50:
                    logger.info(f"💾 Buffer lleno ({len(batch_buffer)}). Ejecutando guardado intermedio...")
                    batch_callback(batch_buffer)
                    batch_buffer = []

                # Paginación
                try:
                    next_btn = self.driver.find_element(By.XPATH, "//a[@aria-label='Next »']")
                    if "disabled" in next_btn.find_element(By.XPATH, "./..").get_attribute("class"): break
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    time.sleep(3)
                except: break
            
            # Guardado final
            if batch_callback and batch_buffer:
                logger.info(f"💾 Guardando últimos {len(batch_buffer)} pedidos...")
                batch_callback(batch_buffer)

        except Exception as e:
            logger.error(f"❌ Scrape error: {e}")
        
        return all_orders
