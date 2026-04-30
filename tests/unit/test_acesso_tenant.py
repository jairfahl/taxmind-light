"""
tests/unit/test_acesso_tenant.py — Testes para verificar_acesso_tenant e tenant_tem_acesso.

Sem chamadas externas: DB e JWT são mockados.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.billing.access import tenant_tem_acesso, dias_restantes_trial


# ---------------------------------------------------------------------------
# tenant_tem_acesso — lógica pura, sem mock necessário
# ---------------------------------------------------------------------------

class TestTenantTemAcesso:
    def test_active_sempre_permite(self):
        tenant = {"subscription_status": "active", "trial_ends_at": None}
        ok, motivo = tenant_tem_acesso(tenant)
        assert ok is True
        assert motivo == ""

    def test_trial_dentro_prazo(self):
        futuro = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        tenant = {"subscription_status": "trial", "trial_ends_at": futuro}
        ok, motivo = tenant_tem_acesso(tenant)
        assert ok is True

    def test_trial_expirado(self):
        passado = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        tenant = {"subscription_status": "trial", "trial_ends_at": passado}
        ok, motivo = tenant_tem_acesso(tenant)
        assert ok is False
        assert motivo == "trial_expired"

    def test_trial_sem_data_libera(self):
        tenant = {"subscription_status": "trial", "trial_ends_at": None}
        ok, _ = tenant_tem_acesso(tenant)
        assert ok is True  # bypass explícito

    def test_past_due_bloqueia(self):
        tenant = {"subscription_status": "past_due", "trial_ends_at": None}
        ok, motivo = tenant_tem_acesso(tenant)
        assert ok is False
        assert motivo == "payment_failed"

    def test_canceled_bloqueia(self):
        tenant = {"subscription_status": "canceled", "trial_ends_at": None}
        ok, motivo = tenant_tem_acesso(tenant)
        assert ok is False
        assert motivo == "canceled"

    def test_status_desconhecido_bloqueia(self):
        tenant = {"subscription_status": "unknown", "trial_ends_at": None}
        ok, motivo = tenant_tem_acesso(tenant)
        assert ok is False
        assert motivo == "unknown_status"

    def test_trial_ends_at_como_datetime_object(self):
        """Aceita trial_ends_at como datetime (não só str)."""
        futuro = datetime.now(timezone.utc) + timedelta(days=1)
        tenant = {"subscription_status": "trial", "trial_ends_at": futuro.isoformat()}
        ok, _ = tenant_tem_acesso(tenant)
        assert ok is True


# ---------------------------------------------------------------------------
# dias_restantes_trial
# ---------------------------------------------------------------------------

class TestDiasRestantesTrial:
    def test_dois_dias_restantes(self):
        futuro = (datetime.now(timezone.utc) + timedelta(days=2, hours=1)).isoformat()
        tenant = {"subscription_status": "trial", "trial_ends_at": futuro}
        assert dias_restantes_trial(tenant) == 2

    def test_expirado_retorna_zero(self):
        passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        tenant = {"subscription_status": "trial", "trial_ends_at": passado}
        assert dias_restantes_trial(tenant) == 0

    def test_nao_trial_retorna_none(self):
        tenant = {"subscription_status": "active", "trial_ends_at": None}
        assert dias_restantes_trial(tenant) is None

    def test_sem_data_retorna_none(self):
        tenant = {"subscription_status": "trial", "trial_ends_at": None}
        assert dias_restantes_trial(tenant) is None


# ---------------------------------------------------------------------------
# verificar_acesso_tenant — mocka DB e JWT
# ---------------------------------------------------------------------------

def _make_payload(sub="user-123", perfil="USUARIO"):
    return {"sub": sub, "email": "u@test.com", "perfil": perfil}


def _make_conn_mock(subscription_status, trial_ends_at=None):
    row = (subscription_status, trial_ends_at)
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = row
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


class TestVerificarAcessoTenant:
    def _call(self, authorization, x_api_key, conn_mock=None, payload=None):
        from src.api.auth_api import verificar_acesso_tenant

        if payload is None:
            payload = _make_payload()

        with patch("src.api.auth_api._validar_api_key"), \
             patch("src.api.auth_api._extrair_payload_jwt", return_value=payload), \
             patch("src.api.auth_api.get_conn", return_value=conn_mock or MagicMock()), \
             patch("src.api.auth_api.put_conn"):
            return verificar_acesso_tenant(authorization=authorization, x_api_key=x_api_key)

    def test_acesso_liberado_trial_ativo(self):
        futuro = datetime.now(timezone.utc) + timedelta(days=3)
        conn = _make_conn_mock("trial", futuro)
        result = self._call("Bearer tok", "key", conn_mock=conn)
        assert result["sub"] == "user-123"

    def test_bloqueia_trial_expirado_com_402(self):
        passado = datetime.now(timezone.utc) - timedelta(seconds=1)
        conn = _make_conn_mock("trial", passado)
        with pytest.raises(HTTPException) as exc_info:
            self._call("Bearer tok", "key", conn_mock=conn)
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail == "trial_expired"

    def test_admin_bypassa_billing(self):
        passado = datetime.now(timezone.utc) - timedelta(days=10)
        conn = _make_conn_mock("trial", passado)
        payload = _make_payload(perfil="ADMIN")
        # ADMIN não deve consultar o banco — conn não é chamado
        result = self._call("Bearer tok", "key", conn_mock=conn, payload=payload)
        assert result["perfil"] == "ADMIN"

    def test_sem_tenant_no_banco_deixa_passar(self):
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = cur
        result = self._call("Bearer tok", "key", conn_mock=conn)
        assert result["sub"] == "user-123"

    def test_bloqueia_canceled(self):
        conn = _make_conn_mock("canceled", None)
        with pytest.raises(HTTPException) as exc_info:
            self._call("Bearer tok", "key", conn_mock=conn)
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail == "canceled"

    def test_bloqueia_past_due(self):
        conn = _make_conn_mock("past_due", None)
        with pytest.raises(HTTPException) as exc_info:
            self._call("Bearer tok", "key", conn_mock=conn)
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail == "payment_failed"

    def test_active_passa_sem_verificar_data(self):
        conn = _make_conn_mock("active", None)
        result = self._call("Bearer tok", "key", conn_mock=conn)
        assert result["sub"] == "user-123"
