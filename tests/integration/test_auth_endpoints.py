"""
tests/integration/test_auth_endpoints.py — TC-AUTH-01..TC-AUTH-08, TC-SESS-01, TC-BILL-01..TC-BILL-03

Testes de integração para os endpoints de autenticação:
  POST /v1/auth/login
  GET  /v1/auth/me
  PATCH /v1/auth/onboarding

Requer banco PostgreSQL rodando em localhost:5436.
Usuários de teste são criados/removidos pelo conftest.py (scope=session).
"""
import os
import time

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

_DB_URL = os.environ.get("DATABASE_URL", "postgresql://taxmind:taxmind123@localhost:5436/taxmind_db")

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


# ---------------------------------------------------------------------------
# TC-SESS-01 — Segundo login invalida sessão anterior em /v1/auth/me
# ---------------------------------------------------------------------------
def test_sessao_unica_segundo_login_invalida_anterior(qa_user_id):
    """
    TC-SESS-01: quando session_id do JWT difere do DB (novo login em outro device),
    GET /v1/auth/me deve retornar 401 com detail='session_expired'.

    Simula segundo login atualizando session_id no DB diretamente (evita rate limit
    de /v1/auth/login que é compartilhado com outros testes da suite).
    """
    import uuid as _uuid
    import psycopg2
    import os
    from auth import gerar_token, Usuario, buscar_usuario_por_email
    from src.api.main import app as _app
    from src.api.auth_api import verificar_token_api, verificar_sessao
    from datetime import datetime, timezone

    # 1. Buscar usuário atual e gerar JWT com session_id atual do DB
    conn = psycopg2.connect(_DB_URL)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT session_id FROM users WHERE id = %s LIMIT 1", (qa_user_id,)
        )
        row = cur.fetchone()
    conn.close()

    current_session_id = str(row[0]) if row and row[0] else str(_uuid.uuid4())
    usuario_fake = Usuario(
        id=qa_user_id,
        email="qa@tribus-ai.com.br",
        nome="QA User",
        perfil="USER",
        ativo=True,
        primeiro_uso=None,
        criado_em=datetime.now(timezone.utc),
        session_id=current_session_id,
    )
    token_antigo = gerar_token(usuario_fake)

    # 2. Simular segundo login: atualizar session_id no DB (invalida JWT antigo)
    novo_session_id = str(_uuid.uuid4())
    conn2 = psycopg2.connect(_DB_URL)
    with conn2.cursor() as cur:
        cur.execute(
            "UPDATE users SET session_id = %s WHERE id = %s",
            (novo_session_id, qa_user_id),
        )
        conn2.commit()
    conn2.close()

    # 3. Chamar /v1/auth/me com o JWT antigo, sem override de verificar_sessao
    original_token = _app.dependency_overrides.pop(verificar_token_api, None)
    original_sessao = _app.dependency_overrides.pop(verificar_sessao, None)
    try:
        api_key = os.environ.get("API_INTERNAL_KEY", "test-internal-key-integration")
        client_real = TestClient(_app, raise_server_exceptions=False)
        resp = client_real.get(
            "/v1/auth/me",
            params={"user_id": qa_user_id},
            headers={
                "x-api-key": api_key,
                "Authorization": f"Bearer {token_antigo}",
            },
        )
        assert resp.status_code == 401, resp.text
        assert resp.json().get("detail") == "session_expired"
    finally:
        if original_token is not None:
            _app.dependency_overrides[verificar_token_api] = original_token
        if original_sessao is not None:
            _app.dependency_overrides[verificar_sessao] = original_sessao
        # Restaurar session_id original para não quebrar testes subsequentes
        conn3 = psycopg2.connect(_DB_URL)
        with conn3.cursor() as cur:
            cur.execute(
                "UPDATE users SET session_id = %s WHERE id = %s",
                (current_session_id, qa_user_id),
            )
            conn3.commit()
        conn3.close()


