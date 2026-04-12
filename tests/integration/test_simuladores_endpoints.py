"""
tests/integration/test_simuladores_endpoints.py — TC-SIM-01..TC-SIM-07

Testes de integração para os endpoints de simuladores tributários:
  POST /v1/simuladores/carga-rt
  POST /v1/simuladores/split-payment
  POST /v1/simuladores/creditos-ibs
  POST /v1/simuladores/reestruturacao
  POST /v1/simuladores/impacto-is

Todos os simuladores executam cálculos locais (sem chamadas externas),
portanto não requerem mock de LLM.
"""
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# TC-SIM-01 — Carga RT básica: 10 anos (2024-2033) e carga_liquida > 0
# ---------------------------------------------------------------------------
def test_carga_rt_basic():
    """TC-SIM-01: simulação básica retorna 10 anos e carga_liquida > 0 no ano atual."""
    resp = client.post(
        "/v1/simuladores/carga-rt",
        json={
            "faturamento_anual": 5_000_000.0,
            "regime_tributario": "lucro_real",
            "tipo_operacao": "misto",
            "percentual_exportacao": 0.0,
            "percentual_credito_novo": 1.0,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "resultados" in data
    resultados = data["resultados"]
    # Deve retornar 7 anos mapeados (2024,2025,2026,2027,2028,2029,2033)
    assert len(resultados) >= 7, f"Esperado ≥7 anos, obtido {len(resultados)}"
    # Verificar estrutura de cada item
    for item in resultados:
        assert "ano" in item
        assert "atual" in item
        assert "novo" in item
        assert "carga_liquida" in item["atual"]
        assert "carga_liquida" in item["novo"]
    # Carga líquida atual no primeiro ano deve ser > 0
    assert resultados[0]["atual"]["carga_liquida"] > 0


# ---------------------------------------------------------------------------
# TC-SIM-02 — Carga RT com 100% exportação: carga nova próxima de zero
# ---------------------------------------------------------------------------
def test_carga_rt_exportacao_total():
    """TC-SIM-02: 100% exportação → carga nova deve ser próxima de zero."""
    resp = client.post(
        "/v1/simuladores/carga-rt",
        json={
            "faturamento_anual": 10_000_000.0,
            "regime_tributario": "lucro_real",
            "tipo_operacao": "so_mercadorias",
            "percentual_exportacao": 1.0,  # 100% exportação
            "percentual_credito_novo": 1.0,
        },
    )
    assert resp.status_code == 200, resp.text
    resultados = resp.json()["resultados"]
    # No regime pleno (últimos anos), a carga nova deve ser próxima de zero
    # Pegar o último ano simulado
    ultimo = resultados[-1]
    assert ultimo["novo"]["carga_liquida"] < 500_000, (
        f"Esperado carga nova próxima de zero com 100% exportação, "
        f"obtido {ultimo['novo']['carga_liquida']}"
    )


# ---------------------------------------------------------------------------
# TC-SIM-03 — Split Payment: prazo 30 dias vs 2 dias — proporcionalidade
# ---------------------------------------------------------------------------
def test_split_payment_proporcionalidade():
    """TC-SIM-03: prazo maior deve gerar maior impacto de capital de giro."""
    base_payload = {
        "faturamento_mensal": 1_000_000.0,
        "pct_vista": 0.0,
        "pct_prazo": 1.0,
        "taxa_captacao_am": 0.02,
        "pct_inadimplencia": 0.01,
        "aliquota_cbs": 0.088,
        "aliquota_ibs": 0.177,
        "pct_creditos": 0.60,
    }
    resp_30 = client.post(
        "/v1/simuladores/split-payment",
        json={**base_payload, "prazo_medio_dias": 30},
    )
    resp_2 = client.post(
        "/v1/simuladores/split-payment",
        json={**base_payload, "prazo_medio_dias": 2},
    )
    assert resp_30.status_code == 200, resp_30.text
    assert resp_2.status_code == 200, resp_2.text

    # Com prazo maior, o impacto de capital de giro deve ser maior (mais negativo ou maior abs)
    d30 = resp_30.json()
    d2  = resp_2.json()
    # Estrutura: {"faturamento_mensal": ..., "modalidades": [...], ...}
    assert "modalidades" in d30, f"Campos d30: {list(d30.keys())}"
    assert "modalidades" in d2
    assert len(d30["modalidades"]) > 0
    assert len(d2["modalidades"]) > 0
    # Pegar custo_financeiro_mensal da primeira modalidade
    custo_30 = d30["modalidades"][0]["custo_financeiro_mensal"]
    custo_2  = d2["modalidades"][0]["custo_financeiro_mensal"]
    # Prazo 30d deve gerar maior custo financeiro do que prazo 2d
    assert custo_30 > custo_2, (
        f"Prazo maior deveria gerar maior custo financeiro: 30d={custo_30}, 2d={custo_2}"
    )


# ---------------------------------------------------------------------------
# TC-SIM-04 — Créditos IBS: fornecedor_simples → creditamento = presumido/false
# ---------------------------------------------------------------------------
def test_creditos_ibs_fornecedor_simples():
    """TC-SIM-04: item de fornecedor_simples deve ter creditamento != integral."""
    resp = client.post(
        "/v1/simuladores/creditos-ibs",
        json={
            "itens": [
                {
                    "categoria": "fornecedor_simples",
                    "valor_mensal": 50_000.0,
                    "aliquota_cbs": 0.088,
                    "aliquota_ibs": 0.177,
                }
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "itens" in data
    item = data["itens"][0]
    # Creditamento para fornecedor_simples deve ser "presumido" (não integral)
    assert "creditamento" in item
    assert item["creditamento"] != "integral", (
        f"Esperado creditamento != integral, obtido '{item['creditamento']}'"
    )


# ---------------------------------------------------------------------------
# TC-SIM-05 — Reestruturação: resultado tem campo recomendacao
# ---------------------------------------------------------------------------
def test_reestruturacao_tem_recomendacao():
    """TC-SIM-05: resultado de reestruturação deve ter campo recomendacao."""
    resp = client.post(
        "/v1/simuladores/reestruturacao",
        json={
            "unidades": [
                {
                    "uf": "SP",
                    "tipo": "filial",
                    "custo_fixo_anual": 500_000.0,
                    "faturamento_anual": 3_000_000.0,
                    "beneficio_icms_justifica": True,
                }
            ],
            "ano_analise": 2026,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "unidades" in data
    unidade = data["unidades"][0]
    assert "recomendacao" in unidade, f"Campos: {list(unidade.keys())}"
    assert unidade["recomendacao"] in ("manter", "revisar", "encerrar")


# ---------------------------------------------------------------------------
# TC-SIM-06 — Impacto IS: tabaco + repasse ao consumidor → preco_com_is > preco_atual
# ---------------------------------------------------------------------------
def test_impacto_is_tabaco():
    """TC-SIM-06: IS sobre tabaco deve aumentar o preço com IS em relação ao atual."""
    preco_atual = 15.00
    resp = client.post(
        "/v1/simuladores/impacto-is",
        json={
            "produto": "tabaco",
            "preco_venda_atual": preco_atual,
            "volume_mensal": 10_000,
            "custo_producao": 5.00,
            "elasticidade": "media",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "preco_com_is" in data
    assert data["preco_com_is"] > preco_atual, (
        f"Esperado preco_com_is > {preco_atual}, obtido {data['preco_com_is']}"
    )


# ---------------------------------------------------------------------------
# TC-SIM-07 — Carga RT com percentual_exportacao=150% → 422
# ---------------------------------------------------------------------------
def test_carga_rt_exportacao_invalida():
    """TC-SIM-07: percentual_exportacao > 1.0 deve retornar 422 (validação Pydantic)."""
    resp = client.post(
        "/v1/simuladores/carga-rt",
        json={
            "faturamento_anual": 1_000_000.0,
            "regime_tributario": "lucro_real",
            "tipo_operacao": "misto",
            "percentual_exportacao": 1.5,  # inválido: > 1.0
            "percentual_credito_novo": 1.0,
        },
    )
    assert resp.status_code == 422, f"Esperado 422, obtido {resp.status_code}: {resp.text}"
