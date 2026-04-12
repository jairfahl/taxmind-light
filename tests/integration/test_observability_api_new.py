"""
tests/integration/test_observability_api_new.py

Integration tests for the observability and health endpoints.
Uses the shared test_client fixture from conftest.py (bypass_internal_auth autouse).
"""
import pytest


# ---------------------------------------------------------------------------
# TC-OBS-01: GET /v1/observability/metrics
# ---------------------------------------------------------------------------

def test_obs_01_metrics_returns_200_and_list(test_client):
    """TC-OBS-01: /v1/observability/metrics?days=7 returns 200 with expected shape."""
    response = test_client.get("/v1/observability/metrics?days=7")
    assert response.status_code == 200, response.text

    body = response.json()
    # The endpoint always returns a dict with "metrics", "resumo", and "days"
    assert "metrics" in body
    assert "resumo" in body
    assert "days" in body
    assert isinstance(body["metrics"], list)
    assert body["days"] == 7


# ---------------------------------------------------------------------------
# TC-OBS-02: GET /v1/observability/drift
# ---------------------------------------------------------------------------

def test_obs_02_drift_returns_200_and_list(test_client):
    """TC-OBS-02: /v1/observability/drift returns 200 with a list (active alerts)."""
    response = test_client.get("/v1/observability/drift")
    assert response.status_code == 200, response.text

    body = response.json()
    assert isinstance(body, list)
    # If there are items, verify all have resolvido=False (endpoint filters on it)
    for alert in body:
        assert alert.get("resolvido") is False


# ---------------------------------------------------------------------------
# TC-OBS-03: GET /v1/observability/budget-pressure
# ---------------------------------------------------------------------------

def test_obs_03_budget_pressure_returns_200_and_expected_keys(test_client):
    """TC-OBS-03: /v1/observability/budget-pressure returns 200 with correct structure."""
    response = test_client.get("/v1/observability/budget-pressure")
    assert response.status_code == 200, response.text

    body = response.json()
    assert isinstance(body, list)
    # If data exists, each item must have the expected keys
    expected_keys = {"query_tipo", "avg_pressao_pct", "max_pressao_pct", "total_analises"}
    for item in body:
        assert expected_keys.issubset(item.keys()), (
            f"Missing keys in item: {expected_keys - item.keys()}"
        )


# ---------------------------------------------------------------------------
# TC-OBS-04: GET /v1/health
# ---------------------------------------------------------------------------

def test_obs_04_health_returns_200_and_corpus_populated(test_client):
    """TC-OBS-04: /v1/health returns 200 with status=ok and populated corpus counters."""
    response = test_client.get("/v1/health")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body.get("status") == "ok"
    assert isinstance(body.get("chunks_total"), int)
    assert body["chunks_total"] > 0, "chunks_total should be > 0 (corpus must be loaded)"
    assert isinstance(body.get("embeddings_total"), int)
    assert body["embeddings_total"] > 0, "embeddings_total should be > 0"
    assert isinstance(body.get("normas"), list)
