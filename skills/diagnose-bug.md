# Skill: Diagnóstico de Bug

## Camadas de Diagnóstico (ordem)

### 1. Banco de Dados
```bash
docker exec tribus-ai-db psql -U taxmind -d taxmind_db -c "\d <tabela>"
docker logs tribus-ai-db --tail=50
```

### 2. API FastAPI
```bash
docker logs tribus-ai-api --tail=100
# Ou localmente:
.venv/bin/python -m uvicorn src.api.main:app --reload --port 8020
```
- Verificar logs de erro (grep "ERROR\|Exception\|Traceback")
- Endpoints: `GET /v1/health` para sanidade básica

### 3. nginx (prod)
```bash
docker logs tribus-ai-nginx --tail=50
# Verificar upstream errors (502, 504)
```

### 4. Frontend Next.js
```bash
cd frontend && npm run dev
# Browser DevTools → Network tab → ver request/response
```

## Padrões de Bugs Conhecidos

| Sintoma | Causa Provável | Verificar |
|---------|---------------|-----------|
| 500 sem mensagem no frontend | `str(e)` genérico (SEC-05) | Logs da API |
| Modal travado silenciosamente | catch block ausente | `OnboardingModal.tsx` pattern |
| Variável de ambiente vazia | `restart` em vez de `force-recreate` | Recriar container |
| Build Next.js falha | `useSearchParams()` sem `<Suspense>` | grep useSearchParams |
| Migration FK falha | Tabela-pai não existe | `\d <tabela>` antes da migration |
| VARCHAR overflow silencioso | Campo muito curto | Verificar tipo da coluna |

## Testes de Diagnóstico

```bash
# Isolamento: testar sem LLM
.venv/bin/python -m pytest tests/unit/ -v --tb=short

# Com banco (requer container rodando)
.venv/bin/python -m pytest tests/integration/ -v --tb=short -k "test_db"

# Linters AST
.venv/bin/python -m pytest tests/linters/ -v --tb=short
```
