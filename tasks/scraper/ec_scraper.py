import logging
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from app.core.config import settings

# Configuración de log
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
        # Lienzo fijo 1366x768
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
        """Mantenemos la grilla para verificar visualmente los clicks"""
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
        """Disparo de precisión con trazador visual"""
        try:
            logger.info(f"🎯 Disparando a: {desc} -> ({x}, {y})")
            
            js_script = f"""
            var x = {x}; var y = {y};

            // Mira visual (Intangible)
            var cross = document.createElement('div');
            cross.style.position = 'absolute'; cross.style.left = (x - 10) + 'px'; cross.style.top = (y - 10) + 'px';
            cross.style.width = '20px'; cross.style.height = '20px'; cross.style.border = '2px solid lime'; 
            cross.style.borderRadius = '50%'; cross.style.zIndex = '10000000'; cross.style.pointerEvents = 'none';
            document.body.appendChild(cross);
            
            var point = document.createElement('div');
            point.style.position = 'absolute'; point.style.left = (x - 2) + 'px'; point.style.top = (y - 2) + 'px';
            point.style.width = '4px'; point.style.height = '4px'; point.style.backgroundColor = 'lime';
            point.style.zIndex = '10000001'; point.style.pointerEvents = 'none';
            document.body.appendChild(point);

            // Disparo Lógico
            var target = document.elementFromPoint(x, y);
            var info = "NADA";
            if(target) {{
                info = target.tagName + '.' + target.className;
                var opts = {{bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, screenX: x, screenY: y}};
                target.dispatchEvent(new MouseEvent('mousedown', opts));
                target.dispatchEvent(new MouseEvent('mouseup', opts));
                target.dispatchEvent(new MouseEvent('click', opts));
                try {{
                    target.dispatchEvent(new PointerEvent('pointerdown', {{...opts, pointerId: 1, pointerType: 'mouse'}}));
                    target.dispatchEvent(new PointerEvent('pointerup', {{...opts, pointerId: 1, pointerType: 'mouse'}}));
                }} catch(e) {{}}
                if (typeof target.click === 'function') target.click();
            }}
            return info;
            """
            element_hit = self.driver.execute_script(js_script)
            logger.info(f"💥 IMPACTO JS: [{element_hit}]")
            
            # Disparo Físico (ActionChains)
            try:
                actions = ActionChains(self.driver)
                actions.move_by_offset(x, y).click().perform()
                actions.move_by_offset(-x, -y).perform() 
            except:
                pass

            return True
        except Exception as e:
            logger.error(f"❌ Error en disparo: {e}")
            return False

    def login(self):
        self.setup_driver(headless=True) 
        
        try:
            logger.info("🚀 StoreBot: Iniciando Secuencia Completa...")
            self.driver.get(self.BASE_URL)
            logger.info("⏳ Esperando carga inicial (15s)...")
            time.sleep(10)

            self._inject_calibration_grid()
            
            # --- PASO 1: CERRAR PUBLICIDAD ---
            # TUS COORDENADAS (Intactas)
            logger.info("⚔️ Paso 1: Cerrando Modal Publicidad...")
            self._click_debug(501, 85, "Cerrar Modal X")
            time.sleep(3) 
            
            # --- PASO 2: ABRIR LOGIN ---
            # TUS COORDENADAS (Intactas)
            logger.info("🔑 Paso 2: Click en botón 'Ingresar'...")
            self._click_debug(1160, 78, "Botón Ingresar")
            time.sleep(3) 
            
            # --- PASO 3: ACEPTAR COOKIES ---
            # CAMBIO: Usamos 895, 645 para darle al botón verde "Sí, acepto".
            # Esto quita la barra negra que tapa el formulario.
            logger.info("🍪 Paso 3: Aceptando cookies para limpiar pantalla...")
            self._click_debug(895, 645, "Botón Aceptar Cookies")
            time.sleep(2) 

            # --- PASO 4: METODO USUARIO Y CLAVE ---
            # CAMBIO: Usamos 683, 630. 
            # 683 es el centro del modal. 630 es justo debajo del botón amarillo.
            logger.info("🔀 Paso 4: Cambiando a modo 'Usuario/Contraseña'...")
            self._click_debug(683, 630, "Link Cambiar Metodo")
            
            logger.info("⏳ Esperando 3s a que el formulario se actualice...")
            time.sleep(3)
            
            # --- FOTO FINAL ---
            output_path = "/tmp/debug_final.png"
            self.driver.save_screenshot(output_path)
            
            if os.path.exists(output_path):
                logger.info(f"📸 FOTO LISTA: {output_path}")
                logger.info("👉 Ahora deberías ver 4 puntos verdes y el formulario de correo abierto.")
            
            return True

        except Exception as e:
            logger.error(f"❌ Crash: {e}")
            return False
        finally:
            self.close()

if __name__ == "__main__":
    bot = ECScraper()
    bot.login()
