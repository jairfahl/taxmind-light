# Orbis.tax — Instruções para Claude Code
**Versão:** 3.2 | **Atualizado em:** Maio 2026

> Lido automaticamente pelo Claude Code a cada sessão. Não remover.

---

## LEITURA OBRIGATÓRIA AO INICIAR QUALQUER SESSÃO

```bash
cat /Users/jairfahl/Downloads/orbis.tax/ARCHITECTURE.md
.venv/bin/python -m pytest tests/ --tb=no -q 2>/dev/null | tail -3
ls /Users/jairfahl/Downloads/orbis.tax/TASKS_*.md
```

Só prosseguir após concluir os 3 passos acima.

**Para contexto completo:** → ver `AGENTS.md` e `docs/`

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
10. **Isolamento multi-tenant: filtrar por `tenant_id`, nunca por `user_id` diretamente** → ver `docs/DATA_BOUNDARY.md`
11. **Cores de texto no frontend: NUNCA usar `style={{ color: "#..." }}`** — usar `text-foreground`, `text-muted-foreground`
12. **Componentes com `useSearchParams()`: SEMPRE envolver em `<Suspense>`**

### Após implementar
13. **Rodar suite completa:** `.venv/bin/python -m pytest tests/ -v --tb=short`
14. **Zero regressões toleradas** — se um teste quebrou, corrigir antes de entregar

---

## STACK ATIVO

| O que usar | O que NUNCA usar |
|---|---|
| Python 3.12, FastAPI | LangChain / LlamaIndex / LangGraph |
| APScheduler>=3.10.0 | Supabase |
| Next.js 16 App Router, Tailwind v4, shadcn/ui v2 | ChromaDB / FAISS / Pinecone |
| PostgreSQL 16 + pgvector (HNSW, dim 1024) | Qualquer ORM |
| Voyage-3 (embeddings), Claude Sonnet 4.6 | Streamlit (legado) |
| Resend (e-mail), Asaas (billing) | Stripe, PagSeguro, SendGrid |

### Convenções Next.js (OBRIGATÓRIO ler antes de tocar o frontend)
- **App Router:** grupos `(app)` e `(auth)` — o prefixo do grupo NÃO aparece na URL
- **Tailwind v4:** config via CSS (`@theme inline`), sem `tailwind.config.ts`
- **NEXT_PUBLIC_*** são gravadas no build — override de env em runtime não funciona
- **API calls:** sempre via `@/lib/api` (axios com interceptors de `Authorization` e `X-Api-Key`)
- **Auth:** `useAuthStore` (Zustand + localStorage persist) — nunca acessar DB no cliente
- **Standalone output:** `outputFileTracingRoot: path.join(__dirname)` obrigatório em `next.config.ts`
- **`useSearchParams()`:** exige `<Suspense>` no componente pai — sem isso o build `next build` falha

### Convenções de Design (OBRIGATÓRIO)
- **Tokens:** `frontend/src/styles/tokens.css` é a fonte de verdade para cores e tipografia
- **Overrides shadcn/globais:** `frontend/app/globals.css` — não editar tokens.css para ajustes de UI
- **Sidebar:** dark navy `#1a2f4e` via `--color-bg-sidebar`. Texto sempre branco/rgba
- **Dark mode:** `@media (prefers-color-scheme: dark)` em `globals.css` — sem biblioteca JS
- **Cards de estado semânticos:** usar `.tm-card-warning`/`.tm-card-danger` — nunca `bg-amber-50`, `text-amber-700` hardcoded
- **Disclaimer em /analisar:** exibir sempre entre saidas_stakeholders e CTADocumentar (ESP-06 §2.2)

---

## PROTOCOLO E PIPELINE

→ ver `docs/PROTOCOL_P1_P6.md` para campos obrigatórios por passo
→ ver `docs/RAG_ARCHITECTURE.md` para pipeline completo

**6 passos — imutável:** P1 → P2 → P3 → P4 → P5 → P6
**P7, P8, P9 não existem.**

Pipeline: `PTF → Adaptive → SPD → Retrieve → CRAG → [MQ|SB|HyDE] → QG → BM → LLM`

---

## ESTADO ATUAL DO PROJETO (Maio 2026)

→ ver histórico completo em `ARCHITECTURE.md §10`

