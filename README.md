# TaxMind Light — Sprint 1: KB + RAG Funcional

Sistema RAG local para análise da Reforma Tributária brasileira (EC 132/2023, LC 214/2025, LC 227/2026).

## Pré-requisitos

- Python 3.12.3
- Docker + Docker Compose
- Chave Anthropic API (voyage-3 + claude-haiku)

## Setup End-to-End

### 1. Configurar variáveis de ambiente

```bash
# Editar .env e preencher ANTHROPIC_API_KEY
nano .env
```

### 2. Subir o banco PostgreSQL + pgvector

```bash
docker compose up -d
docker compose ps   # aguardar status "healthy"
```

### 3. Instalar dependências Python

```bash
pip install -r requirements.txt
```

### 4. Rodar a ingestão dos PDFs

```bash
python src/ingest/run_ingest.py
```

O pipeline irá:
- Extrair texto dos 3 PDFs (via pdfplumber)
- Segmentar em chunks jurídicos (por artigo, parágrafo, inciso)
- Gerar embeddings voyage-3 (dim 1024) via Anthropic API
- Persistir tudo no PostgreSQL

Verificar resultado:
```bash
docker exec -it taxmind-light-db-1 psql -U taxmind -d taxmind_db \
  -c "SELECT COUNT(*) FROM chunks; SELECT COUNT(*) FROM embeddings;"
```

### 5. Testar o retriever

```bash
python -c "
from src.rag.retriever import retrieve
resultados = retrieve('fato gerador do IBS')
for r in resultados:
    print(f'[{r.score_final:.3f}] {r.norma_codigo} | {r.artigo} | {r.texto[:120]}...')
"
```

### 6. Rodar os testes unitários

```bash
pytest tests/unit/test_retriever.py -v
```

## Arquitetura

```
PDF_SOURCE_DIR (read-only)
      │
      ▼
  loader.py ──► pdfplumber ──► DocumentoNorma
      │
      ▼
 chunker.py ──► hierárquico (artigo → parágrafo → sliding window)
      │
      ▼
 embedder.py ──► voyage-3 (batch 32, retry 3x)
      │
      ▼
PostgreSQL/pgvector ──► HNSW index (cosine, m=16, ef=64)
      │
      ▼
 retriever.py ──► vetorial (pgvector) + BM25 re-ranking
                  score = 0.7 * cosine + 0.3 * bm25
```

## Estrutura de Pastas

```
taxmind-light/
├── docker-compose.yml
├── .env                    # não versionar
├── requirements.txt
├── db/
│   └── init.sql            # schema + extensão pgvector + índice HNSW
├── src/
│   ├── ingest/
│   │   ├── loader.py       # extração de texto dos PDFs
│   │   ├── chunker.py      # chunking jurídico hierárquico
│   │   ├── embedder.py     # embeddings voyage-3
│   │   └── run_ingest.py   # pipeline principal
│   └── rag/
│       └── retriever.py    # retrieve() híbrido
└── tests/
    └── unit/
        └── test_retriever.py
```

## Regras

- PDFs **nunca** são copiados para este repositório
- Único vector store: pgvector (sem LangChain, FAISS, ChromaDB)
- Embedding model: voyage-3 exclusivamente
- Índice HNSW obrigatório (m=16, ef_construction=64)

## Critério de Aceite Sprint 1

≥ 8/10 queries de validação com top-3 chunks pertinentes (registradas em `avaliacoes`).
