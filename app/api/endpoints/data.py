from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, Date, or_
from typing import List, Optional, Any
from datetime import date

from app.api import deps
# Importamos User para la seguridad
from app.db.base import Order, Store, OrderStatusLog, Customer, Driver, User
from app.schemas.order import OrderSchema
from app.services import analysis_service

router = APIRouter()

# --- HELPER INTERNO ---
def apply_filters(query, start_date, end_date, store_name, search):
    # 1. Filtro Fecha
    if start_date:
        query = query.filter(cast(Order.created_at, Date) >= start_date)
    if end_date:
        query = query.filter(cast(Order.created_at, Date) <= end_date)
    
    # 2. Filtro Tienda
    if store_name:
        query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    # 3. Filtro Búsqueda
    if search:
        term = search.strip()
        if term.isdigit():
             query = query.filter(Order.external_id.like(f"{term}%"))
        else:
             query = query.join(Customer, Order.customer_id == Customer.id, isouter=True)\
                          .filter(Customer.name.ilike(f"%{term}%"))
    
    return query

# ---------------------------------------------------------

@router.get("/orders", summary="Obtener lista de pedidos filtrada")
def get_recent_orders(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None), # <--- ¡AQUÍ FALTABA LA COMA!
    current_user: User = Depends(deps.get_current_user) # <--- SEGURIDAD ACTIVADA
):
    query = db.query(Order)
    query = apply_filters(query, start_date, end_date, store_name, search)

    orders = query.order_by(Order.created_at.desc()).limit(100).all()
    
    data_response = []
    for o in orders:
        last_log = db.query(OrderStatusLog).filter(OrderStatusLog.order_id == o.id).order_by(OrderStatusLog.timestamp.desc()).first()
        state_start = last_log.timestamp if last_log else o.created_at

        data_response.append({
            "id": o.id,
            "external_id": o.external_id,
            "current_status": o.current_status,
            "order_type": o.order_type,
            "total_amount": o.total_amount,
            "delivery_fee": o.delivery_fee,
            "created_at": o.created_at,
            "state_start_at": state_start,
            "duration_text": o.duration,
            "distance_km": o.distance_km,
            "customer_name": o.customer.name if o.customer else "N/A",
            "customer_phone": o.customer.phone if o.customer and o.customer.phone else None
        })
    return data_response

@router.get("/stores-locations", summary="Ubicación de Tiendas")
def get_stores_locations(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user) # <--- SEGURIDAD
):
    stores = db.query(Store).filter(Store.latitude != None).all()
    return [{"name": s.name, "lat": s.latitude, "lng": s.longitude} for s in stores]

@router.get("/heatmap", summary="Puntos para Mapa de Calor")
def get_heatmap_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user) # <--- SEGURIDAD
):
    query = db.query(Order.latitude, Order.longitude).filter(
        Order.latitude != None, 
        Order.latitude != 0.0,
        Order.longitude != None
    )
    query = apply_filters(query, start_date, end_date, store_name, search)
    points = query.limit(5000).all()
    return [[p.latitude, p.longitude, 0.8] for p in points]

@router.get("/trends", summary="Tendencias")
def get_trends_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user) # <--- SEGURIDAD
):
    data = analysis_service.get_daily_trends(db, start_date, end_date, store_name, search)
    
    # CENSURA PARA VIEWERS
    if current_user.role != 'admin':
        # Reemplazamos la lista de ingresos con ceros
        data['revenue'] = [0] * len(data['revenue'])
        
    return data

@router.get("/driver-leaderboard", summary="Ranking Repartidores")
def get_driver_leaderboard_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user) # <--- SEGURIDAD
):
    return analysis_service.get_driver_leaderboard(db, start_date, end_date, store_name, search)

@router.get("/top-stores", summary="Ranking Tiendas")
def get_top_stores_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user) # <--- SEGURIDAD
):
    return analysis_service.get_top_stores(db, start_date, end_date, store_name, search)

@router.get("/top-customers", summary="Ranking Clientes")
def get_top_customers_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user) # <--- SEGURIDAD
):
    return analysis_service.get_top_customers(db, start_date, end_date, store_name, search)

@router.get("/all-stores-names", summary="Lista completa de tiendas para filtros")
def get_all_stores_names(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user) # <--- SEGURIDAD
):
    stores = db.query(Store.name).order_by(Store.name.asc()).all()
    return [s.name for s in stores if s.name]
