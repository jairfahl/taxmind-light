"""
ui/components/badge_criticidade.py — Badge de Criticidade (DC v7, G17).
Exibir ANTES do painel de governança (A6) em toda análise.
"""

from __future__ import annotations

import streamlit as st

from src.cognitive.criticidade import (
    CRITICIDADE_CONFIG,
    NivelCriticidade,
    ResultadoCriticidade,
)


def exibir_badge_criticidade(resultado: ResultadoCriticidade) -> None:
    """
    Badge visual diferenciado por nível de criticidade.
    - CRÍTICO   → st.error()   vermelho  (IMEDIATA)
    - ATENÇÃO   → st.warning() amarelo   (PRAZO DEFINIDO)
    - INFORMATIVO → st.info()  azul      (SEM URGÊNCIA)
    """
    config = CRITICIDADE_CONFIG[resultado.nivel]

    if resultado.nivel == NivelCriticidade.CRITICO:
        st.error(
            f"{config['emoji']} **{config['label'].upper()} — {config['urgencia']}**  \n"
            f"{config['descricao']}  \n"
            f"*{resultado.justificativa}*"
        )
    elif resultado.nivel == NivelCriticidade.ATENCAO:
        st.warning(
            f"{config['emoji']} **{config['label']} — {config['urgencia']}**  \n"
            f"{config['descricao']}  \n"
            f"*{resultado.justificativa}*"
        )
    else:
        st.info(
            f"{config['emoji']} **{config['label']}**  \n"
            f"{config['descricao']}"
        )


def exibir_badge_compacto(nivel: str) -> None:
    """Versão inline compacta — caption colorido."""
    try:
        nivel_enum = NivelCriticidade(nivel)
        config = CRITICIDADE_CONFIG[nivel_enum]
        st.caption(f"{config['emoji']} **{config['label']}** — {config['descricao']}")
    except ValueError:
        st.caption("⚪ Criticidade não determinada")
