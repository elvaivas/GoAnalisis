import logging
import time
import re
import os
import glob
from typing import List, Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.service import Service as ChromeService
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderScraper:
    def __init__(self):
        self.base_url = "https://ecosistema.gopharma.com.ve/login/admin"
        self.orders_url = "https://ecosistema.gopharma.com.ve/admin/order/list/all"
        self.driver = None

    def setup_driver(self):
        if self.driver: return
        logger.info("[Scraper] Iniciando Driver (Nativo)...")
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-allow-origins=*")
        chrome_options.add_argument("user-agent=Mozilla/5.0 ...") # (Tu user agent)
        
        # --- CORRECCIÓN: USAR SERVICE VACÍO ---
        service = ChromeService() 
        # --------------------------------------

        # CARPETA DE DESCARGAS
        download_dir = "/tmp/downloads"
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

    def login(self) -> bool:
        if not self.driver: self.setup_driver()
        if "login" not in self.driver.current_url and "admin" in self.driver.current_url: return True
        try:
            self.driver.get(self.base_url)
            wait = WebDriverWait(self.driver, 15)
            wait.until(EC.presence_of_element_located((By.NAME, "email"))).send_keys(settings.GOPHARMA_EMAIL)
            self.driver.find_element(By.NAME, "password").send_keys(settings.GOPHARMA_PASSWORD)
            try: self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            except: self.driver.find_element(By.NAME, "password").submit()
            time.sleep(5)
            return "login" not in self.driver.current_url
        except: return False

    def close_driver(self):
        if self.driver:
            try: self.driver.quit()
            except: pass
            self.driver = None

    def download_official_excel(self, order_id: str):
        """
        Robot que entra, filtra por ID y descarga el Excel oficial.
        """
        if not self.login():
            return None, None

        logger.info(f"🤖 Iniciando robot de descarga para pedido #{order_id}...")
        
        # URL de la lista de pedidos
        list_url = f"{self.BASE_URL}/admin/order/list/all"
        
        try:
            self.driver.get(list_url)
            
            # 1. BUSCAR PEDIDO (Filtrar)
            # Esperamos que el input de búsqueda sea visible
            search_input = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.ID, "datatableSearch_"))
            )
            search_input.clear()
            search_input.send_keys(order_id)
            search_input.send_keys(Keys.RETURN) # Presionar Enter
            
            # Esperamos un poco para que la tabla se actualice (loading spinner o similar)
            time.sleep(2) 

            # 2. ABRIR MENÚ EXPORTAR
            # Buscamos el botón "Exportar" por su clase o texto
            # Nota: El HTML dice que tiene clase 'js-hs-unfold-invoker' y texto 'Exportar'
            export_menu_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Exportar')]"))
            )
            export_menu_btn.click()
            time.sleep(0.5) # Pequeña pausa para animación del menú

            # 3. CLIC EN EXCEL
            excel_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "export-excel"))
            )
            
            # --- TRUCO CRÍTICO: Configurar descarga en carpeta temporal ---
            # Esto se debió configurar al iniciar el driver, pero asumimos descarga a /tmp o Downloads
            # Si usas Docker headless, los archivos van a una carpeta interna.
            # Vamos a intentar hacer click y buscar el archivo más reciente.
            
            excel_btn.click()
            
            # Esperar a que se descargue (Timeout 15s)
            # Buscamos en la carpeta de descargas del contenedor
            download_dir = "/tmp/downloads" # Asegúrate de configurar esto en setup_driver
            
            # Esperamos hasta que aparezca un archivo nuevo
            file_path = None
            for _ in range(30): # 15 segundos max
                files = glob.glob(os.path.join(download_dir, "*.xlsx"))
                if files:
                    # Buscamos el más reciente
                    file_path = max(files, key=os.path.getctime)
                    break
                time.sleep(0.5)
            
            if file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    content = f.read()
                
                # Limpieza: Borrar archivo del contenedor para no llenar disco
                os.remove(file_path)
                
                filename = f"Orden_Oficial_{order_id}.xlsx"
                return content, filename
            else:
                logger.error("⏳ Timeout esperando descarga del archivo.")
                return None, None

        except Exception as e:
            logger.error(f"❌ Error en robot de descarga: {e}")
            return None, None

    def _parse_duration(self, row_element) -> str:
        """Extrae el texto de duración de la fila."""
        try:
            # Buscamos en la segunda columna (td[2]) que suele tener la fecha y duración
            # Ojo: XPath relativo a la fila
            div = row_element.find_element(By.XPATH, ".//div[contains(., 'Duración de tiempo')]")
            return " ".join(div.text.replace("Duración de tiempo:", "").strip().split())
        except: return ""

    def get_recent_order_ids(self, limit: int = 25) -> List[Dict[str, str]]:
        """
        Retorna lista de dicts: [{'id': '123', 'duration': '1h 5m'}]
        """
        if not self.driver: self.setup_driver(); self.login()
        orders_found = []
        
        try:
            self.driver.get(self.orders_url)
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.ID, "datatable")))
            
            rows = self.driver.find_elements(By.XPATH, "//table[@id='datatable']/tbody/tr")
            
            for row in rows:
                if len(orders_found) >= limit: break
                try:
                    # Ignorar filas basura
                    if "Carrito" in row.text or "group-separator" in row.get_attribute("class"): continue

                    # ID
                    link = row.find_element(By.XPATH, ".//a[contains(@href, '/order/details/')]")
                    href = link.get_attribute("href")
                    order_id = href.split("/")[-1]
                    
                    # Duración (La rescatamos aquí)
                    duration = self._parse_duration(row)

                    if order_id.isdigit():
                        orders_found.append({"id": order_id, "duration": duration})
                except: continue
                
        except Exception as e:
            logger.error(f"Error get_recent: {e}")
        
        return orders_found

    def get_historical_ids(self, max_pages: int = None) -> List[Dict[str, str]]:
        """
        Navega por la paginación hasta el final.
        Si max_pages es None, sigue hasta que no haya botón 'Siguiente'.
        """
        if not self.driver: self.setup_driver(); self.login()
        all_data = []
        
        try:
            self.driver.get(self.orders_url)
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.ID, "datatable")))
            
            current_page = 1
            while True:
                # Freno de emergencia opcional (si se pasa un número explícito)
                if max_pages and current_page > max_pages:
                    logger.info(f"🛑 Límite de seguridad alcanzado ({max_pages} págs). Deteniendo.")
                    break

                logger.info(f"📄 Escaneando pág {current_page}...")
                
                rows = self.driver.find_elements(By.XPATH, "//table[@id='datatable']/tbody/tr")
                page_data = []
                
                for row in rows:
                    try:
                        if "Carrito" in row.text: continue
                        
                        link = row.find_element(By.XPATH, ".//a[contains(@href, '/order/details/')]")
                        order_id = link.get_attribute("href").split("/")[-1]
                        duration = self._parse_duration(row)
                        
                        if order_id.isdigit():
                            page_data.append({"id": order_id, "duration": duration})
                    except: continue
                
                all_data.extend(page_data)
                
                # --- LÓGICA DE PAGINACIÓN INFINITA ---
                try:
                    next_btn = self.driver.find_element(By.XPATH, "//a[@aria-label='Next »']")
                    
                    # Verificamos si el botón está deshabilitado (clase 'disabled' en el padre <li>)
                    parent = next_btn.find_element(By.XPATH, "./..")
                    if "disabled" in parent.get_attribute("class"):
                        logger.info("🚫 Fin de la paginación (Botón deshabilitado).")
                        break
                    
                    # Click para avanzar
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    
                    # Esperamos que cargue la siguiente página
                    # (Pequeña pausa técnica para no saturar y dar tiempo al DOM)
                    time.sleep(2) 
                    
                    current_page += 1
                except NoSuchElementException:
                    logger.info("🚫 No se encontró botón siguiente. Fin de la lista.")
                    break
                except Exception as e:
                    logger.error(f"⚠️ Error al cambiar de página: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error backfill: {e}")
        
        # Deduplicar
        unique = {d['id']: d for d in all_data}
        return list(unique.values())
