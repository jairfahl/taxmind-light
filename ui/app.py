"""
ui/app.py — Interface Streamlit para TaxMind Light.
Aba 1: Consultar · Aba 2: Carregar Documento · Aba 3: Protocolo P1→P9 · Aba 4: Outputs
Consome a FastAPI em http://localhost:8000.
"""

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="TaxMind Light — Reforma Tributária",
    page_icon="⚖️",
    layout="wide",
)


# --- Buscar normas disponíveis do /v1/health ---
@st.cache_data(ttl=30)
def _buscar_normas_disponiveis() -> dict[str, str]:
    """Retorna dict {nome_display: codigo} buscado dinamicamente da API."""
    try:
        hr = httpx.get(f"{API_BASE}/v1/health", timeout=3)
        normas = hr.json().get("normas", [])
        return {n["nome"]: n["codigo"] for n in normas}
    except Exception:
        # Fallback estático se API offline
        return {
            "EC 132/2023": "EC132_2023",
            "LC 214/2025": "LC214_2025",
            "LC 227/2026": "LC227_2026",
        }


# --- Sidebar ---
st.sidebar.title("⚖️ TaxMind Light")
st.sidebar.caption("Reforma Tributária · Base dinâmica de normas")

normas_disponiveis = _buscar_normas_disponiveis()

normas_sel = st.sidebar.multiselect(
    "Filtrar por norma",
    options=list(normas_disponiveis.keys()),
    default=list(normas_disponiveis.keys()),
)
norma_filter = [normas_disponiveis[n] for n in normas_sel] if normas_sel else None

top_k = st.sidebar.slider("Top-K chunks", min_value=1, max_value=5, value=3)

st.sidebar.divider()

# Health check na sidebar
try:
    hr = httpx.get(f"{API_BASE}/v1/health", timeout=3)
    hdata = hr.json()
    st.sidebar.success(
        f"API online · {hdata['chunks_total']:,} chunks · "
        f"{hdata['embeddings_total']:,} embeddings · "
        f"{len(hdata.get('normas', []))} normas"
    )
except Exception:
    st.sidebar.error("API offline — certifique-se que o servidor FastAPI está rodando")

# --- Abas ---
aba1, aba2, aba3, aba4, aba5 = st.tabs(["Consultar", "Carregar Documento", "Protocolo P1→P9", "Outputs", "Observability"])


# ===========================================================================
# ABA 1 — Consultar
# ===========================================================================
with aba1:
    st.title("TaxMind Light — Reforma Tributária")
    st.caption("Análise tributária com grounding legislativo · Sem pareceres jurídicos formais")

    query = st.text_area(
        "Sua consulta tributária",
        placeholder="Ex: Como funciona o split payment para e-commerce com plataforma digital intermediária?",
        height=100,
    )

    if st.button("Analisar", type="primary", disabled=not query.strip()):
        with st.spinner("Analisando..."):
            try:
                resp = httpx.post(
                    f"{API_BASE}/v1/analyze",
                    json={"query": query, "norma_filter": norma_filter, "top_k": top_k},
                    timeout=60,
                )
            except httpx.ConnectError:
                st.error("Não foi possível conectar à API. Verifique se o servidor FastAPI está rodando em localhost:8000.")
                st.stop()

        if resp.status_code == 400:
            err = resp.json()
            st.error("🔴 **Consulta Bloqueada**")
            st.write("**Motivos:**")
            for b in err.get("detail", {}).get("bloqueios", []):
                st.write(f"- {b}")
            st.stop()

        if resp.status_code != 200:
            st.error(f"Erro da API: {resp.status_code} — {resp.text[:300]}")
            st.stop()

        data = resp.json()
        status = data["qualidade"]["status"]
        scoring = data["scoring_confianca"]
        latencia = data["latencia_ms"]

        col1, col2, col3 = st.columns(3)
        with col1:
            if status == "verde":
                st.success("🟢 Qualidade: VERDE")
            elif status == "amarelo":
                st.warning("🟡 Qualidade: AMARELO")
            else:
                st.error("🔴 Qualidade: VERMELHO")
        with col2:
            badge = {"alto": "🟢 Alto", "medio": "🟡 Médio", "baixo": "🔴 Baixo"}.get(scoring, scoring)
            st.metric("Confiança", badge)
        with col3:
            st.metric("Latência", f"{latencia} ms")

        st.divider()

        disc = data.get("disclaimer")
        if disc:
            st.warning(f"⚠️ {disc}")

        st.subheader("Análise")
        if data["anti_alucinacao"]["bloqueado"]:
            st.error("❌ Resposta bloqueada pelo sistema anti-alucinação.")
        st.write(data["resposta"])

        grau = data["grau_consolidacao"]
        grau_icon = {"consolidado": "✅", "divergente": "⚠️", "indefinido": "❓"}.get(grau, "")
        st.caption(f"Grau de consolidação: {grau_icon} {grau.capitalize()}")

        if data["fundamento_legal"]:
            st.subheader("📋 Fundamento Legal")
            for art in data["fundamento_legal"]:
                st.write(f"- {art}")

        if data.get("contra_tese"):
            with st.expander("⚖️ Contra-tese"):
                st.write(data["contra_tese"])

        st.subheader("🔍 Verificação Anti-Alucinação")
        anti = data["anti_alucinacao"]
        ac1, ac2, ac3, ac4 = st.columns(4)
        ac1.metric("M1 Existência", "✓" if anti["m1_existencia"] else "✗")
        ac2.metric("M2 Validade", "✓" if anti["m2_validade"] else "⚠")
        ac3.metric("M3 Pertinência", "✓" if anti["m3_pertinencia"] else "✗")
        ac4.metric("M4 Consistência", "✓" if anti["m4_consistencia"] else "✗")
        if anti["flags"]:
            st.caption(f"Flags: {', '.join(anti['flags'])}")

        with st.expander(f"📄 Chunks utilizados ({len(data['chunks'])})"):
            for i, chunk in enumerate(data["chunks"], 1):
                st.markdown(
                    f"**[{i}]** `{chunk['norma_codigo']}` | "
                    f"`{chunk['artigo'] or 'artigo não identificado'}` "
                    f"| score={chunk['score_final']:.3f}"
                )
                st.text(chunk["texto"][:400] + ("..." if len(chunk["texto"]) > 400 else ""))
                if i < len(data["chunks"]):
                    st.divider()

        st.caption(f"Modelo: {data['model_id']} · Prompt: {data['prompt_version']}")


