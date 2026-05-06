#!/usr/bin/env bash
# scripts/stress_baseline.sh — Coleta métricas baseline no VPS antes do stress test.
#
# Execução (no VPS via SSH):
#   bash scripts/stress_baseline.sh
#
# Ou remotamente:
#   ssh orbis 'bash -s' < scripts/stress_baseline.sh
#
# Salva resultados em: results/baseline_YYYYMMDD_HHMMSS.txt

set -euo pipefail

RESULTS_DIR="$(dirname "$0")/../results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT="$RESULTS_DIR/baseline_${TIMESTAMP}.txt"

BASE_URL="${STRESS_BASE_URL:-https://orbis.tax}"
TEST_TOKEN="${STRESS_TEST_TOKEN:-}"  # JWT já obtido (opcional para chunks)

# ---------------------------------------------------------------------------
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$OUTPUT"; }
separator() { echo "================================================================" | tee -a "$OUTPUT"; }
# ---------------------------------------------------------------------------

log "=== BASELINE ORBIS.TAX — Gate U2 ==="
log "Servidor: $BASE_URL"
log "Arquivo: $OUTPUT"
separator

# ---------------------------------------------------------------------------
# 0.1 — Recursos do sistema (se executando no VPS)
# ---------------------------------------------------------------------------
log "--- RECURSOS DO SISTEMA ---"

if command -v docker &>/dev/null; then
    log "Docker stats:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" 2>/dev/null \
        | tee -a "$OUTPUT" || log "docker stats falhou (sem permissão?)"
else
    log "Docker não disponível neste host"
fi

log ""
log "Memória:"
free -h 2>/dev/null | tee -a "$OUTPUT" || vm_stat 2>/dev/null | tee -a "$OUTPUT" || log "free/vm_stat não disponível"

log ""
log "Disco:"
df -h / 2>/dev/null | tee -a "$OUTPUT" || log "df não disponível"

separator

# ---------------------------------------------------------------------------
# 0.2 — Latência dos endpoints (single request)
# ---------------------------------------------------------------------------
log "--- LATÊNCIAS BASELINE (single request) ---"

measure_latency() {
    local name="$1"
    local method="$2"
    local url="$3"
    shift 3
    local extra_args=("$@")

    log "Medindo $name..."
    local result
    result=$(curl -s -o /dev/null \
        -w "status=%{http_code} time_total=%{time_total}s time_connect=%{time_connect}s time_ttfb=%{time_starttransfer}s" \
        -X "$method" \
        "${extra_args[@]}" \
        "$url" 2>&1) || true

    echo "  $name: $result" | tee -a "$OUTPUT"
}

# Health check (sem auth)
measure_latency "GET /v1/health" "GET" "${BASE_URL}/v1/health"

# Chunks (com auth se disponível)
if [ -n "$TEST_TOKEN" ]; then
    measure_latency "GET /v1/chunks (top_k=5)" "GET" \
        "${BASE_URL}/v1/chunks?q=IBS+reforma+tributaria&top_k=5" \
        -H "Authorization: Bearer ${TEST_TOKEN}"

    measure_latency "GET /v1/cases" "GET" \
        "${BASE_URL}/v1/cases" \
        -H "Authorization: Bearer ${TEST_TOKEN}"
else
    log "  STRESS_TEST_TOKEN não configurado — pulando endpoints autenticados"
    log "  Para medir /v1/chunks e /v1/cases, configure:"
    log "  export STRESS_TEST_TOKEN=\$(curl -s -X POST ${BASE_URL}/v1/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"user@email.com\",\"senha\":\"senha\"}' | jq -r .access_token)"
fi

separator

# ---------------------------------------------------------------------------
# 0.3 — Conexões PostgreSQL ativas
# ---------------------------------------------------------------------------
log "--- CONEXÕES POSTGRESQL ---"

if command -v docker &>/dev/null; then
    PG_RESULT=$(docker exec tribus-ai-db psql -U taxmind -d taxmind_db -t \
        -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" 2>/dev/null || echo "N/A")
    PG_TOTAL=$(docker exec tribus-ai-db psql -U taxmind -d taxmind_db -t \
        -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null || echo "N/A")
    log "  Conexões ativas: ${PG_RESULT// /}"
    log "  Total conexões: ${PG_TOTAL// /}"
    echo "  Conexões ativas: ${PG_RESULT// /}" >> "$OUTPUT"
    echo "  Total conexões: ${PG_TOTAL// /}" >> "$OUTPUT"
else
    log "  Docker não disponível — pulando métricas PG"
fi

separator

# ---------------------------------------------------------------------------
# 0.4 — Cache stats (via /v1/health)
# ---------------------------------------------------------------------------
log "--- CACHE STATS ---"

HEALTH_BODY=$(curl -s "${BASE_URL}/v1/health" 2>/dev/null || echo "{}")
log "  Health response: $HEALTH_BODY" | head -c 500
echo "$HEALTH_BODY" | head -c 500 >> "$OUTPUT"
echo "" >> "$OUTPUT"

separator

log "Baseline salvo em: $OUTPUT"
log ""
log "Próximos passos:"
log "  1. Fase 1.2 — Load sem LLM:"
log "     locust -f tests/stress/locustfile_mock.py --users 20 --spawn-rate 2 --run-time 10m --headless --csv results/load_mock -H $BASE_URL"
log "  2. Fase 4 — Security tests:"
log "     STRESS_BASE_URL=$BASE_URL pytest tests/integration/test_security_manual.py -v -m security"
