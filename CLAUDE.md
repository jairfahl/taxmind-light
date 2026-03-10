# TaxMind Light — Contexto Permanente do Projeto

> Este arquivo é lido automaticamente pelo Claude Code a cada sessão.
> Não remover. Atualizar sempre que houver decisões arquiteturais novas.

---

## Estrutura de Pastas

| Pasta | Propósito |
|-------|-----------|
| `/downloads/taxmind-light/` | Raiz do projeto light (este repositório) |
| `/downloads/taxmind/Docs/Arquivos Upload/` | PDFs das normas — **read-only, nunca copiar** |

## Normas Tributárias (fonte de dados)

| Norma | Arquivo |
|-------|---------|
| EC 132/2023 | `/downloads/taxmind/Docs/Arquivos Upload/EC132_2023.pdf` |
| LC 214/2025 | `/downloads/taxmind/Docs/Arquivos Upload/LC214_2025.pdf` |
| LC 227/2026 | `/downloads/taxmind/Docs/Arquivos Upload/LC227_2026.pdf` |

## Stack Técnica

```
Python        3.12.3
PostgreSQL    16 via Docker Compose
pgvector      extensão obrigatória (dim 1024, índice HNSW)
Embeddings    voyage-3 via Anthropic API
LLM           claude-haiku-4-5-20251001 (dev) | claude-sonnet-4-6 (prod)
UI            Streamlit (Sprint 3)
API           FastAPI (Sprint 2)
Auth          nenhuma (single-user local)
```

## Regras Invioláveis

```
- NUNCA copiar os PDFs para dentro de /downloads/taxmind-light/
- NUNCA usar ChromaDB, FAISS, Pinecone ou qualquer vector store externo
- NUNCA usar LangChain ou LlamaIndex
- NUNCA usar modelo de embedding diferente de voyage-3
- pgvector é o ÚNICO motor de busca vetorial
- Índice HNSW obrigatório na tabela embeddings
- Tratamento de erros em todas as chamadas de API
- Logs estruturados: logging Python, nível INFO
```

## Schema do Banco (5 tabelas)

```sql
normas       -- documentos fonte (EC, LC)
chunks       -- trechos das normas com metadados jurídicos
embeddings   -- vetores voyage-3 (1024 dim) + índice HNSW
consultas    -- log de buscas (Sprint 2+)
avaliacoes   -- validação manual de qualidade
```

## Sprints

| Sprint | Entregável principal | Critério de aceite |
|--------|---------------------|--------------------|
| 1 | KB + RAG funcional | top-3 pertinente ≥ 80% em 10 consultas |
| 2 | Motor cognitivo + FastAPI + Streamlit | alucinação < 5% em 3 casos P1→P4 |
| 3 | Protocolo P1→P9 + testes adversariais | P1→P6 sem inconsistência em 3 casos |

## Estado Atual

- [ ] Sprint 1 — pendente
- [ ] Sprint 2 — pendente
- [ ] Sprint 3 — pendente

> Atualizar checkboxes conforme cada sprint for concluída.

---

## Sprint 1 — Especificação Completa

### TASK-01 — Estrutura de Pastas

```
/downloads/taxmind-light/
├── CLAUDE.md              ← este arquivo
├── docker-compose.yml
├── .env
├── .gitignore
├── requirements.txt
├── README.md
├── db/
│   └── init.sql
├── src/
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   └── run_ingest.py
│   └── rag/
│       ├── __init__.py
│       └── retriever.py
└── tests/
    └── unit/
        └── test_retriever.py
```

### TASK-02 — docker-compose.yml

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    env_file: .env
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      retries: 5
volumes:
  pgdata:
