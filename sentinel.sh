#!/bin/bash

# ==========================================
# GOANALISIS SENTINEL V4.0 - OMNISCIENT
# ==========================================
# 1. Recursos (RAM/CPU/Disco)
# 2. Zombies (Procesos Chrome)
# 3. Heartbeat (Logs de actividad)
# 4. Salud DB (Conexión SQL)
# 5. Atasco de Cola (Redis Overflow)
# ==========================================

LOG_FILE="/root/GoAnalisis/sentinel.log"
MAX_RAM_USAGE=85
MAX_DISK_USAGE=90
MAX_CHROME_PROCESSES=15
MAX_REDIS_QUEUE=200 # Si hay más de 200 tareas en cola, algo va mal

# Nombres de contenedores
C_WORKER="goanalisis_celery_node"
C_BEAT="goanalisis_celery_beat"
C_DB="goanalisis_db"
C_REDIS="goanalisis_redis"
C_API="goanalisis_api"

# Función para registrar logs
log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> $LOG_FILE
}

# --- 1. CHEQUEO DE DISCO DURO (PREVENCIÓN DE CRASH) ---
DISK_USAGE=$(df / | grep / | awk '{ print $5 }' | sed 's/%//g')
if [ "$DISK_USAGE" -gt "$MAX_DISK_USAGE" ]; then
    log_msg "🧹 ALERTA: Disco al $DISK_USAGE%. Limpiando temporales y Docker..."
    docker system prune -f > /dev/null 2>&1
    rm -rf /tmp/tmp*
    rm -rf /tmp/.com.google.Chrome*
    log_msg "✅ Limpieza de disco realizada."
fi

# --- 2. SALUD DE BASE DE DATOS (NUEVO) ---
# Intentamos una consulta simple. Si falla, la DB está pegada.
if ! docker exec $C_DB psql -U operaciones -d goanalisis_db -c "SELECT 1;" > /dev/null 2>&1; then
    log_msg "💀 BASE DE DATOS INACCESIBLE. Reiniciando ecosistema..."
    cd /root/GoAnalisis && docker compose restart db api celery_node
    sleep 10
    log_msg "✅ DB Reiniciada."
fi

# --- 3. ATASCO DE COLA REDIS (NUEVO) ---
# Si hay demasiadas tareas acumuladas, limpiamos para destrabar
QUEUE_SIZE=$(docker exec $C_REDIS redis-cli -n 0 LLEN celery 2>/dev/null)
# Asegurar que sea número
re='^[0-9]+$'
if ! [[ $QUEUE_SIZE =~ $re ]]; then QUEUE_SIZE=0; fi

if [ "$QUEUE_SIZE" -gt "$MAX_REDIS_QUEUE" ]; then
    log_msg "🚦 ATASCO DETECTADO: $QUEUE_SIZE tareas en cola. Purgando Redis..."
    docker exec $C_REDIS redis-cli FLUSHALL
    cd /root/GoAnalisis && docker compose restart celery_node
    log_msg "✅ Cola liberada y worker reiniciado."
fi

# --- 4. VERIFICAR WORKER VIVO ---
if [ ! "$(docker ps -q -f name=$C_WORKER)" ]; then
    log_msg "❌ PÁNICO: El Worker no está corriendo. Levantando..."
    cd /root/GoAnalisis && docker compose up -d
    exit 0
fi

# --- 5. VERIFICAR RAM ---
RAM_USAGE=$(free | grep Mem | awk '{print $3/$2 * 100.0}')
RAM_USAGE=${RAM_USAGE%.*}

if [ "$RAM_USAGE" -gt "$MAX_RAM_USAGE" ]; then
    log_msg "⚠️ ALERTA: RAM Crítica ($RAM_USAGE%). Reiniciando Workers..."
    cd /root/GoAnalisis && docker compose restart celery_node celery_beat
    log_msg "✅ Reinicio por RAM completado."
    exit 0
fi

# --- 6. CAZADOR DE ZOMBIES (CHROME) ---
CHROME_COUNT=$(docker exec $C_WORKER ps aux | grep -c "chrome")

if [ "$CHROME_COUNT" -gt "$MAX_CHROME_PROCESSES" ]; then
    log_msg "🧟 PLAGA DETECTADA: $CHROME_COUNT procesos Chrome. Limpiando..."
    docker exec $C_WORKER pkill -f chrome || true
    docker exec $C_WORKER pkill -f chromedriver || true
    
    if [ "$CHROME_COUNT" -gt 50 ]; then
        log_msg "☢️ Demasiados zombies. Reinicio fuerte del contenedor."
        cd /root/GoAnalisis && docker compose restart celery_node
    fi
    log_msg "✅ Limpieza de zombies completada."
fi

# --- 7. HEARTBEAT (SIGNOS VITALES) ---
RECENT_LOGS=$(docker logs --since 15m $C_WORKER 2>&1 | grep "Monitor V4")
if [ -z "$RECENT_LOGS" ]; then
    log_msg "💀 SIGNOS VITALES PERDIDOS: Monitor inactivo por 15 min."
    log_msg "🚑 Reiniciando..."
    docker exec $C_WORKER pkill -f chrome || true
    cd /root/GoAnalisis && docker compose restart celery_node celery_beat
    log_msg "✅ Sistema reanimado."
fi

# Rotación de logs
tail -n 1000 $LOG_FILE > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" $LOG_FILE