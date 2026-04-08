"""
conftest.py raiz — Variáveis de ambiente obrigatórias para toda a suite de testes.

Executado pelo pytest antes de qualquer coleta ou importação de módulo de teste.
Define valores de teste para JWT_SECRET e API_INTERNAL_KEY, que são obrigatórios
pelos módulos auth.py e src/api/auth_api.py.
"""
import os

# Obrigatórios para auth.py e src/api/auth_api.py iniciarem sem RuntimeError
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-do-not-use-in-production")
os.environ.setdefault("API_INTERNAL_KEY", "test-api-internal-key-do-not-use-in-prod")
