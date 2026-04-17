"""
src/simuladores/creditos_ibs_cbs.py — MP-02 Monitor de Créditos IBS/CBS.
DC v7, Seção: Métodos Proprietários — Capítulo RT.

Mapeia o portfólio de créditos de CBS/IBS nas aquisições,
identifica créditos bloqueados e oportunidades de recuperação.
Fundamentação: LC 214/2025, arts. 28–55 (não-cumulatividade plena).
"""

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Tipos de creditamento
# ---------------------------------------------------------------------------

class TipoCreditamento(str, Enum):
    INTEGRAL   = "integral"
    PRESUMIDO  = "presumido"    # fornecedor Simples Nacional
    PARCIAL    = "parcial"
    NENHUM     = "nenhum"
    INDEFINIDO = "indefinido"   # aguarda regulamentação


# ---------------------------------------------------------------------------
# Categorias de aquisição
# ---------------------------------------------------------------------------

CATEGORIAS_AQUISICAO = {
    "insumos_diretos": {
        "label": "Insumos diretos / matérias-primas",
        "creditamento": TipoCreditamento.INTEGRAL,
        "base_legal": "LC 214/2025, art. 28",
        "descricao": "Não-cumulatividade plena — crédito integral sobre insumos da cadeia produtiva.",
        "risco": "baixo",
    },
    "servicos_tomados": {
        "label": "Serviços tomados (B2B)",
        "creditamento": TipoCreditamento.INTEGRAL,
        "base_legal": "LC 214/2025, art. 28",
        "descricao": "Crédito integral sobre serviços adquiridos para a atividade.",
        "risco": "baixo",
    },
    "ativo_imobilizado": {
        "label": "Ativo imobilizado (CAPEX)",
        "creditamento": TipoCreditamento.INTEGRAL,
        "base_legal": "LC 214/2025, art. 29",
        "descricao": "Nova regra RT — crédito integral sobre CAPEX (antes restrito no regime PIS/Cofins).",
        "risco": "medio",
        "alerta": "Regulamentação do Comitê Gestor sobre prazo de apropriação pendente.",
    },
    "fornecedor_simples": {
        "label": "Aquisições de fornecedores do Simples Nacional",
        "creditamento": TipoCreditamento.PRESUMIDO,
        "base_legal": "LC 214/2025, art. 30",
        "descricao": "Crédito presumido — alíquota presumida aplicada sobre valor da NF-e.",
        "risco": "medio",
        "alerta": "Alíquota presumida a ser definida pelo CGIBS. Risco de glosa se presumido incorreto.",
    },
    "uso_consumo": {
        "label": "Uso e consumo (despesas gerais de negócio)",
        # CR-1 fix: art. 28 garante não-cumulatividade ampla; art. 57 lista taxativamente o
        # que NÃO gera crédito (itens de uso pessoal). Despesas gerais de negócio SÃO creditáveis.
        "creditamento": TipoCreditamento.INTEGRAL,
        "base_legal": "LC 214/2025, arts. 28 e 57",
        "descricao": (
            "Despesas gerais da atividade econômica geram crédito integral (art. 28). "
            "Exceções — sem direito a crédito: joias, bebidas alcoólicas, tabaco, armas, "
            "bens recreativos/estéticos e bens cedidos a pessoas físicas vinculadas (art. 57)."
        ),
        "risco": "medio",
        "alerta": (
            "Segregar itens de uso pessoal (art. 57 LC 214/2025) — estes NÃO geram crédito. "
            "Demais despesas gerais da atividade econômica são creditáveis."
        ),
    },
    "operacoes_imunes_isentas": {
        "label": "Aquisições vinculadas a saídas imunes ou isentas",
        "creditamento": TipoCreditamento.NENHUM,
        "base_legal": "LC 214/2025, art. 35",
        "descricao": "Sem direito a crédito. Exige reversão proporcional conforme art. 35.",
        "risco": "alto",
        # CR-3 fix: removida referência "Ajuste SINIEF 49/2025" não verificável na lei
        "alerta": (
            "Créditos já tomados devem ser revertidos na proporção das saídas imunes/isentas "
            "(LC 214/2025, art. 35). Verificar regulamentação do CGIBS sobre procedimento de estorno."
        ),
    },
    "exportacoes": {
        "label": "Aquisições para exportação",
        "creditamento": TipoCreditamento.INTEGRAL,
        "base_legal": "LC 214/2025, art. 32 (desoneração exportações)",
        "descricao": "Crédito integral — exportações são desoneradas.",
        "risco": "baixo",
    },
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ItemAquisicao:
    categoria: str
    valor_mensal: float
    aliquota_cbs: float = 0.088
    aliquota_ibs: float = 0.177
    aliquota_presumida_simples: float = 0.04  # estimativa para Simples


@dataclass
class ResultadoCredito:
    categoria: str
    label: str
    creditamento: TipoCreditamento
    base_legal: str
    valor_aquisicao_mensal: float
    credito_estimado_mensal: float
    credito_estimado_anual: float
    risco: str
    alerta: str = ""
    ressalvas: list = field(default_factory=list)


@dataclass
class ResultadoMonitorCreditos:
    total_aquisicoes_mensal: float
    total_credito_mensal: float
    total_credito_anual: float
    creditos_em_risco: float
    oportunidade_capex: float
    itens: list = field(default_factory=list)
    alertas: list = field(default_factory=list)
    # CR-2 fix: prazo padrão é 180 dias (art. 39 LC 214/2025).
    # Fast-track 60 dias: créditos de ativo imobilizado (CAPEX) ou dentro de 150% da média
    # mensal dos 24 meses anteriores. Fast-track 30 dias: contribuintes em programa de
    # conformidade tributária (CGIBS/RFB).
    prazo_restituicao_dias: int = 180


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------

def _calcular_credito_item(item: ItemAquisicao) -> ResultadoCredito:
    config = CATEGORIAS_AQUISICAO.get(item.categoria, {})
    creditamento = config.get("creditamento", TipoCreditamento.INDEFINIDO)
    aliquota_total = item.aliquota_cbs + item.aliquota_ibs
    ressalvas = []

    if creditamento == TipoCreditamento.INTEGRAL:
        credito_mensal = item.valor_mensal * aliquota_total

    elif creditamento == TipoCreditamento.PRESUMIDO:
        credito_mensal = item.valor_mensal * item.aliquota_presumida_simples
        ressalvas.append(
            f"Alíquota presumida de {item.aliquota_presumida_simples:.1%} "
            "é estimativa — valor definitivo a ser regulamentado pelo CGIBS."
        )

    elif creditamento == TipoCreditamento.PARCIAL:
        credito_mensal = item.valor_mensal * aliquota_total * 0.5
        ressalvas.append("Creditamento parcial estimado em 50% — aguardar regulamentação.")

    elif creditamento == TipoCreditamento.NENHUM:
        credito_mensal = 0.0
        ressalvas.append(
            "Sem direito a crédito. Verifique necessidade de emissão de NF-e débito tipo 02."
        )

    else:  # INDEFINIDO
        credito_mensal = 0.0
        ressalvas.append(
            "Creditamento indefinido — aguardar regulamentação do CGIBS. "
            "Não reconhecer até definição oficial."
        )

    return ResultadoCredito(
        categoria=item.categoria,
        label=config.get("label", item.categoria),
        creditamento=creditamento,
        base_legal=config.get("base_legal", ""),
        valor_aquisicao_mensal=round(item.valor_mensal, 2),
        credito_estimado_mensal=round(credito_mensal, 2),
        credito_estimado_anual=round(credito_mensal * 12, 2),
        risco=config.get("risco", "medio"),
        alerta=config.get("alerta", ""),
        ressalvas=ressalvas,
    )


def mapear_creditos(itens: list) -> ResultadoMonitorCreditos:
    """Mapeia o portfólio completo de créditos IBS/CBS."""
    resultados = [_calcular_credito_item(item) for item in itens]

    total_aquisicoes = sum(i.valor_mensal for i in itens)
    total_credito = sum(r.credito_estimado_mensal for r in resultados)
    em_risco = sum(
        r.credito_estimado_mensal
        for r in resultados
        if r.risco in ("alto", "medio")
    )

    capex_item = next((r for r in resultados if r.categoria == "ativo_imobilizado"), None)
    oportunidade_capex = capex_item.credito_estimado_mensal if capex_item else 0.0

    alertas = [f"[{r.label}] {r.alerta}" for r in resultados if r.alerta]

    return ResultadoMonitorCreditos(
        total_aquisicoes_mensal=round(total_aquisicoes, 2),
        total_credito_mensal=round(total_credito, 2),
        total_credito_anual=round(total_credito * 12, 2),
        creditos_em_risco=round(em_risco, 2),
        oportunidade_capex=round(oportunidade_capex, 2),
        itens=resultados,
        alertas=alertas,
    )


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

def formatar_brl(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
