# Orbis.tax

Plataforma de inteligência tributária com RAG e protocolo de decisão para a Reforma Tributária brasileira (EC 132/2023, LC 214/2025, LC 227/2026).

**Produção:** https://orbis.tax

---

## O que é o Orbis.tax?

O Orbis.tax é uma plataforma de suporte à decisão tributária composta por dois modos de uso:

- **Consulta rápida** — perguntas pontuais sobre a Reforma Tributária, respondidas com fundamentação legal via RAG
- **Protocolo de Decisão (6 passos)** — processo estruturado para análise, recomendação e decisão sobre cenários tributários complexos

---

## Funcionalidades

| Página | Função |
|--------|--------|
| **Analisar** | Análise RAG principal com criticidade, fundamentação legal e ação recomendada |
| **Consultar** | Consulta rápida à base de conhecimento |
| **Protocolo** | Protocolo de 6 passos: classificar → estruturar → analisar → hipótese → decidir → monitorar |
| **Simuladores** | Simuladores de carga tributária (IS, Split Payment, Reestruturação, Carga RT, Créditos IBS/CBS) |
| **Documentos** | Geração de documentos acionáveis (Alerta, Nota de Trabalho, Recomendação Formal, Dossiê, Compartilhamento) com visões por stakeholder |
| **Base de Conhecimento** | Upload de PDFs (INs, Resoluções, Pareceres), dedup por hash MD5, ingestão assíncrona, monitor de fontes oficiais |
| **Admin** | Gestão de usuários (ADMIN only): criar/ativar/desativar, redefinir senhas, monitorar consumo, mailing com filtros e exportação CSV |
| **Assinar** | Página de assinatura do plano Starter (R$497/mês) via Asaas (PIX ou Cartão) |

### Fluxo de Cadastro

1. Usuário acessa `/register` e preenche o formulário (nome, e-mail, senha forte, empresa, LGPD)
2. API cria conta com `email_verificado = FALSE`, dispara e-mail via Resend
3. Usuário clica no link de verificação (`/verify-email?token=...`)
4. Conta ativada, usuário redirecionado para `/analisar`
5. Trial de 7 dias inicia a partir do `primeiro_uso`

**Senha forte obrigatória:** mínimo 8 caracteres, maiúscula, minúscula, número e caractere especial. Validação Zod no frontend + Pydantic no backend.

### RAG Avançado

| Técnica | Ativação | Referência |
|---------|----------|------------|
| **Multi-Query Retrieval** | Query coloquial detectada (sem termos técnicos) | RDM-024 |
| **Step-Back Prompting** | Alta especificidade (CNAE, NCM, regime) em queries INTERPRETATIVA/COMPARATIVA | RDM-025 |
| **HyDE** | Score vetorial < 0.72 em queries INTERPRETATIVA | RDM-020 |
| **Context Budget Manager** | Toda query — modo SUMMARY (FACTUAL) ou FULL (INTERPRETATIVA/COMPARATIVA) | RDM-028 |
| **Prompt Integrity Lockfile** | Boot do engine — SHA-256 dos prompts com modo BLOCK/WARN | RDM-029 |

As ferramentas RAG avançadas (Multi-Query, Step-Back, HyDE) são mutuamente exclusivas por query, com prioridade nesta ordem.

---

## Stack Técnica

| Componente | Tecnologia |
|------------|------------|
| Linguagem backend | Python 3.12+ |
| API | FastAPI (uvicorn, porta 8020 local) |
| Frontend | Next.js 16 App Router + Tailwind v4 + shadcn/ui v2 |
| Estado do cliente | Zustand + localStorage persist |
| HTTP client | axios com interceptors (Bearer + X-Api-Key) |
| Banco de dados | PostgreSQL 16 + pgvector (Docker) |
| Embeddings | voyage-3 (1024 dim) via VoyageAI API |
| LLM | claude-sonnet-4-6 |
| Autenticação | JWT (HS256, 8h) + bcrypt rounds=12 |
| Perfis | ADMIN (visão global) / USER (isolamento de tenant) |
| Busca vetorial | pgvector com índice HNSW (cosine, m=16, ef=64) |
| Re-ranking | BM25 em memória (score híbrido: 0.7 cosine + 0.3 BM25) |
| RAG avançado | Adaptive Retrieval: Multi-Query > Step-Back > HyDE |
| Rate limiting | slowapi 0.1.9 |
| Integridade | Prompt Integrity Lockfile (SHA-256, BLOCK/WARN) |
| E-mail transacional | Resend (domínio orbis.tax verificado) |
| Billing | Asaas (sandbox ativo; produção aguarda contrato) |
| Infra local | Docker Compose (db + api + ui) |
| Infra produção | Docker Compose (db + api + ui + nginx) + VPS Hostinger |

