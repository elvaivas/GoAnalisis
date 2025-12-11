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
        'jul': '07', 'ago': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dic': '12',
        'Dec': '12'
    }
    try:
        lower_str = date_str.lower().replace('.', '')
        for mes_nombre, mes_num in month_map.items():
            if mes_nombre.lower() in lower_str:
                lower_str = lower_str.replace(mes_nombre.lower(), mes_num)
                break
        match = re.search(r'(\d{1,2})\s+(\d{1,2})\s+(\d{4})\s+(\d{1,2}:\d{2})', lower_str)
        if match:
            clean_date_str = f"{match.group(1)} {match.group(2)} {match.group(3)} {match.group(4)}"
            return datetime.strptime(clean_date_str, '%d %m %Y %H:%M')
        return datetime.utcnow()
    except Exception:
        return datetime.utcnow()

def parse_duration_to_minutes(duration_str: str):
    """Calcula minutos totales desde texto como '1 Horas 30 Minutos'"""
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
        
        total = (hours * 60) + minutes + (seconds / 60)
        return round(total, 2)
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

def process_drone_data(db, data: dict):
    try:
        external_id = data.get('external_id')
        if not external_id: return

        # 1. ANALIZAR EL CHOFER PRIMERO
        driver_name = data.get('driver_name', 'N/A')
        # Es un conductor real si no es N/A y tiene más de 2 letras
        has_real_driver = driver_name and "N/A" not in driver_name and len(driver_name) > 2

        # 2. MAPEO DE ESTADO (LÓGICA FINA)
        status_text = data.get('status_text', '').lower()
        db_status = "pending"
        
        if "entregado" in status_text: 
            db_status = "delivered"
        
        elif "cancelado" in status_text or "rechazado" in status_text: 
            db_status = "canceled"
        
        elif "camino" in status_text or "ruta" in status_text: 
            db_status = "on_the_way"
        
        # --- CORRECCIÓN AQUÍ ---
        elif "entrega" in status_text and "repartidor" in status_text:
            if has_real_driver:
                db_status = "driver_assigned" # Fase 2: Aceptado
            else:
                db_status = "confirmed"       # Fase 1: Solicitando (N/A)
        
        elif "asignado" in status_text:
            db_status = "driver_assigned"
        # -----------------------

        elif "proceso" in status_text or "aceptado" in status_text: 
            db_status = "processing"
        
        elif "confirmado" in status_text: 
            db_status = "confirmed"

        # (Fallback de seguridad: si tiene driver, forzamos asignado a menos que sea finalizado)
        if has_real_driver and db_status not in ['delivered', 'canceled', 'on_the_way']:
            db_status = "driver_assigned"

        # 3. RELACIONES
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
            if data.get('customer_phone'):
                customer.phone = data['customer_phone']

        driver = None
        if has_real_driver:
            driver = db.query(Driver).filter(Driver.name == driver_name).first()
            if not driver:
                driver = Driver(name=driver_name, external_id=f"driver_{driver_name}")
                db.add(driver); db.commit(); db.refresh(driver)

        # 4. PEDIDO
        order = db.query(Order).filter(Order.external_id == external_id).first()
        created_at_dt = parse_spanish_date(data.get('created_at_text', ''))
        minutes_calc = parse_duration_to_minutes(data.get('duration_text', ''))
        
        # Distancia y Tipo
        dist_km = 0.0
        cust_lat, cust_lng = data.get('customer_lat'), data.get('customer_lng')
        if cust_lat and store and store.latitude:
            dist_km = calculate_distance_km(store.latitude, store.longitude, cust_lat, cust_lng)
        
        order_type = "Delivery"
        if db_status == "canceled": order_type = None
        elif dist_km < 0.1 and dist_km > 0: order_type = "Pickup"
        
        if not order:
            order = Order(
                external_id=external_id,
                created_at=created_at_dt,
                total_amount=data.get('total_amount', 0.0),
                delivery_fee=data.get('delivery_fee', 0.0),
                gross_delivery_fee=data.get('real_delivery_fee', 0.0),
                service_fee=data.get('service_fee', 0.0),
                coupon_discount=data.get('coupon_discount', 0.0),
                tips=data.get('tips', 0.0),
                current_status=db_status,
                order_type=order_type,
                distance_km=dist_km,
                latitude=cust_lat,
                longitude=cust_lng,
                cancellation_reason=data.get('cancellation_reason'),
                delivery_time_minutes=minutes_calc,
                duration=data.get('duration_text'),
                store_id=store.id if store else None,
                customer_id=customer.id if customer else None,
                driver_id=driver.id if driver else None
            )
            db.add(order); db.commit(); db.refresh(order)
            db.add(OrderStatusLog(order_id=order.id, status=db_status, timestamp=datetime.utcnow()))
            logger.info(f"✅ Nuevo Pedido #{external_id}: {db_status}")
        else:
            if order.current_status != db_status:
                logger.info(f"🔄 Cambio #{external_id}: {order.current_status} -> {db_status}")
                db.add(OrderStatusLog(order_id=order.id, status=db_status, timestamp=datetime.utcnow()))
                order.current_status = db_status
            
            # Actualizaciones
            order.total_amount = data.get('total_amount', order.total_amount)
            if data.get('real_delivery_fee'): order.gross_delivery_fee = data['real_delivery_fee']
            if data.get('service_fee'): order.service_fee = data['service_fee']
            if minutes_calc: order.delivery_time_minutes = minutes_calc
            if data.get('duration_text'): order.duration = data['duration_text']
            
            if cust_lat: 
                order.latitude=cust_lat; order.longitude=cust_lng; order.distance_km=dist_km; order.order_type=order_type
            
            # Solo actualizamos driver si es real
            if driver: order.driver_id = driver.id

        db.commit()
    except Exception as e:
        logger.error(f"Error procesando orden {data.get('external_id')}: {e}")
        db.rollback()

