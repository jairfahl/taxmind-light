"""
tests/unit/test_simulador_carga.py — Testes unitários do Simulador de Carga RT (G18).

Verifica cálculos de carga, formatação e projeção plurianual.
Nenhuma chamada externa — matemática pura.
"""

import pytest

from src.simuladores.carga_rt import (
    ANOS_SIMULADOS,
    CBS_ALIQUOTA_PLENA,
    IBS_ALIQUOTA_PLENA,
    CenarioOperacional,
    _aliquota_cbs,
    _aliquota_ibs,
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


def test_carga_nova_2033_plena(cenario_lucro_real_misto):
    """Em 2033 CBS+IBS plenos — CBS=8,8%, IBS=17,7%; regime = novo."""
    _, novo = simular_carga(cenario_lucro_real_misto, 2033)
    assert novo.carga_bruta > 0
    assert novo.regime == "novo"
    assert novo.detalhes["aliquota_cbs"] == pytest.approx(8.8)
    assert novo.detalhes["aliquota_ibs"] == pytest.approx(17.7)


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
# Novos testes — modelo de transição corrigido
# ---------------------------------------------------------------------------

def test_2024_2025_nova_igual_atual():
    """Em 2024 e 2025, regime novo deve espelhar o atual (CBS/IBS inexistentes)."""
    cenario = CenarioOperacional(
        faturamento_anual=10_000_000.0,
        regime_tributario="lucro_presumido",
        tipo_operacao="so_mercadorias",
        percentual_credito_novo=0.0,
    )
    for ano in (2024, 2025):
        atual, novo = simular_carga(cenario, ano)
        assert novo.carga_liquida == atual.carga_liquida, f"Falhou no ano {ano}"


def test_2026_nova_igual_atual():
    """Em 2026, CBS-teste é neutro por crédito PIS/COFINS — carga nova == atual."""
    cenario = CenarioOperacional(
        faturamento_anual=10_000_000.0,
        regime_tributario="lucro_presumido",
        tipo_operacao="so_mercadorias",
        percentual_credito_novo=0.0,
    )
    atual, novo = simular_carga(cenario, 2026)
    assert novo.carga_liquida == atual.carga_liquida


def test_2027_icms_fator_1_para_so_mercadorias():
    """Em 2027, so_mercadorias deve usar fator ICMS 1.0 (não 0.5)."""
    cenario = CenarioOperacional(
        faturamento_anual=10_000_000.0,
        regime_tributario="lucro_presumido",
        tipo_operacao="so_mercadorias",
        percentual_credito_novo=0.0,
    )
    _, novo = simular_carga(cenario, 2027)
    # ICMS_MEDIO=0.17, fator_tipo=1.0 (so_mercadorias), fator_icms=1.0 (2027)
    esperado_icms = round(10_000_000.0 * 0.17 * 1.0 * 1.0, 2)
    assert novo.detalhes["icms_residual"] == esperado_icms


def test_ibs_2029_nao_e_pleno():
    """Em 2029, IBS deve ser 11% (transição), não 17,7% (pleno)."""
    aliq_2029 = _aliquota_ibs(2029)
    assert aliq_2029 < IBS_ALIQUOTA_PLENA
    assert aliq_2029 == pytest.approx(0.110)


def test_cbs_uniforme_bens_servicos():
    """CBS deve ser uniforme (8,8%) para qualquer operação em 2033."""
    aliq_2033 = _aliquota_cbs(2033)
    assert aliq_2033 == pytest.approx(CBS_ALIQUOTA_PLENA)
    assert aliq_2033 == pytest.approx(0.088)


# ---------------------------------------------------------------------------
# formatar_brl
# ---------------------------------------------------------------------------

def test_formatar_brl_inteiro():
    assert formatar_brl(1234567.89) == "R$ 1.234.567,89"


def test_formatar_brl_zero():
    assert formatar_brl(0.0) == "R$ 0,00"
