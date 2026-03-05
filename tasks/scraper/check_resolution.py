import logging
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_screen():
    options = Options()
    # Usamos la configuración actual para ver qué está pasando realmente
    options.add_argument("--window-size=1366,768")
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")

    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    # Escudo SRE: Timeout de 30s contra desconexiones
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)

    try:
        logger.info("📏 Midiendo resolución real del Servidor...")
        driver.get("https://ec.gopharma.com.ve/?from-splash=false")
        time.sleep(5)

        # MAGIA JAVASCRIPT: Obtener el tamaño útil real (Viewport)
        # Esto es lo que realmente importa para los clics, no el tamaño de la ventana externa.
        metrics = driver.execute_script(
            """
            return {
                outerWidth: window.outerWidth,
                outerHeight: window.outerHeight,
                innerWidth: window.innerWidth,   
                innerHeight: window.innerHeight,
                dpr: window.devicePixelRatio
            };
        """
        )

        print("\n" + "=" * 40)
        print(f"🖥️  DATOS REALES DEL SERVIDOR:")
        print(
            f"   • Ventana Externa: {metrics['outerWidth']} x {metrics['outerHeight']}"
        )
        print(
            f"   • LIENZO ÚTIL (Viewport): {metrics['innerWidth']} x {metrics['innerHeight']}"
        )
        print(f"   • Pixel Ratio: {metrics['dpr']}")
        print("=" * 40 + "\n")

    finally:
        driver.quit()


if __name__ == "__main__":
    check_screen()
