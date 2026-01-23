import logging
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from app.core.config import settings

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ECScraper:
    def __init__(self):
        self.BASE_URL = "https://ec.gopharma.com.ve/?from-splash=false"
        self.driver = None
        
        # --- USAR NUEVAS CREDENCIALES ---
        self.username = settings.EC_USER      # <--- CAMBIO AQUÍ
        self.password = settings.EC_PASSWORD  # <--- CAMBIO AQUÍ

    def setup_driver(self, headless=True):
        options = Options()
        
        # --- CONFIGURACIÓN DE PANTALLA CRÍTICA ---
        # Debe ser EXACTAMENTE la resolución donde tomaste las coordenadas
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        
        if headless:
            options.add_argument("--headless=new")
        
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        service = Service()
        self.driver = webdriver.Chrome(service=service, options=options)

    def close(self):
        if self.driver:
            self.driver.quit()

    def _click_at(self, x, y, desc="Elemento"):
        """
        Hace clic en X,Y usando JavaScript (Inmune a 'out of bounds').
        """
        try:
            logger.info(f"🖱️ Click JS en: {desc} ({x}, {y})")
            
            # MAGIA: Creamos un punto virtual y le damos click
            script = f"""
                var el = document.elementFromPoint({x}, {y});
                if(el) {{
                    el.click();
                    // También disparamos eventos de mouse por si acaso
                    var evt = new MouseEvent('click', {{
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: {x},
                        clientY: {y}
                    }});
                    el.dispatchEvent(evt);
                }} else {{
                    throw new Error("No hay elemento en esas coordenadas");
                }}
            """
            self.driver.execute_script(script)
            
            time.sleep(1.5)
            return True
        except Exception as e:
            logger.error(f"❌ Falló click en {desc}: {e}")
            return False

    def _type_text(self, text):
        """
        Escribe texto en el campo que tenga el foco activo.
        """
        try:
            actions = ActionChains(self.driver)
            actions.send_keys(text)
            actions.perform()
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"❌ Error escribiendo texto: {e}")

    def login(self):
        self.setup_driver(headless=True) 
        
        try:
            logger.info("🚀 StoreBot: Iniciando secuencia de Login...")
            self.driver.get(self.BASE_URL)
            
            logger.info("⏳ Esperando carga del motor Flutter (15s)...")
            time.sleep(15) # Damos más tiempo para que el anuncio termine de animar

            # --- TÁCTICA 1: TECLA ESCAPE (El mata-popups) ---
            logger.info("🎹 Enviando ESC para cerrar publicidad...")
            actions = ActionChains(self.driver)
            actions.send_keys(Keys.ESCAPE).perform()
            time.sleep(1)
            actions.send_keys(Keys.ESCAPE).perform() # Doble tap por si acaso
            time.sleep(2)

            # --- TÁCTICA 2: CLIC EN LA X (Respaldo) ---
            # Si el ESC no funcionó, intentamos la coordenada que mediste
            self._click_at(460, 111, "Cerrar Publicidad (Backup)")
            time.sleep(2)

            # --- SECUENCIA DE LOGIN ---
            
            # 2. Botón Inicio Sesión
            self._click_at(1174, 86, "Botón Login (Header)")
            time.sleep(3) # Esperar que abra el modal de login

            # 3. Cambiar a modo Usuario/Contraseña
            self._click_at(688, 698, "Switch a Password")

            # 4. Campo Usuario
            self._click_at(719, 309, "Input Usuario")
            # Borrar por si acaso tiene algo escrito
            ActionChains(self.driver).send_keys(Keys.CONTROL + "a").send_keys(Keys.DELETE).perform()
            
            logger.info(f"⌨️ Escribiendo usuario...")
            self._type_text(self.username)

            # 5. Campo Contraseña
            self._click_at(628, 400, "Input Password")
            logger.info("⌨️ Escribiendo contraseña...")
            self._type_text(self.password)

            # 6. Botón Ingresar
            self._click_at(610, 534, "BTN INGRESAR")
            
            # Esperar redirección
            time.sleep(8)
            
            # FOTO DE VERIFICACIÓN
            output_path = "/tmp/debug_ec_login.png"
            self.driver.save_screenshot(output_path)
            
            import os
            if os.path.exists(output_path):
                logger.info(f"📸 ÉXITO: Screenshot guardado en: {output_path}")
            
            return True

        except Exception as e:
            logger.error(f"❌ Crash crítico: {e}")
            return False
        finally:
            self.close()

# Bloque para prueba manual rápida: python tasks/scraper/ec_scraper.py
if __name__ == "__main__":
    bot = ECScraper()
    bot.login()
