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
    
    # --- 1. CONSTRUCCIÓN DE LA CONSULTA ---
    base_query = db.query(Order)

    if start_date: base_query = base_query.filter(cast(Order.created_at, Date) >= start_date)
    if end_date: base_query = base_query.filter(cast(Order.created_at, Date) <= end_date)
    if store_name: base_query = base_query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    
    if search_query:
        base_query = base_query.join(Customer, Order.customer_id == Customer.id, isouter=True)\
            .filter(or_(Order.external_id.ilike(f"%{search_query}%"), Customer.name.ilike(f"%{search_query}%")))

    # --- 2. CÁLCULO FINANCIERO DETALLADO (Iterando) ---
    # Traemos los objetos para aplicar las fórmulas complejas
    orders = base_query.all()
    
    total_revenue = 0.0
    total_fees_gross = 0.0
    total_coupons = 0.0
    
    driver_payout = 0.0
    
    # Los 3 pilares de la ganancia
    profit_delivery = 0.0
    profit_service = 0.0
    profit_commission = 0.0

    count_deliveries = 0
    count_pickups = 0
    count_canceled = 0
    lost_revenue = 0.0
    
    durations_minutes = []

    for o in orders:
        # Contadores básicos
        if o.current_status == 'canceled': 
            count_canceled += 1
            lost_revenue += (o.total_amount or 0.0)
            # Los cancelados NO suman a la ganancia
            continue 
        elif o.order_type == 'Delivery': count_deliveries += 1
        elif o.order_type == 'Pickup': count_pickups += 1

        if o.current_status == 'delivered' and o.order_type == 'Delivery' and o.delivery_time_minutes:
            durations_minutes.append(o.delivery_time_minutes)

        # --- EXTRACCIÓN DE VALORES ---
        total_amt = o.total_amount or 0.0
        # Delivery Bruto (Lo que vale el viaje, no lo que pagó el cliente)
        delivery_real = o.gross_delivery_fee if o.gross_delivery_fee > 0 else (o.delivery_fee or 0.0)
        coupon = o.coupon_discount or 0.0
        prod_price = o.product_price or 0.0
        svc_fee = o.service_fee or 0.0 # Tarifa de servicio base (ej: 0.375)

        # Acumuladores Globales
        total_revenue += total_amt
        total_fees_gross += delivery_real
        total_coupons += coupon

        # --- FÓRMULAS DE GANANCIA (SEGÚN TUS INSTRUCCIONES) ---

        # 1. GANANCIA DELIVERY (20% del valor del delivery, entre 1.16)
        # El 80% va al motorizado
        driver_payout += (delivery_real * 0.80)
        profit_delivery += (delivery_real * 0.20) / 1.16

        # 2. GANANCIA SERVICIO (5% del Total Bruto, entre 1.16)
        # Fórmula: (Producto + IVA(16%) + Delivery + ServiceFeeBase) * 5% / 1.16
        # IVA del producto
        iva_prod = prod_price * 0.16
        # Base imponible total
        base_calc = prod_price + iva_prod + delivery_real + svc_fee
        
        profit_service += (base_calc * 0.05) / 1.16

        # 3. GANANCIA COMISIÓN ALIADO (Producto * %)
        # Obtenemos % de la tienda (o 0 si no se ha scrapeado)
        rate = o.store.commission_rate if o.store and o.store.commission_rate else 0.0
        profit_commission += prod_price * (rate / 100.0)

    # --- RESULTADOS FINALES ---
    
    # Ganancia Neta = Suma de Ganancias - Inversión en Cupones
    company_net_profit = (profit_delivery + profit_service + profit_commission) - total_coupons

    # Promedios
    avg_ticket = (total_revenue / len(orders)) if orders else 0.0
    avg_time = sum(durations_minutes) / len(durations_minutes) if durations_minutes else 0.0

    # Usuarios
    total_users_historic = db.query(Customer).count()
    
    # Nuevos usuarios en el periodo (usando joined_at)
    new_users_q = db.query(Customer)
    if start_date: new_users_q = new_users_q.filter(cast(Customer.joined_at, Date) >= start_date)
    if end_date: new_users_q = new_users_q.filter(cast(Customer.joined_at, Date) <= end_date)
    new_users_count = new_users_q.count()
    
    # Usuarios Activos (Únicos que compraron)
    active_users = len(set(o.customer_id for o in orders if o.customer_id))

    return {
        "total_orders": len(orders),
        "total_revenue": round(total_revenue, 2),
        "total_fees": round(total_fees_gross, 2),
        "total_coupons": round(total_coupons, 2),
        
        "driver_payout": round(driver_payout, 2),
        "company_profit": round(company_net_profit, 2),
        
        "total_deliveries": count_deliveries,
        "total_pickups": count_pickups,
        "total_canceled": count_canceled,
        "lost_revenue": round(lost_revenue, 2),
        
        "avg_delivery_minutes": round(avg_time, 1),
        "avg_ticket": round(avg_ticket, 2),
        
        "total_users_historic": total_users_historic,
        "active_users_period": active_users,
        "new_users_registered": new_users_count
    }
