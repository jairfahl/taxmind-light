"""
tests/unit/test_limite_casos_admin.py — Testes para o endpoint GET /v1/cases/limite.

Foco: bypass de limite para usuário ADMIN (bug corrigido: admin sem tenant
retornava limite=0 → badge "Limite atingido (0/0 casos de trial)").

Sem chamadas externas: banco mockado via MagicMock.
"""

from unittest.mock import MagicMock, patch

import pytest


def _make_cursor(perfil_row, tenant_row):
    """Cria cursor mock que retorna perfil e depois tenant info."""
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.side_effect = [perfil_row, tenant_row]
    return cur


def _make_conn(perfil_row, tenant_row=None):
    cur = _make_cursor(perfil_row, tenant_row)
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def _call_limite(user_id: str, conn_mock):
    """Chama get_limite_casos com banco mockado."""
    from src.api.main import get_limite_casos

    with patch("src.api.routers.auth.get_conn", return_value=conn_mock), \
         patch("src.api.routers.auth.put_conn"), \
         patch("src.api.routers.auth._get_tenant_info_by_user", return_value=None), \
         patch("src.api.routers.auth._verificar_limite_casos"):
        return get_limite_casos(user_id=user_id)


class TestLimiteCasosAdmin:
    def test_admin_sem_tenant_retorna_limite_menos_um(self):
        """ADMIN sem tenant_id deve retornar limite=-1 (ilimitado)."""
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = ("ADMIN",)
        conn = MagicMock()
        conn.cursor.return_value = cur

        result = _call_limite("admin-uuid", conn)

        assert result["limite"] == -1
        assert result["subscription_status"] == "active"

    def test_admin_sem_tenant_nao_exibe_badge(self):
        """limite=-1 significa que o frontend não exibe badge (lim === -1 → return null)."""
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = ("ADMIN",)
        conn = MagicMock()
        conn.cursor.return_value = cur

        result = _call_limite("admin-uuid", conn)

        # Frontend: if (lim === -1) return null — badge não exibido
        assert result["limite"] == -1

    def test_usuario_sem_tenant_retorna_limite_zero(self):
        """USER sem tenant_id deve retornar limite=0 (comportamento original preservado)."""
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = ("USER",)
        conn = MagicMock()
        conn.cursor.return_value = cur

        result = _call_limite("user-uuid", conn)

        assert result["limite"] == 0
        assert result["subscription_status"] == "trial"

    def test_usuario_desconhecido_sem_tenant_retorna_limite_zero(self):
        """User sem linha no banco retorna limite=0 (fallback seguro)."""
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = cur

        result = _call_limite("ghost-uuid", conn)

        assert result["limite"] == 0
