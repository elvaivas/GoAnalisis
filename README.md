# GoAnalisis - Dashboard de Inteligencia de Negocio Operativo

**GoAnalisis** es una aplicación web full-stack diseñada para la monitorización y análisis en tiempo real de una plataforma de gestión de pedidos.
 La aplicación utiliza un sistema de web scraping avanzado para extraer datos 24/7, los procesa para generar KPIs clave y los presenta en un dashboard
 interactivo y profesional.

El objetivo principal de GoAnalisis es identificar cuellos de botella operativos, analizar tendencias de negocio y proporcionar una visión clara del
 rendimiento de entidades clave como tiendas y repartidores.

---

## Características Principales

*   **Monitorización 24/7:** Workers asíncronos con Celery y Selenium que extraen datos continuamente.
*   **Análisis de Cuellos de Botella:** Calcula y visualiza el tiempo promedio que los pedidos pasan en cada estado operativo.
*   **KPIs en Tiempo Real:** Tarjetas con métricas clave que se actualizan periódicamente (total de pedidos, ingresos, etc.).
*   **Análisis de Tendencias:** Gráficos interactivos para visualizar la evolución de los ingresos y el volumen de pedidos a lo largo del tiempo.
*   **Rankings de Entidades:** Gráficos y listas con el top 10 de repartidores y tiendas por volumen de pedidos.
*   **Dashboard Interactivo:** Frontend moderno construido con Bootstrap 5 y Chart.js, con filtros por rango de fechas.
*   **Arquitectura Contenerizada:** Todo el ecosistema (API, workers, base de datos, broker) está dockerizado para un despliegue fácil y reproducible.

---

## Arquitectura y Tecnologías

| Componente        | Tecnología                               | Propósito                                                |
|-------------------|------------------------------------------|----------------------------------------------------------|
| **Backend API**   | Python 3.12, FastAPI                     | Servir los datos procesados a través de una API RESTful. |
| **Scraping**      | Selenium                                 | Simular la navegación y extraer datos de la plataforma.  |
| **Tareas Async**  | Celery                                   | Orquestar y programar las tareas de scraping.            |
| **Message Broker**| Redis                                    | Comunicar las tareas programadas a los workers.          |
| **Base de Datos** | PostgreSQL                               | Almacenar y persistir todos los datos extraídos.         |
| **ORM**           | SQLAlchemy                               | Mapear los objetos de Python a las tablas de la BD.      |
| **Análisis**      | Pandas (a futuro), SQLAlchemy            | Procesar y agregar los datos para los KPIs.              |
| **Frontend**      | HTML5, CSS3, JavaScript                  | Estructura y lógica del dashboard.                       |
| **UI Frameworks** | Bootstrap 5, Chart.js, Flatpickr.js      | Diseño responsive, gráficos y selector de fechas.        |
| **Entorno**       | Docker, Docker Compose                   | Contenerización y orquestación de todos los servicios.   |

---

## Puesta en Marcha (Despliegue)

Para levantar la aplicación completa en un entorno de desarrollo o producción, sigue estos pasos.

### Prerrequisitos

*   [Docker](https://www.docker.com/get-started) instalado.
*   [Docker Compose](https://docs.docker.com/compose/install/) instalado.
*   Git (para clonar el repositorio).

### 1. Clonar el Repositorio

```bash
git clone [URL_DE_TU_REPOSITORIO]
cd goanalisis
```

### 2. Configurar el Entorno

La aplicación se configura a través de un archivo `.env`. Crea una copia del archivo de ejemplo y rellena las variables.

```bash
# Aún no tenemos un .env.example, pero este sería el paso.
# Por ahora, crea el archivo .env manualmente.
touch .env
```

Abre el archivo `.env` y añade la siguiente configuración, reemplazando los valores necesarios:

```ini
# Configuración de PostgreSQL (Docker la usará para inicializar la BD)
POSTGRES_USER=operaciones
POSTGRES_PASSWORD=[TU_CONTRASEÑA_SEGURA_PARA_LA_BD]
POSTGRES_DB=goanalisis_db

# Configuración de la Aplicación (los contenedores la leerán)
# ¡IMPORTANTE! POSTGRES_SERVER debe ser el nombre del servicio de Docker ('db')
POSTGRES_SERVER=db
REDIS_URL=redis://redis:6379/0

# Credenciales de la plataforma de scraping
LOGIN_URL=https://ecosistema.gopharma.com.ve/login/admin
GOPHARMA_EMAIL=[TU_EMAIL_DE_LOGIN]
GOPHARMA_PASSWORD=[TU_PASSWORD_DE_LOGIN]
SCRAPER_HEADLESS=True
```

### 3. Levantar la Aplicación con Docker Compose

Este comando construirá las imágenes de la aplicación, descargará las de Postgres y Redis, creará la red y lanzará todos los contenedores.

```bash
docker compose up --build
```

La primera vez, la construcción puede tardar varios minutos. En las siguientes ejecuciones, será mucho más rápido. Verás los logs de todos los servicios en tu terminal. Para detener todo, presiona `Ctrl + C`.

### 4. Inicializar la Base de Datos

La primera vez que levantes la aplicación, la base de datos estará vacía. Abre una **nueva terminal** (sin detener `docker compose`) y ejecuta el siguiente comando para crear todas las tablas:

```bash
docker compose exec api python create_tables.py```

Deberías ver el mensaje "¡Tablas creadas con éxito!".

### 5. Acceder al Dashboard

¡Listo! La aplicación está en marcha.

*   **Dashboard:** Abre tu navegador y ve a `http://localhost:8000`
*   **Documentación de la API:** Accede a `http://localhost:8000/docs`

El sistema comenzará a recopilar y procesar datos automáticamente. La información aparecerá en el dashboard a medida que los workers de Celery completen sus ciclos.

---

## Estructura del Proyecto

```
/goanalisis/
├── app/                  # Código de la aplicación FastAPI (API, frontend, DB)
│   ├── api/              # Endpoints y dependencias de la API
│   ├── core/             # Configuración central
│   ├── db/               # Modelos y sesión de SQLAlchemy
│   ├── schemas/          # Esquemas Pydantic para validación
│   ├── services/         # Lógica de negocio (cálculos, etc.)
│   └── static/           # Archivos CSS y JS
│   └── templates/        # Plantillas HTML (index.html)
├── tasks/                # Código de las tareas asíncronas de Celery
│   ├── scraper/          # Lógica de scraping con Selenium
│   └── celery_tasks.py   # Definición de las tareas
├── .env                  # Archivo de configuración (NO versionar)
├── create_tables.py      # Script para inicializar la BD
├── Dockerfile            # Instrucciones para construir la imagen de la app
└── docker-compose.yml    # Orquestación de todos los servicios
```
