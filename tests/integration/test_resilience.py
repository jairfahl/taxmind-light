"""
tests/integration/test_resilience.py — Testes de resiliência (Fase 3).

Valida comportamento do sistema sob falhas:
  3.1 — API down / DB down (requer Docker rodando localmente)
  3.2 — Falha da API Anthropic (mock de resilient_call)
  3.3 — Falha do Voyage AI (mock de get_embedding)

Os testes 3.1 são marcados com @pytest.mark.docker e requerem
permissão de executar docker stop/start (normalmente apenas em dev local).

Execução completa:
  pytest tests/integration/test_resilience.py -v -m resilience

Execução apenas mocks (sem docker):
  pytest tests/integration/test_resilience.py -v -m "resilience and not docker"
"""
import os
import time
from unittest.mock import patch, MagicMock

import pytest
import httpx
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("STRESS_BASE_URL", "http://localhost:8000")

pytestmark = pytest.mark.resilience


# ---------------------------------------------------------------------------
# 3.2 — Falha da API Anthropic
# ---------------------------------------------------------------------------

class TestFalhaAnthropic:
    """Testa comportamento quando a API Anthropic está indisponível."""

    def setup_method(self):
        # Importação lazy — evitar problema de circular import em testes unitários
        os.environ.setdefault("JWT_SECRET", "test-jwt-secret-resilience")
        os.environ.setdefault("API_INTERNAL_KEY", "test-api-key-resilience")

    def test_anthropic_429_retorna_erro_amigavel(self):
        """
        Testando comportamento quando Anthropic retorna 429 (rate limit).
        Por que importa: o sistema deve retentar e, se esgotar retries, retornar
        erro amigável ao usuário — nunca travar ou expor exceção interna.
        Esperado: resposta com erro claro (5xx ou 4xx) sem stack trace.
        """
        from anthropic import RateLimitError
        import httpx as _httpx

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}

        with patch("src.resilience.backoff.resilient_call") as mock_call:
            mock_call.side_effect = RateLimitError(
                message="Rate limit exceeded",
                response=mock_response,
                body={"error": {"message": "Rate limit exceeded"}},
            )

            from src.api.main import app
            from src.api.auth_api import verificar_acesso_tenant
            app.dependency_overrides[verificar_acesso_tenant] = lambda: {
                "sub": "00000000-0000-0000-0000-000000000099",
                "email": "test@resilience.local",
                "perfil": "USER",
            }

            try:
                client = TestClient(app)
                resp = client.post(
                    "/v1/analyze",
                    json={"query": "Como funciona o IBS?"},
                    headers={"Authorization": "Bearer fake-token"},
                )
                # Não deve ser 200 (sem resultado), não deve ser 500 com stack trace
                assert resp.status_code != 200 or "erro" in resp.text.lower(), (
                    "AVISO — Anthropic mockado como 429 mas analyze retornou 200"
                )
                assert "Traceback" not in resp.text, (
                    f"FALHOU — stack trace exposto em falha Anthropic 429. Body: {resp.text[:300]}"
                )
            finally:
                app.dependency_overrides.clear()

    def test_anthropic_500_retorna_erro_amigavel(self):
        """
        Testando comportamento quando Anthropic retorna 500 (erro interno).
        Esperado: erro amigável — nunca crash da API.
        """
        from anthropic import APIStatusError
        import httpx as _httpx

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}

        with patch("src.resilience.backoff.resilient_call") as mock_call:
            mock_call.side_effect = APIStatusError(
                message="Internal server error",
                response=mock_response,
                body={},
            )

            from src.api.main import app
            from src.api.auth_api import verificar_acesso_tenant
            app.dependency_overrides[verificar_acesso_tenant] = lambda: {
                "sub": "00000000-0000-0000-0000-000000000099",
                "email": "test@resilience.local",
                "perfil": "USER",
            }

            try:
                client = TestClient(app)
                resp = client.post(
                    "/v1/analyze",
                    json={"query": "Como funciona o IBS?"},
                    headers={"Authorization": "Bearer fake-token"},
                )
                assert "Traceback" not in resp.text, (
                    f"FALHOU — stack trace exposto em falha Anthropic 500. Body: {resp.text[:300]}"
                )
            finally:
                app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 3.3 — Falha do Voyage AI (embeddings)
# ---------------------------------------------------------------------------

