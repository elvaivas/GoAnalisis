import os
from celery import Celery
from celery.schedules import crontab

# Leemos la variable del docker-compose
broker_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "goanalisis_tasks",
    broker=broker_url,
    backend=broker_url,
    # 👇👇 AQUÍ ESTÁ LA CLAVE: Debes agregar el nuevo archivo a esta lista 👇👇
    include=[
        "tasks.celery_tasks",
        "tasks.ops_tasks",  # <--- ¡ESTE FALTABA!
        "tasks.maintenance",  # <--- Este también para la tarea de las 4 AM
    ],
)


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Caracas",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
)

# --- PROGRAMACIÓN AUTOMÁTICA (CRONOGRAMA) ---
celery_app.conf.beat_schedule = {
    # 1. Monitor en Vivo (Cada minuto)
    # Busca pedidos nuevos en la página 1 y 2
    "monitor-every-minute": {
        "task": "tasks.celery_tasks.monitor_active_orders",
        "schedule": crontab(minute="*"),
    },
    # VIGILANTE DE HORARIOS (CADA 5 MINUTOS)
    "store-schedule-enforcer": {
        "task": "tasks.ops_tasks.enforce_schedules",
        "schedule": crontab(minute="*/5"),  # Cada 5 min (0, 5, 10, 15...)
    },
    # 2. Dron de Limpieza (Cada 30 minutos)
    # Revisa si quedaron pedidos sin mapa o sin finanzas y los arregla
    "drone-cleanup-every-30-mins": {
        "task": "tasks.celery_tasks.enrich_missing_data",
        "schedule": crontab(minute="*/30"),
    },
    # 3. VIGILANCIA DE CLIENTES (BARRIDO PROFUNDO)
    # Ejecuta a las 3:00 AM todos los días.
    "customer-surveillance-daily": {
        "task": "tasks.celery_tasks.sync_customer_database",
        "schedule": crontab(hour=3, minute=0),
        "kwargs": {"limit_pages": None},  # <--- AHORA ES INFINITO (FULL SYNC)
    },
    # 4. AUTOREPARACIÓN DE SISTEMA
    # 4:00 AM todos los días
    "nightly-healing": {
        "task": "tasks.maintenance.nightly_deep_clean",
        "schedule": crontab(hour=4, minute=0),
    },
}