```

### TASK-03 — .env

```dotenv
POSTGRES_USER=taxmind
POSTGRES_PASSWORD=taxmind123
POSTGRES_DB=taxmind_db
DATABASE_URL=postgresql://taxmind:taxmind123@localhost:5432/taxmind_db
ANTHROPIC_API_KEY=<PREENCHER>
EMBEDDING_MODEL=voyage-3
CHUNK_SIZE=512
CHUNK_OVERLAP=64
TOP_K=3
RERANK_TOP_N=10
PDF_SOURCE_DIR=/downloads/taxmind/Docs/Arquivos Upload
```

### TASK-04 — db/init.sql

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE normas (
    id         SERIAL PRIMARY KEY,
    codigo     VARCHAR(20)  NOT NULL UNIQUE,
    nome       VARCHAR(200) NOT NULL,
    tipo       VARCHAR(10)  NOT NULL,
    numero     VARCHAR(10)  NOT NULL,
    ano        INTEGER      NOT NULL,
    arquivo    VARCHAR(500),
    vigente    BOOLEAN      DEFAULT TRUE,
    created_at TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE chunks (
    id          SERIAL PRIMARY KEY,
    norma_id    INTEGER      NOT NULL REFERENCES normas(id),
    chunk_index INTEGER      NOT NULL,
    texto       TEXT         NOT NULL,
    artigo      VARCHAR(50),
    secao       VARCHAR(200),
    titulo      VARCHAR(200),
    tokens      INTEGER,
    created_at  TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (norma_id, chunk_index)
);

CREATE TABLE embeddings (
    id         SERIAL PRIMARY KEY,
    chunk_id   INTEGER      NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    modelo     VARCHAR(100) NOT NULL,
    vetor      vector(1024) NOT NULL,
    created_at TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (chunk_id, modelo)
);

CREATE INDEX ON embeddings USING hnsw (vetor vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE TABLE consultas (
    id          SERIAL PRIMARY KEY,
    query_texto TEXT        NOT NULL,
    chunks_ids  INTEGER[],
    scores      FLOAT[],
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE avaliacoes (
    id              SERIAL PRIMARY KEY,
    query_texto     TEXT    NOT NULL,
    top3_pertinente BOOLEAN,
    nota            INTEGER CHECK (nota BETWEEN 1 AND 5),
    observacao      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### TASK-05 — src/ingest/loader.py

- Usar `pdfplumber` para extrair texto
- Ler de `PDF_SOURCE_DIR` (do `.env`)
- Retornar `DocumentoNorma(codigo, nome, tipo, numero, ano, arquivo, texto)`

Mapeamento fixo:

| Arquivo | codigo | tipo | numero | ano |
|---------|--------|------|--------|-----|
| EC132_2023.pdf | EC132_2023 | EC | 132 | 2023 |
| LC214_2025.pdf | LC214_2025 | LC | 214 | 2025 |
| LC227_2026.pdf | LC227_2026 | LC | 227 | 2026 |

### TASK-05 — src/ingest/chunker.py

Chunking hierárquico para normas jurídicas:

1. Por artigo: regex `Art\.\s*\d+` → se ≤ 512 tokens, manter inteiro
2. Por parágrafo/inciso: se artigo > 512 tokens → quebrar em `§`, `I -`, `II -`, overlap 64 tokens
3. Fallback sliding window: 512 tokens, overlap 64

Usar `tiktoken` (cl100k_base). Preservar: `artigo`, `secao`, `titulo`, `texto`.

### TASK-05 — src/ingest/embedder.py

- `client.embeddings.create(model="voyage-3", input=[...])`
- Batches de 32 chunks
- Retry com backoff exponencial: 3 tentativas, delays 1s → 2s → 4s
- INSERT com `ON CONFLICT DO NOTHING`

### TASK-05 — src/ingest/run_ingest.py

```
1. Carregar .env
2. Conectar ao banco
3. Para cada PDF em PDF_SOURCE_DIR:
   a. loader → DocumentoNorma
   b. INSERT normas (ON CONFLICT DO UPDATE)
   c. chunker → chunks
   d. INSERT chunks (batch, ON CONFLICT DO NOTHING)
   e. embedder → vetores
   f. INSERT embeddings (batch)
   g. Log: norma | chunks | embeddings | tempo
4. Resumo: total normas | chunks | embeddings
```

### TASK-06 — src/rag/retriever.py

```python
@dataclass
class ChunkResultado:
    chunk_id:       int
    norma_codigo:   str
    artigo:         str | None
    texto:          str
    score_vetorial: float
    score_bm25:     float
    score_final:    float

def retrieve(
    query: str,
    top_k: int = 3,
    rerank_top_n: int = 10,
    norma_filter: list[str] | None = None
) -> list[ChunkResultado]:
    # 1. Embedding da query (voyage-3)
    # 2. Busca vetorial pgvector: LIMIT rerank_top_n
    # 3. Re-ranking em memória: score_final = 0.7*cosine + 0.3*bm25
    # 4. Retorna top_k ordenados por score_final DESC
```

### TASK-07 — tests/unit/test_retriever.py (mínimo 5)

1. `retrieve()` retorna exatamente `top_k` resultados
2. Scores entre 0 e 1
3. Resultados ordenados por `score_final` decrescente
4. `norma_filter` retorna apenas chunks da norma especificada
5. Query vazia lança exceção tipada

### TASK-08 — Validação Manual (10 consultas)

| # | Query |
|---|-------|
| 1 | Qual o fato gerador do IBS? |
| 2 | Quais operações são imunes ao IBS e CBS? |
| 3 | Como funciona o split payment? |
| 4 | Quais setores têm redução de 60% na alíquota? |
| 5 | O que é o CGIBS e quais são suas competências? |
| 6 | Qual o prazo de transição para extinção do ICMS? |
| 7 | Como é calculada a alíquota de referência do IBS? |
| 8 | Quais medicamentos têm alíquota zero? |
| 9 | Como funciona o cashback do IBS/CBS? |
| 10 | Quais são as regras do IBS no Simples Nacional? |

Critério: ≥ 8/10 com top-3 pertinente. Registrar em `avaliacoes`.

### requirements.txt

```
anthropic==0.40.0
psycopg2-binary==2.9.9
pgvector==0.3.2
pdfplumber==0.11.0
python-dotenv==1.0.1
rank-bm25==0.2.2
tiktoken==0.7.0
pydantic==2.6.0
```

### Sequência de Execução

```
1.  Criar estrutura de pastas
2.  Criar .env e preencher ANTHROPIC_API_KEY
3.  Criar docker-compose.yml + db/init.sql
4.  docker compose up -d
5.  docker compose ps  (aguardar healthy)
6.  pip install -r requirements.txt
7.  Implementar src/ingest/
8.  python src/ingest/run_ingest.py
9.  SELECT COUNT(*) FROM chunks; SELECT COUNT(*) FROM embeddings;
10. Implementar src/rag/retriever.py
11. python -c "from src.rag.retriever import retrieve; print(retrieve('fato gerador IBS'))"
12. pytest tests/unit/test_retriever.py
13. Executar 10 consultas de validação
14. Escrever README.md
```
