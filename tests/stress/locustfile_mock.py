"""
tests/stress/locustfile_mock.py — Load test sem custo de API (zero LLM).

Testa apenas a infra: pgvector HNSW, PostgreSQL, connection pool, nginx.
Ideal para validar o servidor antes de gastar com chamadas de LLM.

Execução (Fase 1.2 — carga sem LLM):
  locust -f tests/stress/locustfile_mock.py \\
    --users 20 --spawn-rate 2 --run-time 10m \\
    --headless --csv results/load_mock \\
    -H https://orbis.tax

Execução (Fase 5 — soak 2h):
  locust -f tests/stress/locustfile_mock.py \\
    --users 5 --spawn-rate 1 --run-time 2h \\
    --headless --csv results/soak_2h \\
    -H https://orbis.tax

Execução (Fase 2 — stress 50 users):
  STRESS_TEST_EMAIL=... STRESS_TEST_PASSWORD=... \\
  locust -f tests/stress/locustfile_mock.py \\
    --users 50 --spawn-rate 2 --run-time 15m \\
    --headless --csv results/stress_50 \\
    -H https://orbis.tax
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from locust import HttpUser, task, between

from tests.stress.config import TEST_EMAIL, TEST_PASSWORD, QUERIES_FISCAIS

# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Usuário mock — sem chamadas LLM
# ---------------------------------------------------------------------------

class OrbisUserMock(HttpUser):
    """
    Simula carga de infra sem chamar LLM.
    wait_time menor (1-3s) para estressar mais a infra.
    Endpoints: /v1/chunks (pgvector), /v1/cases (DB), /v1/health (nginx).
    """
    wait_time = between(1, 3)

    def on_start(self):
        """Login se credenciais disponíveis, senão usa apenas /v1/health."""
        self.token = None
        self.headers = {}

        if not TEST_EMAIL or not TEST_PASSWORD:
            # Sem credenciais: apenas health check (válido para testar nginx/infra)
            return

        with self.client.post(
            "/api/v1/auth/login",
            json={"email": TEST_EMAIL, "senha": TEST_PASSWORD},
            catch_response=True,
            name="/v1/auth/login",
        ) as resp:
            if resp.status_code == 200:
                self.token = resp.json().get("access_token")
                self.headers = _bearer(self.token)
                resp.success()
            elif resp.status_code == 429:
                # Rate limit no login — não é falha
                resp.success()
            else:
                # Login falhou — continua sem token (apenas health ficará disponível)
                resp.success()

    # -------------------------------------------------------------------
    # Task 1 — Retrieval pgvector (peso 5, operação mais custosa da infra)
    # -------------------------------------------------------------------
    @task(5)
    def buscar_chunks(self):
        """GET /v1/chunks — Stress do índice HNSW pgvector."""
        if not self.token:
            return

        query = random.choice(QUERIES_FISCAIS)
        top_k = random.choice([1, 5, 10])

        with self.client.get(
            "/api/v1/chunks",
            params={"q": query, "top_k": top_k},
            headers=self.headers,
            catch_response=True,
            name="/v1/chunks",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code in (401, 402, 429):
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")

    # -------------------------------------------------------------------
    # Task 2 — Listagem de casos (peso 4, DB puro)
    # -------------------------------------------------------------------
    @task(4)
    def listar_casos(self):
        """GET /v1/cases — Stress do PostgreSQL (sem pgvector)."""
        if not self.token:
            return

        with self.client.get(
            "/api/v1/cases",
            headers=self.headers,
            catch_response=True,
            name="/v1/cases [GET]",
        ) as resp:
            if resp.status_code in (200, 401, 402):
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")

    # -------------------------------------------------------------------
    # Task 3 — Health check (peso 1, apenas nginx)
    # -------------------------------------------------------------------
    @task(1)
    def health(self):
        """GET /v1/health — Stress do nginx."""
        with self.client.get(
            "/api/v1/health",
            catch_response=True,
            name="/v1/health",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")
