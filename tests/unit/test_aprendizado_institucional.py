"""
tests/unit/test_aprendizado_institucional.py — Testes unitários do Motor de Aprendizado (C6, G24).

Apenas lógica pura — sem chamadas ao banco.
"""

from src.cognitive.aprendizado_institucional import (
    PRAZO_VALIDADE_HEURISTICA_DIAS,
    _calcular_metricas_caso,
    _extrair_tags_premissas,
)


def test_prazo_validade_seis_meses():
    assert PRAZO_VALIDADE_HEURISTICA_DIAS == 180


def test_extrair_tags_premissas_cbs():
    tags = _extrair_tags_premissas(["Assumo alíquota CBS de 0,9%"])
    assert "cbs" in tags


def test_extrair_tags_premissas_split():
    tags = _extrair_tags_premissas(["Assumo split payment opcional em 2026"])
    assert "split_payment" in tags


def test_extrair_tags_multiplos():
    tags = _extrair_tags_premissas([
        "Assumo CBS de 8,8%",
        "Assumo crédito de IBS integral",
    ])
    assert "cbs" in tags
    assert "ibs" in tags
    assert "creditamento" in tags


def test_calcular_metricas_sem_divergencia():
    dossie = {
        "p2_estruturacao": {"premissas": ["p1", "p2", "p3"], "riscos_fiscais": ["r1"]},
        "p5_decisao": {"carimbo_similaridade": 0.85},
    }
    m = _calcular_metricas_caso(dossie)
    assert m["houve_divergencia"] is False
    assert m["n_premissas"] == 3
    assert m["n_riscos"] == 1


def test_calcular_metricas_com_divergencia():
    dossie = {
        "p2_estruturacao": {"premissas": ["p1"], "riscos_fiscais": []},
        "p5_decisao": {"carimbo_similaridade": 0.40},
    }
    m = _calcular_metricas_caso(dossie)
    assert m["houve_divergencia"] is True
    assert m["similaridade_ia"] == 0.40


def test_calcular_metricas_sem_carimbo():
    dossie = {
        "p2_estruturacao": {"premissas": [], "riscos_fiscais": []},
        "p5_decisao": {},
    }
    m = _calcular_metricas_caso(dossie)
    assert m["houve_divergencia"] is False
    assert m["similaridade_ia"] is None


def test_calcular_metricas_dossie_vazio():
    m = _calcular_metricas_caso({})
    assert m["n_premissas"] == 0
    assert m["n_riscos"] == 0
    assert m["houve_divergencia"] is False


def test_extrair_tags_query_sem_termos():
    tags = _extrair_tags_premissas(["Qual é o prazo para entrega da declaração?"])
    # "declaração" não está nos termos mapeados
    assert isinstance(tags, list)
