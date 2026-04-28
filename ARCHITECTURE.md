# Orbis.tax — Architecture Reference
**Versão:** 2.8
**Atualizado em:** Abril 2026
**Mantido por:** PO (Jair)

> Este documento é leitura obrigatória antes de qualquer sessão de desenvolvimento.
> Claude Code deve ler este arquivo ANTES de ler qualquer outro arquivo do projeto.

---

## 1. Identidade do Projeto

Orbis.tax é um sistema RAG de inteligência tributária focado na Reforma Tributária
brasileira (EC 132/2023, LC 214/2025, LC 227/2026).

**Não é:** calculadora de tributos, ERP, gerador de obrigações acessórias.
**É:** sistema de apoio à decisão tributária com protocolo de 6 passos (P1→P6).

---

## 2. Raiz e Estrutura do Projeto

```
/Users/jairfahl/Downloads/tribus-ai-light/
├── auth.py                   ← Autenticação JWT + bcrypt (usado pela API)
├── admin.py                  ← Painel admin Streamlit (LEGADO — não modificar)
├── ARCHITECTURE.md           ← Este arquivo
├── CLAUDE.md                 ← Regras e contexto permanente para Claude Code
├── docker-compose.yml        ← Serviços: db (5436), api (8020), ui (8521→3000)
├── Dockerfile                ← Imagem do backend FastAPI
├── redeploy.sh               ← Script de redeploy (pull + build + up)
├── landing/
│   └── index.html            ← Landing page pública (trust signals + WhatsApp CTA + badge nav)
├── ui/                       ← LEGADO Streamlit — não modificar, substituído por frontend/
├── frontend/                 ← ⭐ UI ATIVA — Next.js 16 App Router
│   ├── app/
│   │   ├── route.ts              ← Redirect raiz → /analisar
│   │   ├── globals.css           ← Tailwind v4 + tokens shadcn + UI Upgrade overrides + dark mode + tm-card-warning/danger/tm-text-warning/danger
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx        ← Login com split-layout + link "Recuperar senha" no rodapé e no card de erro
│   │   │   ├── register/page.tsx     ← Cadastro: Zod senha forte + LGPD + asteriscos obrigatórios + SenhaRequisitos sempre visível
│   │   │   ├── verify-email/page.tsx ← Verificação de e-mail via token (com Suspense boundary)
│   │   │   ├── recuperar-senha/page.tsx ← Formulário de recuperação: envia e-mail via Resend; estados sucesso/naoEncontrado
│   │   │   └── redefinir-senha/page.tsx ← Redefinição com token URL; Zod senha forte; progresso 3s → /login
│   │   ├── (app)/
│   │   │   ├── layout.tsx        ← AuthGuard + Sidebar + hamburguer mobile + OnboardingModal
│   │   │   ├── analisar/         ← ⭐ Análise RAG principal (URL: /analisar) — CTA primário
│   │   │   ├── consultar/        ← Análise RAG alternativa (URL: /consultar)
│   │   │   ├── protocolo/        ← Protocolo P1→P6 (URL: /protocolo)
│   │   │   ├── simuladores/      ← Simuladores de carga tributária (URL: /simuladores)
│   │   │   ├── documentos/       ← Histórico de outputs + modal de detalhes (URL: /documentos)
│   │   │   ├── base-conhecimento/ ← Upload normas + Monitor de Fontes (URL: /base-conhecimento)
│   │   │   ├── assinar/          ← Plano Starter R$297/2 meses → R$497/mês — Asaas PIX/Cartão (URL: /assinar)
│   │   │   └── conta/page.tsx    ← Minha Conta: dados, status assinatura, CancelModal exit survey (URL: /conta)
│   │   ├── politica-privacidade/page.tsx ← Política de Privacidade LGPD — pública estática (URL: /politica-privacidade)
│   │   ├── termos-de-uso/page.tsx        ← Termos de Uso — pública estática (URL: /termos-de-uso)
│   │   ├── sla/page.tsx                  ← SLA — uptime/suporte/severidade/compensações — pública estática (URL: /sla)
│   │   └── admin/
│   │       ├── page.tsx          ← Painel admin redirect (ADMIN only) (URL: /admin)
│   │       ├── usuarios/page.tsx  ← Gestão de usuários ADMIN
│   │       ├── mailing/page.tsx   ← Painel de leads: filtros trial/convertido/cancelado + exportação CSV + desconto por tenant
│   │       └── consumo/page.tsx   ← Dashboard de consumo de API: resumo, por dia, por tenant, por serviço (ADMIN)
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx       ← Nav dark navy (#1a2f4e) + logo + avatar com iniciais
│   │   │   ├── AuthGuard.tsx     ← Redirect não-autenticados
│   │   │   ├── AdminGuard.tsx    ← Redirect não-ADMIN
│   │   │   └── OnboardingModal.tsx ← Progressive profiling step 0 + catch block com feedback de erro
│   │   ├── shared/
│   │   │   ├── Card.tsx          ← shadow-card + hover lift opcional (prop clickable)
│   │   │   ├── BadgeCriticidade.tsx ← px-4 py-1.5 + shadow colorida por nível
│   │   │   ├── PainelGovernanca.tsx ← Shield header + metric cards coloridos
│   │   │   └── AnalysisLoading.tsx  ← Spinner SVG marca + mensagens rotativas 3s
│   │   └── ui/                   ← shadcn/ui v2 (button, input, textarea, select…)
│   ├── lib/
│   │   ├── api.ts                ← axios instance com interceptors auth + x-api-key
│   │   └── utils.ts
│   ├── store/
│   │   └── auth.ts               ← Zustand store (user, token, logout) + localStorage persist
│   ├── src/styles/tokens.css     ← Design tokens — fonte de verdade para cores/tipografia
│   ├── types/index.ts            ← Tipos TypeScript globais
│   ├── public/
│   │   ├── logo.png              ← Logo para fundos claros
│   │   ├── logo-dark.png         ← Logo para sidebar navy e login
│   │   └── app-screenshot.png    ← Screenshot para landing page
│   ├── next.config.ts            ← output: standalone + outputFileTracingRoot
│   └── Dockerfile                ← Multi-stage build (node:20-alpine)
├── src/
│   ├── api/
│   │   ├── main.py               ← FastAPI — 40+ endpoints REST
│   │   └── auth_api.py           ← Dependency verificar_token_api (X-Api-Key)
│   ├── cognitive/
│   │   ├── engine.py             ← Orquestração cognitiva principal
│   │   ├── criticidade.py        ← Classificação de criticidade 3 níveis (G17)
│   │   ├── proatividade.py       ← Detecção de padrões + sugestões (G25)
│   │   ├── monitoramento_p6.py   ← Ciclo pós-decisão P6
│   │   └── aprendizado_institucional.py ← Extração de heurísticas (G24)
│   ├── rag/
│   │   ├── retriever.py, hyde.py, multi_query.py, step_back.py
│   │   ├── corrector.py, adaptive.py, ptf.py, spd.py
│   │   ├── decomposer.py, remissao_resolver.py
│   │   └── vigencia_checker.py
│   ├── billing/
│   │   ├── access.py, mau_tracker.py
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── scheduler.py          ← APScheduler jobs diários: check_trial_expiring (09h UTC) + check_inactive_tenants (09h30 UTC)
│   ├── integrity/
│   │   └── lockfile_manager.py
│   ├── email_service.py          ← Envio de e-mails via Resend API (verificação de conta + recuperação de senha)
│   ├── outputs/                  ← 5 classes de output + legal_hold.py + stakeholder_decomposer.py
│   ├── protocol/                 ← Engine P1→P6
│   ├── quality/                  ← Quality gate
│   ├── observability/            ← Métricas + drift + regression
│   ├── monitor/                  ← Monitor DOU/Planalto/CGIBS/NF-e/RFB/SIJUT2
│   │   ├── checker.py            ← verificar_todas_fontes, listar_pendentes
│   │   └── sources.py            ← Scrapers por tipo (6 checkers)
│   ├── ingest/                   ← Pipeline de ingestão assíncrona + dedup por file_hash
│   └── db/
│       └── pool.py               ← ThreadedConnectionPool — get_conn/put_conn (USAR SEMPRE)
├── migrations/
│   └── NNN_descricao.sql         ← Numeração sequencial obrigatória (última: 129_api_usage_tenant.sql)
├── docs/                         ← ⭐ Contexto estruturado para agentes (Harness Engineering)
│   ├── DOMAIN_FISCAL.md          ← Taxonomia EC132/LC214/LC227, PTF, terminologia IBS/CBS/IS
│   ├── RAG_ARCHITECTURE.md       ← Pipeline completo, file paths, embedding lock, Loop Depth QG
│   ├── CITATION_CONTRACT.md      ← Contrato JSON, M1-M4, THRESHOLDS_REGRESSAO
│   ├── PROTOCOL_P1_P6.md         ← 6 passos, campos obrigatórios, P4 guard, nota histórica
│   ├── QUALITY_SCORECARD.md      ← Dimensões, thresholds, módulos de qualidade
│   ├── DATA_BOUNDARY.md          ← Multi-tenant, LGPD, legal hold, secrets
│   ├── SCHEMA_REFERENCE.md       ← 31 tabelas com descrição
│   ├── DEPLOY_REFERENCE.md       ← VPS, comandos, armadilhas, variáveis obrigatórias
│   ├── FEEDBACK_LOOP.md          ← Processo erro→regra→linter
│   └── HARNESS_METRICS.md        ← Baseline vs meta, estado atual, roadmap Sprint 4
├── skills/                       ← ⭐ Guias de processo passo-a-passo
│   ├── new-feature.md            ← Processo de nova feature
│   ├── new-migration.md          ← Convenções e passos de migration SQL
│   ├── pre-deploy.md             ← Checklist completo pré-deploy
│   ├── diagnose-bug.md           ← Diagnóstico por camadas DB→API→nginx→Frontend
│   ├── rag-pipeline.md           ← Como modificar pipeline RAG sem quebrar invariantes
│   └── protocol-step.md          ← Como alterar protocolo respeitando P4/P5
├── AGENTS.md                     ← ⭐ Mapa de contexto curto para agentes (< 100 linhas)
├── pyproject.toml                ← ruff config (target py312, line-length 120)
├── requirements-dev.txt          ← ruff, pytest, pytest-cov (não incluir no Docker prod)
└── tests/
    ├── unit/                     ← test_[modulo].py + conftest.py (autouse mocks)
    │   └── test_iterative_quality_loop.py ← 17 testes do Loop Depth Quality Gate (sem LLM)
    ├── integration/              ← test_[fluxo].py + conftest.py (bypass_internal_auth)
    │   ├── conftest.py           ← fixtures: test_client, user_token, admin_token, bypass_internal_auth
    │   ├── test_auth_endpoints.py       ← TC-AUTH-01..08
    │   ├── test_analyze_endpoint.py     ← TC-ANALYZE-01..08 (LLM mockado)
    │   ├── test_simuladores_endpoints.py ← TC-SIM-01..07
    │   ├── test_protocol_endpoints.py   ← TC-PROT-01..11
    │   ├── test_multi_tenant_isolation.py ← TC-MT-01..05
    │   ├── test_observability_api_new.py ← TC-OBS-01..04
    │   ├── test_admin_monitor.py        ← TC-ADMIN-01, TC-MON-02..03
    │   ├── test_db_integrity.py         ← TC-DB-01..05 (constraints + HNSW)
    │   ├── test_api.py                  ← testes de integração gerais
    │   ├── test_outputs_api.py          ← testes de outputs C1..C5
    │   └── test_protocol_api.py         ← testes do protocolo P1→P6
    ├── linters/                  ← ⭐ Linters AST (Harness Engineering — Sprint 2)
    │   ├── test_embedding_lock.py       ← default voyage-3 em 3 arquivos
    │   ├── test_p4_guard.py             ← hipotese_gestor/decisao_final nunca via LLM
    │   ├── test_citation_contract.py    ← M1-M4, fundamento_legal, precisao_citacao>=0.90
    │   └── test_ptf_enforcement.py      ← data_referencia + vigencia_inicio/fim
    ├── adversarial/              ← testes adversariais Sprint 3
    └── e2e/                      ← testes E2E (rodam manualmente)
```

