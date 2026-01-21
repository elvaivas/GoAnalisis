import logging
import re
import time
import math
from datetime import datetime, timedelta
from contextlib import contextmanager
from celery import shared_task
import redis

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.base import Order, Store, Customer, Driver, OrderStatusLog, OrderItem
from tasks.scraper.order_scraper import OrderScraper 
from tasks.scraper.drone_scraper import DroneScraper 
from tasks.scraper.customer_scraper import CustomerScraper 
from tasks.scraper.store_scraper import StoreScraper 

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
    """
    Parsea fechas híbridas (Español/Inglés) con o sin puntos.
    Ej: '03 ene. 2026', '10 Dec 2025'
    """
    if not date_str: return datetime.utcnow()
    
    # Mapa Bilingüe y a prueba de errores
    month_map = {
        'ene': '01', 'jan': '01', 'enero': '01', 'january': '01',
        'feb': '02', 'febrero': '02', 'february': '02',
        'mar': '03', 'marzo': '03', 'march': '03',
        'abr': '04', 'apr': '04', 'abril': '04', 'april': '04',
        'may': '05', 'mayo': '05',
        'jun': '06', 'junio': '06', 'june': '06',
        'jul': '07', 'julio': '07', 'july': '07',
        'ago': '08', 'aug': '08', 'agosto': '08', 'august': '08',
        'sep': '09', 'septiembre': '09', 'september': '09',
        'oct': '10', 'octubre': '10', 'october': '10',
        'nov': '11', 'noviembre': '11', 'november': '11',
        'dic': '12', 'dec': '12', 'diciembre': '12', 'december': '12'
    }
    
    original = date_str
    try:
        # Limpieza: minúsculas y quitar puntos
        clean_str = date_str.lower().replace('.', '').strip()
        
        # Reemplazo inteligente de mes
        for m_name, m_num in month_map.items():
            # Usamos espacios para evitar reemplazar partes de palabras
            if m_name in clean_str:
                clean_str = clean_str.replace(m_name, m_num)
                break
        
        # Regex flexible: Busca (Dia) (MesNum) (Año 4 digitos) (Hora:Min)
        match = re.search(r'(\d{1,2})[\s/-]+(\d{1,2})[\s/-]+(\d{4})\s+(\d{1,2}:\d{2})', clean_str)
        
        if match:
            day, month, year, time_str = match.groups()
            return datetime.strptime(f"{day} {month} {year} {time_str}", '%d %m %Y %H:%M')
            
        # Fallback: Si no encuentra hora, intenta solo fecha
        match_date = re.search(r'(\d{1,2})[\s/-]+(\d{1,2})[\s/-]+(\d{4})', clean_str)
        if match_date:
            day, month, year = match_date.groups()
            return datetime.strptime(f"{day} {month} {year}", '%d %m %Y')

        logger.warning(f"⚠️ No se pudo parsear fecha: '{original}'. Usando UTC Now.")
        return datetime.utcnow()
        
    except Exception as e:
        logger.error(f"Error parseando fecha '{original}': {e}")
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
        R = 6371; dLat = math.radians(lat2-lat1); dLon = math.radians(lon2-lon1)
        a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dLon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return round(R * c, 3)
    except: return 0.0

def normalize_cancellation_reason(text: str) -> str:
    """Estandariza los motivos de cancelación."""
    if not text or text == "." or len(text) < 3: return "Sin especificar"
    
    text = text.replace("del pedido :", "").replace("del pedido", "").strip()
    text_lower = text.lower()

    if any(x in text_lower for x in ['disponible','existencia','vencido','dañado','no hay','no tenemos','blister','inventario','coca cola','falta','agotado','stock','medicamento','existente']):
        return "Producto No Disponible / Dañado"
    if any(x in text_lower for x in ['payment','pago','transferencia','zelle','móvil','movil']):
        if "agotado" in text_lower or "tiempo" in text_lower: return "Tiempo de Pago Agotado"
        return "Problemas con el Pago"
    if any(x in text_lower for x in ['equivocado','descripcion','descripción','precio','código','codigo','error']):
        return "Error en Pedido / Descripción"
    if any(x in text_lower for x in ['nota','prueba','test','orden de','admin','traspaso']):
        return "Cancelación Administrativa"
    
    return text.title()

