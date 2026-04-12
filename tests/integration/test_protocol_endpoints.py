"""
tests/integration/test_protocol_endpoints.py — TC-PROT-01..TC-PROT-11

Testes de integração para os endpoints de protocolo P1→P6:
  POST /v1/cases           — criar caso
  GET  /v1/cases           — listar casos
  POST /v1/cases/{id}/steps/{passo} — avançar passo
  POST /v1/registrar_decisao        — fluxo PME completo

Requer banco PostgreSQL rodando em localhost:5436.
Não faz chamadas ao LLM — registrar_decisao usa texto pré-gerado.
"""
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Helper — cria um caso com título único para evitar filtros de listagem
# ---------------------------------------------------------------------------
def _criar_caso(titulo: str = "Caso integração protocolo P1 válido") -> int:
    resp = client.post(
        "/v1/cases",
        json={
            "titulo": titulo,
            "descricao": "Descrição para teste de integração",
            "contexto_fiscal": "Empresa tributada pelo Lucro Real",
        },
    )
    assert resp.status_code == 201, f"Falha ao criar caso: {resp.text}"
    return resp.json()["case_id"]


def _avancar_step1(case_id: int, titulo: str = "Caso integração protocolo P1 válido"):
    return client.post(
        f"/v1/cases/{case_id}/steps/1",
        json={
            "dados": {
                "titulo": titulo,
                "descricao": "Descrição para teste de integração",
                "contexto_fiscal": "Empresa tributada pelo Lucro Real",
                "premissas": [
                    "Empresa enquadrada no Lucro Real",
                    "Período fiscal 2025-2026",
                ],
                "periodo_fiscal": "2025-01 a 2026-12",
            },
            "acao": "avancar",
        },
    )


# ---------------------------------------------------------------------------
# TC-PROT-01 — POST /v1/cases com dados válidos → 201 + campos corretos
# ---------------------------------------------------------------------------
def test_criar_caso_valido():
    """TC-PROT-01: criar caso válido retorna 201, case_id int, status=rascunho, passo_atual=1."""
    resp = client.post(
        "/v1/cases",
        json={
            "titulo": "Caso protocolo integração válido TC01",
            "descricao": "Análise de impacto da Reforma Tributária",
            "contexto_fiscal": "Empresa de TI — Lucro Real 2026",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "case_id" in data
    assert isinstance(data["case_id"], int)
    assert data["case_id"] > 0
    assert data["status"] == "rascunho"
    assert data["passo_atual"] == 1


# ---------------------------------------------------------------------------
# TC-PROT-02 — POST /v1/cases com menos de 2 premissas no step 1 → validação
# ---------------------------------------------------------------------------
def test_avancar_step1_premissas_insuficientes():
    """TC-PROT-02: avançar step1 com apenas 1 premissa deve retornar 422."""
    case_id = _criar_caso("Caso integração premissa insuficiente P2")
    resp = client.post(
        f"/v1/cases/{case_id}/steps/1",
        json={
            "dados": {
                "titulo": "Caso integração premissa insuficiente P2",
                "descricao": "desc",
                "contexto_fiscal": "ctx fiscal",
                "premissas": ["Apenas uma premissa"],  # mín 2
                "periodo_fiscal": "2025",
            },
            "acao": "avancar",
        },
    )
    assert resp.status_code in (400, 422), (
        f"Esperado 400 ou 422, obtido {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# TC-PROT-03 — POST /v1/cases com titulo < 10 chars → 422
# ---------------------------------------------------------------------------
def test_criar_caso_titulo_curto():
    """TC-PROT-03: título com menos de 10 caracteres deve retornar 422."""
    resp = client.post(
        "/v1/cases",
        json={
            "titulo": "Curto",   # 5 chars — abaixo do mínimo de 10
            "descricao": "desc",
            "contexto_fiscal": "ctx",
        },
    )
    assert resp.status_code == 422, (
        f"Esperado 422, obtido {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# TC-PROT-04 — Avançar P1→P2 → passo_atual = 2
# ---------------------------------------------------------------------------
def test_avancar_p1_para_p2():
    """TC-PROT-04: submeter step 1 válido deve retornar passo=2, case_id correto."""
    case_id = _criar_caso("Caso integração avancar passo um para dois")
    resp = _avancar_step1(case_id, "Caso integração avancar passo um para dois")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # O engine retorna o novo passo corrente (2), não o passo que foi concluído
    assert data["passo"] == 2
    assert data["case_id"] == case_id
    # concluido refere-se ao novo passo corrente (ainda não submetido), pode ser False
    assert "concluido" in data
    assert "proximo_passo" in data


# ---------------------------------------------------------------------------
# TC-PROT-10 — GET /v1/cases → array de casos com campos obrigatórios
# ---------------------------------------------------------------------------
def test_listar_casos():
    """TC-PROT-10: GET /v1/cases retorna lista; cada item tem campos obrigatórios."""
    resp = client.get("/v1/cases")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    # Se houver casos (pode estar vazio em banco limpo), verificar estrutura
    if data:
        campos = {"case_id", "titulo", "status", "passo_atual", "created_at"}
        for item in data:
            for campo in campos:
                assert campo in item, f"Campo '{campo}' ausente no item: {item}"


# ---------------------------------------------------------------------------
# TC-PROT-11 — POST /v1/registrar_decisao → 200, sucesso=true
# ---------------------------------------------------------------------------
def test_registrar_decisao():
    """TC-PROT-11: fluxo PME completo retorna 200 e sucesso=true."""
    resp = client.post(
        "/v1/registrar_decisao",
        json={
            "query": "Qual o impacto do IBS sobre empresa de serviços no Lucro Real?",
            "premissas": [
                "Empresa tributada pelo Lucro Real",
                "Faturamento anual R$ 10MM",
                "100% serviços — sem exportação",
            ],
            "riscos": ["Alíquota IBS definitiva pendente de regulamentação"],
            "resultado_ia": (
                "A alíquota combinada CBS+IBS de 26,5% impacta significativamente "
                "empresas de serviços no Lucro Real, substituindo PIS/COFINS (9,25%) "
                "e ISS (3-5%). O creditamento pleno pode reduzir a carga efetiva."
            ),
            "grau_consolidacao": "consolidado",
            "contra_tese": "Possível redução por creditamento de insumos",
            "criticidade": "relevante",
            "hipotese_gestor": "Adotar regime de créditos ampliado desde 2026",
            "decisao_final": "Avaliar migração para regime de apuração mensal de IBS",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("sucesso") is True, f"sucesso != true: {data}"
    assert "case_id" in data
    assert isinstance(data["case_id"], int)
