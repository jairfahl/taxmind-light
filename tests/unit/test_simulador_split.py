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


# ---------------------------------------------------------------------------
# SP-1 fix: DIAS_AJUSTE["simplificado"] deve ser 3 (art. 33 LC 214/2025)
# ---------------------------------------------------------------------------

def test_dias_ajuste_simplificado_tres_dias():
    """Art. 33 LC 214/2025: excesso retido devolvido em até 3 dias úteis (não 30)."""
    assert DIAS_AJUSTE["simplificado"] == 3, (
        f"DIAS_AJUSTE['simplificado'] deve ser 3 (dias úteis, art. 33 LC 214/2025), "
        f"não {DIAS_AJUSTE['simplificado']} — isso causava overstatement 10x do custo financeiro"
    )


def test_dias_ajuste_contingencia_tres_dias():
    """Art. 32 §4º LC 214/2025: contingência também devolve em 3 dias úteis."""
    assert DIAS_AJUSTE["contingencia"] == 3


def test_custo_simplificado_compativel_com_contingencia():
    """Com dias_ajuste igual, simplificado deve ter custo próximo ao contingência
    (a diferença vem só do percentual de retenção e da forma de crédito)."""
    r = simular_split_payment(CENARIO)
    simplificado = next(m for m in r.modalidades if m.modalidade == "simplificado")
    contingencia = next(m for m in r.modalidades if m.modalidade == "contingencia")
    # custo financeiro do simplificado não deve ser 10x maior que o da contingência
    if contingencia.custo_financeiro_mensal > 0:
        ratio = simplificado.custo_financeiro_mensal / contingencia.custo_financeiro_mensal
        assert ratio < 5, (
            f"Custo simplificado/contingencia ratio={ratio:.1f} — "
            "com dias_ajuste correto (3 dias para ambos) a diferença deve ser menor"
        )
