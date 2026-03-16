"""
tests/unit/conftest.py — Fixtures autouse para testes unitários.

REGRA PERMANENTE: testes unitários NUNCA fazem chamadas externas (LLM, Voyage, banco real).
Todas as dependências externas são mockadas aqui globalmente via autouse=True.
Testes que precisam de API real ficam em tests/e2e/ e rodam manualmente.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

def _make_mock_anti_alucinacao():
    m = MagicMock()
    m.m1_existencia = True
    m.m2_validade = True
    m.m3_pertinencia = True
    m.m4_consistencia = True
    m.bloqueado = False
    m.flags = []
    return m


def _make_mock_qualidade():
    from src.quality.engine import QualidadeStatus
    m = MagicMock()
    m.status = QualidadeStatus.VERDE
    m.regras_ok = []
    m.bloqueios = []
    m.ressalvas = []
    m.disclaimer = ""
    return m


def _make_mock_analise_result():
    from src.cognitive.engine import AnaliseResult
    return AnaliseResult(
        query="Mock query tributária",
        qualidade=_make_mock_qualidade(),
        fundamento_legal=["Art. 9 LC 214/2025"],
        grau_consolidacao="consolidado",
        contra_tese=None,
        scoring_confianca="alto",
        resposta="Resposta fixture de análise tributária.",
        disclaimer="Disclaimer fixture",
        anti_alucinacao=_make_mock_anti_alucinacao(),
        chunks=[],
        prompt_version="v1.0.0-sprint2",
        model_id="claude-haiku-4-5-20251001",
        latencia_ms=100,
    )


# ---------------------------------------------------------------------------
# Autouse mocks globais
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_llm_calls():
    """Bloqueia toda chamada real ao LLM (cognitive engine)."""
    result = _make_mock_analise_result()
    with patch("src.cognitive.engine.analisar", return_value=result):
        yield result


@pytest.fixture(autouse=True)
def mock_spd_normas():
    """Bloqueia chamada ao banco em listar_normas_ativas."""
    with patch(
        "src.rag.spd.listar_normas_ativas",
        return_value=["EC132_2023", "LC214_2025", "LC227_2026"],
    ), patch(
        "src.cognitive.engine.listar_normas_ativas",
        return_value=["EC132_2023", "LC214_2025", "LC227_2026"],
    ):
        yield


@pytest.fixture(autouse=True)
def mock_embedding_calls():
    """Bloqueia chamadas ao Voyage AI (embeddings e retriever)."""
    with patch("src.rag.retriever._embed_query", return_value=[0.1] * 1024), \
         patch("src.protocol.carimbo._embed", return_value=[0.1] * 1024), \
         patch("src.ingest.embedder.gerar_e_persistir_embeddings", return_value=0):
        yield


@pytest.fixture(autouse=True)
def mock_materialidade():
    """Bloqueia chamada LLM na MaterialidadeCalculator."""
    with patch(
        "src.outputs.materialidade.MaterialidadeCalculator.calcular",
        return_value=3,
    ), patch(
        "src.outputs.materialidade.MaterialidadeCalculator.calcular_detalhado",
        return_value=MagicMock(score=3, justificativa="Mock justificativa"),
    ):
        yield


@pytest.fixture(autouse=True)
def mock_stakeholder_adaptar():
    """Bloqueia chamada LLM na StakeholderDecomposer."""
    with patch(
        "src.outputs.stakeholders.StakeholderDecomposer._adaptar_conteudo",
        return_value="Resumo mock adaptado para stakeholder.",
    ):
        yield


@pytest.fixture(autouse=True)
def mock_usage_tracking():
    """Bloqueia registro de uso de API (evita acesso ao banco)."""
    with patch("src.observability.usage.registrar_uso"):
        yield
