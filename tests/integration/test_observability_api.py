"""
tests/integration/test_observability_api.py — Testes de integração dos endpoints de observability.

Dependências externas (banco, DriftDetector, RegressionRunner) são mockadas.
Executa com: pytest tests/integration/test_observability_api.py -v
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cur_mock(fetchall=None, fetchone=None):
    cur = MagicMock()
    cur.fetchall.return_value = fetchall or []
    cur.fetchone.return_value = fetchone
    return cur


def _make_conn_mock(fetchall=None, fetchone=None):
    conn = MagicMock()
    conn.cursor.return_value = _make_cur_mock(fetchall=fetchall, fetchone=fetchone)
    return conn


# ---------------------------------------------------------------------------
# 1. GET /v1/observability/metrics → 200
# ---------------------------------------------------------------------------

@patch("psycopg2.connect")
def test_get_metrics_retorna_200(mock_connect):
    """GET /v1/observability/metrics deve retornar 200 mesmo sem dados."""
    mock_connect.return_value = _make_conn_mock(fetchall=[], fetchone=None)

    resp = client.get("/v1/observability/metrics")

    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert "days" in data


@patch("psycopg2.connect")
def test_get_metrics_com_dados(mock_connect):
    """GET /v1/observability/metrics com dados retorna lista de métricas."""
    # Simular linha de ai_metrics_daily
    rows = [
        ("2026-03-10", "v1.0.0", "claude-haiku-4-5-20251001",
         10, 200.0, 500.0, 900.0, 0.8, 0.5, 0.9, 0.02, 0.01, 0.01, 0.02, 0.01)
    ]
    cols = [
        "data_referencia", "prompt_version", "model_id",
        "total_interacoes", "avg_response_length", "avg_latencia_ms",
        "p95_latencia_ms", "pct_scoring_alto", "pct_contra_tese",
        "pct_grounding_presente", "taxa_alucinacao",
        "taxa_bloqueio_m1", "taxa_bloqueio_m2", "taxa_bloqueio_m3", "taxa_bloqueio_m4",
    ]

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = rows
    cur.fetchone.return_value = (10, 500.0, 900.0, 0.8, 0.02)
    cur.description = [(c, None, None, None, None, None, None) for c in cols]
    conn.cursor.return_value = cur
    mock_connect.return_value = conn

    resp = client.get("/v1/observability/metrics?days=7")

    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert data["days"] == 7


# ---------------------------------------------------------------------------
# 2. POST /v1/observability/baseline → baseline criado (201)
# ---------------------------------------------------------------------------

@patch("src.observability.drift.DriftDetector.registrar_baseline")
def test_registrar_baseline_201(mock_baseline):
    """POST /v1/observability/baseline deve retornar 201 com resultado do baseline."""
    mock_baseline.return_value = {
        "prompt_version": "v1.0.0",
        "model_id": "claude-haiku-4-5-20251001",
        "dias_dados": 5,
        "baseline_id": 1,
    }

    resp = client.post("/v1/observability/baseline", json={
        "prompt_version": "v1.0.0",
        "model_id": "claude-haiku-4-5-20251001",
    })

    assert resp.status_code == 201
    data = resp.json()
    assert data["prompt_version"] == "v1.0.0"


@patch("src.observability.drift.DriftDetector.registrar_baseline")
def test_registrar_baseline_dados_insuficientes_400(mock_baseline):
    """POST /v1/observability/baseline com dados insuficientes → 400."""
    from src.observability.drift import DriftDetectorError
    mock_baseline.side_effect = DriftDetectorError("Dados insuficientes: apenas 2 dias disponíveis")

    resp = client.post("/v1/observability/baseline", json={
        "prompt_version": "v1.0.0",
        "model_id": "claude-haiku-4-5-20251001",
    })

    assert resp.status_code == 400
    assert "insuficientes" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 3. GET /v1/observability/drift → 200
# ---------------------------------------------------------------------------

@patch("psycopg2.connect")
def test_get_drift_retorna_200(mock_connect):
    """GET /v1/observability/drift deve retornar 200."""
    mock_connect.return_value = _make_conn_mock(fetchall=[])

    resp = client.get("/v1/observability/drift")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@patch("psycopg2.connect")
def test_get_drift_sem_alertas_lista_vazia(mock_connect):
    """GET /v1/observability/drift sem alertas retorna lista vazia."""
    mock_connect.return_value = _make_conn_mock(fetchall=[])

    resp = client.get("/v1/observability/drift")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# 4. POST /v1/observability/drift/{alert_id}/resolver → 200
# ---------------------------------------------------------------------------

@patch("src.observability.drift.DriftDetector.resolver_alert")
def test_resolver_drift_alert_200(mock_resolver):
    """POST /v1/observability/drift/{id}/resolver deve retornar 200."""
    mock_resolver.return_value = None

    resp = client.post("/v1/observability/drift/42/resolver", json={
        "observacao": "Falso positivo — batch de migração",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["resolvido"] is True
    assert data["alert_id"] == 42


@patch("src.observability.drift.DriftDetector.resolver_alert")
def test_resolver_drift_inexistente_404(mock_resolver):
    """POST /v1/observability/drift/{id}/resolver com id inexistente → 404."""
    from src.observability.drift import DriftDetectorError
    mock_resolver.side_effect = DriftDetectorError("Alert 99999 não encontrado")

    resp = client.post("/v1/observability/drift/99999/resolver", json={
        "observacao": "Teste inexistente",
    })

    assert resp.status_code == 404
