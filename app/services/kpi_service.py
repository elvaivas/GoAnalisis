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
    search_query: Optional[str] = None
) -> Dict[str, Any]:
    
    base_query = db.query(Order)

    # --- FILTROS ---
    if start_date:
        base_query = base_query.filter(cast(Order.created_at, Date) >= start_date)
    if end_date:
        base_query = base_query.filter(cast(Order.created_at, Date) <= end_date)
    if store_name:
        base_query = base_query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    if search_query:
        base_query = base_query.join(Customer, Order.customer_id == Customer.id, isouter=True)\
            .filter(or_(Order.external_id.ilike(f"%{search_query}%"), Customer.name.ilike(f"%{search_query}%")))

    # --- CONTADORES ---
    total_orders = base_query.count()
    total_deliveries = base_query.filter(Order.order_type == 'Delivery').count()
    total_pickups = base_query.filter(Order.order_type == 'Pickup').count()
    total_canceled = base_query.filter(Order.current_status == 'canceled').count()

    # --- FINANZAS (CÁLCULO REAL) ---
    
    # 1. Movimiento Total (GMV)
    total_revenue = base_query.filter(Order.current_status == 'delivered')\
        .with_entities(func.sum(Order.total_amount)).scalar() or 0.0

    # 2. DINERO PERDIDO (NUEVO KPI)
    # Suma de montos de pedidos cancelados
    lost_revenue = base_query.filter(Order.current_status == 'canceled')\
        .with_entities(func.sum(Order.total_amount)).scalar() or 0.0
    
    # 3. Base Delivery (Precio real del viaje, pagado o no)
    total_gross_delivery = base_query.with_entities(func.sum(func.coalesce(Order.gross_delivery_fee, Order.delivery_fee))).scalar() or 0.0
    
    # 4. Costo Cupones (Inversión de la empresa)
    total_coupons = base_query.with_entities(func.sum(Order.coupon_discount)).scalar() or 0.0

    # 5. Service Fee (Ingreso administrativo)
    total_service_fee = base_query.with_entities(func.sum(Order.service_fee)).scalar() or 0.0

    # 6. REPARTICIÓN
    driver_payout = total_gross_delivery * 0.80  # El motorizado siempre cobra su 80% del valor real
    company_share_delivery = total_gross_delivery * 0.20 # El 20% teórico de la empresa

    # 7. GANANCIA NETA REAL (REAL PROFIT)
    # (Lo que le toca a la empresa + Service Fee) - (Lo que la empresa pagó en cupones)
    real_net_profit = (company_share_delivery + total_service_fee) - total_coupons

    # --- TIEMPOS ---
    avg_delivery_minutes = base_query.filter(
        Order.current_status == 'delivered',
        Order.order_type == 'Delivery',
        Order.delivery_time_minutes != None
    ).with_entities(func.avg(Order.delivery_time_minutes)).scalar() or 0.0

    return {
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "lost_revenue": float(lost_revenue),
        "total_fees": float(total_gross_delivery), # Mostramos el valor bruto del delivery generado
        "total_coupons": float(total_coupons),
        "driver_payout": float(driver_payout),
        "company_profit": float(real_net_profit), # Puede ser negativo
        "total_deliveries": total_deliveries,
        "total_pickups": total_pickups,
        "total_canceled": total_canceled,
        "avg_delivery_minutes": round(float(avg_delivery_minutes), 1)
    }
