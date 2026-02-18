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
        text = s.lower().replace("á", "a").strip()

        h_match = re.search(r"(\d+)\s*(?:horas?|hours?|hrs?|h)", text)
        m_match = re.search(r"(\d+)\s*(?:minutos?|minutes?|mins?|min|m)", text)

        if h_match:
            minutes += float(h_match.group(1)) * 60

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

    # OPTIMIZACIÓN: Eager Loading
    base_query = db.query(Order).options(
        joinedload(Order.status_logs), joinedload(Order.store)
    )

    # --- CORRECCIÓN DE ZONA HORARIA (PEDIDOS) ---
    # Los pedidos SÍ tienen hora exacta, así que mantenemos la lógica VET
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

    orders = base_query.all()

    # Inicialización
    total_revenue = 0.0
    total_fees_gross = 0.0
    total_coupons = 0.0
    total_service_fee_accum = 0.0
    total_delivery_fees_only = 0.0
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
        if o.current_status == "canceled":
            count_canceled += 1
            lost_revenue += float(o.total_amount or 0.0)
            continue

        raw = o.order_type
        o_type_clean = str(raw.value if hasattr(raw, "value") else raw).lower().strip()
        if not o_type_clean or o_type_clean == "none":
            o_type_clean = "delivery"

        total_amt = float(o.total_amount or 0.0)
        delivery_real = float(
            o.gross_delivery_fee
            if o.gross_delivery_fee and o.gross_delivery_fee > 0
            else (o.delivery_fee or 0.0)
        )
        coupon = float(o.coupon_discount or 0.0)
        prod_price = float(o.product_price or 0.0)
        svc_fee = float(o.service_fee or 0.0)

        if "pickup" in o_type_clean:
            count_pickups += 1
        else:
            count_deliveries += 1
            total_delivery_fees_only += delivery_real
            if o.current_status == "delivered":
                duration_val = 0.0
                if o.duration:
                    duration_val = _parse_duration_to_minutes(o.duration)
                if (
                    duration_val == 0
                    and o.delivery_time_minutes
                    and o.delivery_time_minutes > 0
                ):
                    duration_val = float(o.delivery_time_minutes)
                if duration_val == 0:
                    done_log = next(
                        (l for l in o.status_logs if l.status == "delivered"), None
                    )
                    if done_log and o.created_at:
                        created_utc = o.created_at + timedelta(hours=4)
                        total_seconds = (
                            done_log.timestamp - created_utc
                        ).total_seconds()
                        if total_seconds > 0:
                            duration_val = int(total_seconds / 60)
                if 0 < duration_val < 600:
                    durations_minutes.append(duration_val)

        total_revenue += total_amt
        total_fees_gross += delivery_real
        total_coupons += coupon
        total_service_fee_accum += svc_fee
        driver_payout += delivery_real * 0.80
        profit_delivery += (delivery_real * 0.20) / 1.16
        iva_prod = prod_price * 0.16
        base_service = prod_price + iva_prod + delivery_real + svc_fee
        profit_service += (base_service * 0.05) / 1.16
        rate = 0.0
        if o.store and o.store.commission_rate:
            rate = float(o.store.commission_rate)
        profit_commission += prod_price * (rate / 100.0)

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

    # --- CORRECCIÓN QUIRÚRGICA AQUÍ ---
    # El Scraper guarda 'joined_at' como fecha sin hora (00:00:00).
    # Si aplicamos timezone("America/Caracas"), restamos 4h y retrocedemos al día anterior.
    # SOLUCIÓN: Usamos cast directo a Date.
    local_joined_at = cast(Customer.joined_at, Date)

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