class TestFalhaVoyage:
    """Testa comportamento quando o Voyage AI está indisponível."""

    def setup_method(self):
        os.environ.setdefault("JWT_SECRET", "test-jwt-secret-resilience")
        os.environ.setdefault("API_INTERNAL_KEY", "test-api-key-resilience")

    def test_voyage_429_chunks_retorna_erro_claro(self):
        """
        Testando comportamento quando Voyage retorna 429 em /v1/chunks.
        Por que importa: se o embedding falha, o retrieval falha — o usuário
        deve receber uma mensagem clara, não um 500.
        Esperado: 4xx ou 5xx amigável — nunca stack trace.
        """
        with patch("src.resilience.backoff.resilient_call") as mock_call:
            mock_call.side_effect = Exception("Voyage API rate limit exceeded")

            from src.api.main import app
            from src.api.auth_api import verificar_token_api
            app.dependency_overrides[verificar_token_api] = lambda: None

            try:
                client = TestClient(app)
                resp = client.get(
                    "/v1/chunks",
                    params={"q": "Qual é a alíquota do IBS?"},
                )
                assert "Traceback" not in resp.text, (
                    f"FALHOU — stack trace exposto em falha Voyage. Body: {resp.text[:300]}"
                )
            finally:
                app.dependency_overrides.clear()

    def test_voyage_timeout_nao_trava_api(self):
        """
        Testando que timeout no Voyage não trava a API indefinidamente.
        Esperado: resposta dentro de 30s (não trava esperando o Voyage).
        """
        import time

        with patch("src.resilience.backoff.resilient_call") as mock_call:
            def slow_call(*args, **kwargs):
                time.sleep(2)  # Simula delay mas não eternamente
                raise TimeoutError("Voyage AI timeout simulado")

            mock_call.side_effect = slow_call

            from src.api.main import app
            from src.api.auth_api import verificar_token_api
            app.dependency_overrides[verificar_token_api] = lambda: None

            try:
                client = TestClient(app)
                start = time.time()
                resp = client.get("/v1/chunks", params={"q": "IBS"})
                elapsed = time.time() - start

                assert elapsed < 30, (
                    f"FALHOU — API travou por {elapsed:.1f}s esperando Voyage (máx: 30s)"
                )
                assert "Traceback" not in resp.text
            finally:
                app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 3.1 — Container kill/restart (Docker — requer permissão local)
# ---------------------------------------------------------------------------

class TestContainerKill:
    """
    Testes que requerem Docker disponível localmente.
    Executar manualmente: pytest -m docker tests/integration/test_resilience.py -v
    """

    @pytest.mark.docker
    def test_api_down_health_conexao_recusada(self):
        """
        Testando comportamento quando o container da API está parado.
        Por que importa: load balancer precisa detectar API offline.
        Esperado: conexão recusada (não 500 com stack trace).
        Instrução manual:
          docker stop tribus-ai-api
          curl -v http://localhost:8000/v1/health  # deve recusar conexão
          docker start tribus-ai-api
          curl -v http://localhost:8000/v1/health  # deve retornar 200 em < 30s
        """
        import subprocess

        # Para o container
        result = subprocess.run(
            ["docker", "stop", "tribus-ai-api"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            pytest.skip(f"Docker não disponível: {result.stderr}")

        try:
            time.sleep(2)
            with httpx.Client(timeout=5) as client:
                try:
                    resp = client.get(f"{BASE_URL}/v1/health")
                    # Se chegou aqui, o nginx ainda está de pé mas deve retornar erro
                    assert resp.status_code in (502, 503, 504), (
                        f"FALHOU — API parada mas retornou {resp.status_code}"
                    )
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass  # Conexão recusada — comportamento correto
        finally:
            # Reinicia o container
            subprocess.run(
                ["docker", "start", "tribus-ai-api"],
                capture_output=True, text=True, timeout=30,
            )

    @pytest.mark.docker
    def test_api_restart_recupera_em_30s(self):
        """
        Testando que a API se recupera em menos de 30s após restart.
        Por que importa: SLA de disponibilidade exige recuperação rápida.
        """
        import subprocess

        result = subprocess.run(
            ["docker", "restart", "tribus-ai-api"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            pytest.skip(f"Docker não disponível: {result.stderr}")

        start = time.time()
        recovered = False
        deadline = start + 30

        with httpx.Client(timeout=3) as client:
            while time.time() < deadline:
                try:
                    resp = client.get(f"{BASE_URL}/v1/health")
                    if resp.status_code == 200:
                        recovered = True
                        break
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass
                time.sleep(1)

        elapsed = time.time() - start
        assert recovered, (
            f"FALHOU — API não se recuperou em 30s após restart (elapsed: {elapsed:.1f}s)"
        )

    @pytest.mark.docker
    def test_db_down_api_retorna_503(self):
        """
        Testando comportamento quando o PostgreSQL está parado.
        Por que importa: falha do banco não deve expor stack trace.
        Esperado: /v1/health retorna 503 (não 500 com traceback PG).
        Instrução manual:
          docker stop tribus-ai-db
          curl -v http://localhost:8000/v1/health  # deve retornar 503
          docker start tribus-ai-db
          sleep 10  # aguarda reconexão do pool
          curl -v http://localhost:8000/v1/health  # deve retornar 200
        """
        import subprocess

        result = subprocess.run(
            ["docker", "stop", "tribus-ai-db"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            pytest.skip(f"Docker não disponível ou container não existe: {result.stderr}")

        try:
            time.sleep(3)
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{BASE_URL}/v1/health")
                # Deve retornar erro claro — sem traceback
                assert resp.status_code in (503, 500), (
                    f"AVISO — status inesperado com DB parado: {resp.status_code}"
                )
                assert "Traceback" not in resp.text, (
                    f"FALHOU — stack trace exposto quando DB está parado. Body: {resp.text[:300]}"
                )
        finally:
            subprocess.run(
                ["docker", "start", "tribus-ai-db"],
                capture_output=True, text=True, timeout=30,
            )
