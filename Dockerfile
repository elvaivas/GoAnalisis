# Usamos una imagen base que ya incluye muchas herramientas comunes
FROM python:3.12-bullseye

# Establecemos el directorio de trabajo
WORKDIR /app

# Actualizamos los paquetes e instalamos 'wget' y 'build-essential'
RUN apt-get update && apt-get install -y wget build-essential locales

# --- NUEVO: Configurar la localización en español ---
RUN echo "es_ES.UTF-8 UTF-8" >> /etc/locale.gen && \
    locale-gen es_ES.UTF-8 && \
    update-locale LANG=es_ES.UTF-8
ENV LANG es_ES.UTF-8

# --- INSTALACIÓN DIRECTA DE GOOGLE CHROME ---
# 1. Descargamos el paquete oficial .deb de Google Chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 2. Instalamos el paquete. El comando 'apt-get install -f -y' es crucial,
# ya que automáticamente busca e instala TODAS las dependencias que Chrome necesita.
RUN apt-get install -y ./google-chrome-stable_current_amd64.deb || apt-get install -f -y

# 3. Limpiamos el archivo descargado para mantener la imagen ligera
RUN rm google-chrome-stable_current_amd64.deb
# --------------------------------------------

# Copiamos solo el archivo de requerimientos para aprovechar la caché de Docker
COPY requirements.txt .

# Instalamos las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el código fuente de nuestra aplicación a la imagen
COPY . .

# Exponemos el puerto de la API
EXPOSE 8000

# Definimos el comando por defecto para iniciar el servidor uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
