#!/usr/bin/env bash
# stop_regression_gate.sh — Stop event
# Avisa se a suite de testes tem mais falhas do que o baseline pré-existente
# Não bloqueia (Stop não suporta exit 2), mas surfaça regressões

BASELINE_FAILURES=10  # ~10 falhas pré-existentes conhecidas (ref 2026-04-30)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if [[ ! -f "$PROJECT_ROOT/.venv/bin/python" ]]; then
  exit 0
fi

# Roda pytest de forma silenciosa e captura contagem de falhas
RESULT=$(cd "$PROJECT_ROOT" && .venv/bin/python -m pytest tests/ --tb=no -q 2>/dev/null | tail -5)

# Extrai número de falhas da última linha (ex: "15 failed, 771 passed in 12.3s")
FAILURES=$(echo "$RESULT" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' | head -1)

if [[ -z "$FAILURES" ]]; then
  # Sem falhas detectadas
  exit 0
fi

if [[ "$FAILURES" -gt "$BASELINE_FAILURES" ]]; then
  NEW=$(( FAILURES - BASELINE_FAILURES ))
  echo ""
  echo "⚠️  REGRESSION GATE: $FAILURES falhas detectadas (+$NEW acima do baseline de $BASELINE_FAILURES)"
  echo "   Corrija as regressões antes de commitar. Ver CLAUDE.md Regras 13-14."
  echo "   Run: .venv/bin/python -m pytest tests/ -v --tb=short"
  echo ""
fi

exit 0