---

## 3. Stack — Tecnologias Ativas

| Camada | Tecnologia |
|---|---|
| Linguagem backend | Python 3.12 |
| API Backend | FastAPI (porta 8020 local / 8020 Docker) |
| Frontend | **Next.js 16 App Router** (porta 3000 dev / 8521 Docker) |
| Estado do cliente | Zustand + localStorage |
| HTTP client | axios com interceptors (lib/api.ts) |
| UI Components | shadcn/ui v2, Tailwind v4 (config CSS-only) |
| Banco | PostgreSQL 16 + pgvector (HNSW, dim 1024) |
| Embeddings | Voyage-3 |
| LLM | Claude Sonnet 4.6 |
| E-mail | Resend (domínio orbis.tax verificado, DKIM configurado) |
| Billing | Asaas (sandbox ativo) |
| Rate limiting | slowapi 0.1.9 + limits 3.6.0 |
| Infraestrutura | Docker Compose (4 serviços: db, api, ui, nginx) |
| Container DB | tribus-ai-db |
| DATABASE_URL local | postgresql://taxmind:taxmind123@localhost:5436/taxmind_db |
| DATABASE_URL Docker | postgresql://taxmind:taxmind123@db:5432/taxmind_db |

**Tecnologias EXPLICITAMENTE EXCLUÍDAS (nunca usar):**
- LangChain / LlamaIndex
- LangGraph
- Supabase
- ChromaDB / FAISS / Pinecone
- Streamlit (legado — não adicionar novas features)

