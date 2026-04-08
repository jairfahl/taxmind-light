"""
ui/components/grau_consolidacao.py — Componente Streamlit: Grau de Consolidação.

Reutilizável em todos os pontos de saída da UI.
DC v7 — Seção: Hierarquia de Fontes e Posicionamento Interpretativo.
G10: Exibição consistente do grau em todos os pontos de saída.
"""

import streamlit as st


# Configuração visual por grau
GRAU_CONFIG = {
    "Consolidada": {
        "emoji": "🟢",
        "cor_texto": "green",
        "risco_label": "Risco mínimo de contestação",
        "descricao": "Posição uniforme em legislação, doutrina e jurisprudência.",
    },
    "Majoritária": {
        "emoji": "🔵",
        "cor_texto": "blue",
        "risco_label": "Risco baixo — corrente minoritária existe",
        "descricao": "Posição predominante, mas com corrente minoritária relevante.",
    },
    "Divergente": {
        "emoji": "🟠",
        "cor_texto": "orange",
        "risco_label": "Risco moderado a alto — posições conflitantes",
        "descricao": (
            "Posições conflitantes em doutrina ou jurisprudência. "
            "Avalie o risco antes de adotar."
        ),
    },
    "Emergente": {
        "emoji": "🔴",
        "cor_texto": "red",
        "risco_label": "Risco alto — sem jurisprudência consolidada",
        "descricao": (
            "Posição nova sem jurisprudência consolidada. "
            "Requer monitoramento contínuo."
        ),
    },
}

# Mapeamento de aliases do engine → graus DC v7
_ALIAS_MAP = {
    "consolidado": "Consolidada",
    "consolidada": "Consolidada",
    "em_disputa": "Divergente",
    "divergente": "Divergente",
    "sem_precedente": "Emergente",
    "emergente": "Emergente",
    "majoritaria": "Majoritária",
    "majoritária": "Majoritária",
    "indefinido": "Emergente",
}

GRAU_DESCONHECIDO = {
    "emoji": "⚪",
    "cor_texto": "gray",
    "risco_label": "Grau não determinado",
    "descricao": "Não foi possível determinar o grau de consolidação desta posição.",
}


def _normalizar_grau(grau: str) -> str:
    """Normaliza aliases do engine para os 4 graus canônicos do DC v7."""
    return _ALIAS_MAP.get(grau.lower().strip(), grau) if grau else ""


def exibir_painel_governanca(
    grau: str,
    forca_contra_tese: str = "",
    risco: str = "",
    scoring_confianca: str = "",
) -> None:
    """
    Exibe painel completo de governança da análise:
    grau de consolidação + força da contra-tese + scoring + risco.

    Usar após cada análise da IA nos pontos de saída.
    """
    grau_norm = _normalizar_grau(grau)
    config = GRAU_CONFIG.get(grau_norm, GRAU_DESCONHECIDO)

    with st.container():
        st.divider()
        st.markdown("##### 📊 Governança da Análise")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                label="Grau de Consolidação",
                value=f"{config['emoji']} {grau_norm or grau or 'N/D'}",
                help=config["descricao"],
            )

        with col2:
            if forca_contra_tese:
                emoji_forca = {"Alta": "🔴", "Média": "🟠", "Baixa": "🟢"}.get(
                    forca_contra_tese, "⚪"
                )
                st.metric(
                    label="Força da Contra-Tese",
                    value=f"{emoji_forca} {forca_contra_tese}",
                    help="Força da corrente interpretativa contrária à posição recomendada.",
                )
            else:
                st.metric(label="Força da Contra-Tese", value="⚪ N/D")

        with col3:
            if scoring_confianca:
                _sc_norm = scoring_confianca.capitalize()
                emoji_score = {"Alto": "🟢", "Médio": "🟠", "Medio": "🟠", "Baixo": "🔴"}.get(
                    _sc_norm, "⚪"
                )
                st.metric(
                    label="Scoring de Confiança",
                    value=f"{emoji_score} {_sc_norm}",
                    help="Baseado na solidez das fontes utilizadas na análise.",
                )
            else:
                st.metric(label="Scoring de Confiança", value="⚪ N/D")

        if risco:
            st.warning(f"⚠ **Risco:** {risco}")

        st.divider()
