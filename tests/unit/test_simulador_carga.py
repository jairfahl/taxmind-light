"""
tests/unit/test_simulador_carga.py — Testes unitários do Simulador de Carga RT (G18).

Verifica cálculos de carga, formatação e projeção plurianual.
Nenhuma chamada externa — matemática pura.
"""

import pytest

from src.simuladores.carga_rt import (
    ANOS_SIMULADOS,
    CenarioOperacional,
    formatar_brl,
    simular_carga,
    simular_multiplos_anos,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cenario_lucro_real_misto():
    return CenarioOperacional(
        faturamento_anual=5_000_000.0,
        regime_tributario="lucro_real",
        tipo_operacao="misto",
    )


@pytest.fixture
def cenario_presumido_servicos():
    return CenarioOperacional(
        faturamento_anual=1_000_000.0,
        regime_tributario="lucro_presumido",
        tipo_operacao="so_servicos",
    )


# ---------------------------------------------------------------------------
# CenarioOperacional — validação
# ---------------------------------------------------------------------------

def test_cenario_regime_invalido():
    with pytest.raises(ValueError, match="regime_tributario"):
        CenarioOperacional(
            faturamento_anual=1_000_000.0,
            regime_tributario="regime_inexistente",
            tipo_operacao="misto",
        )


def test_cenario_tipo_invalido():
    with pytest.raises(ValueError, match="tipo_operacao"):
        CenarioOperacional(
            faturamento_anual=1_000_000.0,
            regime_tributario="lucro_real",
            tipo_operacao="invalido",
        )


def test_cenario_exportacao_invalida():
    with pytest.raises(ValueError, match="percentual_exportacao"):
        CenarioOperacional(
            faturamento_anual=1_000_000.0,
            regime_tributario="lucro_real",
            tipo_operacao="misto",
            percentual_exportacao=1.5,
        )


# ---------------------------------------------------------------------------
# simular_carga — comportamento por ano
# ---------------------------------------------------------------------------

def test_carga_atual_positiva(cenario_lucro_real_misto):
    atual, _ = simular_carga(cenario_lucro_real_misto, 2024)
    assert atual.carga_liquida > 0
    assert atual.regime == "atual"


def test_carga_nova_2026_menor_que_atual(cenario_lucro_real_misto):
    """Em 2026 (ano-teste CBS 0,9% + IBS 0,1%), carga nova deve ser bem menor."""
    atual, novo = simular_carga(cenario_lucro_real_misto, 2026)
    assert novo.carga_liquida < atual.carga_liquida


def test_carga_nova_2033_plena(cenario_lucro_real_misto):
    """Em 2033 CBS+IBS plenos — carga bruta deve ser > 0; regime = novo."""
    _, novo = simular_carga(cenario_lucro_real_misto, 2033)
    assert novo.carga_bruta > 0
    assert novo.regime == "novo"


def test_aliquota_efetiva_entre_0_e_1(cenario_lucro_real_misto):
    atual, novo = simular_carga(cenario_lucro_real_misto, 2033)
    assert 0 < atual.aliquota_efetiva < 1
    assert 0 <= novo.aliquota_efetiva < 1


def test_exportacao_total_reduz_base():
    """100% exportação → base zero → carga nova zero."""
    cenario = CenarioOperacional(
        faturamento_anual=1_000_000.0,
        regime_tributario="lucro_real",
        tipo_operacao="misto",
        percentual_exportacao=1.0,
    )
    _, novo = simular_carga(cenario, 2033)
    assert novo.carga_liquida == 0.0


# ---------------------------------------------------------------------------
# simular_multiplos_anos
# ---------------------------------------------------------------------------

def test_projecao_retorna_anos_corretos(cenario_lucro_real_misto):
    proj = simular_multiplos_anos(cenario_lucro_real_misto)
    anos = [p["ano"] for p in proj]
    assert anos == ANOS_SIMULADOS


def test_projecao_variacao_pct_presente(cenario_lucro_real_misto):
    proj = simular_multiplos_anos(cenario_lucro_real_misto)
    for p in proj:
        assert "variacao_pct" in p
        assert isinstance(p["variacao_pct"], float)


# ---------------------------------------------------------------------------
# formatar_brl
# ---------------------------------------------------------------------------

def test_formatar_brl_inteiro():
    assert formatar_brl(1234567.89) == "R$ 1.234.567,89"


def test_formatar_brl_zero():
    assert formatar_brl(0.0) == "R$ 0,00"
