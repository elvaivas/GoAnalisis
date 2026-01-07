from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, Date, case, and_, or_, text
from typing import List, Dict, Any, Optional
from datetime import date, datetime, timedelta
from app.db.base import OrderItem
import re

from app.db.base import Order, OrderStatusLog, Driver, Store, Customer

# --- HELPER: BÚSQUEDA GLOBAL ---
def apply_search(query, search_query: str):
    if search_query:
        return query.join(Customer, Order.customer_id == Customer.id, isouter=True)\
            .filter(or_(
                Order.external_id.ilike(f"%{search_query}%"),
                Customer.name.ilike(f"%{search_query}%")
            ))
    return query

def _parse_duration_string(duration_str: str) -> int:
    if not duration_str: return 0
    total_seconds = 0
    duration_str = duration_str.lower()
    hours_match = re.search(r'(\d+)\s*(h|hr|hora)', duration_str)
    if hours_match: total_seconds += int(hours_match.group(1)) * 3600
    minutes_match = re.search(r'(\d+)\s*(m|min)', duration_str)
    if minutes_match: total_seconds += int(minutes_match.group(1)) * 60
    return total_seconds

# --- FUNCIONES DE ANÁLISIS ---

def get_daily_trends(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None, store_name: Optional[str] = None, search_query: Optional[str] = None) -> Dict[str, List]:
    # Usamos timezone para agrupar por el día CORRECTO en Venezuela
    # Convertimos UTC -> America/Caracas y luego extraemos la fecha
    date_col = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))
    
    query = db.query(
        date_col.label('date'),
        func.count(Order.id).label('total_orders'),
        func.sum(Order.total_amount).label('total_revenue'),
        func.avg(case(
            (and_(
                Order.current_status == 'delivered', 
                Order.order_type == 'Delivery',
                Order.delivery_time_minutes != None
            ), Order.delivery_time_minutes),
            else_=None
        )).label('avg_time')
    )

    # Filtros con Timezone
    if start_date: query = query.filter(date_col >= start_date)
    if end_date: query = query.filter(date_col <= end_date)
    
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    query = apply_search(query, search_query)

    results = query.group_by(date_col).order_by(date_col).all()

    return {
        "labels": [r.date.strftime('%Y-%m-%d') for r in results],
        "revenue": [float(r.total_revenue or 0) for r in results],
        "orders": [int(r.total_orders) for r in results],
        "avg_times": [round(float(r.avg_time or 0), 1) for r in results]
    }

def get_driver_leaderboard(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None, store_name: Optional[str] = None, search_query: Optional[str] = None):
    # Usamos la misma lógica de fecha local para filtros
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))

    query = db.query(
        Driver.name, 
        func.count(Order.id).label('total_orders'), 
        func.max(Order.created_at).label('last_delivery'), 
        func.min(Order.created_at).label('first_delivery')
    ).join(Order, Order.driver_id == Driver.id)

    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    query = apply_search(query, search_query)

    # Límite aumentado a 50
    results = query.group_by(Driver.name).order_by(desc('total_orders'), Driver.name).limit(50).all()
    
    data = []
    now = datetime.utcnow()
    for row in results:
        days_inactive = -1; daily_avg = 0.0; status = "unknown"
        if row.first_delivery:
            days_active = (now - row.first_delivery).days
            if days_active < 1: days_active = 1
            daily_avg = row.total_orders / days_active
        if row.last_delivery:
            days_inactive = (now - row.last_delivery).days
            if row.total_orders < 20: status = "new"
            elif days_inactive <= 2: status = "active"
            elif days_inactive <= 10: status = "warning"
            else: status = "inactive"
        data.append({"name": row.name, "orders": row.total_orders, "days_inactive": days_inactive, "daily_avg": round(daily_avg, 1), "status": status})
    return data

def get_top_stores(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None, store_name: Optional[str] = None, search_query: Optional[str] = None):
    # Subquery para fecha de inicio
    start_date_subquery = db.query(Order.store_id, func.min(Order.created_at).label('first_order_date')).group_by(Order.store_id).subquery()
    
    query = db.query(
        Store.name, 
        func.count(Order.id).label('total_orders'), 
        start_date_subquery.c.first_order_date
    ).join(Order, Order.store_id == Store.id).outerjoin(start_date_subquery, Store.id == start_date_subquery.c.store_id)
    
    # Filtro fecha local
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))
    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    
    if store_name: query = query.filter(Store.name == store_name)
    query = apply_search(query, search_query)

    # SIN LIMIT
    results = query.group_by(Store.name, start_date_subquery.c.first_order_date).order_by(desc('total_orders')).all()
    return [{"name": row.name or "Tienda Desconocida", "orders": row.total_orders, "first_seen": row.first_order_date.strftime('%d/%m/%Y') if row.first_order_date else "N/A"} for row in results]

