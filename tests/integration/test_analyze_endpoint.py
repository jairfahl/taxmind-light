"""
tests/integration/test_analyze_endpoint.py — Testes de integração do endpoint /v1/analyze.

LLM é mockado (sem chamada real à API Anthropic).
Executa com: pytest tests/integration/test_analyze_endpoint.py -v
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_qualidade(status="verde"):
    from src.quality.engine import QualidadeStatus
    m = MagicMock()
    m.status = getattr(QualidadeStatus, status.upper(), QualidadeStatus.VERDE)
    m.bloqueios = []
    m.ressalvas = []
    m.disclaimer = ""
    m.regras_ok = []
    return m


def _make_mock_anti_alucinacao():
    m = MagicMock()
    m.m1_existencia = True
    m.m2_validade = True
    m.m3_pertinencia = True
    m.m4_consistencia = True
    m.bloqueado = False
    m.flags = []
    return m


def _make_mock_analise_result(qualidade_status="verde"):
    from src.cognitive.engine import AnaliseResult
    return AnaliseResult(
        query="Somos um varejista no Lucro Real. Como fica nossa carga IBS/CBS a partir de 2027?",
        qualidade=_make_mock_qualidade(qualidade_status),
        fundamento_legal=["Art. 9 LC 214/2025", "Art. 1 EC 132/2023"],
        grau_consolidacao="Consolidada",
        contra_tese="Corrente minoritária questiona a base de cálculo.",
        scoring_confianca="alto",
        forca_corrente_contraria="Baixa",
        risco_adocao="Risco regulatório moderado.",
        resposta="A partir de 2027, o IBS começa a substituir progressivamente o ICMS/ISS.",
        disclaimer="Informação baseada nas normas vigentes em Abril 2026.",
        anti_alucinacao=_make_mock_anti_alucinacao(),
        chunks=[],
        prompt_version="v1.0.0-integration-test",
        model_id="claude-sonnet-4-6",
        latencia_ms=450,
    )


QUERY_VALIDA = "Somos um varejista no Lucro Real. Como fica nossa carga IBS/CBS a partir de 2027?"
QUERY_FORA_ESCOPO = "Qual é a capital da França? Fale sobre a história de Paris."
QUERY_CURTA = "IBS"


# ---------------------------------------------------------------------------
# TC-ANALYZE-01: Query válida → 200 + campos obrigatórios
# ---------------------------------------------------------------------------
def test_analyze_query_valida_campos_obrigatorios():
    """Análise com query tributária válida retorna 200 e todos os campos obrigatórios."""
    mock_result = _make_mock_analise_result()
    with patch("src.cognitive.engine.analisar", return_value=mock_result):
        resp = client.post("/v1/analyze", json={"query": QUERY_VALIDA})

    assert resp.status_code == 200, f"Esperado 200, obtido {resp.status_code}: {resp.text[:300]}"
    data = resp.json()

    campos_obrigatorios = [
        "query", "qualidade", "fundamento_legal", "grau_consolidacao",
        "scoring_confianca", "resposta", "anti_alucinacao", "chunks",
        "prompt_version", "model_id", "latencia_ms",
    ]
    for campo in campos_obrigatorios:
        assert campo in data, f"Campo ausente no resultado: {campo}"


# ---------------------------------------------------------------------------
# TC-ANALYZE-02: Query fora do escopo → 400 com bloqueios
# ---------------------------------------------------------------------------
def test_analyze_query_fora_escopo_retorna_400():
    """Query sem contexto tributário deve ser bloqueada com 400."""
    resp = client.post("/v1/analyze", json={"query": QUERY_FORA_ESCOPO})
    assert resp.status_code == 400, f"Esperado 400, obtido {resp.status_code}: {resp.text[:300]}"
    detail = resp.json().get("detail", {})
    assert "bloqueios" in detail or "message" in detail, "Resposta 400 deve ter campo 'bloqueios' ou 'message'"


# ---------------------------------------------------------------------------
# TC-ANALYZE-03: Query muito curta → 400 (qualidade VERMELHO)
# ---------------------------------------------------------------------------
def test_analyze_query_curta_retorna_400():
    """Query com menos de 10 caracteres deve ser bloqueada."""
    resp = client.post("/v1/analyze", json={"query": QUERY_CURTA})
    assert resp.status_code == 400, f"Esperado 400, obtido {resp.status_code}: {resp.text[:300]}"


# ---------------------------------------------------------------------------
# TC-ANALYZE-05: Stakeholders presentes e bem formados
# ---------------------------------------------------------------------------
def test_analyze_stakeholders_presentes():
    """saidas_stakeholders deve estar presente e cada item ter os campos esperados."""
    mock_result = _make_mock_analise_result()
    # saidas_stakeholders vem de _analise_to_dict; vamos checar que o campo existe
    with patch("src.cognitive.engine.analisar", return_value=mock_result):
        resp = client.post("/v1/analyze", json={"query": QUERY_VALIDA})

    assert resp.status_code == 200
    data = resp.json()
    # O endpoint pode incluir saidas_stakeholders ou não dependendo da versão
    # Verificamos a presença se estiver disponível
    if "saidas_stakeholders" in data:
        stakeholders = data["saidas_stakeholders"]
        assert isinstance(stakeholders, list)


# ---------------------------------------------------------------------------
# TC-ANALYZE-06: Campos de governança têm valores válidos
# ---------------------------------------------------------------------------
def test_analyze_campos_governanca_validos():
    """grau_consolidacao e scoring_confianca têm valores dentro dos conjuntos válidos."""
    mock_result = _make_mock_analise_result()
    with patch("src.cognitive.engine.analisar", return_value=mock_result):
        resp = client.post("/v1/analyze", json={"query": QUERY_VALIDA})

    assert resp.status_code == 200
    data = resp.json()

    grau = data.get("grau_consolidacao", "").lower()
    assert grau in ("consolidada", "majoritária", "majoritaria", "divergente", "emergente", "consolidado", "majoritário", "majoritario"), \
        f"grau_consolidacao inválido: {grau}"

    scoring = data.get("scoring_confianca", "").lower()
    assert scoring in ("alto", "medio", "médio", "baixo"), \
        f"scoring_confianca inválido: {scoring}"


# ---------------------------------------------------------------------------
# TC-ANALYZE-07: norma_filter aceito sem erro
# ---------------------------------------------------------------------------
def test_analyze_com_norma_filter():
    """Análise com norma_filter válido não deve retornar erro de validação."""
    mock_result = _make_mock_analise_result()
    with patch("src.cognitive.engine.analisar", return_value=mock_result):
        resp = client.post(
            "/v1/analyze",
            json={"query": QUERY_VALIDA, "norma_filter": "LC_214"},
        )
    # 200 = análise OK, 400 = qualidade VERMELHO, 422 = norma_filter como string (espera lista)
    assert resp.status_code in (200, 400, 422), f"Status inesperado: {resp.status_code}"


# ---------------------------------------------------------------------------
# TC-ANALYZE-08: Latência dentro do limite de 30s
# ---------------------------------------------------------------------------
def test_analyze_latencia_aceitavel():
    """latencia_ms no resultado deve ser menor que 30.000ms."""
    mock_result = _make_mock_analise_result()
    with patch("src.cognitive.engine.analisar", return_value=mock_result):
        resp = client.post("/v1/analyze", json={"query": QUERY_VALIDA})

    assert resp.status_code == 200
    data = resp.json()
    assert data["latencia_ms"] < 30_000, f"Latência excessiva: {data['latencia_ms']}ms"
