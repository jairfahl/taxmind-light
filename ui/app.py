"""
ui/app.py — Interface Streamlit para TaxMind Light.
Aba 1: Consultar · Aba 2: Adicionar Norma · Aba 3: Protocolo P1→P9 · Aba 4: Documentos · Aba 5: Qualidade do Sistema
Consome a FastAPI em http://localhost:8000.
"""

import os
import re
import time

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

# BUG-04 — nomes legíveis para os códigos internos de norma
NOMES_NORMAS = {
    "EC132_2023": "EC 132/2023",
    "LC214_2025": "LC 214/2025",
    "LC227_2026": "LC 227/2026",
}


def nome_norma(codigo: str) -> str:
    return NOMES_NORMAS.get(codigo, codigo)


def _sanitize_latex(texto: str) -> str:
    """Remove notação LaTeX/MathJax que o Streamlit renderiza como fórmula."""
    if not texto:
        return texto
    # Substituir $...$ por texto sem cifrões (evita renderização de fórmulas)
    resultado = re.sub(r'\$([^$]+)\$', r'\1', texto)
    # Remover \( \) \[ \] soltos
    resultado = resultado.replace('\\(', '').replace('\\)', '')
    resultado = resultado.replace('\\[', '').replace('\\]', '')
    return resultado


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


# --- Alerta global de creditos ---
@st.cache_data(ttl=60)
def _verificar_creditos():
    """Consulta saldo de creditos de API a cada 60s."""
    try:
        resp = httpx.get(f"{API_BASE}/v1/credits", timeout=3)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

_creditos = _verificar_creditos()
if _creditos and _creditos.get("alerta"):
    if _creditos["saldo_restante"] <= 0:
        st.error(f"🚨 {_creditos['mensagem']}")
    else:
        st.warning(f"⚠️ {_creditos['mensagem']}")

# --- Sidebar ---
st.sidebar.title("⚖️ TaxMind Light")
st.sidebar.caption("Reforma Tributária · Base dinâmica de normas")

if _creditos:
    saldo = _creditos.get("saldo_restante", 0)
    limite = _creditos.get("limite", 0)
    pct = (saldo / limite * 100) if limite > 0 else 0
    st.sidebar.metric("Saldo API", f"US$ {saldo:.2f}", delta=f"{pct:.0f}% restante")
    st.sidebar.divider()

normas_disponiveis = _buscar_normas_disponiveis()

normas_sel = st.sidebar.multiselect(
    "Filtrar por norma",
    options=list(normas_disponiveis.keys()),
    default=list(normas_disponiveis.keys()),
)
norma_filter = [normas_disponiveis[n] for n in normas_sel] if normas_sel else None

top_k = st.sidebar.slider("Trechos consultados", min_value=3, max_value=10, value=5)

incluir_outros = st.sidebar.checkbox(
    "Incluir documentos adicionais (tipo Outro)",
    value=False,
    help="Por padrão, PDFs adicionados manualmente ficam fora do RAG. "
         "Marque para incluí-los nas consultas.",
)

st.sidebar.divider()

# Health check na sidebar — BUG-07
try:
    hr = httpx.get(f"{API_BASE}/v1/health", timeout=10)
    if hr.status_code == 200:
        hdata = hr.json()
        st.sidebar.success(
            f"API online · {hdata['chunks_total']:,} trechos legislativos · "
            f"{len(hdata.get('normas', []))} normas"
        )
    else:
        st.sidebar.warning(f"API com problema (status {hr.status_code})")
except httpx.TimeoutException:
    st.sidebar.warning("API demorando a responder — aguarde e recarregue")
except Exception:
    st.sidebar.error("API offline — certifique-se que o servidor está rodando")

# --- Abas ---
aba1, aba2, aba3, aba4, aba5 = st.tabs(["Consultar", "Adicionar Norma", "Protocolo P1→P9", "Documentos", "Qualidade do Sistema"])


