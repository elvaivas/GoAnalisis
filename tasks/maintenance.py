import logging
import redis
import time
from datetime import datetime, timedelta
from celery import shared_task
from sqlalchemy import text, asc

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.base import Order, OrderStatusLog
from tasks.scraper.order_scraper import OrderScraper
from tasks.scraper.drone_scraper import DroneScraper
from tasks.celery_tasks import process_drone_data

# Configuración de Logging
logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(settings.REDIS_URL)


@shared_task(bind=True, name="tasks.maintenance.nightly_deep_clean")
def nightly_deep_clean(self):
    """
    PROTOCOL DE MANTENIMIENTO NOCTURNO (4:00 AM)
    1. Rompe candados de Redis olvidados.
    2. Ejecuta auditoría profunda de las últimas 48h.
    3. Saneamiento Quirúrgico de Logs (Elimina rebotes y basura).
    """
    logger.info("🏥 INICIANDO PROTOCOLO DE AUTOCURACIÓN NOCTURNA...")

    # --- FASE 1: ROMPER CANDADOS VIEJOS ---
    try:
        keys = redis_client.keys("celery_lock_*")
        if keys:
            logger.info(f"🔓 Liberando {len(keys)} candados de tareas trabadas...")
            redis_client.delete(*keys)
    except Exception as e:
        logger.error(f"Error limpiando Redis: {e}")

    # --- FASE 2: AUDITORÍA DE DATOS (ÚLTIMAS 48H) ---
    try:
        logger.info("🕵️‍♂️ Iniciando Auditoría de Integridad (48 Horas)...")
        db = SessionLocal()
        ls = OrderScraper()
        drone = DroneScraper()

        if ls.login():
            items = ls.get_historical_ids(max_pages=20)
            ls.close_driver()

            if drone.login():
                count = 0
                for item in items:
                    eid = item["id"]
                    local_order = (
                        db.query(Order).filter(Order.external_id == eid).first()
                    )

                    needs_repair = False
                    if not local_order:
                        needs_repair = True
                    elif local_order.current_status not in ["delivered", "canceled"]:
                        needs_repair = True
                    elif local_order.total_amount == 0:
                        needs_repair = True
                    elif (
                        local_order.current_status == "delivered"
                        and local_order.order_type == "Delivery"
                        and local_order.driver_id is None
                    ):
                        needs_repair = True
                        logger.info(
                            f"🧐 Detectada Incoherencia en #{eid}: Delivery sin Chofer. Forzando corrección..."
                        )

                    if needs_repair:
                        count += 1
                        logger.info(f"🚑 Reparando Pedido #{eid}...")
                        try:
                            data = drone.scrape_detail(eid, mode="full")
                            if not data.get("duration_text"):
                                data["duration_text"] = item.get("duration", "")
                            process_drone_data(db, data)
                        except Exception as scrape_err:
                            logger.error(f"Fallo reparando {eid}: {scrape_err}")

                drone.close_driver()
                logger.info(f"✅ Auditoría finalizada. {count} pedidos corregidos.")
            else:
                logger.error("❌ Dron no pudo loguearse para la auditoría.")
        else:
            logger.error("❌ Scraper de lista no pudo loguearse.")

    except Exception as e:
        logger.error(f"❌ Error crítico en Auditoría de Datos: {e}")

    # --- FASE 3: SANEAMIENTO INTELIGENTE DE LOGS (Eliminar Rebotes) ---
    try:
        logger.info("🧹 FASE 3: Iniciando Saneamiento Quirúrgico de Tiempos...")
        orders = db.query(Order).all()
        total_borrados = 0
        pedidos_afectados = 0

        for o in orders:
            logs = (
                db.query(OrderStatusLog)
                .filter(OrderStatusLog.order_id == o.id)
                .order_by(asc(OrderStatusLog.timestamp))
                .all()
            )

            if len(logs) <= 1:
                continue

            logs_a_borrar = []
            estados_vistos = set()
            estado_final_alcanzado = False

            for log in logs:
                estado_actual = log.status.lower().strip()

                if estado_final_alcanzado:
                    logs_a_borrar.append(log)
                    continue

                if estado_actual in estados_vistos:
                    logs_a_borrar.append(log)
                    continue

                estados_vistos.add(estado_actual)

                if estado_actual in ["delivered", "canceled"]:
                    estado_final_alcanzado = True

            if logs_a_borrar:
                logger.info(
                    f"📦 Pedido #{o.external_id}: Borrando {len(logs_a_borrar)} logs (Rebotes/Zombies)."
                )
                for basura in logs_a_borrar:
                    db.delete(basura)
                total_borrados += len(logs_a_borrar)
                pedidos_afectados += 1

        if total_borrados > 0:
            db.commit()  # <--- GUARDADO AUTOMÁTICO (Sin preguntar 's/n')
            logger.info(
                f"✅ Limpieza Quirúrgica completada. Se borraron {total_borrados} logs en {pedidos_afectados} pedidos."
            )
        else:
            logger.info("✨ La Base de Datos está inmaculada. No hay rebotes.")

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error en la Fase 3 de Saneamiento: {e}")
    finally:
        db.close()

    logger.info("🏆 PROTOCOLO DE MANTENIMIENTO NOCTURNO COMPLETADO.")
    return "System Healthy"
