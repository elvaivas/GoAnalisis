import logging
import time
from tasks.celery_tasks import sync_customer_database, sync_store_commissions
from tasks.maintenance import nightly_deep_clean

# Configuración de logs para ver qué pasa en la consola
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_manual_protocols():
    print("\n⚡ INICIANDO PROTOCOLOS DE MANTENIMIENTO MANUAL (MODO LOCAL) ⚡")
    print("===============================================================")

    # --- 1. SINCRONIZACIÓN DE CLIENTES ---
    print("\n👥 [1/3] Iniciando Sincronización de Clientes...")
    print("    (Esto escanea la lista de usuarios para obtener fechas reales y teléfonos)")
    try:
        # Llamamos a la función directamente (síncrona), no a través de Celery (.delay)
        # limit_pages=10 para que sea rápido en la prueba (aprox 200 usuarios recientes)
        # Si quieres TODOS, quita el limit_pages (tardará bastante)
        result = sync_customer_database(limit_pages=20) 
        print(f"    ✅ Resultado: {result}")
    except Exception as e:
        print(f"    ❌ Error en Clientes: {e}")

    # --- 2. COMISIONES DE TIENDAS (Rápido) ---
    print("\n🏪 [2/3] Sincronizando Comisiones de Tiendas...")
    try:
        result = sync_store_commissions()
        print(f"    ✅ Resultado: {result}")
    except Exception as e:
        print(f"    ❌ Error en Tiendas: {e}")

    # --- 3. MANTENIMIENTO NOCTURNO (AUTOCURACIÓN) ---
    print("\n🌙 [3/3] Ejecutando Protocolo 'Nightly Deep Clean'...")
    print("    (Buscando zombies, falsos deliveries y montos cero en las últimas 48h)")
    try:
        result = nightly_deep_clean()
        print(f"    ✅ Resultado: {result}")
    except Exception as e:
        print(f"    ❌ Error en Mantenimiento: {e}")

    print("\n===============================================================")
    print("✨ ¡LISTO! Tu entorno local está sincronizado y auditado.")

if __name__ == "__main__":
    run_manual_protocols()