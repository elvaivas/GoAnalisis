from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date, or_
from typing import Dict, Any, Optional
from datetime import date, datetime
from app.db.base import Order, Store, Customer

def get_main_kpis(
    db: Session, 
    start_date: Optional[date] = None, 
    end_date: Optional[date] = None, 
    store_name: Optional[str] = None,
    search_query: Optional[str] = None
) -> Dict[str, Any]:
    
    # 1. BASE QUERY
    base_query = db.query(Order)

    if start_date: base_query = base_query.filter(cast(Order.created_at, Date) >= start_date)
    if end_date: base_query = base_query.filter(cast(Order.created_at, Date) <= end_date)
    if store_name: base_query = base_query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    if search_query:
        base_query = base_query.join(Customer, Order.customer_id == Customer.id, isouter=True)\
            .filter(or_(Order.external_id.ilike(f"%{search_query}%"), Customer.name.ilike(f"%{search_query}%")))

    # --- CÁLCULO SEGURO ---
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
        # Contadores
        if o.current_status == 'canceled': 
            count_canceled += 1
            lost_revenue += (o.total_amount or 0.0)
            continue 
        elif o.order_type == 'Delivery': count_deliveries += 1
        elif o.order_type == 'Pickup': count_pickups += 1

        if o.current_status == 'delivered' and o.order_type == 'Delivery' and o.delivery_time_minutes:
            durations_minutes.append(o.delivery_time_minutes)

        # Valores Base (Con validación de tipos)
        total_amt = float(o.total_amount or 0.0)
        delivery_real = float(o.gross_delivery_fee if o.gross_delivery_fee and o.gross_delivery_fee > 0 else (o.delivery_fee or 0.0))
        coupon = float(o.coupon_discount or 0.0)
        prod_price = float(o.product_price or 0.0)
        svc_fee = float(o.service_fee or 0.0)

        # Acumuladores
        total_revenue += total_amt
        total_fees_gross += delivery_real
        total_coupons += coupon

        # Fórmulas
        driver_payout += (delivery_real * 0.80)
        profit_delivery += (delivery_real * 0.20) / 1.16
        
        # Ganancia Servicio
        iva_prod = prod_price * 0.16
        base_service = prod_price + iva_prod + delivery_real + svc_fee
        profit_service += (base_calc * 0.05) / 1.16 if 'base_calc' in locals() else (total_amt * 0.05) / 1.16 # Fallback seguro

        # Ganancia Comisión (Validar que store exista)
        rate = 0.0
        if o.store and o.store.commission_rate:
            rate = float(o.store.commission_rate)
        
        profit_commission += prod_price * (rate / 100.0)

    # Totales Finales
    real_net_profit = (profit_delivery + profit_service + profit_commission) - total_coupons

    # Métricas Usuario
    avg_ticket = (total_revenue / len(orders)) if orders else 0.0
    avg_time = sum(durations_minutes) / len(durations_minutes) if durations_minutes else 0.0
    total_users_historic = db.query(Customer).count()
    unique_customers = {o.customer_id for o in orders if o.customer_id}
    
    new_users_q = db.query(Customer)
    if start_date: new_users_q = new_users_q.filter(cast(Customer.joined_at, Date) >= start_date)
    if end_date: new_users_q = new_users_q.filter(cast(Customer.joined_at, Date) <= end_date)
    
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
