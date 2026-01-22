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
    # Subquery para fecha inicio
    start_date_subquery = db.query(Order.store_id, func.min(Order.created_at).label('first_order_date')).group_by(Order.store_id).subquery()
    
    # FIX: Join estricto + Filtro de nombre no nulo
    query = db.query(
        Store.name, 
        func.count(Order.id).label('total_orders'), 
        start_date_subquery.c.first_order_date
    ).join(Order, Order.store_id == Store.id).join(start_date_subquery, Store.id == start_date_subquery.c.store_id)
    
    # Filtros
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))
    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    
    # QUIRÚRGICO: Eliminar tiendas sin nombre
    query = query.filter(Store.name != None)
    
    if store_name: query = query.filter(Store.name == store_name)
    query = apply_search(query, search_query)

    results = query.group_by(Store.name, start_date_subquery.c.first_order_date).order_by(desc('total_orders')).all()
    
    return [{"name": row.name, "orders": row.total_orders, "first_seen": row.first_order_date.strftime('%d/%m/%Y') if row.first_order_date else "N/A"} for row in results]

def get_heatmap_data(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None, store_name: Optional[str] = None):
    # FIX: Solo 'delivered' y coordenadas válidas
    query = db.query(Order.latitude, Order.longitude)\
        .filter(Order.current_status == 'delivered')\
        .filter(Order.latitude != None)\
        .filter(Order.latitude != 0)\
        .filter(Order.latitude != 0.0)

    local_created_at = func.timezone('America/Caracas', func.timezone('UTC', Order.created_at))
    local_date = func.date(local_created_at)

    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    results = query.all()
    return [[float(r.latitude), float(r.longitude), 0.6] for r in results]

def calculate_bottlenecks(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None, store_name: Optional[str] = None, search_query: Optional[str] = None):
    # Limites Anti-Zombie
    MAX_STEP_SEC = 21600 

    query = db.query(OrderStatusLog.order_id, OrderStatusLog.status, OrderStatusLog.timestamp, Order.created_at, Order.order_type, Order.current_status).join(Order, OrderStatusLog.order_id == Order.id)
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))

    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    query = apply_search(query, search_query)

    logs = query.order_by(OrderStatusLog.order_id, OrderStatusLog.timestamp).all()
    if not logs: return {"delivery": [], "pickup": []}

    metrics = {
        'Delivery': {'pending':[], 'processing':[], 'confirmed':[], 'driver_assigned':[], 'on_the_way':[], 'delivered_life_time':[], 'canceled_life_time':[]},
        'Pickup': {'pending':[], 'processing':[], 'canceled_life_time':[]}
    }

    orders_data = {}
    for log in logs:
        if log.order_id not in orders_data: orders_data[log.order_id] = {'created_at': log.created_at, 'type': log.order_type, 'current_status': log.current_status, 'logs': []}
        orders_data[log.order_id]['logs'].append(log)

    for oid, data in orders_data.items():
        o_created, o_type, o_status, o_logs = data['created_at'], data['type'], data['current_status'], data['logs']
        
        # 1. Decidir tipo de pedido (Si no está definido, forzamos Delivery)
        o_type = o_type or 'Delivery'
        if o_type not in metrics: continue # Evitar errores si el tipo no existe
        target = metrics[o_type] # AHORA USAMOS PICKUP/DELIVERY

        # 2. Cancelados (Separados)
        if o_status == 'canceled':
            # Buscamos cuándo ocurrió la cancelación
            cancel_log = next((l for l in reversed(o_logs) if l.status == 'canceled'), None)
            if cancel_log:
                life = (cancel_log.timestamp - o_created).total_seconds()
                
                # FILTRO DE OUTLIERS (Datos Atípicos):
                # 1. Ignoramos tiempos negativos o cero.
                # 2. Ignoramos tiempos > 8 horas (28800 seg). 
                #    Si un pedido tardó 8 horas en cancelarse, fue un error administrativo/zombie, 
                #    no un flujo operativo real, y ensucia el promedio.
                if 60 < life < 28800: 
                    target['canceled_life_time'].append(life)
            continue

        # 3. Calcular tiempos por estado
        for i in range(len(o_logs) - 1):
            curr, nxt = o_logs[i], o_logs[i+1]
            if curr.status in target:
                delta = (nxt.timestamp - curr.timestamp).total_seconds()
                if 10 < delta < MAX_STEP_SEC:
                    target[curr.status].append(delta)
    
    # 4. Construir las barras de tiempo
    def build_flow(metric_dict):
        res = []
        total = 0.0
        
        # Orden de estados (Importante)
        steps = ['pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way']
        
        for step in steps:
            if step in metric_dict and metric_dict[step]:
                avg = sum(metric_dict[step]) / len(metric_dict[step])
                res.append({"status": step, "avg_duration_seconds": avg})
                total += avg
        
        # Barra TOTAL Entregado (Calculada)
        if total > 0: res.append({"status": "delivered", "avg_duration_seconds": total})

        # Barra Cancelado (Promedio, por separado)
        if metric_dict.get('canceled_life_time'):
            avg_can = sum(metric_dict['canceled_life_time']) / len(metric_dict['canceled_life_time'])
            res.append({"status": "canceled", "avg_duration_seconds": avg_can})
        
        return res

    return {
        "delivery": build_flow(metrics['Delivery']),
        "pickup": build_flow(metrics['Pickup'])
    } 

    query = db.query(OrderStatusLog.order_id, OrderStatusLog.status, OrderStatusLog.timestamp, Order.created_at, Order.order_type, Order.current_status).join(Order, OrderStatusLog.order_id == Order.id)
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))

    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    query = apply_search(query, search_query)

    logs = query.order_by(OrderStatusLog.order_id, OrderStatusLog.timestamp).all()
    if not logs: return {"delivery": [], "pickup": []}

    metrics = {
        'Delivery': {'pending':[], 'processing':[], 'confirmed':[], 'driver_assigned':[], 'on_the_way':[], 'canceled_life_time':[]},
        'Pickup': {'pending':[], 'processing':[], 'canceled_life_time':[]}
    }

    orders_data = {}
    for log in logs:
        if log.order_id not in orders_data: orders_data[log.order_id] = {'created_at': log.created_at, 'type': log.order_type, 'current_status': log.current_status, 'logs': []}
        orders_data[log.order_id]['logs'].append(log)

    for oid, data in orders_data.items():
        o_created, o_type, o_status, o_logs = data['created_at'], data['type'], data['current_status'], data['logs']
        if o_type not in metrics: continue
        target = metrics[o_type]

        # FIX: Cancelados se acumulan aparte
        if o_status == 'canceled':
            cancel_log = next((l for l in reversed(o_logs) if l.status == 'canceled'), None)
            if cancel_log:
                life = (cancel_log.timestamp - o_created).total_seconds()
                if 0 < life < 172800: target['canceled_life_time'].append(life)
            continue

        for i in range(len(o_logs) - 1):
            curr, nxt = o_logs[i], o_logs[i+1]
            if curr.status in target:
                delta = (nxt.timestamp - curr.timestamp).total_seconds()
                if 10 < delta < MAX_STEP_SEC: target[curr.status].append(delta)

    # FIX: Sumar promedios para el Total Entregado
    def build_flow(metric_dict):
        res = []
        total = 0.0
        steps = ['pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way']
        for step in steps:
            if step in metric_dict and metric_dict[step]:
                avg = sum(metric_dict[step]) / len(metric_dict[step])
                res.append({"status": step, "avg_duration_seconds": avg})
                total += avg
        
        # Barra Total
        if total > 0: res.append({"status": "delivered", "avg_duration_seconds": total})
        
        # Barra Cancelado (Promedio)
        if metric_dict.get('canceled_life_time'):
            avg_can = sum(metric_dict['canceled_life_time']) / len(metric_dict['canceled_life_time'])
            res.append({"status": "canceled", "avg_duration_seconds": avg_can})
        return res

    return {
        "delivery": build_flow(metrics['Delivery']),
        "pickup": build_flow(metrics['Pickup'])
    }

