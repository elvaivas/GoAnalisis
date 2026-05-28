import os
import sys
import json
import logging

# Aseguramos que Python reconozca los módulos
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tasks.scraper.drone_scraper import DroneScraper

logging.basicConfig(level=logging.INFO)


def run_debug():
    bot = DroneScraper()
    order_id = (
        "109193"  # Puedes cambiar este número por cualquier otro ID que quieras probar
    )

    print(f"\n🚀 Iniciando Debug del Dron para el pedido #{order_id}...")

    # Ejecutamos la extracción
    data = bot.scrape_detail(order_id, mode="full")

    print("\n" + "=" * 60)
    print("🎯 RESULTADO EN BRUTO DE LA EXTRACCIÓN (JSON):")
    print("=" * 60)

    # Imprimimos el diccionario extraído de forma bonita
    if data:
        print(json.dumps(data, indent=4, ensure_ascii=False))
    else:
        print("❌ El dron devolvió un diccionario vacío (None).")

    print("=" * 60)

    # Tomamos una foto de lo que vio el bot por si acaso
    if bot.driver:
        bot.driver.save_screenshot("/tmp/debug_drone_vision.png")
        print(
            "📸 Captura de pantalla del navegador guardada en /tmp/debug_drone_vision.png"
        )

    bot.close_driver()


if __name__ == "__main__":
    run_debug()
