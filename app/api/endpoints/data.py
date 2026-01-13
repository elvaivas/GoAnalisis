from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date
from fastapi.responses import StreamingResponse
import io
from tasks.scraper.order_scraper import OrderScraper 
from app.api import deps
from app.db.base import Order, OrderStatusLog, Store, Customer, User, Driver, OrderItem
from app.services import analysis_service

router = APIRouter()

# --- HELPER INTERNO ---
def apply_filters(query, start_date, end_date, store_name, search):
    local_date = func.date(func.timezone('America/Caracas', func.timezone('UTC', Order.created_at)))
    if start_date: query = query.filter(local_date >= start_date)
    if end_date: query = query.filter(local_date <= end_date)
    if store_name: query = query.join(Store, Order.store_id == Store.id).filter(Store.name == store_name)
    if search:
        term = search.strip()
        if term.isdigit(): query = query.filter(Order.external_id.like(f"{term}%"))
        else: query = query.join(Customer, Order.customer_id == Customer.id, isouter=True).filter(Customer.name.ilike(f"%{term}%"))
    return query

@router.get("/orders", summary="Lista de pedidos con Items (Drill-Down)")
def get_recent_orders(
    db: Session = Depends(deps.get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user)
):
    query = db.query(Order)
    query = apply_filters(query, start_date, end_date, store_name, search)
    
    # Límite de 50 para velocidad
    orders = query.order_by(Order.created_at.desc()).limit(50).all()
    
    data_response = []
    for o in orders:
        # 1. Tiempos
        last_log = db.query(OrderStatusLog).filter(OrderStatusLog.order_id == o.id).order_by(OrderStatusLog.timestamp.desc()).first()
        state_start = last_log.timestamp if last_log else o.created_at
        
        # 2. Lealtad
        order_count = 0
        if o.customer_id:
            order_count = db.query(func.count(Order.id)).filter(Order.customer_id == o.customer_id).scalar()

        # 3. Driver
        driver_info = {"name": "No Asignado", "phone": None}
        if o.driver:
            driver_info["name"] = o.driver.name
            driver_info["phone"] = getattr(o.driver, 'phone', None)

        # 4. ITEMS (ESTO ES LO QUE FALTABA PARA VER LA LISTA)
        db_items = db.query(OrderItem).filter(OrderItem.order_id == o.id).all()
        items_list = [{
            "name": i.name,
            "quantity": i.quantity,
            "unit_price": i.unit_price,
            "total_price": i.total_price
        } for i in db_items]

        data_response.append({
            "id": o.id,
            "external_id": o.external_id,
            "current_status": o.current_status,
            "order_type": o.order_type,
            "total_amount": o.total_amount,
            
            "store_name": o.store.name if o.store else "Sin Tienda",
            "customer_name": o.customer.name if o.customer else "Anónimo",
            "customer_phone": o.customer.phone if o.customer else None,
            "customer_orders_count": order_count,
            "driver": driver_info,
            
            "created_at": o.created_at,
            "state_start_at": state_start,
            "duration_text": o.duration,
            
            "items": items_list # <--- AQUÍ SE ENVÍA LA DATA AL FRONT
        })
    return data_response

# --- ENDPOINTS DELEGADOS AL SERVICIO (Igual que antes) ---

@router.get("/heatmap")
def get_heatmap_endpoint(db: Session = Depends(deps.get_db), start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None), store_name: Optional[str] = Query(None)):
    return analysis_service.get_heatmap_data(db, start_date, end_date, store_name)

@router.get("/trends")
def get_trends_data(db: Session = Depends(deps.get_db), start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None), store_name: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    return analysis_service.get_daily_trends(db, start_date, end_date, store_name, search)

@router.get("/top-products")
def get_top_products_data(db: Session = Depends(deps.get_db), start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None), store_name: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    return analysis_service.get_top_products(db, start_date, end_date, store_name, search)

@router.get("/driver-leaderboard")
def get_driver_leaderboard_data(db: Session = Depends(deps.get_db), start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None), store_name: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    return analysis_service.get_driver_leaderboard(db, start_date, end_date, store_name, search)

@router.get("/top-stores")
def get_top_stores_data(db: Session = Depends(deps.get_db), start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None), store_name: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    return analysis_service.get_top_stores(db, start_date, end_date, store_name, search)

@router.get("/top-customers")
def get_top_customers_data(db: Session = Depends(deps.get_db), start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None), store_name: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    return analysis_service.get_top_customers(db, start_date, end_date, store_name, search)

@router.get("/stores-locations")
def get_stores_locations(db: Session = Depends(deps.get_db)):
    stores = db.query(Store).filter(Store.latitude != None).all()
    return [{"name": s.name, "lat": s.latitude, "lng": s.longitude} for s in stores]

@router.get("/all-stores-names")
def get_all_stores_names(db: Session = Depends(deps.get_db)):
    stores = db.query(Store.name).order_by(Store.name.asc()).all()
    return [s.name for s in stores if s.name]

@router.get("/download-legacy-excel/{order_id}", summary="Descargar Excel Oficial (Proxy)")
def download_legacy_excel(
    order_id: str,
    current_user: User = Depends(deps.get_current_user)
):
    """
    Actúa como proxy: Se loguea en GoPharma, descarga el Excel real y lo entrega al usuario.
    """
    scraper = OrderScraper()
    
    # Ejecutamos la descarga
    # El scraper ya gestiona su propio ciclo de vida (abre y cierra driver internamente)
    file_content, filename = scraper.download_official_excel(order_id)
    
    if not file_content:
        # Si falla, devolvemos un JSON (pero ya no crasheará con 500)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=404, 
            content={"error": "No se pudo descargar el archivo. Verifica la captura de error en /static/error_login.png"}
        )

    # Convertimos bytes a un stream para FastAPI
    stream = io.BytesIO(file_content)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
