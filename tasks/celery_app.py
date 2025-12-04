import os
from celery import Celery
from celery.schedules import crontab # <--- Importar crontab

broker_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "goanalisis_tasks", 
    broker=broker_url, 
    backend=broker_url,
    include=['tasks.celery_tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Caracas',
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

# --- PROGRAMACIÓN AUTOMÁTICA (BEAT) ---
celery_app.conf.beat_schedule = {
    # 1. Monitor en Vivo: AHORA CORRE CADA MINUTO
    'monitor-every-minute': {
        'task': 'tasks.celery_tasks.monitor_active_orders',
        'schedule': crontab(minute='*'), # El asterisco significa "cada minuto"
    },
    # 2. Dron de Limpieza: Sigue cada 30 min
    'drone-cleanup-every-30-mins': {
        'task': 'tasks.celery_tasks.enrich_missing_data',
        'schedule': crontab(minute='*/30'),
    },
}
