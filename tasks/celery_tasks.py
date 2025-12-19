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
# IMPORTANTE: Asegúrate de que este archivo exista
from tasks.scraper.order_scraper import OrderScraper 
from tasks.scraper.drone_scraper import DroneScraper 
from tasks.scraper.customer_scraper import CustomerScraper 

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
    month_map = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12','ene':'01','feb':'02','mar':'03','abr':'04','may':'05','jun':'06','jul':'07','ago':'08','sep':'09','oct':'10','nov':'11','dic':'12'}
    try:
        lower_str = date_str.lower().replace('.', '')
        for m, n in month_map.items(): 
            if m in lower_str: lower_str = lower_str.replace(m, n); break
        match = re.search(r'(\d{1,2})\s+(\d{1,2})\s+(\d{4})\s+(\d{1,2}:\d{2})', lower_str)
        if match: return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)} {match.group(4)}", '%d %m %Y %H:%M')
        return datetime.utcnow()
    except: return datetime.utcnow()

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
        R = 6371; dLat = math.radians(lat2-lat1); dLon = math.radians(lon2-lon1)
        a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dLon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return round(R * c, 3)
    except: return 0.0

def process_drone_data(db, data: dict):
    # (Tu función process_drone_data intacta, la omito para ahorrar espacio visual pero DEBE ESTAR AQUÍ)
    # ... (Copia el contenido de process_drone_data que ya tenías) ...
    try:
        external_id = data.get('external_id')
        if not external_id: return

        # Mapeos
        status_text = data.get('status_text', '').lower()
        db_status = "pending"
        if "entregado" in status_text: db_status = "delivered"
        elif "cancelado" in status_text: db_status = "canceled"
        elif "camino" in status_text or "ruta" in status_text: db_status = "on_the_way"
        elif "asignado" in status_text or ("driver_name" in data and "N/A" not in data['driver_name']): db_status = "driver_assigned"
        elif "proceso" in status_text: db_status = "processing"
        elif "confirmado" in status_text: db_status = "confirmed"

        # Relaciones
        store = None
        if data.get('store_name'):
            store = db.query(Store).filter(Store.name == data['store_name']).first()
            if not store:
                store = Store(name=data['store_name'], external_id=f"store_{data['store_name']}")
                db.add(store); db.commit(); db.refresh(store)
            if "store_lat" in data and store.latitude is None:
                store.latitude = data['store_lat']
                store.longitude = data['store_lng']

        customer = None
        if data.get('customer_name'):
            customer = db.query(Customer).filter(Customer.name == data['customer_name']).first()
            if not customer:
                customer = Customer(name=data['customer_name'], external_id=f"cust_{data['customer_name']}")
                db.add(customer); db.commit(); db.refresh(customer)
            if data.get('customer_phone'): customer.phone = data['customer_phone']

        driver = None
        d_name = data.get('driver_name', 'N/A')
        if d_name and "N/A" not in d_name:
            driver = db.query(Driver).filter(Driver.name == d_name).first()
            if not driver: driver = Driver(name=d_name, external_id=f"driver_{d_name}"); db.add(driver); db.commit(); db.refresh(driver)

        # Pedido
        order = db.query(Order).filter(Order.external_id == external_id).first()
        created_at_dt = parse_spanish_date(data.get('created_at_text', ''))
        minutes_calc = parse_duration_to_minutes(data.get('duration_text', ''))
        dist_km = 0.0
        cust_lat, cust_lng = data.get('customer_lat'), data.get('customer_lng')
        if cust_lat and store and store.latitude: dist_km = calculate_distance_km(store.latitude, store.longitude, cust_lat, cust_lng)
        
        order_type = "Delivery"
        if db_status == "canceled": order_type = None
        elif dist_km < 0.1 and dist_km > 0: order_type = "Pickup"

        if not order:
            order = Order(
                external_id=external_id, created_at=created_at_dt, total_amount=data.get('total_amount',0), delivery_fee=data.get('delivery_fee',0),
                gross_delivery_fee=data.get('real_delivery_fee',0), service_fee=data.get('service_fee',0), coupon_discount=data.get('coupon_discount',0), tips=data.get('tips',0),
                current_status=db_status, order_type=order_type, distance_km=dist_km, latitude=cust_lat, longitude=cust_lng,
                cancellation_reason=data.get('cancellation_reason'), delivery_time_minutes=minutes_calc, duration=data.get('duration_text'),
                store_id=store.id if store else None, customer_id=customer.id if customer else None, driver_id=driver.id if driver else None
            )
            db.add(order); db.commit(); db.refresh(order)
            db.add(OrderStatusLog(order_id=order.id, status=db_status, timestamp=datetime.utcnow()))
        else:
            if order.current_status != db_status:
                logger.info(f"🔄 Cambio #{external_id}: {order.current_status}->{db_status}")
                db.add(OrderStatusLog(order_id=order.id, status=db_status, timestamp=datetime.utcnow()))
                order.current_status = db_status
            
            # Updates
            if data.get('total_amount'): order.total_amount = data['total_amount']
            if data.get('real_delivery_fee'): order.gross_delivery_fee = data['real_delivery_fee']
            if minutes_calc: order.delivery_time_minutes = minutes_calc
            if cust_lat: order.latitude=cust_lat; order.longitude=cust_lng; order.distance_km=dist_km; order.order_type=order_type
            if driver: order.driver_id = driver.id
        
        db.commit()
    except Exception as e:
        logger.error(f"Error save {data.get('external_id')}: {e}"); db.rollback()