def process_drone_data(db, data: dict):
    try:
        external_id = data.get('external_id')
        if not external_id: return

        # --- DIAGNÓSTICO DE ESTATUS (Log visible) ---
        raw_status = data.get('status_text', '').strip()
        status_text = raw_status.lower()
        
        db_status = "pending" # Default
        
        # Lógica de Mapeo Blindada
        if "entregado" in status_text: 
            db_status = "delivered"
        elif "cancelado" in status_text: 
            db_status = "canceled"
        elif "asignado" in status_text: 
            db_status = "driver_assigned"
        elif "camino" in status_text or "ruta" in status_text: 
            db_status = "on_the_way"
        elif "proceso" in status_text: 
            db_status = "processing"
        elif "confirmado" in status_text: 
            db_status = "confirmed"
        
        # Log para ver qué decidió el sistema
        if db_status == "pending" and "pendiente" not in status_text:
            logger.warning(f"⚠️ Estatus Raro en #{external_id}: '{raw_status}' -> Se quedó como Pending")
        
        # --- BUSCAR O CREAR RELACIONES ---
        # (Tiendas, Clientes, Drivers)
        
        store = None
        if data.get('store_name'):
            store = db.query(Store).filter(Store.name == data['store_name']).first()
            if not store:
                store = Store(name=data['store_name'], external_id=f"store_{data['store_name']}")
                db.add(store); db.commit(); db.refresh(store)
            # Actualizar coords tienda si faltan
            if "store_lat" in data and store.latitude is None:
                store.latitude = data['store_lat']; store.longitude = data['store_lng']

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
            if not driver: 
                driver = Driver(name=d_name, external_id=f"driver_{d_name}")
                db.add(driver); db.commit(); db.refresh(driver)

        # --- BUSCAR PEDIDO ---
        order = db.query(Order).filter(Order.external_id == external_id).first()
        
        # Fechas y Cálculos
        created_at_dt = parse_spanish_date(data.get('created_at_text', ''))
        minutes_calc = parse_duration_to_minutes(data.get('duration_text', ''))
        
        dist_km = 0.0
        cust_lat, cust_lng = data.get('customer_lat'), data.get('customer_lng')
        if cust_lat and store and store.latitude: 
            dist_km = calculate_distance_km(store.latitude, store.longitude, cust_lat, cust_lng)
        
        # --- LÓGICA DE CLASIFICACIÓN LOGÍSTICA V2 (La que arreglamos antes) ---
        order_type = "Delivery"
        
        # 1. Si hay driver, es Delivery seguro
        if driver and driver.name and "N/A" not in driver.name:
            order_type = "Delivery"
        # 2. Cancelado no tiene tipo
        elif db_status == "canceled":
            order_type = None
        # 3. Distancia cero = Pickup
        elif dist_km is not None and dist_km < 0.2 and dist_km >= 0:
            order_type = "Pickup"
        
        c_reason = normalize_cancellation_reason(data.get('cancellation_reason'))

        # --- GUARDADO ---
        if not order:
            # CREAR NUEVO
            order = Order(
                external_id=external_id, created_at=created_at_dt, 
                total_amount=data.get('total_amount',0), 
                delivery_fee=data.get('delivery_fee',0),
                gross_delivery_fee=data.get('real_delivery_fee',0), 
                service_fee=data.get('service_fee',0), 
                coupon_discount=data.get('coupon_discount',0), 
                tips=data.get('tips',0),
                product_price=data.get('product_price',0),
                current_status=db_status, 
                order_type=order_type, 
                distance_km=dist_km, 
                latitude=cust_lat, longitude=cust_lng,
                cancellation_reason=c_reason, 
                delivery_time_minutes=minutes_calc, 
                duration=data.get('duration_text'),
                store_id=store.id if store else None, 
                customer_id=customer.id if customer else None, 
                driver_id=driver.id if driver else None
            )
            db.add(order); db.commit(); db.refresh(order)
            # Log inicial
            db.add(OrderStatusLog(order_id=order.id, status=db_status, timestamp=datetime.utcnow()))
        else:
            # ACTUALIZAR EXISTENTE
            
            # 1. Cambio de Estatus
            if order.current_status != db_status:
                logger.info(f"🔄 Cambio #{external_id}: {order.current_status} -> {db_status}")
                db.add(OrderStatusLog(order_id=order.id, status=db_status, timestamp=datetime.utcnow()))
                order.current_status = db_status
            
            # 2. Updates Financieros
            order.total_amount = data.get('total_amount', order.total_amount)
            if data.get('real_delivery_fee'): order.gross_delivery_fee = data['real_delivery_fee']
            if data.get('service_fee'): order.service_fee = data['service_fee']
            if data.get('product_price'): order.product_price = data['product_price']
            if c_reason: order.cancellation_reason = c_reason
            
            # 3. Logística
            if minutes_calc: order.delivery_time_minutes = minutes_calc
            if cust_lat: 
                order.latitude = cust_lat; order.longitude = cust_lng; order.distance_km = dist_km
            
            if order_type: order.order_type = order_type
            if driver: order.driver_id = driver.id
            if customer: order.customer_id = customer.id
        
        # 4. PRODUCTOS (Siempre actualizar detalle)
        if "items" in data and data["items"]:
            db.query(OrderItem).filter(OrderItem.order_id == order.id).delete()
            for item in data["items"]:
                db.add(OrderItem(
                    order_id=order.id, name=item['name'], 
                    quantity=item['quantity'], unit_price=item['unit_price'], 
                    total_price=item['total_price'], barcode=item.get('barcode')
                ))
        
        db.commit()
        logger.info(f"✅ Procesado #{external_id}: {db_status} | {order_type}")

    except Exception as e:
        logger.error(f"Error save {data.get('external_id')}: {e}")
        db.rollback()

