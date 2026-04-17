#!/usr/bin/env bash
# ============================================================
# install_token_savers.sh
# Instala RTK + Caveman para redução de tokens com Claude Code
# ============================================================
set -euo pipefail

PROJECT_ROOT="/Users/jairfahl/Downloads/tribus-ai-light"
CLAUDE_MD="$PROJECT_ROOT/CLAUDE.md"
CLAUDE_MD_BACKUP="$PROJECT_ROOT/CLAUDE.md.bak_token_savers"

# ── Cores ────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
fail() { echo -e "${RED}✗ $*${NC}"; exit 1; }

echo ""
echo "============================================================"
echo " Token Savers — RTK + Caveman"
echo "============================================================"
echo ""

# ── Pré-requisitos ───────────────────────────────────────────
command -v brew >/dev/null 2>&1 || fail "Homebrew não encontrado. Instale em https://brew.sh"
command -v claude >/dev/null 2>&1 || fail "Claude Code CLI não encontrado. Instale antes de continuar."
[ -f "$CLAUDE_MD" ] || fail "CLAUDE.md não encontrado em $PROJECT_ROOT"

# ── Backup do CLAUDE.md ──────────────────────────────────────
echo "→ Fazendo backup do CLAUDE.md..."
cp "$CLAUDE_MD" "$CLAUDE_MD_BACKUP"
ok "Backup salvo em: $CLAUDE_MD_BACKUP"
echo ""

# ════════════════════════════════════════════════════════════
# 1. RTK — Rust Token Killer
# Filtra output de comandos CLI (pytest, git, docker, psql...)
# antes de chegarem ao contexto do modelo
# ════════════════════════════════════════════════════════════
echo "------------------------------------------------------------"
echo " [1/2] RTK — Rust Token Killer"
echo "------------------------------------------------------------"

if command -v rtk >/dev/null 2>&1; then
    warn "RTK já instalado ($(rtk --version 2>/dev/null || echo 'versão desconhecida')). Pulando instalação."
else
    echo "→ Instalando RTK via Homebrew..."
    brew install rtk
    ok "RTK instalado: $(rtk --version)"
fi

echo ""
echo "→ Inicializando RTK (hook global)..."
echo "  Isso adicionará instruções ao CLAUDE.md do projeto."
echo ""

# Captura linhas do CLAUDE.md antes
LINES_BEFORE=$(wc -l < "$CLAUDE_MD")

rtk init --global

LINES_AFTER=$(wc -l < "$CLAUDE_MD")
LINES_ADDED=$((LINES_AFTER - LINES_BEFORE))

if [ "$LINES_ADDED" -gt 0 ]; then
    ok "RTK adicionou $LINES_ADDED linha(s) ao CLAUDE.md"
    echo ""
    echo "  Diff do que foi adicionado:"
    echo "  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"
    diff "$CLAUDE_MD_BACKUP" "$CLAUDE_MD" | grep "^>" | head -20 | sed 's/^/  /'
    echo "  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"
else
    warn "RTK não modificou o CLAUDE.md (pode já estar configurado ou usar outro mecanismo)."
fi
echo ""

# ════════════════════════════════════════════════════════════
# 2. Caveman — compressor de output do modelo
# Instrui o Claude a responder em estilo telegráfico (~65% menos tokens)
# ════════════════════════════════════════════════════════════
echo "------------------------------------------------------------"
echo " [2/2] Caveman — plugin Claude Code"
echo "------------------------------------------------------------"

echo "→ Instalando Caveman manualmente (não está no marketplace oficial)..."

SKILLS_DIR="$HOME/.claude/skills"
CAVEMAN_DIR="$SKILLS_DIR/caveman"
CAVEMAN_TMP="/tmp/caveman_install"

mkdir -p "$SKILLS_DIR"

# Clona repo temporariamente
rm -rf "$CAVEMAN_TMP"
git clone --depth=1 --quiet https://github.com/juliusbrussee/caveman "$CAVEMAN_TMP"

# Copia apenas o diretório do skill
rm -rf "$CAVEMAN_DIR"
cp -r "$CAVEMAN_TMP/skills/caveman" "$CAVEMAN_DIR"
rm -rf "$CAVEMAN_TMP"

ok "Caveman instalado em: $CAVEMAN_DIR"
echo "  Arquivos instalados:"
ls "$CAVEMAN_DIR" | sed 's/^/    /'
echo ""

# ════════════════════════════════════════════════════════════
# Validação final do CLAUDE.md
# ════════════════════════════════════════════════════════════
echo "------------------------------------------------------------"
echo " Validação"
echo "------------------------------------------------------------"

# Verifica que as seções críticas do CLAUDE.md continuam intactas
CHECKS=(
    "IDENTIDADE DO PROJETO"
    "REGRAS DE OURO"
    "PIPELINE COGNITIVO"
    "SCHEMA DO BANCO"
    "DEPLOY VPS"
)

ALL_OK=true
for check in "${CHECKS[@]}"; do
    if grep -q "$check" "$CLAUDE_MD"; then
        ok "CLAUDE.md — seção '$check' intacta"
    else
        warn "CLAUDE.md — seção '$check' não encontrada! Verifique o arquivo."
        ALL_OK=false
    fi
done

echo ""
if [ "$ALL_OK" = true ]; then
    ok "CLAUDE.md íntegro — todas as seções críticas preservadas"
else
    warn "Algumas seções não foram encontradas. Comparar com backup:"
    echo "  diff $CLAUDE_MD_BACKUP $CLAUDE_MD"
fi

# ════════════════════════════════════════════════════════════
# Resumo
# ════════════════════════════════════════════════════════════
echo ""
echo "============================================================"
echo " Instalação concluída"
echo "============================================================"
echo ""
echo "  RTK     — ativo automaticamente em pytest, git, docker, psql etc."
echo "  Caveman — ative por sessão com /caveman no Claude Code"
echo ""
echo "  Modos Caveman disponíveis:"
echo "    /caveman        → modo full (padrão)"
echo "    /caveman lite   → menos agressivo"
echo "    /caveman ultra  → máxima compressão"
echo "    stop caveman    → volta ao modo normal"
echo ""
echo "  Backup do CLAUDE.md original: $CLAUDE_MD_BACKUP"
echo "  Para restaurar: cp $CLAUDE_MD_BACKUP $CLAUDE_MD"
echo ""
echo "  Métricas RTK: rtk gain"
echo "============================================================"
