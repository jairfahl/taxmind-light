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
from src.api.main import app
from src.api.auth_api import verificar_token_api


@pytest.fixture(autouse=True)
def bypass_internal_auth():
    """
    Override da autenticação interna X-API-Key para testes de integração.
    Evita que os testes precisem enviar o header em cada requisição.
    """
    app.dependency_overrides[verificar_token_api] = lambda: None
    yield
    app.dependency_overrides.pop(verificar_token_api, None)
