"""
tests/unit/test_simulador_split.py — Testes unitários do MP-05 Split Payment (G22).

Verifica cálculo das 3 modalidades, créditos, ressalvas e recomendação.
Nenhuma chamada externa — matemática pura.
"""

from src.simuladores.split_payment import (
    DIAS_AJUSTE,
    PERCENTUAL_RETENCAO,
    CenarioSplitPayment,
    simular_split_payment,
)

CENARIO = CenarioSplitPayment(
    faturamento_mensal=5_000_000.0,
    pct_vista=0.4,
    pct_prazo=0.6,
    prazo_medio_dias=30,
    taxa_captacao_am=0.02,
)


def test_tres_modalidades_retornadas():
    r = simular_split_payment(CENARIO)
    assert len(r.modalidades) == 3
    modalidades = [m.modalidade for m in r.modalidades]
    assert "inteligente" in modalidades
    assert "simplificado" in modalidades
    assert "contingencia" in modalidades


def test_contingencia_maior_custo():
    r = simular_split_payment(CENARIO)
    inteligente = next(m for m in r.modalidades if m.modalidade == "inteligente")
    contingencia = next(m for m in r.modalidades if m.modalidade == "contingencia")
    assert contingencia.custo_financeiro_mensal >= inteligente.custo_financeiro_mensal


def test_inteligente_tem_creditos_compensados():
    r = simular_split_payment(CENARIO)
    inteligente = next(m for m in r.modalidades if m.modalidade == "inteligente")
    assert inteligente.creditos_compensados > 0


def test_simplificado_sem_creditos_compensados():
    r = simular_split_payment(CENARIO)
    simplificado = next(m for m in r.modalidades if m.modalidade == "simplificado")
    assert simplificado.creditos_compensados == 0


def test_percentual_retencao_contingencia_integral():
    assert PERCENTUAL_RETENCAO["contingencia"] == 1.00


def test_dias_ajuste_inteligente_zero():
    assert DIAS_AJUSTE["inteligente"] == 0


def test_recomendacao_presente():
    r = simular_split_payment(CENARIO)
    assert r.recomendacao != ""


def test_ressalvas_presentes():
    r = simular_split_payment(CENARIO)
    for m in r.modalidades:
        assert len(m.ressalvas) > 0
