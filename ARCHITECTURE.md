# Tribus-AI — Architecture Reference
**Versão:** 2.2
**Atualizado em:** Abril 2026
**Mantido por:** PO (Jair)

> Este documento é leitura obrigatória antes de qualquer sessão de desenvolvimento.
> Claude Code deve ler este arquivo ANTES de ler qualquer outro arquivo do projeto.

---

## 1. Identidade do Projeto

Tribus-AI é um sistema RAG de inteligência tributária focado na Reforma Tributária
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
├── landing/
│   └── index.html            ← Landing page pública (CTAs trial + WhatsApp)
├── ui/                       ← LEGADO Streamlit — não modificar, substituído por frontend/
├── frontend/                 ← ⭐ UI ATIVA — Next.js 16 App Router
│   ├── app/
│   │   ├── page.tsx              ← Redirect → /analisar
│   │   ├── globals.css           ← Tailwind v4 + tokens shadcn + UI Upgrade overrides + dark mode
│   │   ├── (auth)/
│   │   │   └── login/page.tsx    ← Login com split-layout (painel navy + form branco)
│   │   ├── (app)/
│   │   │   ├── layout.tsx        ← AuthGuard + Sidebar + hamburguer mobile + OnboardingModal
│   │   │   ├── analisar/         ← ⭐ Análise RAG principal (URL: /analisar) — CTA primário
│   │   │   ├── consultar/        ← Análise RAG alternativa (URL: /consultar)
│   │   │   ├── protocolo/        ← Protocolo P1→P6 (URL: /protocolo)
│   │   │   ├── simuladores/      ← Simuladores de carga tributária (URL: /simuladores)
│   │   │   ├── documentos/       ← Histórico de outputs + modal de detalhes (URL: /documentos)
│   │   │   └── base-conhecimento/ ← Upload normas + Monitor de Fontes (URL: /base-conhecimento)
│   │   └── admin/
│   │       └── page.tsx          ← Painel admin (ADMIN only) (URL: /admin)
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx       ← Nav dark navy (#1a2f4e) + logo + avatar com iniciais
│   │   │   ├── AuthGuard.tsx     ← Redirect não-autenticados
│   │   │   ├── AdminGuard.tsx    ← Redirect não-ADMIN
│   │   │   └── OnboardingModal.tsx ← Progressive profiling step 0
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
│   ├── public/logo.png           ← TrisbusAI_Logo_Dark_v1.png (dark — adequado para sidebar navy e login)
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
│   ├── integrity/
│   │   └── lockfile_manager.py
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
│   └── NNN_descricao.sql         ← Numeração sequencial obrigatória (última: 117)
└── tests/
    ├── unit/                     ← test_[modulo].py + conftest.py (autouse mocks)
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
| Rate limiting | slowapi 0.1.9 + limits 3.6.0 |
| Infraestrutura | Docker Compose (3 serviços: db, api, ui) |
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
| `frontend/app/(app)/` | Páginas da aplicação autenticada — consultar, protocolo, simuladores, documentos, base-conhecimento | Zero lógica tributária, zero chamadas diretas ao banco |
| `frontend/app/(auth)/login/` | Tela de login — chama `/v1/auth/login`, salva token no Zustand | Zero lógica de negócio |
| `frontend/components/layout/AuthGuard.tsx` | Redireciona não-autenticados para /login | Zero rendering de conteúdo |
| `frontend/lib/api.ts` | Instância axios com `Authorization: Bearer` + `X-Api-Key` em todos os requests | Zero lógica de domínio |
| `frontend/store/auth.ts` | Estado global de auth (user, token) com persistência localStorage | Zero chamadas diretas à API |
| `src/api/main.py` | 40+ endpoints REST, validação, serialização, rate limiting (slowapi) | Zero lógica de domínio — delega ao engine |
| `src/api/auth_api.py` | Dependency `verificar_token_api` — valida `X-Api-Key` em todos os endpoints protegidos | Zero lógica tributária |
| `src/cognitive/engine.py` | Orquestração do pipeline cognitivo completo | Zero renderização UI |
| `src/rag/retriever.py` | Retrieval HNSW, adaptive tool chain, PTF | Zero lógica de negócio tributária |
| `auth.py` | JWT, bcrypt, autenticação, busca de usuário | Zero renderização UI |
| `src/cognitive/criticidade.py` | Classifica Crítico/Atenção/Informativo por termos detectados | Zero renderização |
| `src/cognitive/proatividade.py` | Detecta padrões de tags e gera sugestões de monitoramento | Zero rendering |
| `src/cognitive/monitoramento_p6.py` | Ativa/encerra monitoramento P6, verifica premissas | Zero rendering |
| `src/cognitive/aprendizado_institucional.py` | Extrai heurísticas de casos encerrados, expira com 6 meses | Zero rendering |
| `src/billing/mau_tracker.py` | Registra e consulta MAU por análise realizada (DEC-08) | Zero lógica tributária |
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
  - Correto: `os.getenv("JWT_SECRET", "fallback-apenas-dev")`
  - Errado: `JWT_SECRET = "minha-chave-secreta"`
- **Toda lógica de negócio e segurança: backend.** Streamlit captura intenção apenas.
- **Chamadas à Claude API: somente via engine.py.** Nunca do Streamlit diretamente.

### Banco de Dados
- **Toda nova feature que toca o banco começa por migration SQL versionada.**
  - Formato: `migrations/NNN_descricao.sql` (NNN = número sequencial de 3 dígitos)
  - Migration mais recente: `117_onboarding_profile.sql` → próxima será `118_...`
- **Nunca alterar schema sem migration.** ALTER TABLE direto no banco sem arquivo = proibido.

### Código
- **Nunca modificar um arquivo sem lê-lo completo primeiro.**
- **Nunca assumir o conteúdo de um arquivo — sempre ler.**
- **Novos módulos RAG:** criar em `src/rag/`, nunca dentro de `engine.py` diretamente.
- **Testes:** todo novo módulo tem `tests/unit/test_[modulo].py` correspondente.
- **Testes unitários:** NUNCA fazem chamadas externas (LLM, embeddings, banco real). Mockar sempre.

### Specs
- **Specs (.docx) nunca são editados diretamente.** Processo: unpack → editar XML → repack.
- **Nova versão de spec:** se v1.1 existe, a próxima é v1.2. Nunca sobrescrever.

### Gate de Qualidade
- **RDMs da Onda 1.5 estão implementados** (HyDE, Multi-Query, Step-Back, Context Budget, Lockfile). Não reimplementar.
- **647 testes devem passar, 0 falhas** após qualquer modificação (referência pós Sprint T1/T2 QA, Abril 2026).
  - Comando: `.venv/bin/python -m pytest tests/unit/ tests/integration/ -v --tb=short`
  - Zero falhas toleradas — o baseline está limpo desde Abril 2026

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
| Admin Module | ✅ Implementado | JWT + bcrypt + trial 30 dias + painel gestão (5 abas) |
| Pool de conexões unificado | ✅ Implementado | get_conn/put_conn em todos os módulos — sem _get_conn() local |
| Criticidade 3 níveis | ✅ Implementado | Crítico/Atenção/Informativo — G17, migration 114 |
| MAU Metering por análise | ✅ Implementado | DEC-08: usuário ativo = análise realizada, não login — G26, migration 115 |
| Proatividade customizada | ✅ Implementado | Detecção de padrões de tags, sugestões não intrusivas — G25, migration 116 |
| Onboarding progressive profiling | ✅ Implementado | 3 steps: step 0 obrigatório, 1-2 opcionais — GTM E, migration 117 |
| Landing page WhatsApp CTA | ✅ Implementado | Botão WhatsApp em hero + CTA final + footer — GTM A/DEC-11 |
| Badge "Memória de Decisão" | ✅ Implementado | Label no card do Dossiê na aba Documentos — GTM D |
| Migração UI Streamlit → Next.js 16 | ✅ Implementado | App Router, Tailwind v4, shadcn/ui v2, Zustand, axios — P01–P20 |
| SEC-01 CORS restrito | ✅ Implementado | allow_origins apenas tribus-ai.com.br + localhost:8521 + localhost:3000 |
| SEC-02 JWT_SECRET sem fallback | ✅ Implementado | RuntimeError se env não configurada |
| SEC-05 str(e) genérico | ✅ Implementado | 31 instâncias → "Erro interno. Tente novamente." |
| SEC-06 Rate limiting slowapi | ✅ Implementado | /v1/analyze: 20/min, /upload: 10/min, demais: 60/min |
| SEC-07 MIME validation upload | ✅ Implementado | magic bytes + limite 50MB server-side |
| SEC-08 X-Api-Key em todos os endpoints | ✅ Implementado | Dependency verificar_token_api em auth_api.py |
| Monitor de Fontes Oficiais no frontend | ✅ Implementado | Verificar agora + docs pendentes + descartar — página base-conhecimento |
| Modal de detalhes na aba Documentos | ✅ Implementado | Conteúdo completo + stakeholders + materialidade + disclaimer |
| Mensagem amigável fora-de-escopo | ✅ Implementado | HTTP 400 → card âmbar com sugestão de consulta correta |
| ISS-05: Monitor com timeout por fonte | ✅ Implementado | ThreadPoolExecutor + 30s por fonte — evita que DOU/PGFN offline trave endpoint inteiro |
| ISS-06: max_tokens stakeholders 800→1200 | ✅ Implementado | Evita truncamento de stakeholders em queries complexas |
| ISS-16: Filtro/busca em Documentos | ✅ Implementado | useMemo filtrando por título, classe, conteúdo — documentos/page.tsx |
| ISS-18: Alertas drift em P6 | ✅ Implementado | P6Monitoramento.tsx busca /v1/observability/drift e exibe alertas ativos |
| ISS-20: Data de revisão em guias.ts | ✅ Implementado | ULTIMA_REVISAO = "Abril 2026" exportado do módulo guias.ts |
| Bug: gerar_alerta passo=3→2 | ✅ Corrigido | Engine só aceita passo in (2, 6) — main.py corrigido + 3 arquivos de teste |
| Bug: criar_caso sem premissas/periodo_fiscal | ✅ Corrigido | Adicionados parâmetros opcionais em protocol/engine.py |
| Bug: mock psycopg2.connect em vez de get_conn | ✅ Corrigido | test_spd.py, test_stakeholders.py, test_carimbo.py — mockar na camada do pool |
| Sprint T1/T2 QA — suite limpa | ✅ Implementado | 647 testes passando, 0 falhas — 8 novos arquivos de integração (Abril 2026) |
| UI Upgrade — Sidebar dark navy | ✅ Implementado | bg #1a2f4e, texto branco, active item gradient + borda 3px accent-vivid, avatar com iniciais |
| UI Upgrade — globals.css tokens | ✅ Implementado | --shadow-card, --gradient-primary, --color-accent-vivid, --color-bg-sidebar override, dark mode CSS media query |
| UI Upgrade — Login split-layout | ✅ Implementado | Painel esquerdo navy (desktop) + bullets de valor + form branco direita; mobile single-column |
| UI Upgrade — AnalysisLoading spinner | ✅ Implementado | SVG spinner marca + mensagens rotativas a cada 3s ("Consultando LC 214/2025…" etc.) |
| UI Upgrade — PainelGovernança Shield | ✅ Implementado | Header com ícone Shield, cada métrica em card colorido (verde/âmbar/vermelho por valor) |
| UI Upgrade — BadgeCriticidade polished | ✅ Implementado | px-4 py-1.5, icon size=16, font-bold, shadow colorida por criticidade |
| UI Upgrade — Card sombra + hover lift | ✅ Implementado | shadow-card em todos os cards; prop clickable ativa hover:-translate-y-0.5 |
| UI Upgrade — Botão primário gradiente | ✅ Implementado | bg-primary → gradient-primary + scale on hover/active via CSS @layer components |
| UI Upgrade — Layout mobile hamburguer | ✅ Implementado | Sidebar deslizante + overlay + botão hamburguer no topo em mobile; fecha ao navegar |
| Logo dark (TrisbusAI_Logo_Dark_v1) | ✅ Implementado | Substituiu public/logo.png — adequado para sidebar navy e painel login escuro |

---

## 11. Atualização deste Documento

Este documento deve ser atualizado sempre que:
- Um novo módulo for criado
- Uma decisão arquitetural for tomada ou revertida
- A estrutura de pastas mudar
- Uma regra absoluta for adicionada

**Quem atualiza:** PO (Jair) via este chat (Specs e Arquitetura).
**Como atualizar:** gerar prompt neste chat → executar no terminal.
