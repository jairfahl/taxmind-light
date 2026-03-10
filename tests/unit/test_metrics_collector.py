"""
tests/unit/test_metrics_collector.py — Testes unitários do MetricsCollector.
Todos mockados — sem chamadas reais ao banco ou LLM.
"""

from datetime import date
from unittest.mock import MagicMock, patch, call

import pytest

from src.observability.collector import MetricsCollector, _percentil


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analise_result(
    resposta="Resposta teste", fundamento_legal=None, contra_tese=None,
    bloqueado=False, flags=None, model_id="claude-haiku-4-5-20251001",
):
    m = MagicMock()
    m.resposta = resposta
    m.fundamento_legal = fundamento_legal or ["Art. 12 LC 214/2025"]
    m.contra_tese = contra_tese
    m.model_id = model_id
    m.anti_alucinacao = MagicMock()
    m.anti_alucinacao.bloqueado = bloqueado
    m.anti_alucinacao.flags = flags or []
    return m


# ---------------------------------------------------------------------------
# 1. _percentil helper
# ---------------------------------------------------------------------------
def test_percentil_p95():
    valores = list(range(1, 101))  # 1..100
    p95 = _percentil(valores, 95)
    assert abs(p95 - 95.05) < 1.0  # ~95


def test_percentil_lista_vazia():
    assert _percentil([], 95) == 0.0


def test_percentil_elemento_unico():
    assert _percentil([42.0], 50) == 42.0


# ---------------------------------------------------------------------------
# 2. registrar_interacao persiste com campos corretos
# ---------------------------------------------------------------------------
@patch("src.observability.collector._get_conn")
def test_registrar_interacao_campos_corretos(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.rowcount = 1
    mock_get_conn.return_value = mock_conn

    analise = _make_analise_result(
        resposta="Resposta longa de teste tributário",
        fundamento_legal=["Art. 9 LC 214/2025"],
        contra_tese="Existe contra-tese",
    )
    collector = MetricsCollector()
    collector.registrar_interacao(analise, "query teste")

    # Verificar que execute foi chamado com UPDATE
    assert mock_cur.execute.called
    call_args = mock_cur.execute.call_args[0]
    assert "UPDATE ai_interactions" in call_args[0]
    params = mock_cur.execute.call_args[0][1]
    assert params[0] is True   # contra_tese_gerada = True
    assert params[1] is True   # grounding_presente = True
    assert isinstance(params[2], int)  # response_length


# ---------------------------------------------------------------------------
# 3. registrar_interacao com exceção no banco: não propaga
# ---------------------------------------------------------------------------
@patch("src.observability.collector._get_conn", side_effect=Exception("Banco indisponível"))
def test_registrar_interacao_nao_propaga_excecao(mock_get_conn):
    """Exceção no banco deve ser logada, não propagada."""
    collector = MetricsCollector()
    analise = _make_analise_result()
    # Deve executar sem lançar exceção
    collector.registrar_interacao(analise, "query")  # não deve levantar


# ---------------------------------------------------------------------------
# 4. agregar_diario calcula p95 corretamente
# ---------------------------------------------------------------------------
@patch("src.observability.collector._get_conn")
def test_agregar_diario_p95(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_get_conn.return_value = mock_conn

    # Simular 10 registros com latências variadas
    latencias = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
    rows = [
        ("v1.0.0", "claude-haiku-4-5-20251001",
         lat, "alto", False, False, False, False, False, True, True, 500)
        for lat in latencias
    ]
    mock_cur.fetchall.return_value = rows

    collector = MetricsCollector()
    result = collector.agregar_diario(date(2026, 3, 10))

    assert result is not None
    # p95 de [100..1000] deve ser próximo de 950
    assert result.p95_latencia_ms is not None
    assert result.p95_latencia_ms > 800


# ---------------------------------------------------------------------------
# 5. calcular_taxa_alucinacao retorna 0.0 se nenhum flag
# ---------------------------------------------------------------------------
@patch("src.observability.collector._get_conn")
def test_taxa_alucinacao_zero_sem_flags(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = (0, 100)  # 0 bloqueados de 100
    mock_get_conn.return_value = mock_conn

    collector = MetricsCollector()
    taxa = collector.calcular_taxa_alucinacao(date(2026, 1, 1), date(2026, 3, 10))
    assert taxa == 0.0


# ---------------------------------------------------------------------------
# 6. calcular_taxa_alucinacao retorna 1.0 se todos bloqueados
# ---------------------------------------------------------------------------
@patch("src.observability.collector._get_conn")
def test_taxa_alucinacao_um_todos_bloqueados(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = (50, 50)  # 50 bloqueados de 50
    mock_get_conn.return_value = mock_conn

    collector = MetricsCollector()
    taxa = collector.calcular_taxa_alucinacao(date(2026, 1, 1), date(2026, 3, 10))
    assert taxa == 1.0


# ---------------------------------------------------------------------------
# 7. calcular_taxa_alucinacao retorna 0.0 se sem interações
# ---------------------------------------------------------------------------
@patch("src.observability.collector._get_conn")
def test_taxa_alucinacao_zero_sem_interacoes(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = (0, 0)
    mock_get_conn.return_value = mock_conn

    collector = MetricsCollector()
    taxa = collector.calcular_taxa_alucinacao(date(2026, 1, 1), date(2026, 3, 10))
    assert taxa == 0.0


# ---------------------------------------------------------------------------
# 8. agregar_diario retorna None se sem interações
# ---------------------------------------------------------------------------
@patch("src.observability.collector._get_conn")
def test_agregar_diario_sem_interacoes(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchall.return_value = []
    mock_get_conn.return_value = mock_conn

    collector = MetricsCollector()
    result = collector.agregar_diario(date(2026, 3, 10))
    assert result is None