---

## 4. Responsabilidades dos Módulos

| Módulo | Responsabilidade | O que NÃO faz |
|---|---|---|
| `frontend/app/(app)/` | Páginas da aplicação autenticada — consultar, protocolo, simuladores, documentos, base-conhecimento, assinar | Zero lógica tributária, zero chamadas diretas ao banco |
| `frontend/app/(auth)/login/` | Tela de login — chama `/v1/auth/login`, salva token no Zustand | Zero lógica de negócio |
| `frontend/app/(auth)/register/` | Cadastro com Zod (senha forte + LGPD) — chama `/v1/auth/register` | Zero lógica de negócio |
| `frontend/app/(auth)/verify-email/` | Verificação de e-mail com token — chama `/v1/auth/verify-email` com Suspense boundary | Zero lógica de negócio |
| `frontend/app/(app)/assinar/` | Seleção PIX/Cartão e chamada `/v1/billing/subscribe` — redireciona para invoice_url Asaas | Zero lógica de cobrança |
| `frontend/app/admin/mailing/` | Exibe leads com filtros, exporta CSV, aplica desconto por tenant | Zero lógica de autenticação |
| `frontend/app/admin/consumo/` | Dashboard de consumo de API: resumo geral, custo por dia, por tenant, por serviço/modelo (ADMIN only) | Zero lógica de billing |
| `frontend/components/layout/AuthGuard.tsx` | Redireciona não-autenticados para /login | Zero rendering de conteúdo |
| `frontend/lib/api.ts` | Instância axios com `Authorization: Bearer` + `X-Api-Key` em todos os requests | Zero lógica de domínio |
| `frontend/store/auth.ts` | Estado global de auth (user, token) com persistência localStorage | Zero chamadas diretas à API |
| `src/api/main.py` | 40+ endpoints REST, validação, serialização, rate limiting (slowapi) | Zero lógica de domínio — delega ao engine |
| `src/api/auth_api.py` | Dependency `verificar_token_api` — valida `X-Api-Key` em todos os endpoints protegidos | Zero lógica tributária |
| `src/email_service.py` | Envio de e-mail transacional via Resend: verificação, recuperação de senha, trial D-3/D-1, falha de pagamento, inatividade 14 dias | Zero lógica de negócio |
| `src/tasks/scheduler.py` | APScheduler jobs diários de retenção: check_trial_expiring (D-3/D-1), check_inactive_tenants (14 dias sem análise) | Zero lógica tributária |
| `frontend/app/(app)/conta/page.tsx` | Minha Conta: exibe dados, status assinatura, CancelModal com exit survey → POST /v1/billing/cancel | Zero lógica de cobrança |
| `frontend/app/politica-privacidade/` | Política de Privacidade LGPD — página pública estática sem auth | Zero lógica de aplicação |
| `frontend/app/termos-de-uso/` | Termos de Uso — página pública estática sem auth | Zero lógica de aplicação |
| `frontend/app/sla/` | SLA — uptime, suporte, severidade, compensações — página pública estática sem auth | Zero lógica de aplicação |
| `src/cognitive/engine.py` | Orquestração do pipeline cognitivo completo | Zero renderização UI |
| `src/rag/retriever.py` | Retrieval HNSW, adaptive tool chain, PTF | Zero lógica de negócio tributária |
| `auth.py` | JWT, bcrypt, autenticação, busca de usuário | Zero renderização UI |
| `src/cognitive/criticidade.py` | Classifica Crítico/Atenção/Informativo por termos detectados | Zero renderização |
| `src/cognitive/proatividade.py` | Detecta padrões de tags e gera sugestões de monitoramento | Zero rendering |
| `src/cognitive/monitoramento_p6.py` | Ativa/encerra monitoramento P6, verifica premissas | Zero rendering |
| `src/cognitive/aprendizado_institucional.py` | Extrai heurísticas de casos encerrados, expira com 6 meses | Zero rendering |
| `src/billing/mau_tracker.py` | Registra e consulta MAU por análise realizada (DEC-08) | Zero lógica tributária |
| `src/observability/usage.py` | Registra consumo de tokens (`registrar_uso`) com `tenant_id` para atribuição de custo por cliente | Zero lógica tributária |
| `src/outputs/legal_hold.py` | Ativa/desativa/verifica Legal Hold em outputs e interações | Zero rendering |
| `src/monitor/checker.py` | verificar_todas_fontes (concurrent, 30s timeout/fonte), listar_pendentes, atualizar_status | Zero rendering |
| `src/monitor/sources.py` | Scrapers por tipo: dou, planalto, cgibs, nfe, rfb, sijut2 | Zero persistência |
| `src/rag/remissao_resolver.py` | Resolve remissões entre normas e injeta no contexto (RAR) | Zero orquestração |
| `src/db/pool.py` | Pool de conexões psycopg2 — get_conn/put_conn | Zero lógica de negócio |
| `src/integrity/lockfile_manager.py` | Verificação de integridade de prompts (RDM-029) | Zero lógica tributária |

