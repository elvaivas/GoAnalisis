#!/bin/bash

# ==========================================
# GOANALISIS SENTINEL V3.0 - ZOMBIE HUNTER
# ==========================================

LOG_FILE="/root/GoAnalisis/sentinel.log"
MAX_RAM_USAGE=85
MAX_CHROME_PROCESSES=15  # Si hay más de 15 Chromes, algo anda mal
CONTAINER_WORKER="goanalisis_celery_node"

# Función para registrar logs
log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> $LOG_FILE
}

# 1. VERIFICAR CONTENEDOR VIVO
if [ ! "$(docker ps -q -f name=$CONTAINER_WORKER)" ]; then
    log_msg "❌ PÁNICO: El Worker no está corriendo. Levantando..."
    cd /root/GoAnalisis && docker compose up -d
    exit 0
fi

# 2. VERIFICAR MEMORIA RAM
RAM_USAGE=$(free | grep Mem | awk '{print $3/$2 * 100.0}')
RAM_USAGE=${RAM_USAGE%.*}

if [ "$RAM_USAGE" -gt "$MAX_RAM_USAGE" ]; then
    log_msg "⚠️ ALERTA: RAM Crítica ($RAM_USAGE%). Reiniciando..."
    cd /root/GoAnalisis && docker compose restart celery_node
    exit 0
fi

# 3. VERIFICAR CONTEO DE PROCESOS CHROME (NUEVO)
# Contamos cuántos procesos de chrome/chromedriver hay dentro del contenedor
CHROME_COUNT=$(docker exec $CONTAINER_WORKER ps aux | grep -c "chrome")

if [ "$CHROME_COUNT" -gt "$MAX_CHROME_PROCESSES" ]; then
    log_msg "🧟 PLAGA DETECTADA: Hay $CHROME_COUNT procesos de Chrome (Límite: $MAX_CHROME_PROCESSES)."
    log_msg "🧹 Ejecutando limpieza de zombies..."
    
    docker exec $CONTAINER_WORKER pkill -f chrome || true
    docker exec $CONTAINER_WORKER pkill -f chromedriver || true
    
    # Si hay demasiados, a veces es mejor reiniciar el contenedor para limpiar la tabla de procesos del kernel
    if [ "$CHROME_COUNT" -gt 50 ]; then
        log_msg "☢️ Demasiados zombies. Reiniciando contenedor por seguridad."
        cd /root/GoAnalisis && docker compose restart celery_node
    fi
    
    log_msg "✅ Limpieza completada."
fi

# 4. HEARTBEAT (Logs recientes)
RECENT_LOGS=$(docker logs --since 5m $CONTAINER_WORKER 2>&1 | grep "Monitor V4")
if [ -z "$RECENT_LOGS" ]; then
    log_msg "💀 SIGNOS VITALES PERDIDOS: Monitor inactivo por 5 min."
    log_msg "🚑 Reiniciando..."
    cd /root/GoAnalisis && docker compose restart celery_node
    log_msg "✅ Sistema reanimado."
fi

# Limpieza de logs del sentinel
tail -n 1000 $LOG_FILE > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" $LOG_FILE