"""
ui/components/saidas_stakeholder.py — Componente UI para Saídas por Stakeholder (C3, G16).

Exibe os resumos por público-alvo gerados pelo stakeholders_inline após cada análise.
"""

from __future__ import annotations

import streamlit as st


def exibir_saidas_stakeholder(saidas: list[dict]) -> None:
    """
    Exibe cards expansíveis com resumos por stakeholder.

    Args:
        saidas: lista de dicts retornada por resumos_para_dict()
                (campos: stakeholder_id, label, emoji, foco, resumo, gerado_com_sucesso)
    """
    if not saidas:
        return

    st.markdown("---")
    st.markdown("#### 👥 Resumos por Público-Alvo")

    cols_por_linha = 3
    linhas = [saidas[i:i + cols_por_linha] for i in range(0, len(saidas), cols_por_linha)]

    for linha in linhas:
        cols = st.columns(len(linha))
        for col, item in zip(cols, linha):
            with col:
                if not item.get("gerado_com_sucesso", True):
                    with st.expander(f"{item['emoji']} {item['label']}"):
                        st.warning("Resumo não disponível nesta análise.")
                    continue

                with st.expander(f"{item['emoji']} {item['label']}"):
                    st.caption(f"Foco: {item['foco']}")
                    resumo = item.get("resumo", "")
                    if resumo:
                        for linha_bullet in resumo.splitlines():
                            if linha_bullet.strip():
                                st.markdown(linha_bullet)
                    else:
                        st.info("Resumo vazio.")
