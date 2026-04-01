# Tribus-AI — Instruções para Claude Code
**Versão:** 2.0 | **Atualizado em:** Abril 2026

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
- **Entry point UI:** `ui/app.py` (Streamlit, porta 8501)
- **Entry point API:** `src/api/main.py` (FastAPI, porta 8020)
- **Banco:** `postgresql://taxmind:taxmind123@localhost:5436/taxmind_db`
- **Container DB:** `tribus-ai-db`
- **PDFs das normas:** `/Users/jairfahl/Downloads/taxmind/Docs/Arquivos Upload/` — **read-only, NUNCA copiar**
- **Specs (.docx):** `/Users/jairfahl/Downloads/taxmind/Specs/`

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
| Python 3.12, FastAPI, Streamlit | LangChain / LlamaIndex |
| PostgreSQL 16 + pgvector (HNSW, dim 1024) | LangGraph |
| Voyage-3 (embeddings) | Supabase |
| Claude Sonnet 4.6 (LLM padrão) | ChromaDB / FAISS / Pinecone |
| Docker, psycopg2 direto | Qualquer ORM |

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

## SCHEMA DO BANCO (15 tabelas)

```sql
normas            -- documentos fonte (EC, LC) + file_hash para dedup
chunks            -- trechos das normas com metadados jurídicos
embeddings        -- vetores voyage-3 (1024 dim) + índice HNSW
consultas         -- log de buscas
avaliacoes        -- validação manual de qualidade
ai_interactions   -- log de chamadas ao LLM + user_id + input_tokens + output_tokens
cases             -- casos protocolares, 6 passos
case_steps        -- dados de cada passo por caso
case_state_history-- audit trail de transições
carimbo_alerts    -- alertas de terceirização cognitiva
outputs           -- documentos acionáveis gerados (5 classes)
stakeholder_views -- visões por público-alvo
monitored_docs    -- documentos detectados pelo monitor de fontes
prompt_lockfiles  -- lockfiles de integridade de prompts (RDM-029)
users             -- usuários do sistema (Admin Module, migration 100)
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
| **Gate U2** | ⏳ Pendente |
| **Deploy VPS Hostinger** | ⏳ Pendente |

- **Suite de testes:** 354 testes passando (referência pós Admin Module)
- **Domínios registrados:** tribus-ai.com.br / tribus-ia.com.br

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