---

## Setup Local (Desenvolvimento)

### 1. Variáveis de ambiente

```bash
cp .env.example .env
# Preencher:
# ANTHROPIC_API_KEY, VOYAGE_API_KEY
# JWT_SECRET, API_INTERNAL_KEY
# RESEND_API_KEY (para e-mail de verificação)
# ASAAS_API_KEY (sandbox: prefixar $$ se valor começa com $)
```

### 2. Subir com Docker Compose

```bash
docker compose up -d --build
docker compose ps   # aguardar todos "Up" e DB "healthy"
```

Serviços:
- **db** — PostgreSQL 16 + pgvector (porta 5436)
- **api** — FastAPI/uvicorn (porta 8020)
- **ui** — Next.js (porta 8521)

Acesse `http://localhost:8521` no navegador.

### 3. Aplicar migrations (primeira vez)

```bash
for f in $(ls migrations/*.sql | sort); do
  docker exec -i tribus-ai-db psql -U taxmind -d taxmind_db < "$f"
done
```

Admin padrão criado pela migration 100: `admin@orbis.tax`
Última migration: `124_tenant_desconto.sql`

### 4. Ingestão inicial dos PDFs (opcional)

```bash
python src/ingest/run_ingest.py
```

### 5. Rodar os testes

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
# 667+ testes passando (referência Abril 2026 + novos testes de simuladores)
```

### Comandos úteis

```bash
docker compose down                        # parar todos os serviços
docker compose up -d                       # subir novamente
docker compose restart api                 # reiniciar apenas a API
docker compose logs api --tail 50          # logs da API
```

---

## Deploy Produção

### Requisitos no VPS
- Docker + Docker Compose Plugin
- Certificado SSL via Let's Encrypt

### Primeiro deploy (uma vez)

```bash
git clone https://github.com/<org>/tribus-ai-light.git /opt/tribus-ai-light
cd /opt/tribus-ai-light
docker volume create taxmind_pgdata
cp .env.prod.example .env.prod
# Preencher .env.prod com valores reais
# ATENÇÃO: valores com $ devem usar $$ (escape docker compose)
certbot certonly --standalone -d orbis.tax -d www.orbis.tax
bash deploy.sh
```

### Redeploy

```bash
cd /opt/tribus-ai-light && bash redeploy.sh
```

### Logs em produção

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f
```

### Após alterar .env.prod

```bash
# NUNCA usar restart — não relê env_file
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate api
```

---

## Arquitetura

```
PDF (upload via UI ou PDF_SOURCE_DIR)
      │
      ▼
  loader.py ──► pdfplumber ──► texto extraído
      │
      ▼
 chunker.py ──► chunking jurídico hierárquico (artigo → parágrafo → sliding window)
      │
      ▼
 embedder.py ──► voyage-3 (batch 32, retry 3x)
      │
      ▼
PostgreSQL/pgvector ──► HNSW index (1024 dim)
      │
      ▼
 retriever.py ──► busca vetorial + BM25 re-ranking + deduplicação por artigo
      │
      ▼
 Adaptive Retrieval ──► Multi-Query | Step-Back | HyDE (mutuamente exclusivos)
      │
      ▼
 Budget Manager ──► SUMMARY/FULL por tipo de query + limite de tokens/chunks
      │
      ▼
 engine.py (cognitivo) ──► Claude LLM com anti-alucinação (M1-M4)
      │
      ▼
Next.js UI ◄──► FastAPI (40+ endpoints REST)
      │
      ▼
nginx ──► HTTPS ──► orbis.tax
```

