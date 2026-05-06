# Skill: Novo Endpoint FastAPI

## Sequência Obrigatória

```
1. Migration SQL (se tocar banco) → ver skills/new-migration.md
2. Identificar o router correto em src/api/routers/ (auth, analyze, cases, outputs, ingest, observability, billing, admin, simuladores)
3. Implementar endpoint no router adequado
4. Teste em tests/integration/test_[feature]_endpoint.py
5. Atualizar ARCHITECTURE.md §10 se decisão arquitetural relevante
```

## Template de Endpoint

```python
# No arquivo src/api/routers/[modulo].py
from fastapi import APIRouter, Depends, HTTPException, Request
from src.api.limiter import limiter
from src.api.auth_api import verificar_acesso_tenant, verificar_usuario_autenticado
from src.api.helpers import _get_tenant_info_by_user
from src.db.pool import get_conn, put_conn

router = APIRouter()  # já existente no arquivo

@router.post("/v1/[recurso]", dependencies=[Depends(verificar_acesso_tenant)])
@limiter.limit("20/minute")
def meu_endpoint(request: Request, req: MeuRequest, current_user: dict = Depends(verificar_acesso_tenant)):
    """
    Descrição do endpoint.
    Retorna 400 se [condição de erro].
    """
    user_id = verificar_token_api(request)        # resolve user_id
    tenant_id = _get_tenant_id_from_user(user_id) # SEMPRE tenant_id, nunca user_id

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ... FROM tabela WHERE tenant_id = %s",
                (tenant_id,)
            )
            resultado = cur.fetchall()
        conn.commit()
        return {"data": resultado}
    except Exception as e:
        conn.rollback()
        logger.error("Erro em /v1/[recurso]: %s", e)
        raise HTTPException(status_code=500, detail="Erro interno")
    finally:
        put_conn(conn)
```

## Dependências de Auth/Billing

| Situação | Dependência |
|----------|-------------|
| Endpoint autenticado (padrão) | `Depends(verificar_token_api)` |
| Verifica assinatura ativa | `Depends(verificar_acesso_tenant)` → retorna HTTP 402 se expirado |
| Admin only | `Depends(verificar_admin)` |
| Rate limiting | `@limiter.limit("N/minute")` + `request: Request` obrigatório |

## Modelos Pydantic

```python
class MeuRequest(BaseModel):
    campo: str
    campo_opcional: Optional[str] = None

class MeuResponse(BaseModel):
    id: uuid.UUID
    resultado: str
```

## Checklist Obrigatório

- [ ] Filtra por `tenant_id` — nunca `user_id` diretamente
- [ ] `Depends(verificar_acesso_tenant)` se funcionalidade core
- [ ] Rate limiting com `@limiter.limit()`
- [ ] `try/finally` com `put_conn(conn)` garantido
- [ ] Erro retornado como `HTTPException` (nunca string crua)
- [ ] Migration SQL criada e commitada se ALTER/CREATE TABLE
- [ ] Swagger: `docs_url=None` em prod — endpoint não aparecerá em `/docs`

## Armadilhas

- **user_id ≠ tenant_id** — `ai_interactions` não tem `tenant_id`; joins via `users` table
- `docker compose restart` não re-lê `.env.prod` — usar `force-recreate`
- Campos UUID em `cases.id` e `outputs.id` (não integer, desde migration 126)
- `tipo_atuacao` é VARCHAR(100) — migration 122 (era VARCHAR(20), bug silencioso)
