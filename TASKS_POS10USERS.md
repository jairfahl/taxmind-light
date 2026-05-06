# TASKS — Plano Pós-10 Users
**Data:** 2026-05-06
**Responsável:** PO (Jair)
**Status:** [ ] Planejado | [ ] Em execução | [ ] Concluído | [ ] Bloqueado

---

## 1. Descrição

Hardening técnico pós-validação de mercado. Este plano só deve ser executado
após atingir 10 usuários pagantes ativos. Baseado no diagnóstico técnico de
2026-05-06 (engine review completo: código, arquitetura, segurança, infra,
integrações, funcionalidades).

Não contém nenhuma feature nova — é exclusivamente débito técnico estrutural e
segurança com potencial de impacto real em produção.

**Gatilho de execução:** 10 users pagantes confirmados no painel Asaas.

---

## 2. Gate de entrada

```
[ ] 10 users pagantes confirmados no Asaas
[ ] ARCHITECTURE.md lido
[ ] Suite de testes passando (sem novas regressões vs. baseline)
[ ] bash scripts/pre_deploy_check.sh passando
[ ] Backup VPS confirmado (Hostinger Snapshots ativo)
```

---

## 3. Tarefas — organizadas por prioridade e esforço

---

### P1-A — Corrigir `test_protocol_engine.py` mal categorizado
**Prioridade:** P1 | **Esforço:** 30 min | **Gate:** Antes de qualquer outra task

**Problema:** `tests/unit/test_protocol_engine.py` contém 7 testes que chamam
`ProtocolStateEngine.criar_caso()` e outras operações que fazem `get_conn()`
real. Quando o Docker não está rodando localmente, quebram. Mesmo padrão do
`test_retriever.py` (já corrigido em 2026-05-06).

**Solução:** Mover os 7 testes DB-dependentes para `tests/e2e/`. Os 19 testes
de lógica pura permanecem em `tests/unit/`.

**Critério de aceite:**
```
[ ] tests/unit/test_protocol_engine.py: 0 falhas com Docker off
[ ] tests/e2e/test_protocol_engine_db.py: testes DB-dependentes documentados
[ ] pytest tests/unit/ tests/linters/ → 0 falhas (baseline limpo)
```

**Arquivos:**
```
CRIADOS:   tests/e2e/test_protocol_engine_db.py
MODIFICADOS: tests/unit/test_protocol_engine.py (remove 7 testes DB-dependentes)
```

---

### P1-B — RLS como middleware obrigatório (Fase 2)
**Prioridade:** P1 | **Esforço:** 1–2 dias | **Gate:** Após P1-A

**Problema:** `set_tenant_id()` existe em `src/db/pool.py` mas não é chamado
automaticamente. Cada router é responsável por chamar — se esquecer, o RLS
não é ativado para aquela request. Com 10+ tenants ativos, um endpoint sem
`set_tenant_id` pode vazar dados entre tenants.

**Contexto técnico:**
- `src/db/pool.py:set_tenant_id()` — helper que executa `SET LOCAL app.tenant_id`
- Migrations 133+134 implementaram RLS em 4 tabelas (users, cases, mau_records, api_usage)
- ARCHITECTURE.md §10: "FASE 2 pendente" — enforcement via middleware

**Solução:** FastAPI middleware (ou dependency) que extrai `tenant_id` do JWT
e chama `set_tenant_id()` automaticamente na conexão antes de cada request,
sem depender de disciplina individual de cada router.

**Critério de aceite:**
```
[ ] Middleware ou dependency injeta set_tenant_id() em toda request autenticada
[ ] Testes de isolamento multi-tenant passam: tests/integration/test_multi_tenant_isolation.py
[ ] ADMIN continua com acesso irrestrito (bypass do middleware para perfil ADMIN)
[ ] ARCHITECTURE.md §10 atualizado: "FASE 2 concluída"
[ ] pytest tests/unit/ tests/integration/ tests/linters/ → 0 novas regressões
```

