"""
tests/integration/test_protocol_api.py — Testes de integração dos endpoints de protocolo.
Requer banco rodando com tabelas Sprint 3 criadas.
Executa com: pytest tests/integration/test_protocol_api.py -v

Protocolo de 6 passos:
  Step 1 — Registrar & Classificar  (titulo, descricao, contexto_fiscal, premissas, periodo_fiscal)
  Step 2 — Estruturar               (riscos, dados_qualidade)
  Step 3 — Analisar                 (query_analise, analise_result)
  Step 4 — Hipotetizar              (hipotese_gestor)
  Step 5 — Decidir                  (recomendacao, decisao_final, decisor)  ← carimbo triggered aqui
  Step 6 — Ciclo Pós-Decisão        (resultado_real, data_revisao, aprendizado_extraido)  ← terminal
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _criar_caso_fixture(
    titulo: str = "Caso teste integração protocolo API",
    descricao: str = "Descrição de teste",
    contexto_fiscal: str = "Lucro Presumido",
    premissas: list | None = None,
    periodo_fiscal: str = "2025-01 a 2025-12",
) -> int:
    """Cria um caso e retorna o case_id."""
    resp = client.post("/v1/cases", json={
        "titulo": titulo,
        "descricao": descricao,
        "contexto_fiscal": contexto_fiscal,
        "premissas": premissas or ["Premissa padrão de teste um", "Premissa padrão de teste dois"],
        "periodo_fiscal": periodo_fiscal,
    })
    assert resp.status_code == 201, f"Falha ao criar caso: {resp.text}"
    return resp.json()["case_id"]


# ---------------------------------------------------------------------------
# 1. POST /v1/cases — criar caso válido
# ---------------------------------------------------------------------------
def test_criar_caso_valido():
    resp = client.post("/v1/cases", json={
        "titulo": "Caso de integração válido Sprint3",
        "descricao": "Descrição detalhada do caso",
        "contexto_fiscal": "Empresa de TI — Lucro Real",
        "premissas": ["Empresa optante pelo Lucro Real", "Período 2025-01 a 2025-12"],
        "periodo_fiscal": "2025-01 a 2025-12",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "case_id" in data
    assert data["status"] == "rascunho"
    assert data["passo_atual"] == 1
    assert isinstance(data["case_id"], int)
    assert data["case_id"] > 0


def test_criar_caso_titulo_curto():
    resp = client.post("/v1/cases", json={
        "titulo": "Curto",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
        "premissas": ["p1", "p2"],
        "periodo_fiscal": "2025",
    })
    assert resp.status_code in (422, 400), f"Esperado 422/400, obtido {resp.status_code}"


def test_criar_caso_campos_ausentes():
    resp = client.post("/v1/cases", json={"titulo": "Apenas título longo suficiente"})
    assert resp.status_code == 422  # Pydantic validation — premissas e periodo_fiscal ausentes


# ---------------------------------------------------------------------------
# 2. GET /v1/cases/{case_id} — estado completo
# ---------------------------------------------------------------------------
def test_get_caso_existente():
    case_id = _criar_caso_fixture("Caso get estado completo teste")
    resp = client.get(f"/v1/cases/{case_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == case_id
    assert data["passo_atual"] == 1
    assert data["status"] == "rascunho"
    assert "steps" in data
    assert "historico" in data
    assert isinstance(data["historico"], list)
    assert len(data["historico"]) >= 1


def test_get_caso_inexistente():
    resp = client.get("/v1/cases/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. POST /v1/cases/{case_id}/steps/{passo} — avanço de passo
# ---------------------------------------------------------------------------
def test_submeter_step1_valido():
    case_id = _criar_caso_fixture("Caso submeter step um valido teste")
    resp = client.post(f"/v1/cases/{case_id}/steps/1", json={
        "dados": {
            "titulo": "Caso submeter step um valido teste",
            "descricao": "Descrição detalhada",
            "contexto_fiscal": "Lucro Presumido",
            "premissas": ["Empresa do Simples Nacional", "Período 2025"],
            "periodo_fiscal": "2025-01 a 2025-12",
        },
        "acao": "avancar",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["passo"] == 2
    assert data["case_id"] == case_id


def test_submeter_step1_dados_invalidos():
    case_id = _criar_caso_fixture("Caso dados invalidos step 1 teste")
    resp = client.post(f"/v1/cases/{case_id}/steps/1", json={
        "dados": {
            "titulo": "Curto",  # < 10 chars → ProtocolError
            "descricao": "desc",
            "contexto_fiscal": "ctx",
            "premissas": ["p1", "p2"],
            "periodo_fiscal": "2025",
        },
        "acao": "avancar",
    })
    assert resp.status_code == 422


def test_submeter_step_voltar():
    case_id = _criar_caso_fixture("Caso voltar step protocolo teste")
    # Avançar para Step 2
    client.post(f"/v1/cases/{case_id}/steps/1", json={
        "dados": {
            "titulo": "Caso voltar step protocolo teste",
            "descricao": "desc",
            "contexto_fiscal": "ctx",
            "premissas": ["premissa 1", "premissa 2"],
            "periodo_fiscal": "2025",
        },
        "acao": "avancar",
    })
    # Voltar para Step 1
    resp = client.post(f"/v1/cases/{case_id}/steps/2", json={
        "dados": {},
        "acao": "voltar",
    })
    assert resp.status_code == 200
    assert resp.json()["passo"] == 1


# ---------------------------------------------------------------------------
# 4. POST /v1/cases/{case_id}/carimbo/confirmar
# Carimbo é triggered ao concluir Step 5 (Decidir).
# ---------------------------------------------------------------------------
def test_confirmar_carimbo_justificativa_curta():
    resp = client.post("/v1/cases/1/carimbo/confirmar", json={
        "alert_id": 1,
        "justificativa": "Curta",
    })
    assert resp.status_code == 422


def test_confirmar_carimbo_alert_inexistente():
    resp = client.post("/v1/cases/1/carimbo/confirmar", json={
        "alert_id": 999999,
        "justificativa": "Justificativa longa suficiente para o teste de protocolo",
    })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Fluxo completo Step 1→Step 3 (smoke test)
# ---------------------------------------------------------------------------
def test_fluxo_step1_step2_step3():
    case_id = _criar_caso_fixture("Fluxo completo Step1 ate Step3 smoke test")

    # Step 1 → Step 2 (Registrar & Classificar — campos P1+P2 merged)
    r1 = client.post(f"/v1/cases/{case_id}/steps/1", json={
        "dados": {
            "titulo": "Fluxo completo Step1 ate Step3 smoke test",
            "descricao": "Descrição detalhada",
            "contexto_fiscal": "Lucro Real",
            "premissas": ["Empresa optante pelo Lucro Real", "Período 2025-01 a 2025-12"],
            "periodo_fiscal": "2025-01 a 2025-12",
        },
        "acao": "avancar",
    })
    assert r1.status_code == 200
    assert r1.json()["passo"] == 2

    # Step 2 → Step 3 (Estruturar — antigo P3)
    r2 = client.post(f"/v1/cases/{case_id}/steps/2", json={
        "dados": {
            "riscos": ["Risco de autuação por alíquota incorreta"],
            "dados_qualidade": "Dados completos e auditados",
        },
        "acao": "avancar",
    })
    assert r2.status_code == 200
    assert r2.json()["passo"] == 3

    # Step 3 → Step 4 (Analisar — antigo P4)
    r3 = client.post(f"/v1/cases/{case_id}/steps/3", json={
        "dados": {
            "query_analise": "SELECT nf.valor FROM nf WHERE competencia = '2025-01'",
            "analise_result": "Identificada divergência de 12% na alíquota de CSLL",
        },
        "acao": "avancar",
    })
    assert r3.status_code == 200
    assert r3.json()["passo"] == 4

    # Verificar estado final
    estado = client.get(f"/v1/cases/{case_id}").json()
    assert estado["passo_atual"] == 4
    assert estado["status"] == "em_analise"
    assert len(estado["historico"]) >= 4


# ---------------------------------------------------------------------------
# 6. Carimbo triggered ao concluir Step 5 — smoke test de integração
# ---------------------------------------------------------------------------
def test_carimbo_triggered_ao_concluir_step5():
    """Step 5 (Decidir) deve acionar o carimbo ao ser submetido com sucesso."""
    case_id = _criar_caso_fixture("Caso carimbo step5 smoke test integ")

    passos = [
        (1, {
            "titulo": "Caso carimbo step5 smoke test integ",
            "descricao": "Descrição detalhada do caso",
            "contexto_fiscal": "Lucro Real",
            "premissas": ["Empresa do Lucro Real", "Período 2025"],
            "periodo_fiscal": "2025-01 a 2025-12",
        }),
        (2, {"riscos": ["Risco de autuação"], "dados_qualidade": "Dados auditados"}),
        (3, {"query_analise": "SELECT 1", "analise_result": "Divergência identificada"}),
        (4, {"hipotese_gestor": "Hipótese: alíquota de CSLL aplicada incorretamente em 2025"}),
    ]
    for passo, dados in passos:
        r = client.post(f"/v1/cases/{case_id}/steps/{passo}", json={"dados": dados, "acao": "avancar"})
        assert r.status_code == 200, f"Falha no Step {passo}: {r.text}"

    # Step 5 — deve acionar carimbo
    r5 = client.post(f"/v1/cases/{case_id}/steps/5", json={
        "dados": {
            "recomendacao": "Retificar guias de CSLL dos meses com alíquota divergente",
            "decisao_final": "Aprovado para retificação imediata",
            "decisor": "Sócio-administrador",
        },
        "acao": "avancar",
    })
    assert r5.status_code == 200
    assert r5.json()["passo"] == 6
    # Carimbo deve constar no estado do caso
    estado = client.get(f"/v1/cases/{case_id}").json()
    assert estado.get("carimbo_gerado") is True or "carimbo" in estado
