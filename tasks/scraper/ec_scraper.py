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
        Hace click, dibuja una MIRA VERDE donde hizo click e identifica qué tocó.
        """
        try:
            logger.info(f"🎯 INTENTO: Click en {desc} -> Coordenadas ({x}, {y})")
            
            js_script = f"""
            // 1. Dibujar Mira de Francotirador (Crosshair)
            var cross = document.createElement('div');
            cross.style.position = 'absolute';
            cross.style.left = ({x} - 10) + 'px';
            cross.style.top = ({y} - 10) + 'px';
            cross.style.width = '20px'; cross.style.height = '20px';
            cross.style.border = '2px solid lime'; // Verde brillante
            cross.style.borderRadius = '50%';
            cross.style.zIndex = '10000000';
            cross.style.pointerEvents = 'none';
            
            var point = document.createElement('div');
            point.style.position = 'absolute';
            point.style.left = ({x} - 2) + 'px'; point.style.top = ({y} - 2) + 'px';
            point.style.width = '4px'; point.style.height = '4px';
            point.style.backgroundColor = 'lime';
            point.style.zIndex = '10000001';
            
            document.body.appendChild(cross);
            document.body.appendChild(point);

            // 2. Ejecutar Click y Detectar Elemento
            var target = document.elementFromPoint({x}, {y});
            var info = "NADA (null)";
            if(target) {{
                // Obtener info útil para el programador
                var tag = target.tagName;
                var cls = target.className;
                var src = target.src ? target.src.substring(0, 30) + '...' : 'sin-src';
                info = tag + " | Class: " + cls + " | Src: " + src;

                // Forzar eventos de click
                var opts = {{bubbles: true, cancelable: true, view: window, clientX: {x}, clientY: {y}}};
                target.dispatchEvent(new MouseEvent('mousedown', opts));
                target.dispatchEvent(new MouseEvent('mouseup', opts));
                target.dispatchEvent(new MouseEvent('click', opts));
            }}
            return info;
            """
            
            # Ejecutamos y obtenemos qué tocamos
            element_hit = self.driver.execute_script(js_script)
            
            logger.info(f"💥 RESULTADO IMPACTO: El click cayó sobre: [{element_hit}]")
            
            # Análisis rápido para log
            if "IMG" in element_hit:
                logger.warning("⚠️ ALERTA: Le diste a una IMAGEN. Probablemente abriste la publicidad en vez de cerrarla.")
            elif "button" in element_hit.lower() or "close" in element_hit.lower() or "modal" in element_hit.lower():
                logger.info("✅ PINTA BIEN: Parece que le diste a un botón o elemento de cierre.")
            else:
                logger.info("ℹ️ INFO: Le diste a un elemento genérico. Revisa la foto.")

            time.sleep(2)
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en click: {e}")
            return False

    def login(self):
        self.setup_driver(headless=True) 
        
        try:
            logger.info("🚀 StoreBot: Iniciando modo calibración...")
            self.driver.get(self.BASE_URL)
            
            logger.info("⏳ Esperando carga inicial (15s)...")
            time.sleep(15)

            # 1. Poner la Grilla
            self._inject_calibration_grid()
            
            # 2. INTENTO DE CLICK
            # Coordenada actual a probar: 480, 72
            # Sugerencia: Si 480 abre la imagen, intenta subir Y o mover X.
            # Prueba cambiar a 495, 65 si esta falla.
            TARGET_X = 480
            TARGET_Y = 72
            
            self._click_debug(TARGET_X, TARGET_Y, "Boton Cierre")

            # Esperar reacción visual
            time.sleep(3)
            
            # 3. FOTO DE DIAGNÓSTICO
            output_path = "/tmp/debug_calibracion.png"
            self.driver.save_screenshot(output_path)
            
            if os.path.exists(output_path):
                logger.info(f"📸 FOTO GUARDADA: {output_path}")
                logger.info("👉 Abre la foto. Busca la MIRA VERDE (tu click) y compárala con las líneas ROJAS/AZULES.")
            
            return True

        except Exception as e:
            logger.error(f"❌ Crash: {e}")
            return False
        finally:
            self.close()

if __name__ == "__main__":
    bot = ECScraper()
    bot.login()
