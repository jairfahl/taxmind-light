"""
ui/pages/painel_aprendizado.py — Painel de Aprendizado Institucional (C6, G24).
"""

from __future__ import annotations

import streamlit as st

from src.cognitive.aprendizado_institucional import (
    calcular_metricas_usuario,
    verificar_heuristicas_expiradas,
)


def render_painel_aprendizado() -> None:
    st.header("🧠 Inteligência Institucional")
    st.caption(
        "Padrões extraídos de casos encerrados. "
        "O conhecimento tributário da organização não se perde com rotatividade."
    )

    user_id = st.session_state.get("user_id")

    # Salvaguarda DC v7: verificar expiradas
    try:
        expiradas = verificar_heuristicas_expiradas(user_id)
        if expiradas > 0:
            st.warning(
                f"⚠ {expiradas} heurística(s) expiraram e foram sinalizadas para revisão. "
                "Revalide antes de usar em novas análises."
            )
    except Exception:
        pass

    try:
        metricas = calcular_metricas_usuario(user_id)
    except Exception:
        metricas = {
            "total_heuristicas": 0, "ativas": 0, "expiradas": 0,
            "divergencias": 0, "casos_ativos": 0, "casos_encerrados": 0,
        }

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Casos em Monit. (ativos)", metricas.get("casos_ativos", 0))
    col2.metric("Casos Encerrados", metricas.get("casos_encerrados", 0))
    col3.metric("Heurísticas Ativas", metricas.get("ativas", 0))
    col4.metric("Divergências Registradas", metricas.get("divergencias", 0))

    if metricas.get("casos_encerrados", 0) == 0:
        st.info(
            "Nenhum caso encerrado ainda. "
            "Encerre casos no P6 (Ciclo Pós-Decisão) para gerar heurísticas institucionais."
        )
        return

    st.divider()
    st.subheader("Salvaguardas Ativas (DC v7)")
    st.caption(
        "Toda heurística tem prazo de validade de 6 meses. "
        "Heurísticas expiradas são sinalizadas automaticamente."
    )

    col1, col2 = st.columns(2)
    total = metricas.get("total_heuristicas", 0)
    ativas = metricas.get("ativas", 0)
    pct_ativas = ativas / total if total > 0 else 0
    with col1:
        st.metric("Heurísticas Ativas", f"{ativas}/{total}", f"{pct_ativas:.0%}")
    with col2:
        exp = metricas.get("expiradas", 0)
        st.metric(
            "Expiradas (revalidar)", exp,
            delta_color="inverse" if exp > 0 else "normal",
        )
