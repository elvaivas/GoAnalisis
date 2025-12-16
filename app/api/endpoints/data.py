from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, Date, or_
from typing import List, Optional, Any
from datetime import date

from app.api import deps
from app.db.base import Order, Store, OrderStatusLog, Customer, Driver
from app.schemas.order import OrderSchema
from app.services import analysis_service

router = APIRouter()

# --- HELPER INTERNO PARA REUTILIZAR FILTROS ---
def apply_filters(query, start_date, end_date, store_name, search):
    # 1. Filtro Fecha
    if start_date:
        query = query.filter(cast(Order.created_at, Date) >= start_date)
    if end_date:
        query = query.filter(cast(Order.created_at, Date) <= end_date)
    
    # 2. Filtro Tienda
    if store_name:
        query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    # 3. FILTRO BÚSQUEDA (EL CEREBRO NUEVO)
    if search:
        # Limpiamos espacios
        term = search.strip()
        
        # Si es un número puro, asumimos búsqueda de ID de Pedido (Prioridad Exacta o Inicio)
        # Esto cumple tu requerimiento de "ID Exacto" o aproximado numérico
        if term.isdigit():
             query = query.filter(Order.external_id.like(f"{term}%"))
        else:
             # Si es texto, buscamos en Nombre Cliente (Partial Match)
             # Necesitamos unir con Customer si no se ha hecho
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
    search: Optional[str] = Query(None) # <--- RECIBE SEARCH
):
    query = db.query(Order)
    query = apply_filters(query, start_date, end_date, store_name, search)

    # Ordenar y limitar
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
def get_stores_locations(db: Session = Depends(deps.get_db)):
    # Las tiendas son estáticas, no dependen del filtro de búsqueda de pedidos
    stores = db.query(Store).filter(Store.latitude != None).all()
    return [{"name": s.name, "lat": s.latitude, "lng": s.longitude} for s in stores]

@router.get("/heatmap", summary="Puntos para Mapa de Calor")
def get_heatmap_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None) # <--- AHORA EL MAPA ESCUCHA
):
    # Base: Coordenadas válidas
    query = db.query(Order.latitude, Order.longitude).filter(
        Order.latitude != None, 
        Order.latitude != 0.0,
        Order.longitude != None
    )

    # Aplicamos el filtro universal
    query = apply_filters(query, start_date, end_date, store_name, search)
    
    points = query.limit(5000).all()
    return [[p.latitude, p.longitude, 0.8] for p in points]

@router.get("/trends", summary="Tendencias")
def get_trends_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    return analysis_service.get_daily_trends(db, start_date, end_date, store_name, search)

@router.get("/driver-leaderboard", summary="Ranking Repartidores")
def get_driver_leaderboard_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    return analysis_service.get_driver_leaderboard(db, start_date, end_date, store_name, search)

@router.get("/top-stores", summary="Ranking Tiendas")
def get_top_stores_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    return analysis_service.get_top_stores(db, start_date, end_date, store_name, search)

@router.get("/top-customers", summary="Ranking Clientes")
def get_top_customers_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    return analysis_service.get_top_customers(db, start_date, end_date, store_name, search)
