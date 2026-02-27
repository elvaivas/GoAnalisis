import shutil
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
        self.BASE_URL = f"{settings.LEGACY_BASE_URL}"
        self.LOGIN_URL = f"{self.BASE_URL}/login/admin"
        # --- AGREGAR ESTA LÍNEA ---
        self.orders_url = f"{self.BASE_URL}/admin/order/list/all"
        # --------------------------
        self.driver = None
        self.download_dir = "/tmp/downloads"

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

    def login(self):
        if self.driver:
            try:
                # Si estamos en dashboard o admin, es válido
                if (
                    "dashboard" in self.driver.current_url
                    or "/admin" in self.driver.current_url
                ):
                    return True
            except:
                pass
        else:
            self.setup_driver()

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"🔑 Intento de Login {attempt}/{max_retries}...")

                # LIMPIEZA PREVENTIVA: Borrar cookies para evitar "Session Expired"
                try:
                    self.driver.delete_all_cookies()
                except:
                    pass

                self.driver.get(self.LOGIN_URL)

                # MANEJO EXPLÍCITO DE ALERTAS (Doble seguridad)
                try:
                    WebDriverWait(self.driver, 3).until(EC.alert_is_present())
                    alert = self.driver.switch_to.alert
                    logger.warning(f"⚠️ Alerta detectada y aceptada: {alert.text}")
                    alert.accept()
                except:
                    pass

                # Validar si ya entró
                if "dashboard" in self.driver.current_url:
                    return True

                wait = WebDriverWait(self.driver, 20)
                email_input = wait.until(
                    EC.presence_of_element_located((By.NAME, "email"))
                )
                email_input.clear()
                email_input.send_keys(settings.GOPHARMA_EMAIL)
                time.sleep(0.5)

                pass_input = self.driver.find_element(By.NAME, "password")
                pass_input.clear()
                pass_input.send_keys(settings.GOPHARMA_PASSWORD)
                pass_input.send_keys(Keys.RETURN)

                # Esperamos dashboard O admin
                wait.until(
                    lambda d: "dashboard" in d.current_url or "/admin" in d.current_url
                )
                logger.info("✅ Login Exitoso.")
                return True

            except Exception as e:
                logger.warning(f"⚠️ Falló intento {attempt}: {e}")
                # Si hay una alerta bloqueando, intentamos aceptarla de nuevo
                try:
                    self.driver.switch_to.alert.accept()
                except:
                    pass

                if self.driver:
                    self.driver.save_screenshot(
                        f"/app/static/error_login_try_{attempt}.png"
                    )

                time.sleep(2)

        logger.error("❌ Se agotaron los intentos de Login.")
        self.close_driver()
        return False

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def get_official_data_json(self, order_id: str):
        if not self.login():
            return None

        # 1. Limpieza
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, mode=0o777)
        for f in glob.glob(os.path.join(self.download_dir, "*")):
            try:
                os.remove(f)
            except:
                pass

        # Permisos
        try:
            self.driver.execute_cdp_cmd(
                "Page.setDownloadBehavior",
                {"behavior": "allow", "downloadPath": self.download_dir},
            )
        except:
            pass

        logger.info(f"🤖 Robot: Auditando pedido #{order_id} (Smart Parser)...")

        try:
            self.driver.get(f"{self.BASE_URL}/admin/order/list/all")

            # 2. FILTRADO
            search_input = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.ID, "datatableSearch_"))
            )
            search_input.clear()
            search_input.send_keys(order_id)
            search_input.send_keys(Keys.RETURN)
            time.sleep(3)

            # 3. CLICK CSV (Sin target blank)
            try:
                export_btn = self.driver.find_element(
                    By.CSS_SELECTOR, ".js-hs-unfold-invoker"
                )
                self.driver.execute_script("arguments[0].click();", export_btn)
                time.sleep(1)
                csv_btn = self.driver.find_element(
                    By.XPATH,
                    "//a[contains(@id, 'export-csv') or contains(text(), 'CSV')]",
                )
                self.driver.execute_script(
                    "arguments[0].removeAttribute('target');", csv_btn
                )
                self.driver.execute_script("arguments[0].click();", csv_btn)
            except Exception as e:
                logger.error(f"❌ Falló clic UI: {e}")
                return None

            # 4. ESPERA
            file_path = None
            for i in range(40):
                files = os.listdir(self.download_dir)
                candidates = [f for f in files if f.endswith(".csv")]
                if candidates:
                    full_path = os.path.join(self.download_dir, candidates[0])
                    if os.path.getsize(full_path) > 50:
                        file_path = full_path
                        break
                time.sleep(1)

            if not file_path:
                return None

            # 5. PARSEO INTELIGENTE (AQUÍ ESTÁ LA MAGIA)
            logger.info(f"📄 Analizando estructura CSV: {file_path}")
            try:
                import csv

                # Leemos todas las líneas primero
                with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    lines = f.readlines()

                # A. BUSCAR DONDE EMPIEZAN LOS DATOS
                start_index = 0
                header_line = ""

                for i, line in enumerate(lines):
                    # Buscamos una columna clave que sabemos que existe
                    if "ID del pedido" in line or "order_id" in line or "Fecha" in line:
                        start_index = i
                        header_line = line
                        break

                logger.info(
                    f"🎯 Encabezados encontrados en línea {start_index}: {header_line.strip()[:50]}..."
                )

                # B. DETECTAR SEPARADOR (; o ,)
                # Contamos cuál aparece más en la línea de encabezado
                semicolons = header_line.count(";")
                commas = header_line.count(",")
                delimiter = ";" if semicolons > commas else ","
                logger.info(f"🔍 Separador detectado: '{delimiter}'")

                # C. PARSEAR DESDE LA LÍNEA CORRECTA
                data_list = []
                # Pasamos las líneas desde start_index en adelante
                reader = csv.DictReader(lines[start_index:], delimiter=delimiter)

                for row in reader:
                    # Limpieza profunda de keys y values
                    clean_row = {}
                    for k, v in row.items():
                        if k:  # Solo si la llave existe
                            # Quitamos espacios y caracteres raros del nombre de la columna
                            clean_key = k.strip().replace('"', "")
                            clean_val = (v or "").strip().replace('"', "")
                            clean_row[clean_key] = clean_val

                    data_list.append(clean_row)

                return data_list

            except Exception as e:
                logger.error(f"⚠️ Error parseando CSV: {e}")
                return None

        except Exception as e:
            logger.error(f"❌ Crash Scraper: {e}")
            return None
        finally:
            self.close_driver()

    def _parse_duration(self, row_element) -> str:
        """Extrae el texto de duración de la fila."""
        try:
            # Buscamos en la segunda columna (td[2]) que suele tener la fecha y duración
            # Ojo: XPath relativo a la fila
            div = row_element.find_element(
                By.XPATH, ".//div[contains(., 'Duración de tiempo')]"
            )
            return " ".join(div.text.replace("Duración de tiempo:", "").strip().split())
        except:
            return ""

    def get_recent_order_ids(self, limit: int = 25) -> List[Dict[str, str]]:
        """
        Retorna lista de dicts: [{'id': '123', 'duration': '1h 5m'}]
        """
        if not self.driver:
            self.setup_driver()
            self.login()
        orders_found = []

        try:
            self.driver.get(self.orders_url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "datatable"))
            )

            rows = self.driver.find_elements(
                By.XPATH, "//table[@id='datatable']/tbody/tr"
            )

            for row in rows:
                if len(orders_found) >= limit:
                    break
                try:
                    # Ignorar filas basura
                    if "Carrito" in row.text or "group-separator" in row.get_attribute(
                        "class"
                    ):
                        continue

                    # ID
                    link = row.find_element(
                        By.XPATH, ".//a[contains(@href, '/order/details/')]"
                    )
                    href = link.get_attribute("href")
                    order_id = href.split("/")[-1]

                    # Duración (La rescatamos aquí)
                    duration = self._parse_duration(row)

                    if order_id.isdigit():
                        orders_found.append({"id": order_id, "duration": duration})
                except:
                    continue

        except Exception as e:
            logger.error(f"Error get_recent: {e}")

        return orders_found

    def get_historical_ids(self, max_pages: int = None) -> List[Dict[str, str]]:
        """
        Navega por la paginación hasta el final.
        Si max_pages es None, sigue hasta que no haya botón 'Siguiente'.
        """
        if not self.driver:
            self.setup_driver()
            self.login()
        all_data = []

        try:
            self.driver.get(self.orders_url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "datatable"))
            )

            current_page = 1
            while True:
                # Freno de emergencia opcional (si se pasa un número explícito)
                if max_pages and current_page > max_pages:
                    logger.info(
                        f"🛑 Límite de seguridad alcanzado ({max_pages} págs). Deteniendo."
                    )
                    break

                logger.info(f"📄 Escaneando pág {current_page}...")

                rows = self.driver.find_elements(
                    By.XPATH, "//table[@id='datatable']/tbody/tr"
                )
                page_data = []

                for row in rows:
                    try:
                        if "Carrito" in row.text:
                            continue

                        link = row.find_element(
                            By.XPATH, ".//a[contains(@href, '/order/details/')]"
                        )
                        order_id = link.get_attribute("href").split("/")[-1]
                        duration = self._parse_duration(row)

                        if order_id.isdigit():
                            page_data.append({"id": order_id, "duration": duration})
                    except:
                        continue

                all_data.extend(page_data)

                # --- LÓGICA DE PAGINACIÓN INFINITA ---
                try:
                    next_btn = self.driver.find_element(
                        By.XPATH, "//a[@aria-label='Next »']"
                    )

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
        unique = {d["id"]: d for d in all_data}
        return list(unique.values())
