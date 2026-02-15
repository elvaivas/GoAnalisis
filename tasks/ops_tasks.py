import logging
import re
from datetime import datetime, timedelta
from celery import shared_task
from app.db.session import SessionLocal
from app.db.base import Store, StoreSchedule, StoreHoliday
from tasks.scraper.store_controller import StoreControllerScraper
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def enforce_schedules(self):
    """
    Tarea que revisa horarios y apaga farmacias.
    Pasa nombre e ID externo para una búsqueda híbrida infalible.
    """
    db = SessionLocal()
    now_vet = datetime.utcnow() - timedelta(hours=4)
    today_date = now_vet.date()
    current_day = now_vet.weekday()
    current_minutes_total = now_vet.hour * 60 + now_vet.minute

    # 1. Buscamos todas las tiendas
    all_stores = db.query(Store).filter(Store.external_id != None).all()

    controller = StoreControllerScraper()
    login_done = False
    changes_count = 0

    for store in all_stores:
        # A. Verificar si hoy es feriado (Regla de Precedencia)
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
                h_open_h, h_open_m = map(int, holiday.open_time.split(":"))
                h_close_h, h_close_m = map(int, holiday.close_time.split(":"))
                start_min = h_open_h * 60 + h_open_m
                end_min = (h_close_h * 60 + h_close_m) - 60
                is_forbidden_time = (current_minutes_total < start_min) or (
                    current_minutes_total >= end_min
                )
        else:
            # B. Si no es feriado, buscar regla semanal
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

            r_open_h, r_open_m = map(int, rule.open_time.split(":"))
            r_close_h, r_close_m = map(int, rule.close_time.split(":"))
            start_min = r_open_h * 60 + r_open_m
            end_min = (r_close_h * 60 + r_close_m) - rule.buffer_minutes
            is_forbidden_time = (current_minutes_total < start_min) or (
                current_minutes_total >= end_min
            )

        # --- EJECUCIÓN ---
        if is_forbidden_time:
            if not login_done:
                if controller.login():
                    login_done = True
                else:
                    break

            logger.info(
                f"🛡️ Vigilante: Auditando {store.name} (ID Externo: {store.external_id})..."
            )

            # ENVIAMOS AMBOS DATOS AL CONTROLADOR
            was_switched_off = controller.enforce_store_status(
                store_name=store.name,
                store_external_id=store.external_id,
                desired_status_bool=False,
            )

            if was_switched_off:
                changes_count += 1

    if login_done:
        controller.close()
    db.close()
    return f"Vigilancia completada. Se forzaron {changes_count} cierres."
