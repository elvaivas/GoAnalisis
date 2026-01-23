import logging
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ECScraper:
    def __init__(self):
        self.BASE_URL = "https://ec.gopharma.com.ve/?from-splash=false"
        self.driver = None
        self.username = settings.EC_USER
        self.password = settings.EC_PASSWORD

    def setup_driver(self, headless=True):
        options = Options()
        # Mantenemos 1366x768 ya que ahí mediste las coordenadas
        options.add_argument("--window-size=1366,768")
        
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

    def _click_at(self, x, y, desc="Elemento", step=0):
        """
        Dibuja un punto rojo NUMERADO y hace un clic avanzado.
        """
        try:
            logger.info(f"🖱️ [{step}] Click en: {desc} ({x}, {y})")
            
            # 1. DIBUJAR PUNTO NUMERADO
            # Ponemos el número dentro del punto para ver el orden en la foto
            debug_script = f"""
                var dot = document.createElement('div');
                dot.style.position = 'absolute';
                dot.style.left = '{x}px';
                dot.style.top = '{y}px';
                dot.style.width = '24px';
                dot.style.height = '24px';
                dot.style.backgroundColor = 'red';
                dot.style.color = 'white';
                dot.style.borderRadius = '50%';
                dot.style.zIndex = '999999';
                dot.style.pointerEvents = 'none';
                dot.style.border = '2px solid white';
                dot.style.display = 'flex';
                dot.style.alignItems = 'center';
                dot.style.justifyContent = 'center';
                dot.style.fontWeight = 'bold';
                dot.style.fontSize = '12px';
                dot.innerText = '{step}';
                document.body.appendChild(dot);
            """
            self.driver.execute_script(debug_script)
            
            # 2. CLICK AVANZADO (Pointer Events)
            click_script = f"""
                var target = document.elementFromPoint({x}, {y});
                if(target) {{
                    var opts = {{
                        bubbles: true, cancelable: true, view: window,
                        clientX: {x}, clientY: {y}, screenX: {x}, screenY: {y}
                    }};
                    target.dispatchEvent(new PointerEvent('pointerdown', opts));
                    target.dispatchEvent(new PointerEvent('mousedown', opts));
                    target.dispatchEvent(new PointerEvent('pointerup', opts));
                    target.dispatchEvent(new PointerEvent('mouseup', opts));
                    target.dispatchEvent(new PointerEvent('click', opts));
                }}
            """
            self.driver.execute_script(click_script)
            
            time.sleep(2) # Pausa generosa entre pasos
            return True
        except Exception as e:
            logger.error(f"❌ Falló click en {desc}: {e}")
            return False

    def _type_text(self, text):
        try:
            actions = ActionChains(self.driver)
            actions.send_keys(text)
            actions.perform()
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"❌ Error escribiendo: {e}")

    def login(self):
        self.setup_driver(headless=True) 
        
        try:
            logger.info("🚀 StoreBot: Iniciando secuencia de Login...")
            self.driver.get(self.BASE_URL)
            
            logger.info("⏳ Esperando carga (15s)...")
            time.sleep(15)

            # --- OPERACIÓN: MATAR PUBLICIDAD ---
            # Haremos 3 disparos estratégicos para asegurar el cierre
            
            # 2. Disparo a la X del Modal (Recalibrado)
            # Estaba en 465, 106 (letra 'd'). Subimos y vamos a la izquierda.
            self._click_at(415, 60, "Clic en X (Modal)", 2)

            # Pausa para ver si se fue
            time.sleep(2)
            
            # FOTO
            output_path = "/tmp/debug_ec_login.png"
            self.driver.save_screenshot(output_path)
            
            if os.path.exists(output_path):
                logger.info(f"📸 ÉXITO: Foto guardada en {output_path}")
            
            return True

        except Exception as e:
            logger.error(f"❌ Crash crítico: {e}")
            return False
        finally:
            self.close()

if __name__ == "__main__":
    bot = ECScraper()
    bot.login()
