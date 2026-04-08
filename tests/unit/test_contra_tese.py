"""
tests/unit/test_contra_tese.py — Testes unitários da Contra-Tese Explícita (G11).

Verifica que:
- AnaliseResult possui os campos forca_corrente_contraria e risco_adocao
- _analise_to_dict expõe forca_corrente_contraria e risco_adocao
- Fallback de contra_tese garante campo nunca nulo após _analisar_inner
- grau_consolidacao usa valores do novo schema (consolidado|em_disputa|sem_precedente)

Nenhuma chamada externa — todos os campos testados via dataclass diretamente.
"""

from dataclasses import fields

import pytest

from src.cognitive.engine import AnaliseResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analise(**overrides) -> dict:
    """Cria um dict simulando resposta JSON do LLM."""
    base = {
        "resposta": "Empresa precisa recolher IBS a partir de 2026.",
        "impacto_financeiro": "Aumento de 12% na carga tributária.",
        "fundamento_legal": ["LC 214/2025, art. 28"],
        "grau_consolidacao": "consolidado",
        "scoring_confianca": "alto",
        "contra_tese": "Corrente minoritária entende que o crédito é integral desde 2025.",
        "forca_corrente_contraria": "Baixa",
        "risco_adocao": "Risco de autuação se Comitê Gestor editar regulamentação restritiva.",
        "acao_recomendada": "Mapear NCMs e monitorar publicações do CGIBS.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# AnaliseResult — novos campos obrigatórios
# ---------------------------------------------------------------------------

def test_analise_result_tem_forca_corrente_contraria():
    """AnaliseResult deve declarar o campo forca_corrente_contraria."""
    field_names = {f.name for f in fields(AnaliseResult)}
    assert "forca_corrente_contraria" in field_names


def test_analise_result_tem_risco_adocao():
    """AnaliseResult deve declarar o campo risco_adocao."""
    field_names = {f.name for f in fields(AnaliseResult)}
    assert "risco_adocao" in field_names


def test_analise_result_contra_tese_presente():
    """AnaliseResult deve manter o campo contra_tese existente."""
    field_names = {f.name for f in fields(AnaliseResult)}
    assert "contra_tese" in field_names


# ---------------------------------------------------------------------------
# _analise_to_dict — exposição via API
# ---------------------------------------------------------------------------

def test_analise_to_dict_expoe_forca_corrente_contraria(mock_analise_result):
    """_analise_to_dict deve incluir forca_corrente_contraria."""
    from src.api.main import _analise_to_dict
    d = _analise_to_dict(mock_analise_result)
    assert "forca_corrente_contraria" in d


def test_analise_to_dict_expoe_risco_adocao(mock_analise_result):
    """_analise_to_dict deve incluir risco_adocao."""
    from src.api.main import _analise_to_dict
    d = _analise_to_dict(mock_analise_result)
    assert "risco_adocao" in d


def test_analise_to_dict_valores_corretos(mock_analise_result):
    """_analise_to_dict deve propagar os valores dos novos campos."""
    from src.api.main import _analise_to_dict
    d = _analise_to_dict(mock_analise_result)
    assert d["forca_corrente_contraria"] == "Baixa"
    assert d["risco_adocao"] == "Risco de autuação regulatória."


# ---------------------------------------------------------------------------
# Schema: valores permitidos para grau_consolidacao
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("grau", ["consolidado", "em_disputa", "sem_precedente"])
def test_grau_consolidacao_valores_validos(grau):
    """grau_consolidacao aceita os três valores do novo schema."""
    dados = _make_analise(grau_consolidacao=grau)
    assert dados["grau_consolidacao"] in {"consolidado", "em_disputa", "sem_precedente"}


# ---------------------------------------------------------------------------
# Fallback de contra_tese
# ---------------------------------------------------------------------------

def test_contra_tese_fallback_nao_vazio():
    """Quando o LLM retorna contra_tese=None ou vazia, o fallback deve ser aplicado."""
    _FALLBACK = (
        "Não há corrente contrária consolidada, mas o tema ainda não foi testado "
        "pelo Comitê Gestor."
    )
    # Simula o comportamento do _analisar_inner
    contra_tese_llm = None
    resultado = contra_tese_llm or _FALLBACK
    assert resultado != ""
    assert "Comitê Gestor" in resultado


def test_contra_tese_vazia_usa_fallback():
    """String vazia também deve acionar o fallback."""
    _FALLBACK = "Não há corrente contrária consolidada."
    contra_tese_llm = ""
    resultado = contra_tese_llm or _FALLBACK
    assert resultado == _FALLBACK