# ===========================================================================
# ABA 1 — Consultar
# ===========================================================================
with aba1:
    st.title("TaxMind Light — Reforma Tributária")
    st.caption("Análise tributária com base legislativa verificada · Esta análise não substitui a avaliação do seu time fiscal")

    query = st.text_area(
        "Sua consulta",
        placeholder="Ex: Como funciona o split payment para e-commerce com plataforma digital intermediária?",
        height=100,
    )

    if st.button("Analisar", type="primary", disabled=not query.strip()):
        with st.spinner("Analisando..."):
            try:
                resp = httpx.post(
                    f"{API_BASE}/v1/analyze",
                    json={
                        "query": query,
                        "norma_filter": norma_filter,
                        "top_k": top_k,
                        "excluir_tipos": [] if incluir_outros else ["Outro"],
                    },
                    timeout=60,
                )
            except httpx.ConnectError:
                st.error("Não foi possível conectar à API. Verifique se o servidor FastAPI está rodando em localhost:8000.")
                st.stop()

        if resp.status_code == 400:
            err = resp.json()
            bloqueios = err.get("detail", {}).get("bloqueios", [])
            _tem_bl02 = any("BL-02" in b for b in bloqueios)

            if _tem_bl02:
                st.warning(
                    "⚠️ **Sua consulta não contém termos tributários reconhecidos.**\n\n"
                    "O TaxMind analisa questões relacionadas à Reforma Tributária "
                    "(IBS, CBS, ICMS, alíquotas, split payment, etc.). "
                    "Tente reformular incluindo o contexto tributário.\n\n"
                    f"**Sugestão:**\n\n"
                    f"> *Como o IBS/CBS impacta {query.strip().rstrip('?').lower()} "
                    f"— alíquotas, obrigações acessórias e prazos de recolhimento?*"
                )
            else:
                st.error("🔴 **Consulta Bloqueada**")
                for b in bloqueios:
                    st.write(f"- {b}")
            st.stop()

        if resp.status_code != 200:
            st.error(f"Erro da API: {resp.status_code} — {resp.text[:300]}")
            st.stop()

        data = resp.json()
        status = data["qualidade"]["status"]
        scoring = data["scoring_confianca"]

        col1, col2 = st.columns(2)
        with col1:
            _conf_help = (
                "Avalia se a resposta está bem ancorada na legislação disponível. "
                "'Com ressalvas' indica que os trechos recuperados cobrem parcialmente "
                "o tema — a resposta é válida, mas recomenda-se verificar aspectos "
                "não cobertos pela base de conhecimento atual."
            )
            if status == "verde":
                st.metric("Confiabilidade da resposta", "🟢 Boa", help=_conf_help)
            elif status == "amarelo":
                st.metric("Confiabilidade da resposta", "🟡 Com ressalvas", help=_conf_help)
            else:
                st.metric("Confiabilidade da resposta", "🔴 Insuficiente", help=_conf_help)
        with col2:
            badge = {"alto": "🟢 Alta cobertura", "medio": "🟡 Cobertura parcial", "baixo": "🔴 Cobertura insuficiente"}.get(scoring, scoring)
            st.metric(
                "Cobertura da base legal",
                badge,
                help=(
                    "Indica quantos trechos legislativos relevantes foram encontrados "
                    "para fundamentar esta resposta. 'Cobertura insuficiente' não significa "
                    "erro — significa que o tema pode ter regulamentação complementar ainda "
                    "não incluída na base (ex: regulamentos do Comitê Gestor do IBS). "
                    "A base cobre EC 132/2023, LC 214/2025 e LC 227/2026."
                ),
            )

        st.divider()

        disclaimer = (
            "⚠️ Esta análise é um ponto de partida baseado na legislação disponível. "
            "Valide com seu consultor tributário antes de tomar qualquer decisão "
            "que impacte a operação ou o caixa da empresa."
        )
        st.warning(disclaimer)

        st.subheader("Análise")
        if data["anti_alucinacao"]["bloqueado"]:
            st.error("❌ Análise bloqueada pelas verificações de integridade.")
        st.write(_sanitize_latex(data["resposta"]))

        if data.get("impacto_financeiro"):
            st.subheader("💰 Impacto Financeiro")
            st.info(_sanitize_latex(data["impacto_financeiro"]))

        if data.get("acao_recomendada"):
            st.subheader("🎯 Ação Recomendada")
            st.success(_sanitize_latex(data["acao_recomendada"]))

        grau = data["grau_consolidacao"]
        grau_label = {
            "consolidado": "Entendimento consolidado",
            "divergente":  "Tema em disputa — risco moderado",
            "indefinido":  "Sem precedente — risco elevado",
        }.get(grau, grau.capitalize())
        grau_icon = {"consolidado": "✅", "divergente": "⚠️", "indefinido": "❓"}.get(grau, "")
        st.caption(f"Consenso de Mercado: {grau_icon} {grau_label}")

        if data["fundamento_legal"]:
            st.subheader("📋 Base legal")
            for art in data["fundamento_legal"]:
                st.write(f"- {art}")

        if data.get("contra_tese"):
            with st.expander("⚖️ Posição contrária"):
                st.write(_sanitize_latex(data["contra_tese"]))

        anti = data["anti_alucinacao"]
        flags = anti.get("flags", [])
        with st.expander("🔍 Verificações de integridade", expanded=False):
            ac1, ac2, ac3, ac4 = st.columns(4)
            ac1.metric("Artigo existe na base", "✓" if anti["m1_existencia"] else "✗")
            ac2.metric("Norma em vigor", "✓" if anti["m2_validade"] else "⚠")
            ac3.metric("Tema pertinente", "✓" if anti["m3_pertinencia"] else "✗")
            ac4.metric("Consistência interna", "✓" if anti["m4_consistencia"] else "✗")
            if flags:
                st.caption(f"Alertas de integridade: {', '.join(flags)}")

        with st.expander(f"📄 Trechos legislativos consultados ({len(data['chunks'])})"):
            for i, chunk in enumerate(data["chunks"], 1):
                score = chunk["score_final"]
                st.markdown(
                    f"**[{i}]** {nome_norma(chunk['norma_codigo'])} | "
                    f"{chunk['artigo'] or 'artigo não identificado'}"
                )
                st.progress(score, text=f"Relevância: {score:.0%}")
                st.text(chunk["texto"][:400] + ("..." if len(chunk["texto"]) > 400 else ""))
                if i < len(data["chunks"]):
                    st.divider()

        with st.expander("Detalhes técnicos", expanded=False):
            st.write(f"Versão da análise: {data['prompt_version']}")
            st.write(f"Motor de análise: {data['model_id']}")
            st.write(f"Trechos consultados: {len(data['chunks'])}")


# ===========================================================================
# ABA 2 — Adicionar Norma
# ===========================================================================
with aba2:
    st.title("Adicionar Norma")
    st.caption("Adicione INs, Resoluções, Pareceres ou Manuais à base de conhecimento.")

    uploaded_file = st.file_uploader(
        "Selecione o arquivo",
        type=["pdf", "docx", "xlsx", "html", "htm", "txt", "md", "csv"],
    )

    # Verificar duplicidade imediatamente após upload
    _dup_bloqueado = False
    if uploaded_file is not None:
        try:
            check_resp = httpx.post(
                f"{API_BASE}/v1/ingest/check-duplicate",
                files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                timeout=15,
            )
            if check_resp.status_code == 200:
                check_data = check_resp.json()
                if check_data["duplicado"]:
                    st.warning(
                        f"⚠️ {check_data['mensagem']} "
                        f"Para substituir, remova o documento existente primeiro."
                    )
                    _dup_bloqueado = True
        except Exception:
            pass  # Se a verificação falhar, permitir seguir normalmente

    if _dup_bloqueado:
        st.stop()

    nome_doc = st.text_input(
        "Nome do documento",
        placeholder="Ex: IN RFB 2184/2024",
    )
    tipo_doc = st.selectbox(
        "Tipo",
        options=["IN", "Resolução", "Parecer", "Manual", "Outro"],
    )

    st.info(
        "Após incluído, o documento estará disponível automaticamente "
        "nas consultas da Aba 1."
    )

    pode_ingerir = uploaded_file is not None and nome_doc.strip()

    if st.button("Incluir na base", type="primary", disabled=not pode_ingerir):
        # 1. Disparar ingest assíncrono (retorna imediatamente com job_id)
        try:
            resp = httpx.post(
                f"{API_BASE}/v1/ingest/upload",
                files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                data={"nome": nome_doc.strip(), "tipo": tipo_doc},
                timeout=30,
            )
        except httpx.ConnectError:
            st.error("Não foi possível conectar à API.")
            st.stop()

        if resp.status_code != 200:
            try:
                detalhe = resp.json().get("detail", resp.text[:200])
            except Exception:
                detalhe = resp.text[:200]
            st.error(f"❌ Erro ao iniciar processamento: {detalhe}")
            st.stop()

        job_id = resp.json()["job_id"]

        # 2. Polling com barra de progresso
        progresso = st.progress(0, text="Processando documento...")
        for i in range(120):  # máximo 120 × 3s = 6 minutos
            time.sleep(3)
            try:
                poll = httpx.get(f"{API_BASE}/v1/ingest/jobs/{job_id}", timeout=10)
                data = poll.json()
                status = data["status"]
            except Exception:
                continue

            if status == "done":
                progresso.empty()
                r = data.get("result", {})
                st.success(
                    f"✅ **{r.get('nome', nome_doc)}** incluído com sucesso — "
                    f"{r.get('chunks', '?')} trechos extraídos"
                )
                if r.get("codigo"):
                    st.caption(f"Código interno: `{r['codigo']}` · norma_id={r.get('norma_id')}")
                _buscar_normas_disponiveis.clear()
                st.info("Recarregue a página para ver o novo documento no filtro da Aba 1.")
                break
            elif status == "error":
                progresso.empty()
                st.error(f"❌ Erro: {data.get('message', 'Erro desconhecido')}")
                break
            else:
                progresso.progress(
                    min((i + 1) / 120, 0.95),
                    text=f"Processando... ({(i + 1) * 3}s)",
                )
        else:
            progresso.empty()
            st.warning("⚠️ Processamento em andamento. Verifique novamente em alguns minutos.")

    # --- Gerenciar documentos existentes ---
    st.divider()
    st.subheader("Documentos na base de conhecimento")

    try:
        resp_normas = httpx.get(f"{API_BASE}/v1/ingest/normas", timeout=10)
        if resp_normas.status_code == 200:
            normas_lista = resp_normas.json()
            if not normas_lista:
                st.info("Nenhum documento na base.")
            else:
                for norma in normas_lista:
                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(
                            f"**{norma['nome']}** · `{norma['codigo']}` · "
                            f"{norma['tipo']} · {norma['total_chunks']} trechos"
                        )
                    with col_btn:
                        btn_key = f"del_norma_{norma['id']}"
                        if st.button("🗑️ Remover", key=btn_key, type="secondary"):
                            st.session_state[f"confirmar_del_{norma['id']}"] = True

                    # Confirmação de exclusão
                    if st.session_state.get(f"confirmar_del_{norma['id']}"):
                        st.warning(
                            f"Tem certeza que deseja remover **{norma['nome']}**? "
                            f"Serão excluídos {norma['total_chunks']} trechos e seus embeddings. "
                            f"Esta ação não pode ser desfeita."
                        )
                        col_sim, col_nao, _ = st.columns([1, 1, 4])
                        with col_sim:
                            if st.button("Sim, remover", key=f"confirmar_sim_{norma['id']}", type="primary"):
                                try:
                                    del_resp = httpx.delete(
                                        f"{API_BASE}/v1/ingest/normas/{norma['id']}",
                                        timeout=30,
                                    )
                                    if del_resp.status_code == 200:
                                        del_data = del_resp.json()
                                        st.success(
                                            f"✅ **{del_data['nome']}** removido — "
                                            f"{del_data['chunks_removidos']} trechos e "
                                            f"{del_data['embeddings_removidos']} embeddings excluídos."
                                        )
                                        st.session_state.pop(f"confirmar_del_{norma['id']}", None)
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        detalhe = del_resp.json().get("detail", del_resp.text[:200])
                                        st.error(f"Erro: {detalhe}")
                                except Exception as exc:
                                    st.error(f"Erro ao remover: {exc}")
                        with col_nao:
                            if st.button("Cancelar", key=f"confirmar_nao_{norma['id']}"):
                                st.session_state.pop(f"confirmar_del_{norma['id']}", None)
                                st.rerun()
        else:
            st.error("Erro ao carregar lista de documentos.")
    except httpx.ConnectError:
        st.warning("API indisponível. Não foi possível carregar os documentos.")


