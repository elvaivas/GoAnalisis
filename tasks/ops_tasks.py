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
    db = SessionLocal()
    now_vet = datetime.utcnow() - timedelta(hours=4)
    today_date = now_vet.date()
    current_day = now_vet.weekday()
    current_minutes_total = now_vet.hour * 60 + now_vet.minute

    # 1. BUSCAR TIENDAS ACTIVAS
    # Para cada tienda, decidiremos qué regla aplicar
    all_stores = db.query(Store).filter(Store.external_id != None).all()

    controller = StoreControllerScraper()
    login_done = False
    changes_count = 0

    for store in all_stores:
        # --- LÓGICA DE PRECEDENCIA ---

        # A. ¿Hay un feriado para esta tienda hoy (o un feriado global)?
        holiday = (
            db.query(StoreHoliday)
            .filter(
                StoreHoliday.date == today_date,
                (StoreHoliday.store_id == store.id) | (StoreHoliday.store_id == None),
            )
            .first()
        )

        rule_to_apply = None

        if holiday:
            logger.info(f"🎊 Hoy es feriado para {store.name}: {holiday.description}")
            if holiday.is_closed_all_day:
                # Forzar apagado todo el día
                is_forbidden_time = True
            else:
                # Usar horario especial del feriado
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
            # B. Si no es feriado, buscar regla semanal normal
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
                continue  # No hay reglas para esta tienda hoy

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

        # --- EJECUCIÓN DEL APAGADO ---
        if is_forbidden_time:
            if not login_done:
                if controller.login():
                    login_done = True
                else:
                    break

            was_switched_off = controller.enforce_store_status(
                store.name, desired_status_bool=False
            )

            if was_switched_off:
                changes_count += 1

    if login_done:
        controller.close()
    db.close()

    # Reporte final más honesto
    return f"Vigilancia completada. Se forzó el cierre de {changes_count} tiendas que estaban abiertas indebidamente."