**Arquivos:**
```
MODIFICADOS: src/api/auth_api.py (adicionar injeção de tenant_id)
             src/db/pool.py (verificar assinatura de set_tenant_id)
VERIFICADOS (não tocar): src/api/routers/*.py (apenas validar que nenhum router
                          sofre duplo set_tenant_id)
```

**Atenção:** `ai_interactions` não tem `tenant_id` — não é afetado pelo RLS.
Joins por tenant continuam via `users`.

---

### P2-A — Rate limiting por tenant (não por IP)
**Prioridade:** P2 | **Esforço:** 1 dia | **Gate:** Após P1-B

**Problema:** `slowapi` limita por IP (`20/min` para `/v1/analyze`). Com múltiplos
tenants legítimos atrás do mesmo IP corporativo (NAT), um tenant pode ser
bloqueado pelo uso de outro. E um tenant malicioso com IP dedicado pode esgotar
a cota de análises sem restrição por conta.

**Solução:** Custom key function no `slowapi` que extrai `tenant_id` do JWT
para endpoints autenticados, com fallback para IP em endpoints públicos.

**Critério de aceite:**
```
[ ] /v1/analyze: rate limit por tenant_id (JWT), não por IP
[ ] /v1/upload: rate limit por tenant_id
[ ] Endpoints públicos (/v1/auth/login, /v1/webhooks/*): rate limit por IP (mantido)
[ ] Teste: dois tenants em IPs diferentes e iguais — limites independentes
[ ] ARCHITECTURE.md §10 atualizado
```

**Arquivos:**
```
MODIFICADOS: src/api/limiter.py (custom key function)
             src/api/routers/analyze.py (ajustar decorator @limiter.limit)
             src/api/routers/ingest.py (ajustar decorator)
CRIADOS:     tests/unit/test_rate_limit_per_tenant.py
```

---

### P2-B — Extrair módulos de `engine.py` (God Object)
**Prioridade:** P2 | **Esforço:** 2–3 dias | **Gate:** Após P2-A | **Risco: Alto**

**Problema:** `src/cognitive/engine.py` tem 1.521 linhas e 52 funções —
é o God Object do sistema. Orquestra pipeline, lockfile, prompts, LLM calls,
quality gate, loop iterativo, SPD, PTF, anti-alucinação, stakeholders e
budget manager num único arquivo. Qualquer alteração exige navegar ~1500 linhas.

**Escopo de extração (3 módulos candidatos):**

| Módulo a extrair | Funções-alvo em engine.py | Destino |
|---|---|---|
| Loop Quality Gate | `_executar_quality_loop`, constantes `_QUALITY_MAX_ITER`/`_QUALITY_TOPK_SCALE` | `src/cognitive/quality_loop.py` |
| Lockfile Boot | `verificar_lockfile_boot`, `_obter_prompts_sistema` | `src/cognitive/lockfile_boot.py` |
| Budget + Prompt Assembly | `_montar_contexto_prompt`, `_aplicar_budget_manager` | `src/cognitive/prompt_assembler.py` |

**engine.py permanece** como orquestrador — apenas delega para os módulos.
Lógica de negócio não muda, apenas reorganização.

**Critério de aceite:**
```
[ ] engine.py < 800 linhas após extração
[ ] 3 novos módulos em src/cognitive/ com testes unitários correspondentes
[ ] Linters AST continuam passando: pytest tests/linters/ → 12 testes OK
[ ] pytest tests/unit/ tests/integration/ → 0 novas regressões
[ ] ARCHITECTURE.md §2 e §4 atualizados com novos módulos
```

**Atenção:** Antes de iniciar, ler `docs/RAG_ARCHITECTURE.md` e
`docs/PROTOCOL_P1_P6.md`. Qualquer refactor em engine.py exige rodar
os linters AST depois de cada extração.

**Arquivos:**
```
CRIADOS:   src/cognitive/quality_loop.py + tests/unit/test_quality_loop.py
           src/cognitive/lockfile_boot.py + tests/unit/test_lockfile_boot.py
           src/cognitive/prompt_assembler.py + tests/unit/test_prompt_assembler.py
MODIFICADOS: src/cognitive/engine.py (apenas imports + delegação)
             ARCHITECTURE.md §2, §4
```

