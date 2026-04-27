# Harness Engineering — Métricas de Efetividade

## Baseline vs Meta

| Métrica | Baseline (antes do harness) | Meta (pós-Sprint 4) |
|---------|----------------------------|---------------------|
| Contexto carregado por sessão | ~51KB (CLAUDE.md + ARCHITECTURE.md) | ~8–13KB (AGENTS.md + 1–2 docs/) |
| Invariantes com linter | 0 | 5+ (embedding, P4, citation, PTF, ruff) |
| Cobertura de "regras derivadas" | 0% | >= 50% das lições em LESSONS_LEARNED |
| CI pipeline | Inexistente | pre_deploy_check.sh (5→7 checks) |
| CLAUDE.md linhas | 369 | < 200 |
| ARCHITECTURE.md linhas | 409 | Inalterado (referência viva) |

---

## Estado Atual (Abril 2026 — pós Sprint 1–3)

| Dimensão | Status |
|----------|--------|
| AGENTS.md criado | ✅ 82 linhas |
| docs/ criado (9 arquivos) | ✅ DOMAIN_FISCAL, RAG_ARCHITECTURE, CITATION_CONTRACT, PROTOCOL_P1_P6, QUALITY_SCORECARD, DATA_BOUNDARY, SCHEMA_REFERENCE, DEPLOY_REFERENCE, FEEDBACK_LOOP |
| CLAUDE.md reduzido | ✅ < 200 linhas |
| skills/ criado (6 arquivos) | ✅ new-feature, new-migration, pre-deploy, diagnose-bug, rag-pipeline, protocol-step |
| pyproject.toml (ruff config) | ✅ |
| tests/linters/ (4 linters) | ✅ embedding lock, P4 guard, citation contract, PTF enforcement |
| scripts/quality_scorecard.sh | ✅ 5 dimensões |
| pre_deploy_check.sh + linters + ruff | ✅ seções 6 + 7 adicionadas |

---

## Plano Sprint 4

### 4.1 Promover ruff para bloqueante

Após corrigir violações existentes em `src/`:
```bash
# pre_deploy_check.sh — mudar seção 7 de warn() para fail()
```

### 4.2 Novos Linters (Candidatos)

| Regra | Arquivo | Impacto |
|-------|---------|---------|
| `style={{ color: "#` em TSX | `test_hardcoded_color.py` | Previne regressão de dark mode |
| `useSearchParams` sem `<Suspense>` | `test_suspense_boundary.py` | Previne falha de build Next.js |
| `docker-compose.prod.yml` em tests/ | `test_no_prod_refs_in_tests.py` | Segurança |

### 4.3 GitHub Actions CI (fecha D-08 de LESSONS_LEARNED)

**Depende de decisão do PO.** Trigger: "Ao iniciar Onda 2".

Arquivo: `.github/workflows/ci.yml`

Steps propostos:
1. ruff check src/
2. pytest tests/unit/ tests/integration/ tests/linters/
3. npm run build (frontend)

---

## Como Verificar Que o Harness Funciona

```bash
# 1. Scorecard completo
bash scripts/quality_scorecard.sh

# 2. Suite completa (incluindo linters)
.venv/bin/python -m pytest tests/ -v --tb=short

# 3. Verificar tamanho dos arquivos-chave
wc -l AGENTS.md CLAUDE.md docs/*.md

# 4. Testar P4 guard (smoke test)
# Adicionar temporariamente em src/: hipotese_gestor = analisar(q)
# → test_p4_guard.py deve FALHAR
# → reverter

# 5. Testar embedding lock (smoke test)
# Mudar default em retriever.py para "voyage-4"
# → test_embedding_lock.py deve FALHAR
# → reverter
```
