from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from app.api import deps
from app.services import kpi_service

router = APIRouter()

@router.get("/main", summary="Obtener KPIs Principales")
def get_main_kpis(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    # Si no hay ningún filtro, forzamos HOY
    if not start_date and not end_date and not store_name and not search:
        start_date = date.today()
        end_date = date.today()

    return kpi_service.get_main_kpis(
        db=db, start_date=start_date, end_date=end_date, 
        store_name=store_name, search_query=search
    )
    return kpis
