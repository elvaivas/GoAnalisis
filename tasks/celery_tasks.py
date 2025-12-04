import logging
import re
import time
import math
from datetime import datetime
from contextlib import contextmanager
from celery import shared_task
import redis

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.base import Order, Store, Customer, Driver, OrderStatusLog 
from tasks.scraper.order_scraper import OrderScraper 
from tasks.scraper.drone_scraper import DroneScraper 

redis_client = redis.Redis.from_url(settings.REDIS_URL)
logger = logging.getLogger(__name__)

# --- GESTOR DE CONTEXTO ---
@contextmanager
def redis_lock(lock_key: str, expire: int):
    acquired = redis_client.set(lock_key, "true", nx=True, ex=expire)
    try:
        yield acquired
    finally:
        if acquired:
            redis_client.delete(lock_key)

# --- HELPERS ---
def parse_spanish_date(date_str: str):
    if not date_str: return datetime.utcnow()
    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
        'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
        'ene': '01', 'feb': '02', 'mar': '03', 'abr': '04', 'may': '05', 'jun': '06',
        'jul': '07', 'ago': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dic': '12'
    }
    try:
        lower_str = date_str.lower().replace('.', '')
        for mes_nombre, mes_num in month_map.items():
            if mes_nombre in lower_str:
                lower_str = lower_str.replace(mes_nombre, mes_num)
                break
        match = re.search(r'(\d{1,2})\s+(\d{1,2})\s+(\d{4})\s+(\d{1,2}:\d{2})', lower_str)
        if match:
            clean_date_str = f"{match.group(1)} {match.group(2)} {match.group(3)} {match.group(4)}"
            return datetime.strptime(clean_date_str, '%d %m %Y %H:%M')
        raise ValueError("No pattern")
    except Exception:
        return datetime.utcnow()

def parse_duration_to_minutes(duration_str: str):
    if not duration_str: return None
    try:
        hours = 0
        h_match = re.search(r'(\d+)\s*Horas', duration_str, re.IGNORECASE)
        if h_match: hours = int(h_match.group(1))
        minutes = 0
        m_match = re.search(r'(\d+)\s*Minutos', duration_str, re.IGNORECASE)
        if m_match: minutes = int(m_match.group(1))
        seconds = 0
        s_match = re.search(r'(\d+)\s*segundos', duration_str, re.IGNORECASE)
        if s_match: seconds = int(s_match.group(1))
        return round((hours * 60) + minutes + (seconds / 60), 2)
    except: return None

