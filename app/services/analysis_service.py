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
    start_date_subquery = db.query(Order.store_id, func.min(Order.created_at).label('first_order_date')).group_by(Order.store_id).subquery()
    
    query = db.query(
        Store.name, 
        func.count(Order.id).label('total_orders'), 
        start_date_subquery.c.first_order_date
    ).join(Order, Order.store_id == Store.id).outerjoin(start_date_subquery, Store.id == start_date_subquery.c.store_id)
    
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))
    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    
    if store_name: query = query.filter(Store.name == store_name)
    query = apply_search(query, search_query)

    results = query.group_by(Store.name, start_date_subquery.c.first_order_date).order_by(desc('total_orders')).all()
    return [{"name": row.name or "Tienda Desconocida", "orders": row.total_orders, "first_seen": row.first_order_date.strftime('%d/%m/%Y') if row.first_order_date else "N/A"} for row in results]

def calculate_bottlenecks(
    db: Session, 
    start_date: Optional[date] = None, 
    end_date: Optional[date] = None,
    store_name: Optional[str] = None, 
    search_query: Optional[str] = None
):
    """
    Calcula Cuellos de Botella (Lógica V5.4 - Suma de Promedios).
    - Delivery Total = Suma(Avg Pendiente + Avg Prep + Avg Asignado + Avg Camino).
    - Pickup Total = Suma(Avg Pendiente + Avg Prep).
    - Cancelado = Promedio del tiempo de vida de los pedidos cancelados.
    """
    # 1. Definición de Límites (Anti-Zombie)
    MAX_STEP_SEC = 21600 # 6 Horas máx por paso (si es más, es error de data)

    # 2. Query
    query = db.query(
        OrderStatusLog.order_id, 
        OrderStatusLog.status, 
        OrderStatusLog.timestamp,
        Order.created_at,
        Order.order_type,
        Order.current_status
    ).join(Order, OrderStatusLog.order_id == Order.id)

    # 3. Filtros
    local_created_at = func.timezone('America/Caracas', func.timezone('UTC', Order.created_at))
    local_date = func.date(local_created_at)

    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    query = apply_search(query, search_query)

    logs = query.order_by(OrderStatusLog.order_id, OrderStatusLog.timestamp).all()

    if not logs: 
        return {"delivery": [], "pickup": []}

    # 4. Buckets para acumular [listas de segundos]
    # Usamos listas separadas para cada paso específico
    metrics = {
        'Delivery': {
            'pending': [], 'processing': [], 'confirmed': [], 'driver_assigned': [], 'on_the_way': [], 
            'canceled_life_time': [] # Tiempo de vida de los cancelados
        },
        'Pickup': {
            'pending': [], 'processing': [], 
            'canceled_life_time': []
        }
    }

    orders_data = {}
    for log in logs:
        if log.order_id not in orders_data:
            orders_data[log.order_id] = {
                'created_at': log.created_at,
                'type': log.order_type,
                'current_status': log.current_status,
                'logs': []
            }
        orders_data[log.order_id]['logs'].append(log)

    # 5. Procesamiento Lógico
    for oid, data in orders_data.items():
        o_created = data['created_at']
        o_type = data['type'] 
        o_status = data['current_status']
        o_logs = data['logs']

        if o_type not in metrics: continue
        target_metrics = metrics[o_type]

        # CASO A: Pedido Cancelado (Calculamos cuánto tiempo se perdió)
        if o_status == 'canceled':
            # Buscamos cuándo ocurrió la cancelación
            cancel_log = next((l for l in reversed(o_logs) if l.status == 'canceled'), None)
            if cancel_log:
                life_time = (cancel_log.timestamp - o_created).total_seconds()
                # Filtro: Ignorar cancelaciones de más de 2 días (zombies)
                if 0 < life_time < 172800:
                    target_metrics['canceled_life_time'].append(life_time)
            # Nota: Los cancelados NO suman a los promedios de pasos exitosos para no ensuciarlos
            continue 

        # CASO B: Pedidos Exitosos o En Curso (Calculamos pasos intermedios)
        for i in range(len(o_logs) - 1):
            current = o_logs[i]
            next_l = o_logs[i+1]
            status = current.status

            # Solo guardamos si el paso existe en nuestra estructura (Whitelist)
            if status in target_metrics:
                delta = (next_l.timestamp - current.timestamp).total_seconds()
                # Filtro Zombie (6h)
                if 10 < delta < MAX_STEP_SEC:
                    target_metrics[status].append(delta)

    # 6. Construcción de Resultados (SUMA DE PROMEDIOS)
    
    def build_flow_result(metric_dict):
        result_list = []
        total_process_time = 0.0

        # Pasos secuenciales (El orden importa para la suma)
        # Definimos el orden lógico de visualización
        steps_order = ['pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way']
        
        for step in steps_order:
            if step in metric_dict and metric_dict[step]:
                # Calculamos promedio de este paso
                avg = sum(metric_dict[step]) / len(metric_dict[step])
                result_list.append({"status": step, "avg_duration_seconds": avg})
                
                # Sumamos al total acumulado
                total_process_time += avg
        
        # Agregamos la barra de "Entregado" que es la SUMA de los anteriores
        if total_process_time > 0:
            result_list.append({
                "status": "delivered", 
                "avg_duration_seconds": total_process_time
            })

        # Agregamos la barra de "Cancelado" (Promedio independiente)
        if metric_dict.get('canceled_life_time'):
            avg_cancel = sum(metric_dict['canceled_life_time']) / len(metric_dict['canceled_life_time'])
            result_list.append({
                "status": "canceled",
                "avg_duration_seconds": avg_cancel
            })
            
        return result_list

    return {
        "delivery": build_flow_result(metrics['Delivery']),
        "pickup": build_flow_result(metrics['Pickup'])
    }

def get_top_customers(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None, store_name: Optional[str] = None, search_query: Optional[str] = None):
    # Filtro fecha local
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))
    
    # query BASE ya incluye Customer implícitamente en el select y join
    query = db.query(
        Customer.name, 
        func.count(Order.id).label("total_orders"), 
        func.sum(Order.total_amount).label("total_spent")
    ).join(Order, Order.customer_id == Customer.id).filter(Order.current_status == 'delivered')
    
    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    # FIX ERROR 500: No usar apply_search() aquí porque causa DOBLE JOIN con Customer.
    # Aplicamos el filtro manualmente sobre la tabla Customer ya unida.
    if search_query:
        term = f"%{search_query}%"
        # Filtramos por nombre de cliente directamente
        query = query.filter(Customer.name.ilike(term))

    all_results = query.group_by(Customer.name).order_by(desc("total_spent")).all()
    
    final_list = []
    
    # Procesamiento
    for index, row in enumerate(all_results):
        rank = index + 1
        name = row.name or "Cliente Desconocido"
        
        final_list.append({
            "rank": rank, 
            "name": name, 
            "count": row.total_orders, 
            "total_amount": float(row.total_spent or 0)
        })
    
    # Paginación manual simple (Top 20)
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
