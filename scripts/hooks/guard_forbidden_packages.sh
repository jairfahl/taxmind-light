#!/usr/bin/env bash
# guard_forbidden_packages.sh — PreToolUse(Write|Edit)
# Bloqueia imports de pacotes proibidos pelo stack do Orbis.tax
# Exit 2 = bloqueia a operação | Exit 0 = limpo

FORBIDDEN=(
  "langchain"
  "llamaindex"
  "llama_index"
  "langgraph"
  "supabase"
  "chromadb"
  "faiss"
  "pinecone"
  "streamlit"
)

# Lê o conteúdo enviado via stdin (Claude Code passa o conteúdo do arquivo)
CONTENT=$(cat)

for pkg in "${FORBIDDEN[@]}"; do
  if echo "$CONTENT" | grep -qiE "(import|from)\s+${pkg}"; then
    echo "🚫 HOOK BLOQUEADO: import de pacote proibido detectado: '${pkg}'"
    echo "   Stack permitido: FastAPI, PostgreSQL, pgvector, Voyage-3, Claude, Resend, Asaas"
    echo "   Ver CLAUDE.md § STACK ATIVO para a lista completa."
    exit 2
  fi
done

exit 0
