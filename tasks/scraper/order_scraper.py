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
        self.session = requests.Session()

    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--ignore-certificate-errors")
        
        # --- CONFIGURACIÓN DE DESCARGAS ROBUSTA ---
        self.download_dir = "/tmp/downloads"
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, mode=0o777) # Permisos totales

        # Preferencias agresivas para evitar popups
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,  # Necesario para evitar bloqueos por 'archivo sospechoso'
            "profile.default_content_settings.popups": 0,
            "profile.content_settings.exceptions.automatic_downloads.*.setting": 1
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        service = Service()
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # --- DOBLE SEGURO: CDP COMMAND ---
        # Enviamos el comando directamente al navegador para asegurar la ruta
        self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {
            'behavior': 'allow',
            'downloadPath': self.download_dir
        })

    def login(self):
        """Login híbrido: Requests (rápido) + Selenium (si es necesario)"""
        # (Mantenemos tu lógica de login actual o la básica)
        # Para descarga de Excel NECESITAMOS Selenium logueado
        if self.driver: return True
        
        try:
            self.setup_driver()
            self.driver.get(self.LOGIN_URL)
            
            # Verificar si ya estamos dentro (cookies)
            if "dashboard" in self.driver.current_url: return True

            email_input = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.NAME, "email")))
            email_input.send_keys(settings.GOPHARMA_EMAIL)
            
            pass_input = self.driver.find_element(By.NAME, "password")
            pass_input.send_keys(settings.GOPHARMA_PASSWORD)
            pass_input.send_keys(Keys.RETURN)
            
            # Esperar redirección
            WebDriverWait(self.driver, 15).until(EC.url_contains("dashboard"))
            return True
        except Exception as e:
            logger.error(f"Error Login Selenium: {e}")
            self.close_driver()
            return False

    def close_driver(self):
        if self.driver:
            try: self.driver.quit()
            except: pass
            self.driver = None

    def download_official_excel(self, order_id: str):
        """
        Estrategia V4 (Blindada):
        1. Dispara evento JS en el botón CSV (evita bloqueos de Excel).
        2. Descarga el archivo ligero (~1KB).
        3. Reconstruye un .xlsx nativo usando openpyxl para entregar calidad.
        """
        if not self.login(): return None, None
        
        # Limpieza de zona de descarga
        for f in glob.glob(os.path.join(self.download_dir, "*")):
            try: os.remove(f)
            except: pass

        logger.info(f"🤖 Robot: Extrayendo CSV para pedido #{order_id}...")
        list_url = f"{self.BASE_URL}/admin/order/list/all"
        
        try:
            self.driver.get(list_url)
            
            # 1. FILTRADO
            search_input = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.ID, "datatableSearch_"))
            )
            search_input.clear()
            search_input.send_keys(order_id)
            search_input.send_keys(Keys.RETURN)
            time.sleep(2) # Pausa para que la tabla reaccione

            # 2. DESPLIEGUE DEL MENÚ
            try:
                # Forzamos el clic vía JS para abrir el dropdown
                export_btn = self.driver.find_element(By.CSS_SELECTOR, ".js-hs-unfold-invoker")
                self.driver.execute_script("arguments[0].click();", export_btn)
                time.sleep(0.5)
            except: pass

            # 3. DISPARO JS AL BOTÓN CSV
            # Buscamos el botón por texto o ID y le damos click() nativo
            try:
                # XPath robusto: busca un enlace que diga CSV o tenga ID relacionado
                csv_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(@id, 'export-csv') or contains(text(), 'CSV')]"))
                )
                self.driver.execute_script("arguments[0].click();", csv_btn)
                logger.info("✅ Clic en exportar CSV realizado.")
            except Exception as e:
                logger.error(f"❌ No se pudo clicar el botón CSV: {e}")
                return None, None
            
            # 4. ESPERAR ARCHIVO .CSV
            file_path = None
            # Esperamos 30s (es un archivo de 1KB, debería bajar en 1s)
            for i in range(30):
                files = glob.glob(os.path.join(self.download_dir, "*.csv"))
                if files:
                    candidate = max(files, key=os.path.getctime)
                    # Validación mínima de peso (bytes) para asegurar que no está vacío
                    if os.path.getsize(candidate) > 50: 
                        file_path = candidate
                        break
                time.sleep(1)
            
            if not file_path:
                logger.error("❌ El archivo CSV no apareció en el disco.")
                return None, None

            # 5. CONVERSIÓN A EXCEL (Magia)
            try:
                import csv
                import openpyxl
                from io import BytesIO

                # Leemos el CSV
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = f"Orden {order_id}"
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for r_idx, row in enumerate(reader, 1):
                        for c_idx, value in enumerate(row, 1):
                            ws.cell(row=r_idx, column=c_idx, value=value)
                
                # Ajuste de ancho de columnas (Estético)
                for column_cells in ws.columns:
                    length = max(len(str(cell.value) or "") for cell in column_cells)
                    ws.column_dimensions[column_cells[0].column_letter].width = length + 2

                # Guardamos en memoria
                output = BytesIO()
                wb.save(output)
                output.seek(0)
                excel_bytes = output.read()
                
                logger.info(f"✨ Conversión exitosa. Entregando XLSX ({len(excel_bytes)} bytes).")
                return excel_bytes, f"Orden_Oficial_{order_id}.xlsx"

            except ImportError:
                # Si falla openpyxl, entregamos el CSV tal cual
                logger.warning("⚠️ Librería openpyxl no encontrada. Entregando CSV original.")
                with open(file_path, "rb") as f:
                    content = f.read()
                return content, f"Orden_Oficial_{order_id}.csv"

        except Exception as e:
            logger.error(f"❌ Error en proceso descarga/conversión: {e}")
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
