"""
tests/unit/test_spd.py — Testes unitarios para SPD-RAG (roteamento + retrieval per-norma).

Todos com mocks — zero chamadas externas.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.rag.retriever import ChunkResultado
from src.rag.spd import (
    SPDResult,
    SPDRoutingDecision,
    SPDStrategy,
    decidir_estrategia,
    listar_normas_ativas,
    spd_retrieve,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(chunk_id: int, norma: str, score: float, artigo: str = "Art. 1") -> ChunkResultado:
    return ChunkResultado(
        chunk_id=chunk_id,
        norma_codigo=norma,
        artigo=artigo,
        texto=f"Texto do chunk {chunk_id} da {norma}",
        score_vetorial=score,
        score_bm25=score * 0.5,
        score_final=score,
    )


# ---------------------------------------------------------------------------
# decidir_estrategia
# ---------------------------------------------------------------------------

class TestDecidirEstrategia:
    def test_spd_para_comparativa_com_2_ou_mais_normas(self):
        """COMPARATIVA com >= 2 normas -> SPD."""
        decisao = decidir_estrategia("comparativa", None, 3)
        assert decisao.strategy == SPDStrategy.SPD
        assert "comparativa" in decisao.reason

    def test_standard_para_factual(self):
        """FACTUAL -> STANDARD independente do numero de normas."""
        decisao = decidir_estrategia("factual", None, 5)
        assert decisao.strategy == SPDStrategy.STANDARD

    def test_standard_quando_norma_filter_definido(self):
        """Se usuario definiu norma_filter -> STANDARD."""
        decisao = decidir_estrategia("comparativa", ["LC214_2025"], 3)
        assert decisao.strategy == SPDStrategy.STANDARD
        assert "norma_filter" in decisao.reason

    def test_standard_quando_apenas_1_norma(self):
        """Menos de 2 normas -> STANDARD."""
        decisao = decidir_estrategia("comparativa", None, 1)
        assert decisao.strategy == SPDStrategy.STANDARD
        assert "1" in decisao.reason

    def test_spd_para_interpretativa_com_3_normas(self):
        """INTERPRETATIVA com >= 3 normas -> SPD."""
        decisao = decidir_estrategia("interpretativa", None, 3)
        assert decisao.strategy == SPDStrategy.SPD

    def test_standard_para_interpretativa_com_2_normas(self):
        """INTERPRETATIVA com < 3 normas -> STANDARD."""
        decisao = decidir_estrategia("interpretativa", None, 2)
        assert decisao.strategy == SPDStrategy.STANDARD


# ---------------------------------------------------------------------------
# spd_retrieve
# ---------------------------------------------------------------------------

class TestSPDRetrieve:
    @patch("src.rag.spd.retrieve")
    def test_chama_retrieve_uma_vez_por_norma(self, mock_retrieve):
        """retrieve() deve ser chamado uma vez para cada norma."""
        mock_retrieve.return_value = [_make_chunk(1, "EC132_2023", 0.9)]
        normas = ["EC132_2023", "LC214_2025", "LC227_2026"]

        result = spd_retrieve("query teste", normas, top_k_por_norma=3)

        assert mock_retrieve.call_count == 3
        # Verifica que cada norma recebeu seu norma_filter
        normas_chamadas = set()
        for call in mock_retrieve.call_args_list:
            norma_filter = call.kwargs.get("norma_filter") or call[1].get("norma_filter")
            if norma_filter:
                normas_chamadas.update(norma_filter)
        assert normas_chamadas == set(normas)

    @patch("src.rag.spd.retrieve")
    def test_deduplicacao_por_chunk_id_mantem_maior_score(self, mock_retrieve):
        """Chunks duplicados por chunk_id devem manter o de maior score."""
        def side_effect(query, **kwargs):
            norma = kwargs["norma_filter"][0]
            if norma == "EC132_2023":
                return [_make_chunk(1, "EC132_2023", 0.9)]
            else:
                return [_make_chunk(1, "LC214_2025", 0.7)]  # mesmo chunk_id, score menor

        mock_retrieve.side_effect = side_effect

        result = spd_retrieve("query", ["EC132_2023", "LC214_2025"])

        # Apenas 1 chunk com chunk_id=1, e deve ser o de maior score
        assert len(result.chunks_merged) == 1
        assert result.chunks_merged[0].score_final == 0.9

    @patch("src.rag.spd.retrieve")
    def test_resultado_ordenado_por_score_final_desc(self, mock_retrieve):
        """chunks_merged deve estar ordenado por score_final DESC."""
        def side_effect(query, **kwargs):
            norma = kwargs["norma_filter"][0]
            if norma == "EC132_2023":
                return [_make_chunk(1, "EC132_2023", 0.5)]
            else:
                return [_make_chunk(2, "LC214_2025", 0.9)]

        mock_retrieve.side_effect = side_effect

        result = spd_retrieve("query", ["EC132_2023", "LC214_2025"])

        assert len(result.chunks_merged) == 2
        assert result.chunks_merged[0].score_final >= result.chunks_merged[1].score_final

    @patch("src.rag.spd.retrieve")
    def test_contem_chunks_de_multiplas_normas(self, mock_retrieve):
        """Resultado deve conter chunks de diferentes normas."""
        def side_effect(query, **kwargs):
            norma = kwargs["norma_filter"][0]
            return [_make_chunk(hash(norma) % 1000, norma, 0.8)]

        mock_retrieve.side_effect = side_effect

        result = spd_retrieve("query", ["EC132_2023", "LC214_2025", "LC227_2026"])

        normas_no_resultado = {c.norma_codigo for c in result.chunks_merged}
        assert len(normas_no_resultado) >= 2
        assert result.normas_consultadas == 3

    @patch("src.rag.spd.retrieve")
    def test_trata_falha_de_uma_norma_gracefully(self, mock_retrieve):
        """Se retrieve() falha para uma norma, continua com as demais."""
        def side_effect(query, **kwargs):
            norma = kwargs["norma_filter"][0]
            if norma == "EC132_2023":
                raise RuntimeError("Erro simulado")
            return [_make_chunk(2, norma, 0.8)]

        mock_retrieve.side_effect = side_effect

        result = spd_retrieve("query", ["EC132_2023", "LC214_2025"])

        # Deve ter resultado da norma que nao falhou
        assert len(result.chunks_merged) >= 1
        assert result.chunks_por_norma["EC132_2023"] == []


# ---------------------------------------------------------------------------
# listar_normas_ativas
# ---------------------------------------------------------------------------

class TestListarNormasAtivas:
    @patch("src.rag.spd.put_conn")
    @patch("src.rag.spd.get_conn")
    def test_retorna_codigos_do_banco(self, mock_get_conn, mock_put_conn):
        """Deve retornar lista de codigos de normas vigentes."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("EC132_2023",), ("LC214_2025",), ("LC227_2026",),
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        result = listar_normas_ativas()

        assert result == ["EC132_2023", "LC214_2025", "LC227_2026"]
        mock_cursor.execute.assert_called_once()
        assert "vigente = TRUE" in mock_cursor.execute.call_args[0][0]
