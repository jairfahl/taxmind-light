#!/usr/bin/env bash
# guard_suspense_searchparams.sh — PostToolUse(Write|Edit)
# Rejeita useSearchParams() sem Suspense no mesmo arquivo TSX/JSX
# Exit 2 = rejeita | Exit 0 = limpo

FILE_PATH="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"

if [[ "$FILE_PATH" != *.tsx && "$FILE_PATH" != *.jsx ]]; then
  exit 0
fi

if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# Verifica se useSearchParams está presente
if ! grep -q "useSearchParams" "$FILE_PATH"; then
  exit 0
fi

# Se useSearchParams presente, Suspense deve estar presente
if ! grep -q "Suspense" "$FILE_PATH"; then
  echo "🚫 HOOK BLOQUEADO: useSearchParams() sem <Suspense> em $FILE_PATH"
  echo "   Envolva o componente que usa useSearchParams() em <Suspense fallback={...}>."
  echo "   Sem Suspense, o next build falha. Ver CLAUDE.md Regra 12."
  exit 2
fi

exit 0