# ===========================================================================
# ABA 3 — Protocolo P1→P9
# ===========================================================================
PASSO_NOME = {
    1: "P1 · Identificar o problema",
    2: "P2 · Mapear o cenário da empresa",
    3: "P3 · Avaliar riscos e dados",
    4: "P4 · Análise tributária",
    5: "P5 · Posição do gestor",
    6: "P6 · Recomendação TaxMind",
    7: "P7 · Decisão e responsável",
    8: "P8 · Acompanhamento",
    9: "P9 · Registro de aprendizado",
}
STATUS_BADGE = {
    "rascunho": "🔵",
    "em_analise": "🟡",
    "aguardando_hipotese": "🟠",
    "decidido": "🟢",
    "em_monitoramento": "🔵",
    "aprendizado_extraido": "✅",
}
STATUS_LABEL = {
    "rascunho":            "Em elaboração",
    "em_analise":          "Em análise",
    "aguardando_hipotese": "Aguardando posição do gestor",
    "decidido":            "Decisão registrada",
    "em_monitoramento":    "Em acompanhamento",
    "em_revisao":          "Em revisão",
    "aprendizado_extraido":"Concluído",
    "arquivado":           "Arquivado",
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
            titulo_caso = st.text_input("Nome do caso (mín. 10 chars)", placeholder="Ex: Apuração CBS — CNPJ 12.345.678/0001-90")
            descricao_caso = st.text_area("Descreva o problema tributário", placeholder="Descreva o contexto do caso...", height=80)
            contexto_fiscal = st.text_input("Situação atual da empresa", placeholder="Ex: Empresa de serviços de TI — Lucro Presumido")
            submitted_criar = st.form_submit_button("Criar Caso", type="primary")

        if submitted_criar:
            if not titulo_caso.strip() or len(titulo_caso.strip()) < 10:
                st.error("O nome do caso deve ter pelo menos 10 caracteres.")
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
                        st.session_state["case_id_ativo"] = d["case_id"]
                        st.success(f"✅ Caso criado — Nº {d['case_id']}")
                        st.rerun()
                    else:
                        st.error(f"Erro: {r.json().get('detail', r.text[:200])}")
                except httpx.ConnectError:
                    st.error("API offline.")

    st.divider()

    # ------ Seção: Consultar estado do caso ------
    st.subheader("Consultar / Avançar Caso")
    _default_case_id = int(st.session_state.get("case_id_ativo", 1))
    case_id_input = st.number_input("Número do caso", min_value=1, step=1, value=_default_case_id)

    col_load, col_refresh = st.columns([1, 4])
    with col_load:
        load_case = st.button("Carregar Caso")

    _autoload = st.session_state.get("case_id_ativo") == case_id_input
    if load_case or st.session_state.get("_proto_case_id") == case_id_input or _autoload:
        st.session_state["_proto_case_id"] = case_id_input
        try:
            r = httpx.get(f"{API_BASE}/v1/cases/{case_id_input}", timeout=30)
        except httpx.TimeoutException:
            st.error("O servidor demorou a responder. Recarregue e tente novamente.")
            st.stop()
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
            status_label = STATUS_LABEL.get(status, status)

            st.markdown(f"### {badge} {caso['titulo']}")
            st.caption(f"Etapa atual: **{PASSO_NOME.get(passo_atual, str(passo_atual))}** · Status: {status_label}")

            # Caso já concluído — modo read-only com navegação entre passos
            _caso_concluido = status == "aprendizado_extraido"
            if _caso_concluido:
                st.progress(1.0, text="Etapa 9/9 — Concluído")
                st.success(
                    "**Caso concluído e registrado com sucesso!** "
                    "Navegue pelos passos abaixo para revisar todas as informações."
                )
                st.info(
                    "**Próximos passos:** "
                    "Acesse a aba **Documentos** para gerar relatórios · "
                    "**Consultar** para novas análises · "
                    "ou crie um **novo caso** acima"
                )

                # Navegador de passos read-only
                _steps_data_ro = caso.get("steps") or caso.get("passos") or {}
                _passo_vis = st.selectbox(
                    "Visualizar passo:",
                    options=[1, 2, 3, 4, 5, 6, 7, 8, 9],
                    format_func=lambda p: PASSO_NOME.get(p, f"P{p}"),
                    key="passo_visualizar_readonly",
                )
                _step_ro = _steps_data_ro.get(_passo_vis) or _steps_data_ro.get(str(_passo_vis)) or {}
                _dados_ro = _step_ro.get("dados") or {}

                st.divider()

                if _passo_vis == 1:
                    st.subheader("P1 — Identificar o problema")
                    st.caption("Título do caso")
                    st.info(_dados_ro.get("titulo", caso.get("titulo", "—")))
                    st.caption("Descrição do problema tributário")
                    st.markdown(_dados_ro.get("descricao") or "—")
                    st.caption("Situação atual da empresa")
                    st.markdown(_dados_ro.get("contexto_fiscal") or "—")

                elif _passo_vis == 2:
                    st.subheader("P2 — Mapear o cenário da empresa")
                    st.caption("Premissas declaradas")
                    _prems = _dados_ro.get("premissas", [])
                    if _prems:
                        for _p in _prems:
                            st.markdown(f"- {_p}")
                    else:
                        st.info("Nenhuma premissa registrada.")
                    st.caption("Período de referência")
                    st.info(_dados_ro.get("periodo_fiscal") or "—")

                elif _passo_vis == 3:
                    st.subheader("P3 — Avaliar riscos e dados")
                    st.caption("Riscos mapeados")
                    _riscos = _dados_ro.get("riscos", [])
                    if _riscos:
                        for _r in _riscos:
                            st.markdown(f"- {_r}")
                    else:
                        st.info("Nenhum risco registrado.")
                    st.caption("Avaliação dos dados disponíveis")
                    _qual_map = {"verde": "🟢 Verde — dados completos", "amarelo": "🟡 Amarelo — dados parciais", "vermelho": "🔴 Vermelho — dados insuficientes"}
                    st.info(_qual_map.get(_dados_ro.get("dados_qualidade", ""), _dados_ro.get("dados_qualidade") or "—"))

                elif _passo_vis == 4:
                    st.subheader("P4 — Análise tributária (TaxMind)")
                    st.caption("Pergunta submetida")
                    st.info(_dados_ro.get("query_analise") or "—")
                    _analise = _dados_ro.get("analise_result") or {}
                    if _analise:
                        col_sc, col_gc = st.columns(2)
                        with col_sc:
                            st.caption("Cobertura da base legal")
                            st.info(_analise.get("scoring_confianca") or "—")
                        with col_gc:
                            st.caption("Consenso de mercado")
                            st.info(_analise.get("grau_consolidacao") or "—")
                        st.caption("Análise")
                        st.markdown(_sanitize_latex(_analise.get("resposta") or "—"))
                        if _analise.get("acao_recomendada"):
                            st.caption("Ação recomendada")
                            st.info(_sanitize_latex(_analise["acao_recomendada"]))
                        if _analise.get("impacto_financeiro"):
                            st.caption("Impacto financeiro")
                            st.info(_sanitize_latex(_analise["impacto_financeiro"]))
                        if _analise.get("fundamento_legal"):
                            st.caption("Base legal")
                            _fl = _analise["fundamento_legal"]
                            if isinstance(_fl, list):
                                st.markdown(", ".join(_fl))
                            else:
                                st.markdown(str(_fl))
                        if _analise.get("contra_tese"):
                            st.caption("Contra-tese")
                            st.warning(_sanitize_latex(_analise["contra_tese"]))
                        if _analise.get("disclaimer"):
                            st.caption("Ressalva")
                            st.warning(_sanitize_latex(_analise["disclaimer"]))
                        # Chunks utilizados
                        _chunks = _analise.get("chunks", [])
                        if _chunks:
                            with st.expander(f"📚 {len(_chunks)} trechos da base legal utilizados"):
                                for _ch in _chunks:
                                    st.markdown(
                                        f"**{_ch.get('norma_codigo', '?')}** · {_ch.get('artigo') or 'sem artigo'} "
                                        f"(score: {_ch.get('score_final', 0):.3f})"
                                    )
                                    st.caption(_ch.get("texto", "")[:300])
                    else:
                        st.warning("Dados da análise não disponíveis.")

                elif _passo_vis == 5:
                    st.subheader("P5 — Posição do gestor")
                    st.caption("Posição independente registrada antes da recomendação da IA")
                    st.markdown(_dados_ro.get("hipotese_gestor") or "—")

                elif _passo_vis == 6:
                    st.subheader("P6 — Recomendação TaxMind")
                    st.caption("Recomendação gerada pela IA (com base na análise P4)")
                    st.markdown(_sanitize_latex(_dados_ro.get("recomendacao") or "—"))

                elif _passo_vis == 7:
                    st.subheader("P7 — Decisão e responsável")
                    st.caption("Decisão tomada")
                    st.info(_dados_ro.get("decisao_final") or "—")
                    st.caption("Responsável pela decisão")
                    st.info(_dados_ro.get("decisor") or "—")

                elif _passo_vis == 8:
                    st.subheader("P8 — Acompanhamento")
                    st.caption("O que aconteceu na prática")
                    st.markdown(_dados_ro.get("resultado_real") or "—")
                    st.caption("Data de revisão")
                    st.info(_dados_ro.get("data_revisao") or "—")

                elif _passo_vis == 9:
                    st.subheader("P9 — Registro de aprendizado")
                    st.caption("Aprendizado extraído deste caso")
                    st.markdown(_dados_ro.get("aprendizado_extraido") or "—")

                # Histórico de transições — sempre visível
                st.divider()
                with st.expander("📜 Histórico de transições"):
                    for h in caso["historico"]:
                        de_label = STATUS_LABEL.get(h["status_de"], h["status_de"] or "início")
                        para_label = STATUS_LABEL.get(h["status_para"], h["status_para"])
                        st.caption(
                            f"`{h['created_at'][:19]}` — P{h['passo_de'] or '?'} → P{h['passo_para']} "
                            f"({de_label} → {para_label}) — {h['motivo'] or ''}"
                        )

            else:
                # Progresso visual
                st.progress((passo_atual - 1) / 8.0, text=f"Etapa {passo_atual}/9")

                # Histórico colapsado
                with st.expander("📜 Histórico de transições"):
                    for h in caso["historico"]:
                        de_label = STATUS_LABEL.get(h["status_de"], h["status_de"] or "início")
                        para_label = STATUS_LABEL.get(h["status_para"], h["status_para"])
                        st.caption(
                            f"`{h['created_at'][:19]}` — P{h['passo_de'] or '?'} → P{h['passo_para']} "
                            f"({de_label} → {para_label}) — {h['motivo'] or ''}"
                        )

                st.divider()

                # ------ Formulário de avanço por passo ------
                st.subheader(f"Submeter dados — {PASSO_NOME.get(passo_atual, str(passo_atual))}")

            # BUG-10 — pré-preencher campos com dados já salvos
            _steps_data = caso.get("steps") or caso.get("passos") or {}
            _step_entry = _steps_data.get(passo_atual) or _steps_data.get(str(passo_atual)) or {}
            step_dados_salvos = _step_entry.get("dados") or {}

            # P4: fluxo especial fora de form — chama a API diretamente sem colar JSON manualmente
            if _caso_concluido:
                pass  # Formulário não renderizado para caso concluído
            elif passo_atual == 4:
                query_analise = st.text_area(
                    "Pergunta para o TaxMind",
                    placeholder="Ex: Qual a alíquota do IBS para serviços de TI sob Lucro Presumido?",
                    height=80,
                )
                if st.button("Analisar →", type="primary"):
                    if not query_analise or len(query_analise.strip()) < 10:
                        st.error("A consulta deve ter ao menos 10 caracteres.")
                    else:
                        with st.spinner("Analisando..."):
                            try:
                                resp = httpx.post(
                                    f"{API_BASE}/v1/analyze",
                                    json={
                                        "query": query_analise,
                                        "excluir_tipos": [] if incluir_outros else ["Outro"],
                                    },
                                    timeout=60.0,
                                )
                                resp.raise_for_status()
                                analise = resp.json()

                                st.markdown(
                                    f"**Cobertura da base legal**: {analise['scoring_confianca']} | "
                                    f"**Consenso de Mercado**: {analise['grau_consolidacao']}"
                                )
                                st.markdown(f"**Análise**: {_sanitize_latex(analise['resposta'])}")
                                if analise.get("fundamento_legal"):
                                    st.markdown(f"**Base legal**: {', '.join(analise['fundamento_legal'])}")
                                if analise.get("disclaimer"):
                                    st.warning(analise["disclaimer"])

                                step_resp = httpx.post(
                                    f"{API_BASE}/v1/cases/{case_id_input}/steps/4",
                                    json={"dados": {"query_analise": query_analise, "analise_result": analise}, "acao": "avancar"},
                                    timeout=30.0,
                                )
                                step_resp.raise_for_status()
                                st.session_state["_proto_case_id"] = case_id_input
                                st.rerun()

                            except httpx.TimeoutException:
                                st.error("O servidor demorou a responder. Recarregue o caso e tente novamente.")
                            except httpx.HTTPStatusError as e:
                                st.error(f"Erro ao analisar: {e.response.text[:200]}")
                            except httpx.ConnectError:
                                st.error("API offline.")

            else:
                with st.form(f"form_passo_{passo_atual}"):
                    dados_passo = {}

                    if passo_atual == 1:
                        dados_passo["titulo"] = st.text_input("Nome do caso", value=step_dados_salvos.get("titulo", caso["titulo"]))
                        dados_passo["descricao"] = st.text_area("Descreva o problema tributário", value=step_dados_salvos.get("descricao", ""))
                        dados_passo["contexto_fiscal"] = st.text_input("Situação atual da empresa", value=step_dados_salvos.get("contexto_fiscal", ""))

                    elif passo_atual == 2:
                        _prem_salvas = step_dados_salvos.get("premissas", ["", "", ""])
                        premissa1 = st.text_input("O que sabemos — premissa 1", value=_prem_salvas[0] if len(_prem_salvas) > 0 else "")
                        premissa2 = st.text_input("O que sabemos — premissa 2", value=_prem_salvas[1] if len(_prem_salvas) > 1 else "")
                        premissa3 = st.text_input("O que sabemos — premissa 3 (opcional)", value=_prem_salvas[2] if len(_prem_salvas) > 2 else "")
                        dados_passo["premissas"] = [p for p in [premissa1, premissa2, premissa3] if p.strip()]
                        dados_passo["periodo_fiscal"] = st.text_input("Período de referência", placeholder="Ex: 2025-01 a 2025-12", value=step_dados_salvos.get("periodo_fiscal", ""))

                    elif passo_atual == 3:
                        risco1 = st.text_input("Risco mapeado 1")
                        risco2 = st.text_input("Risco mapeado 2 (opcional)")
                        dados_passo["riscos"] = [r for r in [risco1, risco2] if r.strip()]
                        qualidade_opcoes = {
                            "🟢 Verde — dados completos e consistentes": "verde",
                            "🟡 Amarelo — dados parciais, análise com ressalva": "amarelo",
                            "🔴 Vermelho — dados insuficientes, análise bloqueada": "vermelho",
                        }
                        qualidade_label = st.selectbox(
                            "Avaliação dos dados disponíveis",
                            options=list(qualidade_opcoes.keys()),
                            index=0,
                        )
                        dados_passo["dados_qualidade"] = qualidade_opcoes[qualidade_label]

                    elif passo_atual == 5:
                        st.info("Esta é a sua posição — registre ANTES de ver a recomendação do TaxMind (P6).")
                        dados_passo["hipotese_gestor"] = st.text_area(
                            "Nossa posição antes da análise",
                            placeholder="Descreva sua posição independente sobre como resolver este caso...",
                            height=120,
                            value=step_dados_salvos.get("hipotese_gestor", ""),
                        )

                    elif passo_atual == 6:
                        # Auto-preencher com análise do P4 se campo vazio
                        _rec_salva = step_dados_salvos.get("recomendacao", "")
                        if not _rec_salva:
                            _p4_entry = _steps_data.get(4) or _steps_data.get("4") or {}
                            _p4_dados = _p4_entry.get("dados") or {}
                            _analise_p4 = _p4_dados.get("analise_result") or {}
                            _partes = []
                            if _analise_p4.get("resposta"):
                                _partes.append(_analise_p4["resposta"])
                            if _analise_p4.get("acao_recomendada"):
                                _partes.append(f"Ação recomendada: {_analise_p4['acao_recomendada']}")
                            if _analise_p4.get("impacto_financeiro"):
                                _partes.append(f"Impacto financeiro: {_analise_p4['impacto_financeiro']}")
                            if _analise_p4.get("fundamento_legal"):
                                _partes.append(f"Base legal: {', '.join(_analise_p4['fundamento_legal'])}")
                            # Fallback: campos do SYSTEM_PROMPT antigo
                            if not _partes:
                                if _analise_p4.get("contra_tese"):
                                    _partes.append(_analise_p4["contra_tese"])
                                if _analise_p4.get("disclaimer"):
                                    _partes.append(_analise_p4["disclaimer"])
                            _rec_salva = "\n\n".join(_partes)

                        if _rec_salva:
                            st.info("Recomendação gerada automaticamente pelo TaxMind com base na análise do P4. Edite se necessário antes de avançar.")
                        else:
                            st.warning("Não foi possível recuperar a análise do P4. Preencha a recomendação manualmente ou volte ao P4 e refaça a análise.")
                        dados_passo["recomendacao"] = st.text_area(
                            "Recomendação TaxMind",
                            height=200,
                            value=_rec_salva,
                        )

                    elif passo_atual == 7:
                        st.warning("⚠️ A decisão final será comparada com a recomendação da IA para verificação de independência decisória.")
                        dados_passo["decisao_final"] = st.text_area(
                            "Decisão tomada",
                            height=120,
                            value=step_dados_salvos.get("decisao_final", ""),
                        )
                        dados_passo["decisor"] = st.text_input("Responsável pela decisão", value=step_dados_salvos.get("decisor", ""))

                    elif passo_atual == 8:
                        dados_passo["resultado_real"] = st.text_area("O que aconteceu na prática", height=80, value=step_dados_salvos.get("resultado_real", ""))
                        dados_passo["data_revisao"] = st.text_input(
                            "Data para revisão",
                            placeholder="dd-mm-aaaa",
                            help="Formato: dia-mês-ano. Ex: 01-09-2025",
                            value=step_dados_salvos.get("data_revisao", ""),
                        )

                    elif passo_atual == 9:
                        dados_passo["aprendizado_extraido"] = st.text_area(
                            "O que aprendemos com este caso",
                            placeholder="Registre o aprendizado para casos futuros...",
                            height=100,
                            value=step_dados_salvos.get("aprendizado_extraido", ""),
                        )

                    # BUG-13 — botão diferente no passo terminal P9
                    PASSO_TERMINAL = 9
                    col_av, col_vo = st.columns([2, 1])
                    with col_av:
                        _label_btn = "✅ Concluir Caso" if passo_atual == PASSO_TERMINAL else "Avançar →"
                        btn_avancar = st.form_submit_button(_label_btn, type="primary")
                    with col_vo:
                        btn_voltar = st.form_submit_button("← Voltar", disabled=(passo_atual == PASSO_TERMINAL))

                if not _caso_concluido and (btn_avancar or btn_voltar):
                    acao = "avancar" if btn_avancar else "voltar"
                    # BUG-12 — validar data em P8 antes de chamar API
                    if btn_avancar and passo_atual == 8:
                        _data_rev = dados_passo.get("data_revisao", "")
                        if _data_rev and not re.match(r"^\d{2}-\d{2}-\d{4}$", _data_rev):
                            st.error("Data inválida. Use o formato dd-mm-aaaa")
                            st.stop()

                    try:
                        r2 = httpx.post(
                            f"{API_BASE}/v1/cases/{case_id_input}/steps/{passo_atual}",
                            json={"dados": dados_passo, "acao": acao},
                            timeout=60,
                        )
                    except httpx.TimeoutException:
                        st.error("O servidor demorou a responder. Recarregue o caso e tente novamente.")
                        st.stop()
                    except httpx.ConnectError:
                        st.error("API offline.")
                        st.stop()
                    except httpx.HTTPError as e:
                        st.error(f"Erro de comunicação: {e}")
                        st.stop()

                    if r2.status_code == 422:
                        st.error(f"Erro de validação: {r2.json().get('detail', '')}")
                    elif r2.status_code != 200:
                        st.error(f"Erro {r2.status_code}: {r2.text[:200]}")
                    else:
                        d2 = r2.json()
                        novo_passo = d2["passo"]

                        if passo_atual == 9:
                            st.success("✅ **Caso concluído com sucesso!**")
                            st.balloons()
                            st.info(
                                "**Próximos passos:**\n\n"
                                "- Acesse a aba **Documentos** para gerar o Dossiê de Decisão ou outros documentos formais\n"
                                "- Volte à aba **Consultar** para fazer novas análises\n"
                                "- Ou crie um **novo caso** no Protocolo P1→P9"
                            )
                        else:
                            st.success(f"✅ Avançado para {PASSO_NOME.get(novo_passo, str(novo_passo))}")

                        # Exibir alerta de independência decisória se presente
                        carimbo = d2.get("carimbo")
                        if carimbo and carimbo.get("alerta"):
                            st.warning(f"🔔 **Alerta de independência decisória** — {carimbo['mensagem']}")
                            st.caption(f"Similaridade com recomendação da IA: {carimbo['score_similaridade']:.0%} · alert_id={carimbo['alert_id']}")

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
                                            st.success("Independência decisória confirmada e registrada.")
                                        else:
                                            st.error(rc.json().get("detail", rc.text[:200]))
                                    except httpx.ConnectError:
                                        st.error("API offline.")

                        # Forçar recarga do caso
                        st.session_state["_proto_case_id"] = case_id_input
                        st.rerun()


# ===========================================================================
# ABA 4 — Documentos Acionáveis
# ===========================================================================
CLASSE_BADGE = {
    "alerta":                  ("🔔", "#FF6B35"),
    "nota_trabalho":           ("📝", "#4A90D9"),
    "recomendacao_formal":     ("📋", "#2ECC71"),
    "dossie_decisao":          ("📁", "#9B59B6"),
    "material_compartilhavel": ("📤", "#F39C12"),
}
CLASSE_LABEL = {
    "alerta":                  "Alerta",
    "nota_trabalho":           "Nota de Trabalho",
    "recomendacao_formal":     "Recomendação Formal",
    "dossie_decisao":          "Dossiê de Decisão",
    "material_compartilhavel": "Material para Compartilhamento",
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
STAKEHOLDER_LABEL = {
    "cfo":       "CFO / Financeiro",
    "juridico":  "Jurídico",
    "compras":   "Compras",
    "auditoria": "Auditoria",
    "diretoria": "Diretoria",
    "externo":   "Externo",
}
CLASSES_OPCOES = [
    "alerta", "nota_trabalho", "recomendacao_formal",
    "dossie_decisao", "material_compartilhavel",
]

with aba4:
    st.title("Documentos Acionáveis")
    st.caption(
        "Gere, aprove e compartilhe documentos tributários estruturados vinculados ao Protocolo P1→P9. "
        "Aviso legal obrigatório e não removível em toda saída."
    )

    col_esq, col_dir = st.columns([1, 3])

    with col_esq:
        st.subheader("Filtros")
        case_id_out = st.number_input("Número do caso", min_value=1, step=1, value=1, key="out_case_id")
        filtro_classe = st.multiselect(
            "Tipo de documento", options=CLASSES_OPCOES,
            format_func=lambda x: CLASSE_LABEL.get(x, x),
            default=CLASSES_OPCOES, key="out_filtro_classe",
        )
        filtro_status = st.multiselect(
            "Status", options=["rascunho", "gerado", "aprovado", "publicado", "revogado"],
            default=["gerado", "aprovado", "publicado"],
        )
        carregar_outputs = st.button("Carregar Documentos", type="primary")

        st.divider()
        st.subheader("Gerar Documento")
        with st.form("form_gerar_output"):
            classe_sel = st.selectbox(
                "Tipo de documento",
                options=CLASSES_OPCOES,
                format_func=lambda x: CLASSE_LABEL.get(x, x),
            )
            stk_sel = st.multiselect(
                "Público-alvo",
                options=STAKEHOLDERS_OPCOES,
                format_func=lambda x: STAKEHOLDER_LABEL.get(x, x),
            )

            # Campos condicionais por classe (mostrar todos — simplificado)
            query_out = st.text_area("Consulta (Nota de Trabalho / Recomendação Formal)", height=60,
                placeholder="Ex: Alíquota IBS para serviços de saúde")
            titulo_out = st.text_input("Título (Alerta)",
                placeholder="Ex: Alerta prazo recolhimento IBS")
            contexto_out = st.text_area("Contexto (Alerta)", height=60)
            mat_out = st.slider("Nível de prioridade (Alerta)", min_value=1, max_value=5, value=3)
            base_id_out = st.number_input("ID do documento base (Material Compartilhável)", min_value=0, step=1, value=0)

            gerar_btn = st.form_submit_button("Gerar Documento", type="primary")

        if gerar_btn:
            # Validação de campos obrigatórios por tipo de documento
            if classe_sel == "alerta":
                _campos_faltando = []
                if not titulo_out.strip():
                    _campos_faltando.append("Título")
                if not contexto_out.strip():
                    _campos_faltando.append("Contexto")
                if _campos_faltando:
                    st.error(f"Preencha os campos obrigatórios para Alerta: **{', '.join(_campos_faltando)}**")
                    st.stop()
            elif classe_sel in ("nota_trabalho", "recomendacao_formal"):
                _tipo_label = CLASSE_LABEL.get(classe_sel, classe_sel)
                if not query_out.strip():
                    st.error(f"O campo **Consulta** é obrigatório para {_tipo_label}. Informe a pergunta que o TaxMind deve analisar.")
                    st.stop()
            elif classe_sel == "material_compartilhavel":
                if base_id_out <= 0:
                    st.error("Informe o **ID do documento base** (Recomendação Formal ou Dossiê aprovado) para gerar o Material Compartilhável.")
                    st.stop()
                if not stk_sel:
                    st.error("Selecione ao menos um **público-alvo** para o Material Compartilhável.")
                    st.stop()

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
                    classe_nome = CLASSE_LABEL.get(d["classe"], d["classe"])
                    st.success(f"{emoji} {classe_nome} **#{d['id']}** gerado — {d['titulo'][:60]}")
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
                    st.warning(f"Não foi possível carregar documentos: {ro.text[:200]}")
                else:
                    outputs = ro.json()
                    # Filtrar por classe e status
                    outputs = [
                        o for o in outputs
                        if o["classe"] in filtro_classe and o["status"] in filtro_status
                    ]
                    if not outputs:
                        st.info("Nenhum documento encontrado com os filtros selecionados.")
                    else:
                        st.caption(f"{len(outputs)} documento(s) encontrado(s)")
                        for out in outputs:
                            emoji, cor = CLASSE_BADGE.get(out["classe"], ("📄", "#888"))
                            classe_nome = CLASSE_LABEL.get(out["classe"], out["classe"])
                            estrelas = ESTRELAS.get(out.get("materialidade") or 3, "★★★☆☆")
                            status_badge = STATUS_COR.get(out["status"], "⚪")

                            with st.expander(
                                f"{emoji} [{out['id']}] {out['titulo'][:70]}  |  "
                                f"{status_badge} {out['status']}  |  {estrelas}",
                                expanded=False,
                            ):
                                st.caption(
                                    f"Tipo: {classe_nome} · Etapa: P{out['passo_origem']} · "
                                    f"Criado: {str(out.get('created_at', ''))[:19]}"
                                )

                                # Conteúdo principal
                                conteudo = out.get("conteudo", {})
                                _CHAVE_LABEL = {
                                    "recomendacao_principal": "Recomendação principal",
                                    "resposta": "Análise",
                                    "decisao_final": "Decisão final",
                                    "contexto": "Contexto",
                                    "hipotese_gestor": "Hipótese do gestor",
                                }
                                for chave in ["recomendacao_principal", "resposta", "decisao_final",
                                              "contexto", "hipotese_gestor"]:
                                    if conteudo.get(chave):
                                        st.markdown(f"**{_CHAVE_LABEL.get(chave, chave)}**")
                                        st.write(conteudo[chave])
                                        break

                                if conteudo.get("fundamento_legal"):
                                    st.markdown("**Base legal**")
                                    for art in conteudo["fundamento_legal"]:
                                        st.write(f"- {art}")

                                # Aviso legal em destaque (não colapsável)
                                st.warning(f"⚠️ **Aviso legal:**\n\n{out['disclaimer']}")

                                # Views por público-alvo
                                views = out.get("stakeholder_views", [])
                                if views:
                                    st.markdown("**Visões por público-alvo**")
                                    tabs_labels = [STAKEHOLDER_LABEL.get(v["stakeholder"], v["stakeholder"].upper()) for v in views]
                                    stk_tabs = st.tabs(tabs_labels)
                                    for tab, view in zip(stk_tabs, views):
                                        with tab:
                                            st.write(view["resumo"])

                                if out.get("versao_prompt"):
                                    st.divider()
                                    st.caption(f"Detalhes técnicos — Versão da análise: `{out['versao_prompt']}` · Base: `{out.get('versao_base','')}`")

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
                                            "Público-alvo (Material Compartilhável)", STAKEHOLDERS_OPCOES,
                                            format_func=lambda x: STAKEHOLDER_LABEL.get(x, x),
                                            key=f"c5stk_{out['id']}"
                                        )
                                        if st.button("📤 Gerar Material para Compartilhamento", key=f"c5_{out['id']}"):
                                            if not stk_c5:
                                                st.warning("Selecione ao menos 1 público-alvo.")
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
                                                        st.success(f"Material para Compartilhamento #{rc5.json()['id']} gerado!")
                                                        st.rerun()
                                                    else:
                                                        st.error(rc5.json().get("detail", rc5.text[:200]))
                                                except httpx.ConnectError:
                                                    st.error("API offline.")


# ===========================================================================
# ABA 5 — Qualidade do Sistema
# ===========================================================================
MODEL_DEV_UI = "claude-haiku-4-5-20251001"
PROMPT_VERSION_UI = "v1.0.0-sprint2"

with aba5:
    st.title("Qualidade do Sistema")
    st.caption("Monitoramento contínuo, detecção de variações e validação automática do TaxMind Light.")

    # ------ Linha 1 — KPIs ------
    st.subheader("Indicadores — Últimos 7 dias")
    try:
        rm = httpx.get(f"{API_BASE}/v1/observability/metrics", params={"days": 7}, timeout=5)
        resumo = rm.json().get("resumo", {}) if rm.status_code == 200 else {}
    except Exception:
        resumo = {}

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        val = resumo.get("taxa_alucinacao")
        st.metric(
            "Respostas sem fundamentação",
            f"{val*100:.1f}%" if val is not None else "—",
            delta=None,
            help="% de respostas bloqueadas pelas verificações de integridade",
        )
    with kpi2:
        val = resumo.get("p95_latencia_ms")
        st.metric("Tempo de resposta p95", f"{val/1000:.1f}s" if val is not None else "—")
    with kpi3:
        val = resumo.get("pct_scoring_alto")
        st.metric("% Análises com alta confiança", f"{val*100:.1f}%" if val is not None else "—")
    with kpi4:
        val = resumo.get("total_interacoes")
        st.metric("Total de consultas", str(val) if val is not None else "0")

    st.divider()

    # ------ Linha 2 — Gráficos ------
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("Tempo de resposta (30 dias)")
        try:
            rm30 = httpx.get(f"{API_BASE}/v1/observability/metrics", params={"days": 30}, timeout=5)
            metrics_list = rm30.json().get("metrics", []) if rm30.status_code == 200 else []
        except Exception:
            metrics_list = []

        if metrics_list:
            lat_avg = [m.get("avg_latencia_ms") for m in metrics_list]
            lat_p95 = [m.get("p95_latencia_ms") for m in metrics_list]
            st.line_chart({"Média": [v for v in lat_avg if v],
                           "p95":   [v for v in lat_p95 if v]})
        else:
            st.info("Sem dados de tempo de resposta disponíveis.")

    with col_g2:
        st.subheader("Bloqueios por tipo de verificação")
        if metrics_list:
            mecanismos = {}
            _BLOQUEIO_LABEL = {
                "taxa_bloqueio_m1": "Artigo inexistente",
                "taxa_bloqueio_m2": "Norma revogada",
                "taxa_bloqueio_m3": "Tema não pertinente",
                "taxa_bloqueio_m4": "Inconsistência",
            }
            for key in ("taxa_bloqueio_m1", "taxa_bloqueio_m2", "taxa_bloqueio_m3", "taxa_bloqueio_m4"):
                vals = [m.get(key) for m in metrics_list if m.get(key) is not None]
                mecanismos[_BLOQUEIO_LABEL[key]] = sum(vals)/len(vals) if vals else 0
            st.bar_chart(mecanismos)
        else:
            st.info("Sem dados de bloqueio disponíveis.")

    st.divider()

    # ------ Linha 3 — Alertas de variação ------
    st.subheader("Alertas de variação de comportamento")
    col_d1, col_d2 = st.columns([3, 1])
    with col_d2:
        pv_drift = st.text_input("Versão da análise", value=PROMPT_VERSION_UI, key="pv_drift")
        st.button("Atualizar")

    try:
        rd = httpx.get(f"{API_BASE}/v1/observability/drift",
                       params={"prompt_version": pv_drift}, timeout=5)
        drift_alerts = rd.json() if rd.status_code == 200 else []
    except Exception:
        drift_alerts = []

    _METRICA_LABEL = {
        "avg_latencia_ms":       "Tempo médio de resposta",
        "pct_scoring_alto":      "% análises com alta confiança",
        "pct_contra_tese":       "% análises com posição contrária",
        "pct_grounding_presente":"% análises com base legal citada",
        "taxa_bloqueio_m1":      "Bloqueios: artigo inexistente",
        "taxa_bloqueio_m2":      "Bloqueios: norma revogada",
        "taxa_bloqueio_m3":      "Bloqueios: tema não pertinente",
        "taxa_bloqueio_m4":      "Bloqueios: inconsistência interna",
    }

    if not drift_alerts:
        st.success("Nenhum alerta de variação ativo.")
    else:
        st.warning(f"⚠️ {len(drift_alerts)} alerta(s) ativo(s)")
        for alert in drift_alerts:
            metrica_nome = _METRICA_LABEL.get(alert["metrica"], alert["metrica"])
            with st.expander(f"🔔 {metrica_nome} — {float(alert['desvios_padrao']):.2f}σ de variação"):
                st.write(f"**Referência:** {float(alert['valor_baseline']):.4f} → **Atual:** {float(alert['valor_atual']):.4f}")
                st.caption(f"Detectado em: {str(alert.get('detectado_em',''))[:19]}")
                with st.form(f"form_resolve_{alert['id']}"):
                    obs = st.text_input("Observação")
                    if st.form_submit_button("✅ Marcar como resolvido"):
                        try:
                            rr = httpx.post(
                                f"{API_BASE}/v1/observability/drift/{alert['id']}/resolver",
                                json={"observacao": obs or "Resolvido via painel"},
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

    # ------ Linha 4 — Validação automática ------
    st.subheader("Validação automática de desempenho")
    with st.form("form_regression"):
        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            pv_reg = st.text_input("Versão da análise", value=PROMPT_VERSION_UI)
        with col_r2:
            mid_reg = st.text_input("Motor de análise", value=MODEL_DEV_UI)
        with col_r3:
            bv_reg = st.text_input("Referência de desempenho", value=PROMPT_VERSION_UI)
        run_reg = st.form_submit_button("▶ Validar desempenho", type="primary")
        st.caption("⚠️ Executa análises reais — pode levar até 2 minutos.")

    if run_reg:
        with st.spinner("Executando validação (5 casos)..."):
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
                ("Precisão das citações legais",       res["precisao_citacao"],      "≥ 90%", res["precisao_citacao"] >= 0.90),
                ("Respostas sem fundamentação",         res["taxa_alucinacao"],        "≤ 5%",  res["taxa_alucinacao"] <= 0.05),
                ("Acurácia das recomendações",          res["acuracia_recomendacao"], "≥ 80%", res["acuracia_recomendacao"] >= 0.80),
                ("Tempo de resposta p95 (s)",           res["latencia_p95"],          "≤ 15s", res["latencia_p95"] <= 15.0),
                ("Cobertura de posição contrária",      res["cobertura_contra_tese"], "≥ 80%", res["cobertura_contra_tese"] >= 0.80),
            ]
            for nome, valor, threshold, ok in metricas_res:
                icon = "✅" if ok else "❌"
                if threshold.endswith("s"):
                    st.write(f"{icon} **{nome}**: {valor:.2f}s (limite: {threshold})")
                else:
                    st.write(f"{icon} **{nome}**: {valor:.1%} (limite: {threshold})")
        elif rr is not None:
            st.error(f"Erro: {rr.text[:300]}")

    st.divider()

    # ------ Linha 5 — Gestão de referência ------
    st.subheader("Gestão de referência de desempenho")
    with st.form("form_baseline"):
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            pv_base = st.text_input("Versão da análise", value=PROMPT_VERSION_UI, key="pv_base")
        with col_b2:
            mid_base = st.text_input("Motor de análise", value=MODEL_DEV_UI, key="mid_base")
        reg_base = st.form_submit_button("📊 Registrar referência de desempenho", type="primary")

    if reg_base:
        try:
            rb = httpx.post(
                f"{API_BASE}/v1/observability/baseline",
                json={"prompt_version": pv_base, "model_id": mid_base},
                timeout=10,
            )
            if rb.status_code == 201:
                d = rb.json()
                st.success(f"Referência registrada — {d.get('sample_size', '?')} dias de dados")
                st.json({k: round(v, 4) if isinstance(v, float) else v
                         for k, v in d.items() if v is not None})
            else:
                st.error(rb.json().get("detail", rb.text[:200]))
        except httpx.ConnectError:
            st.error("API offline.")