def get_top_customers(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None, store_name: Optional[str] = None, search_query: Optional[str] = None):
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))
    
    # FIX: Evitamos apply_search() para no duplicar el JOIN con Customer
    query = db.query(
        Customer.name, 
        func.count(Order.id).label("total_orders"), 
        func.sum(Order.total_amount).label("total_spent")
    ).join(Order, Order.customer_id == Customer.id).filter(Order.current_status == 'delivered')
    
    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    # Filtro manual
    if search_query:
        query = query.filter(Customer.name.ilike(f"%{search_query}%"))

    all_results = query.group_by(Customer.name).order_by(desc("total_spent")).all()
    
    final_list = []
    for index, row in enumerate(all_results):
        final_list.append({
            "rank": index + 1, 
            "name": row.name or "Cliente Desconocido", 
            "count": row.total_orders, 
            "total_amount": float(row.total_spent or 0)
        })
    return final_list[:20]

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
    query = db.query(
        OrderItem.name,
        func.sum(OrderItem.quantity).label('total_qty'),
        func.sum(OrderItem.total_price).label('total_revenue')
    ).join(Order, OrderItem.order_id == Order.id)

    if start_date: query = query.filter(cast(Order.created_at, Date) >= start_date)
    if end_date: query = query.filter(cast(Order.created_at, Date) <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    if search_query:
        query = query.join(Customer, Order.customer_id == Customer.id, isouter=True).filter(or_(
            OrderItem.name.ilike(f"%{search_query}%"),
            Customer.name.ilike(f"%{search_query}%"),
            Order.external_id.ilike(f"%{search_query}%")
        ))

    query = query.filter(
        OrderItem.unit_price > 0.01,
        ~OrderItem.name.ilike('%obsequio%'),
        ~OrderItem.name.ilike('%bolsa%gopharma%')
    )

    results = query.group_by(OrderItem.name).order_by(desc('total_qty')).limit(10).all()

    return [{
        "name": row.name,
        "quantity": int(row.total_qty),
        "revenue": float(row.total_revenue)
    } for row in results]
