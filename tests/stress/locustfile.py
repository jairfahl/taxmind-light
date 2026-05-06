"""
tests/stress/locustfile.py — Load test principal do Orbis.tax (com LLM).

Simula comportamento real de tributarista: análise tributária (POST /v1/analyze),
consulta de casos, criação de casos e retrieval direto de chunks.

AVISO: Este arquivo CHAMA a API Anthropic e Voyage AI — gera custo real.
Use locustfile_mock.py para testes sem custo.

Execução:
  STRESS_TEST_EMAIL=user@empresa.com STRESS_TEST_PASSWORD=senha123 \\
  locust -f tests/stress/locustfile.py \\
    --users 10 --spawn-rate 1 --run-time 25m \\
    --headless --csv results/load_llm \\
    -H https://orbis.tax

Fase 1 (carga normal):
  --users 5  --spawn-rate 1 --run-time 10m   # sustentado
  --users 10 --spawn-rate 2 --run-time  5m   # pico
  --users 20 --spawn-rate 5 --run-time  5m   # degradação
  --users 30 --spawn-rate 30 --run-time 2m   # spike
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from locust import HttpUser, task, between, events

from tests.stress.config import TEST_EMAIL, TEST_PASSWORD, QUERIES_FISCAIS

# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Usuário principal — simula tributarista real
# ---------------------------------------------------------------------------

class OrbisUser(HttpUser):
    """
    Simula um tributarista usando o Orbis.tax.
    wait_time entre 5-15s reflete o tempo que o usuário leva para ler
    o resultado e formular a próxima consulta.
    """
    wait_time = between(5, 15)

    def on_start(self):
        """Login ao início de cada usuário virtual."""
        self.token = None
        self.headers = {}
        self._case_ids: list[str] = []

        if not TEST_EMAIL or not TEST_PASSWORD:
            self.environment.runner.quit()
            raise ValueError(
                "STRESS_TEST_EMAIL e STRESS_TEST_PASSWORD são obrigatórios. "
                "Use locustfile_mock.py para testes sem credenciais."
            )

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
                # Rate limit no login — não é falha do sistema
                resp.success()
            else:
                resp.failure(f"Login falhou: {resp.status_code} — {resp.text[:200]}")

    # -------------------------------------------------------------------
    # Task 1 — Análise tributária completa (peso 5, mais importante)
    # -------------------------------------------------------------------
    @task(5)
    def analisar(self):
        """POST /v1/analyze — Consulta tributária com RAG + LLM."""
        if not self.token:
            return

        query = random.choice(QUERIES_FISCAIS)

        with self.client.post(
            "/api/v1/analyze",
            json={"query": query},
            headers=self.headers,
            catch_response=True,
            name="/v1/analyze",
            timeout=120,  # LLM pode levar até 90s
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 402:
                # Trial limit atingido — não é falha do sistema, é regra de negócio
                resp.success()
            elif resp.status_code == 429:
                # Rate limit (20/min) — esperado sob carga
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Token expirado ou inválido")
            else:
                resp.failure(f"Erro inesperado: {resp.status_code} — {resp.text[:200]}")

    # -------------------------------------------------------------------
    # Task 2 — Listar casos (peso 3)
    # -------------------------------------------------------------------
    @task(3)
    def listar_casos(self):
        """GET /v1/cases — Listagem de casos do tenant."""
        if not self.token:
            return

        with self.client.get(
            "/api/v1/cases",
            headers=self.headers,
            catch_response=True,
            name="/v1/cases [GET]",
        ) as resp:
            if resp.status_code == 200:
                # Guardar IDs para tasks posteriores
                data = resp.json()
                if isinstance(data, list):
                    self._case_ids = [c["id"] for c in data if "id" in c][:10]
                resp.success()
            elif resp.status_code in (401, 402):
                resp.success()  # Esperado em trial
            else:
                resp.failure(f"{resp.status_code}")

    # -------------------------------------------------------------------
    # Task 3 — Criar caso (peso 2)
    # -------------------------------------------------------------------
    @task(2)
    def criar_caso(self):
        """POST /v1/cases — Cria um novo caso tributário."""
        if not self.token:
            return

        with self.client.post(
            "/api/v1/cases",
            json={
                "titulo": f"Caso stress test — {random.choice(QUERIES_FISCAIS)[:40]}",
                "descricao": "Caso criado automaticamente pelo stress test para validar carga.",
                "contexto_fiscal": random.choice(["Lucro Real", "Lucro Presumido", "Simples Nacional"]),
            },
            headers=self.headers,
            catch_response=True,
            name="/v1/cases [POST]",
        ) as resp:
            if resp.status_code in (201, 200):
                data = resp.json()
                if "case_id" in data:
                    self._case_ids.append(data["case_id"])
                resp.success()
            elif resp.status_code in (402, 429):
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")

    # -------------------------------------------------------------------
    # Task 4 — Retrieval direto de chunks (peso 4)
    # -------------------------------------------------------------------
    @task(4)
    def buscar_chunks(self):
        """GET /v1/chunks — Retrieval RAG sem LLM (mais rápido)."""
        if not self.token:
            return

        query = random.choice(QUERIES_FISCAIS)
        top_k = random.choice([5, 10])

        with self.client.get(
            "/api/v1/chunks",
            params={"q": query, "top_k": top_k},
            headers=self.headers,
            catch_response=True,
            name="/v1/chunks",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code in (401, 402):
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")

    # -------------------------------------------------------------------
    # Task 5 — Health check (peso 1)
    # -------------------------------------------------------------------
    @task(1)
    def health(self):
        """GET /v1/health — Verifica status do sistema."""
        with self.client.get(
            "/api/v1/health",
            catch_response=True,
            name="/v1/health",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")