# ===========================================================================
# ABA 2 — Carregar Documento
# ===========================================================================
with aba2:
    st.title("Carregar Documento")
    st.caption("Adicione INs, Resoluções, Pareceres ou Manuais à base de conhecimento.")

    uploaded_file = st.file_uploader("Selecione o arquivo PDF", type=["pdf"])
    nome_doc = st.text_input(
        "Nome do documento",
        placeholder="Ex: IN RFB 2184/2024",
    )
    tipo_doc = st.selectbox(
        "Tipo",
        options=["IN", "Resolução", "Parecer", "Manual", "Outro"],
    )

    st.info(
        "Após ingerido, o documento estará disponível automaticamente "
        "nas consultas da Aba 1."
    )

    pode_ingerir = uploaded_file is not None and nome_doc.strip()

    if st.button("Ingerir Documento", type="primary", disabled=not pode_ingerir):
        with st.spinner(f"Processando '{nome_doc}'... (pode levar alguns minutos)"):
            try:
                resp = httpx.post(
                    f"{API_BASE}/v1/ingest/upload",
                    files={"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")},
                    data={"nome": nome_doc.strip(), "tipo": tipo_doc},
                    timeout=300,
                )
            except httpx.ConnectError:
                st.error("Não foi possível conectar à API.")
                st.stop()

        if resp.status_code == 200:
            r = resp.json()
            st.success(
                f"✅ **{r['nome']}** ingerido com sucesso — "
                f"{r['chunks']} chunks, {r['embeddings']} embeddings"
            )
            st.caption(f"Código interno: `{r['codigo']}` · norma_id={r['norma_id']}")
            # Invalidar cache de normas para que a Aba 1 atualize o multiselect
            _buscar_normas_disponiveis.clear()
            st.info("Recarregue a página para ver o novo documento no filtro da Aba 1.")
        else:
            try:
                detalhe = resp.json().get("detail", resp.text[:200])
            except Exception:
                detalhe = resp.text[:200]
            st.error(f"❌ Erro ao ingerir documento: {detalhe}")


# ===========================================================================
# ABA 3 — Protocolo P1→P9
# ===========================================================================
PASSO_NOME = {
    1: "P1 · Registrar",
    2: "P2 · Contextualizar",
    3: "P3 · Estruturar",
    4: "P4 · Analisar",
    5: "P5 · Formular Hipótese",
    6: "P6 · Recomendar",
    7: "P7 · Decidir",
    8: "P8 · Monitorar",
    9: "P9 · Aprender",
}
STATUS_BADGE = {
    "rascunho": "🔵",
    "em_analise": "🟡",
    "aguardando_hipotese": "🟠",
    "decidido": "🟢",
    "em_monitoramento": "🔵",
    "aprendizado_extraido": "✅",
}

