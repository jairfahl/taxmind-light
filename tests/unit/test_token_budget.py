"""
tests/unit/test_token_budget.py — testes para src/billing/token_budget.py
"""

from unittest.mock import MagicMock, patch

import pytest

from src.billing.token_budget import (
    PLAN_LIMITS,
    TokenBudgetExceeded,
    obter_uso_diario_tenant,
    verificar_budget_tenant,
)


def _mock_conn(input_tokens=0, output_tokens=0, estimated_cost=0.0):
    """Retorna um mock de conexão DB que responde à query de uso diário."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (input_tokens, output_tokens, estimated_cost)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# obter_uso_diario_tenant
# ---------------------------------------------------------------------------

def test_obter_uso_diario_aggregates_correctly():
    conn = _mock_conn(input_tokens=100_000, output_tokens=20_000, estimated_cost=0.30)
    uso = obter_uso_diario_tenant("tenant-abc", conn)
    assert uso["input_tokens"] == 100_000
    assert uso["output_tokens"] == 20_000
    assert uso["estimated_cost"] == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# verificar_budget_tenant
# ---------------------------------------------------------------------------

def test_budget_ok_under_limit():
    conn = _mock_conn(estimated_cost=0.50)  # trial limit = $1.00
    result = verificar_budget_tenant("tenant-1", "trial", conn)
    assert result is True


def test_budget_exceeded_raises():
    conn = _mock_conn(estimated_cost=1.05)  # acima do trial limit $1.00
    with pytest.raises(TokenBudgetExceeded) as exc_info:
        verificar_budget_tenant("tenant-1", "trial", conn)
    err = exc_info.value
    assert err.plan == "trial"
    assert err.limit == pytest.approx(1.00)
    assert err.usage["estimated_cost"] == pytest.approx(1.05)


def test_enterprise_unlimited():
    conn = _mock_conn(estimated_cost=9999.99)  # qualquer valor
    result = verificar_budget_tenant("tenant-ent", "enterprise", conn)
    assert result is True
    conn.cursor.assert_not_called()  # enterprise não consulta o banco


def test_trial_limits_enforced():
    assert PLAN_LIMITS["trial"]["daily_cost_usd"] == pytest.approx(1.00)
    assert PLAN_LIMITS["trial"]["daily_input_tokens"] == 500_000
    assert PLAN_LIMITS["trial"]["daily_output_tokens"] == 100_000


def test_budget_check_null_tenant_skips():
    conn = MagicMock()
    result = verificar_budget_tenant(None, "trial", conn)
    assert result is True
    conn.cursor.assert_not_called()


def test_budget_graceful_on_db_error():
    conn = MagicMock()
    conn.cursor.side_effect = Exception("DB down")
    # Fail-open: deve retornar True sem propagar exceção
    result = verificar_budget_tenant("tenant-x", "trial", conn)
    assert result is True