# ---------------------------------------------------------------------------
# TC-BILL-01 — POST /v1/billing/subscribe com tenant sem assinatura
# TC-BILL-02 — POST /v1/billing/subscribe com tenant já assinante → 409
# TC-BILL-03 — PATCH /v1/admin/tenants/{id}/desconto
# ---------------------------------------------------------------------------
def test_billing_desconto_patch(qa_user_id):
    """
    TC-BILL-03: PATCH /v1/admin/tenants/{id}/desconto deve retornar 200 com
    desconto_percentual atualizado.
    Usa tenant_id do usuário QA (se existir). Se não houver tenant, skip.
    """
    import psycopg2
    conn = psycopg2.connect(_DB_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id FROM users WHERE id = %s LIMIT 1", (qa_user_id,))
        row = cur.fetchone()
    conn.close()

    if not row or not row[0]:
        pytest.skip("Usuário QA não tem tenant_id — pulando TC-BILL-03")

    tenant_id = str(row[0])
    resp = _raw_client.patch(
        f"/v1/admin/tenants/{tenant_id}/desconto",
        json={"desconto_percentual": 20.0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["desconto_percentual"] == 20.0


def test_billing_subscribe_tenant_sem_assinatura(qa_user_id):
    """
    TC-BILL-01: POST /v1/billing/subscribe com tenant sem assinatura deve retornar
    200 e invoice_url. Asaas é mockado via unittest.mock.patch.
    """
    import unittest.mock as mock
    import psycopg2
    conn = psycopg2.connect(_DB_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id FROM users WHERE id = %s LIMIT 1", (qa_user_id,))
        row = cur.fetchone()
    conn.close()

    if not row or not row[0]:
        pytest.skip("Usuário QA não tem tenant_id — pulando TC-BILL-01")

    tenant_id = str(row[0])

    # Mock das funções Asaas para não chamar sandbox real
    with mock.patch("src.billing.asaas.criar_customer") as mock_customer, \
         mock.patch("src.billing.asaas.criar_assinatura") as mock_sub, \
         mock.patch("src.billing.asaas.buscar_pagamentos_assinatura") as mock_pag:

        mock_customer.return_value = {"id": "cus_mock_123"}
        mock_sub.return_value = {"id": "sub_mock_456"}
        mock_pag.return_value = {"data": [{"invoiceUrl": "https://sandbox.asaas.com/i/mock"}]}

        resp = _raw_client.post(
            "/v1/billing/subscribe",
            json={"tenant_id": tenant_id, "billing_type": "PIX"},
        )

    # Pode retornar 200 ou 409 (se já tiver assinatura de test anterior)
    assert resp.status_code in (200, 409), resp.text
    if resp.status_code == 200:
        data = resp.json()
        assert "invoice_url" in data
        assert "valor" in data


def test_billing_subscribe_tenant_ja_assinante(qa_user_id):
    """
    TC-BILL-02: POST /v1/billing/subscribe com tenant que já tem assinatura
    deve retornar 409 Conflict.
    """
    import unittest.mock as mock
    import psycopg2
    conn = psycopg2.connect(_DB_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id FROM users WHERE id = %s LIMIT 1", (qa_user_id,))
        row = cur.fetchone()
        if row and row[0]:
            # Forçar assinatura existente temporariamente
            cur.execute(
                "UPDATE tenants SET asaas_subscription_id = 'sub_fake_test' WHERE id = %s",
                (str(row[0]),),
            )
        conn.commit()
    conn.close()

    if not row or not row[0]:
        pytest.skip("Usuário QA não tem tenant_id — pulando TC-BILL-02")

    tenant_id = str(row[0])
    resp = _raw_client.post(
        "/v1/billing/subscribe",
        json={"tenant_id": tenant_id, "billing_type": "CREDIT_CARD"},
    )
    assert resp.status_code == 409, resp.text

    # Limpar assinatura fake
    conn2 = psycopg2.connect(_DB_URL)
    with conn2.cursor() as cur:
        cur.execute(
            "UPDATE tenants SET asaas_subscription_id = NULL WHERE id = %s AND asaas_subscription_id = 'sub_fake_test'",
            (tenant_id,),
        )
        conn2.commit()
    conn2.close()
