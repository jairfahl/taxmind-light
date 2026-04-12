"""
tests/integration/test_auth_endpoints.py — TC-AUTH-01..TC-AUTH-08

Testes de integração para os endpoints de autenticação:
  POST /v1/auth/login
  GET  /v1/auth/me
  PATCH /v1/auth/onboarding

Requer banco PostgreSQL rodando em localhost:5436.
Usuários de teste são criados/removidos pelo conftest.py (scope=session).
"""
import time

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

# Cliente síncrono compartilhado (sem bypass de auth para TC-AUTH-05)
_raw_client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# TC-AUTH-01 — login com credenciais válidas
# ---------------------------------------------------------------------------
def test_login_valido(qa_user_id):
    """TC-AUTH-01: POST /v1/auth/login retorna 200 + access_token + perfil."""
    resp = _raw_client.post(
        "/v1/auth/login",
        json={"email": "qa@tribus-ai.com.br", "senha": "Qa@12345"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data
    assert data["user"]["perfil"] in ("USER", "ADMIN")
    assert data["user"]["email"] == "qa@tribus-ai.com.br"


# ---------------------------------------------------------------------------
# TC-AUTH-02 — login com senha errada
# ---------------------------------------------------------------------------
def test_login_senha_errada(qa_user_id):
    """TC-AUTH-02: senha incorreta deve retornar 401."""
    resp = _raw_client.post(
        "/v1/auth/login",
        json={"email": "qa@tribus-ai.com.br", "senha": "SenhaErrada!"},
    )
    assert resp.status_code == 401
    # Mensagem deve ser genérica (não revelar detalhes)
    detail = resp.json().get("detail", "")
    assert "credenciais" in detail.lower() or "inválid" in detail.lower()


# ---------------------------------------------------------------------------
# TC-AUTH-03 — rate-limit em /v1/auth/login (5 req/min)
# ---------------------------------------------------------------------------
def test_login_rate_limit(qa_user_id):
    """TC-AUTH-03: a 6ª requisição (mesma tentativa) deve retornar 429."""
    payload = {"email": "ratelimit-tc03@tribus-ai.com.br", "senha": "x"}
    got_429 = False
    # Até 8 tentativas para garantir que o limite de 5/min é atingido
    for i in range(8):
        r = _raw_client.post("/v1/auth/login", json=payload)
        if r.status_code == 429:
            got_429 = True
            break
        # Pequena pausa para não travar o event loop, mas dentro do mesmo minuto
        if i < 7:
            time.sleep(0.1)
    assert got_429, "Rate limit de 5/min não foi acionado após 8 tentativas"


# ---------------------------------------------------------------------------
# TC-AUTH-04 — /v1/auth/me sem parâmetro user_id → 422
# ---------------------------------------------------------------------------
def test_auth_me_sem_user_id():
    """TC-AUTH-04: GET /v1/auth/me sem query param user_id deve retornar 422."""
    resp = _raw_client.get("/v1/auth/me")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TC-AUTH-05 — X-Api-Key inválida (cliente sem override)
# ---------------------------------------------------------------------------
def test_x_api_key_invalida():
    """
    TC-AUTH-05: endpoint protegido com X-Api-Key incorreta deve retornar 401.
    Este teste usa o app diretamente SEM o override do conftest para verificar
    que a proteção está ativa. Usa o fixture autouse=False implícito ao não
    depender do override.
    """
    from src.api.main import app as _app
    from src.api.auth_api import verificar_token_api

    # Temporariamente remover o override para simular cliente sem bypass
    original = _app.dependency_overrides.pop(verificar_token_api, None)
    try:
        client_no_override = TestClient(_app, raise_server_exceptions=False)
        resp = client_no_override.get(
            "/v1/auth/me",
            params={"user_id": "00000000-0000-0000-0000-000000000000"},
            headers={"x-api-key": "chave-invalida"},
        )
        assert resp.status_code == 401
    finally:
        if original is not None:
            _app.dependency_overrides[verificar_token_api] = original


# ---------------------------------------------------------------------------
# TC-AUTH-06 — GET /v1/auth/me com user_id válido
# ---------------------------------------------------------------------------
def test_auth_me_usuario_valido(qa_user_id):
    """TC-AUTH-06: GET /v1/auth/me com user_id correto retorna 200 + campos obrigatórios."""
    resp = _raw_client.get("/v1/auth/me", params={"user_id": qa_user_id})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for campo in ("id", "email", "nome", "perfil", "onboarding_step"):
        assert campo in data, f"Campo '{campo}' ausente na resposta"
    assert data["email"] == "qa@tribus-ai.com.br"


# ---------------------------------------------------------------------------
# TC-AUTH-07 — PATCH /v1/auth/onboarding com dados válidos
# ---------------------------------------------------------------------------
def test_auth_onboarding_valido(qa_user_id):
    """TC-AUTH-07: PATCH /v1/auth/onboarding deve retornar 200 + {"ok": true}."""
    resp = _raw_client.patch(
        "/v1/auth/onboarding",
        json={
            "user_id": qa_user_id,
            "tipo_atuacao": "gestor_fiscal",
            "cargo_responsavel": "Diretor Tributário",
            "onboarding_step": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("ok") is True


# ---------------------------------------------------------------------------
# TC-AUTH-08 — GET /v1/auth/me retorna todos os campos esperados
# ---------------------------------------------------------------------------
def test_auth_me_campos_completos(qa_user_id):
    """TC-AUTH-08: resposta de /v1/auth/me contém id, email, nome, perfil, tenant_id, onboarding_step."""
    resp = _raw_client.get("/v1/auth/me", params={"user_id": qa_user_id})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    campos_obrigatorios = ["id", "email", "nome", "perfil", "tenant_id", "onboarding_step"]
    for campo in campos_obrigatorios:
        assert campo in data, f"Campo '{campo}' ausente"
    # tenant_id pode ser None pois não foi atribuído — mas a chave deve existir
    assert isinstance(data["onboarding_step"], int)
