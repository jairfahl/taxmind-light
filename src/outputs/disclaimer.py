"""
src/outputs/disclaimer.py — Disclaimer obrigatório do Tribus-AI.
DC v7, Seção: Rastreabilidade, Legal Hold e Disclaimer.

"Este disclaimer é obrigatório e não pode ser removido pelo usuário."
Renderizado por código — nunca delegado ao conteúdo gerado pela IA.
"""

from __future__ import annotations

# ── DISCLAIMER PADRÃO (DC v7) ─────────────────────────────────────────────────
DISCLAIMER_TEXTO = (
    "Esta análise é gerada por sistema de inteligência artificial com base "
    "na legislação vigente. Não constitui parecer jurídico ou contábil. "
    "A decisão final é responsabilidade do profissional competente."
)

# Versão compacta para uso inline
DISCLAIMER_COMPACTO = (
    "IA com base na legislação vigente · Não constitui parecer jurídico · "
    "Decisão final: responsabilidade do profissional"
)

# Versão para dossiês (mais formal)
DISCLAIMER_DOSSIE = (
    "AVISO LEGAL: Esta análise é gerada por sistema de inteligência artificial "
    "(Orbis.tax) com base na legislação tributária vigente na data da análise. "
    "Não constitui parecer jurídico, contábil ou consultoria tributária formal. "
    "A adoção de qualquer posição tributária é responsabilidade exclusiva do "
    "profissional competente e da organização. Recomenda-se validação com "
    "assessoria jurídica especializada para posições de alto risco."
)

# Termos mínimos para validação de presença
_TERMOS_OBRIGATORIOS = [
    "não constitui parecer",
    "responsabilidade do profissional",
    "inteligência artificial",
]


def obter_disclaimer(modo: str = "padrao") -> str:
    """
    Retorna o disclaimer conforme o modo.

    Args:
        modo: 'padrao' | 'compacto' | 'dossie'
    """
    return {
        "padrao":   DISCLAIMER_TEXTO,
        "compacto": DISCLAIMER_COMPACTO,
        "dossie":   DISCLAIMER_DOSSIE,
    }.get(modo, DISCLAIMER_TEXTO)


def validar_disclaimer_presente(texto: str) -> bool:
    """
    Verifica se o disclaimer (ou parte dele) está presente no texto.
    Usado para garantir que a IA não removeu o disclaimer da resposta.
    """
    texto_lower = texto.lower()
    return any(termo in texto_lower for termo in _TERMOS_OBRIGATORIOS)


def render_disclaimer_streamlit(modo: str = "padrao") -> None:
    """
    Renderiza o disclaimer obrigatório na UI Streamlit.
    SEMPRE usar esta função — nunca renderizar disclaimer via conteúdo gerado pela IA.
    """
    import streamlit as st

    texto = obter_disclaimer(modo)

    if modo == "compacto":
        st.caption(f"*{texto}*")
    else:
        st.divider()
        st.caption(f"⚠️ **Aviso legal:** {texto}")
