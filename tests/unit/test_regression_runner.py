"""
tests/unit/test_regression_runner.py — Testes unitários do RegressionRunner.

CognitiveEngine e banco são mockados — sem chamadas reais à API.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.observability.regression import (
    DATASET_AVALIACAO,
    THRESHOLDS_REGRESSAO,
    RegressionResult,
    RegressionRunner,
    _citar_norma,
    _percentil,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analise_mock(
    fundamento_legal=None,
    bloqueado=False,
    flags=None,
    contra_tese=None,
):
    m = MagicMock()
    m.fundamento_legal = fundamento_legal or ["Art. 9 LC 214/2025"]
    m.anti_alucinacao.bloqueado = bloqueado
    m.anti_alucinacao.flags = flags or []
    m.contra_tese = contra_tese
    return m


def _make_conn_mock():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn


# ---------------------------------------------------------------------------
# _citar_norma helper
# ---------------------------------------------------------------------------

def test_citar_norma_encontra_214():
    assert _citar_norma(["Art. 9 LC 214/2025"], ["214"]) is True


def test_citar_norma_nao_encontra():
    assert _citar_norma(["Art. 9 LC 214/2025"], ["132"]) is False


def test_citar_norma_lista_vazia():
    assert _citar_norma([], ["214"]) is False


# ---------------------------------------------------------------------------
# 1. Todos os casos retornam grounding → aprovado=True
# ---------------------------------------------------------------------------

@patch("src.observability.regression._get_conn")
@patch("src.cognitive.engine.analisar")
def test_todos_grounding_aprovado(mock_analisar, mock_get_conn):
    """Quando todos os casos citam normas esperadas e sem alucinação → aprovado."""
    mock_get_conn.return_value = _make_conn_mock()

    # Todos os casos: citam 214 e 132, sem alucinação, com contra_tese (cobre caso 4)
    mock_analisar.return_value = _make_analise_mock(
        fundamento_legal=["Art. 9 LC 214/2025", "Art. 5 EC 132/2023"],
        bloqueado=False,
        flags=[],
        contra_tese="Existe interpretação divergente",
    )

    runner = RegressionRunner()
    result = runner.executar("v1.0.0", "claude-haiku-4-5-20251001", "v1.0.0")

    assert result.precisao_citacao >= THRESHOLDS_REGRESSAO["precisao_citacao"]
    assert result.taxa_alucinacao <= THRESHOLDS_REGRESSAO["taxa_alucinacao"]
    assert result.acuracia_recomendacao >= THRESHOLDS_REGRESSAO["acuracia_recomendacao"]
    assert result.aprovado is True
    assert mock_analisar.call_count == len(DATASET_AVALIACAO)


# ---------------------------------------------------------------------------
# 2. Taxa de alucinação > 5% → aprovado=False
# ---------------------------------------------------------------------------

@patch("src.observability.regression._get_conn")
@patch("src.cognitive.engine.analisar")
def test_taxa_alucinacao_alta_reprovado(mock_analisar, mock_get_conn):
    """Quando todos os casos têm bloqueado=True → taxa=1.0 > threshold=0.05 → reprovado."""
    mock_get_conn.return_value = _make_conn_mock()

    mock_analisar.return_value = _make_analise_mock(
        fundamento_legal=["Art. 9 LC 214/2025"],
        bloqueado=True,   # alucinação detectada em todos os casos
        flags=["M1:FALHA:Art. 9 LC 214/2025"],
        contra_tese=None,
    )

    runner = RegressionRunner()
    result = runner.executar("v1.0.0", "claude-haiku-4-5-20251001", "v1.0.0")

    assert result.taxa_alucinacao > THRESHOLDS_REGRESSAO["taxa_alucinacao"]
    assert result.aprovado is False


# ---------------------------------------------------------------------------
# 3. Latência p95 > 15s → aprovado=False
# ---------------------------------------------------------------------------

@patch("src.observability.regression._get_conn")
@patch("src.observability.regression.time")
@patch("src.cognitive.engine.analisar")
def test_latencia_p95_alta_reprovado(mock_analisar, mock_time, mock_get_conn):
    """Quando latência p95 excede 15s → aprovado=False."""
    mock_get_conn.return_value = _make_conn_mock()

    # Simular 20s por chamada: time.time() retorna 0, 20, 0, 20, ...
    mock_time.time.side_effect = [0, 20_000, 0, 20_000, 0, 20_000, 0, 20_000, 0, 20_000]

    mock_analisar.return_value = _make_analise_mock(
        fundamento_legal=["Art. 9 LC 214/2025", "Art. 5 EC 132/2023"],
        bloqueado=False,
        flags=[],
        contra_tese="Contra-tese presente",
    )

    runner = RegressionRunner()
    result = runner.executar("v1.0.0", "claude-haiku-4-5-20251001", "v1.0.0")

    # latencia_p95 em segundos: (20_000 - 0) * 1000 / 1000 = 20_000s — muito acima de 15s
    assert result.latencia_p95 > THRESHOLDS_REGRESSAO["latencia_p95"]
    assert result.aprovado is False


# ---------------------------------------------------------------------------
# 4. Falha em caso individual: penalidade de 30s aplicada
# ---------------------------------------------------------------------------

@patch("src.observability.regression._get_conn")
@patch("src.cognitive.engine.analisar")
def test_caso_com_excecao_penalidade(mock_analisar, mock_get_conn):
    """Quando analisar() levanta exceção → penalidade de 30000ms aplicada."""
    mock_get_conn.return_value = _make_conn_mock()

    mock_analisar.side_effect = RuntimeError("LLM indisponível")

    runner = RegressionRunner()
    result = runner.executar("v1.0.0", "claude-haiku-4-5-20251001", "v1.0.0")

    # Todos falharam: precisao=0.0, alucinacao=0.0, latencia muito alta
    assert result.precisao_citacao == 0.0
    assert result.latencia_p95 >= 30.0  # 30_000ms / 1000 = 30s (penalidade)
    assert result.aprovado is False


# ---------------------------------------------------------------------------
# 5. dataset_avaliacao tem exatamente 5 casos
# ---------------------------------------------------------------------------

def test_dataset_tem_5_casos():
    assert len(DATASET_AVALIACAO) == 5
    for caso in DATASET_AVALIACAO:
        assert "query" in caso
        assert "artigos_esperados" in caso
        assert "deve_ter_grounding" in caso
