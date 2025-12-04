from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date, or_ # <--- Agregamos or_
from typing import Dict, Any, Optional
from datetime import date
from app.db.base import Order, Store, Customer # <--- Agregamos Customer

def get_main_kpis(
    db: Session, 
    start_date: Optional[date] = None, 
    end_date: Optional[date] = None, 
    store_name: Optional[str] = None,
    search_query: Optional[str] = None # <--- Parámetro Nuevo
) -> Dict[str, Any]:
    
    base_query = db.query(Order)

    # 1. Filtros Básicos
    if start_date:
        base_query = base_query.filter(cast(Order.created_at, Date) >= start_date)
    if end_date:
        base_query = base_query.filter(cast(Order.created_at, Date) <= end_date)
    if store_name:
        base_query = base_query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)

    # 2. FILTRO DE BÚSQUEDA (GLOBAL)
    if search_query:
        # Hacemos Join con Customer (Left Outer por si el pedido no tiene cliente registrado aun)
        base_query = base_query.join(Customer, Order.customer_id == Customer.id, isouter=True)\
            .filter(or_(
                Order.external_id.ilike(f"%{search_query}%"), # ID Pedido
                Customer.name.ilike(f"%{search_query}%")      # Nombre Cliente
            ))

    # 3. Cálculos (Se aplicarán sobre la base filtrada)
    total_orders = base_query.count()
    
    total_revenue = base_query.with_entities(func.sum(Order.total_amount)).scalar() or 0.0
    total_fees = base_query.with_entities(func.sum(Order.delivery_fee)).scalar() or 0.0
    total_coupons = base_query.with_entities(func.sum(Order.coupon_discount)).scalar() or 0.0

    total_gross_delivery = base_query.with_entities(func.sum(func.coalesce(Order.gross_delivery_fee, Order.delivery_fee))).scalar() or 0.0
    
    driver_payout = total_gross_delivery * 0.80
    company_delivery_revenue = total_gross_delivery * 0.20
    
    total_service_fee = base_query.with_entities(func.sum(Order.service_fee)).scalar() or 0.0
    total_company_profit = company_delivery_revenue + total_service_fee

    total_deliveries = base_query.filter(Order.order_type == 'Delivery').count()
    total_pickups = base_query.filter(Order.order_type == 'Pickup').count()
    total_canceled = base_query.filter(Order.current_status == 'canceled').count()

    avg_time_query = base_query.filter(
        Order.current_status == 'delivered',
        Order.order_type == 'Delivery',
        Order.delivery_time_minutes != None
    )
    avg_delivery_minutes = avg_time_query.with_entities(func.avg(Order.delivery_time_minutes)).scalar() or 0.0

    return {
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "total_fees": float(total_fees),
        "total_coupons": float(total_coupons),
        "driver_payout": float(driver_payout),
        "company_profit": float(total_company_profit),
        "total_deliveries": total_deliveries,
        "total_pickups": total_pickups,
        "total_canceled": total_canceled,
        "avg_delivery_minutes": round(float(avg_delivery_minutes), 1)
    }
