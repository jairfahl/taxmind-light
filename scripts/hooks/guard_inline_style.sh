#!/usr/bin/env bash
# guard_inline_style.sh — PostToolUse(Write|Edit)
# Rejeita uso de style={{ color: "..." }} em arquivos TSX/JSX
# Exit 2 = rejeita | Exit 0 = limpo

# Só atua em arquivos .tsx ou .jsx
FILE_PATH="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"

if [[ "$FILE_PATH" != *.tsx && "$FILE_PATH" != *.jsx ]]; then
  exit 0
fi

if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# Detecta style={{ color (hardcoded)
if grep -qE 'style=\{\{[^}]*color\s*:' "$FILE_PATH"; then
  echo "🚫 HOOK BLOQUEADO: style={{ color: ... }} detectado em $FILE_PATH"
  echo "   Use classes Tailwind: text-foreground, text-muted-foreground, text-primary, etc."
  echo "   Ver CLAUDE.md Regra 11 — Convenções de Design."
  exit 2
fi

exit 0
