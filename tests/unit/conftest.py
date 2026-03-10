"""
conftest.py — aguarda entre testes para respeitar o rate limit Voyage AI (3 RPM).
"""

import time
import pytest

# 3 RPM = 1 chamada a cada 20s. Usamos 25s por segurança.
INTER_TEST_DELAY = 25


@pytest.fixture(autouse=True)
def aguardar_rate_limit(request):
    """Espera entre testes para não estourar o rate limit de 3 RPM."""
    yield
    # Aguarda após cada teste (exceto os que não chamam a API)
    marcadores_sem_api = {"query_vazia", "so_espacos"}
    test_name = request.node.name
    if not any(m in test_name for m in marcadores_sem_api):
        time.sleep(INTER_TEST_DELAY)