with aba3:
    st.title("Protocolo de Decisão Tributária P1→P9")
    st.caption(
        "Registre, analise e documente decisões tributárias com rastreabilidade completa. "
        "P5 (hipótese do gestor) deve ser concluído antes de ver a recomendação da IA (P6)."
    )

    # ------ Seção: Criar novo caso ------
    with st.expander("➕ Criar Novo Caso", expanded=False):
        with st.form("form_criar_caso"):
            titulo_caso = st.text_input("Título do caso (mín. 10 chars)", placeholder="Ex: Apuração CBS — CNPJ 12.345.678/0001-90")
            descricao_caso = st.text_area("Descrição", placeholder="Descreva o contexto do caso...", height=80)
            contexto_fiscal = st.text_input("Contexto fiscal", placeholder="Ex: Empresa de serviços de TI — Lucro Presumido")
            submitted_criar = st.form_submit_button("Criar Caso", type="primary")

        if submitted_criar:
            if not titulo_caso.strip() or len(titulo_caso.strip()) < 10:
                st.error("Título deve ter no mínimo 10 caracteres.")
            elif not descricao_caso.strip() or not contexto_fiscal.strip():
                st.error("Preencha todos os campos.")
            else:
                try:
                    r = httpx.post(
                        f"{API_BASE}/v1/cases",
                        json={"titulo": titulo_caso.strip(), "descricao": descricao_caso.strip(),
                              "contexto_fiscal": contexto_fiscal.strip()},
                        timeout=10,
                    )
                    if r.status_code == 201:
                        d = r.json()
                        st.success(f"✅ Caso criado — ID: **{d['case_id']}** · Status: {d['status']}")
                        st.info(f"Guarde o Case ID: `{d['case_id']}` para continuar o protocolo.")
                    else:
                        st.error(f"Erro: {r.json().get('detail', r.text[:200])}")
                except httpx.ConnectError:
                    st.error("API offline.")

    st.divider()

    # ------ Seção: Consultar estado do caso ------
    st.subheader("Consultar / Avançar Caso")
    case_id_input = st.number_input("Case ID", min_value=1, step=1, value=1)

    col_load, col_refresh = st.columns([1, 4])
    with col_load:
        load_case = st.button("Carregar Caso")

    if load_case or st.session_state.get("_proto_case_id") == case_id_input:
        st.session_state["_proto_case_id"] = case_id_input
        try:
            r = httpx.get(f"{API_BASE}/v1/cases/{case_id_input}", timeout=10)
        except httpx.ConnectError:
            st.error("API offline.")
            st.stop()

        if r.status_code == 404:
            st.warning(f"Caso {case_id_input} não encontrado.")
        elif r.status_code != 200:
            st.error(f"Erro: {r.text[:200]}")
        else:
            caso = r.json()
            passo_atual = caso["passo_atual"]
            status = caso["status"]
            badge = STATUS_BADGE.get(status, "")

            st.markdown(f"### {badge} {caso['titulo']}")
            st.caption(f"Passo atual: **{PASSO_NOME.get(passo_atual, str(passo_atual))}** · Status: `{status}`")

            # Progresso visual
            progress_val = (passo_atual - 1) / 8.0
            st.progress(progress_val, text=f"Passo {passo_atual}/9")

            # Histórico colapsado
            with st.expander("📜 Histórico de transições"):
                for h in caso["historico"]:
                    st.caption(
                        f"`{h['created_at'][:19]}` — P{h['passo_de'] or '?'} → P{h['passo_para']} "
                        f"({h['status_de'] or 'início'} → {h['status_para']}) — {h['motivo'] or ''}"
                    )

            st.divider()

            # ------ Formulário de avanço por passo ------
            st.subheader(f"Submeter dados — {PASSO_NOME.get(passo_atual, str(passo_atual))}")

            with st.form(f"form_passo_{passo_atual}"):
                dados_passo = {}

                if passo_atual == 1:
                    dados_passo["titulo"] = st.text_input("Título", value=caso["titulo"])
                    dados_passo["descricao"] = st.text_area("Descrição")
                    dados_passo["contexto_fiscal"] = st.text_input("Contexto fiscal")

                elif passo_atual == 2:
                    premissa1 = st.text_input("Premissa 1")
                    premissa2 = st.text_input("Premissa 2")
                    premissa3 = st.text_input("Premissa 3 (opcional)")
                    dados_passo["premissas"] = [p for p in [premissa1, premissa2, premissa3] if p.strip()]
                    dados_passo["periodo_fiscal"] = st.text_input("Período fiscal", placeholder="Ex: 2025-01 a 2025-12")

                elif passo_atual == 3:
                    risco1 = st.text_input("Risco identificado 1")
                    risco2 = st.text_input("Risco identificado 2 (opcional)")
                    dados_passo["riscos"] = [r for r in [risco1, risco2] if r.strip()]
                    dados_passo["dados_qualidade"] = st.text_area("Qualidade dos dados", placeholder="Descreva a qualidade dos dados disponíveis...")

                elif passo_atual == 4:
                    dados_passo["query_analise"] = st.text_area(
                        "Query para análise cognitiva",
                        placeholder="Ex: Qual a alíquota do IBS para serviços de TI sob Lucro Presumido?",
                        height=80,
                    )
                    dados_passo["analise_result"] = st.text_area(
                        "Resultado da análise (cole o output do /v1/analyze)",
                        height=120,
                    )

                elif passo_atual == 5:
                    st.info("Esta é a hipótese do gestor — registre ANTES de ver a recomendação da IA (P6).")
                    dados_passo["hipotese_gestor"] = st.text_area(
                        "Sua hipótese de decisão",
                        placeholder="Descreva sua hipótese independente sobre como resolver este caso...",
                        height=120,
                    )

                elif passo_atual == 6:
                    dados_passo["recomendacao"] = st.text_area(
                        "Recomendação baseada na análise da IA",
                        height=120,
                    )

                elif passo_atual == 7:
                    st.warning("⚠️ A decisão final será comparada com a recomendação da IA para verificação de carimbo.")
                    dados_passo["decisao_final"] = st.text_area(
                        "Decisão final do gestor",
                        height=120,
                    )
                    dados_passo["decisor"] = st.text_input("Nome do decisor responsável")

                elif passo_atual == 8:
                    dados_passo["resultado_real"] = st.text_area("Resultado real observado", height=80)
                    dados_passo["data_revisao"] = st.text_input("Data de revisão", placeholder="YYYY-MM-DD")

                elif passo_atual == 9:
                    dados_passo["padrao_extraido"] = st.text_area(
                        "Padrão extraído para aprendizado futuro",
                        placeholder="Descreva o padrão aprendido com este caso...",
                        height=100,
                    )

                col_av, col_vo = st.columns([2, 1])
                with col_av:
                    btn_avancar = st.form_submit_button("Avançar →", type="primary")
                with col_vo:
                    btn_voltar = st.form_submit_button("← Voltar")

            if btn_avancar or btn_voltar:
                acao = "voltar" if btn_voltar else "avancar"
                try:
                    r2 = httpx.post(
                        f"{API_BASE}/v1/cases/{case_id_input}/steps/{passo_atual}",
                        json={"dados": dados_passo, "acao": acao},
                        timeout=120,
                    )
                except httpx.ConnectError:
                    st.error("API offline.")
                    st.stop()

                if r2.status_code == 422:
                    st.error(f"Erro de validação: {r2.json().get('detail', '')}")
                elif r2.status_code != 200:
                    st.error(f"Erro {r2.status_code}: {r2.text[:200]}")
                else:
                    d2 = r2.json()
                    novo_passo = d2["passo"]
                    st.success(f"✅ Movido para {PASSO_NOME.get(novo_passo, str(novo_passo))}")

                    # Exibir alerta de carimbo se presente
                    carimbo = d2.get("carimbo")
                    if carimbo and carimbo.get("alerta"):
                        st.warning(f"🔔 **Alerta Carimbo** — {carimbo['mensagem']}")
                        st.caption(f"Score de similaridade: {carimbo['score_similaridade']:.0%} · alert_id={carimbo['alert_id']}")

                        with st.form("form_confirmar_carimbo"):
                            justificativa = st.text_area(
                                "Justificativa (mín. 20 chars) — confirme que esta é sua posição independente",
                                height=80,
                            )
                            if st.form_submit_button("Confirmar Decisão Independente"):
                                try:
                                    rc = httpx.post(
                                        f"{API_BASE}/v1/cases/{case_id_input}/carimbo/confirmar",
                                        json={"alert_id": carimbo["alert_id"], "justificativa": justificativa},
                                        timeout=10,
                                    )
                                    if rc.status_code == 200:
                                        st.success("Carimbo confirmado com justificativa registrada.")
                                    else:
                                        st.error(rc.json().get("detail", rc.text[:200]))
                                except httpx.ConnectError:
                                    st.error("API offline.")

                    # Forçar recarga do caso
                    st.session_state["_proto_case_id"] = case_id_input
                    st.rerun()


