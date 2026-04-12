"""
src/outputs/stakeholders_inline.py — Saídas por Stakeholder (DC v7, G16).

Gera resumos inline por stakeholder após cada análise do motor cognitivo.
Diferente de src/outputs/stakeholders.py (que decompe documentos armazenados),
este módulo opera sobre a resposta da análise em tempo real.

Princípio DC v7: "Análise sem ação é análise inútil."
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Definição dos 5 stakeholders DC v7
# ---------------------------------------------------------------------------

STAKEHOLDERS: dict[str, dict] = {
    "cfo": {
        "label": "CFO / Direção",
        "emoji": "💼",
        "foco": "impacto financeiro",
        "instrucao": (
            "Resumo executivo para o CFO. Foco em: impacto em margem operacional, "
            "fluxo de caixa, EBITDA, capital de giro e ROI. "
            "Quantificar o impacto em R$ sempre que possível. "
            "Máximo 4 bullets. Linguagem executiva, sem jargão tributário."
        ),
    },
    "juridico": {
        "label": "Jurídico / Compliance",
        "emoji": "⚖️",
        "foco": "riscos e contencioso",
        "instrucao": (
            "Resumo para a área jurídica. Foco em: riscos de autuação, "
            "probabilidade de contencioso, multas e penalidades, posições divergentes "
            "que podem ser questionadas, grau de consolidação da posição adotada. "
            "Máximo 4 bullets. Citar base legal quando relevante."
        ),
    },
    "compras": {
        "label": "Compras / Supply Chain",
        "emoji": "🛒",
        "foco": "cadeia de fornecedores",
        "instrucao": (
            "Resumo para a área de compras. Foco em: impacto de credenciamento de "
            "fornecedores, créditos de IBS/CBS nas aquisições, fornecedores no "
            "Simples Nacional (crédito presumido), impacto no preço de compra, "
            "necessidade de revisar contratos com fornecedores. "
            "Máximo 4 bullets. Linguagem operacional."
        ),
    },
    "ti": {
        "label": "TI / Sistemas",
        "emoji": "💻",
        "foco": "adequações de sistemas",
        "instrucao": (
            "Resumo para a área de TI. Foco em: adequações necessárias no ERP, "
            "novos campos na NF-e (CBS/IBS/IS), split payment (integração com "
            "meios de pagamento), NF-e débito/crédito (finNFe 5 e 6), "
            "prazo de implementação, integração com CGIBS e RFB. "
            "Máximo 4 bullets. Linguagem técnica de sistemas."
        ),
    },
    "tributario": {
        "label": "Área Tributária",
        "emoji": "📊",
        "foco": "análise técnica completa",
        "instrucao": (
            "Resumo técnico para o gestor tributário. Foco em: posição recomendada "
            "com fundamentação legal, premissas críticas, riscos identificados, "
            "contra-tese, próximos passos concretos. "
            "Máximo 5 bullets. Linguagem técnica tributária completa."
        ),
    },
}

_PROMPT_TEMPLATE = """\
Com base na análise tributária abaixo, gere um resumo para {stakeholder_label}.

ANÁLISE ORIGINAL:
{analise_original}

INSTRUÇÕES PARA O RESUMO:
{instrucao}

Formato da resposta:
• [bullet 1]
• [bullet 2]
• [bullet 3]
(máximo 4–5 bullets conforme instrução)

Responda APENAS com os bullets. Sem introdução, sem conclusão, sem cabeçalho.
"""

# Stakeholders padrão para consultas rápidas (minimiza latência)
STAKEHOLDERS_PADRAO = ["cfo", "juridico", "tributario"]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ResumoStakeholder:
    stakeholder_id: str
    label: str
    emoji: str
    foco: str
    resumo: str
    gerado_com_sucesso: bool = True
    erro: str = ""


@dataclass
class SaidasPorStakeholder:
    resumos: list[ResumoStakeholder] = field(default_factory=list)
    analise_base: str = ""


# ---------------------------------------------------------------------------
# Geração de prompt
# ---------------------------------------------------------------------------

def _gerar_prompt_stakeholder(
    stakeholder_id: str,
    analise_original: str,
) -> str:
    config = STAKEHOLDERS[stakeholder_id]
    return _PROMPT_TEMPLATE.format(
        stakeholder_label=config["label"],
        analise_original=analise_original[:3000],
        instrucao=config["instrucao"],
    )


# ---------------------------------------------------------------------------
# Geração dos resumos (chamada pelo engine)
# ---------------------------------------------------------------------------

def gerar_resumos_stakeholders(
    analise_original: str,
    client,
    model: str,
    stakeholders_ativos: list[str] | None = None,
) -> SaidasPorStakeholder:
    """
    Gera resumos por stakeholder após a análise principal.
    Falhas individuais não interrompem os demais.

    Args:
        analise_original: texto da resposta da análise
        client: instância anthropic.Anthropic
        model: model ID
        stakeholders_ativos: IDs a gerar (default: STAKEHOLDERS_PADRAO)
    """
    if stakeholders_ativos is None:
        stakeholders_ativos = STAKEHOLDERS_PADRAO

    resumos: list[ResumoStakeholder] = []
    for st_id in stakeholders_ativos:
        if st_id not in STAKEHOLDERS:
            continue
        config = STAKEHOLDERS[st_id]
        try:
            prompt = _gerar_prompt_stakeholder(st_id, analise_original)
            response = client.messages.create(
                model=model,
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}],
            )
            texto = response.content[0].text.strip()
            resumos.append(ResumoStakeholder(
                stakeholder_id=st_id,
                label=config["label"],
                emoji=config["emoji"],
                foco=config["foco"],
                resumo=texto,
            ))
        except Exception as exc:
            resumos.append(ResumoStakeholder(
                stakeholder_id=st_id,
                label=config["label"],
                emoji=config["emoji"],
                foco=config["foco"],
                resumo="",
                gerado_com_sucesso=False,
                erro=str(exc),
            ))

    return SaidasPorStakeholder(resumos=resumos, analise_base=analise_original)


def resumos_para_dict(saidas: SaidasPorStakeholder) -> list[dict]:
    """Serializa SaidasPorStakeholder para JSON-safe list."""
    return [
        {
            "stakeholder_id": r.stakeholder_id,
            "label": r.label,
            "emoji": r.emoji,
            "foco": r.foco,
            "resumo": r.resumo,
            "gerado_com_sucesso": r.gerado_com_sucesso,
        }
        for r in saidas.resumos
    ]