---

## Estrutura de Pastas

```
tribus-ai-light/
├── Dockerfile                     # Imagem backend FastAPI
├── docker-compose.yml             # Dev: db + api + ui
├── docker-compose.prod.yml        # Prod: db + api + ui + nginx
├── deploy.sh                      # Deploy inicial (build + up)
├── redeploy.sh                    # Redeploy (pull + build + up)
├── nginx/nginx.conf               # Reverse proxy HTTPS
├── .env.prod.example              # Template de variáveis de produção
├── auth.py                        # Autenticação JWT + bcrypt
├── frontend/                      # ⭐ UI ATIVA — Next.js 16 App Router
│   ├── app/
│   │   ├── route.ts               # Redirect raiz → /analisar (autenticado) ou landing
│   │   ├── globals.css            # Tailwind v4 + tokens shadcn + dark mode CSS vars
│   │   ├── (auth)/
│   │   │   ├── login/             # Login split-layout (navy + form branco)
│   │   │   ├── register/          # Cadastro com validação forte de senha + LGPD
│   │   │   └── verify-email/      # Verificação de e-mail via token
│   │   ├── (app)/                 # Rotas autenticadas
│   │   │   ├── analisar/          # Análise RAG principal
│   │   │   ├── consultar/         # Consulta rápida
│   │   │   ├── protocolo/         # Protocolo P1→P6
│   │   │   ├── simuladores/       # Simuladores tributários
│   │   │   ├── documentos/        # Outputs acionáveis + modal de detalhes
│   │   │   ├── base-conhecimento/ # Upload + monitor fontes
│   │   │   └── assinar/           # Assinatura do plano (Asaas PIX/Cartão)
│   │   └── admin/
│   │       ├── page.tsx           # Painel admin (redirect)
│   │       ├── usuarios/          # Gestão de usuários
│   │       └── mailing/           # Painel de leads com filtros e exportação CSV
│   ├── components/
│   │   ├── layout/                # AuthGuard, Sidebar, AdminGuard, OnboardingModal
│   │   ├── protocolo/             # P1..P6 components
│   │   ├── simuladores/           # Simuladores components
│   │   └── shared/                # Card, Badge, PainelGovernança, AnalysisLoading
│   └── lib/api.ts                 # axios instance (Bearer + X-Api-Key)
├── src/
│   ├── api/main.py                # FastAPI — 40+ endpoints REST
│   ├── cognitive/engine.py        # Motor cognitivo (Claude LLM)
│   ├── email_service.py           # Envio de e-mails via Resend API
│   ├── rag/                       # retriever, hyde, multi_query, step_back, spd…
│   ├── outputs/                   # 5 classes de output + stakeholders
│   ├── protocol/                  # Engine P1→P6 + carimbo
│   ├── observability/             # Métricas + drift + regression
│   ├── monitor/                   # Monitor DOU/PGFN/RFB/SIJUT2
│   ├── ingest/                    # Pipeline ingestão assíncrona
│   └── db/pool.py                 # ThreadedConnectionPool
├── migrations/                    # NNN_descricao.sql (última: 124_tenant_desconto.sql)
└── tests/
    ├── unit/                      # Mocks obrigatórios (sem chamadas externas)
    ├── integration/               # Testes de integração com TestClient
    ├── adversarial/               # Testes adversariais Sprint 3
    └── e2e/                       # Rodam manualmente
```

---

## Protocolo de Decisão — 6 Passos

| Passo | Nome | Responsável |
|-------|------|-------------|
| P1 | Registrar & Classificar | Usuário |
| P2 | Estruturar riscos e dados | Usuário |
| P3 | Análise tributária | Orbis.tax (RAG + LLM) |
| P4 | Posição do gestor (hipótese) | Usuário |
| P5 | Decidir | Usuário (com recomendação Orbis.tax) |
| P6 | Ciclo Pós-Decisão | Usuário |

---

