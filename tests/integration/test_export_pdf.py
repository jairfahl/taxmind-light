"""
Testes de integração para POST /v1/export/pdf.
WeasyPrint é mockado — sem system deps necessários.
bypass_internal_auth é autouse=True (conftest) — todos os requests já passam auth.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from src.api.main import app
from src.api.auth_api import verificar_acesso_tenant
from tests.integration.conftest import _FAKE_USER_PAYLOAD


# ---------------------------------------------------------------------------
# Fixture local — client sem override de autenticação
# ---------------------------------------------------------------------------

@pytest.fixture()
def no_auth_client():
    """Client sem nenhum override de autenticação."""
    app.dependency_overrides.pop(verificar_acesso_tenant, None)
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    # Restaura para não poluir outros testes
    app.dependency_overrides[verificar_acesso_tenant] = lambda: _FAKE_USER_PAYLOAD


# ---------------------------------------------------------------------------
# Sem token — verificar_acesso_tenant usa Header(...) obrigatório,
# FastAPI retorna 422 (campos ausentes) antes de checar credenciais.
# ---------------------------------------------------------------------------

def test_export_pdf_sem_token(no_auth_client):
    """Sem headers Authorization/x-api-key → 422 (campos obrigatórios ausentes)."""
    res = no_auth_client.post(
        "/v1/export/pdf",
        json={"source_type": "analysis", "analysis_data": {"resposta": "foo"}},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# 422 — payload inválido (bypass_internal_auth autouse ativo)
# ---------------------------------------------------------------------------

def test_export_pdf_analysis_sem_analysis_data(test_client: TestClient):
    res = test_client.post(
        "/v1/export/pdf",
        json={"source_type": "analysis"},
    )
    assert res.status_code == 422


def test_export_pdf_dossie_sem_source_id(test_client: TestClient):
    res = test_client.post(
        "/v1/export/pdf",
        json={"source_type": "dossie"},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# 200 analysis — retorna application/pdf
# ---------------------------------------------------------------------------

def test_export_pdf_analysis_ok(test_client: TestClient):
    fake_pdf = b"%PDF-1.4 fake"
    mock_instance = MagicMock()
    mock_instance.write_pdf.return_value = fake_pdf

    with patch("src.export.pdf_generator.HTML", return_value=mock_instance):
        res = test_client.post(
            "/v1/export/pdf",
            json={
                "source_type": "analysis",
                "analysis_data": {
                    "resposta": "Análise de teste.",
                    "classe": "nota_trabalho",
                },
            },
        )

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert "attachment" in res.headers.get("content-disposition", "")
    assert res.content == fake_pdf


# ---------------------------------------------------------------------------
# 404 dossiê de outro tenant
# ---------------------------------------------------------------------------

def test_export_pdf_dossie_outro_tenant(test_client: TestClient):
    with patch(
        "src.api.main._verificar_acesso_output",
        side_effect=HTTPException(status_code=404, detail="Acesso negado"),
    ):
        res = test_client.post(
            "/v1/export/pdf",
            json={"source_type": "dossie", "source_id": "00000000-0000-0000-0000-000000000001"},
        )
    assert res.status_code == 404