# ===========================================================================
# ABA 4 — Outputs Acionáveis
# ===========================================================================
CLASSE_BADGE = {
    "alerta":                  ("🔔", "#FF6B35"),
    "nota_trabalho":           ("📝", "#4A90D9"),
    "recomendacao_formal":     ("📋", "#2ECC71"),
    "dossie_decisao":          ("📁", "#9B59B6"),
    "material_compartilhavel": ("📤", "#F39C12"),
}
STATUS_COR = {
    "rascunho": "🔵",
    "gerado":   "🟡",
    "aprovado": "🟢",
    "publicado": "✅",
    "revogado": "🔴",
}
ESTRELAS = {1: "★☆☆☆☆", 2: "★★☆☆☆", 3: "★★★☆☆", 4: "★★★★☆", 5: "★★★★★"}
STAKEHOLDERS_OPCOES = ["cfo", "juridico", "compras", "auditoria", "diretoria", "externo"]
CLASSES_OPCOES = [
    "alerta", "nota_trabalho", "recomendacao_formal",
    "dossie_decisao", "material_compartilhavel",
]

with aba4:
    st.title("Outputs Acionáveis")
    st.caption(
        "Gere, aprove e compartilhe outputs tributários estruturados vinculados ao Protocolo P1→P9. "
        "Disclaimer obrigatório e não removível em toda saída."
    )

    col_esq, col_dir = st.columns([1, 3])

    with col_esq:
        st.subheader("Filtros")
        case_id_out = st.number_input("Case ID", min_value=1, step=1, value=1, key="out_case_id")
        filtro_classe = st.multiselect(
            "Classe", options=CLASSES_OPCOES,
            default=CLASSES_OPCOES, key="out_filtro_classe",
        )
        filtro_status = st.multiselect(
            "Status", options=["rascunho", "gerado", "aprovado", "publicado", "revogado"],
            default=["gerado", "aprovado", "publicado"],
        )
        carregar_outputs = st.button("Carregar Outputs", type="primary")

        st.divider()
        st.subheader("Gerar Output")
        with st.form("form_gerar_output"):
            classe_sel = st.selectbox("Classe", options=CLASSES_OPCOES)
            stk_sel = st.multiselect("Stakeholders", options=STAKEHOLDERS_OPCOES)

            # Campos condicionais por classe (mostrar todos — simplificado)
            query_out = st.text_area("Query (C2/C3)", height=60,
                placeholder="Ex: Alíquota IBS para serviços de saúde")
            titulo_out = st.text_input("Título (C1 Alerta)",
                placeholder="Ex: Alerta prazo recolhimento IBS")
            contexto_out = st.text_area("Contexto (C1 Alerta)", height=60)
            mat_out = st.slider("Materialidade (C1)", min_value=1, max_value=5, value=3)
            base_id_out = st.number_input("Output Base ID (C5)", min_value=0, step=1, value=0)

            gerar_btn = st.form_submit_button("Gerar Output", type="primary")

        if gerar_btn:
            body: dict = {"case_id": case_id_out, "classe": classe_sel}
            if stk_sel:
                body["stakeholders"] = stk_sel
            if classe_sel == "alerta":
                body.update({"titulo": titulo_out, "contexto": contexto_out, "materialidade": mat_out})
            elif classe_sel in ("nota_trabalho", "recomendacao_formal"):
                body["query"] = query_out
            elif classe_sel == "material_compartilhavel":
                body["output_base_id"] = base_id_out if base_id_out > 0 else None

            try:
                rg = httpx.post(f"{API_BASE}/v1/outputs", json=body, timeout=120)
            except httpx.ConnectError:
                st.error("API offline.")
                rg = None

            if rg is not None:
                if rg.status_code == 201:
                    d = rg.json()
                    emoji, _ = CLASSE_BADGE.get(d["classe"], ("📄", "#888"))
                    st.success(f"{emoji} Output **{d['id']}** gerado — {d['titulo'][:60]}")
                else:
                    try:
                        detalhe = rg.json().get("detail", rg.text[:300])
                    except Exception:
                        detalhe = rg.text[:300]
                    st.error(f"Erro: {detalhe}")

    with col_dir:
        if carregar_outputs or st.session_state.get("_out_case_id") == case_id_out:
            st.session_state["_out_case_id"] = case_id_out
            try:
                ro = httpx.get(f"{API_BASE}/v1/cases/{case_id_out}/outputs", timeout=10)
            except httpx.ConnectError:
                st.error("API offline.")
                ro = None

            if ro is not None:
                if ro.status_code != 200:
                    st.warning(f"Não foi possível carregar outputs: {ro.text[:200]}")
                else:
                    outputs = ro.json()
                    # Filtrar por classe e status
                    outputs = [
                        o for o in outputs
                        if o["classe"] in filtro_classe and o["status"] in filtro_status
                    ]
                    if not outputs:
                        st.info("Nenhum output encontrado com os filtros selecionados.")
                    else:
                        st.caption(f"{len(outputs)} output(s) encontrado(s)")
                        for out in outputs:
                            emoji, cor = CLASSE_BADGE.get(out["classe"], ("📄", "#888"))
                            estrelas = ESTRELAS.get(out.get("materialidade") or 3, "★★★☆☆")
                            status_badge = STATUS_COR.get(out["status"], "⚪")

                            with st.expander(
                                f"{emoji} [{out['id']}] {out['titulo'][:70]}  |  "
                                f"{status_badge} {out['status']}  |  {estrelas}",
                                expanded=False,
                            ):
                                st.caption(
                                    f"Classe: `{out['classe']}` · Passo: P{out['passo_origem']} · "
                                    f"Criado: {str(out.get('created_at', ''))[:19]}"
                                )
                                if out.get("versao_prompt"):
                                    st.caption(f"Prompt: `{out['versao_prompt']}` · Base: `{out.get('versao_base','')}`")

                                # Conteúdo principal
                                conteudo = out.get("conteudo", {})
                                for chave in ["recomendacao_principal", "resposta", "decisao_final",
                                              "contexto", "hipotese_gestor"]:
                                    if conteudo.get(chave):
                                        st.markdown(f"**{chave.replace('_', ' ').title()}**")
                                        st.write(conteudo[chave])
                                        break

                                if conteudo.get("fundamento_legal"):
                                    st.markdown("**Fundamento Legal**")
                                    for art in conteudo["fundamento_legal"]:
                                        st.write(f"- {art}")

                                # Disclaimer em destaque (não colapsável)
                                st.warning(f"⚠️ **Disclaimer:**\n\n{out['disclaimer']}")

                                # Views por stakeholder
                                views = out.get("stakeholder_views", [])
                                if views:
                                    st.markdown("**Views por Stakeholder**")
                                    tabs_labels = [v["stakeholder"].upper() for v in views]
                                    stk_tabs = st.tabs(tabs_labels)
                                    for tab, view in zip(stk_tabs, views):
                                        with tab:
                                            st.write(view["resumo"])
                                            st.caption(f"Campos: {', '.join(view['campos_visiveis'])}")

                                # Ações
                                col_ap, col_c5 = st.columns(2)
                                with col_ap:
                                    if out["status"] in ("rascunho", "gerado"):
                                        with st.form(f"form_aprovar_{out['id']}"):
                                            aprovado_por = st.text_input("Aprovado por", key=f"ap_{out['id']}")
                                            obs = st.text_input("Observação (opcional)", key=f"obs_{out['id']}")
                                            if st.form_submit_button("✅ Aprovar"):
                                                try:
                                                    ra = httpx.post(
                                                        f"{API_BASE}/v1/outputs/{out['id']}/aprovar",
                                                        json={"aprovado_por": aprovado_por, "observacao": obs or None},
                                                        timeout=10,
                                                    )
                                                    if ra.status_code == 200:
                                                        st.success("Aprovado com sucesso!")
                                                        st.session_state["_out_case_id"] = case_id_out
                                                        st.rerun()
                                                    else:
                                                        st.error(ra.json().get("detail", ra.text[:200]))
                                                except httpx.ConnectError:
                                                    st.error("API offline.")

                                with col_c5:
                                    if out["status"] == "aprovado" and out["classe"] in ("recomendacao_formal", "dossie_decisao"):
                                        stk_c5 = st.multiselect(
                                            "Stakeholders C5", STAKEHOLDERS_OPCOES,
                                            key=f"c5stk_{out['id']}"
                                        )
                                        if st.button("📤 Gerar Material Compartilhável", key=f"c5_{out['id']}"):
                                            if not stk_c5:
                                                st.warning("Selecione ao menos 1 stakeholder.")
                                            else:
                                                try:
                                                    rc5 = httpx.post(
                                                        f"{API_BASE}/v1/outputs",
                                                        json={
                                                            "case_id": case_id_out,
                                                            "classe": "material_compartilhavel",
                                                            "output_base_id": out["id"],
                                                            "stakeholders": stk_c5,
                                                        },
                                                        timeout=120,
                                                    )
                                                    if rc5.status_code == 201:
                                                        st.success(f"Material Compartilhável #{rc5.json()['id']} gerado!")
                                                        st.rerun()
                                                    else:
                                                        st.error(rc5.json().get("detail", rc5.text[:200]))
                                                except httpx.ConnectError:
                                                    st.error("API offline.")


