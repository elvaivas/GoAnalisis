from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Este es nuestro "plano" para la respuesta JSON.
class OrderSchema(BaseModel):
    id: int
    external_id: str
    current_status: str
    
    # Campos opcionales (ahora con Optional para evitar errores 500)
    order_type: Optional[str] = None 
    distance_km: Optional[float] = None 
    total_amount: Optional[float] = None
    delivery_fee: Optional[float] = None
    
    # Fechas
    placed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None # Cambiado a Optional por si no existe
    
    # --- NUEVOS CAMPOS DE INTELIGENCIA (V2) ---
    # Los agregamos aquí para que el Frontend pueda recibirlos
    payment_method: Optional[str] = None
    cancellation_reason: Optional[str] = None
    canceled_by: Optional[str] = None

    class Config:
        from_attributes = True
