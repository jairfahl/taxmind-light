#!/usr/bin/env bash
# scripts/stress_monitor.sh — Monitoramento contínuo durante soak testing (Fase 5).
#
# Coleta métricas a cada 5 minutos: CPU, RAM, conexões PG, cache hit rate.
# Detecta: memory leak, connection pool exhaustion, degradação de latência.
#
# Execução (em paralelo com o locust):
#   Terminal 1: bash scripts/stress_monitor.sh
#   Terminal 2: locust -f tests/stress/locustfile_mock.py --users 5 --run-time 2h ...
#
# Parar: Ctrl+C
# Resultados: results/resource_log_YYYYMMDD_HHMMSS.txt

set -euo pipefail

INTERVAL="${MONITOR_INTERVAL:-300}"  # 5 minutos padrão
BASE_URL="${STRESS_BASE_URL:-https://orbis.tax}"

RESULTS_DIR="$(dirname "$0")/../results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$RESULTS_DIR/resource_log_${TIMESTAMP}.txt"

# ---------------------------------------------------------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
separator() { echo "------------------------------------------------------------" | tee -a "$LOG_FILE"; }
# ---------------------------------------------------------------------------

log "=== SOAK TEST MONITOR — Orbis.tax ==="
log "Intervalo: ${INTERVAL}s | Servidor: $BASE_URL"
log "Log: $LOG_FILE"
log "Parar: Ctrl+C"
separator

ITERATION=0

collect_metrics() {
    ITERATION=$((ITERATION + 1))
    log "=== COLETA #${ITERATION} ==="

    # Docker stats
    if command -v docker &>/dev/null; then
        log "Docker stats:"
        docker stats --no-stream --format \
            "{{.Name}}: CPU={{.CPUPerc}} MEM={{.MemUsage}} ({{.MemPerc}})" 2>/dev/null \
            | tee -a "$LOG_FILE" || log "  (docker stats falhou)"
    fi

    # Memória do sistema
    log "Sistema:"
    if command -v free &>/dev/null; then
        free -h | grep Mem | awk '{printf "  RAM: total=%s used=%s free=%s\n", $2, $3, $4}' \
            | tee -a "$LOG_FILE"
    elif command -v vm_stat &>/dev/null; then
        # macOS
        vm_stat | grep -E "Pages (free|active|inactive|wired)" | tee -a "$LOG_FILE"
    fi

    # Conexões PostgreSQL
    if command -v docker &>/dev/null; then
        PG_ACTIVE=$(docker exec tribus-ai-db psql -U taxmind -d taxmind_db -t \
            -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" 2>/dev/null \
            | tr -d ' ' || echo "N/A")
        PG_TOTAL=$(docker exec tribus-ai-db psql -U taxmind -d taxmind_db -t \
            -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null \
            | tr -d ' ' || echo "N/A")
        log "  PG conexões: ativas=${PG_ACTIVE} total=${PG_TOTAL} (max pool=20, max PG=200)"
    fi

    # Cache stats + latência via /v1/health
    HEALTH=$(curl -s --max-time 10 "${BASE_URL}/v1/health" 2>/dev/null || echo '{"status":"unreachable"}')
    HEALTH_STATUS=$(echo "$HEALTH" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    log "  Health: status=$HEALTH_STATUS"

    # Latência de /v1/health
    LATENCY=$(curl -s -o /dev/null -w "%{time_total}" --max-time 10 "${BASE_URL}/v1/health" 2>/dev/null || echo "timeout")
    log "  Latência /v1/health: ${LATENCY}s"

    # Alerta se latência alta
    if command -v bc &>/dev/null && [ "$LATENCY" != "timeout" ]; then
        if (( $(echo "$LATENCY > 2.0" | bc -l) )); then
            log "  ⚠️  ALERTA: latência /v1/health acima de 2s (${LATENCY}s)"
        fi
    fi

    # Disco
    DISK_PCT=$(df / 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%' || echo "N/A")
    log "  Disco /: ${DISK_PCT}% usado"
    if [ "$DISK_PCT" != "N/A" ] && [ "$DISK_PCT" -gt 90 ] 2>/dev/null; then
        log "  ⚠️  ALERTA: disco acima de 90% (${DISK_PCT}%)"
    fi

    separator
}

# Loop principal
trap 'log "Monitor encerrado após $ITERATION coletas. Log: $LOG_FILE"' EXIT

while true; do
    collect_metrics
    log "Próxima coleta em ${INTERVAL}s... (Ctrl+C para parar)"
    sleep "$INTERVAL"
done
