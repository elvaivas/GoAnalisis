from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.api import deps
from app.db.base import StoreSchedule, Store, User
from app.schemas.schedule import ScheduleCreate, ScheduleOut

router = APIRouter()


@router.get("/", response_model=List[ScheduleOut])
def get_schedules(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    # Traemos las reglas unidas con el nombre de la tienda
    results = (
        db.query(StoreSchedule, Store.name)
        .join(Store, StoreSchedule.store_id == Store.id)
        .all()
    )

    # Formateamos la salida
    output = []
    for schedule, store_name in results:
        s_dict = schedule.__dict__
        s_dict["store_name"] = store_name
        output.append(s_dict)

    return output


@router.post("/", response_model=ScheduleOut)
def create_schedule(
    schedule_in: ScheduleCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Solo administradores pueden configurar horarios"
        )

    new_rule = StoreSchedule(**schedule_in.dict())
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)

    # Obtenemos nombre para la respuesta
    store = db.query(Store).filter(Store.id == new_rule.store_id).first()

    # Hack para Pydantic response
    response = new_rule.__dict__
    response["store_name"] = store.name if store else "Desconocida"

    return response


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Permiso denegado")

    rule = db.query(StoreSchedule).filter(StoreSchedule.id == schedule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Regla no encontrada")

    db.delete(rule)
    db.commit()
    return {"status": "deleted"}
