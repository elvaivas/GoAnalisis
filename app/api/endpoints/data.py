from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, Date # <--- Agregamos 'desc'
from typing import List, Optional, Any
from datetime import date

from app.api import deps
# Agregamos OrderStatusLog para consultar el historial
from app.db.base import Order, Store, OrderStatusLog 
from app.schemas.order import OrderSchema
from app.services import analysis_service

router = APIRouter()

# --- MODIFICADO: Quitamos response_model para permitir campos extra ---
@router.get("/orders", summary="Obtener lista de pedidos filtrada")
def get_recent_orders(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None, description="Fecha inicio"),
    end_date: Optional[date] = Query(None, description="Fecha fin"),
    store_name: Optional[str] = Query(None, description="Nombre de la tienda"),
    search: Optional[str] = Query(None)
):
    """
    Devuelve pedidos recientes con datos para cronómetros en vivo.
    """
    query = db.query(Order)

    # NUEVO: BÚSQUEDA
    if search:
        query = query.join(Customer, Order.customer_id == Customer.id, isouter=True)\
            .filter(or_(Order.external_id.ilike(f"%{search}%"), Customer.name.ilike(f"%{search}%")))

    # 1. Filtro de Tienda
    if store_name:
        query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)

    # 2. Filtro de Fechas
    if start_date and end_date:
        query = query.filter(cast(Order.created_at, Date) >= start_date)
        query = query.filter(cast(Order.created_at, Date) <= end_date)
    elif start_date:
        query = query.filter(cast(Order.created_at, Date) >= start_date)
    else:
        # Por defecto HOY para rapidez
        today = date.today()
        query = query.filter(cast(Order.created_at, Date) == today)

    # Traemos los objetos Order
    orders = query.order_by(Order.created_at.desc()).limit(100).all()
    
    # --- CONSTRUCCIÓN DE DATOS ENRIQUECIDOS ---
    data_response = []
    
    for o in orders:
        # Buscamos cuándo empezó el estado actual
        last_log = db.query(OrderStatusLog)\
            .filter(OrderStatusLog.order_id == o.id)\
            .order_by(OrderStatusLog.timestamp.desc())\
            .first()
        
        # Si hay log, usamos su fecha. Si no, usamos la creación del pedido.
        state_start = last_log.timestamp if last_log else o.created_at

        # Construimos el diccionario manual con los campos extra
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
            
            # --- NUEVOS CAMPOS ---
            "distance_km": o.distance_km,
            "customer_name": o.customer.name if o.customer else "N/A",
            "customer_phone": o.customer.phone if o.customer and o.customer.phone else None
            # ---------------------
        })
    return data_response

@router.get("/stores-locations", summary="Ubicación de Tiendas")
def get_stores_locations(db: Session = Depends(deps.get_db)):
    # OJO: Aquí NO debe haber .limit(10). Debe ser .all()
    stores = db.query(Store).filter(Store.latitude != None).all()
    return [{"name": s.name, "lat": s.latitude, "lng": s.longitude} for s in stores]

@router.get("/heatmap", summary="Puntos para Mapa de Calor")
def get_heatmap_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None)
):
    """
    Retorna lista de [lat, lng, intensidad] para Leaflet.heat.
    """
    query = db.query(Order.latitude, Order.longitude).filter(
        Order.latitude != None,
        Order.latitude != 0.0,
        Order.longitude != None
    )

    if start_date:
        query = query.filter(func.date(Order.created_at) >= start_date)
    if end_date:
        query = query.filter(func.date(Order.created_at) <= end_date)
    if store_name:
        query = query.join(Store).filter(Store.name == store_name)
    
    points = query.limit(5000).all()
    
    return [[p.latitude, p.longitude, 0.8] for p in points]

@router.get("/trends", summary="Obtener datos para el gráfico de tendencias")
def get_trends_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None)
):
    trends_data = analysis_service.get_daily_trends(
        db=db, start_date=start_date, end_date=end_date, store_name=store_name
    )
    return trends_data

@router.get("/driver-leaderboard", summary="Obtener ranking de repartidores")
def get_driver_leaderboard_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None)
):
    leaderboard_data = analysis_service.get_driver_leaderboard(
        db=db, start_date=start_date, end_date=end_date, store_name=store_name
    )
    return leaderboard_data

@router.get("/top-stores", summary="Obtener ranking de tiendas")
def get_top_stores_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None)
):
    top_stores_data = analysis_service.get_top_stores(
        db=db, start_date=start_date, end_date=end_date, store_name=store_name
    )
    return top_stores_data

@router.get("/top-customers", summary="Obtener ranking de clientes fieles")
def get_top_customers_data(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None)
):
    return analysis_service.get_top_customers(
        db=db, start_date=start_date, end_date=end_date, store_name=store_name
    )

@router.get("/all-stores-list", summary="Lista completa de tiendas para filtros")
def get_all_stores_list(db: Session = Depends(deps.get_db)):
    """
    Retorna TODAS las tiendas ordenadas alfabéticamente (Sin límite).
    """
    stores = db.query(Store.name).order_by(Store.name.asc()).all()
    # Retornamos lista simple de strings
    return [s.name for s in stores if s.name]

@router.get("/all-stores-names", summary="Lista simple de nombres de tiendas")
def get_all_stores_names(db: Session = Depends(deps.get_db)):
    """
    Retorna TODAS las tiendas para el filtro (sin límite).
    """
    # Consulta ligera: Solo nombres, ordenados alfabéticamente
    stores = db.query(Store.name).order_by(Store.name.asc()).all()
    return [s.name for s in stores if s.name]
