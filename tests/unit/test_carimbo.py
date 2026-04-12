"""
tests/unit/test_carimbo.py — Testes unitários do DetectorCarimbo.
Executa com: pytest tests/unit/test_carimbo.py -v

Usa mocks para evitar chamadas reais à API Voyage e ao banco.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.protocol.carimbo import (
    THRESHOLD_COSSENO,
    CarimboConfirmacaoError,
    CarimboResult,
    DetectorCarimbo,
    _cosseno,
)


# ---------------------------------------------------------------------------
# 1. Função _cosseno
# ---------------------------------------------------------------------------
def test_cosseno_vetores_iguais():
    v = [1.0, 0.0, 0.0]
    assert abs(_cosseno(v, v) - 1.0) < 1e-9


def test_cosseno_vetores_opostos():
    v1 = [1.0, 0.0]
    v2 = [-1.0, 0.0]
    assert abs(_cosseno(v1, v2) - (-1.0)) < 1e-9


def test_cosseno_vetores_ortogonais():
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    assert abs(_cosseno(v1, v2)) < 1e-9


def test_cosseno_vetor_zero():
    assert _cosseno([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# 2. DetectorCarimbo.verificar — alerta disparado (score >= threshold)
# ---------------------------------------------------------------------------
@patch("src.protocol.carimbo._embed")
@patch("src.protocol.carimbo.psycopg2.connect")
def test_verificar_alerta_disparado(mock_connect, mock_embed):
    """Score >= 0.70 deve disparar alerta e persistir em carimbo_alerts."""
    # Vetores quase idênticos → score ~1.0
    mock_embed.side_effect = [[1.0, 0.0, 0.0], [0.99, 0.01, 0.0]]
    # Mock do banco
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = (42,)  # alert_id
    mock_connect.return_value = mock_conn

    detector = DetectorCarimbo()
    result = detector.verificar(
        case_id=1,
        passo=7,
        texto_decisao="Optamos por adotar o regime de crédito integral do IBS.",
        texto_recomendacao="Recomendamos adotar o regime de crédito integral do IBS.",
    )

    assert result.alerta is True
    assert result.score_similaridade >= THRESHOLD_COSSENO
    assert result.alert_id == 42
    assert result.mensagem is not None
    assert "similaridade" in result.mensagem.lower()


# ---------------------------------------------------------------------------
# 3. DetectorCarimbo.verificar — sem alerta (score < threshold)
# ---------------------------------------------------------------------------
@patch("src.protocol.carimbo._embed")
def test_verificar_sem_alerta(mock_embed):
    """Score < 0.70 não deve disparar alerta."""
    # Vetores ortogonais → score = 0.0
    mock_embed.side_effect = [[1.0, 0.0], [0.0, 1.0]]

    detector = DetectorCarimbo()
    result = detector.verificar(
        case_id=1,
        passo=7,
        texto_decisao="Decisão completamente diferente.",
        texto_recomendacao="Recomendação sem relação alguma.",
    )

    assert result.alerta is False
    assert result.score_similaridade < THRESHOLD_COSSENO
    assert result.alert_id is None
    assert result.mensagem is None


# ---------------------------------------------------------------------------
# 4. DetectorCarimbo.confirmar — justificativa inválida
# ---------------------------------------------------------------------------
def test_confirmar_justificativa_curta():
    detector = DetectorCarimbo()
    with pytest.raises(CarimboConfirmacaoError, match="20 caracteres"):
        detector.confirmar(alert_id=1, justificativa="curta")


def test_confirmar_justificativa_vazia():
    detector = DetectorCarimbo()
    with pytest.raises(CarimboConfirmacaoError):
        detector.confirmar(alert_id=1, justificativa="")


# ---------------------------------------------------------------------------
# 5. DetectorCarimbo.confirmar — alert_id inexistente
# ---------------------------------------------------------------------------
@patch("src.protocol.carimbo.put_conn")
@patch("src.protocol.carimbo.get_conn")
def test_confirmar_alert_id_inexistente(mock_get_conn, mock_put_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.rowcount = 0  # nenhuma linha atualizada
    mock_get_conn.return_value = mock_conn

    detector = DetectorCarimbo()
    with pytest.raises(ValueError, match="não encontrado"):
        detector.confirmar(alert_id=99999, justificativa="Justificativa suficientemente longa para o teste")


# ---------------------------------------------------------------------------
# 6. Threshold configurado em 0.70
# ---------------------------------------------------------------------------
def test_threshold_valor():
    assert THRESHOLD_COSSENO == 0.70


# ---------------------------------------------------------------------------
# 7. CarimboResult dataclass
# ---------------------------------------------------------------------------
def test_carimbo_result_dataclass():
    r = CarimboResult(score_similaridade=0.85, alerta=True, mensagem="msg", alert_id=1)
    assert r.score_similaridade == 0.85
    assert r.alerta is True
