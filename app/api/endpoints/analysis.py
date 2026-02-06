from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date  # <--- Importante para date.today()
from app.db.base import OrderStatusLog, User

# Importamos deps y nuestros servicios
from app.api import deps
from app.services import analysis_service, task_service

router = APIRouter()


@router.get("/bottlenecks", summary="Calcular Tiempos Promedio por Estado")
def get_bottleneck_analysis(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),  # <--- AGREGADO
    end_date: Optional[date] = Query(None),  # <--- AGREGADO
    store_name: Optional[str] = Query(None, description="Filtrar por nombre de tienda"),
    search: Optional[str] = Query(None, description="Buscar por ID o Cliente"),
):
    bottlenecks = analysis_service.calculate_bottlenecks(
        db=db,
        start_date=start_date,  # <--- PASAMOS EL DATO
        end_date=end_date,  # <--- PASAMOS EL DATO
        store_name=store_name,
        search_query=search,
    )
    return bottlenecks


@router.get(
    "/order-duration/{order_id}", summary="Calcular Duración Total de un Pedido"
)
def get_order_duration(order_id: int, db: Session = Depends(deps.get_db)):
    duration_data = analysis_service.get_total_duration_for_order(
        db=db, order_id=order_id
    )
    return duration_data


@router.post(
    "/trigger-backfill",
    status_code=202,
    summary="Disparar Tarea de Backfilling Histórico",
)
def trigger_backfill_task():
    task_id = task_service.trigger_backfill()
    return {
        "message": "La tarea de backfilling de datos históricos ha sido iniciada.",
        "task_id": task_id,
    }


@router.get("/cancellations", summary="Obtener motivos de cancelación")
def get_cancellation_analysis(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None, description="Filtrar por nombre de tienda"),
    search: Optional[str] = Query(None, description="Buscar por ID o Cliente"),
):
    # --- LÓGICA: SI NO HAY FILTROS, MOSTRAR SOLO HOY ---
    if not start_date and not end_date and not store_name and not search:
        start_date = date.today()
        end_date = date.today()
    # ---------------------------------------------------

    return analysis_service.get_cancellation_reasons(
        db=db,
        start_date=start_date,
        end_date=end_date,
        store_name=store_name,
        search_query=search,
    )


@router.post(
    "/trigger-drone", status_code=202, summary="Activar Drone de Enriquecimiento"
)
def trigger_drone_task(
    force: bool = Query(False, description="Set a True para borrar candados zombies.")
):
    task_id = task_service.trigger_drone(force=force)

    msg = "Drone desplegado."
    if force:
        msg += " (AVISO: Se forzó la liberación del candado)."

    return {"message": msg, "task_id": task_id}


@router.post("/trigger-customer-sync", status_code=202)
def trigger_customer_sync_task():
    task_service.trigger_customer_sync()
    return {"message": "Sincronización de clientes iniciada"}


@router.get("/order/{order_id}/timeline", summary="Cronología detallada de un pedido")
def get_order_timeline(
    order_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Calcula cuánto tiempo pasó el pedido en cada estado.
    Retorna etiquetas y tiempos en minutos para graficar.
    """
    # 1. Obtener logs ordenados
    logs = (
        db.query(OrderStatusLog)
        .filter(OrderStatusLog.order_id == order_id)
        .order_by(OrderStatusLog.timestamp.asc())
        .all()
    )

    if not logs:
        return {"labels": [], "data": [], "colors": []}

    labels = []
    durations = []
    colors = []

    # Mapa de colores coherente con el Dashboard
    color_map = {
        "created": "#343a40",  # Dark
        "pending": "#6c757d",  # Grey
        "processing": "#ffc107",  # Warning (Amarillo)
        "confirmed": "#0d6efd",  # Primary (Azul)
        "driver_assigned": "#212529",  # Dark (Negro)
        "on_the_way": "#0dcaf0",  # Info (Celeste)
        "delivered": "#198754",  # Success (Verde)
        "canceled": "#dc3545",  # Danger (Rojo)
    }

    # Traductor
    trans_map = {
        "created": "Creado",
        "pending": "Pendiente",
        "processing": "Facturando",
        "confirmed": "Solicitando",
        "driver_assigned": "Asignado",
        "on_the_way": "En Camino",
        "delivered": "Entregado",
        "canceled": "Cancelado",
    }

    # 2. Calcular Deltas
    for i in range(len(logs) - 1):
        current_log = logs[i]
        next_log = logs[i + 1]

        # Diferencia en minutos
        delta = (next_log.timestamp - current_log.timestamp).total_seconds() / 60

        # Solo guardamos si duró algo significativo (> 0.1 min)
        if delta > 0.1:
            status_key = current_log.status.lower()
            labels.append(trans_map.get(status_key, status_key))
            durations.append(round(delta, 1))
            colors.append(color_map.get(status_key, "#cccccc"))

    # El último estado es el final (no tiene duración medible hasta el infinito)
    # A menos que queramos mostrar cuándo terminó

    return {"labels": labels, "data": durations, "colors": colors}
