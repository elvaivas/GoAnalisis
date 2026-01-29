#!/bin/bash

# ==========================================
# GOANALISIS SENTINEL - GUARDIÁN DEL SISTEMA
# ==========================================
# Ejecutar cada hora en crontab del host
# ==========================================

LOG_FILE="/root/GoAnalisis/sentinel.log"
MAX_RAM_USAGE=85 # Porcentaje máximo permitido antes de reiniciar
CONTAINER_WORKER="goanalisis_celery_node"

echo "---------------------------------" >> $LOG_FILE
echo "🛡️ Sentinel Check: $(date)" >> $LOG_FILE

# 1. VERIFICAR MEMORIA RAM
# Obtenemos el % de uso de RAM
RAM_USAGE=$(free | grep Mem | awk '{print $3/$2 * 100.0}')
RAM_USAGE=${RAM_USAGE%.*} # Convertir a entero

echo "📊 Uso de RAM: $RAM_USAGE%" >> $LOG_FILE

if [ "$RAM_USAGE" -gt "$MAX_RAM_USAGE" ]; then
    echo "⚠️ ALERTA: Memoria crítica. Reiniciando Workers para liberar Chrome..." >> $LOG_FILE
    # Reiniciamos solo los nodos de trabajo pesados
    cd /root/GoAnalisis && docker compose restart celery_node
    echo "✅ Reinicio completado." >> $LOG_FILE
fi

# 2. MATAR PROCESOS ZOMBIE DE CHROME (DENTRO DEL CONTENEDOR)
# A veces Chrome se queda colgado aunque la tarea termine.
echo "🧹 Limpiando procesos Chrome huérfanos..." >> $LOG_FILE
docker compose exec -T celery_node pkill -f chrome || true
docker compose exec -T celery_node pkill -f undetected_chromedriver || true

# 3. VERIFICAR QUE LOS CONTENEDORES ESTÉN VIVOS
if [ $(docker ps -q -f name=$CONTAINER_WORKER) ]; then
    echo "✅ Worker Online." >> $LOG_FILE
else
    echo "❌ PÁNICO: Worker caído. Levantando..." >> $LOG_FILE
    cd /root/GoAnalisis && docker compose up -d celery_node
fi

echo "✅ Sentinel Finalizado." >> $LOG_FILE
