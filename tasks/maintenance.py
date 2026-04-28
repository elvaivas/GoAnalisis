import logging
import redis
import time
from datetime import datetime, timedelta, timezone
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
    1.5. Rescate de Pedidos Atascados (Zombies locales).
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
        logger.error(f"❌ Error limpiando Redis: {e}")

    db = SessionLocal()

    # --- NUEVA FASE 1.5: RESCATE DE PEDIDOS ATASCADOS (De fix_stuck_orders.py) ---
    try:
        logger.info("🚨 FASE 1.5: Buscando pedidos atascados (Zombies) en BD local...")
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        yesterday = now_utc - timedelta(hours=30)
        limit_time = now_utc - timedelta(hours=4)

        stuck_orders = (
            db.query(Order)
            .filter(
                Order.created_at >= yesterday,
                Order.created_at <= limit_time,
                Order.current_status.in_(
                    [
                        "pending",
                        "processing",
                        "confirmed",
                        "driver_assigned",
                        "on_the_way",
                    ]
                ),
            )
            .all()
        )

        if stuck_orders:
            logger.info(
                f"⚠️ Se encontraron {len(stuck_orders)} pedidos atascados. Iniciando Dron Médico..."
            )
            drone_fix = DroneScraper()
            try:
                if drone_fix.login():
                    for stuck in stuck_orders:
                        logger.info(
                            f"💉 Reparando pedido atascado #{stuck.external_id}..."
                        )
                        try:
                            # Dependiendo de tu scraper, usa scrape_single_order o scrape_detail
                            data = drone_fix.scrape_detail(
                                stuck.external_id, mode="full"
                            )
                            if data:
                                process_drone_data(db, data)
                        except Exception as e:
                            logger.error(
                                f"❌ Fallo al destrabar #{stuck.external_id}: {e}"
                            )
                else:
                    logger.error("❌ El dron médico no pudo loguearse.")
            finally:
                drone_fix.close_driver()  # Previene el error 'invalid session id'
        else:
            logger.info("✅ Cero pedidos atascados. Base de datos local al día.")

    except Exception as e:
        logger.error(f"❌ Error crítico en Fase 1.5 (Rescate): {e}")

    # --- FASE 2: AUDITORÍA DE DATOS (ÚLTIMAS 48H) ---
    try:
        logger.info("🕵️‍♂️ FASE 2: Iniciando Auditoría de Integridad (48 Horas)...")
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
                    # 👇 DETECTOR DE INFECCIÓN CORREGIDO (Seguro para SQLAlchemy) 👇
                    elif not getattr(local_order, 'order_type', None) or getattr(local_order, 'order_type', '') == "desconocido":
                        needs_repair = True
                        logger.info(f"🦠 Orden ciega detectada en #{eid}. Marcando para re-escaneo...")
                    # 👆 FIN DETECTOR CORREGIDO 👆
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
                            if data and not data.get("duration_text"):
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
            db.commit()
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
