from app.db.session import SessionLocal

def get_db():
    """
    Dependencia de FastAPI para obtener una sesión de base de datos.
    Asegura que la sesión se cierre después de cada petición.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
