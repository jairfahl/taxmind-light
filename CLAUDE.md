# Orbis.tax — Instruções para Claude Code
**Versão:** 3.0 | **Atualizado em:** Abril 2026

> Lido automaticamente pelo Claude Code a cada sessão. Não remover.

---

## LEITURA OBRIGATÓRIA AO INICIAR QUALQUER SESSÃO

```bash
cat /Users/jairfahl/Downloads/tribus-ai-light/ARCHITECTURE.md
.venv/bin/python -m pytest tests/ --tb=no -q 2>/dev/null | tail -3
ls /Users/jairfahl/Downloads/tribus-ai-light/TASKS_*.md
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

## ESTADO ATUAL DO PROJETO (Abril 2026)

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

- **Suite de testes:** 744 passando, ~9 falhas conhecidas pré-existentes (referência 2026-04-28)
- **Linters AST:** `tests/linters/` — 12 testes: embedding lock, P4 guard, citation contract, PTF
- **Última migration:** `129_api_usage_tenant.sql` → próxima: `130_...`

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
ls migrations/ | sort | tail -5   # Última: 129 → próxima: 130
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
