#!/bin/bash
# =============================================================
# Orbis.tax — Quality Scorecard
# Computa scorecard de qualidade ao vivo.
# Uso: bash scripts/quality_scorecard.sh
# =============================================================

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

pass_count=0
fail_count=0
warn_count=0

pass() { echo -e "  ${GREEN}PASS${NC}  $1"; pass_count=$((pass_count+1)); }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; fail_count=$((fail_count+1)); }
warn() { echo -e "  ${YELLOW}WARN${NC}  $1"; warn_count=$((warn_count+1)); }
header() { echo -e "\n${BLUE}## $1${NC}"; }

echo ""
echo "================================================"
echo " ORBIS.TAX — QUALITY SCORECARD"
echo "================================================"

# ── 1. SUITE DE TESTES ──────────────────────────────
header "1. Suite de Testes"

PYTEST_OUT=$(.venv/bin/python -m pytest tests/unit/ tests/integration/ --tb=no -q 2>/dev/null | tail -1)
if echo "$PYTEST_OUT" | grep -q "passed"; then
  PASSED=$(echo "$PYTEST_OUT" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
  FAILED=$(echo "$PYTEST_OUT" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo "0")
  if [ "${FAILED:-0}" -gt "0" ]; then
    fail "pytest: $FAILED falhas — $PYTEST_OUT"
  else
    pass "pytest: $PASSED testes passando"
  fi
else
  fail "pytest: suite com falha — $PYTEST_OUT"
fi

# ── 2. LINTERS AST ──────────────────────────────────
header "2. Linters AST"

LINTER_OUT=$(.venv/bin/python -m pytest tests/linters/ --tb=no -q 2>/dev/null | tail -1)
if echo "$LINTER_OUT" | grep -q "passed" && ! echo "$LINTER_OUT" | grep -q "failed"; then
  pass "linters: todos passando — $LINTER_OUT"
elif echo "$LINTER_OUT" | grep -q "no tests ran"; then
  warn "linters: nenhum teste encontrado em tests/linters/"
else
  fail "linters: $LINTER_OUT"
fi

# ── 3. RUFF ─────────────────────────────────────────
header "3. Ruff (Python linter)"

if command -v ruff >/dev/null 2>&1 || .venv/bin/ruff --version >/dev/null 2>&1; then
  RUFF_CMD=".venv/bin/ruff"
  if ! $RUFF_CMD --version >/dev/null 2>&1; then
    RUFF_CMD="ruff"
  fi
  RUFF_OUT=$($RUFF_CMD check src/ --quiet 2>&1)
  RUFF_COUNT=$(echo "$RUFF_OUT" | grep -c "^" || echo "0")
  if [ -z "$RUFF_OUT" ]; then
    pass "ruff: zero violações"
  else
    warn "ruff: ${RUFF_COUNT} violação(ões) — (não-bloqueante até Sprint 4)"
  fi
else
  warn "ruff não instalado — execute: pip install ruff"
fi

# ── 4. INTEGRIDADE LOCKFILE ─────────────────────────
header "4. Integridade de Prompts (Lockfile)"

LOCKFILE_OUT=$(.venv/bin/python -c "
import os, sys
os.environ.setdefault('DATABASE_URL', 'postgresql://taxmind:taxmind123@localhost:5436/taxmind_db')
os.environ.setdefault('LOCKFILE_MODE', 'WARN')
try:
    from src.integrity.lockfile_manager import LockfileManager
    print('OK: módulo lockfile importado')
except Exception as e:
    print(f'WARN: {e}')
" 2>/dev/null)
if echo "$LOCKFILE_OUT" | grep -q "^OK"; then
  pass "lockfile: módulo importado com sucesso"
else
  warn "lockfile: $LOCKFILE_OUT"
fi

# ── 5. BUILD FRONTEND ────────────────────────────────
header "5. Build Frontend"

if [ -d "frontend" ]; then
  if npm run build --prefix frontend --silent 2>/dev/null; then
    pass "frontend: build OK"
  else
    fail "frontend: build falhou"
  fi
else
  warn "frontend/: diretório não encontrado"
fi

# ── SCORECARD FINAL ──────────────────────────────────
echo ""
echo "================================================"
echo " SCORECARD FINAL"
echo "================================================"
echo ""
echo "  Dimensão               | Status"
echo "  -----------------------|--------"
echo "  Suite de Testes        | $([ $fail_count -eq 0 ] && echo -e "${GREEN}PASS${NC}" || echo -e "${RED}FAIL${NC}")"
echo "  Linters AST            | $([ $fail_count -eq 0 ] && echo -e "${GREEN}PASS${NC}" || echo -e "${RED}FAIL${NC}")"
echo "  Ruff Python            | WARN (não-bloqueante)"
echo "  Lockfile               | WARN (requer DB)"
echo ""
echo "  PASS: $pass_count  FAIL: $fail_count  WARN: $warn_count"
echo ""

if [ "$fail_count" -gt "0" ]; then
  echo -e "${RED}STATUS: $fail_count dimensão(ões) com FAIL — resolver antes do deploy${NC}"
  exit 1
else
  echo -e "${GREEN}STATUS: Scorecard OK${NC}"
  exit 0
fi
