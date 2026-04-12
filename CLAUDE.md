# Tribus-AI — Instruções para Claude Code
**Versão:** 2.2 | **Atualizado em:** Abril 2026

> Este arquivo é lido automaticamente pelo Claude Code a cada sessão.
> Não remover. Atualizar sempre que houver decisões arquiteturais novas.

---

## LEITURA OBRIGATÓRIA AO INICIAR QUALQUER SESSÃO

Execute esta sequência ANTES de qualquer tarefa, sem exceção:

```bash
# 1. Ler referência de arquitetura
cat /Users/jairfahl/Downloads/tribus-ai-light/ARCHITECTURE.md

# 2. Verificar estado atual dos testes
cd /Users/jairfahl/Downloads/tribus-ai-light
.venv/bin/python -m pytest tests/ --tb=no -q 2>/dev/null | tail -3

# 3. Verificar se há TASKS ativa para esta sessão
ls /Users/jairfahl/Downloads/tribus-ai-light/TASKS_*.md
```

Só prosseguir após concluir os 3 passos acima.

---

## IDENTIDADE DO PROJETO

- **Produto:** Tribus-AI — RAG de inteligência tributária (Reforma Tributária brasileira)
- **Raiz:** `/Users/jairfahl/Downloads/tribus-ai-light/`
- **Entry point UI:** `frontend/` (Next.js 16 App Router, porta 3000 dev / 8521 Docker)
- **Entry point API:** `src/api/main.py` (FastAPI, porta 8020)
- **Banco:** `postgresql://taxmind:taxmind123@localhost:5436/taxmind_db`
- **Container DB:** `tribus-ai-db`
- **PDFs das normas:** `/Users/jairfahl/Downloads/taxmind/Docs/Arquivos Upload/` — **read-only, NUNCA copiar**
- **Specs (.docx):** `/Users/jairfahl/Downloads/taxmind/Specs/`
- **ATENÇÃO:** Streamlit (`ui/app.py`) foi **substituído** pelo Next.js. Não modificar `ui/app.py`.

---

## REGRAS DE OURO — NUNCA VIOLAR

### Antes de codar
1. **Ler ARCHITECTURE.md** — sempre, sem exceção
2. **Ler cada arquivo que será modificado na íntegra** — nunca assumir conteúdo
3. **Declarar escopo** — listar arquivos criados, modificados e os que não devem ser tocados
4. **Verificar testes atuais** — `.venv/bin/python -m pytest tests/ -q` antes de começar

