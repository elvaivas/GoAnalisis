import logging
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
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

        # Tamaño de ventana base (contenedor)
        options.add_argument("--window-size=1366,768")

        if headless:
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        service = Service()
        self.driver = webdriver.Chrome(service=service, options=options)

        # --- MAGIA DE CALIBRACIÓN: FORZAR RESOLUCIÓN INTERNA ---
        # Esto obliga al navegador a comportarse como una pantalla de 1366x768
        # sin importar si tiene bordes, barras o si está en modo headless.
        width = 1366
        height = 768

        self.driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
                "fitWindow": True,  # Ajusta el contenido a la ventana visible
            },
        )

        # Verificar tamaño real (para debug)
        size = self.driver.execute_script(
            "return [window.innerWidth, window.innerHeight];"
        )
        logger.info(f"📏 Viewport Calibrado: {size[0]}x{size[1]}")

    def close(self):
        if self.driver:
            self.driver.quit()

    def _inject_calibration_grid(self):
        """Dibuja cuadrícula para verificar alineación en la foto"""
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
        try:
            self.driver.execute_script(script)
        except:
            pass

    def _click_debug(self, x, y, desc="Elemento"):
        try:
            logger.info(f"🎯 Disparando a: {desc} -> ({x}, {y})")

            # 1. Marca visual (Punto verde)
            js_mark = f"""
            var d = document.createElement('div');
            d.style.position='absolute'; d.style.left='{x-5}px'; d.style.top='{y-5}px';
            d.style.width='10px'; d.style.height='10px'; d.style.background='lime';
            d.style.borderRadius='50%'; d.style.zIndex='10000000'; d.style.pointerEvents='none';
            d.style.border='2px solid black';
            document.body.appendChild(d);
            """
            self.driver.execute_script(js_mark)

            # 2. Click JS Avanzado (Pointer Events)
            js_script = f"""
            var target = document.elementFromPoint({x}, {y});
            if(target) {{
                var opts = {{bubbles: true, cancelable: true, view: window, clientX: {x}, clientY: {y}}};
                target.dispatchEvent(new MouseEvent('mousedown', opts));
                target.dispatchEvent(new MouseEvent('mouseup', opts));
                target.dispatchEvent(new MouseEvent('click', opts));
                try {{
                    target.dispatchEvent(new PointerEvent('pointerdown', {{...opts, pointerId: 1, pointerType: 'mouse'}}));
                    target.dispatchEvent(new PointerEvent('pointerup', {{...opts, pointerId: 1, pointerType: 'mouse'}}));
                }} catch(e) {{}}
            }}
            """
            self.driver.execute_script(js_script)

            # 3. Respaldo: Click Físico (ActionChains)
            # Esto ayuda a mover el foco real del navegador si JS falla
            try:
                actions = ActionChains(self.driver)
                body = self.driver.find_element(By.TAG_NAME, "body")
                actions.move_to_element_with_offset(body, 0, 0)
                actions.move_by_offset(x, y).click().perform()
            except:
                pass

            return True
        except Exception as e:
            logger.error(f"❌ Error disparo: {e}")
            return False

    def _type_text_at_coords(self, text, x, y, submit=False):
        """
        Combina Movimiento + Click + Escritura.
        Si submit=True, presiona ENTER al final.
        """
        try:
            logger.info(f"⌨️ Escribiendo en ({x},{y})...")

            # 1. Mover y Click Físico para asegurar foco
            body = self.driver.find_element(By.TAG_NAME, "body")
            actions = ActionChains(self.driver)
            actions.move_to_element_with_offset(body, 0, 0)
            actions.move_by_offset(x, y)
            actions.click()
            actions.perform()

            time.sleep(0.5)

            # 2. Limpiar, Escribir y (Opcional) Enter
            actions = ActionChains(self.driver)  # Reiniciamos actions
            actions.send_keys(Keys.CONTROL + "a")
            actions.send_keys(Keys.DELETE)
            actions.send_keys(text)

            if submit:
                logger.info("🚀 Enviando tecla ENTER...")
                actions.send_keys(Keys.ENTER)

            actions.perform()

            return True
        except Exception as e:
            logger.error(f"❌ Error escribiendo: {e}")
            return False

    def login(self):
        self.setup_driver(headless=True)

        try:
            logger.info("🚀 StoreBot: Iniciando Secuencia Login (Server Scale)...")
            self.driver.get(self.BASE_URL)
            logger.info("⏳ Esperando carga (15s)...")
            time.sleep(15)

            self._inject_calibration_grid()

            # 1. Cerrar Publicidad
            self._click_debug(501, 85, "1. Cerrar Modal X")
            time.sleep(2)

            # 2. Botón Ingresar
            self._click_debug(1160, 78, "2. Botón Ingresar")
            time.sleep(2)

            # 3. Aceptar Cookies (Si sale)
            self._click_debug(1200, 600, "3. Aceptar Cookies")
            time.sleep(1)

            # 4. Cambiar a Contraseña
            self._click_debug(683, 627, "4. Cambiar a Contraseña")
            time.sleep(2)

            # 5. Campo Usuario (Con función integrada)
            # Usamos _type_text_at_coords que incluye el click y movimiento
            self._type_text_at_coords(self.username, 600, 250)
            time.sleep(1)

            # 6. Campo Usuario
            # Usamos coordenadas ajustadas a tu última foto
            # Nota: Si funcionaron las anteriores, usa esas. Aquí pongo las centradas del último intento.
            self._type_text_at_coords(self.username, 683, 395)
            time.sleep(1)

            # 7. Campo Contraseña + ENTER
            # Enviamos submit=True para que lance el Enter automático
            self._type_text_at_coords(self.password, 683, 490, submit=True)

            # No hacemos click en el botón verde inmediatamente, esperamos a ver si el Enter funcionó
            logger.info("⏳ Esperando reacción al ENTER (5s)...")
            time.sleep(5)

            # 8. Botón INGRESAR (Solo por seguridad/respaldo si el Enter falla)
            # Si ya entró, este click no hará daño o fallará silenciosamente
            logger.info("👆 Click de respaldo en botón Ingresar...")
            self._click_debug(683, 580, "Boton Ingresar")

            logger.info("⏳ Esperando carga final del Dashboard (10s)...")
            time.sleep(10)

            # FOTO DE CONFIRMACIÓN
            output_path = "/tmp/debug_ec_login.png"
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
    # DENTRO DE DOCKER SIEMPRE DEBE SER TRUE
    bot.login()
