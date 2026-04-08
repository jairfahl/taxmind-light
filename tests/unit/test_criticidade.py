"""
tests/unit/test_criticidade.py — Testes unitários da Calibração por Criticidade (D3, G17).
"""

from src.cognitive.criticidade import (
    CRITICIDADE_CONFIG,
    NivelCriticidade,
    TERMOS_ATENCAO,
    TERMOS_CRITICO,
    classificar_criticidade,
)


def test_tres_niveis_configurados():
    assert len(CRITICIDADE_CONFIG) == 3


def test_termos_criticos_nao_vazios():
    assert len(TERMOS_CRITICO) >= 5


def test_termos_atencao_nao_vazios():
    assert len(TERMOS_ATENCAO) >= 5


def test_autuacao_gera_critico():
    r = classificar_criticidade("Risco de autuação fiscal imediato.")
    assert r.nivel == NivelCriticidade.CRITICO


def test_multa_gera_critico():
    r = classificar_criticidade("A empresa está sujeita a multa de 75%.")
    assert r.nivel == NivelCriticidade.CRITICO


def test_adequacao_gera_atencao():
    r = classificar_criticidade(
        "É necessário adequar os sistemas de NF-e até maio de 2026."
    )
    assert r.nivel == NivelCriticidade.ATENCAO


def test_divergente_alta_gera_critico():
    r = classificar_criticidade(
        "Análise sobre CBS.",
        grau_consolidacao="Divergente",
        forca_contra_tese="Alta",
    )
    assert r.nivel == NivelCriticidade.CRITICO


def test_divergente_baixa_gera_atencao():
    r = classificar_criticidade(
        "Análise sobre CBS.",
        grau_consolidacao="Divergente",
        forca_contra_tese="Baixa",
    )
    assert r.nivel == NivelCriticidade.ATENCAO


def test_sem_risco_gera_informativo():
    r = classificar_criticidade(
        "A LC 214/2025 foi publicada em janeiro de 2025 e está vigente."
    )
    assert r.nivel == NivelCriticidade.INFORMATIVO


def test_impacto_alto_gera_critico():
    r = classificar_criticidade(
        "Análise de impacto tributário.",
        impacto_financeiro_estimado=60_000_000.0,
    )
    assert r.nivel == NivelCriticidade.CRITICO


def test_resultado_tem_justificativa():
    r = classificar_criticidade("Risco de autuação.")
    assert r.justificativa != ""
    assert r.impacto_estimado != ""


def test_impacto_medio_gera_atencao():
    r = classificar_criticidade(
        "Análise sobre impacto tributário.",
        impacto_financeiro_estimado=20_000_000.0,
    )
    assert r.nivel == NivelCriticidade.ATENCAO
