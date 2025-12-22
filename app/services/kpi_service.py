from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date, or_
from typing import Dict, Any, Optional
from datetime import date
from app.db.base import Order, Store, Customer

def get_main_kpis(
    db: Session, 
    start_date: Optional[date] = None, 
    end_date: Optional[date] = None, 
    store_name: Optional[str] = None,
    search_query: Optional[str] = None
) -> Dict[str, Any]:
    
    base_query = db.query(Order)

    # --- CORRECCIÓN DE ZONA HORARIA (VENEZUELA) ---
    # Convertimos la fecha guardada (UTC) a America/Caracas antes de extraer el día
    local_created_at = func.timezone('America/Caracas', func.timezone('UTC', Order.created_at))
    local_date = func.date(local_created_at)

    # --- FILTROS ---
    if start_date:
        base_query = base_query.filter(local_date >= start_date)
    if end_date:
        base_query = base_query.filter(local_date <= end_date)
    
    if store_name:
        base_query = base_query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    if search_query:
        base_query = base_query.join(Customer, Order.customer_id == Customer.id, isouter=True)\
            .filter(or_(Order.external_id.ilike(f"%{search_query}%"), Customer.name.ilike(f"%{search_query}%")))

    # --- CÁLCULO DE DATOS (Igual que antes) ---
    orders = base_query.all()
    
    total_revenue = 0.0
    total_fees_gross = 0.0
    total_coupons = 0.0
    driver_payout = 0.0
    profit_delivery = 0.0
    profit_service = 0.0
    profit_commission = 0.0

    count_deliveries = 0
    count_pickups = 0
    count_canceled = 0
    lost_revenue = 0.0
    
    durations_minutes = []

    for o in orders:
        if o.current_status == 'canceled': 
            count_canceled += 1
            lost_revenue += (o.total_amount or 0.0)
            continue 
        elif o.order_type == 'Delivery': count_deliveries += 1
        elif o.order_type == 'Pickup': count_pickups += 1

        if o.current_status == 'delivered' and o.order_type == 'Delivery' and o.delivery_time_minutes:
            durations_minutes.append(o.delivery_time_minutes)

        total_amt = float(o.total_amount or 0.0)
        delivery_real = float(o.gross_delivery_fee if o.gross_delivery_fee and o.gross_delivery_fee > 0 else (o.delivery_fee or 0.0))
        coupon = float(o.coupon_discount or 0.0)
        prod_price = float(o.product_price or 0.0)
        svc_fee = float(o.service_fee or 0.0)

        total_revenue += total_amt
        total_fees_gross += delivery_real
        total_coupons += coupon

        # Fórmulas
        driver_payout += (delivery_real * 0.80)
        profit_delivery += (delivery_real * 0.20) / 1.16
        
        iva_prod = prod_price * 0.16
        base_service = prod_price + iva_prod + delivery_real + svc_fee
        profit_service += (base_service * 0.05) / 1.16

        rate = 0.0
        if o.store and o.store.commission_rate:
            rate = float(o.store.commission_rate)
        
        profit_commission += prod_price * (rate / 100.0)

    real_net_profit = (profit_delivery + profit_service + profit_commission) - total_coupons
    
    avg_ticket = (total_revenue / len(orders)) if orders else 0.0
    avg_time = sum(durations_minutes) / len(durations_minutes) if durations_minutes else 0.0

    # Usuarios (Total Histórico y Nuevos en Periodo)
    total_users_historic = db.query(Customer).count()
    
    # Nuevos usuarios (Usando Timezone también en joined_at)
    local_joined_at = func.date(func.timezone('America/Caracas', func.timezone('UTC', Customer.joined_at)))
    new_users_q = db.query(Customer)
    if start_date: new_users_q = new_users_q.filter(local_joined_at >= start_date)
    if end_date: new_users_q = new_users_q.filter(local_joined_at <= end_date)
    
    unique_customers = {o.customer_id for o in orders if o.customer_id}

    return {
        "total_orders": len(orders),
        "total_revenue": round(total_revenue, 2),
        "total_fees": round(total_fees_gross, 2),
        "total_coupons": round(total_coupons, 2),
        "driver_payout": round(driver_payout, 2),
        "company_profit": round(real_net_profit, 2),
        "total_deliveries": count_deliveries,
        "total_pickups": count_pickups,
        "total_canceled": count_canceled,
        "lost_revenue": round(lost_revenue, 2),
        "avg_delivery_minutes": round(avg_time, 1),
        "avg_ticket": round(avg_ticket, 2),
        "total_users_historic": total_users_historic,
        "active_users_period": len(unique_customers),
        "new_users_registered": new_users_q.count()
    }