### Durante a execução
5. **Um arquivo por vez** — implementar, testar, confirmar antes de avançar
6. **Se surgir necessidade de tocar arquivo fora do escopo declarado: parar e reportar ao PO**
7. **Secrets via variável de ambiente** — nunca hardcoded
8. **Nova feature que toca o banco: começar pela migration** — sempre
9. **NUNCA copiar os PDFs para dentro de /downloads/tribus-ai-light/**

### Após implementar
10. **Rodar suite completa:** `.venv/bin/python -m pytest tests/ -v --tb=short`
11. **Zero regressões toleradas** — se um teste quebrou, corrigir antes de entregar

---

## STACK ATIVO

| O que usar | O que NUNCA usar |
|---|---|
| Python 3.12, FastAPI | LangChain / LlamaIndex |
| Next.js 16 App Router, React, Tailwind v4, shadcn/ui v2 | LangGraph |
| PostgreSQL 16 + pgvector (HNSW, dim 1024) | Supabase |
| Voyage-3 (embeddings) | ChromaDB / FAISS / Pinecone |
| Claude Sonnet 4.6 (LLM padrão) | Qualquer ORM |
| Docker, psycopg2 direto, Zustand, axios | Streamlit (legado) |

### Convenções Next.js (OBRIGATÓRIO ler antes de tocar o frontend)
- **App Router:** grupos `(app)` e `(auth)` — o prefixo do grupo NÃO aparece na URL
- **Tailwind v4:** config via CSS (`@theme inline`), sem `tailwind.config.ts`
- **NEXT_PUBLIC_*** são gravadas no build — override de env em runtime não funciona
- **API calls:** sempre via `@/lib/api` (axios com interceptors de `Authorization` e `X-Api-Key`)
- **Auth:** `useAuthStore` (Zustand + localStorage persist) — nunca acessar DB no cliente
- **Standalone output:** `outputFileTracingRoot: path.join(__dirname)` obrigatório em `next.config.ts`

### Convenções de Design (OBRIGATÓRIO)
- **Tokens:** `frontend/src/styles/tokens.css` é a fonte de verdade para cores e tipografia
- **Overrides shadcn/globais:** `frontend/app/globals.css` (`:root` block) — não editar tokens.css para ajustes visuais de UI
- **Variáveis de sombra/gradiente:** `--shadow-card`, `--shadow-card-hover`, `--gradient-primary` definidas em `globals.css`
- **Sidebar:** dark navy `#1a2f4e` — via `--color-bg-sidebar` em `globals.css`. Texto sempre branco/rgba
- **Dark mode:** `@media (prefers-color-scheme: dark)` em `globals.css` — sem biblioteca JS, sem `next-themes`
- **Logo:** `public/logo.png` = `TrisbusAI_Logo_Dark_v1.png` — adequado para fundos escuros e claros
- **Card.tsx:** prop `clickable` ativa hover lift; sem prop = apenas sombra estática
- **AnalysisLoading:** componente `"use client"` — depende de `useEffect` para mensagens rotativas

---

## PROTOCOLO DE DECISÃO

**6 passos — imutável:** P1 → P2 → P3 → P4 → P5 → P6
**P7, P8, P9 não existem.** Se aparecerem em algum arquivo, é erro legado.

---

## PIPELINE COGNITIVO — ORDEM OBRIGATÓRIA

```
PTF → Adaptive Params → SPD routing → Retrieve → CRAG →
  [Multi-Query > Step-Back > HyDE] → Quality Gate → Budget Manager → LLM
```

- Apenas UMA ferramenta RAG avançada por query (mutuamente exclusivas)
- Flag `_tool_activated` em `src/cognitive/engine.py` controla isso — **nunca remover**
- RAG: 0.7 cosine + 0.3 BM25, top_k=5, rerank_top_n=20

---

## SCHEMA DO BANCO (31 tabelas)

```sql
-- Corpus
normas                -- documentos fonte (EC, LC) + file_hash para dedup
chunks                -- trechos das normas com metadados jurídicos
embeddings            -- vetores voyage-3 (1024 dim) + índice HNSW

-- Consultas e IA
consultas             -- log de buscas
avaliacoes            -- validação manual de qualidade
ai_interactions       -- log de chamadas ao LLM + user_id + criticidade + tokens
ai_metrics_daily      -- métricas agregadas por dia
api_usage             -- consumo de API por tenant

-- Protocolo P1→P6
cases                 -- casos protocolares, 6 passos
case_steps            -- dados de cada passo por caso
case_state_history    -- audit trail de transições
carimbo_alerts        -- alertas de terceirização cognitiva

-- Outputs e documentos
outputs               -- documentos acionáveis gerados (5 classes) + legal_hold
output_aprovacoes     -- histórico de aprovações
output_stakeholders   -- visões por público-alvo
legal_hold_log        -- audit trail de ativações/desativações de Legal Hold

-- RAG e integridade
prompt_lockfiles      -- lockfiles de integridade de prompts (RDM-029)
prompt_baselines      -- baselines para comparação

-- Observability
drift_alerts          -- alertas de drift semântico
regression_results    -- resultados de testes de regressão

-- Monitor de fontes
monitor_fontes        -- fontes DOU/PGFN monitoradas
monitor_documentos    -- documentos detectados pelo monitor

-- Simulações
simulacoes_carga      -- simulações de carga tributária

-- Ciclo pós-decisão (P6) e aprendizado
monitoramento_p6      -- monitoramento ativo de decisões tomadas
heuristicas           -- heurísticas extraídas de casos encerrados (6 meses validade)
metricas_aprendizado  -- métricas mensais por usuário

-- Proatividade e padrões
padroes_uso           -- frequência de temas por usuário (G25)
sugestoes_silenciadas -- silenciamentos de sugestões proativas

-- Auth e billing
tenants               -- tenants com plano, trial e status de pagamento
users                 -- usuários + perfil onboarding (migration 117)
mau_records           -- Monthly Active Users por tenant/mês (DEC-08)
```

---

## ESTADO ATUAL DO PROJETO (Abril 2026)

| Entrega | Status |
|---|---|
| Sprint 1 — KB + RAG (1596 embeddings) | ✅ |
| Sprint 2 — Motor Cognitivo + FastAPI + Streamlit | ✅ |
| Sprint 3 — Protocolo P1→P6 + Carimbo + Testes adversariais | ✅ |
| Sprint 4 — Outputs Acionáveis (5 classes + stakeholders) | ✅ |
| Sprint 5 — Observability (métricas + drift + regression) | ✅ |
| Pós-Sprint — UX corporativa + ingest assíncrono + melhorias RAG | ✅ |
| RDM-020 HyDE | ✅ |
| RDM-024 Multi-Query | ✅ |
| RDM-025 Step-Back | ✅ |
| RDM-028 Context Budget Manager | ✅ |
| RDM-029 Prompt Integrity Lockfile | ✅ |
| Admin Module (auth + trial + painel admin) | ✅ |
| Onda C — P6 + Monitoramento + Aprendizado Institucional | ✅ |
| Onda D — Criticidade (G17) + MAU Metering (G26) + Proatividade (G25) | ✅ |
| Auditoria de código — pool unificado, credenciais sem fallback | ✅ |
| GTM A — WhatsApp CTA na landing page (DEC-11) | ✅ |
| GTM D — Badge "Memória de Decisão" na UI do Dossiê | ✅ |
| GTM E — Qualificação de tenant via progressive profiling (3 steps) | ✅ |
| **Migração UI: Streamlit → Next.js 16 (P01–P20)** | ✅ |
| **Segurança — SEC-01 CORS, SEC-02 JWT sem fallback** | ✅ |
| **Segurança — SEC-05 str(e) genérico, SEC-06 slowapi rate limit** | ✅ |
| **Segurança — SEC-07 MIME validation upload, SEC-08 X-Api-Key endpoints** | ✅ |
| **Frontend — Página Base de Normas (upload + monitor de fontes)** | ✅ |
| **Frontend — Modal de detalhes na aba Documentos** | ✅ |
| **Frontend — Mensagem amigável para consultas fora do escopo** | ✅ |
| **Plano de Testes QA — Sprint T1+T2 (integração + DB + isolamento)** | ✅ |
| **Correções de bugs — passo=3→2 alerta, P7→P5, criar_caso premissas, mocks get_conn** | ✅ |
| **Segurança — ISS-05 timeout por fonte no monitor, ISS-06 max_tokens=1200 stakeholders** | ✅ |
| **Frontend — Filtro/busca na página Documentos (ISS-16)** | ✅ |
| **Frontend — P6 exibe alertas de monitoramento ativos (ISS-18)** | ✅ |
| **Frontend — Data de revisão em guias.ts (ISS-20)** | ✅ |
| **UI Upgrade — Sidebar dark navy + tokens CSS + dark mode** | ✅ |
| **UI Upgrade — Login split-layout + AnalysisLoading spinner** | ✅ |
| **UI Upgrade — PainelGovernança Shield + BadgeCriticidade + Card sombra** | ✅ |
| **UI Upgrade — Botão gradiente + inputs focus accent + slider** | ✅ |
| **UI Upgrade — Layout mobile hamburguer + Logo dark v1** | ✅ |
| **Gate U2** | ⏳ Pendente |
| **Deploy VPS Hostinger** | ✅ Produção no ar — https://tribus-ai.com.br |
| **SEC-09 BYPASS_AUTH=False** | ✅ Confirmado: FastAPI ativo não tem BYPASS_AUTH. Zero UUIDs renomeados para _NULL_USER_SENTINEL (sentinela de integridade DB, não auth bypass) |
| **SEC-10 IDs sequenciais → UUID (cases/outputs)** | ⏳ Pendente (requer migration + backup) |

- **Suite de testes backend:** 647 passando, 0 falhas (referência pós Sprint-T1/T2 QA — Abril 2026)
- **Novos testes de integração:** test_auth_endpoints, test_simuladores_endpoints, test_protocol_endpoints, test_analyze_endpoint, test_multi_tenant_isolation, test_observability_api_new, test_admin_monitor, test_db_integrity
- **Última migration:** `117_onboarding_profile.sql`
- **Domínios registrados:** tribus-ai.com.br / tribus-ia.com.br
- **slowapi:** já está em `requirements.txt` — incluído no build Docker automaticamente
- **VOYAGE_API_KEY ativa:** `pa-GA8lfUZKLFS_9Xv3Xoh01cPJdKqsagDAivrqcJ5jsPG`

---

## DEPLOY VPS — Referência de Produção

- **VPS:** Hostinger — IP `69.62.100.24`
- **Domínio:** https://tribus-ai.com.br (SSL Let's Encrypt — expira 2026-07-11, renovação automática)
- **Arquivos de produção no VPS:** `/opt/tribus-ai-light/`
- **Arquivo de secrets:** `/opt/tribus-ai-light/.env.prod` (nunca commitar)
- **Stack prod:** `docker-compose.prod.yml` + nginx reverse proxy (porta 80+443)
- **Redeploy:** `cd /opt/tribus-ai-light && bash redeploy.sh`
- **Logs:** `docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f`
- **Admin padrão:** `admin@tribus-ai.com.br` / `Admin2026`
- **LOCKFILE_MODE no .env.prod:** deve ser `WARN` (não `ENFORCE` — valor inválido)
- **ASAAS_API_KEY no .env.prod:** deve iniciar com `$$` (não `$`) para escape do docker compose
- **Fix de senha via container:** `docker exec -i tribus-ai-api python3 < /tmp/fix_hash.py`

---

## PADRÃO PARA NOVA FEATURE

```
1. Ler ARCHITECTURE.md
2. Copiar TASKS_TEMPLATE.md → TASKS_[nome].md
3. Preencher: descrição, gate, escopo, ordem de execução
4. Apresentar ao PO para aprovação
5. Só então iniciar implementação
```

Template: `/Users/jairfahl/Downloads/tribus-ai-light/TASKS_TEMPLATE.md`

### Antes de qualquer git push para produção:

```bash
bash scripts/pre_deploy_check.sh
```

Zero erros = pode prosseguir. Qualquer erro = corrigir antes do push.
O script verifica: arquivos não rastreados, testes backend, build frontend,
LOCKFILE_MODE válido, e ausência de secrets hardcoded em src/.

---

## PADRÃO PARA MIGRATION SQL

```bash
# Verificar última migration
ls /Users/jairfahl/Downloads/tribus-ai-light/migrations/ | sort | tail -5
# Última: 100_users_table.sql → próxima: 101_descricao.sql

# Executar migration
docker exec -i tribus-ai-db \
    psql -U taxmind -d taxmind_db \
    < /Users/jairfahl/Downloads/tribus-ai-light/migrations/NNN_descricao.sql
```

---

## REGRA PERMANENTE — Testes

```
Testes unitários NUNCA fazem chamadas externas (LLM, embeddings, banco real).
Mockar SEMPRE: CognitiveEngine.analisar(), get_embedding(), MaterialidadeCalculator.calcular()
Testes que exigem chamada real ficam em tests/e2e/ e rodam MANUALMENTE.
conftest.py com autouse=True para todos os mocks de API externa.
```

---

## SINAIS DE ALERTA — PARAR E REPORTAR AO PO

Parar imediatamente e reportar se:
- Necessidade de modificar arquivo fora do escopo declarado no TASKS
- Suite de testes com regressão sem solução óbvia
- Dúvida sobre se uma decisão impacta o ARCHITECTURE.md
- Qualquer operação irreversível no banco (DROP, DELETE sem WHERE)
- Necessidade de adicionar dependência nova ao projeto

---

## ATUALIZAÇÃO DESTE ARQUIVO

Atualizar sempre que:
- Um novo módulo for criado
- Estado de uma entrega mudar (⏳ → ✅)
- Uma regra permanente for adicionada
- O número de referência da suite de testes mudar
