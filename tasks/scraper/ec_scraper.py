import logging
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
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
        options.add_argument("--window-size=1366,768")
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        service = Service()
        self.driver = webdriver.Chrome(service=service, options=options)

        # JAULA DE CRISTAL
        self.driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": 1366,
                "height": 768,
                "deviceScaleFactor": 1,
                "mobile": False,
                "fitWindow": True,
            },
        )
        logger.info("🔒 Resolución forzada a: 1366x768")

    def close(self):
        if self.driver:
            self.driver.quit()

    def set_gps_location(self, lat, lng):
        """Teletransporta el navegador"""
        logger.info(f"🌍 GPS Spoofing: {lat}, {lng}")
        self.driver.execute_cdp_cmd(
            "Emulation.setGeolocationOverride",
            {"latitude": lat, "longitude": lng, "accuracy": 100},
        )
        time.sleep(1)

    def _inject_calibration_grid(self):
        script = """
        (function() {
            if (document.getElementById('debug-grid')) return;
            var grid = document.createElement('div');
            grid.id = 'debug-grid';
            grid.style.pointerEvents = 'none'; grid.style.zIndex = '9999999';
            grid.style.position = 'fixed'; grid.style.top = '0'; grid.style.left = '0';
            document.body.appendChild(grid);
            function line(x,y,v){
                var d=document.createElement('div'); d.style.position='absolute'; d.style.background=v?'rgba(255,0,0,0.5)':'rgba(0,0,255,0.5)';
                if(v){d.style.left=x+'px';d.style.top='0';d.style.width='1px';d.style.height='768px';}
                else{d.style.top=y+'px';d.style.left='0';d.style.height='1px';d.style.width='1366px';}
                grid.appendChild(d);
            }
            for(var i=0;i<=1400;i+=100) line(i,0,1);
            for(var j=0;j<=800;j+=100) line(0,j,0);
        })();
        """
        try:
            self.driver.execute_script(script)
        except:
            pass

    def _super_click(self, x, y, desc="Elemento", step=0):
        try:
            logger.info(f"📍 [{step}] Click: {desc} ({x}, {y})")

            # Marcador Rojo
            js_mark = f"""
            var d = document.createElement('div'); d.style.position='absolute'; d.style.left='{x}px'; d.style.top='{y}px';
            d.style.width='15px'; d.style.height='15px'; d.style.background='red'; d.style.borderRadius='50%'; 
            d.style.zIndex='9999999'; d.innerText='{step}'; d.style.color='white'; d.style.fontSize='10px'; d.style.textAlign='center';
            document.body.appendChild(d);
            """
            self.driver.execute_script(js_mark)

            # 1. Disparo JS (Pointer Events)
            js_click = f"""
            var target = document.elementFromPoint({x}, {y}) || document.body;
            var opts = {{bubbles:true, cancelable:true, view:window, clientX:{x}, clientY:{y}, pointerId:1, pointerType:'mouse', button:0, buttons:1}};
            target.dispatchEvent(new PointerEvent('pointerdown', opts));
            target.dispatchEvent(new MouseEvent('mousedown', opts));
            setTimeout(()=>{{
                target.dispatchEvent(new PointerEvent('pointerup', opts));
                target.dispatchEvent(new MouseEvent('mouseup', opts));
                target.dispatchEvent(new MouseEvent('click', opts));
            }}, 100);
            """
            self.driver.execute_script(js_click)

            # 2. Respaldo ActionChains
            try:
                actions = ActionChains(self.driver)
                actions.move_by_offset(x, y).click().perform()
                actions.move_by_offset(-x, -y).perform()
            except:
                pass

            time.sleep(1.5)
            return True
        except Exception as e:
            logger.error(f"❌ Error click {step}: {e}")
            return False

    def _type_text_at_coords(self, text, x, y, step=0, submit=False):
        """Escribe texto. Si submit=True, presiona ENTER."""
        try:
            logger.info(f"⌨️ [{step}] Escribiendo: {text}")
            self._super_click(x, y, "Foco Texto", step)
            time.sleep(0.5)

            actions = ActionChains(self.driver)
            actions.send_keys(Keys.CONTROL + "a")
            actions.send_keys(Keys.DELETE)
            actions.send_keys(text)

            if submit:
                logger.info("🚀 Enviando ENTER...")
                actions.send_keys(Keys.ENTER)

            actions.perform()
            time.sleep(1.0)
            return True
        except Exception as e:
            logger.error(f"❌ Error escribiendo: {e}")
            return False

    def login_and_search(self):
        self.setup_driver(headless=True)  # Siempre headless en server

        try:
            logger.info("🚀 StoreBot: Iniciando Secuencia...")
            self.driver.get(self.BASE_URL)
            time.sleep(15)  # Espera carga inicial

            self._inject_calibration_grid()

            # --- 1. LOGIN ---
            self._super_click(455, 90, "Cerrar Publicidad", 1)
            time.sleep(2)
            self._super_click(1210, 730, "Cookies", 2)
            time.sleep(1)
            self._super_click(455, 90, "Cerrar Publicidad (Intento 2)", 3)
            time.sleep(1)
            self._super_click(1160, 58, "Botón Login", 4)
            time.sleep(3)
            self._super_click(680, 665, "Switch Password", 5)
            time.sleep(2)

            self._type_text_at_coords(self.username, 683, 300, 6)
            self._type_text_at_coords(self.password, 683, 400, 7)

            self._super_click(550, 500, "Ingresar Verde", 8)

            logger.info("⏳ Esperando Login (8s)...")
            time.sleep(8)

            # --- 2. UBICACIÓN (GPS) ---
            # Inyectamos coordenadas de una Farmacia (Ej: Las Mercedes)
            # Esto debe hacerse ANTES de darle a "Estoy Aquí"
            self.set_gps_location(10.4806, -66.9036)

            self._super_click(455, 10, "Abrir Selector Dirección", 9)
            time.sleep(2)

            # Click en la Mira (Usar mi ubicación)
            self._super_click(683, 400, "Boton 'Estoy Aquí' (GPS)", 10)
            time.sleep(5)  # Esperar a que cargue el inventario de la tienda

            # --- 3. BÚSQUEDA ---
            self._super_click(960, 60, "Lupa Buscar", 11)
            time.sleep(2)

            # Escribir producto (Ej: Atamel) + ENTER
            PRODUCTO_PRUEBA = "Atamel"  # Cambia esto si quieres probar otro
            self._type_text_at_coords(PRODUCTO_PRUEBA, 160, 160, 12, submit=True)

            logger.info("⏳ Esperando resultados de búsqueda (5s)...")
            time.sleep(5)

            # --- 4. SELECCIÓN ---
            # Clic en el primer resultado (Coordenada aproximada de la lista)
            self._super_click(150, 250, "Primer Producto", 13)
            time.sleep(5)

            # FOTO FINAL
            output_path = "/tmp/debug_ec_search.png"
            self.driver.save_screenshot(output_path)
            if os.path.exists(output_path):
                logger.info(f"📸 FOTO FINAL: {output_path}")

            return True

        except Exception as e:
            logger.error(f"❌ Crash: {e}")
            return False
        finally:
            self.close()


if __name__ == "__main__":
    bot = ECScraper()
    bot.login_and_search()
