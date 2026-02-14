from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional  # <--- ¡ASEGÚRATE DE AGREGAR 'Optional' AQUÍ!
from app.api import deps
from app.db.base import StoreHoliday, User, Store  # Agregamos Store para el JOIN
from pydantic import BaseModel
from datetime import date

router = APIRouter()


# Esquema simple para recibir datos
class HolidayCreate(BaseModel):
    date: date
    description: str
    store_id: Optional[int] = None  # Ahora sí Python sabrá qué es Optional


@router.get("/")
def get_holidays(db: Session = Depends(deps.get_db)):
    # Ejecutamos la consulta con el JOIN
    results = (
        db.query(StoreHoliday, Store.name)
        .join(Store, StoreHoliday.store_id == Store.id, isouter=True)
        .order_by(StoreHoliday.date.asc())
        .all()
    )

    # --- PLANCHADO DE DATOS ---
    # Convertimos la lista de tuplas (Objeto, String) en una lista de diccionarios planos
    output = []
    for holiday, store_name in results:
        output.append(
            {
                "id": holiday.id,
                "date": holiday.date,
                "description": holiday.description,
                "store_name": store_name
                or "🌍 Todas las Tiendas",  # Si store_name es None, es global
            }
        )

    return output


@router.post("/")
def create_holiday(
    holiday_in: HolidayCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403)

    new_h = StoreHoliday(
        date=holiday_in.date,
        description=holiday_in.description,
        store_id=holiday_in.store_id,  # Guardamos el ID de la tienda (o None)
        is_closed_all_day=True,
    )
    db.add(new_h)
    db.commit()
    db.refresh(new_h)
    return {"status": "ok"}


@router.delete("/{holiday_id}")
def delete_holiday(
    holiday_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="No autorizado")

    h = db.query(StoreHoliday).filter(StoreHoliday.id == holiday_id).first()
    if h:
        db.delete(h)
        db.commit()
    return {"status": "ok"}