---

## 5. Pipeline Cognitivo — Ordem Obrigatória

```
PTF → Adaptive Params → SPD routing → Retrieve → CRAG →
  [Multi-Query > Step-Back > HyDE] (mutuamente exclusivos) →
  Quality Gate → Budget Manager (SUMMARY/FULL) → LLM
```

**Regra de exclusividade:** apenas UMA ferramenta RAG avançada por query.
Flag `_tool_activated` em `engine.py` controla isso. Nunca remover essa flag.

**Loop Depth Quality Gate (ACT-inspired — Abril 2026):**
O bloco Retrieve→CRAG→QualityGate é executado em loop iterativo por tipo de query:
- FACTUAL: 1 iteração (sem loop — velocidade crítica)
- INTERPRETATIVA: até 2 iterações
- COMPARATIVA: até 3 iterações

Critério de halting: `quality_gate.status == VERDE` → halt imediato.
Escala por iteração: `top_k × {1: 1.0, 2: 1.7, 3: 2.5}` via `dataclasses.replace()`.
Campo `quality_iterations: int` em `AnaliseResult` para observability.
Constantes em `engine.py`: `_QUALITY_MAX_ITER`, `_QUALITY_TOPK_SCALE`.

---

## 6. Protocolo de Decisão

**6 passos — imutável:**
- P1: Registrar & Classificar
- P2: Estruturar
- P3: Analisar
- P4: Hipotetizar
- P5: Decidir
- P6: Ciclo Pós-Decisão (Monitorar / Revisar / Aprender)

