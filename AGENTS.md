# Orbis.tax — AGENTS.md
**Produto:** RAG de inteligência tributária (Reforma Tributária brasileira)
**Raiz:** `/Users/jairfahl/Downloads/tribus-ai-light/`
**API:** `src/api/main.py` (FastAPI, porta 8020)
**UI:** `frontend/` (Next.js 16 App Router, porta 3000 dev / 8521 Docker)

---

## Regras de Ouro — Nunca Violar

1. Ler `ARCHITECTURE.md` antes de qualquer tarefa
2. Ler cada arquivo que será modificado na íntegra — nunca assumir conteúdo
3. Declarar escopo: arquivos criados, modificados e os que não devem ser tocados
4. Verificar testes: `.venv/bin/python -m pytest tests/ -q` antes de começar
5. Um arquivo por vez — implementar, testar, confirmar antes de avançar
6. Arquivo fora do escopo declarado: parar e reportar ao PO
7. Secrets via variável de ambiente — nunca hardcoded
8. Nova feature que toca o banco: começar pela migration
9. NUNCA copiar PDFs para dentro de `/downloads/tribus-ai-light/`
10. Isolamento multi-tenant: filtrar por `tenant_id`, nunca por `user_id` diretamente
11. Frontend: nunca `style={{ color: "#..." }}` — usar `text-foreground`, `text-muted-foreground`
12. `useSearchParams()`: sempre envolver em `<Suspense>`
13. Rodar suite completa após implementar; zero regressões toleradas

---

## Stack

| Usar | Nunca usar |
|------|-----------|
| Python 3.12, FastAPI | LangChain / LlamaIndex / LangGraph |
| Next.js 16, Tailwind v4, shadcn/ui v2 | Supabase / ChromaDB / FAISS / Pinecone |
| PostgreSQL 16 + pgvector, psycopg2 direto | Qualquer ORM |
| Voyage-3 (embeddings), Claude Sonnet 4.6 | Streamlit (legado) |
| Resend (e-mail), Asaas (billing) | Stripe, PagSeguro, SendGrid |

---

## Protocolo

**6 passos — imutável:** P1 → P2 → P3 → P4 → P5 → P6
**P7, P8, P9 não existem.** Qualquer referência é erro legado.

## Pipeline

```
PTF → Adaptive Params → SPD routing → Retrieve → CRAG →
  [Multi-Query | Step-Back | HyDE] (mutuamente exclusivos) →
  Quality Gate → Budget Manager → LLM
```

---

## Antes de Qualquer Tarefa

```bash
cat /Users/jairfahl/Downloads/tribus-ai-light/ARCHITECTURE.md
.venv/bin/python -m pytest tests/ --tb=no -q 2>/dev/null | tail -3
ls /Users/jairfahl/Downloads/tribus-ai-light/TASKS_*.md
```

---

## Índice de Contexto

| Precisando de... | Ler |
|-----------------|-----|
| Domínio fiscal, taxonomia normas | `docs/DOMAIN_FISCAL.md` |
| Pipeline RAG, file paths, funções-chave | `docs/RAG_ARCHITECTURE.md` |
| Contrato JSON de resposta, anti-alucinação | `docs/CITATION_CONTRACT.md` |
| Protocolo P1→P6, campos obrigatórios | `docs/PROTOCOL_P1_P6.md` |
| Thresholds de qualidade, métricas | `docs/QUALITY_SCORECARD.md` |
| Multi-tenant, LGPD, legal hold | `docs/DATA_BOUNDARY.md` |
| Schema do banco (31 tabelas) | `docs/SCHEMA_REFERENCE.md` |
| Deploy VPS, comandos prod | `docs/DEPLOY_REFERENCE.md` |
| Feedback loop erro→regra→linter | `docs/FEEDBACK_LOOP.md` |
| Nova feature (processo) | `skills/new-feature.md` |
| Nova migration SQL | `skills/new-migration.md` |
| Checklist pré-deploy | `skills/pre-deploy.md` |
| Diagnóstico de bugs | `skills/diagnose-bug.md` |
| Modificar pipeline RAG | `skills/rag-pipeline.md` |
| Alterar protocolo P1→P6 | `skills/protocol-step.md` |
