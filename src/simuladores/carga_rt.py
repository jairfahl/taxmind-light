"""
src/simuladores/carga_rt.py — MP-01 Simulador Comparativo de Carga RT (G18).

Calcula carga tributária estimada nos regimes atual (PIS/COFINS + ICMS/ISS)
e novo (CBS + IBS) para um cenário operacional, projetando transição 2026-2033.

Premissas de alíquota (EC 132/2023 + LC 214/2025):
  - CBS: 8,8% uniforme (bens e serviços) — fase plena
  - IBS: 17,7% (média nacional estimada RFB/2025) — fase plena
  - Período teste CBS: 0,9% (2026) — neutro por crédito PIS/COFINS equivalente
  - IBS gradual: 1% (2027), 6% (2028), 11% (2029), 13% (2030), 15% (2031), 16,5% (2032)
  - ICMS phase-out: 100% em 2027-2028; 80/60/40/20% em 2029-2032; extinto em 2033
  - 2024-2026: regime atual vigente (CBS-teste 2026 é neutro)
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
# BUG 6 fix: CBS é uniforme para bens e serviços (EC 132/2023 + LC 214/2025)
CBS_ALIQUOTA_PLENA = 0.088             # 8,8% uniforme
CBS_ALIQUOTA_TESTE_2026 = 0.009        # 0,9% (ano-teste — neutro por crédito PIS/COFINS)

# IBS — Imposto sobre Bens e Serviços (estados+municípios)
IBS_ALIQUOTA_PLENA = 0.177             # 17,7% (média nacional RFB/2025)
IBS_ALIQUOTA_TESTE_2026 = 0.001        # 0,1% simbólico
# BUG 5 fix: IBS gradual 2027-2032 per LC 214/2025 (não salta para pleno em 2029)
IBS_ALIQUOTA_TRANSICAO = {
    2027: 0.010,   # 1%
    2028: 0.060,   # 6%
    2029: 0.110,   # 11%
    2030: 0.130,   # 13%
    2031: 0.150,   # 15%
    2032: 0.165,   # 16,5%
}

# BUG 4 fix: ICMS permanece 100% em 2027-2028; redução começa em 2029 per LC 214/2025 art. 348
ICMS_FATOR_TRANSICAO = {
    2027: 1.00,
    2028: 1.00,
    2029: 0.80,
    2030: 0.60,
    2031: 0.40,
    2032: 0.20,
    # 2033+: 0.0 (extinto)
}

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
ANOS_SIMULADOS = [2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033]


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


def _aliquota_cbs(ano: int) -> float:
    """CBS vigente para o ano — uniforme para bens e serviços (EC 132/2023)."""
    if ano <= 2025:
        return 0.0
    if ano == 2026:
        return CBS_ALIQUOTA_TESTE_2026
    return CBS_ALIQUOTA_PLENA  # 2027+: 8,8% uniforme


def _aliquota_ibs(ano: int) -> float:
    """IBS vigente para o ano — gradual 2027-2032, pleno a partir de 2033."""
    if ano <= 2025:
        return 0.0
    if ano == 2026:
        return IBS_ALIQUOTA_TESTE_2026
    return IBS_ALIQUOTA_TRANSICAO.get(ano, IBS_ALIQUOTA_PLENA)


def _carga_regime_novo(cenario: CenarioOperacional, ano: int) -> tuple[float, float, dict]:
    """Retorna (carga_bruta, creditos, detalhes) para regime CBS+IBS num dado ano."""
    # BUG 1/2 fix: 2024-2026 — CBS/IBS inexistentes ou neutros; empresa paga regime atual
    if ano <= 2026:
        cb, cr, det = _carga_regime_atual(cenario)
        det = dict(det, nota="regime_atual_vigente")
        return cb, cr, det

    base = _base_tributavel(cenario)

    aliq_cbs = _aliquota_cbs(ano)
    aliq_ibs = _aliquota_ibs(ano)

    cbs_bruto = base * aliq_cbs
    ibs_bruto = base * aliq_ibs

    # Crédito pleno admitido (não-cumulativo total)
    credito_cbs = cbs_bruto * cenario.percentual_credito_novo
    credito_ibs = ibs_bruto * cenario.percentual_credito_novo

    carga_bruta = cbs_bruto + ibs_bruto

    # ICMS/ISS residual (2027-2032) com fatores corretos per LC 214/2025
    icms_residual = 0.0
    iss_residual = 0.0
    cred_icms_res = 0.0
    if 2027 <= ano <= 2032:
        fator_icms = ICMS_FATOR_TRANSICAO.get(ano, 0.0)
        # BUG 3/4 fix: fator_tipo 1.0 para operação pura; 0.5 somente para misto
        fator_tipo = 0.5 if cenario.tipo_operacao == "misto" else 1.0
        if cenario.tipo_operacao != "so_servicos":
            icms_residual = base * ICMS_MEDIO * fator_tipo * fator_icms
            cred_icms_res = icms_residual * CREDITO_ICMS_PROPORCAO
        if cenario.tipo_operacao != "so_mercadorias":
            iss_residual = base * ISS_MEDIO * fator_tipo * fator_icms
        carga_bruta += icms_residual + iss_residual

    creditos = credito_cbs + credito_ibs + cred_icms_res

    detalhes = {
        "cbs": round(cbs_bruto, 2),
        "ibs": round(ibs_bruto, 2),
        "icms_residual": round(icms_residual, 2),
        "iss_residual": round(iss_residual, 2),
        "credito_cbs": round(credito_cbs, 2),
        "credito_ibs": round(credito_ibs, 2),
        "credito_icms_residual": round(cred_icms_res, 2),
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
