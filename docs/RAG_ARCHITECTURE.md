# Pipeline RAG — Arquitetura

## Ordem Obrigatória

```
PTF → Adaptive Params → SPD routing → Retrieve → CRAG →
  [Multi-Query | Step-Back | HyDE] (mutuamente exclusivos) →
  Quality Gate → Budget Manager (SUMMARY/FULL) → LLM
```

**Regra de exclusividade:** flag `_tool_activated` em `engine.py` controla que apenas UMA ferramenta RAG avançada seja usada por query. **Nunca remover esta flag.**

---

## Funções-Chave por Estágio

| Estágio | Arquivo | Função |
|---------|---------|--------|
| PTF | `src/rag/ptf.py` | `extrair_data_referencia()`, `resolver_vigencia()` |
| Adaptive Params | `src/rag/adaptive.py` | `get_adaptive_params()` |
| SPD routing | `src/rag/spd.py` | `classificar_query()` → FACTUAL/INTERPRETATIVA/COMPARATIVA |
| Retrieve | `src/rag/retriever.py` | `retrieve()` — HNSW + BM25 híbrido |
| CRAG | `src/rag/corrector.py` | `corrigir_resultado()` |
| Multi-Query | `src/rag/multi_query.py` | `expandir_queries()` |
| Step-Back | `src/rag/step_back.py` | `gerar_step_back()` |
| HyDE | `src/rag/hyde.py` | `gerar_hyde()` |
| Quality Gate | `src/quality/engine.py` | `avaliar_qualidade()` |
| Budget Manager | Dentro de `engine.py` | `_aplicar_budget()` |
| Orquestração | `src/cognitive/engine.py` | `analisar()` |

---

## Parâmetros de Retrieval

- **Top-k:** 5 (padrão) — escala ×1.7/×2.5 por iteração no Loop Depth Quality Gate
- **Rerank top-n:** 20
- **Score mínimo:** 0.7 cosine + 0.3 BM25
- **Dimensão:** 1024 (Voyage-3)
- **Índice:** HNSW (pgvector)

---

## Loop Depth Quality Gate (ACT-inspired)

O bloco Retrieve→CRAG→QualityGate é executado em loop iterativo:

| Tipo de Query | Máx. Iterações | Constante |
|--------------|----------------|-----------|
| FACTUAL | 1 | `_QUALITY_MAX_ITER["FACTUAL"] = 1` |
| INTERPRETATIVA | 2 | `_QUALITY_MAX_ITER["INTERPRETATIVA"] = 2` |
| COMPARATIVA | 3 | `_QUALITY_MAX_ITER["COMPARATIVA"] = 3` |

Critério de halting: `quality_gate.status == VERDE` → halt imediato.
Escala: `_QUALITY_TOPK_SCALE = {1: 1.0, 2: 1.7, 3: 2.5}` (via `dataclasses.replace()`).
Campo `quality_iterations: int` em `AnaliseResult` para observability.

---

## Embedding Model Lock

**EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3")**

Locais onde está definido (3 arquivos — nunca alterar o default):
- `src/rag/retriever.py:26`
- `src/ingest/embedder.py:26`
- `src/protocol/carimbo.py:25`

Teste de linter: `tests/linters/test_embedding_lock.py` — falha se default != "voyage-3".

---

## HyDE Prompt (Densificado — H2)

Hipóteses geradas devem conter obrigatoriamente:
- Terminologia: IBS, CBS, IS, fato gerador, SPED
- Estrutura: artigo→regra→vigência→fato gerador
- Referências a EC 132/2023, LC 214/2025 ou LC 227/2026

---

## Remissão Resolver

Módulo `src/rag/remissao_resolver.py` resolve referências cruzadas entre normas e injeta no contexto (RAR). Ativado quando o retriever detecta artigos com remissões explícitas.

---

## Novos Módulos RAG

Criar sempre em `src/rag/`. Nunca adicionar lógica RAG diretamente em `engine.py`.
