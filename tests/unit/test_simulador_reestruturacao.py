"""
tests/unit/test_simulador_reestruturacao.py — Testes unitários do MP-03 Reestruturação RT.

Verifica fases de incentivos ICMS, recomendações e conformidade com LC 214/2025.
Nenhuma chamada externa — matemática pura.
"""

import pytest

from src.simuladores.reestruturacao_rt import (
    PHASEOUT_ICMS,
    UnidadeOperacional,
    ResultadoReestruturacao,
    analisar_reestruturacao,
)


# ---------------------------------------------------------------------------
# RE-1 fix: PHASEOUT_ICMS — redução só começa em 2029
# ---------------------------------------------------------------------------

def test_phaseout_icms_pleno_2027():
    """Incentivos ICMS devem ser 100% em 2027 (IBS ainda em fase-teste)."""
    assert PHASEOUT_ICMS[2027] == 1.00, (
        "PHASEOUT_ICMS[2027] deve ser 1.0 — incentivos ICMS plenos até 2028 "
        "(fundo de compensação inicia em 2029 per LC 214/2025)"
    )


def test_phaseout_icms_pleno_2028():
    """Incentivos ICMS devem ser 100% em 2028."""
    assert PHASEOUT_ICMS[2028] == 1.00


def test_phaseout_icms_inicia_reducao_2029():
    """Fase-out começa em 2029, não antes."""
    assert PHASEOUT_ICMS[2029] < 1.00
    assert PHASEOUT_ICMS[2029] == pytest.approx(0.80)


def test_phaseout_icms_extinto_2033():
    assert PHASEOUT_ICMS[2033] == 0.00


def test_phaseout_icms_monotonicamente_decrescente():
    """Após 2029 os valores devem ser estritamente decrescentes até 2033."""
    anos = [2029, 2030, 2031, 2032, 2033]
    valores = [PHASEOUT_ICMS[a] for a in anos]
    for i in range(len(valores) - 1):
        assert valores[i] > valores[i + 1], f"PHASEOUT_ICMS não decresce de {anos[i]} para {anos[i+1]}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def unidade_am_alta():
    """Unidade no AM (ZFM 18%) com alto incentivo — deve receber recomendação revisar/encerrar."""
    return UnidadeOperacional(
        uf="AM",
        tipo="CD",
        custo_fixo_anual=1_000_000.0,
        faturamento_anual=10_000_000.0,
        beneficio_icms_justifica=True,
    )


@pytest.fixture
def unidade_sp_baixo():
    """Unidade em SP (5%) sem dependência fiscal — deve manter."""
    return UnidadeOperacional(
        uf="SP",
        tipo="escritorio",
        custo_fixo_anual=5_000_000.0,
        faturamento_anual=2_000_000.0,
        beneficio_icms_justifica=False,
    )


# ---------------------------------------------------------------------------
# analisar_reestruturacao — comportamento básico
# ---------------------------------------------------------------------------

def test_retorna_resultado_correto(unidade_am_alta):
    r = analisar_reestruturacao([unidade_am_alta])
    assert isinstance(r, ResultadoReestruturacao)
    assert len(r.unidades) == 1


def test_unidade_sem_dependencia_fiscal_mantem(unidade_sp_baixo):
    r = analisar_reestruturacao([unidade_sp_baixo])
    assert r.unidades[0].recomendacao == "manter"


def test_alto_incentivo_am_gera_alerta(unidade_am_alta):
    r = analisar_reestruturacao([unidade_am_alta])
    assert r.unidades[0].recomendacao in ("revisar", "encerrar")


def test_economia_total_positiva(unidade_am_alta):
    r = analisar_reestruturacao([unidade_am_alta])
    assert r.economia_total_perdida_anual > 0


def test_ano_decisao_critica_nao_antes_2029(unidade_am_alta):
    """Com PHASEOUT correto, ano crítico (≤20%) deve ser 2032, não 2030."""
    r = analisar_reestruturacao([unidade_am_alta])
    # PHASEOUT[2032] = 0.20 → primeiro ano ≤ 20% é 2032
    assert r.unidades[0].ano_decisao_critica >= 2032, (
        "ano_decisao_critica não deve ser anterior a 2032 — "
        "fator ICMS só chega a 20% em 2032 com o schedule correto da LC 214/2025"
    )


def test_multiplas_unidades(unidade_am_alta, unidade_sp_baixo):
    r = analisar_reestruturacao([unidade_am_alta, unidade_sp_baixo])
    assert len(r.unidades) == 2
    assert r.economia_total_perdida_anual > 0


def test_ressalvas_presentes(unidade_am_alta):
    r = analisar_reestruturacao([unidade_am_alta])
    assert len(r.ressalvas) > 0
