"""
src/simuladores/split_payment.py — MP-05 Simulador de Impacto do Split Payment no Caixa.
DC v7, Seção: Métodos Proprietários — Capítulo RT.

Compara as 3 modalidades de split payment:
- Inteligente (art. 32 LC 214/2025)
- Simplificado (art. 33 LC 214/2025)
- Contingência (art. 32, §4º LC 214/2025)
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ALIQUOTA_CBS_REFERENCIA = 0.088
ALIQUOTA_IBS_REFERENCIA = 0.177
ALIQUOTA_TOTAL_REFERENCIA = ALIQUOTA_CBS_REFERENCIA + ALIQUOTA_IBS_REFERENCIA

# Dias de ajuste por modalidade (prazo para devolução de excesso retido)
DIAS_AJUSTE = {
    "inteligente":  0,   # compensação em tempo real — sem antecipação residual
    "simplificado": 30,  # ajuste no final do período de apuração
    "contingencia": 3,   # devolução em até 3 dias úteis (art. 32, §4º)
}

# Percentual de retenção por modalidade
PERCENTUAL_RETENCAO = {
    "inteligente":  0.40,  # estimativa: 40% do tributo bruto após compensação
    "simplificado": 0.80,  # estimativa: 80% do tributo bruto
    "contingencia": 1.00,  # 100% — retenção integral
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CenarioSplitPayment:
    faturamento_mensal: float          # R$ faturamento bruto mensal
    pct_vista: float                   # % vendas à vista (0.0 a 1.0)
    pct_prazo: float                   # % vendas a prazo (0.0 a 1.0)
    prazo_medio_dias: int              # prazo médio de recebimento em dias
    taxa_captacao_am: float            # taxa de captação mensal (ex: 0.02 = 2% a.m.)
    pct_inadimplencia: float = 0.02    # % de inadimplência (default 2%)
    aliquota_cbs: float = ALIQUOTA_CBS_REFERENCIA
    aliquota_ibs: float = ALIQUOTA_IBS_REFERENCIA
    pct_creditos: float = 0.60         # % de créditos a compensar


@dataclass
class ResultadoModalidade:
    modalidade: str
    nome_completo: str
    base_legal: str

    tributo_bruto_mensal: float = 0.0
    tributo_retido_mensal: float = 0.0
    creditos_compensados: float = 0.0

    float_perdido_mensal: float = 0.0
    custo_financeiro_mensal: float = 0.0
    custo_financeiro_anual: float = 0.0
    impacto_margem_pct: float = 0.0

    capital_giro_adicional: float = 0.0
    ressalvas: list = field(default_factory=list)


@dataclass
class ResultadoSplitPayment:
    faturamento_mensal: float
    modalidades: list = field(default_factory=list)
    recomendacao: str = ""
    status_aliquotas: str = "estimada"


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------

def _calcular_modalidade(
    cenario: CenarioSplitPayment,
    modalidade: str,
) -> ResultadoModalidade:

    nomes = {
        "inteligente":  ("Split Payment Inteligente",    "art. 32, LC 214/2025"),
        "simplificado": ("Split Payment Simplificado",   "art. 33, LC 214/2025"),
        "contingencia": ("Split Payment de Contingência", "art. 32, §4º, LC 214/2025"),
    }
    nome, base = nomes[modalidade]

    fat = cenario.faturamento_mensal
    aliquota_total = cenario.aliquota_cbs + cenario.aliquota_ibs
    pct_retencao = PERCENTUAL_RETENCAO[modalidade]
    dias_ajuste = DIAS_AJUSTE[modalidade]

    # Tributo bruto sobre o faturamento
    tributo_bruto = fat * aliquota_total

    # Créditos compensados (apenas no inteligente — em tempo real)
    creditos = (
        fat * cenario.pct_creditos * aliquota_total
        if modalidade == "inteligente"
        else 0.0
    )

    # Tributo efetivamente retido
    tributo_retido = max(0.0, tributo_bruto * pct_retencao - creditos)

    # Float perdido: valor que não transita mais pela conta do vendedor
    float_prazo = fat * cenario.pct_prazo * aliquota_total * pct_retencao
    float_vista = fat * cenario.pct_vista * aliquota_total * pct_retencao
    float_total = float_prazo + float_vista

    # Custo financeiro da antecipação
    prazo_anos = cenario.prazo_medio_dias / 360
    taxa_aa = (1 + cenario.taxa_captacao_am) ** 12 - 1
    custo_prazo = float_prazo * taxa_aa * prazo_anos

    # Custo do período de ajuste (simplificado/contingência)
    custo_ajuste = tributo_retido * cenario.taxa_captacao_am * (dias_ajuste / 30)

    custo_total_mensal = custo_prazo + custo_ajuste
    custo_total_anual = custo_total_mensal * 12

    impacto_margem = custo_total_mensal / fat if fat > 0 else 0.0

    # Capital de giro adicional necessário
    capital_giro = float_prazo * (cenario.prazo_medio_dias / 30)

    ressalvas = []
    if modalidade == "inteligente":
        ressalvas.append(
            "Percentual de retenção estimado em 40% após compensação — "
            "depende de regulamentação do CGIBS e integração com sistemas de pagamento."
        )
    if modalidade == "simplificado":
        ressalvas.append(
            "Percentual fixo de retenção estimado em 80% — "
            "valor definitivo a ser regulamentado pelo CGIBS."
        )
    ressalvas.append(
        f"Alíquotas CBS ({cenario.aliquota_cbs:.1%}) e IBS ({cenario.aliquota_ibs:.1%}) "
        "são estimativas de referência para 2027+."
    )

    return ResultadoModalidade(
        modalidade=modalidade,
        nome_completo=nome,
        base_legal=base,
        tributo_bruto_mensal=round(tributo_bruto, 2),
        tributo_retido_mensal=round(tributo_retido, 2),
        creditos_compensados=round(creditos, 2),
        float_perdido_mensal=round(float_total, 2),
        custo_financeiro_mensal=round(custo_total_mensal, 2),
        custo_financeiro_anual=round(custo_total_anual, 2),
        impacto_margem_pct=round(impacto_margem, 6),
        capital_giro_adicional=round(capital_giro, 2),
        ressalvas=ressalvas,
    )


def simular_split_payment(cenario: CenarioSplitPayment) -> ResultadoSplitPayment:
    """Simula o impacto do split payment nas 3 modalidades."""

    modalidades = [
        _calcular_modalidade(cenario, "inteligente"),
        _calcular_modalidade(cenario, "simplificado"),
        _calcular_modalidade(cenario, "contingencia"),
    ]

    melhor = min(modalidades, key=lambda m: m.custo_financeiro_mensal)
    recomendacao = (
        f"Para este cenário, **{melhor.nome_completo}** apresenta o menor custo financeiro "
        f"({formatar_brl(melhor.custo_financeiro_mensal)}/mês). "
        "Considere também a complexidade operacional de cada modalidade."
    )

    return ResultadoSplitPayment(
        faturamento_mensal=cenario.faturamento_mensal,
        modalidades=modalidades,
        recomendacao=recomendacao,
        status_aliquotas="estimada",
    )


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

def formatar_brl(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
