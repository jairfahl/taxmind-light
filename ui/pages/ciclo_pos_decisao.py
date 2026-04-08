"""
ui/pages/ciclo_pos_decisao.py — P6 Ciclo Pós-Decisão.

Exibe decisões ativas em monitoramento, alertas de mudança legislativa
e formulário de registro de resultado real.
"""

from __future__ import annotations

import streamlit as st

from src.cognitive.monitoramento_p6 import (
    listar_decisoes_ativas,
    registrar_resultado_real,
)


def render_ciclo_pos_decisao() -> None:
    st.header("Ciclo Pós-Decisão — P6")
    st.caption(
        "Monitora mudanças legislativas que afetam decisões registradas. "
        "Registre o resultado real para fechar o loop de aprendizado."
    )

    user_id = st.session_state.get("user_id")

    try:
        decisoes = listar_decisoes_ativas(user_id)
    except Exception as exc:
        st.error(f"Erro ao carregar decisões: {exc}")
        return

    if not decisoes:
        st.info(
            "Nenhuma decisão ativa em monitoramento. "
            "Decisões registradas no P5 aparecem automaticamente aqui após ativação do P6."
        )
        return

    em_revisao = [d for d in decisoes if d["status"] == "revisao_pendente"]
    ativas = [d for d in decisoes if d["status"] == "ativo"]

    # ------------------------------------------------------------------
    # Alertas prioritários — revisão pendente
    # ------------------------------------------------------------------
    if em_revisao:
        st.error(
            f"{len(em_revisao)} decisão(ões) requer(em) revisão — "
            "mudanças legislativas detectadas."
        )
        for d in em_revisao:
            query_preview = (d["query"] or "(sem descrição)")[:80]
            with st.expander(f"REVISÃO PENDENTE — {query_preview}...", expanded=True):
                st.warning(
                    "Novas normas adicionadas à base podem ter impactado as premissas "
                    "desta decisão. Revise antes de continuar."
                )
                if d.get("premissas_invalidas"):
                    st.markdown("**Premissas potencialmente afetadas:**")
                    for p in d["premissas_invalidas"]:
                        st.caption(f"• {p}")

                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button(
                        "Premissas ainda válidas",
                        key=f"ok_{d['id']}",
                    ):
                        st.success("Confirmado. Monitoramento continua ativo.")
                with cc2:
                    if st.button(
                        "Reabrir análise",
                        key=f"reabrir_{d['id']}",
                    ):
                        st.info("Crie uma nova consulta com as premissas atualizadas.")

    st.divider()

    # ------------------------------------------------------------------
    # Decisões ativas sem alerta
    # ------------------------------------------------------------------
    st.subheader(f"Decisões em Monitoramento ({len(ativas)})")

    if not ativas:
        st.caption("Nenhuma decisão ativa no momento.")
        return

    for d in ativas:
        data_str = (
            d["criado_em"].strftime("%d/%m/%Y")
            if d.get("criado_em")
            else "—"
        )
        query_preview = (d["query"] or "(sem descrição)")[:80]
        with st.expander(f"{data_str} — {query_preview}"):

            st.markdown("**Registrar resultado real (P6):**")
            st.caption(
                "O que efetivamente aconteceu após a decisão? "
                "Registrar o resultado fecha o loop e alimenta o aprendizado institucional."
            )
            resultado = st.text_area(
                "Resultado real observado",
                placeholder=(
                    "Ex: Posição adotada foi aceita pelo Fisco. "
                    "Créditos aproveitados conforme planejado. "
                    "Não houve questionamento."
                ),
                key=f"resultado_{d['id']}",
                height=100,
            )
            if st.button(
                "Registrar resultado e encerrar monitoramento",
                key=f"encerrar_{d['id']}",
            ):
                if resultado.strip():
                    try:
                        registrar_resultado_real(str(d["id"]), resultado)
                        st.success("Resultado registrado. Caso encerrado.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Erro ao registrar resultado: {exc}")
                else:
                    st.error("Descreva o resultado antes de encerrar.")
