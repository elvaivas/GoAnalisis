from sqlalchemy import text
from app.db.base import Base
from app.db.session import engine


def create_database_tables():
    print("🚀 Iniciando control de esquema en la base de datos...")

    try:
        # 1. Crea tablas nuevas que no existan
        Base.metadata.create_all(bind=engine)
        print("✅ Verificación de tablas base completada.")

        # 2. Actualiza tablas existentes (Nuestra migración centralizada)
        with engine.begin() as conn:
            print("🛠️ Aplicando parches de esquema (si aplican)...")
            conn.execute(
                text(
                    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS company_name VARCHAR;"
                )
            )

        print("✅ ¡Estructura de Base de Datos actualizada y lista!")

    except Exception as e:
        print(f"❌ Ocurrió un error en el control de esquema: {e}")


if __name__ == "__main__":
    create_database_tables()
