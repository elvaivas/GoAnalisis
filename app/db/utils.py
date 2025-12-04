from contextlib import contextmanager
from app.db.session import SessionLocal

@contextmanager
def get_db_session():
    """
    Context manager para proporcionar una sesión de base de datos a las tareas
    de Celery y asegurar que se cierre correctamente.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
