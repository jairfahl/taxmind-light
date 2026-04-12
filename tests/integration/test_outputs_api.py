"""
tests/integration/test_outputs_api.py — Testes de integração dos endpoints de outputs.
Requer banco rodando com tabelas Sprint 3 + Sprint 4.
Executa com: pytest tests/integration/test_outputs_api.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.outputs.engine import DISCLAIMER_PADRAO, OutputClass, OutputStatus

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helper: criar caso P1→P7 para testes que exigem P7 concluído
# ---------------------------------------------------------------------------
def _criar_caso_pronto(titulo="Caso outputs integração teste API") -> int:
    """Cria e avança caso até P1 concluído. Retorna case_id."""
    resp = client.post("/v1/cases", json={
        "titulo": titulo,
        "descricao": "Desc para testes de output",
        "contexto_fiscal": "Lucro Real",
    })
    assert resp.status_code == 201
    return resp.json()["case_id"]


# ---------------------------------------------------------------------------
# 1. POST /v1/outputs → C1 Alerta com disclaimer
# ---------------------------------------------------------------------------
def test_gerar_alerta_c1_com_disclaimer():
    case_id = _criar_caso_pronto("Caso alerta C1 com disclaimer teste")
    resp = client.post("/v1/outputs", json={
        "case_id": case_id,
        "classe": "alerta",
        "titulo": "Alerta prazo IBS Q1 2025",
        "contexto": "Prazo de recolhimento IBS vence em 30 dias",
        "materialidade": 4,
    })
    assert resp.status_code == 201, f"Esperado 201, obtido {resp.status_code}: {resp.text[:300]}"
    data = resp.json()
    assert data["classe"] == "alerta"
    assert "disclaimer" in data
    assert len(data["disclaimer"]) > 0
    assert data["materialidade"] == 4
    assert data["passo_origem"] == 2
    assert "id" in data and data["id"] > 0


# ---------------------------------------------------------------------------
# 2. POST /v1/outputs → C1 sem campos obrigatórios → 422
# ---------------------------------------------------------------------------
def test_gerar_alerta_sem_campos_obrigatorios():
    resp = client.post("/v1/outputs", json={
        "case_id": 1,
        "classe": "alerta",
        # Faltando titulo, contexto, materialidade
    })
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 3. POST /v1/outputs → C4 Dossiê sem P7 concluído → 400
# ---------------------------------------------------------------------------
def test_gerar_dossie_sem_p7():
    case_id = _criar_caso_pronto("Caso dossie sem P7 concluido teste")
    resp = client.post("/v1/outputs", json={
        "case_id": case_id,
        "classe": "dossie_decisao",
    })
    assert resp.status_code == 400
    # P7 não existe — o protocolo tem 6 passos (P1→P6). Dossiê requer P5 concluído.
    assert "P5" in resp.json().get("detail", "") or "P6" in resp.json().get("detail", "") or "Decidir" in resp.json().get("detail", "")


# ---------------------------------------------------------------------------
# 4. POST /v1/outputs/{id}/aprovar → status muda para aprovado
# ---------------------------------------------------------------------------
def test_aprovar_output_muda_status():
    case_id = _criar_caso_pronto("Caso aprovar output status teste")
    # Gerar C1 primeiro
    resp = client.post("/v1/outputs", json={
        "case_id": case_id,
        "classe": "alerta",
        "titulo": "Alerta para aprovação",
        "contexto": "Contexto de teste aprovação",
        "materialidade": 2,
    })
    assert resp.status_code == 201
    output_id = resp.json()["id"]

    # Aprovar
    resp_ap = client.post(f"/v1/outputs/{output_id}/aprovar", json={
        "aprovado_por": "Gestor Tributário",
        "observacao": "Aprovado em revisão",
    })
    assert resp_ap.status_code == 200
    data = resp_ap.json()
    assert data["status"] == "aprovado"
    assert data["id"] == output_id


# ---------------------------------------------------------------------------
# 5. GET /v1/cases/{case_id}/outputs → lista ordenada por materialidade DESC
# ---------------------------------------------------------------------------
def test_listar_outputs_ordenados_por_materialidade():
    case_id = _criar_caso_pronto("Caso listar outputs materialidade desc")

    # Gerar 2 alertas com materialidades diferentes
    client.post("/v1/outputs", json={
        "case_id": case_id, "classe": "alerta",
        "titulo": "Alerta baixa prioridade", "contexto": "ctx",
        "materialidade": 2,
    })
    client.post("/v1/outputs", json={
        "case_id": case_id, "classe": "alerta",
        "titulo": "Alerta alta prioridade", "contexto": "ctx",
        "materialidade": 5,
    })

    resp = client.get(f"/v1/cases/{case_id}/outputs")
    assert resp.status_code == 200
    outputs = resp.json()
    assert len(outputs) >= 2
    # Verificar ordenação DESC por materialidade
    mats = [o["materialidade"] for o in outputs if o["materialidade"] is not None]
    assert mats == sorted(mats, reverse=True), "Outputs devem estar ordenados por materialidade DESC"


# ---------------------------------------------------------------------------
# 6. GET /v1/outputs/{id} → output completo
# ---------------------------------------------------------------------------
def test_get_output_existente():
    case_id = _criar_caso_pronto("Caso get output existente teste")
    resp_create = client.post("/v1/outputs", json={
        "case_id": case_id, "classe": "alerta",
        "titulo": "Alerta GET teste", "contexto": "ctx",
        "materialidade": 3,
    })
    assert resp_create.status_code == 201
    output_id = resp_create.json()["id"]

    resp = client.get(f"/v1/outputs/{output_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == output_id
    assert data["disclaimer"] == DISCLAIMER_PADRAO


def test_get_output_inexistente():
    resp = client.get("/v1/outputs/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. C5 bloqueado sem C3/C4 aprovado
# ---------------------------------------------------------------------------
def test_c5_bloqueado_sem_aprovacao():
    case_id = _criar_caso_pronto("Caso C5 bloqueado sem aprovacao teste")
    # Gerar alerta (não é C3/C4)
    resp_c1 = client.post("/v1/outputs", json={
        "case_id": case_id, "classe": "alerta",
        "titulo": "Alerta base", "contexto": "ctx",
        "materialidade": 3,
    })
    output_id = resp_c1.json()["id"]

    resp = client.post("/v1/outputs", json={
        "case_id": case_id,
        "classe": "material_compartilhavel",
        "output_base_id": output_id,
        "stakeholders": ["externo"],
    })
    assert resp.status_code == 400  # alerta não é C3/C4


# ---------------------------------------------------------------------------
# 8. Aprovar output já aprovado → 400
# ---------------------------------------------------------------------------
def test_aprovar_output_ja_aprovado():
    case_id = _criar_caso_pronto("Caso output ja aprovado nao reaporvar")
    resp = client.post("/v1/outputs", json={
        "case_id": case_id, "classe": "alerta",
        "titulo": "Alerta dupla aprovação", "contexto": "ctx",
        "materialidade": 1,
    })
    output_id = resp.json()["id"]

    # Primeira aprovação
    client.post(f"/v1/outputs/{output_id}/aprovar",
                json={"aprovado_por": "Gestor A"})

    # Segunda aprovação deve falhar
    resp2 = client.post(f"/v1/outputs/{output_id}/aprovar",
                        json={"aprovado_por": "Gestor B"})
    assert resp2.status_code == 400
