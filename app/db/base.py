from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class OrderTypeEnum(str, enum.Enum):
    DELIVERY = "Delivery"
    PICKUP = "Pickup"

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Datos financieros
    total_amount = Column(Float, nullable=True)
    delivery_fee = Column(Float, nullable=True)
    
    # Estado y Tipo
    current_status = Column(String, default="pending")
    order_type = Column(Enum(OrderTypeEnum), nullable=True)
    
    # --- NUEVOS CAMPOS DE ANÁLISIS ---
    payment_method = Column(String, nullable=True)      # Ej: Pago Móvil, Zelle
    cancellation_reason = Column(String, nullable=True) # Ej: Problemas con el pago
    canceled_by = Column(String, nullable=True)         # Ej: customer, admin
    
    # --- CAMPO CORREGIDO (AMPLIADO) ---
    duration = Column(String(255), nullable=True)       # Antes String (50), ahora soporta texto largo
    # ---------------------------------
    # --- NUEVOS CAMPOS V3 (Drone) ---
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # --- NUEVO CAMPO V4 (Estadísticas de Tiempo) ---
    delivery_time_minutes = Column(Float, nullable=True) 
    
    # --- FINANZAS PROFUNDAS ---
    service_fee = Column(Float, default=0.0)
    coupon_discount = Column(Float, default=0.0)
    tips = Column(Float, default=0.0)
    
    # --- NUEVO: Tarifa Bruta (Base para el 80/20) ---
    gross_delivery_fee = Column(Float, default=0.0) 
    # ...
    # --- NUEVO CAMPO V6 ---
    distance_km = Column(Float, default=0.0) # Distancia Tienda -> Cliente
    # ...

    # Relaciones (Foreing Keys)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)

    # Relaciones (Objetos)
    status_logs = relationship("OrderStatusLog", back_populates="order", cascade="all, delete-orphan")
    store = relationship("Store", back_populates="orders")
    customer = relationship("Customer", back_populates="orders")
    driver = relationship("Driver", back_populates="orders")

class OrderStatusLog(Base):
    __tablename__ = "order_status_logs"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    status = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    order = relationship("Order", back_populates="status_logs")

class Store(Base):
    __tablename__ = "stores"
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    orders = relationship("Order", back_populates="store")

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    external_id = Column(String, unique=True)
    phone = Column(String, nullable=True) # <--- NUEVO CAMPO
    orders = relationship("Order", back_populates="customer")

class Driver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)
    orders = relationship("Order", back_populates="driver")
