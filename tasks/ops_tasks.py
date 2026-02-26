import logging
from datetime import datetime, timedelta
from celery import shared_task
from app.db.session import SessionLocal
from app.db.base import Store, StoreSchedule, StoreHoliday
from tasks.scraper.store_controller import StoreControllerScraper

logger = logging.getLogger(__name__)


# ==========================================
# 1. EL ORQUESTADOR (El que piensa)
# Se ejecuta cada 5 minutos por Celery Beat
# ==========================================
@shared_task(bind=True)
def enforce_schedules(self):
    db = SessionLocal()
    now_vet = datetime.utcnow() - timedelta(hours=4)
    today_date = now_vet.date()
    current_day = now_vet.weekday()
    current_minutes_total = now_vet.hour * 60 + now_vet.minute

    all_stores = db.query(Store).filter(Store.external_id != None).all()

    stores_to_shutdown = []

    for store in all_stores:
        holiday = (
            db.query(StoreHoliday)
            .filter(
                StoreHoliday.date == today_date,
                (StoreHoliday.store_id == store.id) | (StoreHoliday.store_id == None),
            )
            .first()
        )

        is_forbidden_time = False

        if holiday:
            if holiday.is_closed_all_day:
                is_forbidden_time = True
            else:
                start_min = int(holiday.open_time.split(":")[0]) * 60 + int(
                    holiday.open_time.split(":")[1]
                )
                end_min = (
                    int(holiday.close_time.split(":")[0]) * 60
                    + int(holiday.close_time.split(":")[1])
                ) - 60
                is_forbidden_time = (current_minutes_total < start_min) or (
                    current_minutes_total >= end_min
                )
        else:
            rule = (
                db.query(StoreSchedule)
                .filter(
                    StoreSchedule.store_id == store.id,
                    StoreSchedule.day_of_week == current_day,
                    StoreSchedule.is_active == True,
                )
                .first()
            )

            if not rule:
                continue

            start_min = int(rule.open_time.split(":")[0]) * 60 + int(
                rule.open_time.split(":")[1]
            )
            end_min = (
                int(rule.close_time.split(":")[0]) * 60
                + int(rule.close_time.split(":")[1])
            ) - rule.buffer_minutes

            is_forbidden_time = (current_minutes_total < start_min) or (
                current_minutes_total >= end_min
            )

        # Si está fuera de horario, la agregamos a la lista de "objetivos"
        if is_forbidden_time:
            stores_to_shutdown.append(
                {"name": store.name, "external_id": store.external_id}
            )

    db.close()

    # ==========================================
    # 2. EL FAN-OUT (El ataque en paralelo)
    # Mandamos una mini-tarea por cada farmacia
    # ==========================================
    if not stores_to_shutdown:
        return "Orquestador: Ninguna farmacia requiere apagado en este momento."

    logger.info(
        f"🚀 Orquestador: {len(stores_to_shutdown)} farmacias deben estar apagadas. Lanzando ninjas..."
    )

    for target in stores_to_shutdown:
        # Llamamos a la sub-tarea asíncrona para que no bloquee este script
        execute_single_store_shutdown.delay(target["name"], target["external_id"])

    return f"Orquestador: Lanzadas {len(stores_to_shutdown)} tareas de apagado independientes."


# ==========================================
# 3. EL OBRERO / NINJA (El que dispara)
# Toma 1 sola tienda, entra, hace clic, y se va.
# ==========================================
@shared_task(bind=True, max_retries=2)
def execute_single_store_shutdown(self, store_name, store_external_id):
    logger.info(f"🥷 Ninja activado para apagar: {store_name}")

    controller = StoreControllerScraper()
    try:
        # Forzamos el apagado (desired_status_bool = False)
        was_switched_off = controller.enforce_store_status(
            store_name=store_name,
            desired_status_bool=False,
            store_external_id=store_external_id,
        )
        if was_switched_off:
            return f"✅ {store_name} APAGADA con éxito."
        else:
            return f"ℹ️ {store_name} ya estaba apagada."

    except Exception as e:
        logger.error(f"❌ Fallo al apagar {store_name}. Reintentando... Error: {e}")
        # Si falla (ej. Gopharma no carga), la tarea se reintenta automáticamente en 60 segundos
        raise self.retry(exc=e, countdown=60)

    finally:
        controller.close()
