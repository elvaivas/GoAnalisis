import re
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date, or_
from typing import Dict, Any, Optional
from datetime import date, datetime, timedelta
from app.db.base import Order, Store, Customer


def _parse_duration_to_minutes(s: str) -> float:
    if not s or s == "--":
        return 0.0
    try:
        minutes = 0.0
        s = s.lower()
        # Busca horas (h, hr, hora)
        h_match = re.search(r"(\d+)\s*(?:h|hr|hora)", s)
        if h_match:
            minutes += float(h_match.group(1)) * 60
        # Busca minutos (m, min, minuto)
        m_match = re.search(r"(\d+)\s*(?:m|min)", s)
        if m_match:
            minutes += float(m_match.group(1))
        return minutes
    except:
        return 0.0


def get_main_kpis(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    store_name: Optional[str] = None,
    search_query: Optional[str] = None,
) -> Dict[str, Any]:

    # OPTIMIZACIÓN: Cargar logs y tienda en la misma consulta para evitar el problema N+1
    base_query = db.query(Order).options(
        joinedload(Order.status_logs), joinedload(Order.store)
    )
    # --- CORRECCIÓN DE ZONA HORARIA (VENEZUELA) ---
    local_created_at = func.timezone(
        "America/Caracas", func.timezone("UTC", Order.created_at)
    )
    local_date = func.date(local_created_at)

    # --- FILTROS ---
    if start_date:
        base_query = base_query.filter(local_date >= start_date)
    if end_date:
        base_query = base_query.filter(local_date <= end_date)

    if store_name:
        base_query = base_query.join(Store, Order.store_id == Store.id).filter(
            Store.name == store_name
        )

    if search_query:
        base_query = base_query.join(
            Customer, Order.customer_id == Customer.id, isouter=True
        ).filter(
            or_(
                Order.external_id.ilike(f"%{search_query}%"),
                Customer.name.ilike(f"%{search_query}%"),
            )
        )

    # --- CÁLCULO DE DATOS ---
    orders = base_query.all()

    # Inicialización de Acumuladores
    total_revenue = 0.0
    total_fees_gross = 0.0
    total_coupons = 0.0
    total_service_fee_accum = 0.0

    total_delivery_fees_only = 0.0  # KPI Costo Envío

    driver_payout = 0.0
    profit_delivery = 0.0
    profit_service = 0.0
    profit_commission = 0.0

    # Contadores
    count_deliveries = 0
    count_pickups = 0
    count_canceled = 0
    lost_revenue = 0.0

    durations_minutes = []

    for o in orders:
        # 1. Cancelados
        if o.current_status == "canceled":
            count_canceled += 1
            lost_revenue += o.total_amount or 0.0
            continue

        # Casting seguro de tipo
        raw = o.order_type
        o_type_str = raw.value if hasattr(raw, "value") else str(raw)
        if not o_type_str or o_type_str == "None":
            o_type_str = "Delivery"

        # 2. Valores Base (Sanitizados)
        total_amt = float(o.total_amount or 0.0)
        delivery_real = float(
            o.gross_delivery_fee
            if o.gross_delivery_fee and o.gross_delivery_fee > 0
            else (o.delivery_fee or 0.0)
        )
        coupon = float(o.coupon_discount or 0.0)
        prod_price = float(o.product_price or 0.0)
        svc_fee = float(o.service_fee or 0.0)

        # 3. Lógica de Conteo y Tiempos
        if o_type_str == "Delivery":
            count_deliveries += 1
            total_delivery_fees_only += delivery_real

            # --- CÁLCULO OPTIMIZADO (POST-MIGRACIÓN) ---
            # Como ya corrimos el script 'migrate_times.py', confiamos en la DB.
            # Solo si la DB falla (es 0), intentamos calcular al vuelo.

            val = o.delivery_time_minutes or 0.0

            if val == 0 and o.duration:
                val = _parse_duration_to_minutes(o.duration)

            if val > 0:
                durations_minutes.append(val)
            # -------------------------------------------

        elif o_type_str == "Pickup":
            count_pickups += 1

        # 4. Acumuladores Globales
        total_revenue += total_amt
        total_fees_gross += delivery_real
        total_coupons += coupon
        total_service_fee_accum += svc_fee

        # --- FÓRMULAS FINANCIERAS ---
        driver_payout += delivery_real * 0.80
        profit_delivery += (delivery_real * 0.20) / 1.16

        iva_prod = prod_price * 0.16
        base_service = prod_price + iva_prod + delivery_real + svc_fee
        profit_service += (base_service * 0.05) / 1.16

        rate = 0.0
        if o.store and o.store.commission_rate:
            rate = float(o.store.commission_rate)
        profit_commission += prod_price * (rate / 100.0)

    # --- RESULTADOS FINALES ---
    real_net_profit = (
        profit_delivery + profit_service + profit_commission
    ) - total_coupons

    avg_time = (
        sum(durations_minutes) / len(durations_minutes) if durations_minutes else 0.0
    )

    valid_orders_count = count_deliveries + count_pickups

    avg_ticket = (total_revenue / valid_orders_count) if valid_orders_count > 0 else 0.0
    avg_delivery_fee_value = (
        (total_delivery_fees_only / count_deliveries) if count_deliveries > 0 else 0.0
    )
    avg_service_fee = (
        (total_service_fee_accum / valid_orders_count)
        if valid_orders_count > 0
        else 0.0
    )

    total_users_historic = db.query(Customer).count()
    unique_customers = {o.customer_id for o in orders if o.customer_id}

    local_joined_at = func.date(Customer.joined_at)
    new_users_q = db.query(Customer)
    if start_date:
        new_users_q = new_users_q.filter(local_joined_at >= start_date)
    if end_date:
        new_users_q = new_users_q.filter(local_joined_at <= end_date)

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
        "avg_delivery_ticket": round(avg_delivery_fee_value, 2),
        "avg_service_fee": round(avg_service_fee, 2),
        "total_users_historic": total_users_historic,
        "active_users_period": len(unique_customers),
        "new_users_registered": new_users_q.count(),
    }