| Entrega Recente | Status |
|---|---|
| Sprint Retenção — APScheduler + e-mails + /conta + CancelModal | ✅ |
| Páginas legais — /politica-privacidade, /termos-de-uso, /sla | ✅ |
| SEC-10 UUID cases/outputs (migrations 118 + 126) | ✅ |
| Loop Depth Quality Gate (FACTUAL:1 / INTERPRETATIVA:2 / COMPARATIVA:3) | ✅ |
| HyDE prompt densificado (H2) | ✅ |
| Fluxo recuperação de senha (migration 125 + Resend) | ✅ |
| Landing page tagline + limpeza de rodapé + links legais | ✅ |
| **Harness Engineering — AGENTS.md + docs/ + linters + skills** | ✅ Abril 2026 |
| **Admin Consumo API — /admin/consumo + GET /v1/admin/consumo (migrations 128+129)** | ✅ Abril 2026 |
| **tenant_id no pipeline engine.py + usage.py simplificado** | ✅ Abril 2026 |
| **WhatsApp provider: Evolution API → Z-API (src/notifications/whatsapp.py)** | ✅ Abril 2026 |
| **Billing enforcement FastAPI — verificar_acesso_tenant + HTTP 402** | ✅ Abril 2026 |
| **SubscriptionBlocker frontend — TrialExpiradoScreen + bypass /assinar e /conta** | ✅ Abril 2026 |
| **CPF/CNPJ na assinatura — migration 132 + campo /assinar + validação Asaas** | ✅ Abril 2026 |
| **ASAAS_BASE_URL corrigido para produção (era sandbox com chave prod)** | ✅ Abril 2026 |
| **Auditoria QA — Sprint Segurança (7 findings remediados)** | ✅ Abril 2026 |
| **SEC-F03 Credenciais hardcoded removidas — docker-compose.yml usa ${DOCKER_DATABASE_URL}** | ✅ Abril 2026 |
| **SEC-F14 Swagger desabilitado em prod — docs_url=None quando ENV!=dev** | ✅ Abril 2026 |
| **SEC-F07 Prompt injection defense — src/security/prompt_sanitizer.py (OWASP LLM01)** | ✅ Abril 2026 |
| **SEC-F09 CI/CD GitHub Actions — security.yml (Bandit+pip-audit) + tests.yml (pytest)** | ✅ Abril 2026 |
| **SEC-F11 CSP Enforce ativo — nginx.conf (era Report-Only)** | ✅ Abril 2026 |
| **SEC-F02 RLS implementado — migrations 133+134 (users, cases, mau_records, api_usage)** | ✅ Abril 2026 |
| **SEC-F04 SSH hardening no VPS — PermitRootLogin prohibit-password + PasswordAuthentication no** | ✅ Abril 2026 |
| **UX Sprint — terminologia: "Dossiê de Decisão" → "Mapa de Decisão" no frontend** | ✅ Maio 2026 |
| **UX Sprint — terminologia: "Legal Hold" → "Bloqueio Regulatório" no frontend (backend inalterado)** | ✅ Maio 2026 |
| **UX Sprint — ExportPDFButton redesign: outline+primary, ArrowDownToLine, feedback sucesso** | ✅ Maio 2026 |
| **UX Sprint — tooltip métodos P1: redesign dark (bg-slate-900), color-coded, hierarquia visual** | ✅ Maio 2026 |
| **UX Sprint — atalho Cmd/Ctrl+Enter cross-platform em /analisar e /consultar** | ✅ Maio 2026 |
| **UX Sprint — subtítulo /base-conhecimento: inclui Portarias, Decretos e Leis** | ✅ Maio 2026 |
| **Infra hardening — guard file + host nginx + redeploy pre-flight** | ✅ Maio 2026 |
| **Skills index completo — 10 skills em AGENTS.md + CLAUDE.md** | ✅ Maio 2026 |
| **Landing page — plano Pro "Em breve" + pdf_generator tenant_nome sem fallback** | ✅ Maio 2026 |
| **Plano v1.0 — T1 auth.py→pool + T3 APScheduler lock + T4 gzip nginx** | ✅ Maio 2026 |
| **Plano v1.0 — T2 API key exposure fix (NEXT_PUBLIC removido do bundle)** | ✅ Maio 2026 |
| **Plano v1.0 — T5 router extraction — main.py 3.768→143 linhas, 9 routers em src/api/routers/** | ✅ Maio 2026 |
| **Plano v1.0 — T6 CSP hardening + T7 streamlit removido + T8 deps atualizadas** | ✅ Maio 2026 |
| **P5 copy — "detector de terceirização cognitiva" → linguagem de negócio** | ✅ Maio 2026 |
| **PDF dossiê fix — fallback flat-key (premissas/hipotese_gestor/decisao_final)** | ✅ Maio 2026 |
| **Cases DB zerado em produção — TRUNCATE cases CASCADE (base de conhecimento intacta)** | ✅ Maio 2026 |
| **Gate U2 Stress Testing — Locust + OWASP + resiliência + soak (piped-humming-bengio.md)** | ✅ Maio 2026 |
| **SEC: UUID inválido em /v1/cases/{id} retornava 500 → corrigido para 404** | ✅ Maio 2026 |
| **SEC: PromptInjectionError em /v1/analyze retornava 500 → corrigido para 400** | ✅ Maio 2026 |
| **Stop hook simplificado — era pytest completo (~90s), agora git status (~1s)** | ✅ Maio 2026 |

- **Suite de testes:** 799 passando (referência 2026-05-05); 4 falhas adversariais pré-existentes conhecidas (test_adversarial_sprint3)
- **Stress testing:** `tests/stress/` (Locust) + `tests/integration/test_security_manual.py` + `test_resilience.py` + `test_stress_pipeline.py`
- **Gate U2 resultado:** 0 falhas em 16.602 req soak 2h; recovery API=4s, DB=12s; RAM estável
- **Fase 1.1 pendente:** load test com LLM — adiado para após 10 users pagantes
- **Linters AST:** `tests/linters/` — 12 testes: embedding lock, P4 guard, citation contract, PTF
- **Última migration:** `134_rls_api_usage.sql` → próxima: `135_...`

---

## ÍNDICE DE SKILLS E HOOKS

### Skills Disponíveis (`/skills/`)

| Skill | Quando usar |
|-------|-------------|
| `new-feature.md` | Qualquer feature nova |
| `new-migration.md` | ALTER TABLE / CREATE TABLE |
| `new-endpoint.md` | Rota nova em `src/api/routers/*.py` |
| `new-test.md` | Qualquer módulo Python novo |
| `pre-deploy.md` | Antes de git push para produção |
| `diagnose-bug.md` | Bug em produção |
| `debug-regression.md` | Teste que quebrou |
| `review-security.md` | Revisão de segurança pré-deploy |
| `rag-pipeline.md` | Alterar pipeline de retrieval |
| `protocol-step.md` | Alterar protocolo P1→P6 |

### Hooks Ativos (`.claude/settings.json`)

| Evento | O que enforça |
|--------|---------------|
| PreToolUse (Write/Edit) | Bloqueia imports de pacotes proibidos (langchain, supabase, etc.) |
| PostToolUse (Write/Edit) | Rejeita `style={{ color: ... }}` em arquivos TSX/JSX |
| PostToolUse (Write/Edit) | Rejeita `useSearchParams` sem `<Suspense>` em TSX/JSX |
| Stop | Avisa se suite de testes tem regressão acima do baseline |

---

## PADRÃO PARA NOVA FEATURE

→ ver `skills/new-feature.md` para processo completo

```
1. Ler ARCHITECTURE.md
2. Copiar TASKS_TEMPLATE.md → TASKS_[nome].md
3. Declarar escopo
4. Apresentar ao PO
5. Implementar
```

### Antes de qualquer git push para produção:

```bash
bash scripts/pre_deploy_check.sh
bash scripts/quality_scorecard.sh
```

---

## PADRÃO PARA MIGRATION SQL

→ ver `skills/new-migration.md` para processo completo

```bash
ls migrations/ | sort | tail -5   # Última: 134 → próxima: 135
# Dev local:
docker compose -f docker-compose.dev.yml exec -i tribus-ai-db psql -U taxmind -d taxmind_db < migrations/NNN_descricao.sql
# Atalho (container já rodando):
docker exec -i tribus-ai-db psql -U taxmind -d taxmind_db < migrations/NNN_descricao.sql
```

**REGRA:** qualquer ALTER TABLE **DEVE** ter arquivo migration correspondente criado e commitado.

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

- Necessidade de modificar arquivo fora do escopo declarado
- Suite de testes com regressão sem solução óbvia
- Dúvida sobre se uma decisão impacta o ARCHITECTURE.md
- Qualquer operação irreversível no banco (DROP, DELETE sem WHERE)
- Necessidade de adicionar dependência nova ao projeto
