"""
src/cognitive/criticidade.py — Calibração por Criticidade (DC v7, G17).

Classifica todo output em 3 níveis: Crítico | Atenção | Informativo.

Evita dois problemas opostos:
- Liturgia do protocolo: tratar toda análise com o mesmo rigor
- Fadiga de alertas: sobrecarregar o gestor com notificações de igual peso
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NivelCriticidade(str, Enum):
    CRITICO     = "critico"
    ATENCAO     = "atencao"
    INFORMATIVO = "informativo"


# Configuração visual por nível (usado pelo componente Streamlit)
CRITICIDADE_CONFIG = {
    NivelCriticidade.CRITICO: {
        "label":     "Crítico",
        "emoji":     "🔴",
        "descricao": "Risco fiscal / multa — ação imediata requerida",
        "cor_st":    "error",
        "urgencia":  "IMEDIATA",
        "canal":     "Alerta direto",
    },
    NivelCriticidade.ATENCAO: {
        "label":     "Atenção",
        "emoji":     "🟡",
        "descricao": "Impacto operacional — ação recomendada em prazo definido",
        "cor_st":    "warning",
        "urgencia":  "PRAZO DEFINIDO",
        "canal":     "Notificação com prazo",
    },
    NivelCriticidade.INFORMATIVO: {
        "label":     "Informativo",
        "emoji":     "🔵",
        "descricao": "Atualização normativa — ciência, sem ação imediata",
        "cor_st":    "info",
        "urgencia":  "SEM URGÊNCIA",
        "canal":     "Digest periódico",
    },
}

# Termos que indicam criticidade CRÍTICA
TERMOS_CRITICO = [
    "autuação", "autuado", "multa", "penalidade", "infração",
    "auto de infração", "glosa", "passivo tributário",
    "risco imediato", "ação imediata", "prazo vencido",
    "decadência", "prescrição", "contingência fiscal",
    "embargo", "interdição", "bloqueio", "penhora",
]

# Termos que indicam criticidade ATENÇÃO
TERMOS_ATENCAO = [
    "adequação", "adequar", "revisar", "rever",
    "impacto operacional", "prazo", "marco",
    "split payment", "nf-e de débito", "nf-e de crédito",
    "nota de débito", "nota de crédito",
    "regulamentação pendente", "aguardar",
    "recomendar", "recomendado", "necessário adequar",
    "transição", "phase-out", "cronograma",
]


@dataclass
class ResultadoCriticidade:
    nivel: NivelCriticidade
    justificativa: str
    termos_detectados: list[str] = field(default_factory=list)
    impacto_estimado: str = ""


def classificar_criticidade(
    resposta_ia: str,
    grau_consolidacao: str = "",
    forca_contra_tese: str = "",
    impacto_financeiro_estimado: float = 0.0,
) -> ResultadoCriticidade:
    """
    Classifica automaticamente a criticidade de uma análise.

    Critérios:
    - CRÍTICO: termos de autuação/multa OU (grau Divergente/Emergente com força Alta)
               OU impacto > R$ 50M
    - ATENÇÃO: termos de adequação/prazo OU grau Divergente/Emergente
               OU impacto R$ 10M–50M
    - INFORMATIVO: demais casos
    """
    resposta_lower = resposta_ia.lower()

    termos_criticos_encontrados = [
        t for t in TERMOS_CRITICO if t.lower() in resposta_lower
    ]
    termos_atencao_encontrados = [
        t for t in TERMOS_ATENCAO if t.lower() in resposta_lower
    ]

    # ── CRÍTICO ───────────────────────────────────────────────────────────────
    eh_critico = (
        len(termos_criticos_encontrados) > 0
        or (
            grau_consolidacao in ("Divergente", "Emergente")
            and forca_contra_tese == "Alta"
        )
        or impacto_financeiro_estimado > 50_000_000
    )

    if eh_critico:
        partes: list[str] = []
        if termos_criticos_encontrados:
            partes.append(
                f"Termos de risco fiscal detectados: {', '.join(termos_criticos_encontrados[:3])}"
            )
        if grau_consolidacao in ("Divergente", "Emergente") and forca_contra_tese == "Alta":
            partes.append(f"Grau {grau_consolidacao} com força de contra-tese Alta")
        if impacto_financeiro_estimado > 50_000_000:
            partes.append("Impacto estimado > R$ 50M")

        impacto_str = (
            "> R$ 50M" if impacto_financeiro_estimado > 50_000_000 else "Risco de autuação"
        )
        return ResultadoCriticidade(
            nivel=NivelCriticidade.CRITICO,
            justificativa=" | ".join(partes),
            termos_detectados=termos_criticos_encontrados,
            impacto_estimado=impacto_str,
        )

    # ── ATENÇÃO ───────────────────────────────────────────────────────────────
    eh_atencao = (
        len(termos_atencao_encontrados) > 0
        or grau_consolidacao in ("Divergente", "Emergente")
        or (10_000_000 <= impacto_financeiro_estimado <= 50_000_000)
    )

    if eh_atencao:
        partes = []
        if termos_atencao_encontrados:
            partes.append(
                f"Adequação necessária: {', '.join(termos_atencao_encontrados[:3])}"
            )
        if grau_consolidacao in ("Divergente", "Emergente"):
            partes.append(f"Grau {grau_consolidacao}")

        impacto_str = (
            "R$ 10M–50M"
            if impacto_financeiro_estimado >= 10_000_000
            else "Impacto operacional"
        )
        return ResultadoCriticidade(
            nivel=NivelCriticidade.ATENCAO,
            justificativa=" | ".join(partes),
            termos_detectados=termos_atencao_encontrados,
            impacto_estimado=impacto_str,
        )

    # ── INFORMATIVO ───────────────────────────────────────────────────────────
    return ResultadoCriticidade(
        nivel=NivelCriticidade.INFORMATIVO,
        justificativa="Atualização normativa sem ação imediata requerida",
        termos_detectados=[],
        impacto_estimado="< R$ 1M ou sem impacto financeiro direto",
    )