---

### P3-A — Alinhar Python runtime (3.11 → 3.12)
**Prioridade:** P3 | **Esforço:** 2–4h | **Gate:** Independente, janela de manutenção

**Problema:** `CLAUDE.md` e `ARCHITECTURE.md` especificam Python 3.12, mas
o `.venv` usa Python 3.11 (confirmado via traceback dos testes). Divergência
pode causar comportamento diferente em edge cases de tipagem e performance.

**Solução:** Recriar `.venv` com Python 3.12, verificar compatibilidade de
todas as dependências (`requirements.txt` / `requirements-dev.txt`).

**Atenção:** Fazer em janela com Docker off — não há impacto em produção
(VPS usa imagem Docker própria).

**Critério de aceite:**
```
[ ] python --version no .venv retorna 3.12.x
[ ] pytest tests/unit/ tests/linters/ → mesmo número de passando (sem regressão por mudança de runtime)
[ ] requirements.txt sem pacotes incompatíveis com 3.12
```

**Arquivos:**
```
NENHUM ARQUIVO de código alterado — só ambiente local
```

---

### P3-B — Alertas automáticos de downtime
**Prioridade:** P3 | **Esforço:** 2–4h | **Gate:** Independente

**Problema:** Não há monitoramento externo documentado. Downtime do nginx ou
dos containers é detectado apenas por usuário reclamando ou verificação manual.

**Solução candidata:** UptimeRobot (free tier, 5 min interval) monitorando
`https://orbis.tax/api/v1/health` com alerta por e-mail/WhatsApp.
Alternativa: cron job no VPS que chama o health e envia WA via Z-API se falhar.

**Critério de aceite:**
```
[ ] Alerta externo configurado para https://orbis.tax/api/v1/health
[ ] Notificação chega em até 5 min após queda
[ ] Documentado em docs/DEPLOY_REFERENCE.md
```

**Arquivos:**
```
MODIFICADOS: docs/DEPLOY_REFERENCE.md (adicionar seção Monitoramento Externo)
```

---

## 4. Sequência de execução recomendada

```
P1-A → P1-B → P2-A → P2-B → P3-A + P3-B (paralelas)
```

P2-B (engine.py) é a task de maior risco — executar apenas após P1 e P2-A
estabilizados em produção.

---

## 5. O que NÃO entra neste plano

| Item | Motivo da exclusão |
|---|---|
| ColBERT late interaction (reranking pós-HNSW) | Onda 2 — requer corpus maior para validar ganho |
| SLM híbrido (classificação/triage) | Onda 3 — requer volume de queries suficiente |
| P6 notificação proativa | Feature nova — fora do escopo de débito técnico |
| GraphRAG | Descartado — sem Gestor de Corpus para validar grafo |
| Migração token localStorage → cookie httpOnly | Trade-off consciente — CSP mitiga; prioridade baixa até ataque real |

---

## 6. Registro de execução

| Task | Início | Conclusão | Observações |
|---|---|---|---|
| P1-A | | | |
| P1-B | | | |
| P2-A | | | |
| P2-B | | | |
| P3-A | | | |
| P3-B | | | |

---

## 7. Decisões tomadas durante execução

[Registrar aqui qualquer desvio do plano, decisão em campo, ou descoberta
que impacte o ARCHITECTURE.md ou próximas features.]

---

## 8. Contexto — origem do plano

Gerado a partir do diagnóstico técnico de 2026-05-06 (sessão Claude Code).
Diagnóstico cobriu: qualidade de código, arquitetura, segurança, infraestrutura,
integrações e funcionalidades — atrelado ao DNA do produto (apoio à decisão
tributária, não feature creep).

Itens P0 já executados na mesma sessão:
- `test_retriever.py` movido para `tests/e2e/`
- Healthcheck adicionado ao container `ui` em `docker-compose.prod.yml`
- `@app.on_event("shutdown")` deprecated removido de `src/api/main.py`
- `load_dotenv()` duplicado removido de `src/api/main.py`
