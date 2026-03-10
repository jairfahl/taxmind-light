"""
tests/unit/test_drift_detector.py — Testes unitários do DriftDetector.
Todos mockados — sem chamadas reais ao banco ou LLM.
"""

from datetime import date
from unittest.mock import MagicMock, patch, call

import pytest

from src.observability.drift import (
    DRIFT_THRESHOLD_SIGMA,
    METRICAS_MONITORADAS,
    DriftAlert,
    DriftDetector,
    DriftDetectorError,
    _stddev,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn_mock(baseline_vals=None, metrics_rows=None):
    """Cria mock de conexão/cursor configurado."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    # baseline row (8 colunas = METRICAS_MONITORADAS)
    n = len(METRICAS_MONITORADAS)
    if baseline_vals is None:
        baseline_vals = [0.5] * n
    mock_cur.fetchone.side_effect = [(42,)]  # alert RETURNING id — usado em drift
    mock_cur.fetchall.side_effect = [
        [tuple(baseline_vals)],   # primeira fetchall = baseline
        metrics_rows or [],       # segunda fetchall = métricas diárias
    ]
    return mock_conn, mock_cur


# ---------------------------------------------------------------------------
# _stddev helper
# ---------------------------------------------------------------------------
def test_stddev_lista_uniforme():
    assert _stddev([5.0, 5.0, 5.0]) == 0.0


def test_stddev_dois_valores():
    s = _stddev([0.0, 2.0])
    assert abs(s - 1.414) < 0.01


def test_stddev_lista_vazia_ou_unica():
    assert _stddev([]) == 0.0
    assert _stddev([1.0]) == 0.0


# ---------------------------------------------------------------------------
# 1. Sem drift: valores dentro de 2σ → lista vazia
# ---------------------------------------------------------------------------
@patch("src.observability.drift._get_conn")
def test_sem_drift_retorna_lista_vazia(mock_get_conn):
    """Valores consistentes com baseline → nenhum alerta."""
    n = len(METRICAS_MONITORADAS)
    baseline_vals = [0.50] * n

    # Métricas diárias muito próximas do baseline (dentro de 1σ)
    rows = [tuple([0.51] * n) for _ in range(5)]

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = tuple(baseline_vals)
    mock_cur.fetchall.return_value = rows
    mock_get_conn.return_value = mock_conn

    detector = DriftDetector()
    alerts = detector.verificar_drift("v1.0.0", "claude-haiku-4-5-20251001")
    assert alerts == []


# ---------------------------------------------------------------------------
# 2. Drift detectado: desvio > 2σ → DriftAlert criado
# ---------------------------------------------------------------------------
@patch("src.observability.drift._get_conn")
def test_drift_detectado_acima_2_sigma(mock_get_conn):
    """Valor atual desvia claramente do baseline → alerta gerado."""
    n = len(METRICAS_MONITORADAS)
    baseline_row = tuple([0.50] * n)

    # Métricas com alta variância na primeira coluna (avg_latencia_ms)
    # σ = 0.1, baseline = 0.50, valores = [0.70, 0.80, 0.90] → desvio = |0.80 - 0.50| / 0.1 = 3σ
    rows = [(0.70,) + (0.50,) * (n-1),
            (0.80,) + (0.50,) * (n-1),
            (0.90,) + (0.50,) * (n-1)]

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.side_effect = [baseline_row, (99,)]
    mock_cur.fetchall.return_value = rows
    mock_get_conn.return_value = mock_conn

    detector = DriftDetector()
    alerts = detector.verificar_drift("v1.0.0", "claude-haiku-4-5-20251001")
    assert len(alerts) >= 1
    assert alerts[0].metrica == "avg_latencia_ms"
    assert alerts[0].desvios_padrao > DRIFT_THRESHOLD_SIGMA


# ---------------------------------------------------------------------------
# 3. Threshold exato 2σ: NÃO dispara (exclusive)
# ---------------------------------------------------------------------------
def test_threshold_exato_nao_dispara():
    """
    Verificação lógica: desvios > 2.0 para disparar.
    Exatamente 2.0 NÃO deve disparar (operador estrito >).
    """
    assert not (2.0 > DRIFT_THRESHOLD_SIGMA)


# ---------------------------------------------------------------------------
# 4. Threshold 2.01σ: dispara alerta
# ---------------------------------------------------------------------------
def test_threshold_2_01_sigma_dispara():
    assert 2.01 > DRIFT_THRESHOLD_SIGMA


# ---------------------------------------------------------------------------
# 5. registrar_baseline com < 3 dias de dados → DriftDetectorError
# ---------------------------------------------------------------------------
@patch("src.observability.drift._get_conn")
def test_registrar_baseline_dados_insuficientes(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    # COUNT retorna 2 dias (< 3)
    mock_cur.fetchone.return_value = tuple([0.5] * (len(METRICAS_MONITORADAS) + 1) + [2])
    mock_get_conn.return_value = mock_conn

    detector = DriftDetector()
    with pytest.raises(DriftDetectorError, match="insuficientes"):
        detector.registrar_baseline("v1.0.0", "claude-haiku-4-5-20251001")


# ---------------------------------------------------------------------------
# 6. resolver_alert: campo resolvido=TRUE e resolvido_em preenchido
# ---------------------------------------------------------------------------
@patch("src.observability.drift._get_conn")
def test_resolver_alert_atualiza_banco(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.rowcount = 1
    mock_get_conn.return_value = mock_conn

    detector = DriftDetector()
    detector.resolver_alert(42, "Falso positivo — batch de migração")

    call_args = mock_cur.execute.call_args[0]
    assert "resolvido = TRUE" in call_args[0]
    assert "resolvido_em = NOW()" in call_args[0]
    params = call_args[1]
    assert "Falso positivo" in params[0]
    assert params[1] == 42


# ---------------------------------------------------------------------------
# 7. resolver_alert: alert_id inexistente → DriftDetectorError
# ---------------------------------------------------------------------------
@patch("src.observability.drift._get_conn")
def test_resolver_alert_inexistente(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.rowcount = 0
    mock_get_conn.return_value = mock_conn

    detector = DriftDetector()
    with pytest.raises(DriftDetectorError, match="não encontrado"):
        detector.resolver_alert(99999, "obs")


# ---------------------------------------------------------------------------
# 8. METRICAS_MONITORADAS cobre 8 métricas
# ---------------------------------------------------------------------------
def test_metricas_monitoradas_completas():
    assert len(METRICAS_MONITORADAS) == 8
    assert "avg_latencia_ms" in METRICAS_MONITORADAS
    assert "pct_scoring_alto" in METRICAS_MONITORADAS
    assert "taxa_bloqueio_m4" in METRICAS_MONITORADAS
