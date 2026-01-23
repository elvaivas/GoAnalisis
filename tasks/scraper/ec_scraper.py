import logging
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from app.core.config import settings

# Configuración de log para ver claramente los mensajes
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ECScraper:
    def __init__(self):
        self.BASE_URL = "https://ec.gopharma.com.ve/?from-splash=false"
        self.driver = None
        self.username = settings.EC_USER
        self.password = settings.EC_PASSWORD

    def setup_driver(self, headless=True):
        options = Options()
        # Mantenemos la resolución fija para que las coordenadas no cambien
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
        """
        Dibuja una cuadrícula superpuesta para medir coordenadas exactas.
        Rojo = Eje X (Verticales), Azul = Eje Y (Horizontales).
        """
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
                
                if (isVert) { // Línea Vertical (X)
                    d.style.left = x + 'px'; d.style.top = '0'; d.style.bottom = '0'; d.style.width = '1px';
                } else { // Línea Horizontal (Y)
                    d.style.top = y + 'px'; d.style.left = '0'; d.style.right = '0'; d.style.height = '1px';
                }
                
                // Texto de coordenada
                if (labelNum % 100 === 0) {
                    var t = document.createElement('span');
                    t.innerText = labelNum;
                    t.style.position = 'absolute';
                    t.style.fontSize = '10px'; t.style.fontWeight = 'bold';
                    t.style.color = isVert ? 'red' : 'blue';
                    t.style.backgroundColor = 'white';
                    if(isVert) t.style.top = '5px'; else t.style.left = '5px';
                    d.appendChild(t);
                    d.style.backgroundColor = isVert ? 'red' : 'blue'; // Líneas maestras más oscuras
                }
                grid.appendChild(d);
            }

            // Dibujar cada 50px
            for (var i = 0; i < 1400; i+=50) createLine(i, 0, true, i); // X
            for (var j = 0; j < 800; j+=50) createLine(0, j, false, j); // Y
        })();
        """
        self.driver.execute_script(script)
        logger.info("📏 CALIBRACIÓN: Grilla inyectada en pantalla.")

    def _click_debug(self, x, y, desc="Elemento"):
        """
        Versión corregida: El punto verde ahora es intangible (pointer-events: none)
        para asegurar que el click le dé al botón real.
        """
        try:
            logger.info(f"🎯 INTENTO: Click en {desc} -> Coordenadas ({x}, {y})")
            
            js_script = f"""
            var x = {x};
            var y = {y};

            // 1. Dibujar Mira (Círculo) - INTANGIBLE
            var cross = document.createElement('div');
            cross.style.position = 'absolute';
            cross.style.left = (x - 10) + 'px';
            cross.style.top = (y - 10) + 'px';
            cross.style.width = '20px'; cross.style.height = '20px';
            cross.style.border = '2px solid lime';
            cross.style.borderRadius = '50%';
            cross.style.zIndex = '10000000';
            cross.style.pointerEvents = 'none'; // <--- CLAVE: El click atraviesa esto
            document.body.appendChild(cross);
            
            // 2. Dibujar Punto Central - INTANGIBLE
            var point = document.createElement('div');
            point.style.position = 'absolute';
            point.style.left = (x - 2) + 'px'; point.style.top = (y - 2) + 'px';
            point.style.width = '4px'; point.style.height = '4px';
            point.style.backgroundColor = 'lime';
            point.style.zIndex = '10000001';
            point.style.pointerEvents = 'none'; // <--- CLAVE: El click atraviesa esto también
            document.body.appendChild(point);

            // 3. Ejecutar Click Real
            // Obtenemos el elemento que está DEBAJO de nuestros dibujos
            var target = document.elementFromPoint(x, y);
            var info = "NADA";
            
            if(target) {{
                info = target.tagName + '.' + target.className;
                
                // Disparamos una ráfaga de eventos para asegurar compatibilidad
                var opts = {{bubbles: true, cancelable: true, view: window, clientX: x, clientY: y}};
                target.dispatchEvent(new MouseEvent('mousedown', opts));
                target.dispatchEvent(new MouseEvent('mouseup', opts));
                target.dispatchEvent(new MouseEvent('click', opts));
                
                // INTENTO EXTRA: Si es un elemento clicable nativo
                if (typeof target.click === 'function') {{
                    target.click();
                }}
            }}
            return info;
            """
            
            element_hit = self.driver.execute_script(js_script)
            logger.info(f"💥 IMPACTO: El click atravesó la mira y golpeó: [{element_hit}]")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en click: {e}")
            return False

    def login(self):
        self.setup_driver(headless=True) 
        
        try:
            logger.info("🚀 StoreBot: Ejecutando cierre de publicidad...")
            self.driver.get(self.BASE_URL)
            
            logger.info("⏳ Esperando carga (15s)...")
            time.sleep(15)

            # Inyectamos grilla solo para tener referencia visual en la foto final
            self._inject_calibration_grid()
            
            # 🎯 TUS COORDENADAS PERFECTAS
            TARGET_X = 504
            TARGET_Y = 85
            
            # Primer intento
            self._click_debug(TARGET_X, TARGET_Y, "Boton X (Intento 1)")
            
            # Pequeña pausa y segundo intento (Doble Tap de seguridad)
            time.sleep(0.5)
            self._click_debug(TARGET_X, TARGET_Y, "Boton X (Intento 2)")

            logger.info("⏳ Esperando 5 segundos a que la animación termine...")
            time.sleep(5)
            
            # FOTO FINAL
            output_path = "/tmp/debug_final.png"
            self.driver.save_screenshot(output_path)
            
            if os.path.exists(output_path):
                logger.info(f"📸 RESULTADO: {output_path}")
            
            return True

        except Exception as e:
            logger.error(f"❌ Crash: {e}")
            return False
        finally:
            self.close()

if __name__ == "__main__":
    bot = ECScraper()
    bot.login()
