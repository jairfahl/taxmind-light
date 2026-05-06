#!/usr/bin/env bash
# stop_regression_gate.sh — Stop event
# Atualiza docs/IN_PROGRESS.md com contexto da sessão atual (rápido).
# Pytest completo deve ser rodado manualmente antes de commitar.

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IN_PROGRESS="$PROJECT_ROOT/docs/IN_PROGRESS.md"

cat > "$IN_PROGRESS" <<EOF
# Contexto da última sessão Claude Code
**Atualizado:** $(date '+%Y-%m-%d %H:%M:%S')

## Branch atual
$(cd "$PROJECT_ROOT" && git branch --show-current 2>/dev/null || echo "N/A")

## Últimas alterações
$(cd "$PROJECT_ROOT" && git diff --name-only HEAD 2>/dev/null | head -20 || echo "N/A")

## Arquivos não commitados
$(cd "$PROJECT_ROOT" && git status --short 2>/dev/null | head -20 || echo "N/A")
EOF

exit 0
