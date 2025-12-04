from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# El 'engine' es el punto de entrada a la base de datos.
# Le decimos a SQLAlchemy cómo conectarse usando la URL que construimos.
# pool_pre_ping=True verifica las conexiones antes de usarlas, lo que previene errores
# con conexiones que la base de datos haya cerrado por inactividad.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# SessionLocal es una "fábrica" de sesiones. Cada vez que la llamemos,
# nos dará una nueva sesión de base de datos para una transacción o petición.
# autocommit=False y autoflush=False es la configuración estándar para usar
# sesiones de SQLAlchemy dentro de un framework web como FastAPI.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
