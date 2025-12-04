from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from app.api import deps
from app.services import kpi_service

router = APIRouter()

@router.get("/main", summary="Obtener KPIs Principales con Filtros")
def get_main_kpis(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Fecha de fin (YYYY-MM-DD)"),
    store_name: Optional[str] = Query(None, description="Filtrar por nombre de tienda"),
    search: Optional[str] = Query(None, description="Buscar por ID de Pedido o Nombre de Cliente") # <--- NUEVO
):
    """
    Devuelve KPIs principales filtrados por fecha, tienda y búsqueda global.
    """
    kpis = kpi_service.get_main_kpis(
        db=db, 
        start_date=start_date, 
        end_date=end_date,
        store_name=store_name,
        search_query=search # <--- Pasamos el parámetro de búsqueda al servicio
    )
    return kpis
