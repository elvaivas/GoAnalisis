from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api import deps
from app.db.base import OrderAudit, User, Order
from app.schemas.audit import AuditCreate

router = APIRouter()


@router.post("/log", summary="Registrar Gestión de ATC")
def log_audit(
    audit_in: AuditCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Guarda el registro de la gestión realizada por el operador sobre un pedido retrasado.
    """
    # 1. Verificar que el pedido existe
    order = db.query(Order).filter(Order.id == audit_in.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    # 2. Crear auditoría
    new_audit = OrderAudit(
        order_id=audit_in.order_id,
        user_id=current_user.id,
        stage=audit_in.stage,
        action_taken=audit_in.action_taken,
        root_cause=audit_in.root_cause,
        notes=audit_in.notes,
    )

    db.add(new_audit)
    db.commit()

    return {"status": "success", "message": "Gestión registrada correctamente"}


@router.get("/history/{order_id}", summary="Ver historial de gestión")
def get_audit_history(
    order_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    audits = (
        db.query(OrderAudit)
        .filter(OrderAudit.order_id == order_id)
        .order_by(OrderAudit.created_at.desc())
        .all()
    )

    return [
        {
            "user": a.user.username if a.user else "Desconocido",
            "stage": a.stage,
            "action": a.action_taken,
            "cause": a.root_cause,
            "date": a.created_at,
            "notes": a.notes,
        }
        for a in audits
    ]