## API — Principais Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/v1/health` | Status do sistema |
| POST | `/v1/auth/login` | Autenticação (público) |
| POST | `/v1/auth/register` | Cadastro de novo usuário (público) |
| GET | `/v1/auth/verify-email` | Verificação de e-mail via token |
| GET | `/v1/auth/me` | Dados do usuário autenticado |
| PATCH | `/v1/auth/onboarding` | Atualização de step de onboarding |
| POST | `/v1/analyze` | Consulta RAG + LLM |
| GET | `/v1/chunks` | Busca de chunks |
| POST | `/v1/ingest/upload` | Upload assíncrono de PDF |
| POST | `/v1/ingest/check-duplicate` | Verificação de duplicidade |
| GET | `/v1/ingest/jobs/{job_id}` | Polling de ingestão |
| POST | `/v1/cases` | Criar caso |
| GET | `/v1/cases` | Listar casos |
| POST | `/v1/cases/{id}/steps/{passo}` | Submeter passo |
| POST | `/v1/outputs` | Gerar documento acionável |
| POST | `/v1/outputs/{id}/aprovar` | Aprovar documento |
| GET | `/v1/observability/metrics` | Métricas de uso |
| GET | `/v1/observability/drift` | Detecção de drift |
| POST | `/v1/monitor/verificar` | Verificar fontes oficiais |
| GET | `/v1/billing/mau` | MAU por tenant/mês |
| POST | `/v1/billing/subscribe` | Criar assinatura Asaas |
| POST | `/v1/webhooks/asaas` | Webhook de eventos Asaas |
| GET | `/v1/admin/mailing` | Leads com filtro de status |
| GET | `/v1/admin/mailing/export` | Exportar CSV de leads |
| PATCH | `/v1/admin/tenants/{id}/desconto` | Aplicar desconto a tenant |
| GET | `/v1/admin/usuarios` | Listar usuários (ADMIN) |
| POST | `/v1/admin/usuarios` | Criar usuário (ADMIN) |

---

## Autenticação

| Campo | Detalhe |
|-------|---------|
| Perfis | `ADMIN` (visão global) / `USER` (isolamento de tenant) |
| Autenticação | JWT HS256, expiração 8h |
| Senhas | bcrypt rounds=12 + validação forte (8+ chars, maiúscula, minúscula, número, especial) |
| Trial | 7 dias a partir do primeiro uso (`primeiro_uso`) |
| Verificação de e-mail | Token UUID via Resend; conta inativa até verificar |
| Admin padrão | admin@orbis.tax |

---

## Variáveis de Ambiente Necessárias

| Variável | Uso |
|----------|-----|
| `ANTHROPIC_API_KEY` | Chamadas ao Claude Sonnet 4.6 |
| `VOYAGE_API_KEY` | Geração de embeddings voyage-3 |
| `JWT_SECRET` | Assinatura de tokens JWT |
| `API_INTERNAL_KEY` | Autenticação X-Api-Key |
| `DATABASE_URL` | Conexão com PostgreSQL |
| `RESEND_API_KEY` | E-mails transacionais (verificação de conta) |
| `ASAAS_API_KEY` | Billing via Asaas ($$aact_... no .env.prod — escape docker compose) |
| `LOCKFILE_MODE` | `WARN` ou `BLOCK` — nunca outro valor |

---

## Regras do Projeto

- PDFs **nunca** são copiados para este repositório
- Único vector store: pgvector (sem LangChain, FAISS, ChromaDB)
- Embedding model: voyage-3 exclusivamente
- Índice HNSW obrigatório
- Testes unitários nunca fazem chamadas externas (mocks obrigatórios)
- Anti-alucinação: 4 mecanismos (M1-M4) em toda resposta do LLM
- Secrets via variável de ambiente — nunca hardcoded
- Toda query de USER em `ai_interactions` filtrada por `user_id` (isolamento de tenant)
- Streamlit (`ui/app.py`) é **legado** — não adicionar features, substituído pelo Next.js
- `docker compose restart` **não relê** `.env.prod` — usar `up -d --force-recreate` após mudar env
- Valores com `$` no `.env.prod` devem usar `$$` (escape do docker compose)
