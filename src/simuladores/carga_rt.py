"""
src/simuladores/carga_rt.py — MP-01 Simulador Comparativo de Carga RT (G18).

Calcula carga tributária estimada nos regimes atual (PIS/COFINS + ICMS/ISS)
e novo (CBS + IBS) para um cenário operacional, projetando transição 2026-2033.

Premissas de alíquota (DC v7 / LC 214-2025):
  - CBS: 8,8% (serviços) / 9,9% (mercadorias) — fase plena
  - IBS: 17,7% (média nacional estimada RFB 2025)
  - Período teste CBS: 0,9% (2026) → plena em 2027
  - Período teste IBS: idem CBS (simbólico 2026), gradual 2027-2028
  - Crédito pleno admitido para CBS/IBS (exceto setores específicos).
  - ICMS médio nacional: 17%, ISS: 2-5%; PIS/COFINS: 9,25% (lucro real)
    ou 3,65% (presumido).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constantes de alíquota (ajustáveis por atualização normativa)
# ---------------------------------------------------------------------------

# CBS — Contribuição sobre Bens e Serviços (federal)
CBS_ALIQUOTA_PLENA_SERVICOS = 0.088    # 8,8%
CBS_ALIQUOTA_PLENA_MERCADORIAS = 0.099  # 9,9%
CBS_ALIQUOTA_TESTE_2026 = 0.009        # 0,9% (ano-teste)

# IBS — Imposto sobre Bens e Serviços (estados+municípios)
IBS_ALIQUOTA_PLENA = 0.177             # 17,7% (média nacional RFB/2025)
IBS_ALIQUOTA_TESTE_2026 = 0.001        # 0,1% simbólico
IBS_ALIQUOTA_TRANSICAO_2027 = 0.010    # 1% (redução ICMS+ISS compensa)
IBS_ALIQUOTA_TRANSICAO_2028 = 0.060    # 6%

# Regimes atuais (PIS/COFINS)
PISCOFINS_LUCRO_REAL = 0.0925          # 9,25%
PISCOFINS_LUCRO_PRESUMIDO = 0.0365     # 3,65%
PISCOFINS_SIMPLES = 0.0               # embutido no Simples

# ICMS médio nacional; ISS médio
ICMS_MEDIO = 0.17
ISS_SERVICOS_BAIXO = 0.02
ISS_SERVICOS_ALTO = 0.05
ISS_MEDIO = 0.03

# Crédito aproveitável no regime atual (fração da base — limitado a insumos)
CREDITO_ICMS_PROPORCAO = 0.40          # 40% da carga ICMS é creditável na cadeia
CREDITO_PIS_COFINS_PROPORCAO = 0.35    # 35% não cumulativo

# Calendário de transição (LC 214-2025 art. 348-ss)
ANOS_SIMULADOS = [2024, 2025, 2026, 2027, 2028, 2029, 2033]


# ---------------------------------------------------------------------------
# Tipos de entrada
# ---------------------------------------------------------------------------

REGIMES_TRIBUTARIOS = [
    "lucro_real",
    "lucro_presumido",
    "simples_nacional",
]

TIPOS_OPERACAO = [
    "misto",           # mercadorias + serviços
    "so_mercadorias",
    "so_servicos",
]


@dataclass
class CenarioOperacional:
    """Parâmetros do cenário a simular."""

    faturamento_anual: float           # R$ bruto
    regime_tributario: str             # lucro_real | lucro_presumido | simples_nacional
    tipo_operacao: str                 # misto | so_mercadorias | so_servicos
    percentual_exportacao: float = 0.0  # 0-1 (imune a IBS/CBS)
    percentual_credito_novo: float = 1.0  # 0-1 aproveitamento CBS/IBS esperado

    def __post_init__(self) -> None:
        if self.regime_tributario not in REGIMES_TRIBUTARIOS:
            raise ValueError(f"regime_tributario inválido: {self.regime_tributario}")
        if self.tipo_operacao not in TIPOS_OPERACAO:
            raise ValueError(f"tipo_operacao inválido: {self.tipo_operacao}")
        if not (0.0 <= self.percentual_exportacao <= 1.0):
            raise ValueError("percentual_exportacao deve estar entre 0 e 1")
        if not (0.0 <= self.percentual_credito_novo <= 1.0):
            raise ValueError("percentual_credito_novo deve estar entre 0 e 1")


@dataclass
class ResultadoSimulacao:
    """Resultado de um ano de simulação."""

    ano: int
    regime: str                        # "atual" | "novo" | "transicao"
    carga_bruta: float                 # R$ sem créditos
    creditos_estimados: float          # R$ aproveitável
    carga_liquida: float               # carga_bruta - creditos_estimados
    aliquota_efetiva: float            # carga_liquida / faturamento
    detalhes: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Funções de cálculo
# ---------------------------------------------------------------------------

def _base_tributavel(cenario: CenarioOperacional) -> float:
    """Base tributável excluindo exportações (imunes)."""
    return cenario.faturamento_anual * (1.0 - cenario.percentual_exportacao)


def _carga_regime_atual(cenario: CenarioOperacional) -> tuple[float, float, dict]:
    """Retorna (carga_bruta, creditos, detalhes) para regime atual."""
    base = _base_tributavel(cenario)

    # PIS/COFINS
    if cenario.regime_tributario == "lucro_real":
        aliq_piscofins = PISCOFINS_LUCRO_REAL
        cred_piscofins = base * aliq_piscofins * CREDITO_PIS_COFINS_PROPORCAO
    elif cenario.regime_tributario == "lucro_presumido":
        aliq_piscofins = PISCOFINS_LUCRO_PRESUMIDO
        cred_piscofins = 0.0
    else:  # simples
        aliq_piscofins = 0.0
        cred_piscofins = 0.0

    piscofins_bruto = base * aliq_piscofins

    # ICMS / ISS conforme tipo operação
    if cenario.tipo_operacao == "so_servicos":
        icms_bruto = 0.0
        iss_bruto = base * ISS_MEDIO
        cred_icms = 0.0
    elif cenario.tipo_operacao == "so_mercadorias":
        icms_bruto = base * ICMS_MEDIO
        iss_bruto = 0.0
        cred_icms = icms_bruto * CREDITO_ICMS_PROPORCAO
    else:  # misto
        icms_bruto = base * 0.5 * ICMS_MEDIO
        iss_bruto = base * 0.5 * ISS_MEDIO
        cred_icms = icms_bruto * CREDITO_ICMS_PROPORCAO

    carga_bruta = piscofins_bruto + icms_bruto + iss_bruto
    creditos = cred_piscofins + cred_icms

    detalhes = {
        "piscofins": round(piscofins_bruto, 2),
        "icms": round(icms_bruto, 2),
        "iss": round(iss_bruto, 2),
        "credito_piscofins": round(cred_piscofins, 2),
        "credito_icms": round(cred_icms, 2),
    }
    return carga_bruta, creditos, detalhes


def _aliquota_cbs(ano: int, tipo: str) -> float:
    """CBS vigente para o ano e tipo de operação."""
    if ano <= 2025:
        return 0.0
    if ano == 2026:
        return CBS_ALIQUOTA_TESTE_2026
    aliq_plena = (CBS_ALIQUOTA_PLENA_SERVICOS if tipo == "so_servicos"
                  else CBS_ALIQUOTA_PLENA_MERCADORIAS)
    return aliq_plena


def _aliquota_ibs(ano: int) -> float:
    """IBS vigente para o ano."""
    if ano <= 2025:
        return 0.0
    if ano == 2026:
        return IBS_ALIQUOTA_TESTE_2026
    if ano == 2027:
        return IBS_ALIQUOTA_TRANSICAO_2027
    if ano == 2028:
        return IBS_ALIQUOTA_TRANSICAO_2028
    return IBS_ALIQUOTA_PLENA  # 2029+


def _carga_regime_novo(cenario: CenarioOperacional, ano: int) -> tuple[float, float, dict]:
    """Retorna (carga_bruta, creditos, detalhes) para regime CBS+IBS num dado ano."""
    base = _base_tributavel(cenario)

    aliq_cbs = _aliquota_cbs(ano, cenario.tipo_operacao)
    aliq_ibs = _aliquota_ibs(ano)

    cbs_bruto = base * aliq_cbs
    ibs_bruto = base * aliq_ibs

    # Crédito pleno admitido (não-cumulativo total)
    credito_cbs = cbs_bruto * cenario.percentual_credito_novo
    credito_ibs = ibs_bruto * cenario.percentual_credito_novo

    carga_bruta = cbs_bruto + ibs_bruto
    creditos = credito_cbs + credito_ibs

    # Em anos de transição (2027-2032), ICMS/ISS ainda coexistem com IBS
    icms_residual = 0.0
    iss_residual = 0.0
    if 2027 <= ano <= 2032:
        fator_reducao_icms = max(0.0, 1.0 - (ano - 2026) / 7)
        if cenario.tipo_operacao != "so_servicos":
            icms_residual = base * ICMS_MEDIO * 0.5 * fator_reducao_icms
        if cenario.tipo_operacao != "so_mercadorias":
            iss_residual = base * ISS_MEDIO * 0.5 * fator_reducao_icms
        carga_bruta += icms_residual + iss_residual

    detalhes = {
        "cbs": round(cbs_bruto, 2),
        "ibs": round(ibs_bruto, 2),
        "icms_residual": round(icms_residual, 2),
        "iss_residual": round(iss_residual, 2),
        "credito_cbs": round(credito_cbs, 2),
        "credito_ibs": round(credito_ibs, 2),
        "aliquota_cbs": round(aliq_cbs * 100, 2),
        "aliquota_ibs": round(aliq_ibs * 100, 2),
    }
    return carga_bruta, creditos, detalhes


def simular_carga(
    cenario: CenarioOperacional,
    ano: int,
) -> tuple[ResultadoSimulacao, ResultadoSimulacao]:
    """
    Simula carga atual vs. nova para um único ano.

    Returns:
        (resultado_atual, resultado_novo)
    """
    base = _base_tributavel(cenario)
    if cenario.faturamento_anual <= 0:
        raise ValueError("faturamento_anual deve ser positivo")

    # Regime atual
    cb_atual, cr_atual, det_atual = _carga_regime_atual(cenario)
    liq_atual = cb_atual - cr_atual
    atual = ResultadoSimulacao(
        ano=ano,
        regime="atual",
        carga_bruta=round(cb_atual, 2),
        creditos_estimados=round(cr_atual, 2),
        carga_liquida=round(liq_atual, 2),
        aliquota_efetiva=round(liq_atual / base, 4) if base else 0.0,
        detalhes=det_atual,
    )

    # Regime novo (CBS+IBS) para o ano solicitado
    cb_novo, cr_novo, det_novo = _carga_regime_novo(cenario, ano)
    liq_novo = cb_novo - cr_novo
    novo = ResultadoSimulacao(
        ano=ano,
        regime="novo" if ano >= 2029 else "transicao",
        carga_bruta=round(cb_novo, 2),
        creditos_estimados=round(cr_novo, 2),
        carga_liquida=round(liq_novo, 2),
        aliquota_efetiva=round(liq_novo / base, 4) if base else 0.0,
        detalhes=det_novo,
    )

    return atual, novo


def simular_multiplos_anos(
    cenario: CenarioOperacional,
    anos: Optional[list[int]] = None,
) -> list[dict]:
    """
    Projeta carga ao longo dos anos de transição.

    Returns:
        Lista de dicts com {ano, carga_liquida_atual, carga_liquida_nova, variacao_pct}.
    """
    if anos is None:
        anos = ANOS_SIMULADOS

    resultado = []
    for ano in anos:
        atual, novo = simular_carga(cenario, ano)
        if atual.carga_liquida > 0:
            variacao_pct = (novo.carga_liquida - atual.carga_liquida) / atual.carga_liquida
        else:
            variacao_pct = 0.0
        resultado.append({
            "ano": ano,
            "carga_liquida_atual": atual.carga_liquida,
            "carga_liquida_nova": novo.carga_liquida,
            "aliquota_efetiva_atual": atual.aliquota_efetiva,
            "aliquota_efetiva_nova": novo.aliquota_efetiva,
            "variacao_pct": round(variacao_pct, 4),
            "regime_novo": novo.regime,
            "detalhes_atual": atual.detalhes,
            "detalhes_novo": novo.detalhes,
        })
    return resultado


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

def formatar_brl(valor: float) -> str:
    """Formata float como moeda BRL (ex: R$ 1.234.567,89)."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
