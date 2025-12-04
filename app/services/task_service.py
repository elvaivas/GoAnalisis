import os
import logging
import redis # Necesario para el force
from celery import Celery

logger = logging.getLogger(__name__)

def trigger_backfill():
    """
    Envía Backfill usando Import Bypass (Celery Sender).
    """
    broker_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    simple_app = Celery("sender", broker=broker_url)
    
    task_name = "tasks.celery_tasks.backfill_historical_data"
    task = simple_app.send_task(task_name)
    
    logger.info(f"🚀 Tarea '{task_name}' enviada. ID: {task.id}")
    return task.id

def trigger_drone(force: bool = False):
    """
    Lanza el Drone con opción de Rompe-Candados.
    Usa Import Bypass para evitar errores de ruta.
    """
    broker_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    # 1. GESTIÓN DE CANDADOS (FORCE)
    if force:
        try:
            r = redis.Redis.from_url(broker_url)
            lock_key = "celery_lock_drone_enrichment"
            deleted = r.delete(lock_key)
            if deleted:
                logger.warning(f"🔓 FORCE: Candado '{lock_key}' eliminado manualmente.")
            else:
                logger.info(f"ℹ️ FORCE: No había candado.")
        except Exception as e:
            logger.error(f"❌ Error borrando candado: {e}")

    # 2. LANZAMIENTO (Usando Celery Sender "Light")
    simple_app = Celery("sender", broker=broker_url)
    
    task_name = "tasks.celery_tasks.enrich_missing_data"
    task = simple_app.send_task(task_name)
    
    logger.info(f"🚁 Drone lanzado (Force={force}). ID: {task.id}")
    return task.id