def save_orders_batch(orders_data: list):
    pass

# --- TAREAS ---

@shared_task(bind=True)
def backfill_historical_data(self):
    key = "celery_lock_backfill_historical_data"
    with redis_lock(key, 14400) as acquired:
        if not acquired: return
        logger.info("🚀 Backfill V4...")
        ls = OrderScraper(); drone = DroneScraper(); db = SessionLocal()
        try:
            if not ls.login(): return
            items = ls.get_historical_ids() 
            ls.close_driver()
            if not drone.login(): return
            for item in items:
                eid = item['id']
                existing = db.query(Order).filter(Order.external_id == eid).first()
                if existing and existing.delivery_time_minutes and existing.latitude: continue
                data = drone.scrape_detail(eid, mode='full')
                data['duration_text'] = item['duration']
                process_drone_data(db, data)
        except Exception as e: logger.error(f"Fatal: {e}")
        finally: 
            if ls: ls.close_driver()
            if drone: drone.close_driver()
            db.close()

@shared_task(bind=True)
def monitor_active_orders(self):
    key = "celery_lock_monitor_active_orders"
    with redis_lock(key, 55) as acquired:
        if not acquired: return
        logger.info("📡 Monitor V4...")
        ls = OrderScraper(); drone = DroneScraper()
        try:
            if not ls.login(): return
            recent_items = ls.get_recent_order_ids(limit=15)
            ls.close_driver()
            if not recent_items: return
            if not drone.login(): return
            db = SessionLocal()
            for item in recent_items:
                eid = item['id']
                data = drone.scrape_detail(eid, mode='full')
                data['duration_text'] = item['duration']
                process_drone_data(db, data)
            db.close()
        except Exception as e: logger.error(f"Monitor: {e}")
        finally:
            if ls: ls.close_driver()
            if drone: drone.close_driver()

@shared_task(bind=True)
def enrich_missing_data(self):
    key = "celery_lock_drone_enrichment"
    with redis_lock(key, 300) as acquired:
        if not acquired: return "Drone busy"
        db = SessionLocal(); drone = DroneScraper(); processed = 0; BATCH_SIZE = 50 
        try:
            # 1. Cancelados
            missing_reasons = db.query(Order).filter(Order.current_status == 'canceled', Order.cancellation_reason == None).limit(BATCH_SIZE).all()
            if missing_reasons:
                if not drone.login(): return
                for order in missing_reasons:
                    data = drone.scrape_detail(order.external_id, mode='reason')
                    order.cancellation_reason = data.get("cancellation_reason", "Sin especificar")
                    if "service_fee" in data: order.service_fee = data["service_fee"]
                    processed += 1
                db.commit()

            # 2. Entregados sin mapa
            if processed < BATCH_SIZE:
                limit = BATCH_SIZE - processed
                targets = db.query(Order).filter(Order.current_status == 'delivered', (Order.latitude == None) | (Order.gross_delivery_fee == 0)).limit(limit).all()
                if targets:
                    if not drone.driver: drone.login()
                    for order in targets:
                        data = drone.scrape_detail(order.external_id, mode='full')
                        process_drone_data(db, data)
                        processed += 1
            if processed > 0:
                enrich_missing_data.apply_async(countdown=2)
                return f"Enriched {processed}"
            return "All Done"
        except Exception as e: logger.error(f"Drone error: {e}")
        finally:
            if drone: drone.close_driver()
            db.close()

# --- AQUÍ ESTABA EL PROBLEMA: EL NOMBRE DE LA TAREA ---
# Forzamos el nombre exacto que está pidiendo el error log
@shared_task(bind=True)
def sync_customer_database(self, limit_pages: int = None):
    """
    Sincroniza clientes.
    :param limit_pages: Si es None, busca TODO. Si es número, es modo vigilancia.
    """
    key = "celery_lock_sync_customers"
    # Lock extendido a 2 horas por si es full sync
    with redis_lock(key, 7200) as acquired:
        if not acquired: return "Sync running"

        mode_txt = f"Vigilancia ({limit_pages} págs)" if limit_pages else "FULL SYNC (Infinito)"
        logger.info(f"👥 Iniciando Sincronización de Clientes: {mode_txt}")
        
        scraper = CustomerScraper()
        db = SessionLocal()
        
        try:
            # Pasamos el límite (o None) al scraper
            users_data = scraper.scrape_customers(max_pages=limit_pages)
            scraper.close_driver()
            
            count_new = 0
            count_updated = 0
            
            for u in users_data:
                customer = db.query(Customer).filter(Customer.name.ilike(f"{u['name']}")).first()
                
                if customer:
                    if u['joined_at']: customer.joined_at = u['joined_at']
                    if u['phone'] and not customer.phone: customer.phone = u['phone']
                    count_updated += 1
                else:
                    new_c = Customer(
                        name=u['name'], 
                        phone=u['phone'], 
                        joined_at=u['joined_at'],
                        external_id=f"reg_{int(time.time())}_{count_new}"
                    )
                    db.add(new_c)
                    count_new += 1
            
            db.commit()
            return f"Clientes: {count_new} nuevos, {count_updated} actualizados."

        except Exception as e:
            logger.error(f"Error sync customers: {e}")
        finally:
            if scraper: scraper.close_driver()
            db.close()

# Alias por si acaso también lo llamas con el nombre viejo
@shared_task(bind=True)
def sync_customers_task(self):
    return sync_customer_database()
