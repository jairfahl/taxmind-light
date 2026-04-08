"""
ui/pages/simulador_carga.py — MP-01 Simulador Comparativo de Carga RT (G18).

Renderiza o painel Streamlit do simulador comparativo de carga tributária
regime atual vs. CBS+IBS ao longo da transição 2026-2033.
"""

from __future__ import annotations

import streamlit as st

from src.simuladores.carga_rt import (
    ANOS_SIMULADOS,
    REGIMES_TRIBUTARIOS,
    TIPOS_OPERACAO,
    CenarioOperacional,
    formatar_brl,
    simular_carga,
    simular_multiplos_anos,
)


# ---------------------------------------------------------------------------
# Labels amigáveis
# ---------------------------------------------------------------------------

_REGIME_LABELS = {
    "lucro_real": "Lucro Real",
    "lucro_presumido": "Lucro Presumido",
    "simples_nacional": "Simples Nacional",
}

_TIPO_LABELS = {
    "misto": "Misto (mercadorias + serviços)",
    "so_mercadorias": "Somente mercadorias",
    "so_servicos": "Somente serviços",
}


def render_simulador_carga() -> None:
    """Renderiza o simulador comparativo de carga RT na UI Streamlit."""
    st.header("Simulador Comparativo de Carga RT")
    st.caption(
        "Estimativa de carga tributária — regime atual (PIS/COFINS + ICMS/ISS) "
        "vs. novo (CBS + IBS) ao longo da transição 2026-2033. "
        "Baseado em LC 214/2025 e premissas RFB 2025. Não substitui planejamento contábil."
    )

    st.divider()

    # ------------------------------------------------------------------
    # Formulário de entrada
    # ------------------------------------------------------------------
    with st.form("simulador_form"):
        col1, col2 = st.columns(2)

        with col1:
            faturamento = st.number_input(
                "Faturamento anual bruto (R$)",
                min_value=1_000.0,
                max_value=10_000_000_000.0,
                value=5_000_000.0,
                step=100_000.0,
                format="%.2f",
                help="Receita bruta anual estimada.",
            )

            regime = st.selectbox(
                "Regime tributário",
                options=REGIMES_TRIBUTARIOS,
                format_func=lambda x: _REGIME_LABELS.get(x, x),
                index=0,
            )

            tipo = st.selectbox(
                "Tipo de operação",
                options=TIPOS_OPERACAO,
                format_func=lambda x: _TIPO_LABELS.get(x, x),
                index=0,
            )

        with col2:
            pct_exportacao = st.slider(
                "% de exportação (imune a CBS/IBS)",
                min_value=0,
                max_value=100,
                value=0,
                step=5,
                help="Faturamento com destino exterior — imune a IBS e CBS.",
            )

            pct_credito = st.slider(
                "% de crédito CBS/IBS aproveitável",
                min_value=0,
                max_value=100,
                value=80,
                step=5,
                help=(
                    "Estimativa de aproveitamento de créditos no novo regime. "
                    "100% = cadeia totalmente não-cumulativa."
                ),
            )

            ano_base = st.selectbox(
                "Ano de referência (comparação pontual)",
                options=ANOS_SIMULADOS,
                index=ANOS_SIMULADOS.index(2026),
            )

        submitted = st.form_submit_button("Calcular", type="primary", use_container_width=True)

    if not submitted:
        st.info("Preencha os parâmetros e clique em **Calcular** para ver os resultados.")
        return

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------
    try:
        cenario = CenarioOperacional(
            faturamento_anual=faturamento,
            regime_tributario=regime,
            tipo_operacao=tipo,
            percentual_exportacao=pct_exportacao / 100.0,
            percentual_credito_novo=pct_credito / 100.0,
        )
    except ValueError as exc:
        st.error(f"Parâmetro inválido: {exc}")
        return

    atual, novo = simular_carga(cenario, ano_base)
    projecao = simular_multiplos_anos(cenario)

    # ------------------------------------------------------------------
    # Resultado pontual
    # ------------------------------------------------------------------
    st.subheader(f"Comparativo {ano_base}")

    m1, m2, m3 = st.columns(3)

    variacao = novo.carga_liquida - atual.carga_liquida
    variacao_pct = variacao / atual.carga_liquida if atual.carga_liquida else 0.0

    m1.metric(
        "Carga líquida — Regime atual",
        formatar_brl(atual.carga_liquida),
        help=f"Alíquota efetiva: {atual.aliquota_efetiva:.1%}",
    )
    m2.metric(
        f"Carga líquida — CBS+IBS ({ano_base})",
        formatar_brl(novo.carga_liquida),
        delta=f"{variacao_pct:+.1%}",
        delta_color="inverse",
        help=f"Alíquota efetiva: {novo.aliquota_efetiva:.1%}",
    )
    m3.metric(
        "Variação absoluta",
        formatar_brl(variacao),
        delta=formatar_brl(variacao),
        delta_color="inverse",
    )

    # Semáforo de impacto
    if variacao_pct < -0.05:
        st.success(f"**Cenário favorável:** redução de {abs(variacao_pct):.1%} na carga tributária estimada.")
    elif variacao_pct > 0.05:
        st.warning(f"**Atenção:** aumento de {variacao_pct:.1%} na carga tributária estimada.")
    else:
        st.info("Variação inferior a 5% — impacto neutro neste cenário.")

    # ------------------------------------------------------------------
    # Detalhamento dos componentes
    # ------------------------------------------------------------------
    with st.expander("Ver detalhes dos componentes — regime atual"):
        d = atual.detalhes
        cols = st.columns(3)
        cols[0].metric("PIS/COFINS", formatar_brl(d.get("piscofins", 0)))
        cols[1].metric("ICMS", formatar_brl(d.get("icms", 0)))
        cols[2].metric("ISS", formatar_brl(d.get("iss", 0)))
        st.caption(
            f"Crédito PIS/COFINS: {formatar_brl(d.get('credito_piscofins', 0))} | "
            f"Crédito ICMS: {formatar_brl(d.get('credito_icms', 0))}"
        )

    with st.expander(f"Ver detalhes dos componentes — CBS+IBS ({ano_base})"):
        d = novo.detalhes
        cols = st.columns(3)
        cols[0].metric(f"CBS ({d.get('aliquota_cbs', 0):.2f}%)", formatar_brl(d.get("cbs", 0)))
        cols[1].metric(f"IBS ({d.get('aliquota_ibs', 0):.2f}%)", formatar_brl(d.get("ibs", 0)))
        cols[2].metric("ICMS/ISS residual", formatar_brl(d.get("icms_residual", 0) + d.get("iss_residual", 0)))
        st.caption(
            f"Crédito CBS: {formatar_brl(d.get('credito_cbs', 0))} | "
            f"Crédito IBS: {formatar_brl(d.get('credito_ibs', 0))}"
        )

    # ------------------------------------------------------------------
    # Projeção plurianual
    # ------------------------------------------------------------------
    st.subheader("Projeção 2024-2033")

    # Tabela resumo
    import pandas as pd

    rows = []
    for p in projecao:
        rows.append({
            "Ano": str(p["ano"]),
            "Carga atual (R$)": formatar_brl(p["carga_liquida_atual"]),
            "Carga CBS+IBS (R$)": formatar_brl(p["carga_liquida_nova"]),
            "Variação": f"{p['variacao_pct']:+.1%}",
            "Regime": p["regime_novo"].replace("_", " ").title(),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Gráfico de linhas (barras)
    chart_data = pd.DataFrame(
        {
            "Ano": [str(p["ano"]) for p in projecao],
            "Atual": [p["carga_liquida_atual"] for p in projecao],
            "CBS+IBS": [p["carga_liquida_nova"] for p in projecao],
        }
    ).set_index("Ano")

    st.bar_chart(chart_data)

    # ------------------------------------------------------------------
    # Aviso legal
    # ------------------------------------------------------------------
    st.divider()
    st.caption(
        "⚠️ **Aviso:** Simulação baseada em alíquotas estimadas (LC 214/2025, premissas RFB 2025). "
        "Créditos reais dependem de cadeia produtiva específica, atos complementares e regulamentação estadual do IBS. "
        "Consulte seu contador antes de tomar decisões de planejamento."
    )
