import os

# Carpetas y archivos a IGNORAR (Agrega aquí lo que quieras filtrar)
IGNORAR_DIRS = {
    ".git",
    "node_modules",
    "venv",
    "__pycache__",
    "build",
    "dist",
    ".idea",
    ".vscode",
}
IGNORAR_EXTS = {
    ".pyc",
    ".exe",
    ".dll",
    ".so",
    ".db",
    ".sqlite",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
}
IGNORAR_FILES = {".env", "package-lock.json", "yarn.lock", "empacador.py"}


def es_texto(archivo):
    # Intenta leer un poco para ver si es binario
    try:
        with open(archivo, "r", encoding="utf-8") as f:
            f.read(1024)
            return True
    except:
        return False


with open("CONTEXTO_PROYECTO.txt", "w", encoding="utf-8") as salida:
    for root, dirs, files in os.walk("."):
        # Filtrar carpetas ignoradas
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIRS]

        for file in files:
            if file in IGNORAR_FILES or os.path.splitext(file)[1] in IGNORAR_EXTS:
                continue

            path_completo = os.path.join(root, file)

            if es_texto(path_completo):
                # Escribir el nombre del archivo y su contenido
                salida.write(f"\n\n{'='*50}\n")
                salida.write(f"ARCHIVO: {path_completo}\n")
                salida.write(f"{'='*50}\n\n")
                try:
                    with open(path_completo, "r", encoding="utf-8") as f:
                        salida.write(f.read())
                except Exception as e:
                    salida.write(f"Error leyendo archivo: {e}")

print("¡Listo! Sube el archivo 'CONTEXTO_PROYECTO.txt' a Gemini.")
