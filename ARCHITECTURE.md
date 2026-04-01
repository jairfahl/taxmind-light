# TaxMind Light — Architecture Reference
**Versão:** 1.0
**Atualizado em:** Abril 2026
**Mantido por:** PO (Jair)

> Este documento é leitura obrigatória antes de qualquer sessão de desenvolvimento.
> Claude Code deve ler este arquivo ANTES de ler qualquer outro arquivo do projeto.

---

## 1. Identidade do Projeto

TaxMind Light é um sistema RAG de inteligência tributária focado na Reforma Tributária
brasileira (EC 132/2023, LC 214/2025, LC 227/2026).

**Não é:** calculadora de tributos, ERP, gerador de obrigações acessórias.
**É:** sistema de apoio à decisão tributária com protocolo de 6 passos (P1→P6).

---

## 2. Raiz e Estrutura do Projeto

```
/Users/jairfahl/Downloads/taxmind-light/
├── auth.py                   ← Autenticação JWT + bcrypt
├── admin.py                  ← Painel admin (renderização Streamlit apenas)
├── ARCHITECTURE.md           ← Este arquivo
├── CLAUDE.md                 ← Regras e contexto permanente para Claude Code
├── ui/
│   └── app.py                ← Entry point Streamlit + guard de sessão
├── pages/
│   └── login.py              ← Tela de login
├── components/
│   └── trial_banner.py       ← Banner de trial
├── src/
│   ├── api/
│   │   └── main.py           ← FastAPI — 19+ endpoints
│   ├── cognitive/
│   │   └── engine.py         ← Orquestração cognitiva principal
│   ├── rag/
│   │   ├── retriever.py      ← Retrieval pgvector + adaptive tool chain
│   │   ├── hyde.py           ← HyDE — RDM-020
│   │   ├── multi_query.py    ← Multi-Query — RDM-024
│   │   ├── step_back.py      ← Step-Back — RDM-025
│   │   ├── corrector.py      ← CRAG
│   │   ├── adaptive.py       ← Adaptive retrieval chain
│   │   ├── ptf.py            ← PTF (Pre-retrieval Transformation)
│   │   ├── spd.py            ← SPD routing
│   │   └── decomposer.py     ← Decomposição de queries
│   ├── integrity/
│   │   └── lockfile_manager.py ← Prompt Integrity — RDM-029
│   ├── outputs/              ← 5 classes de output acionável
│   ├── protocol/             ← Engine P1→P6
│   ├── quality/              ← Quality gate
│   ├── observability/        ← Métricas + drift + regression
│   ├── monitor/              ← Monitor de fontes oficiais
│   ├── ingest/               ← Pipeline de ingestão de PDFs
│   └── db/                   ← Conexão e pool de banco
├── migrations/
│   └── NNN_descricao.sql     ← Numeração sequencial obrigatória
└── tests/
    ├── unit/                 ← test_[modulo].py
    └── integration/          ← test_[fluxo].py
```

---

## 3. Stack — Tecnologias Ativas

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| API Backend | FastAPI (porta 8020) |
| Frontend | Streamlit (porta 8501) |
| Banco | PostgreSQL 16 + pgvector (HNSW, dim 1024) |
| Embeddings | Voyage-3 |
| LLM | Claude Sonnet 4.6 |
| Infraestrutura | Docker |
| Container DB | tribus-ai-db |
| DATABASE_URL | postgresql://taxmind:taxmind123@localhost:5436/taxmind_db |

**Tecnologias EXPLICITAMENTE EXCLUÍDAS (nunca usar):**
- LangChain
- LangGraph
- Supabase
- ChromaDB / FAISS / Pinecone

---

## 4. Responsabilidades dos Módulos

| Módulo | Responsabilidade | O que NÃO faz |
|---|---|---|
| `ui/app.py` | Entry point Streamlit, guard de sessão, roteamento de abas | Zero lógica tributária, zero chamadas diretas ao banco |
| `src/cognitive/engine.py` | Orquestração do pipeline cognitivo completo | Zero renderização UI |
| `src/rag/retriever.py` | Retrieval HNSW, adaptive tool chain, PTF | Zero lógica de negócio tributária |
| `auth.py` | JWT, bcrypt, autenticação, busca de usuário | Zero renderização UI |
| `admin.py` | Renderização do painel admin no Streamlit | Zero lógica de negócio — delega a auth.py e queries diretas |
| `src/rag/hyde.py` | HyDE — geração de hipótese para expand de query | Zero orquestração |
| `src/rag/multi_query.py` | Multi-Query — variações paralelas da query | Zero orquestração |
| `src/rag/step_back.py` | Step-Back — query mais abstrata | Zero orquestração |
| `src/rag/corrector.py` | CRAG — verificação e correção do retrieval | Zero orquestração |
| `src/integrity/lockfile_manager.py` | Verificação de integridade de prompts (RDM-029) | Zero lógica tributária |
| `src/api/main.py` | Endpoints REST, validação de requests, serialização | Zero lógica de domínio — delega ao engine |

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
  - Migration mais recente: `100_users_table.sql` → próxima será `101_...`
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
- **354 testes devem passar** após qualquer modificação.
  - Comando: `pytest tests/ -v --tb=short`

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
| SLM híbrido | 🔄 Onda 3 | 3B–7B params para classificação/triage |
| Protocolo 9→6 passos | ✅ Consolidado | P7/P8/P9 fundidos em P6 |
| Admin Module | ✅ Implementado | JWT + bcrypt + trial 30 dias + painel gestão |

---

## 11. Atualização deste Documento

Este documento deve ser atualizado sempre que:
- Um novo módulo for criado
- Uma decisão arquitetural for tomada ou revertida
- A estrutura de pastas mudar
- Uma regra absoluta for adicionada

**Quem atualiza:** PO (Jair) via este chat (Specs e Arquitetura).
**Como atualizar:** gerar prompt neste chat → executar no terminal.
