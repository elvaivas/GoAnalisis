from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from app.api import deps
from app.services import kpi_service
from app.db.base import User # Importar User

router = APIRouter()

@router.get("/main", summary="Obtener KPIs Principales con Filtros")
def get_main_kpis(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user) # Obtenemos el usuario
):
    # 1. Obtener la data cruda
    data = kpi_service.get_main_kpis(
        db=db, start_date=start_date, end_date=end_date, 
        store_name=store_name, search_query=search
    )

    # 2. FILTRO DE SEGURIDAD (CENSURA)
    # Si NO es admin, sobrescribimos los valores financieros con 0 o None
    if current_user.role != 'admin':
        data['total_revenue'] = 0
        data['total_fees'] = 0
        data['total_coupons'] = 0
        data['driver_payout'] = 0
        data['company_profit'] = 0
    
    return data
