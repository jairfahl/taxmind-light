"""
tests/integration/test_admin_monitor.py

Integration tests for admin metrics, monitor, and billing endpoints.
Uses the shared test_client fixture from conftest.py (bypass_internal_auth autouse).
"""
import pytest
import uuid


# ---------------------------------------------------------------------------
# TC-ADMIN-01: GET /v1/admin/metricas
# ---------------------------------------------------------------------------

def test_admin_01_metricas_returns_200_and_integer_fields(test_client):
    """TC-ADMIN-01: /v1/admin/metricas returns 200 with expected integer fields."""
    response = test_client.get("/v1/admin/metricas")
    assert response.status_code == 200, response.text

    body = response.json()
    required_fields = ["total_usuarios", "total_analises", "total_dossies", "mau_atual"]
    for field in required_fields:
        assert field in body, f"Missing field: {field}"
        assert isinstance(body[field], int), (
            f"Field {field!r} should be int, got {type(body[field])}"
        )
        assert body[field] >= 0, f"Field {field!r} should be >= 0"


# ---------------------------------------------------------------------------
# TC-MON-02: GET /v1/monitor/pendentes
# ---------------------------------------------------------------------------

def test_mon_02_pendentes_returns_200_and_list(test_client):
    """TC-MON-02: /v1/monitor/pendentes returns 200 with a list of documents."""
    response = test_client.get("/v1/monitor/pendentes")
    assert response.status_code == 200, response.text

    body = response.json()
    # Endpoint returns {"total": int, "documentos": [...]}
    assert "total" in body
    assert "documentos" in body
    assert isinstance(body["documentos"], list)
    assert isinstance(body["total"], int)
    assert body["total"] >= 0


# ---------------------------------------------------------------------------
# TC-MON-03: GET /v1/monitor/contagem
# ---------------------------------------------------------------------------

def test_mon_03_contagem_returns_200_and_count_field(test_client):
    """TC-MON-03: /v1/monitor/contagem returns 200 with a 'pendentes' integer field."""
    response = test_client.get("/v1/monitor/contagem")
    assert response.status_code == 200, response.text

    body = response.json()
    assert "pendentes" in body, f"Expected 'pendentes' key, got: {list(body.keys())}"
    assert isinstance(body["pendentes"], int)
    assert body["pendentes"] >= 0


# ---------------------------------------------------------------------------
# TC-BILLING-01: GET /v1/billing/mau
# ---------------------------------------------------------------------------

def test_billing_01_mau_returns_200_with_valid_tenant(test_client):
    """TC-BILLING-01: /v1/billing/mau with a random UUID tenant returns 200."""
    # Use a random UUID — tenant may not exist, but endpoint returns active_users=0
    fake_tenant_id = str(uuid.uuid4())
    response = test_client.get(
        "/v1/billing/mau",
        params={"tenant_id": fake_tenant_id, "month": "2026-04"},
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert isinstance(body, dict)
    assert "tenant_id" in body
    assert "month" in body
    assert "active_users" in body
    assert "active_month_start" in body
    assert isinstance(body["active_users"], int)
    assert body["active_users"] >= 0
    assert body["month"] == "2026-04"
