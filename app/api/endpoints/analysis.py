from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime  # <--- Importante para date.today()
from app.db.base import OrderStatusLog, User, Order, Store, OrderAudit
from sqlalchemy import func, extract, or_, desc, case

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


@router.get("/ops-executive-summary")
def get_ops_executive_summary(
    start_date: str, end_date: str, db: Session = Depends(deps.get_db)
):
    """
    Motor de Inteligencia Operativa SRE.
    Extrae los KPIs exactos para el Dashboard de Operaciones en una sola llamada.
    """
    try:
        # 1. Parseo de fechas
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )

        # Filtro base para las órdenes
        base_filter = Order.created_at.between(start_dt, end_dt)

        # --- BLOQUE 1: SALUD GLOBAL Y VOLUMEN ---
        total_orders = db.query(func.count(Order.id)).filter(base_filter).scalar() or 0

        status_counts = (
            db.query(Order.current_status, func.count(Order.id))
            .filter(base_filter)
            .group_by(Order.current_status)
            .all()
        )

        status_dict = {status: count for status, count in status_counts}
        delivered = status_dict.get("delivered", 0)

        # 💉 INYECCIÓN SRE: Filtramos cancelados que NO sean en Efectivo (asumiendo que los demás son digitales/pagados)
        canceled = (
            db.query(func.count(Order.id))
            .filter(
                base_filter,
                Order.current_status == "canceled",
                func.lower(Order.payment_method).not_like("%efectivo%"),
                func.lower(Order.payment_method).not_like("%cash%"),
            )
            .scalar()
            or 0
        )

        # El requerimiento de Punto de Venta (POS) Real - Leyendo la DB
        # Buscamos coincidencias con "punto", "pos", "tarjeta", etc. (Ajustable a como lo guarde el Drone)
        pos_orders = (
            db.query(func.count(Order.id))
            .filter(base_filter, func.lower(Order.payment_method).like("%punto%"))
            .scalar()
            or 0
        )

        # Efectividad
        fulfillment_rate = (
            round((delivered / total_orders * 100), 2) if total_orders > 0 else 0
        )

        # --- BLOQUE 2: RENDIMIENTO COMERCIAL (TOP 5 FARMACIAS) ---
        # Ideal para un gráfico de Barras Horizontales
        top_stores = (
            db.query(Store.name, func.count(Order.id).label("total_orders"))
            .join(Order, Store.id == Order.store_id)
            .filter(base_filter)
            .group_by(Store.name)
            .order_by(desc("total_orders"))
            .limit(5)
            .all()
        )

        top_stores_data = [
            {"store": s.name, "orders": s.total_orders} for s in top_stores
        ]

        # --- BLOQUE 3: FRICCIÓN (TOP 5 INCIDENCIAS) ---
        # Ideal para un gráfico de Anillo / Donut Chart (Gracias al Diccionario SRE)

        top_incidences = (
            db.query(OrderAudit.root_cause, func.count(OrderAudit.id).label("count"))
            .join(Order, Order.id == OrderAudit.order_id)
            .filter(
                Order.created_at.between(start_dt, end_dt),
                OrderAudit.root_cause != None,
            )
            .group_by(OrderAudit.root_cause)
            .order_by(desc("count"))
            .limit(5)
            .all()
        )

        incidences_data = [
            {"cause": i.root_cause, "count": i.count} for i in top_incidences
        ]

        # --- BLOQUE 4: OPERACIONES ESPECIALES (TURNO NOCTURNO 22:00 a 08:00) ---
        # Usamos extract('hour') de Postgres para saber la hora de creación
        night_orders = (
            db.query(func.count(Order.id))
            .filter(
                base_filter,
                or_(
                    extract("hour", Order.created_at) >= 22,
                    extract("hour", Order.created_at) < 8,
                ),
            )
            .scalar()
            or 0
        )

        # --- BLOQUE 5: CANCELACIONES POR FARMACIA (SOLO REEMBOLSOS / MÉTODOS DIGITALES) ---
        top_canceled_stores = (
            db.query(Store.name, func.count(Order.id).label("canceled_count"))
            .join(Order, Store.id == Order.store_id)
            .filter(
                base_filter,
                Order.current_status == "canceled",
                func.lower(Order.payment_method).not_like("%efectivo%"),
                func.lower(Order.payment_method).not_like("%cash%"),
            )
            .group_by(Store.name)
            .order_by(desc("canceled_count"))
            .limit(5)
            .all()
        )

        canceled_stores_data = [
            {"store": s.name, "canceled": s.canceled_count} for s in top_canceled_stores
        ]

        # --- EMPAQUETADO FINAL PARA EL FRONTEND ---
        return {
            "global_health": {
                "total_orders": total_orders,
                "delivered": delivered,
                "canceled": canceled,
                "fulfillment_rate": fulfillment_rate,
                "pos_orders": pos_orders,  # Punto de venta (created)
                "night_orders": night_orders,
            },
            "charts": {
                "top_stores": top_stores_data,
                "top_incidences": incidences_data,
                "canceled_stores": canceled_stores_data,
            },
        }

    except Exception as e:
        return {"error": str(e)}
