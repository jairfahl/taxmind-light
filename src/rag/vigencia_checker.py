"""
src/rag/vigencia_checker.py — Verificador de Vigência Legislativa (DC v7, G08).

Verifica se dispositivos citados pela IA estão vigentes na data da análise.
Cobre marcos de transição da Reforma Tributária (2026-2033) não capturados
pelo campo `vigente` (boolean) das normas — que é estático — nem pelos filtros
de data do retriever — que operam por chunk, não por marco de implementação.

Dois níveis de verificação:
  1. Nível norma-código: mapeamento dos códigos do banco → marcos canônicos RT
  2. Nível resposta: busca textual de menções a marcos específicos na resposta LLM
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# MARCOS DE VIGÊNCIA DA REFORMA TRIBUTÁRIA (2026–2033)
# ---------------------------------------------------------------------------

MARCOS_VIGENCIA_RT: dict[str, dict] = {
    "EC_132_2023": {
        "nome": "EC 132/2023",
        "vigente_desde": date(2023, 12, 21),
        "vigente_ate": None,
        "termos_busca": ["EC 132", "EC 132/2023", "Emenda Constitucional 132"],
    },
    "LC_214_2025": {
        "nome": "LC 214/2025",
        "vigente_desde": date(2025, 1, 16),
        "vigente_ate": None,
        "notas": "Implementação escalonada 2026-2033",
        "termos_busca": ["LC 214", "LC 214/2025", "Lei Complementar 214"],
    },
    "LC_227_2026": {
        "nome": "LC 227/2026 (Comitê Gestor)",
        "vigente_desde": date(2026, 1, 1),
        "vigente_ate": None,
        "termos_busca": ["LC 227", "LC 227/2026", "Lei Complementar 227", "Comitê Gestor"],
    },
    "CBS_TESTE": {
        "nome": "CBS alíquota de teste (0,9%)",
        "vigente_desde": date(2026, 1, 1),
        "vigente_ate": date(2026, 12, 31),
        "notas": "Apenas em 2026 — alíquota de teste CBS",
        "termos_busca": ["CBS", "alíquota de teste", "0,9%", "0.9%"],
    },
    "IBS_TESTE": {
        "nome": "IBS alíquota de teste (0,1%)",
        "vigente_desde": date(2026, 1, 1),
        "vigente_ate": date(2026, 12, 31),
        "notas": "Apenas em 2026 — alíquota de teste IBS",
        "termos_busca": ["IBS", "alíquota de teste", "0,1%", "0.1%"],
    },
    "CBS_PLENA": {
        "nome": "CBS alíquota plena + extinção PIS/Cofins",
        "vigente_desde": date(2027, 1, 1),
        "vigente_ate": None,
        "notas": "A partir de 2027: CBS substituiu PIS e COFINS",
        "termos_busca": ["extinção do PIS", "extinção da Cofins", "CBS plena", "alíquota cheia CBS"],
    },
    "NFE_DEBITO_CREDITO": {
        "nome": "NF-e Débito e Crédito (finalidade 5 e 6)",
        "vigente_desde": date(2026, 5, 4),
        "vigente_ate": None,
        "notas": "Obrigatória a partir de 04/05/2026 — Ajuste SINIEF 49/2025",
        "termos_busca": [
            "NF-e débito", "NF-e crédito", "finalidade 5", "finalidade 6",
            "SINIEF 49", "Ajuste SINIEF 49",
        ],
    },
    "SPLIT_PAYMENT_OBRIGATORIO": {
        "nome": "Split Payment obrigatório (implementação gradual)",
        "vigente_desde": date(2027, 1, 1),
        "vigente_ate": None,
        "notas": "Implementação gradual a partir de 2027",
        "termos_busca": [
            "split payment obrigatório", "pagamento fracionado obrigatório",
            "split payment", "pagamento fracionado",
        ],
    },
    "ICMS_ISS_EXTINCAO": {
        "nome": "Extinção ICMS e ISS",
        "vigente_desde": date(2033, 1, 1),
        "vigente_ate": None,
        "notas": "Fim da transição — ICMS e ISS extintos",
        "termos_busca": ["extinção do ICMS", "extinção do ISS", "fim da transição"],
    },
}

# Mapeamento códigos do banco → chaves MARCOS_VIGENCIA_RT
_CODIGO_BANCO_MAP: dict[str, str] = {
    "EC_132": "EC_132_2023",
    "EC132_2023": "EC_132_2023",
    "LC_214": "LC_214_2025",
    "LC214_2025": "LC_214_2025",
    "LC_227": "LC_227_2026",
    "LC227_2026": "LC_227_2026",
}


# ---------------------------------------------------------------------------
# VERIFICAÇÃO DE VIGÊNCIA
# ---------------------------------------------------------------------------

@dataclass
class AlertaVigencia:
    codigo: str
    nome: str
    status: str          # "nao_vigente_ainda" | "revogada" | "vigente" | "nao_mapeada"
    mensagem: str
    alerta: bool
    vigente_desde: Optional[str] = None
    vigente_ate: Optional[str] = None
    notas: str = ""


def verificar_vigencia_norma(
    codigo_norma: str,
    data_analise: Optional[date] = None,
) -> AlertaVigencia:
    """
    Verifica se uma norma/marco está vigente na data da análise.

    Aceita tanto chaves canônicas (EC_132_2023) quanto códigos do banco (EC_132).
    """
    if data_analise is None:
        data_analise = date.today()

    # Normalizar código
    chave = _CODIGO_BANCO_MAP.get(codigo_norma, codigo_norma)
    norma = MARCOS_VIGENCIA_RT.get(chave)

    if not norma:
        return AlertaVigencia(
            codigo=codigo_norma,
            nome=codigo_norma,
            status="nao_mapeada",
            mensagem="",
            alerta=False,
        )

    vigente_desde = norma["vigente_desde"]
    vigente_ate = norma.get("vigente_ate")

    # Ainda não vigente
    if data_analise < vigente_desde:
        return AlertaVigencia(
            codigo=chave,
            nome=norma["nome"],
            status="nao_vigente_ainda",
            mensagem=(
                f"⚠ '{norma['nome']}' não estava vigente em {data_analise} "
                f"(data do cenário consultado). Entrou em vigor em {vigente_desde}."
            ),
            alerta=True,
            vigente_desde=vigente_desde.isoformat(),
            notas=norma.get("notas", ""),
        )

    # Revogada / expirada
    if vigente_ate and data_analise > vigente_ate:
        return AlertaVigencia(
            codigo=chave,
            nome=norma["nome"],
            status="revogada",
            mensagem=(
                f"⚠ '{norma['nome']}' expirou em {vigente_ate} e não era aplicável "
                f"em {data_analise} (data do cenário consultado)."
            ),
            alerta=True,
            vigente_ate=vigente_ate.isoformat(),
            notas=norma.get("notas", ""),
        )

    # Vigente
    return AlertaVigencia(
        codigo=chave,
        nome=norma["nome"],
        status="vigente",
        mensagem="",
        alerta=False,
        vigente_desde=vigente_desde.isoformat(),
        vigente_ate=vigente_ate.isoformat() if vigente_ate else None,
        notas=norma.get("notas", ""),
    )


def verificar_vigencia_chunks(
    norma_codigos: list[str],
    data_analise: Optional[date] = None,
) -> list[AlertaVigencia]:
    """
    Verifica vigência dos códigos de norma presentes nos chunks recuperados.
    Retorna apenas alertas (alerta=True).
    """
    if data_analise is None:
        data_analise = date.today()

    alertas: list[AlertaVigencia] = []
    vistos: set[str] = set()

    for codigo in norma_codigos:
        chave = _CODIGO_BANCO_MAP.get(codigo, codigo)
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado = verificar_vigencia_norma(codigo, data_analise)
        if resultado.alerta:
            alertas.append(resultado)

    return alertas


def verificar_vigencia_resposta(
    resposta_ia: str,
    data_analise: Optional[date] = None,
) -> list[AlertaVigencia]:
    """
    Verifica vigência de marcos RT citados no texto da resposta da IA.

    Faz busca textual pelos termos de cada marco. Retorna apenas alertas.
    Ignora marcos cujos termos de busca são muito genéricos (< 6 chars).
    """
    if data_analise is None:
        data_analise = date.today()

    alertas: list[AlertaVigencia] = []
    vistos: set[str] = set()
    resposta_lower = resposta_ia.lower()

    for chave, norma in MARCOS_VIGENCIA_RT.items():
        if chave in vistos:
            continue
        termos = norma.get("termos_busca", [norma["nome"]])
        encontrada = any(
            len(termo) >= 6 and termo.lower() in resposta_lower
            for termo in termos
        )
        if not encontrada:
            continue

        vistos.add(chave)
        resultado = verificar_vigencia_norma(chave, data_analise)
        if resultado.alerta:
            alertas.append(resultado)

    return alertas


def alertas_para_dict(alertas: list[AlertaVigencia]) -> list[dict]:
    """Converte lista de AlertaVigencia para lista de dicts (JSON-safe)."""
    return [
        {
            "codigo": a.codigo,
            "nome": a.nome,
            "status": a.status,
            "mensagem": a.mensagem,
            "alerta": a.alerta,
            "vigente_desde": a.vigente_desde,
            "vigente_ate": a.vigente_ate,
            "notas": a.notas,
        }
        for a in alertas
    ]
