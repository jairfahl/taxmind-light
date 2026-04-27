# Skill: Modificar Pipeline RAG

## Regras Críticas

1. **Nunca remover `_tool_activated`** em `engine.py` — controla exclusividade das ferramentas RAG
2. **Novos módulos RAG:** criar em `src/rag/`, nunca adicionar lógica em `engine.py` diretamente
3. **Ferramentas mutuamente exclusivas:** Multi-Query, Step-Back e HyDE nunca rodam juntas por query
4. **Loop Depth Quality Gate:** FACTUAL=1 iter / INTERPRETATIVA=2 iter / COMPARATIVA=3 iter — não alterar sem PO

## Adicionando Nova Ferramenta RAG

```python
# src/rag/nova_ferramenta.py
def minha_ferramenta(query: str, params: AdaptiveParams) -> list[str]:
    """Descrição da ferramenta."""
    ...

# src/cognitive/engine.py — seção de tool selection
if not _tool_activated and <condição>:
    resultado = minha_ferramenta(query, params)
    _tool_activated = True
```

## Parâmetros de Retrieval

```python
# src/rag/retriever.py:26
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3")  # NUNCA alterar default

# top_k padrão = 5, escala por iteração:
# iter 1: top_k × 1.0
# iter 2: top_k × 1.7
# iter 3: top_k × 2.5
```

## Teste de Linter Após Modificação

```bash
.venv/bin/python -m pytest tests/linters/test_embedding_lock.py -v
.venv/bin/python -m pytest tests/linters/test_ptf_enforcement.py -v
.venv/bin/python -m pytest tests/unit/test_iterative_quality_loop.py -v
```

## Arquivos do Pipeline

| Arquivo | Responsabilidade |
|---------|-----------------|
| `src/cognitive/engine.py` | Orquestração — `analisar()` |
| `src/rag/retriever.py` | HNSW + BM25, PTF, data_referencia |
| `src/rag/ptf.py` | Extração de data_referencia |
| `src/rag/adaptive.py` | Parâmetros adaptativos por tipo de query |
| `src/rag/spd.py` | Classificação FACTUAL/INTERPRETATIVA/COMPARATIVA |
| `src/rag/corrector.py` | CRAG — correção e validação |
| `src/quality/engine.py` | Quality Gate M1-M4 |
