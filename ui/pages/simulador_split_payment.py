"""
ui/pages/simulador_split_payment.py — MP-05 Simulador de Impacto do Split Payment no Caixa.

Renderiza comparativo das 3 modalidades de split payment (LC 214/2025).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.simuladores.split_payment import (
    CenarioSplitPayment,
    formatar_brl,
    simular_split_payment,
)


def render_simulador_split_payment() -> None:
    st.header("Simulador de Split Payment — MP-05")
    st.caption(
        "Projeta o impacto do split payment no capital de giro e no custo financeiro, "
        "comparando as 3 modalidades previstas na LC 214/2025."
    )

    with st.expander("O que é o split payment?", expanded=False):
        st.markdown(
            "Com o split payment, o tributo (IBS+CBS) é retido automaticamente "
            "na liquidação financeira — o vendedor recebe apenas o valor líquido. "
            "O *float* tributário que antes financiava capital de giro desaparece.\n\n"
            "**3 modalidades (LC 214/2025):**\n"
            "- **Inteligente (art. 32):** compensação de créditos em tempo real — menor impacto\n"
            "- **Simplificado (art. 33):** percentual fixo retido, ajuste mensal — impacto médio\n"
            "- **Contingência (art. 32, §4º):** retenção integral, ajuste em 3 dias úteis — maior impacto"
        )

    st.divider()

    with st.form("form_split"):
        col1, col2 = st.columns(2)

        with col1:
            faturamento = st.number_input(
                "Faturamento Mensal (R$)",
                min_value=100_000.0,
                max_value=1_000_000_000.0,
                value=5_000_000.0,
                step=100_000.0,
                format="%.0f",
            )
            pct_prazo_int = st.slider(
                "% Vendas a Prazo",
                min_value=0,
                max_value=100,
                value=60,
                help="Percentual do faturamento com recebimento a prazo.",
            )
            pct_prazo = pct_prazo_int / 100.0
            pct_vista = 1.0 - pct_prazo

            prazo_medio = st.number_input(
                "Prazo Médio de Recebimento (dias)",
                min_value=1,
                max_value=360,
                value=30,
            )

        with col2:
            taxa_captacao = st.number_input(
                "Taxa de Captação Mensal (%)",
                min_value=0.1,
                max_value=10.0,
                value=2.0,
                step=0.1,
                help="Custo do dinheiro para a empresa (CDI, capital de giro bancário).",
            ) / 100.0

            pct_inadimplencia = st.slider(
                "% Inadimplência",
                min_value=0,
                max_value=20,
                value=2,
            ) / 100.0

            pct_creditos = st.slider(
                "% Aquisições com direito a crédito CBS/IBS",
                min_value=0,
                max_value=100,
                value=60,
                help="Usado no cálculo do split inteligente (compensação em tempo real).",
            ) / 100.0

        submitted = st.form_submit_button("Simular", type="primary", use_container_width=True)

    if not submitted:
        st.info("Preencha os parâmetros e clique em **Simular** para ver os resultados.")
        return

    cenario = CenarioSplitPayment(
        faturamento_mensal=faturamento,
        pct_vista=pct_vista,
        pct_prazo=pct_prazo,
        prazo_medio_dias=int(prazo_medio),
        taxa_captacao_am=taxa_captacao,
        pct_inadimplencia=pct_inadimplencia,
        pct_creditos=pct_creditos,
    )

    resultado = simular_split_payment(cenario)

    st.divider()
    st.subheader("Comparativo das 3 Modalidades")

    # Tabela resumo
    rows = []
    for m in resultado.modalidades:
        rows.append({
            "Modalidade": m.nome_completo,
            "Base Legal": m.base_legal,
            "Tributo Retido/mês": formatar_brl(m.tributo_retido_mensal),
            "Custo Financeiro/mês": formatar_brl(m.custo_financeiro_mensal),
            "Custo Financeiro/ano": formatar_brl(m.custo_financeiro_anual),
            "Impacto na Margem": f"{m.impacto_margem_pct:.2%}",
            "Capital de Giro Adicional": formatar_brl(m.capital_giro_adicional),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Métricas de destaque
    inteligente = next(m for m in resultado.modalidades if m.modalidade == "inteligente")
    contingencia = next(m for m in resultado.modalidades if m.modalidade == "contingencia")

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Custo Anual — Inteligente",
        formatar_brl(inteligente.custo_financeiro_anual),
        help="Menor impacto — maior complexidade operacional.",
    )
    col2.metric(
        "Custo Anual — Contingência",
        formatar_brl(contingencia.custo_financeiro_anual),
        help="Maior impacto — modalidade para situações excepcionais.",
    )
    diferenca = contingencia.custo_financeiro_anual - inteligente.custo_financeiro_anual
    col3.metric(
        "Diferença Anual",
        formatar_brl(diferenca),
        help="Economia potencial ao migrar de contingência para inteligente.",
    )

    # Recomendação
    st.info(resultado.recomendacao)

    # Gráfico comparativo
    chart_data = pd.DataFrame(
        {
            "Modalidade": [m.nome_completo for m in resultado.modalidades],
            "Custo anual (R$)": [m.custo_financeiro_anual for m in resultado.modalidades],
        }
    ).set_index("Modalidade")
    st.bar_chart(chart_data)

    # Ressalvas
    with st.expander("Ressalvas e limitações"):
        for m in resultado.modalidades:
            st.caption(f"**{m.nome_completo}:**")
            for r in m.ressalvas:
                st.caption(f"  • {r}")
        st.caption(
            "Esta simulação usa estimativas de alíquotas IBS+CBS para 2027+. "
            "Valores sujeitos a regulamentação do CGIBS. "
            "Não constitui cálculo fiscal para escrituração."
        )
