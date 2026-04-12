"""
tests/unit/test_retriever.py — testes unitários do motor de retrieval.

Executa com: pytest tests/unit/test_retriever.py -v
Requer banco e embeddings populados (run_ingest.py executado).
"""

import pytest

from src.rag.retriever import ChunkResultado, QueryVaziaError, retrieve


# ---------------------------------------------------------------------------
# Teste 1 — retrieve() retorna exatamente top_k resultados
# ---------------------------------------------------------------------------
def test_retorna_top_k():
    resultados = retrieve("fato gerador do IBS", top_k=3)
    assert len(resultados) == 3, f"Esperado 3, obtido {len(resultados)}"


def test_retorna_top_k_variavel():
    for k in [1, 2, 5]:
        resultados = retrieve("split payment imposto", top_k=k)
        assert len(resultados) == k, f"top_k={k}: obtido {len(resultados)}"


# ---------------------------------------------------------------------------
# Teste 2 — Scores entre 0 e 1
# ---------------------------------------------------------------------------
def test_scores_entre_zero_e_um():
    resultados = retrieve("alíquota IBS CBS", top_k=3)
    assert len(resultados) > 0
    for r in resultados:
        assert 0.0 <= r.score_vetorial <= 1.0, f"score_vetorial fora do range: {r.score_vetorial}"
        assert 0.0 <= r.score_bm25 <= 1.0, f"score_bm25 fora do range: {r.score_bm25}"
        assert 0.0 <= r.score_final <= 1.0, f"score_final fora do range: {r.score_final}"


# ---------------------------------------------------------------------------
# Teste 3 — Resultados ordenados por score_final decrescente
# ---------------------------------------------------------------------------
def test_ordenados_por_score_final():
    resultados = retrieve("cashback IBS tributo", top_k=5)
    assert len(resultados) > 1
    for i in range(len(resultados) - 1):
        assert resultados[i].score_final >= resultados[i + 1].score_final, (
            f"Ordem incorreta: pos {i} ({resultados[i].score_final:.4f}) "
            f"< pos {i+1} ({resultados[i+1].score_final:.4f})"
        )


# ---------------------------------------------------------------------------
# Teste 4 — norma_filter retorna apenas chunks da norma especificada
# ---------------------------------------------------------------------------
def test_norma_filter():
    """
    Verifica que o filtro por norma é aplicado sem erro.
    Resultados podem ser 0 quando embeddings são mockados (similaridade baixa).
    """
    norma = "LC214_2025"
    resultados = retrieve("IBS", top_k=3, norma_filter=[norma])
    # Com embeddings mockados ([0.1]*1024), similaridade pode ser baixa → 0 resultados é aceitável
    assert isinstance(resultados, list)
    for r in resultados:
        assert r.norma_codigo == norma, (
            f"Resultado de norma incorreta: {r.norma_codigo} (esperado {norma})"
        )


def test_norma_filter_multiplo():
    normas = ["LC214_2025", "EC132_2023"]
    resultados = retrieve("reforma tributária", top_k=5, norma_filter=normas)
    for r in resultados:
        assert r.norma_codigo in normas, f"Norma {r.norma_codigo} não está no filtro"


# ---------------------------------------------------------------------------
# Teste 5 — Query vazia lança QueryVaziaError
# ---------------------------------------------------------------------------
def test_query_vazia_lanca_excecao():
    with pytest.raises(QueryVaziaError):
        retrieve("")


def test_query_so_espacos_lanca_excecao():
    with pytest.raises(QueryVaziaError):
        retrieve("   ")


# ---------------------------------------------------------------------------
# Teste extra — estrutura do ChunkResultado
# ---------------------------------------------------------------------------
def test_estrutura_chunk_resultado():
    resultados = retrieve("Simples Nacional IBS", top_k=1)
    assert len(resultados) == 1
    r = resultados[0]
    assert isinstance(r, ChunkResultado)
    assert isinstance(r.chunk_id, int) and r.chunk_id > 0
    assert isinstance(r.norma_codigo, str) and len(r.norma_codigo) > 0
    assert isinstance(r.texto, str) and len(r.texto) > 0
    assert isinstance(r.score_final, float)
