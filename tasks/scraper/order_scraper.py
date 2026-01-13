import logging
import time
import re
import os
import glob
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.service import Service
from app.core.config import settings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderScraper:
    def __init__(self):
        self.BASE_URL = "https://ecosistema.gopharma.com.ve"
        self.LOGIN_URL = f"{self.BASE_URL}/login/admin"
        self.driver = None
        self.download_dir = "/tmp/downloads" # Definido centralmente

    def setup_driver(self):
        if self.driver: return
        
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--disable-popup-blocking") # VITAL para tu caso
        
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, mode=0o777)

        # Preferencias agresivas
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "profile.default_content_settings.popups": 0,
            "profile.content_settings.exceptions.automatic_downloads.*.setting": 1
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        service = Service()
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Comando CDP para asegurar permisos de escritura
        try:
            self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                'behavior': 'allow',
                'downloadPath': self.download_dir
            })
        except: pass

    def login(self):
        if self.driver:
            try:
                if "dashboard" in self.driver.current_url: return True
            except: pass
        else:
            self.setup_driver()
        
        try:
            logger.info("🔑 Iniciando Login (Timeout aumentado 30s)...")
            self.driver.get(self.LOGIN_URL)
            
            # Verificar si ya estamos dentro
            if "dashboard" in self.driver.current_url: return True

            # AUMENTAMOS EL TIMEOUT A 30 SEGUNDOS (Antes 15)
            email_input = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.NAME, "email"))
            )
            email_input.clear()
            email_input.send_keys(settings.GOPHARMA_EMAIL)
            
            pass_input = self.driver.find_element(By.NAME, "password")
            pass_input.clear()
            pass_input.send_keys(settings.GOPHARMA_PASSWORD)
            pass_input.send_keys(Keys.RETURN)
            
            WebDriverWait(self.driver, 30).until(EC.url_contains("dashboard"))
            logger.info("✅ Login Exitoso.")
            return True

        except Exception as e:
            logger.error(f"❌ Error Login Selenium: {e}")
            if self.driver:
                self.driver.save_screenshot("/app/static/error_login.png")
            self.close_driver()
            return False

    def close_driver(self):
        if self.driver:
            try: self.driver.quit()
            except: pass
            self.driver = None

    def download_official_excel(self, order_id: str):
        if not self.login(): return None, None
        
        # 1. Limpieza
        for f in glob.glob(os.path.join(self.download_dir, "*")):
            try: os.remove(f)
            except: pass

        # REFUERZO DE PERMISOS
        try:
            self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': self.download_dir})
        except: pass

        logger.info(f"🤖 Robot: Buscando CSV para #{order_id}...")
        
        try:
            # Navegar a la lista
            self.driver.get(f"{self.BASE_URL}/admin/order/list/all")
            
            # 2. FILTRADO
            search_input = WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "datatableSearch_")))
            search_input.clear()
            search_input.send_keys(order_id)
            search_input.send_keys(Keys.RETURN)
            time.sleep(3) 

            # 3. INTERACCIÓN QUIRÚRGICA
            try:
                # Abrir Dropdown
                export_btn = self.driver.find_element(By.CSS_SELECTOR, ".js-hs-unfold-invoker")
                self.driver.execute_script("arguments[0].click();", export_btn)
                time.sleep(1)
                
                # Encontrar botón CSV
                csv_btn = self.driver.find_element(By.XPATH, "//a[contains(@id, 'export-csv') or contains(text(), 'CSV')]")
                
                # --- EL TRUCO MAESTRO (DOM SANITIZATION) ---
                # Removemos target="_blank" para obligar descarga en la misma pestaña
                # Esto evita el bloqueo "about:blank#blocked"
                self.driver.execute_script("arguments[0].removeAttribute('target');", csv_btn)
                logger.info("💉 JS: Atributo target='_blank' eliminado.")
                
                # Click nativo
                self.driver.execute_script("arguments[0].click();", csv_btn)
                logger.info("✅ Clic en CSV realizado.")
                
            except Exception as e:
                logger.error(f"❌ Falló clic UI: {e}")
                self.driver.save_screenshot("/app/static/error_menu_click.png")
                return None, None
            
            # 4. ESPERA ACTIVA
            file_path = None
            for i in range(40):
                files = os.listdir(self.download_dir)
                if i % 5 == 0: logger.info(f"⏳ [{i}s] Carpeta: {files}")
                
                candidates = [f for f in files if f.endswith(".csv")]
                if candidates:
                    full_path = os.path.join(self.download_dir, candidates[0])
                    if os.path.getsize(full_path) > 50:
                        file_path = full_path
                        break
                time.sleep(1)
            
            if not file_path:
                logger.error("❌ Timeout descarga CSV.")
                self.driver.save_screenshot("/app/static/error_timeout.png")
                return None, None

            # 5. CONVERSIÓN CSV -> XLSX
            logger.info(f"📄 Procesando: {file_path}")
            try:
                import csv
                import openpyxl
                from io import BytesIO

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = f"Orden {order_id}"
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for r_idx, row in enumerate(reader, 1):
                        for c_idx, value in enumerate(row, 1):
                            ws.cell(row=r_idx, column=c_idx, value=value)
                
                for column_cells in ws.columns:
                    length = max(len(str(cell.value) or "") for cell in column_cells)
                    ws.column_dimensions[column_cells[0].column_letter].width = length + 2

                output = BytesIO()
                wb.save(output)
                output.seek(0)
                return output.read(), f"Orden_Oficial_{order_id}.xlsx"

            except ImportError:
                with open(file_path, "rb") as f: content = f.read()
                return content, f"Orden_Oficial_{order_id}.csv"

        except Exception as e:
            logger.error(f"❌ Crash Scraper: {e}")
            self.driver.save_screenshot("/app/static/error_crash.png")
            return None, None
        finally:
            self.close_driver()

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
