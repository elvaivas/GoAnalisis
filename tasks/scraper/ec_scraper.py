import logging
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys  # <--- IMPORTANTE: No borrar
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ECScraper:
    def __init__(self):
        self.BASE_URL = "https://ec.gopharma.com.ve/?from-splash=false"
        self.driver = None
        self.username = settings.EC_USER 
        self.password = settings.EC_PASSWORD

    def setup_driver(self, headless=True):
        options = Options()
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

    def _inject_calibration_grid(self):
        script = """
        (function() {
            if (document.getElementById('debug-grid')) return;
            var grid = document.createElement('div');
            grid.id = 'debug-grid';
            grid.style.position = 'fixed'; grid.style.top = '0'; grid.style.left = '0';
            grid.style.width = '100%'; grid.style.height = '100%';
            grid.style.pointerEvents = 'none'; grid.style.zIndex = '9999999';
            document.body.appendChild(grid);
            function createLine(x, y, isVert, labelNum) {
                var d = document.createElement('div');
                d.style.position = 'absolute';
                d.style.backgroundColor = isVert ? 'rgba(255,0,0,0.4)' : 'rgba(0,0,255,0.4)';
                if (isVert) { d.style.left = x + 'px'; d.style.top = '0'; d.style.bottom = '0'; d.style.width = '1px'; }
                else { d.style.top = y + 'px'; d.style.left = '0'; d.style.right = '0'; d.style.height = '1px'; }
                if (labelNum % 100 === 0) {
                    var t = document.createElement('span');
                    t.innerText = labelNum;
                    t.style.position = 'absolute';
                    t.style.fontSize = '10px'; t.style.fontWeight = 'bold';
                    t.style.color = isVert ? 'red' : 'blue';
                    t.style.backgroundColor = 'white';
                    if(isVert) t.style.top = '5px'; else t.style.left = '5px';
                    d.appendChild(t);
                    d.style.backgroundColor = isVert ? 'red' : 'blue';
                }
                grid.appendChild(d);
            }
            for (var i = 0; i < 1400; i+=50) createLine(i, 0, true, i);
            for (var j = 0; j < 800; j+=50) createLine(0, j, false, j);
        })();
        """
        self.driver.execute_script(script)

    def _click_debug(self, x, y, desc="Elemento"):
        try:
            logger.info(f"🎯 Disparando a: {desc} -> ({x}, {y})")
            
            # Dibujar marca
            js_mark = f"""
            var d = document.createElement('div');
            d.style.position='absolute'; d.style.left='{x-5}px'; d.style.top='{y-5}px';
            d.style.width='10px'; d.style.height='10px'; d.style.background='lime';
            d.style.borderRadius='50%'; d.style.zIndex='10000000'; d.style.pointerEvents='none';
            d.style.border='2px solid black';
            document.body.appendChild(d);
            """
            self.driver.execute_script(js_mark)

            js_script = f"""
            var target = document.elementFromPoint({x}, {y});
            var info = "NADA";
            if(target) {{
                info = target.tagName + '.' + target.className;
                var opts = {{bubbles: true, cancelable: true, view: window, clientX: {x}, clientY: {y}}};
                target.dispatchEvent(new MouseEvent('mousedown', opts));
                target.dispatchEvent(new MouseEvent('mouseup', opts));
                target.dispatchEvent(new MouseEvent('click', opts));
                try {{
                    target.dispatchEvent(new PointerEvent('pointerdown', {{...opts, pointerId: 1, pointerType: 'mouse'}}));
                    target.dispatchEvent(new PointerEvent('pointerup', {{...opts, pointerId: 1, pointerType: 'mouse'}}));
                }} catch(e) {{}}
            }}
            return info;
            """
            element_hit = self.driver.execute_script(js_script)
            logger.info(f"💥 IMPACTO JS: [{element_hit}]")
            
            try:
                actions = ActionChains(self.driver)
                actions.move_by_offset(x, y).click().perform()
                actions.move_by_offset(-x, -y).perform() 
            except:
                pass
            return True
        except Exception as e:
            logger.error(f"❌ Error disparo: {e}")
            return False

    # --- ESTA ES LA FUNCIÓN QUE TE FALTABA ---
    def _type_text_at_coords(self, text):
        """Escribe texto limpiando el campo primero (Ctrl+A -> Del)"""
        try:
            actions = ActionChains(self.driver)
            # Limpiar campo
            actions.send_keys(Keys.CONTROL + "a")
            actions.send_keys(Keys.DELETE)
            # Escribir
            actions.send_keys(text)
            actions.perform()
            logger.info(f"⌨️ Texto escrito: {text}")
            return True
        except Exception as e:
            logger.error(f"❌ Error escribiendo: {e}")
            return False
    # ------------------------------------------

    def login(self):
        self.setup_driver(headless=True) 
        
        try:
            logger.info("🚀 StoreBot: Iniciando Secuencia Completa...")
            self.driver.get(self.BASE_URL)
            logger.info("⏳ Esperando carga (10s)...")
            time.sleep(10)

            self._inject_calibration_grid()
            
            # 1. Cerrar Publicidad
            self._click_debug(501, 85, "1. Cerrar Modal X")
            time.sleep(2)
            
            # 2. Botón Ingresar
            self._click_debug(1160, 78, "2. Botón Ingresar")
            time.sleep(2)
            
            # 3. Aceptar Cookies
            self._click_debug(1200, 600, "3. Aceptar Cookies")
            time.sleep(2)
            
            # 4. Cambiar a Contraseña
            self._click_debug(683, 627, "4. Cambiar a Contraseña")
            time.sleep(2)

            # 5. Campo Usuario (Centrado en la caja de texto)
            logger.info("✍️ Paso 5: Escribiendo Usuario...")
            self._click_debug(600, 250, "Input Usuario")
            time.sleep(0.5)
            self._type_text_at_coords(self.username)
            time.sleep(1)

            # 6. Campo Contraseña (Centrado en la caja de texto)
            logger.info("✍️ Paso 6: Escribiendo Contraseña...")
            self._click_debug(600, 350, "Input Password")
            time.sleep(0.5)
            self._type_text_at_coords(self.password)
            time.sleep(1)

            # 7. Botón Recuerdame
            logger.info("👆 Paso 7: Click Ingresar...")
            self._click_debug(490, 400, "Boton recuerdame")
            time.sleep(1)            
            
            # 8. Botón INGRESAR (Alineado al botón verde)
            logger.info("👆 Paso 7: Click Ingresar...")
            self._click_debug(450, 500, "Boton Ingresar (Verde)")
            
            logger.info("⏳ Esperando 5s login...")
            time.sleep(3)
            
            output_path = "/tmp/debug_final.png"
            self.driver.save_screenshot(output_path)
            
            if os.path.exists(output_path):
                logger.info(f"📸 FOTO LISTA: {output_path}")
            
            return True

        except Exception as e:
            logger.error(f"❌ Crash: {e}")
            return False
        finally:
            self.close()

if __name__ == "__main__":
    bot = ECScraper()
    bot.login()
