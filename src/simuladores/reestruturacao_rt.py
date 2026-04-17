"""
MP-03 — Simulador de Reestruturação RT.
DC v7, Seção: Métodos Proprietários — Capítulo RT.

Analisa o impacto da extinção dos incentivos fiscais estaduais de ICMS
e avalia se a estrutura geográfica atual (CD, filiais, plantas) ainda
faz sentido sob o novo regime tributário.

Premissa: com IBS no destino, incentivos estaduais de ICMS deixam de
justificar decisões de localização geográfica. A eficiência logística
passa a ser o critério determinante.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── BENEFÍCIOS ICMS POR UF (estimativas de mercado) ──────────────────────────
# Representa % de vantagem fiscal de ICMS que justificava operações naquela UF
BENEFICIO_ICMS_UF: dict[str, float] = {
    "AC": 0.12, "AL": 0.08, "AM": 0.18,  # ZFM
    "AP": 0.10, "BA": 0.10, "CE": 0.12,
    "DF": 0.05, "ES": 0.08, "GO": 0.10,
    "MA": 0.08, "MG": 0.07, "MS": 0.09,
    "MT": 0.10, "PA": 0.09, "PB": 0.08,
    "PE": 0.10, "PI": 0.07, "PR": 0.08,
    "RJ": 0.06, "RN": 0.08, "RO": 0.09,
    "RR": 0.10, "RS": 0.07, "SC": 0.08,
    "SE": 0.08, "SP": 0.05, "TO": 0.09,
}

# RE-1 fix: fase-out dos incentivos ICMS conforme LC 214/2025.
# Incentivos ICMS permanecem 100% em 2026-2028; redução começa em 2029
# com Fundo de Compensação de Benefícios Fiscais (2029-2032 per LC 214/2025).
PHASEOUT_ICMS: dict[int, float] = {
    2026: 1.00,
    2027: 1.00,  # incentivos plenos — IBS ainda em fase-teste
    2028: 1.00,  # incentivos plenos — IBS ainda em fase-teste
    2029: 0.80,  # redução começa; fundo de compensação ativo
    2030: 0.60,
    2031: 0.40,
    2032: 0.20,
    2033: 0.00,  # ICMS extinto
}


@dataclass
class UnidadeOperacional:
    uf: str
    tipo: str                                        # 'CD', 'planta', 'filial', 'escritorio'
    custo_fixo_anual: float
    faturamento_anual: float
    beneficio_icms_justifica: bool = True            # foi criada por incentivo fiscal?
    custo_logistico_alternativo: Optional[float] = None


@dataclass
class ResultadoUnidade:
    uf: str
    tipo: str
    beneficio_icms_atual: float
    beneficio_icms_2033: float
    economia_icms_perdida: float
    custo_manutencao: float
    recomendacao: str                                # 'manter' | 'revisar' | 'encerrar'
    justificativa: str
    ano_decisao_critica: int
    ressalvas: list[str] = field(default_factory=list)


@dataclass
class ResultadoReestruturacao:
    unidades: list[ResultadoUnidade] = field(default_factory=list)
    economia_total_perdida_anual: float = 0.0
    unidades_revisar: int = 0
    unidades_encerrar: int = 0
    cronograma_decisoes: dict = field(default_factory=dict)
    ressalvas: list[str] = field(default_factory=list)


def analisar_reestruturacao(
    unidades: list[UnidadeOperacional],
    ano_analise: int = 2026,
) -> ResultadoReestruturacao:
    """Analisa o impacto da extinção dos incentivos ICMS na estrutura operacional."""
    resultado = ResultadoReestruturacao()
    economia_total = 0.0

    for unidade in unidades:
        pct_beneficio = BENEFICIO_ICMS_UF.get(unidade.uf.upper(), 0.05)
        beneficio_atual = unidade.faturamento_anual * pct_beneficio
        economia_perdida = beneficio_atual
        economia_total += economia_perdida

        # Ano em que o benefício cai a ou abaixo de 20%
        ano_critico = 2033
        for ano in range(2026, 2034):
            if PHASEOUT_ICMS.get(ano, 0.0) <= 0.20:
                ano_critico = ano
                break

        if not unidade.beneficio_icms_justifica:
            recomendacao = "manter"
            justificativa = (
                "Unidade não foi criada por incentivo fiscal — "
                "decisão de localização baseada em outros fatores."
            )
        elif economia_perdida > unidade.custo_fixo_anual * 0.30:
            recomendacao = "encerrar"
            justificativa = (
                f"A perda do incentivo ICMS (R$ {economia_perdida:,.0f}/ano) representa "
                f"mais de 30% do custo fixo anual. Reavaliar viabilidade pós-2033."
            )
            resultado.unidades_encerrar += 1
        elif economia_perdida > unidade.custo_fixo_anual * 0.10:
            recomendacao = "revisar"
            justificativa = (
                f"A perda do incentivo ICMS (R$ {economia_perdida:,.0f}/ano) representa "
                f"10–30% do custo fixo anual. Avaliar eficiência logística real."
            )
            resultado.unidades_revisar += 1
        else:
            recomendacao = "manter"
            justificativa = (
                "Impacto da perda do incentivo ICMS é baixo em relação ao custo fixo. "
                "Manter e monitorar."
            )

        ressalvas = [
            f"Benefício ICMS estimado para {unidade.uf}: {pct_beneficio:.0%} — "
            "valor real depende do regime específico do estado.",
            "Análise não considera: substância econômica, trabalhistas, logística detalhada.",
        ]

        resultado.unidades.append(ResultadoUnidade(
            uf=unidade.uf,
            tipo=unidade.tipo,
            beneficio_icms_atual=beneficio_atual,
            beneficio_icms_2033=0.0,
            economia_icms_perdida=economia_perdida,
            custo_manutencao=unidade.custo_fixo_anual,
            recomendacao=recomendacao,
            justificativa=justificativa,
            ano_decisao_critica=ano_critico,
            ressalvas=ressalvas,
        ))

    resultado.economia_total_perdida_anual = economia_total
    resultado.ressalvas = [
        "Benefícios ICMS estimados — valores reais variam por regime estadual específico.",
        "Análise não substitui due diligence jurídica e logística completa.",
        "Reestruturação societária requer revisão jurídica especializada.",
    ]
    return resultado