# --- TAREAS ---

@shared_task(bind=True)
def backfill_historical_data(self):
    """
    Backfill V4 (Deep Dive):
    1. Escanea paginación para obtener IDs y Duraciones.
    2. Procesa cada uno con el Dron.
    """
    key = "celery_lock_backfill_historical_data"
    with redis_lock(key, 14400) as acquired:
        if not acquired: return "Task running"

        logger.info("🚀 Iniciando Backfill Histórico V4 (Deep Dive)...")
        
        list_scraper = OrderScraper()
        drone = DroneScraper()
        db = SessionLocal()
        
        try:
            # 1. Obtener IDs y Duraciones de la lista
            if not list_scraper.login(): return
            # Escanear 20 páginas (aprox 500 pedidos)
            items = list_scraper.get_historical_ids(max_pages=20) 
            list_scraper.close_driver()
            
            logger.info(f"📦 Recolectados {len(items)} items. Iniciando Dron...")

            # 2. Procesar detalle con Dron
            if not drone.login(): return
            
            count = 0
            for item in items:
                eid = item['id']
                duration = item['duration']
                
                # Opcional: Saltar si ya está completo
                existing = db.query(Order).filter(Order.external_id == eid).first()
                if existing and existing.delivery_time_minutes and existing.latitude: 
                    continue
                
                logger.info(f"⏳ ({count+1}/{len(items)}) Detalle #{eid}...")
                data = drone.scrape_detail(eid, mode='full')
                
                # Inyectar duración de la lista al detalle
                data['duration_text'] = duration
                
                process_drone_data(db, data)
                count += 1

            return f"Backfill Finalizado. Procesados: {count}"

        except Exception as e:
            logger.error(f"Error fatal backfill: {e}")
        finally:
            if list_scraper: list_scraper.close_driver()
            if drone: drone.close_driver()
            db.close()

@shared_task(bind=True)
def monitor_active_orders(self):
    """
    Monitor V4: Escanea lista para IDs y usa Dron.
    """
    key = "celery_lock_monitor_active_orders"
    with redis_lock(key, 55) as acquired:
        if not acquired: return "Monitor overlap"
        logger.info("📡 Monitor Live: Buscando nuevos pedidos...")
        
        list_scraper = OrderScraper()
        drone = DroneScraper()
        
        try:
            # 1. Obtener IDs
            if not list_scraper.login(): return
            recent_items = list_scraper.get_recent_order_ids(limit=15)
            list_scraper.close_driver()
            
            if not recent_items: return "Sin cambios"
            if not drone.login(): return
            
            db = SessionLocal()
            for item in recent_items:
                eid = item['id']
                duration = item['duration']
                
                # Ignorar finalizados para ahorrar recursos en el monitor
                existing = db.query(Order).filter(Order.external_id == eid).first()
                if existing and existing.current_status in ['delivered', 'canceled']: 
                    continue
                
                logger.info(f"🆕/🔄 Analizando #{eid}...")
                data = drone.scrape_detail(eid, mode='full')
                
                # Inyectar duración
                data['duration_text'] = duration
                
                process_drone_data(db, data)
            
            db.close()
            return "Monitor Terminado"

        except Exception as e:
            logger.error(f"Monitor error: {e}")
        finally:
            if list_scraper: list_scraper.close_driver()
            if drone: drone.close_driver()

@shared_task(bind=True)
def enrich_missing_data(self):
    """
    Dron de Limpieza (V6 Híbrido)
    """
    key = "celery_lock_drone_enrichment"
    with redis_lock(key, 300) as acquired:
        if not acquired: return "Drone busy"
        
        db = SessionLocal()
        drone = DroneScraper()
        processed = 0
        BATCH_SIZE = 50 
        
        try:
            # Prioridad 1: Cancelados
            missing_reasons = db.query(Order).filter(Order.current_status == 'canceled', Order.cancellation_reason == None).limit(BATCH_SIZE).all()
            if missing_reasons:
                if not drone.login(): return
                for order in missing_reasons:
                    data = drone.scrape_detail(order.external_id, mode='reason')
                    order.cancellation_reason = data.get("cancellation_reason", "Sin especificar")
                    # Intentar capturar finanzas de paso
                    if "service_fee" in data: order.service_fee = data["service_fee"]
                    processed += 1
                db.commit()

            # Prioridad 2: Entregados sin mapa
            if processed < BATCH_SIZE:
                limit = BATCH_SIZE - processed
                targets = db.query(Order).filter(Order.current_status == 'delivered', (Order.latitude == None) | (Order.gross_delivery_fee == 0)).limit(limit).all()
                if targets:
                    if not drone.driver: drone.login()
                    for order in targets:
                        # OJO: Aquí el Dron NO tiene acceso a la duración de la lista
                        # así que solo enriquece finanzas y mapas
                        data = drone.scrape_detail(order.external_id, mode='full')
                        process_drone_data(db, data)
                        processed += 1
            
            if processed > 0:
                enrich_missing_data.apply_async(countdown=2)
                return f"Enriched {processed}"
            return "All Done"

        except Exception as e:
            logger.error(f"Drone error: {e}")
        finally:
            if drone: drone.close_driver()
            db.close()
