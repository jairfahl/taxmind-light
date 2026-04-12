"""
tests/integration/conftest.py — Configuração dos testes de integração.

Define variáveis de ambiente obrigatórias antes de qualquer import e
faz override das dependências de autenticação interna para os testes.
"""
import os

# Definir env vars obrigatórias antes de importar src.api.main
os.environ.setdefault("API_INTERNAL_KEY", "test-internal-key-integration")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-integration-only")

import pytest
import psycopg2
import psycopg2.extras

from fastapi.testclient import TestClient
from src.api.main import app
from src.api.auth_api import verificar_token_api
from auth import gerar_hash_senha, gerar_token, buscar_usuario_por_email, Usuario


# ---------------------------------------------------------------------------
# Constantes dos usuários de teste
# ---------------------------------------------------------------------------
_QA_USER_EMAIL      = "qa@tribus-ai.com.br"
_QA_USER_PASSWORD   = "Qa@12345"
_QA_USER_NOME       = "QA User Integration"
_QA_USER_PERFIL     = "USER"

_QA_ADMIN_EMAIL     = "qaadmin@tribus-ai.com.br"
_QA_ADMIN_PASSWORD  = "QaAdmin@12345"
_QA_ADMIN_NOME      = "QA Admin Integration"
_QA_ADMIN_PERFIL    = "ADMIN"


def _get_db_conn():
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://taxmind:taxmind123@localhost:5436/taxmind_db",
    )
    return psycopg2.connect(db_url)


def _upsert_test_user(email: str, nome: str, perfil: str, password: str) -> str:
    """
    Cria o usuário de teste se não existir, ou atualiza senha/nome se já existir.
    Retorna o UUID do usuário.
    """
    senha_hash = gerar_hash_senha(password)
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, nome, senha_hash, perfil, ativo)
                VALUES (%s, %s, %s, %s, true)
                ON CONFLICT (email) DO UPDATE
                    SET nome = EXCLUDED.nome,
                        senha_hash = EXCLUDED.senha_hash,
                        perfil = EXCLUDED.perfil,
                        ativo = true
                RETURNING id::text
                """,
                (email.lower(), nome, senha_hash, perfil),
            )
            user_id = cur.fetchone()[0]
        conn.commit()
        return user_id
    finally:
        conn.close()


def _delete_test_user(email: str) -> None:
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email.lower(),))
        conn.commit()
    finally:
        conn.close()


def _build_usuario(user_id: str, email: str, nome: str, perfil: str) -> Usuario:
    from datetime import datetime, timezone
    return Usuario(
        id=user_id,
        email=email,
        nome=nome,
        perfil=perfil,
        ativo=True,
        primeiro_uso=None,
        criado_em=datetime.now(timezone.utc),
        tenant_id=None,
    )


# ---------------------------------------------------------------------------
# Fixtures de sessão — criação/remoção de usuários de teste
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qa_user_id() -> str:
    uid = _upsert_test_user(
        _QA_USER_EMAIL,
        _QA_USER_NOME,
        _QA_USER_PERFIL,
        _QA_USER_PASSWORD,
    )
    yield uid
    _delete_test_user(_QA_USER_EMAIL)


@pytest.fixture(scope="session")
def qa_admin_id() -> str:
    uid = _upsert_test_user(
        _QA_ADMIN_EMAIL,
        _QA_ADMIN_NOME,
        _QA_ADMIN_PERFIL,
        _QA_ADMIN_PASSWORD,
    )
    yield uid
    _delete_test_user(_QA_ADMIN_EMAIL)


@pytest.fixture(scope="session")
def user_token(qa_user_id: str) -> str:
    usuario = _build_usuario(qa_user_id, _QA_USER_EMAIL, _QA_USER_NOME, _QA_USER_PERFIL)
    return gerar_token(usuario)


@pytest.fixture(scope="session")
def admin_token(qa_admin_id: str) -> str:
    usuario = _build_usuario(qa_admin_id, _QA_ADMIN_EMAIL, _QA_ADMIN_NOME, _QA_ADMIN_PERFIL)
    return gerar_token(usuario)


@pytest.fixture(scope="session")
def user_id(qa_user_id: str) -> str:
    return qa_user_id


# ---------------------------------------------------------------------------
# TestClient fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Override autouse — bypass X-Api-Key para todos os testes de integração
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def bypass_internal_auth():
    """
    Override da autenticação interna X-API-Key para testes de integração.
    Evita que os testes precisem enviar o header em cada requisição.
    """
    app.dependency_overrides[verificar_token_api] = lambda: None
    yield
    app.dependency_overrides.pop(verificar_token_api, None)
