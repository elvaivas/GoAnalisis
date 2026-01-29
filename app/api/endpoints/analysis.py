from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date # <--- Importante para date.today()

# Importamos deps y nuestros servicios
from app.api import deps
from app.services import analysis_service, task_service

router = APIRouter()

@router.get("/bottlenecks", summary="Calcular Tiempos Promedio por Estado")
def get_bottleneck_analysis(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None), # <--- AGREGADO
    end_date: Optional[date] = Query(None),   # <--- AGREGADO
    store_name: Optional[str] = Query(None, description="Filtrar por nombre de tienda"),
    search: Optional[str] = Query(None, description="Buscar por ID o Cliente")
):
    bottlenecks = analysis_service.calculate_bottlenecks(
        db=db, 
        start_date=start_date, # <--- PASAMOS EL DATO
        end_date=end_date,     # <--- PASAMOS EL DATO
        store_name=store_name,
        search_query=search
    )
    return bottlenecks

@router.get("/order-duration/{order_id}", summary="Calcular Duración Total de un Pedido")
def get_order_duration(order_id: int, db: Session = Depends(deps.get_db)):
    duration_data = analysis_service.get_total_duration_for_order(db=db, order_id=order_id)
    return duration_data

@router.post("/trigger-backfill", status_code=202, summary="Disparar Tarea de Backfilling Histórico")
def trigger_backfill_task():
    task_id = task_service.trigger_backfill()
    return {"message": "La tarea de backfilling de datos históricos ha sido iniciada.", "task_id": task_id}

@router.get("/cancellations", summary="Obtener motivos de cancelación")
def get_cancellation_analysis(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None, description="Filtrar por nombre de tienda"),
    search: Optional[str] = Query(None, description="Buscar por ID o Cliente")
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
        search_query=search
    )

@router.post("/trigger-drone", status_code=202, summary="Activar Drone de Enriquecimiento")
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
