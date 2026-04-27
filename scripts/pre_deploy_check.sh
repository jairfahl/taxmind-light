#!/bin/bash
# =============================================================
# Tribus-AI — Checklist Pré-Deploy
# Executar ANTES de qualquer git push para produção.
# Uso: bash scripts/pre_deploy_check.sh
# =============================================================

set -e
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERROS=0
AVISOS=0

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; ERROS=$((ERROS+1)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; AVISOS=$((AVISOS+1)); }

echo ""
echo "============================="
echo " TRIBUS-AI — PRÉ-DEPLOY CHECK"
echo "============================="
echo ""

# ── 1. GIT ───────────────────────────────────────────────────
echo "1. Git"

UNTRACKED=$(git status --porcelain | grep "^??" | wc -l | tr -d ' ')
if [ "$UNTRACKED" -gt "0" ]; then
  fail "$UNTRACKED arquivo(s) não rastreados — podem não ir para produção:"
  git status --porcelain | grep "^??" | head -10
else
  ok "Nenhum arquivo não rastreado"
fi

MODIFIED=$(git status --porcelain | grep "^.M\| M" | wc -l | tr -d ' ')
if [ "$MODIFIED" -gt "0" ]; then
  warn "$MODIFIED arquivo(s) modificados não commitados"
  git status --porcelain | grep "^.M\| M" | head -10
else
  ok "Nenhuma modificação pendente de commit"
fi

# ── 2. TESTES BACKEND ────────────────────────────────────────
echo ""
echo "2. Testes Backend"

if .venv/bin/python -m pytest tests/ --tb=no -q 2>/dev/null | grep -q "passed"; then
  RESULT=$(.venv/bin/python -m pytest tests/ --tb=no -q 2>/dev/null | tail -1)
  ok "Suite passando: $RESULT"
else
  fail "Suite de testes com falha — não fazer deploy"
fi

# ── 3. BUILD FRONTEND ────────────────────────────────────────
echo ""
echo "3. Build Frontend"

if [ -d "frontend" ]; then
  cd frontend
  if npm run build --silent 2>/dev/null; then
    ok "npm run build: sucesso"
  else
    fail "npm run build: falhou — não fazer deploy"
  fi
  cd "$RAIZ"
else
  warn "Pasta frontend/ não encontrada — pular build"
fi

# ── 4. VARIÁVEIS DE AMBIENTE ─────────────────────────────────
echo ""
echo "4. Variáveis de Ambiente"

if [ -f ".env" ]; then
  if grep -q "LOCKFILE_MODE" .env 2>/dev/null; then
    MODE=$(grep "LOCKFILE_MODE" .env | cut -d= -f2 | tr -d '[:space:]')
    if [ "$MODE" = "WARN" ] || [ "$MODE" = "BLOCK" ]; then
      ok "LOCKFILE_MODE=$MODE (válido)"
    else
      fail "LOCKFILE_MODE=$MODE — valor inválido (use WARN ou BLOCK)"
    fi
  else
    ok "LOCKFILE_MODE não definido — usará default WARN"
  fi
else
  warn ".env não encontrado — verificar variáveis manualmente"
fi

# ── 5. SECRETS ───────────────────────────────────────────────
echo ""
echo "5. Secrets"

if git diff --cached --name-only 2>/dev/null | grep -q "\.env"; then
  fail "Arquivo .env sendo commitado — NUNCA commitar .env com secrets"
else
  ok "Nenhum .env no staging area"
fi

if grep -rq "ANTHROPIC_API_KEY\s*=\s*sk-ant" src/ 2>/dev/null; then
  fail "API key Anthropic hardcoded encontrada em src/ — remover imediatamente"
else
  ok "Nenhuma API key hardcoded detectada em src/"
fi

if grep -rq "VOYAGE_API_KEY\s*=\s*pa-" src/ 2>/dev/null; then
  fail "VOYAGE_API_KEY hardcoded encontrada em src/ — remover imediatamente"
else
  ok "Nenhuma Voyage API key hardcoded detectada em src/"
fi

# ── 6. LINTERS AST ───────────────────────────────────────────
echo ""
echo "6. Linters AST"

if .venv/bin/python -m pytest tests/linters/ --tb=no -q 2>/dev/null | grep -q "passed"; then
  LINTER_RESULT=$(.venv/bin/python -m pytest tests/linters/ --tb=no -q 2>/dev/null | tail -1)
  if echo "$LINTER_RESULT" | grep -q "failed"; then
    fail "Linters AST: $LINTER_RESULT"
  else
    ok "Linters AST: $LINTER_RESULT"
  fi
else
  warn "Linters AST: tests/linters/ não encontrado ou sem testes"
fi

# ── 7. RUFF ───────────────────────────────────────────────────
echo ""
echo "7. Ruff (Python linter — warning até Sprint 4)"

if .venv/bin/ruff check src/ --quiet 2>/dev/null; then
  ok "ruff: zero violações"
else
  warn "ruff: violações encontradas (não-bloqueante)"
fi

# ── RESULTADO ────────────────────────────────────────────────
echo ""
echo "============================="
if [ "$ERROS" -gt "0" ]; then
  echo -e "${RED}RESULTADO: $ERROS erro(s) — NÃO fazer deploy${NC}"
  echo "============================="
  echo ""
  exit 1
elif [ "$AVISOS" -gt "0" ]; then
  echo -e "${YELLOW}RESULTADO: $AVISOS aviso(s) — revisar antes de prosseguir${NC}"
  echo "============================="
  echo ""
  exit 0
else
  echo -e "${GREEN}RESULTADO: Tudo ok — pode fazer deploy${NC}"
  echo "============================="
  echo ""
  exit 0
fi