**P7, P8, P9 não existem.** Qualquer referência a eles é erro histórico da fase de design.

---

## 7. Regras Absolutas — Nunca Violar

### Segurança
- **Secrets via variável de ambiente.** Nunca hardcoded em código.
- **Valores com `$` no `.env.prod` devem usar `$$`** — o docker compose interpreta `$` como variável de shell.
- **Toda lógica de negócio e segurança: backend.** Streamlit captura intenção apenas.
- **Chamadas à Claude API: somente via engine.py.** Nunca do Streamlit diretamente.

### Isolamento Multi-Tenant
- **A unidade de isolamento é o TENANT (CNPJ), não o usuário individual.**
  - Um tenant pode ter N usuários; todos compartilham os mesmos cases, documentos e limites.
  - Nunca filtrar dados por `user_id` diretamente nas queries de negócio — sempre resolver para `tenant_id` primeiro.
  - Padrão: `_get_tenant_info_by_user(user_id, conn)` → retorna `tenant_id` → usar `tenant_id` no WHERE.
  - Exceção permitida: logs de auditoria e `ai_interactions` registram `user_id` para rastreabilidade individual.

### Banco de Dados
- **Toda nova feature que toca o banco começa por migration SQL versionada.**
  - Formato: `migrations/NNN_descricao.sql` (NNN = número sequencial de 3 dígitos)
  - Migration mais recente: `129_api_usage_tenant.sql` → próxima será `130_...`
- **Nunca alterar schema sem migration.** ALTER TABLE direto no banco sem arquivo = proibido.
- **Antes de migration com FK, verificar se tabela-pai existe** com `\d <tabela>` no container.

### Código
- **Nunca modificar um arquivo sem lê-lo completo primeiro.**
- **Nunca assumir o conteúdo de um arquivo — sempre ler.**
- **Novos módulos RAG:** criar em `src/rag/`, nunca dentro de `engine.py` diretamente.
- **Testes:** todo novo módulo tem `tests/unit/test_[modulo].py` correspondente.
- **Testes unitários:** NUNCA fazem chamadas externas (LLM, embeddings, banco real). Mockar sempre.
- **Cores no frontend:** NUNCA usar `style={{ color: "#XXXXXX" }}` hardcoded para texto — usar classes Tailwind semânticas (`text-foreground`, `text-muted-foreground`) que respeitam o dark mode via CSS vars.

### Deploy
- **`docker compose restart` NÃO relê `.env.prod`.** Após alterar variável de ambiente:
  `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate <serviço>`
- **`git status` antes de qualquer push** — arquivos não commitados não chegam ao VPS.

### Specs
- **Specs (.docx) nunca são editados diretamente.** Processo: unpack → editar XML → repack.
- **Nova versão de spec:** se v1.1 existe, a próxima é v1.2. Nunca sobrescrever.

### Gate de Qualidade
- **RDMs da Onda 1.5 estão implementados** (HyDE, Multi-Query, Step-Back, Context Budget, Lockfile). Não reimplementar.
- **667+ testes devem passar** após qualquer modificação (referência 2026-04-25).
  - Comando: `.venv/bin/python -m pytest tests/unit/ tests/integration/ tests/linters/ -v --tb=short`
  - Zero novas regressões toleradas — qualquer falha nova deve ser corrigida antes de entregar
  - Linters AST: `tests/linters/` — 12 testes (embedding lock, P4 guard, citation contract, PTF)