def calculate_bottlenecks(db: Session, store_name: Optional[str] = None, search_query: Optional[str] = None):
    # Nota: Bottlenecks no suele filtrarse por fecha en este diseño, pero si quisieras, usa la misma lógica.
    base_query = db.query(OrderStatusLog.order_id, OrderStatusLog.status, OrderStatusLog.timestamp).join(Order, OrderStatusLog.order_id == Order.id)
    if store_name: base_query = base_query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    base_query = apply_search(base_query, search_query)

    subquery_cte = base_query.cte("filtered_logs")
    subquery = db.query(
        subquery_cte.c.order_id, subquery_cte.c.status, subquery_cte.c.timestamp,
        func.lead(subquery_cte.c.timestamp).over(partition_by=subquery_cte.c.order_id, order_by=subquery_cte.c.timestamp).label('next_timestamp')
    ).subquery()
    results = db.query(subquery.c.status, func.avg(subquery.c.next_timestamp - subquery.c.timestamp).label('avg_duration')).group_by(subquery.c.status).all()
    data = []
    for row in results:
        if row.avg_duration: data.append({"status": row.status, "avg_duration_seconds": row.avg_duration.total_seconds()})
    return data

def get_top_customers(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None, store_name: Optional[str] = None, search_query: Optional[str] = None):
    # Filtro fecha local
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))
    
    query = db.query(
        Customer.name, 
        func.count(Order.id).label("total_orders"), 
        func.sum(Order.total_amount).label("total_spent")
    ).join(Order, Order.customer_id == Customer.id).filter(Order.current_status == 'delivered')
    
    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    query = apply_search(query, search_query)

    all_results = query.group_by(Customer.name).order_by(desc("total_spent")).all()
    
    final_list = []
    search_lower = search_query.lower() if search_query else None

    for index, row in enumerate(all_results):
        rank = index + 1
        name = row.name or "Cliente Desconocido"
        if search_lower and search_lower not in name.lower(): continue
        
        final_list.append({"rank": rank, "name": name, "count": row.total_orders, "total_amount": float(row.total_spent or 0)})
        if search_lower and len(final_list) >= 20: break
    
    if not search_query: return final_list[:20]
    return final_list

def get_total_duration_for_order(db: Session, order_id: int):
    logs = db.query(OrderStatusLog).filter(OrderStatusLog.order_id == order_id).order_by(OrderStatusLog.timestamp).all()
    if logs and len(logs) >= 2: return {"total_seconds": (logs[-1].timestamp - logs[0].timestamp).total_seconds(), "source": "live_logs"}
    order = db.query(Order).filter(Order.id == order_id).first()
    if order and hasattr(order, 'duration') and order.duration:
        seconds = _parse_duration_string(order.duration)
        if seconds > 0: return {"total_seconds": seconds, "source": "historical_scraping"}
    return {"total_seconds": 0, "source": "unknown"}

def get_cancellation_reasons(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None, store_name: Optional[str] = None, search_query: Optional[str] = None):
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))
    
    query = db.query(Order.cancellation_reason, func.count(Order.id).label('count')).filter(Order.current_status == 'canceled', Order.cancellation_reason != None)
    
    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    query = apply_search(query, search_query)

    results = query.group_by(Order.cancellation_reason).order_by(desc('count')).all()
    return [{"reason": row.cancellation_reason, "count": row.count} for row in results]

def get_top_products(
    db: Session, 
    start_date: Optional[date] = None, 
    end_date: Optional[date] = None, 
    store_name: Optional[str] = None, 
    search_query: Optional[str] = None
):
    """
    Retorna los productos más vendidos (Excluyendo insumos corporativos y regalos).
    """
    query = db.query(
        OrderItem.name,
        func.sum(OrderItem.quantity).label('total_qty'),
        func.sum(OrderItem.total_price).label('total_revenue')
    ).join(Order, OrderItem.order_id == Order.id)

    # Filtros Generales
    if start_date: query = query.filter(cast(Order.created_at, Date) >= start_date)
    if end_date: query = query.filter(cast(Order.created_at, Date) <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    if search_query:
        query = query.join(Customer, Order.customer_id == Customer.id, isouter=True).filter(or_(
            OrderItem.name.ilike(f"%{search_query}%"),
            Customer.name.ilike(f"%{search_query}%"),
            Order.external_id.ilike(f"%{search_query}%")
        ))

    # --- FILTROS DE LIMPIEZA INTELIGENTE ---
    query = query.filter(
        OrderItem.unit_price > 0.01,           # Ignora cosas de precio 0
        ~OrderItem.name.ilike('%obsequio%'),   # Ignora cualquier regalo explícito
        ~OrderItem.name.ilike('%bolsa%gopharma%') # Ignora SOLO la bolsa de la marca
    )
    # ----------------------------------------

    results = query.group_by(OrderItem.name).order_by(desc('total_qty')).limit(10).all()

    return [{
        "name": row.name,
        "quantity": int(row.total_qty),
        "revenue": float(row.total_revenue)
    } for row in results]