def calculate_distance_km(lat1, lon1, lat2, lon2):
    if not lat1 or not lon1 or not lat2 or not lon2: return 0.0
    try:
        R = 6371 
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        a = math.sin(dLat/2) * math.sin(dLat/2) + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
            math.sin(dLon/2) * math.sin(dLon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return round(R * c, 3)
    except: return 0.0

def save_orders_batch(orders_data: list):
    db = SessionLocal()
    new_count = 0
    updated_count = 0
    try:
        for data in orders_data:
            # 1. Relaciones
            store = None
            if data['store_name']:
                store = db.query(Store).filter(Store.name == data['store_name']).first()
                if not store:
                    store = Store(name=data['store_name'], external_id=f"store_{data['store_name']}")
                    db.add(store); db.commit(); db.refresh(store)
            
            customer = None
            if data['customer_name']:
                customer = db.query(Customer).filter(Customer.name == data['customer_name']).first()
                if not customer:
                    customer = Customer(name=data['customer_name'], external_id=f"cust_{data['customer_name']}")
                    db.add(customer); db.commit(); db.refresh(customer)

            driver = None
            if data['driver_name'] and "N/A" not in data['driver_name']:
                driver = db.query(Driver).filter(Driver.name == data['driver_name']).first()
                if not driver:
                    driver = Driver(name=data['driver_name'], external_id=f"driver_{data['driver_name']}")
                    db.add(driver); db.commit(); db.refresh(driver)

            # 2. Pedido
            order = db.query(Order).filter(Order.external_id == data['external_id']).first()
            created_at_dt = parse_spanish_date(data.get('created_at_text', ''))
            minutes_calc = parse_duration_to_minutes(data['duration'])

            if not order:
                new_order = Order(
                    external_id=data['external_id'],
                    created_at=created_at_dt,
                    total_amount=data['total_amount'],
                    delivery_fee=data['delivery_fee'],
                    current_status=data['status'],
                    order_type=data['order_type'],
                    duration=data['duration'],
                    delivery_time_minutes=minutes_calc,
                    store_id=store.id if store else None,
                    customer_id=customer.id if customer else None,
                    driver_id=driver.id if driver else None
                )
                db.add(new_order); db.commit(); db.refresh(new_order)
                db.add(OrderStatusLog(order_id=new_order.id, status=data['status'], timestamp=datetime.utcnow()))
                new_count += 1
            else:
                if order.current_status != data['status']:
                    logger.info(f"🔄 Cambio #{order.external_id}: {order.current_status} -> {data['status']}")
                    db.add(OrderStatusLog(order_id=order.id, status=data['status'], timestamp=datetime.utcnow()))
                    order.current_status = data['status']
                    updated_count += 1
                
                if order.order_type != data['order_type'] and data['order_type'] is not None:
                    order.order_type = data['order_type']

                order.duration = data['duration']
                if minutes_calc: order.delivery_time_minutes = minutes_calc
                if driver: order.driver_id = driver.id

        db.commit()
        if new_count or updated_count:
            logger.info(f"✅ Batch: Nuevos={new_count}, Cambios={updated_count}")
    except Exception as e:
        db.rollback()
        logger.error(f"🔥 Error batch: {e}")
    finally:
        db.close()

# --- TAREAS ---

@shared_task(bind=True)
def backfill_historical_data(self):
    key = "celery_lock_backfill_historical_data"
    with redis_lock(key, 7200) as acquired:
        if not acquired: return "Task running"
        logger.info("🚀 Iniciando Backfill V2.1...")
        scraper = OrderScraper()
        try:
            if not scraper.login(): raise Exception("Login fallido")
            scraper.scrape_orders(limit=7000, batch_callback=save_orders_batch)
            return "Backfill Finalizado"
        except Exception as e:
            logger.error(f"Error backfill: {e}")
        finally:
            if scraper: scraper.close_driver()

@shared_task(bind=True)
def monitor_active_orders(self):
    key = "celery_lock_monitor_active_orders"
    with redis_lock(key, 55) as acquired:
        if not acquired: return "Monitor overlap"
        logger.info("📡 Monitor Live: Escaneo Inicial...")
        scraper = OrderScraper()
        try:
            if not scraper.login(): return
            orders = scraper.scrape_orders(limit=50, batch_callback=save_orders_batch)
            active_count = sum(1 for o in orders if o['status'] not in ['delivered', 'canceled'])
            logger.info(f"📡 Activos: {active_count}")
            if active_count > 0:
                logger.info("⏳ Esperando 25s...")
                time.sleep(25)
                logger.info("📡 Monitor Live: Re-escaneo...")
                scraper.scrape_orders(limit=50, batch_callback=save_orders_batch)
                enrich_missing_data.delay()
            return "Monitor Finalizado"
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        finally:
            if scraper: scraper.close_driver()

@shared_task(bind=True)
def enrich_missing_data(self):
    key = "celery_lock_drone_enrichment"
    with redis_lock(key, 300) as acquired:
        if not acquired: return "Drone busy"
        
        db = SessionLocal()
        drone = DroneScraper()
        processed = 0
        BATCH_SIZE = 50 
        
        try:
            # 1. Cancelados
            missing_reasons = db.query(Order).filter(Order.current_status == 'canceled', Order.cancellation_reason == None).limit(BATCH_SIZE).all()
            if missing_reasons:
                if not drone.login(): raise Exception("Login fail")
                for order in missing_reasons:
                    data = drone.scrape_detail(order.external_id, mode='reason')
                    order.cancellation_reason = data.get("cancellation_reason", "Sin especificar")
                    # Finanzas
                    if "service_fee" in data: order.service_fee = data["service_fee"]
                    if "coupon_discount" in data: order.coupon_discount = data["coupon_discount"]
                    if "tips" in data: order.tips = data["tips"]
                    if "real_delivery_fee" in data: order.gross_delivery_fee = data["real_delivery_fee"]
                    
                    # CLIENTE (Teléfono) - CORREGIDO IDENTACIÓN AQUÍ
                    if "customer_phone" in data and order.customer:
                        order.customer.phone = data["customer_phone"]

                    processed += 1
                db.commit()

            # 2. Coordenadas y Tipo
            if processed < BATCH_SIZE:
                limit_coords = BATCH_SIZE - processed
                missing_coords = db.query(Order).filter(
                    Order.current_status == 'delivered', 
                    Order.order_type == 'Delivery', 
                    Order.latitude == None
                ).limit(limit_coords).all()
                
                if missing_coords:
                    if not drone.driver: drone.login()
                    for order in missing_coords:
                        data = drone.scrape_detail(order.external_id, mode='coords')
                        
                        if "customer_lat" in data:
                            order.latitude = data["customer_lat"]
                            order.longitude = data["customer_lng"]
                        else:
                            order.latitude = 0.0
                            order.longitude = 0.0
                            logger.warning(f"⚠️ Sin mapa cliente: {order.external_id}")

                        if "store_lat" in data and order.store and order.store.latitude is None:
                            order.store.latitude = data["store_lat"]
                            order.store.longitude = data["store_lng"]

                        # Cálculo KM
                        if order.latitude and order.latitude != 0.0 and order.store and order.store.latitude:
                            dist = calculate_distance_km(order.store.latitude, order.store.longitude, order.latitude, order.longitude)
                            order.distance_km = dist
                            if dist < 0.1: order.order_type = "Pickup"
                            else: order.order_type = "Delivery"

                        # Finanzas
                        if "service_fee" in data: order.service_fee = data["service_fee"]
                        if "coupon_discount" in data: order.coupon_discount = data["coupon_discount"]
                        if "tips" in data: order.tips = data["tips"]
                        if "real_delivery_fee" in data: order.gross_delivery_fee = data["real_delivery_fee"]
                        
                        # CLIENTE (Teléfono) - CORREGIDO
                        if "customer_phone" in data and order.customer:
                            order.customer.phone = data["customer_phone"]

                        processed += 1
                    db.commit()

            if processed > 0:
                enrich_missing_data.apply_async(countdown=2)
                return f"Ciclo: {processed}"
            return "All Done"

        except Exception as e:
            logger.error(f"Drone error: {e}")
        finally:
            if drone: drone.close_driver()
            db.close()
