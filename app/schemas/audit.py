from pydantic import BaseModel
from typing import Optional


class AuditCreate(BaseModel):
    order_id: int
    stage: str
    action_taken: str
    root_cause: str
    notes: Optional[str] = None
