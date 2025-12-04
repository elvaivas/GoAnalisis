# migrate_times.py
import re
from app.db.session import SessionLocal
from app.db.base import Order

def parse_duration_to_minutes(duration_str: str):
    if not duration_str: return None
    try:
        # Formatos esperados en tu DB:
        # "Entregado: ... 55 Minutos 39 segundos"
        # "Entregado: ... 1 Horas 1 Minutos ..."
        
        # 1. Buscar Horas
        hours = 0
        h_match = re.search(r'(\d+)\s*Horas', duration_str, re.IGNORECASE)
        if h_match:
            hours = int(h_match.group(1))
            
        # 2. Buscar Minutos
        minutes = 0
        m_match = re.search(r'(\d+)\s*Minutos', duration_str, re.IGNORECASE)
        if m_match:
            minutes = int(m_match.group(1))
            
        # 3. Buscar Segundos (Opcional, sumamos como decimal)
        seconds = 0
        s_match = re.search(r'(\d+)\s*segundos', duration_str, re.IGNORECASE)
        if s_match:
            seconds = int(s_match.group(1))

        total_minutes = (hours * 60) + minutes + (seconds / 60)
        return round(total_minutes, 2)
    except:
        return None

def run():
    db = SessionLocal()
    # Solo procesamos Deliverys Entregados que tengan texto de duración pero no cálculo numérico
    orders = db.query(Order).filter(
        Order.current_status == 'delivered',
        Order.order_type == 'Delivery',
        Order.duration != None,
        Order.delivery_time_minutes == None
    ).all()
    
    print(f"🔄 Procesando {len(orders)} pedidos para conversión de tiempo...")
    
    count = 0
    for order in orders:
        minutes = parse_duration_to_minutes(order.duration)
        if minutes:
            order.delivery_time_minutes = minutes
            count += 1
            
    db.commit()
    db.close()
    print(f"✅ Éxito: {count} pedidos actualizados con tiempo numérico.")

if __name__ == "__main__":
    run()