# ===========================================================================
# ABA 5 — Observability de IA
# ===========================================================================
MODEL_DEV_UI = "claude-haiku-4-5-20251001"
PROMPT_VERSION_UI = "v1.0.0-sprint2"

THRESHOLD_LABELS = {
    "precisao_citacao":      ("≥ 90%", 0.90, True),
    "taxa_alucinacao":       ("≤ 5%",  0.05, False),
    "acuracia_recomendacao": ("≥ 80%", 0.80, True),
    "latencia_p95":          ("≤ 15s", 15.0, True),
    "cobertura_contra_tese": ("≥ 80%", 0.80, True),
}

with aba5:
    st.title("Observability de IA")
    st.caption("Métricas contínuas, detecção de drift e regression testing do TaxMind Light.")

    # ------ Linha 1 — KPIs ------
    st.subheader("KPIs — Últimos 7 dias")
    try:
        rm = httpx.get(f"{API_BASE}/v1/observability/metrics", params={"days": 7}, timeout=5)
        resumo = rm.json().get("resumo", {}) if rm.status_code == 200 else {}
    except Exception:
        resumo = {}

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        val = resumo.get("taxa_alucinacao")
        st.metric("Taxa Alucinação", f"{val*100:.1f}%" if val is not None else "—",
                  delta=None, help="Proxy: % interações com anti-alucinação bloqueado")
    with kpi2:
        val = resumo.get("p95_latencia_ms")
        st.metric("Latência p95", f"{val/1000:.1f}s" if val is not None else "—")
    with kpi3:
        val = resumo.get("pct_scoring_alto")
        st.metric("% Scoring Alto", f"{val*100:.1f}%" if val is not None else "—")
    with kpi4:
        val = resumo.get("total_interacoes")
        st.metric("Total Interações", str(val) if val is not None else "0")

    st.divider()

    # ------ Linha 2 — Gráficos ------
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("Latência (30 dias)")
        try:
            rm30 = httpx.get(f"{API_BASE}/v1/observability/metrics", params={"days": 30}, timeout=5)
            metrics_list = rm30.json().get("metrics", []) if rm30.status_code == 200 else []
        except Exception:
            metrics_list = []

        if metrics_list:
            import json as _json
            datas = [m["data_referencia"] for m in metrics_list]
            lat_avg = [m.get("avg_latencia_ms") for m in metrics_list]
            lat_p95 = [m.get("p95_latencia_ms") for m in metrics_list]
            st.line_chart({"p50/avg": [v for v in lat_avg if v],
                           "p95": [v for v in lat_p95 if v]})
        else:
            st.info("Sem dados de latência disponíveis.")

    with col_g2:
        st.subheader("Taxa de Bloqueio por Mecanismo")
        if metrics_list:
            mecanismos = {}
            for key in ("taxa_bloqueio_m1", "taxa_bloqueio_m2", "taxa_bloqueio_m3", "taxa_bloqueio_m4"):
                vals = [m.get(key) for m in metrics_list if m.get(key) is not None]
                mecanismos[key.replace("taxa_bloqueio_", "").upper()] = sum(vals)/len(vals) if vals else 0
            st.bar_chart(mecanismos)
        else:
            st.info("Sem dados de bloqueio disponíveis.")

    st.divider()

    # ------ Linha 3 — Drift Alerts ------
    st.subheader("Drift Alerts Ativos")
    col_d1, col_d2 = st.columns([3, 1])
    with col_d2:
        pv_drift = st.text_input("prompt_version (drift)", value=PROMPT_VERSION_UI, key="pv_drift")
        refresh_drift = st.button("Atualizar Alerts")

    try:
        rd = httpx.get(f"{API_BASE}/v1/observability/drift",
                       params={"prompt_version": pv_drift}, timeout=5)
        drift_alerts = rd.json() if rd.status_code == 200 else []
    except Exception:
        drift_alerts = []

    if not drift_alerts:
        st.success("Nenhum drift alert ativo.")
    else:
        st.warning(f"⚠️ {len(drift_alerts)} alert(s) ativo(s)")
        for alert in drift_alerts:
            with st.expander(f"🔔 {alert['metrica']} — {float(alert['desvios_padrao']):.2f}σ"):
                st.write(f"**Baseline:** {float(alert['valor_baseline']):.4f} → **Atual:** {float(alert['valor_atual']):.4f}")
                st.caption(f"Detectado em: {str(alert.get('detectado_em',''))[:19]}")
                with st.form(f"form_resolve_{alert['id']}"):
                    obs = st.text_input("Observação de resolução")
                    if st.form_submit_button("✅ Resolver"):
                        try:
                            rr = httpx.post(
                                f"{API_BASE}/v1/observability/drift/{alert['id']}/resolver",
                                json={"observacao": obs or "Resolvido via dashboard"},
                                timeout=5,
                            )
                            if rr.status_code == 200:
                                st.success("Resolvido!")
                                st.rerun()
                            else:
                                st.error(rr.text[:200])
                        except httpx.ConnectError:
                            st.error("API offline.")

    st.divider()

    # ------ Linha 4 — Regression Testing ------
    st.subheader("Regression Testing")
    with st.form("form_regression"):
        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            pv_reg = st.text_input("prompt_version", value=PROMPT_VERSION_UI)
        with col_r2:
            mid_reg = st.text_input("model_id", value=MODEL_DEV_UI)
        with col_r3:
            bv_reg = st.text_input("baseline_version", value=PROMPT_VERSION_UI)
        run_reg = st.form_submit_button("▶ Executar Regression", type="primary")
        st.caption("⚠️ Faz chamadas reais ao LLM — pode levar até 2 minutos.")

    if run_reg:
        with st.spinner("Executando regression testing (5 casos)..."):
            try:
                rr = httpx.post(
                    f"{API_BASE}/v1/observability/regression",
                    json={"prompt_version": pv_reg, "model_id": mid_reg, "baseline_version": bv_reg},
                    timeout=180,
                )
            except httpx.ConnectError:
                st.error("API offline.")
                rr = None

        if rr is not None and rr.status_code == 200:
            res = rr.json()
            badge = "🟢 APROVADO" if res["aprovado"] else "🔴 REPROVADO"
            st.markdown(f"### {badge}")
            metricas_res = [
                ("Precisão Citação", res["precisao_citacao"], "≥ 90%", res["precisao_citacao"] >= 0.90),
                ("Taxa Alucinação", res["taxa_alucinacao"], "≤ 5%", res["taxa_alucinacao"] <= 0.05),
                ("Acurácia Recomendação", res["acuracia_recomendacao"], "≥ 80%", res["acuracia_recomendacao"] >= 0.80),
                ("Latência p95 (s)", res["latencia_p95"], "≤ 15s", res["latencia_p95"] <= 15.0),
                ("Cobertura Contra-tese", res["cobertura_contra_tese"], "≥ 80%", res["cobertura_contra_tese"] >= 0.80),
            ]
            for nome, valor, threshold, ok in metricas_res:
                icon = "✅" if ok else "❌"
                st.write(f"{icon} **{nome}**: {valor:.2%} (threshold: {threshold})" if "%" not in threshold or "s" not in threshold else f"{icon} **{nome}**: {valor:.2f} (threshold: {threshold})")
        elif rr is not None:
            st.error(f"Erro: {rr.text[:300]}")

    st.divider()

    # ------ Linha 5 — Baseline Management ------
    st.subheader("Gestão de Baseline")
    with st.form("form_baseline"):
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            pv_base = st.text_input("prompt_version", value=PROMPT_VERSION_UI, key="pv_base")
        with col_b2:
            mid_base = st.text_input("model_id", value=MODEL_DEV_UI, key="mid_base")
        reg_base = st.form_submit_button("📊 Registrar Baseline", type="primary")

    if reg_base:
        try:
            rb = httpx.post(
                f"{API_BASE}/v1/observability/baseline",
                json={"prompt_version": pv_base, "model_id": mid_base},
                timeout=10,
            )
            if rb.status_code == 201:
                d = rb.json()
                st.success(f"Baseline registrado — sample_size={d.get('sample_size', '?')}")
                st.json({k: round(v, 4) if isinstance(v, float) else v
                         for k, v in d.items() if v is not None})
            else:
                st.error(rb.json().get("detail", rb.text[:200]))
        except httpx.ConnectError:
            st.error("API offline.")
