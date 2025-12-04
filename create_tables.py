# Es posible que necesitemos instalar SQLAlchemy si no lo hemos hecho
# pip install SQLAlchemy
from app.db.base import Base
from app.db.session import engine

def create_database_tables():
    """
    Se conecta a la base de datos definida en el engine y crea todas las
    tablas definidas en los modelos que heredan de la Base declarativa.
    """
    print("Iniciando la creación de tablas en la base de datos...")
    
    try:
        # La magia sucede aquí: SQLAlchemy inspecciona todos los modelos
        # importados que heredan de `Base` y crea las tablas correspondientes.
        Base.metadata.create_all(bind=engine)
        print("¡Tablas creadas con éxito!")
        print("Puedes verificarlo conectándote a la base de datos 'goanalisis_db'.")
    except Exception as e:
        print(f"Ocurrió un error al intentar crear las tablas: {e}")

if __name__ == "__main__":
    create_database_tables()
