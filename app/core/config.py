import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Variables de entorno para la conexión a PostgreSQL
    # Usamos os.getenv con valores por defecto para asegurar que no falle si falta el .env
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "db")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "operaciones")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "admin123")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "goanalisis_db")

    # Variable para Redis (AQUÍ ESTABA EL PROBLEMA)
    # Forzamos la ruta interna de Docker por defecto
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # Variables para el Scraper
    LOGIN_URL: str = "https://ecosistema.gopharma.com.ve/login/admin"
    GOPHARMA_EMAIL: str = os.getenv("GOPHARMA_EMAIL", "soporte@gopharma.com.ve")
    GOPHARMA_PASSWORD: str = os.getenv("GOPHARMA_PASSWORD", "GoPharma2024.")
    SCRAPER_HEADLESS: bool = True 

    @property
    def DATABASE_URL(self) -> str:
        # Construcción robusta de la URL
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}/{self.POSTGRES_DB}"
        )

    class Config:
        env_file = ".env"
        extra = "ignore"
        case_sensitive = True

settings = Settings()
