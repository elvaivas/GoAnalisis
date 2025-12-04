from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.api.endpoints import analysis, kpis, data
from pathlib import Path
import os

app = FastAPI(
    title="GoAnalisis Dashboard",
    version="2.0.2"
)

# --- CONFIGURACIÓN DE RUTAS INTELIGENTE ---
# Obtenemos la ruta donde vive este archivo main.py (ej: /app)
BASE_DIR = Path(__file__).resolve().parent

# LÓGICA DEL DOBLE APP:
# Verificamos si existe la carpeta 'app' dentro del directorio actual
# Esto soluciona la anidación /app/app/templates vs /app/templates
if (BASE_DIR / "app" / "templates").exists():
    print("INFO: Detectada estructura anidada (/app/app). Ajustando rutas...")
    static_path = BASE_DIR / "app" / "static"
    templates_path = BASE_DIR / "app" / "templates"
else:
    print("INFO: Estructura estándar detectada.")
    static_path = BASE_DIR / "static"
    templates_path = BASE_DIR / "templates"

print(f"DEBUG: Static Path final: {static_path}")
print(f"DEBUG: Templates Path final: {templates_path}")

# Montamos estáticos con la ruta calculada
app.mount("/static", StaticFiles(directory=str(static_path), check_dir=False), name="static")
templates = Jinja2Templates(directory=str(templates_path))

# --- RUTAS DE LA API ---
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis"])
app.include_router(kpis.router, prefix="/api/kpi", tags=["KPIs"])
app.include_router(data.router, prefix="/api/data", tags=["Data"])

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
