#!/bin/bash

# ==========================================
# GOANALISIS SENTINEL V2.0 - HEARTBEAT
# ==========================================

LOG_FILE="/root/GoAnalisis/sentinel.log"
MAX_RAM_USAGE=85
CONTAINER_WORKER="goanalisis_celery_node"
CONTAINER_BEAT="goanalisis_celery_beat"

# Función para registrar logs
log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> $LOG_FILE
}

log_msg "🛡 Iniciando Ronda de Guardia..."

# 1. VERIFICAR MEMORIA RAM
RAM_USAGE=$(free | grep Mem | awk '{print $3/$2 * 100.0}')
RAM_USAGE=${RAM_USAGE%.*}

if [ "$RAM_USAGE" -gt "$MAX_RAM_USAGE" ]; then
    log_msg "⚠ ALERTA: RAM Crítica ($RAM_USAGE%). Reiniciando Workers..."
    cd /root/GoAnalisis && docker compose restart celery_node celery_beat
    log_msg "✅ Reinicio por RAM completado."
    exit 0
fi

# 2. VERIFICAR QUE LOS CONTENEDORES ESTÉN VIVOS (STATUS UP)
if [ ! "$(docker ps -q -f name=$CONTAINER_WORKER)" ]; then
    log_msg "❌ PÁNICO: El Worker no está corriendo. Levantando..."
    cd /root/GoAnalisis && docker compose up -d
    exit 0
fi

# 3. VERIFICACIÓN DE SIGNOS VITALES (HEARTBEAT - NUEVO)
# Buscamos en los logs de los últimos 5 minutos si el Monitor dijo "Monitor V4..."
# Si no hay rastro, significa que se congeló.

RECENT_LOGS=$(docker logs --since 5m $CONTAINER_WORKER 2>&1 | grep "Monitor V4")

if [ -z "$RECENT_LOGS" ]; then
    log_msg "💀 SIGNOS VITALES PERDIDOS: El Monitor no ha dado señales en 5 minutos."
    log_msg "🚑 Aplicando desfibrilador (Reinicio forzado)..."
    
    # Matar procesos zombies antes de reiniciar
    docker exec $CONTAINER_WORKER pkill -f chrome || true
    
    cd /root/GoAnalisis && docker compose restart celery_node
    
    log_msg "✅ Sistema reanimado."
else
    # Si todo está bien, solo registramos un check positivo (opcional, para no llenar el log)
    # log_msg "💓 Latido detectado. Sistema saludable."
    :
fi

# Limpieza de logs viejos del Sentinel (Mantiene ultimas 1000 lineas)
tail -n 1000 $LOG_FILE > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" $LOG_FILE

