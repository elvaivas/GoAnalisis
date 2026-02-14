from pydantic import BaseModel
from typing import Optional


class ScheduleCreate(BaseModel):
    store_id: int
    day_of_week: int  # 0=Lunes, 6=Domingo
    open_time: str  # "08:00"
    close_time: str  # "20:00"
    buffer_minutes: int = 60
    is_active: bool = True


class ScheduleOut(ScheduleCreate):
    id: int
    store_name: str  # Para mostrarlo en la tabla

    class Config:
        from_attributes = True
