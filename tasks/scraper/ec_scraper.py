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
        Dibuja un punto rojo y hace un clic avanzado (Pointer Events) para Flutter.
        """
        try:
            logger.info(f"🖱️ Click JS en: {desc} ({x}, {y})")
            
            # 1. DIBUJAR EL PUNTO ROJO (Para depuración visual)
            debug_script = f"""
                var dot = document.createElement('div');
                dot.style.position = 'absolute';
                dot.style.left = '{x}px';
                dot.style.top = '{y}px';
                dot.style.width = '20px';
                dot.style.height = '20px';
                dot.style.backgroundColor = 'red';
                dot.style.borderRadius = '50%';
                dot.style.zIndex = '999999';
                dot.style.pointerEvents = 'none'; // Para no bloquear el click real
                dot.style.border = '2px solid white';
                document.body.appendChild(dot);
            """
            self.driver.execute_script(debug_script)
            
            # 2. CLICK AVANZADO (Pointer Events para pantallas táctiles/Flutter)
            # Flutter web a veces ignora 'click' y escucha 'pointerdown/up'
            click_script = f"""
                var target = document.elementFromPoint({x}, {y});
                if(target) {{
                    // Simular toque/click completo
                    var opts = {{
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: {x},
                        clientY: {y},
                        screenX: {x},
                        screenY: {y}
                    }};
                    
                    target.dispatchEvent(new PointerEvent('pointerdown', opts));
                    target.dispatchEvent(new PointerEvent('mousedown', opts));
                    target.dispatchEvent(new PointerEvent('pointerup', opts));
                    target.dispatchEvent(new PointerEvent('mouseup', opts));
                    target.dispatchEvent(new PointerEvent('click', opts));
                }}
            """
            self.driver.execute_script(click_script)
            
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