---

## 8. Padrão de Isolamento por Feature

Antes de implementar qualquer feature, identificar e declarar:

```
Arquivos que serão CRIADOS: [lista explícita]
Arquivos que serão MODIFICADOS: [lista explícita + seção específica]
Arquivos que NÃO devem ser tocados: [lista explícita]
```

Se a implementação exigir tocar arquivo fora do escopo declarado: **parar e reportar ao PO**.

---

## 9. Corpus Tributário

**Normas na base (não subir via "Adicionar Norma"):**
- EC 132/2023
- LC 214/2025
- LC 227/2026

**"Adicionar Norma":** exclusivo para normas novas não presentes na base.

---

## 10. Histórico de Decisões Arquiteturais

| Decisão | Escolha | Motivo |
|---|---|---|
| GraphRAG | ❌ Excluído | Sem Gestor de Corpus para validar grafo |
| LangGraph | ❌ Excluído | Over-engineering para protocolo fixo |
| CRAG web fallback | ❌ Excluído | Base fechada |
| Supabase | ❌ Excluído | Docker na VPS é suficiente |
| ColBERT late interaction | 🔄 Candidato futuro | Reranking pós-HNSW — Onda 2+ |
| SLM híbrido | 🔄 Onda 3 | 3B–7B params para classificação/triage (DEC-09) |
| Protocolo 9→6 passos | ✅ Consolidado | P7/P8/P9 fundidos em P6 |
| Admin Module | ✅ Implementado | JWT + bcrypt + trial + painel gestão (usuários + mailing) |
| Pool de conexões unificado | ✅ Implementado | get_conn/put_conn em todos os módulos — sem _get_conn() local |
| Criticidade 3 níveis | ✅ Implementado | Crítico/Atenção/Informativo — G17, migration 114 |
| MAU Metering por análise | ✅ Implementado | DEC-08: usuário ativo = análise realizada, não login — G26, migration 115 |
| Proatividade customizada | ✅ Implementado | Detecção de padrões de tags, sugestões não intrusivas — G25, migration 116 |
| Onboarding progressive profiling | ✅ Implementado | 3 steps: step 0 obrigatório, 1-2 opcionais — GTM E, migration 117 |
| Landing page WhatsApp CTA | ✅ Implementado | Botão WhatsApp em hero (pulse) + CTA final + footer — GTM A/DEC-11 |
| Landing page trust signals | ✅ Implementado | "1.596 normas indexadas · 3 leis-base curadas · Auditável P1→P6" abaixo do subtítulo |
| Badge "Memória de Decisão" | ✅ Implementado | Label no card do Dossiê na aba Documentos — GTM D |
| Migração UI Streamlit → Next.js 16 | ✅ Implementado | App Router, Tailwind v4, shadcn/ui v2, Zustand, axios — P01–P20 |
| SEC-01 CORS restrito | ✅ Implementado | allow_origins apenas orbis.tax + localhost:8521 + localhost:3000 |
| SEC-02 JWT_SECRET sem fallback | ✅ Implementado | RuntimeError se env não configurada |
| SEC-05 str(e) genérico | ✅ Implementado | 31 instâncias → "Erro interno. Tente novamente." |
| SEC-06 Rate limiting slowapi | ✅ Implementado | /v1/analyze: 20/min, /upload: 10/min, demais: 60/min |
| SEC-07 MIME validation upload | ✅ Implementado | magic bytes + limite 50MB server-side |
| SEC-08 X-Api-Key em todos os endpoints | ✅ Implementado | Dependency verificar_token_api em auth_api.py |
| Fluxo de cadastro com e-mail | ✅ Implementado | /register → Resend email → /verify-email?token= → /analisar |
| Validação de senha forte | ✅ Implementado | Zod (frontend) + Pydantic @field_validator (backend): 8+ chars, maiúsc, minúsc, número, especial |
| E-mail transacional via Resend | ✅ Implementado | Domínio orbis.tax verificado, DKIM configurado (split strings por limite DNS 255 chars) |
| Asaas billing integrado | ✅ Implementado | /assinar page + /v1/billing/subscribe + webhook /v1/webhooks/asaas — sandbox ativo |
| Admin mailing page | ✅ Implementado | Painel de leads com filtros trial/convertido/cancelado, exportação CSV, desconto inline por tenant |
| Dark mode CSS vars | ✅ Implementado | @media prefers-color-scheme dark em globals.css — texto usa text-foreground/text-muted-foreground |
| Monitor de Fontes Oficiais no frontend | ✅ Implementado | Verificar agora + docs pendentes + descartar — página base-conhecimento |
| Modal de detalhes na aba Documentos | ✅ Implementado | Conteúdo completo + stakeholders + materialidade + disclaimer |
| Mensagem amigável fora-de-escopo | ✅ Implementado | HTTP 400 → card âmbar com sugestão de consulta correta |
| ISS-05: Monitor com timeout por fonte | ✅ Implementado | ThreadPoolExecutor + 30s por fonte |
| ISS-06: max_tokens stakeholders 800→1200 | ✅ Implementado | Evita truncamento em queries complexas |
| ISS-16: Filtro/busca em Documentos | ✅ Implementado | useMemo filtrando por título, classe, conteúdo |
| ISS-18: Alertas drift em P6 | ✅ Implementado | P6Monitoramento.tsx busca /v1/observability/drift |
| ISS-20: Data de revisão em guias.ts | ✅ Implementado | ULTIMA_REVISAO = "Abril 2026" |
| UI Upgrade — Sidebar dark navy | ✅ Implementado | bg #1a2f4e, texto branco, active item gradient + borda 3px accent-vivid |
| UI Upgrade — globals.css tokens | ✅ Implementado | --shadow-card, --gradient-primary, --color-accent-vivid, dark mode CSS media query |
| UX/UI Redesign — contraste | ✅ Implementado | tm-card-warning/danger + tm-text-warning/danger; hardcoded colors removidos (Sidebar, analisar, FluxoDocumentacao, CalculadoraIS, SimuladorReestruturacao) |
| UX/UI Redesign — responsive | ✅ Implementado | Sidebar logo h-20 sm:h-24; GuiaSimulador grid-cols-1 sm:...; SimuladorReestruturacao grid-cols-2→lg:grid-cols-5 |
| UX/UI Redesign — landing page | ✅ Implementado | Pricing cards contraste; WhatsApp CTA → 5511972521970 (landing/index.html + public/landing-page.html) |
| Disclaimer obrigatório /analisar | ✅ Implementado | Texto estático entre saidas_stakeholders e CTADocumentar — ESP-06 §2.2 item 6 |
| UI Upgrade — Login split-layout | ✅ Implementado | Painel esquerdo navy (desktop) + bullets de valor + form branco direita |
| UI Upgrade — AnalysisLoading spinner | ✅ Implementado | SVG spinner marca + mensagens rotativas a cada 3s |
| UI Upgrade — PainelGovernança Shield | ✅ Implementado | Header com ícone Shield, cada métrica em card colorido |
| UI Upgrade — BadgeCriticidade polished | ✅ Implementado | px-4 py-1.5, icon size=16, font-bold, shadow colorida por criticidade |
| UI Upgrade — Card sombra + hover lift | ✅ Implementado | shadow-card em todos os cards; prop clickable ativa hover |
| UI Upgrade — Botão primário gradiente | ✅ Implementado | gradient-primary + scale on hover/active via CSS @layer components |
| UI Upgrade — Layout mobile hamburguer | ✅ Implementado | Sidebar deslizante + overlay + botão hamburguer |
| Logo Orbis.tax | ✅ Implementado | logo-dark.png na sidebar navy e login; logo.png para fundos claros |
| Sprint T1/T2 QA — suite limpa | ✅ Implementado | 667+ testes passando, 5 falhas conhecidas pré-existentes |
| redeploy.sh no repositório | ✅ Implementado | Script com branding Orbis.tax, versionado no git |
| Migrations 119–124 aplicadas em prod | ✅ Aplicado Abril 2026 | lgpd_consent, documento, marketing_consent, onboarding_varchar, session_id, desconto_percentual |
| Migration 122 aplicada em prod (tipo_atuacao VARCHAR(100)) | ✅ Abril 2026 | Corrigiu bug silencioso: "Empresa (uso interno)" (21 chars) estourava VARCHAR(20) → 500 sem catch → modal travado |
| Migration 125 reset_password_token | ✅ Abril 2026 | reset_token TEXT + reset_token_expires_at TIMESTAMPTZ em users; índice parcial WHERE reset_token IS NOT NULL |
| Recuperação de senha via e-mail | ✅ Implementado Abril 2026 | POST /v1/auth/forgot-password → Resend → /redefinir-senha?token= → POST /v1/auth/reset-password; token UUID 1h |
| Login: links de recuperação de senha | ✅ Implementado Abril 2026 | Link no card de erro de credenciais + links permanentes no rodapé (recuperar-senha · criar conta) |
| Register: UX melhorado | ✅ Implementado Abril 2026 | Asteriscos vermelhos em campos obrigatórios + SenhaRequisitos sempre visível (não só quando senha tem conteúdo) |
| OnboardingModal: error handling | ✅ Implementado Abril 2026 | Catch block explícito com estado `erro` — erros de API exibem mensagem em vez de travar silenciosamente |
| SEC-10 UUID cases/outputs | ✅ Aplicado Abril 2026 | Migration 126 executada em prod — cases.id e outputs.id são UUID; type annotations int→str nos schemas Pydantic |
| Loop Depth Quality Gate | ✅ Implementado Abril 2026 | Iteração adaptativa FACTUAL:1 / INTERPRETATIVA:2 / COMPARATIVA:3; halting em VERDE; top_k escala ×1.7/×2.5 |
| HyDE prompt densificado (H2) | ✅ Implementado Abril 2026 | Terminologia IBS/CBS/IS/fato gerador/SPED obrigatória; estrutura artigo→regra→vigência→fato gerador |
| Asaas webhook GET handler | ✅ Implementado Abril 2026 | GET /v1/webhooks/asaas retorna {"status":"ok"} para validação de URL no painel Asaas |
| Pricing promocional Starter | ✅ Implementado Abril 2026 | R$297 por 2 meses → R$497/mês; discount.type=FIXED + duracaoMeses=2 via Asaas API |
| Sprint Retenção — APScheduler | ✅ Implementado Abril 2026 | BackgroundScheduler via asynccontextmanager lifespan em main.py; 2 jobs diários UTC |
| Sprint Retenção — self-serve cancel | ✅ Implementado Abril 2026 | POST /v1/billing/cancel + CancelModal exit survey 4 opções — Asaas 404 = sucesso silencioso |
| Sprint Retenção — email falha pagamento | ✅ Implementado Abril 2026 | Webhook asaas past_due → _notificar_falha_pagamento → enviar_email_falha_pagamento |
| Páginas legais públicas | ✅ Implementado Abril 2026 | /politica-privacidade, /termos-de-uso, /sla fora dos grupos (app)/(auth) — sem AuthGuard |
| Landing page tagline refinada | ✅ Implementado Abril 2026 | "Feito para quem decide, não para quem experimenta" — menos agressiva, mesmo posicionamento |
| ai_interactions não tem tenant_id | ✅ Confirmado Abril 2026 | Tabela tem user_id; joins por tenant devem passar por users: JOIN users u ON u.id = ai.user_id WHERE u.tenant_id = t.id |
| Harness Engineering — docs/ + skills/ + linters | ✅ Implementado Abril 2026 | AGENTS.md (82L), CLAUDE.md reduzido (<200L), docs/ (10 arquivos), skills/ (6 arquivos), tests/linters/ (12 testes AST), pyproject.toml (ruff), scripts/quality_scorecard.sh |
| Migration 128 — cases.tenant_id | ✅ Abril 2026 | ALTER TABLE cases ADD COLUMN tenant_id UUID — vincula casos ao tenant para enforcement de limites por plano |
| Migration 129 — api_usage.tenant_id | ✅ Abril 2026 | ALTER TABLE api_usage ADD COLUMN tenant_id UUID — rastreio de consumo de API por cliente; índices em (tenant_id) e (tenant_id, created_at) |
| Admin Consumo API (/admin/consumo) | ✅ Implementado Abril 2026 | GET /v1/admin/consumo + frontend/app/admin/consumo/page.tsx — dashboard ADMIN: resumo geral + por dia + por tenant + por serviço/modelo; filtro por período (1–365 dias) |
| usage.py simplificado — tenant_id + sem alerta de crédito | ✅ Implementado Abril 2026 | Removidos CreditStatus, obter_status_creditos, API_CREDIT_LIMIT_USD; registrar_uso agora recebe tenant_id; /v1/credits simplificado (retorna total_gasto + detalhamento) |
| WhatsApp provider — Evolution API → Z-API | ✅ Implementado Abril 2026 | Evolution API (self-hosted) descartada: IP Hostinger bloqueado pelo WhatsApp no handshake Baileys. Migração para Z-API gerenciado (z-api.io). Interface `enviar_whatsapp_admin()` inalterada; vars EVOLUTION_* → ZAPI_INSTANCE_ID + ZAPI_TOKEN + ZAPI_SECURITY_TOKEN; sem container adicional em prod |
| engine.py propaga tenant_id pelo pipeline | ✅ Implementado Abril 2026 | _chamar_llm aceita tenant_id; _analisar_inner resolve tenant_id do user_id via SELECT antes do PTF; propagado para todas as chamadas LLM (SPD, MQ, SB, HyDE, loop quality) |

---

## 11. Atualização deste Documento

Este documento deve ser atualizado sempre que:
- Um novo módulo for criado
- Uma decisão arquitetural for tomada ou revertida
- A estrutura de pastas mudar
- Uma regra absoluta for adicionada

**Quem atualiza:** PO (Jair) via este chat (Specs e Arquitetura).
**Como atualizar:** gerar prompt neste chat → executar no terminal.