def save_orders_batch(orders_data: list):
    pass

# --- TAREAS ---

@shared_task(bind=True)
def backfill_historical_data(self):
    key = "celery_lock_backfill_historical_data"
    with redis_lock(key, 14400) as acquired:
        if not acquired: return
        ls = OrderScraper(); drone = DroneScraper(); db = SessionLocal()
        try:
            if not ls.login(): return
            items = ls.get_historical_ids() 
            ls.close_driver()
            if not drone.login(): return
            for item in items:
                eid = item['id']
                existing = db.query(Order).filter(Order.external_id == eid).first()
                if existing and existing.delivery_time_minutes and existing.latitude and existing.product_price: continue
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
    """
    Dron de Limpieza: 1. Cancelados, 2. Mapas/Finanzas, 3. Zombies (Pendientes viejos).
    """
    key = "celery_lock_drone_enrichment"
    with redis_lock(key, 300) as acquired:
        if not acquired: return "Drone busy"
        
        db = SessionLocal()
        drone = DroneScraper()
        processed = 0
        BATCH_SIZE = 50 
        
        try:
            # 1. Cancelados (Prioridad Alta)
            missing_reasons = db.query(Order).filter(Order.current_status == 'canceled', Order.cancellation_reason == None).limit(BATCH_SIZE).all()
            if missing_reasons:
                if not drone.login(): return
                for order in missing_reasons:
                    data = drone.scrape_detail(order.external_id, mode='reason')
                    order.cancellation_reason = normalize_cancellation_reason(data.get("cancellation_reason"))
                    if "service_fee" in data: order.service_fee = data["service_fee"]
                    processed += 1
                db.commit()

            # 2. Entregados incompletos (Mapa, Fee, Productos)
            if processed < BATCH_SIZE:
                limit = BATCH_SIZE - processed
                targets = db.query(Order).filter(
                    Order.current_status == 'delivered', 
                    (Order.latitude == None) | (Order.gross_delivery_fee == 0) | (Order.product_price == 0)
                ).limit(limit).all()
                
                if targets:
                    if not drone.driver: drone.login()
                    for order in targets:
                        data = drone.scrape_detail(order.external_id, mode='full')
                        process_drone_data(db, data)
                        processed += 1
                db.commit() # Commit parcial

            # --- 3. ZOMBIES (Pedidos 'Pendientes' con > 6 horas) ---
            # Esto arregla el caso del pedido 106784 automáticamente
            if processed < BATCH_SIZE:
                limit = BATCH_SIZE - processed
                # Hora actual menos 6 horas
                time_threshold = datetime.utcnow() - timedelta(hours=6)
                
                zombies = db.query(Order).filter(
                    Order.current_status.in_(['pending', 'processing', 'confirmed', 'driver_assigned', 'on_the_way']),
                    Order.created_at < time_threshold
                ).limit(limit).all()
                
                if zombies:
                    logger.info(f"🧟 Dron: Revisando {len(zombies)} pedidos zombies antiguos...")
                    if not drone.driver: drone.login()
                    
                    for order in zombies:
                        # Entramos a ver si ya cambió
                        data = drone.scrape_detail(order.external_id, mode='full')
                        process_drone_data(db, data)
                        processed += 1
                    db.commit()
            # -------------------------------------------------------
            
            if processed > 0:
                enrich_missing_data.apply_async(countdown=2)
                return f"Enriched {processed}"
            return "All Done"

        except Exception as e:
            logger.error(f"Drone error: {e}")
        finally:
            if drone: drone.close_driver()
            db.close()

@shared_task(bind=True, name="tasks.celery_tasks.sync_customer_database")
def sync_customer_database(self, limit_pages: int = None):
    """
    Sincroniza la base de datos de clientes.
    """
    key = "celery_lock_sync_customers"
    with redis_lock(key, 7200) as acquired:
        if not acquired: return "Sync running"

        mode_txt = f"Vigilancia ({limit_pages} págs)" if limit_pages else "FULL SYNC (Infinito)"
        logger.info(f"👥 Iniciando Sincronización de Clientes: {mode_txt}")
        
        scraper = CustomerScraper()
        db = SessionLocal()
        
        # --- CORRECCIÓN: Inicializar variables AQUÍ arriba ---
        count_new = 0
        count_updated = 0
        # ---------------------------------------------------
        
        try:
            users_data = scraper.scrape_customers(max_pages=limit_pages)
            scraper.close_driver()
            
            for u in users_data:
                # 1. Buscar por ID externo real (Prioridad)
                customer = None
                if u.get('id'):
                    customer = db.query(Customer).filter(Customer.external_id == u['id']).first()
                
                # 2. Buscar por nombre (Fallback)
                if not customer:
                    customer = db.query(Customer).filter(Customer.name.ilike(f"{u['name']}")).first()
                
                if customer:
                    # Actualizamos fecha si el scraper trajo una válida
                    if u['joined_at']: 
                        customer.joined_at = u['joined_at']
                        count_updated += 1
                    
                    if u['phone']: customer.phone = u['phone']
                    
                    # Guardamos el ID real si no lo tenía
                    if u.get('id') and not customer.external_id:
                        customer.external_id = u['id']
                else:
                    # Crear nuevo
                    new_c = Customer(
                        name=u['name'], 
                        phone=u['phone'], 
                        joined_at=u['joined_at'],
                        external_id=u.get('id') or f"reg_{int(time.time())}_{count_new}"
                    )
                    db.add(new_c)
                    count_new += 1
            
            db.commit()
            return f"Clientes: {count_new} nuevos, {count_updated} actualizados."

        except Exception as e:
            logger.error(f"Sync error: {e}")
            db.rollback()
        finally:
            if scraper: scraper.close_driver()
            db.close()

@shared_task(bind=True)
def sync_store_commissions(self):
    key = "celery_lock_sync_stores"
    with redis_lock(key, 1800) as acquired:
        if not acquired: return
        db = SessionLocal(); stores = db.query(Store).all(); scraper = StoreScraper()
        if not scraper.login(): return
        updated = 0
        for s in stores:
            try:
                real_id = re.search(r'\d+', s.external_id or "").group(0)
                commission = scraper.scrape_commission(real_id)
                if commission > 0:
                    s.commission_rate = commission
                    updated += 1
            except: continue
        db.commit()
        scraper.close_driver()
        db.close()
        return f"Tiendas: {updated}"
