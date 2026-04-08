"""
ui/app.py — Interface Streamlit para Tribus-AI.
Aba 1: Consultar · Aba 2: Adicionar Norma · Aba 3: Protocolo de Decisão · Aba 4: Documentos · Aba 5: Qualidade do Sistema
Consome a FastAPI em http://localhost:8000.
"""

import os
import re
import sys
import time

import httpx
import streamlit as st
from dotenv import load_dotenv
from src.cognitive.metodos import METODOS_ANALISE, MAX_METODOS, sugerir_metodos
from src.cognitive.detector_carimbo import detectar_carimbo as _detectar_carimbo
from ui.components.grau_consolidacao import exibir_painel_governanca
from ui.components.qualificacao_fatica import coletar_qualificacao_fatica
from ui.pages.simulador_carga import render_simulador_carga
from ui.pages.simulador_split_payment import render_simulador_split_payment
from ui.pages.monitor_creditos import render_monitor_creditos
from ui.pages.ciclo_pos_decisao import render_ciclo_pos_decisao
from src.cognitive.monitoramento_p6 import ativar_monitoramento_p6

load_dotenv()

# Garantir que a raiz do projeto está no path para imports de auth/pages/components
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8020")

# SEC-08: chave interna para autenticar chamadas Streamlit → FastAPI
_API_INTERNAL_KEY = os.getenv("API_INTERNAL_KEY", "")
_INTERNAL_HEADERS = {"X-API-Key": _API_INTERNAL_KEY}


def _api_get(url: str, **kw):
    """Wrapper httpx.get que injeta o header X-API-Key."""
    kw.setdefault("headers", {}).update(_INTERNAL_HEADERS)
    return httpx.get(url, **kw)


def _api_post(url: str, **kw):
    """Wrapper httpx.post que injeta o header X-API-Key."""
    kw.setdefault("headers", {}).update(_INTERNAL_HEADERS)
    return httpx.post(url, **kw)


def _api_patch(url: str, **kw):
    """Wrapper httpx.patch que injeta o header X-API-Key."""
    kw.setdefault("headers", {}).update(_INTERNAL_HEADERS)
    return httpx.patch(url, **kw)


def _api_delete(url: str, **kw):
    """Wrapper httpx.delete que injeta o header X-API-Key."""
    kw.setdefault("headers", {}).update(_INTERNAL_HEADERS)
    return httpx.delete(url, **kw)

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
    page_title="Tribus-AI",
    page_icon="⚖️",
    layout="wide",
)

# ─── AUTH CONFIG ──────────────────────────────────────────────────────────────
# BYPASS_AUTH = True  → período de testes (sem login)
# BYPASS_AUTH = False → produção (login obrigatório)
# Para reativar o login: alterar para False e reiniciar o app.
BYPASS_AUTH = False

# ─── IMPORTS DO MÓDULO ADMIN ──────────────────────────────────────────────────
from pages.login import render_login, sessao_valida
from components.trial_banner import render_trial_banner, render_header_com_logout


# ─── GUARD DE SESSÃO ─────────────────────────────────────────────────────────
def _verificar_autenticacao():
    """Guard de sessão: redireciona para login se não autenticado."""
    if BYPASS_AUTH:
        # Modo teste: injetar sessão anônima sem autenticação
        if "user_id" not in st.session_state:
            st.session_state["auth_token"]    = "bypass-test-token"
            st.session_state["user_id"]       = "00000000-0000-0000-0000-000000000000"
            st.session_state["user_nome"]     = "Usuário Teste"
            st.session_state["user_email"]    = "teste@tribus-ai.com.br"
            st.session_state["user_perfil"]   = "USER"
            st.session_state["user_is_admin"] = False
            st.session_state["primeiro_uso"]  = None
        return  # pula o guard completamente

    if not sessao_valida():
        render_login()
        st.stop()

_verificar_autenticacao()

# ─── CONTROLE DE ACESSO POR BILLING ───────────────────────────────────────────
# Ativo apenas em modo produção (BYPASS_AUTH=False)
if not BYPASS_AUTH:
    from src.billing.access import tenant_tem_acesso, dias_restantes_trial
    _tenant = st.session_state.get("tenant", {})
    _tem_acesso, _motivo = tenant_tem_acesso(_tenant)
    if not _tem_acesso:
        st.error({
            "trial_expired":  "Seu período de teste encerrou. Assine um plano para continuar.",
            "payment_failed": "Houve um problema com seu pagamento. Verifique e tente novamente.",
            "canceled":       "Sua assinatura foi cancelada. Entre em contato para reativar.",
        }.get(_motivo, "Acesso não autorizado."))
        st.markdown("[Falar com suporte](mailto:suporte@tribus-ai.com.br)")
        st.stop()
    _dias = dias_restantes_trial(_tenant)
    if _dias is not None and _dias <= 7:
        st.warning(f"⚠️ Seu trial encerra em {_dias} dia(s). Assine agora para não perder o acesso.")

# ─── HEADER ───────────────────────────────────────────────────────────────────
# Header e banner apenas em modo produção
if not BYPASS_AUTH:
    render_header_com_logout()
    render_trial_banner()

# ────────────────────────────────────────────────────────────────────────────────

_TOOLTIP_CSS_INJECTED = False


def _inject_tooltip_css() -> None:
    """Injeta CSS de tooltip uma única vez."""
    global _TOOLTIP_CSS_INJECTED  # noqa: PLW0603
    if _TOOLTIP_CSS_INJECTED:
        return
    st.markdown("""
    <style>
    .tm-tip{display:inline-block;position:relative}
    .tm-tip .tm-icon{cursor:help;color:#999;font-size:0.8em;
        border:1px solid #666;border-radius:50%;padding:0 5px;margin-left:4px;
        font-weight:bold;user-select:none}
    .tm-tip .tm-box{visibility:hidden;opacity:0;
        background:#1e1e1e;color:#e0e0e0;border:1px solid #444;
        text-align:left;border-radius:8px;padding:10px 14px;
        position:absolute;z-index:9999;bottom:calc(100% + 8px);left:0;
        min-width:280px;max-width:420px;font-size:0.82em;font-weight:400;
        line-height:1.5;box-shadow:0 4px 12px rgba(0,0,0,0.4);
        transition:opacity 0.15s ease-in-out,visibility 0.15s ease-in-out}
    .tm-tip:hover .tm-box{visibility:visible;opacity:1}
    </style>
    """, unsafe_allow_html=True)
    _TOOLTIP_CSS_INJECTED = True


def _lbl(texto: str, dica: str) -> None:
    """Renderiza label com (?) e tooltip CSS imediatamente ao lado do texto."""
    _inject_tooltip_css()
    st.markdown(
        f'{texto} <span class="tm-tip">'
        f'<span class="tm-icon">?</span>'
        f'<span class="tm-box">{dica}</span>'
        f'</span>',
        unsafe_allow_html=True,
    )


# --- Buscar normas disponíveis do /v1/health ---
_FALLBACK_NORMAS = {
    "EC 132/2023": "EC_132",
    "LC 214/2025": "LC_214",
    "LC 227/2026": "LC_227",
}


@st.cache_data(ttl=30)
def _buscar_normas_disponiveis() -> dict[str, str]:
    """Busca normas da API. Se falhar, retorna fallback e limpa cache na próxima."""
    import time as _t
    for _tentativa in range(3):
        try:
            hr = _api_get(f"{API_BASE}/v1/health", timeout=10)
            normas = hr.json().get("normas", [])
            if normas:
                return {n["nome"]: n["codigo"] for n in normas}
        except Exception:
            if _tentativa < 2:
                _t.sleep(2)
    return _FALLBACK_NORMAS


# --- Alerta global de creditos ---
@st.cache_data(ttl=60)
def _verificar_creditos():
    """Consulta saldo de creditos de API a cada 60s."""
    try:
        resp = _api_get(f"{API_BASE}/v1/credits", timeout=3)
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
st.sidebar.title("⚖️ Tribus-AI")
st.sidebar.caption("Reforma Tributária · Base dinâmica de normas")

if _creditos:
    saldo = _creditos.get("saldo_restante", 0)
    limite = _creditos.get("limite", 0)
    pct = (saldo / limite * 100) if limite > 0 else 0
    gasto = _creditos.get("total_gasto", 0)
    st.sidebar.metric("Consumo estimado (API)", f"US$ {gasto:.2f}", delta=f"{pct:.0f}% do limite usado")
    st.sidebar.divider()

# --- Notificação de novos documentos detectados ---
@st.cache_data(ttl=120)
def _contar_docs_novos():
    try:
        resp = _api_get(f"{API_BASE}/v1/monitor/contagem", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("pendentes", 0)
    except Exception:
        pass
    return 0

_docs_novos = _contar_docs_novos()
if _docs_novos > 0:
    st.sidebar.warning(f"📄 {_docs_novos} documento(s) novo(s) detectado(s) nas fontes oficiais")
    st.sidebar.divider()

normas_disponiveis = _buscar_normas_disponiveis()
# Se retornou o fallback (3 normas), limpar cache para tentar de novo no próximo reload
if len(normas_disponiveis) <= len(_FALLBACK_NORMAS):
    _buscar_normas_disponiveis.clear()

norma_filter = None

top_k = st.sidebar.slider(
    "Trechos consultados", min_value=3, max_value=10, value=5,
    help="Quantidade de trechos legislativos que o sistema recupera para fundamentar cada análise. Mais trechos = resposta mais completa, mas potencialmente mais lenta.",
)

incluir_outros = st.sidebar.checkbox(
    "Incluir documentos adicionais (tipo Outro)",
    value=False,
    help="Por padrão, PDFs adicionados manualmente ficam fora do RAG. "
         "Marque para incluí-los nas consultas.",
)

st.sidebar.divider()

# Health check na sidebar — reusa cache de _buscar_normas_disponiveis (evita 2a chamada)
@st.cache_data(ttl=30)
def _health_check():
    import time as _time
    for _attempt in range(3):
        try:
            hr = _api_get(f"{API_BASE}/v1/health", timeout=10)
            if hr.status_code == 200:
                return hr.json()
        except (httpx.ConnectError, httpx.TimeoutException):
            if _attempt < 2:
                _time.sleep(2)
            continue
        except Exception:
            return None
    return None

_hdata = _health_check()
if _hdata:
    st.sidebar.success(
        f"API online · {_hdata['chunks_total']:,} trechos legislativos · "
        f"{len(_hdata.get('normas', []))} normas"
    )
else:
    st.sidebar.warning("API indisponível — recarregue a página")

# --- Abas ---
is_admin = st.session_state.get("user_is_admin", False)

if is_admin:
    aba1, aba2, aba3, aba4, aba5, tab_admin = st.tabs([
        "Consultar", "Adicionar Norma", "Protocolo de Decisão", "Documentos", "Simuladores", "⚙️ Admin"
    ])
else:
    aba1, aba2, aba3, aba4, aba5 = st.tabs([
        "Consultar", "Adicionar Norma", "Protocolo de Decisão", "Documentos", "Simuladores"
    ])
    tab_admin = None


# ===========================================================================
# ABA 1 — Consultar
# ===========================================================================
with aba1:
    st.title("Tribus-AI — Reforma Tributária")
    st.caption("Análise tributária com base legislativa verificada · Esta análise não substitui a avaliação do seu time fiscal")

    _lbl("Sua consulta", "Digite sua dúvida tributária relacionada à Reforma Tributária (IBS, CBS, ICMS, alíquotas, etc.). O sistema buscará na legislação e gerará uma análise fundamentada.")
    query = st.text_area(
        "Sua consulta",
        placeholder="Insira aqui sua consulta ou dúvida sobre a Reforma Tributária",
        height=100,
        label_visibility="collapsed",
    )

    _fatos_consultar = coletar_qualificacao_fatica(key_prefix="consul")

    if st.button("Analisar", type="primary", disabled=not query.strip()):
        with st.spinner("Analisando..."):
            try:
                resp = _api_post(
                    f"{API_BASE}/v1/analyze",
                    json={
                        "query": query,
                        "norma_filter": norma_filter,
                        "top_k": top_k,
                        "excluir_tipos": [] if incluir_outros else ["Outro"],
                        "user_id": st.session_state.get("user_id"),
                        "fatos_cliente": _fatos_consultar,
                    },
                    timeout=60,
                )
            except httpx.ConnectError:
                st.error("Não foi possível conectar à API. Verifique se o servidor FastAPI está rodando em localhost:8000.")
                st.stop()
            except httpx.TimeoutException:
                st.error("A API demorou demais para responder. Tente novamente com uma consulta mais curta ou recarregue a página.")
                st.stop()

        if resp.status_code == 400:
            err = resp.json()
            bloqueios = err.get("detail", {}).get("bloqueios", [])
            _tem_bl02 = any("BL-02" in b for b in bloqueios)

            if _tem_bl02:
                st.warning(
                    "⚠️ **Sua consulta não contém termos tributários reconhecidos.**\n\n"
                    "O Tribus-AI analisa questões relacionadas à Reforma Tributária "
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
            "consolidado":   "Entendimento consolidado",
            "em_disputa":    "Tema em disputa — risco moderado",
            "divergente":    "Tema em disputa — risco moderado",
            "sem_precedente":"Sem precedente — risco elevado",
            "indefinido":    "Sem precedente — risco elevado",
        }.get(grau, grau.capitalize())
        grau_icon = {
            "consolidado": "✅", "em_disputa": "⚠️", "divergente": "⚠️",
            "sem_precedente": "❓", "indefinido": "❓",
        }.get(grau, "")
        st.caption(f"Consenso de Mercado: {grau_icon} {grau_label}")

        exibir_painel_governanca(
            grau=data.get("grau_consolidacao", ""),
            forca_contra_tese=data.get("forca_corrente_contraria", ""),
            risco=data.get("risco_adocao", ""),
            scoring_confianca=data.get("scoring_confianca", ""),
        )

        if data["fundamento_legal"]:
            st.subheader("📋 Base legal")
            for art in data["fundamento_legal"]:
                st.write(f"- {art}")

        if data.get("contra_tese"):
            _forca = data.get("forca_corrente_contraria", "")
            _forca_label = {"Alta": "🔴 Alta", "Média": "🟡 Média", "Baixa": "🟢 Baixa"}.get(_forca, _forca)
            with st.expander(f"⚖️ Contra-tese {'— Força ' + _forca_label if _forca_label else ''}"):
                st.write(_sanitize_latex(data["contra_tese"]))
                if data.get("risco_adocao"):
                    st.warning(f"**Risco de adotar a posição recomendada:** {_sanitize_latex(data['risco_adocao'])}")

        _alertas_vig = data.get("alertas_vigencia", [])
        if _alertas_vig:
            with st.expander(f"⚠️ Alertas de Vigência ({len(_alertas_vig)})", expanded=True):
                for _av in _alertas_vig:
                    if _av.get("status") == "revogada":
                        st.error(_av["mensagem"])
                    else:
                        st.warning(_av["mensagem"])

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

    _lbl("Selecione o arquivo", "Faça upload do documento legislativo que deseja adicionar à base de conhecimento. Formatos aceitos: PDF, DOCX, XLSX, HTML, TXT, MD, CSV.")
    uploaded_file = st.file_uploader(
        "Selecione o arquivo",
        type=["pdf", "docx", "xlsx", "html", "htm", "txt", "md", "csv"],
        label_visibility="collapsed",
    )

    # Verificar duplicidade imediatamente após upload
    _dup_bloqueado = False
    if uploaded_file is not None:
        try:
            check_resp = _api_post(
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
        except (httpx.ConnectError, httpx.TimeoutException):
            pass  # Se a verificação falhar, permitir seguir normalmente
        except Exception:
            pass

    if _dup_bloqueado:
        st.stop()

    _lbl("Nome do documento", "Informe o nome oficial ou identificador do documento (tipo, número e ano).")
    nome_doc = st.text_input(
        "Nome do documento",
        label_visibility="collapsed",
    )
    _lbl("Tipo", "Classificação do documento: IN (Instrução Normativa), Resolução, Parecer, Manual ou Outro. Documentos do tipo 'Outro' ficam fora das consultas por padrão.")
    tipo_doc = st.selectbox(
        "Tipo",
        options=["IN", "Resolução", "Parecer", "Manual", "Outro"],
        label_visibility="collapsed",
    )

    st.info(
        "Após incluído, o documento estará disponível automaticamente "
        "nas consultas da Aba 1."
    )

    pode_ingerir = uploaded_file is not None and nome_doc.strip()

    if st.button("Incluir na base", type="primary", disabled=not pode_ingerir):
        # 1. Disparar ingest assíncrono (retorna imediatamente com job_id)
        try:
            resp = _api_post(
                f"{API_BASE}/v1/ingest/upload",
                files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                data={"nome": nome_doc.strip(), "tipo": tipo_doc},
                timeout=30,
            )
        except httpx.ConnectError:
            st.error("Não foi possível conectar à API.")
            st.stop()
        except httpx.TimeoutException:
            st.error("A API demorou demais para responder. Tente novamente.")
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
                poll = _api_get(f"{API_BASE}/v1/ingest/jobs/{job_id}", timeout=10)
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
        resp_normas = _api_get(f"{API_BASE}/v1/ingest/normas", timeout=10)
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
                                    del_resp = _api_delete(
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
    except (httpx.ConnectError, httpx.TimeoutException):
        st.warning("API indisponível ou demorando. Recarregue a página.")
    except Exception as e:
        st.warning(f"Erro ao carregar documentos: {e}")

    # --- Monitor de fontes oficiais ---
    st.divider()
    st.subheader("Monitor de Fontes Oficiais")
    st.caption(
        "Verifica DOU, Planalto, CGIBS, Portal NF-e e Receita Federal "
        "em busca de novos documentos sobre a Reforma Tributária."
    )

    if st.button("Verificar agora", type="secondary", key="btn_monitor_check"):
        with st.spinner("Consultando fontes oficiais..."):
            try:
                resp_mon = _api_post(f"{API_BASE}/v1/monitor/verificar", timeout=60)
                if resp_mon.status_code == 200:
                    mon_data = resp_mon.json()
                    total_novos = mon_data.get("total_novos", 0)
                    if total_novos > 0:
                        st.success(f"**{total_novos}** novo(s) documento(s) detectado(s)!")
                    else:
                        st.info("Nenhum documento novo encontrado.")
                    for r in mon_data.get("resultados", []):
                        icon = "✅" if not r["erro"] else "❌"
                        st.caption(
                            f"{icon} **{r['fonte']}**: "
                            f"{r['novos']} novos de {r['encontrados']} encontrados"
                            + (f" — erro: {r['erro']}" if r["erro"] else "")
                        )
                    _contar_docs_novos.clear()
                else:
                    st.error("Erro ao verificar fontes.")
            except httpx.ConnectError:
                st.error("API indisponível.")
            except Exception as e:
                st.error(f"Erro: {e}")

    # Listar documentos pendentes
    try:
        resp_pend = _api_get(f"{API_BASE}/v1/monitor/pendentes", timeout=10)
        if resp_pend.status_code == 200:
            pend_data = resp_pend.json()
            docs_pendentes = pend_data.get("documentos", [])
            if docs_pendentes:
                st.markdown(f"**{len(docs_pendentes)} documento(s) aguardando sua decisao:**")
                for doc in docs_pendentes:
                    with st.container():
                        col_doc, col_acoes = st.columns([4, 1])
                        with col_doc:
                            st.markdown(f"**{doc['titulo']}**")
                            detalhes = f"Fonte: {doc['fonte']}"
                            if doc.get("data_publicacao"):
                                detalhes += f" · {doc['data_publicacao']}"
                            st.caption(detalhes)
                            if doc.get("resumo"):
                                st.caption(doc["resumo"][:200])
                            if doc.get("url"):
                                st.markdown(f"[Abrir documento]({doc['url']})")
                        with col_acoes:
                            if st.button("Descartar", key=f"mon_desc_{doc['id']}", type="secondary"):
                                try:
                                    _api_patch(
                                        f"{API_BASE}/v1/monitor/documentos/{doc['id']}",
                                        json={"status": "descartado"},
                                        timeout=5,
                                    )
                                    _contar_docs_novos.clear()
                                    st.rerun()
                                except Exception:
                                    st.error("Erro ao descartar.")
    except Exception:
        pass  # Monitor opcional — nao bloquear se falhar


# ===========================================================================
# ABA 3 — Protocolo de Decisão (6 Passos)
# ===========================================================================
PASSO_NOME = {
    1: "Passo 1 · Registrar & Classificar",
    2: "Passo 2 · Estruturar riscos e dados",
    3: "Passo 3 · Análise tributária",
    4: "Passo 4 · Posição do gestor (hipótese)",
    5: "Passo 5 · Decidir",
    6: "Passo 6 · Ciclo Pós-Decisão",
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
    st.title("Protocolo de Decisão Tributária — 6 Passos")
    st.caption(
        "Registre, analise e documente decisões tributárias com rastreabilidade completa. "
        "Passo 4 (hipótese do gestor) deve ser concluído antes de ver a recomendação da IA (Passo 5 — Decidir)."
    )

    # ------ Seção: Criar novo caso ------
    with st.expander("➕ Criar Novo Caso", expanded=False):
        with st.form("form_criar_caso"):
            _lbl("Nome do caso (mín. 10 chars)", "Identificação única do caso. Deve ter no mínimo 10 caracteres e permitir reconhecer o caso rapidamente na lista.")
            titulo_caso = st.text_input("Nome do caso", label_visibility="collapsed")
            _lbl("Descreva o problema tributário", "Explique a questão tributária que precisa ser analisada, incluindo o contexto e as dúvidas principais.")
            descricao_caso = st.text_area("Descreva o problema", height=80, label_visibility="collapsed")
            _lbl("Situação atual da empresa", "Regime tributário, porte, setor de atuação e outras informações relevantes sobre a empresa.")
            contexto_fiscal = st.text_input("Situação atual", label_visibility="collapsed")
            submitted_criar = st.form_submit_button("Criar Caso", type="primary")

        if submitted_criar:
            if not titulo_caso.strip() or len(titulo_caso.strip()) < 10:
                st.error("O nome do caso deve ter pelo menos 10 caracteres.")
            elif not descricao_caso.strip() or not contexto_fiscal.strip():
                st.error("Preencha todos os campos.")
            else:
                try:
                    r = _api_post(
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
                except httpx.TimeoutException:
                    st.error("A API demorou demais para responder.")

    st.divider()

    # ------ Seção: Casos existentes ------
    st.subheader("Seus Casos")

    _proto_cases = []
    try:
        _proto_resp = _api_get(f"{API_BASE}/v1/cases", timeout=10)
        if _proto_resp.status_code == 200:
            _proto_cases = _proto_resp.json()
    except Exception:
        pass

    if _proto_cases:
        _proto_options = {
            f"#{c['case_id']}  |  {c['titulo'][:55]}  |  P{c['passo_atual']} — {STATUS_LABEL.get(c['status'], c['status'])}": c["case_id"]
            for c in _proto_cases
        }
        _lbl("Selecione um caso", "Escolha o caso que deseja visualizar ou continuar preenchendo. Cada caso passa por 6 etapas de análise.")
        _proto_sel = st.selectbox(
            "Selecione um caso",
            options=list(_proto_options.keys()),
            key="proto_case_select",
            label_visibility="collapsed",
        )
        case_id_input = _proto_options[_proto_sel]
    else:
        st.info("Nenhum caso encontrado. Crie um caso acima.")
        case_id_input = int(st.session_state.get("case_id_ativo", 1))

    _autoload = True
    if _proto_cases or st.session_state.get("_proto_case_id") == case_id_input:
        st.session_state["_proto_case_id"] = case_id_input
        try:
            r = _api_get(f"{API_BASE}/v1/cases/{case_id_input}", timeout=30)
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
                st.progress(1.0, text="Etapa 6/6 — Concluído")
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
                _lbl("Visualizar passo", "Navegue entre as 6 etapas do protocolo para revisar os dados registrados em cada passo.")
                _passo_vis = st.selectbox(
                    "Visualizar passo:",
                    options=[1, 2, 3, 4, 5, 6],
                    format_func=lambda p: PASSO_NOME.get(p, f"Passo {p}"),
                    key="passo_visualizar_readonly",
                    label_visibility="collapsed",
                )
                _step_ro = _steps_data_ro.get(_passo_vis) or _steps_data_ro.get(str(_passo_vis)) or {}
                _dados_ro = _step_ro.get("dados") or {}

                st.divider()

                if _passo_vis == 1:
                    st.subheader("Passo 1 — Registrar & Classificar")
                    st.caption("Título do caso")
                    st.info(_dados_ro.get("titulo", caso.get("titulo", "—")))
                    st.caption("Descrição do problema tributário")
                    st.markdown(_dados_ro.get("descricao") or "—")
                    st.caption("Situação atual da empresa")
                    st.markdown(_dados_ro.get("contexto_fiscal") or "—")
                    st.caption("Premissas declaradas")
                    _prems = _dados_ro.get("premissas", [])
                    if _prems:
                        for _p in _prems:
                            st.markdown(f"- {_p}")
                    else:
                        st.info("Nenhuma premissa registrada.")
                    st.caption("Período de referência")
                    st.info(_dados_ro.get("periodo_fiscal") or "—")

                elif _passo_vis == 2:
                    st.subheader("Passo 2 — Estruturar riscos e dados")
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

                elif _passo_vis == 3:
                    st.subheader("Passo 3 — Análise tributária (Tribus-AI)")
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
                            _forca_ro = _analise.get("forca_corrente_contraria", "")
                            _forca_ro_label = {"Alta": "🔴 Alta", "Média": "🟡 Média", "Baixa": "🟢 Baixa"}.get(_forca_ro, _forca_ro)
                            st.caption(f"Contra-tese {'— Força ' + _forca_ro_label if _forca_ro_label else ''}")
                            st.warning(_sanitize_latex(_analise["contra_tese"]))
                            if _analise.get("risco_adocao"):
                                st.caption("Risco de adotar a posição recomendada")
                                st.error(_sanitize_latex(_analise["risco_adocao"]))
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

                elif _passo_vis == 4:
                    st.subheader("Passo 4 — Posição do gestor (hipótese)")
                    st.caption("Posição independente registrada antes da recomendação da IA")
                    st.markdown(_dados_ro.get("hipotese_gestor") or "—")

                elif _passo_vis == 5:
                    st.subheader("Passo 5 — Decidir")
                    st.caption("Recomendação gerada pela IA (com base na análise do Passo 3)")
                    st.markdown(_sanitize_latex(_dados_ro.get("recomendacao") or "—"))
                    st.divider()
                    st.caption("Decisão tomada")
                    st.info(_dados_ro.get("decisao_final") or "—")
                    st.caption("Responsável pela decisão")
                    st.info(_dados_ro.get("decisor") or "—")

                elif _passo_vis == 6:
                    st.subheader("Passo 6 — Ciclo Pós-Decisão")
                    st.caption("O que aconteceu na prática")
                    st.markdown(_dados_ro.get("resultado_real") or "—")
                    st.caption("Data de revisão")
                    st.info(_dados_ro.get("data_revisao") or "—")
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
                st.progress((passo_atual - 1) / 5.0, text=f"Etapa {passo_atual}/6")

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

            # Passo 3: fluxo especial fora de form — chama a API diretamente sem colar JSON manualmente
            if _caso_concluido:
                pass  # Formulário não renderizado para caso concluído
            elif passo_atual == 3:
                # ── P4 PRIMEIRO: hipótese do gestor antes de ver a IA ──────────
                st.subheader("📝 Passo 4 — Sua posição antes da análise")
                st.info(
                    "Registre sua interpretação do caso **antes** de ver a recomendação do Tribus-AI. "
                    "Isso preserva sua independência decisória e previne viés de ancoragem."
                )
                _hipotese_key = f"_hipotese_p4_{case_id_input}"
                hipotese_p4 = st.text_area(
                    "Sua leitura do caso e inclinação decisória",
                    height=130,
                    key=_hipotese_key,
                    placeholder="Ex: Com base nas premissas levantadas, entendo que o crédito de IBS é aproveitável "
                                "neste caso. Minha inclinação é aprovar, mas há dúvida sobre o art. X da LC 214/2025...",
                    label_visibility="collapsed",
                )

                _hipotese_ok = bool(hipotese_p4 and hipotese_p4.strip())
                if not _hipotese_ok:
                    st.warning("⚠️ Registre sua posição acima para liberar a análise da IA.")

                st.divider()

                # ── P3: análise da IA — só liberada após hipótese preenchida ───
                st.subheader("🤖 Passo 3 — Análise do Tribus-AI")
                _lbl("Pergunta para o Tribus-AI", "Formule a pergunta tributária que deseja que o Tribus-AI analise com base na legislação. Quanto mais específica a pergunta, mais precisa será a análise.")
                query_analise = st.text_area(
                    "Pergunta",
                    height=80,
                    label_visibility="collapsed",
                )
                if st.button("Registrar posição e analisar →", type="primary", disabled=not _hipotese_ok):
                    if not query_analise or len(query_analise.strip()) < 10:
                        st.error("A consulta deve ter ao menos 10 caracteres.")
                    else:
                        with st.spinner("Analisando..."):
                            try:
                                # Ler dados salvos do P1 e P2
                                _p1_entry = _steps_data.get(1) or _steps_data.get("1") or {}
                                _p1_dados = _p1_entry.get("dados") or {}
                                _metodos_p1 = _p1_dados.get("metodos_selecionados", [])
                                _criticidade_p1 = _p1_dados.get("criticidade", "media")
                                _premissas_p1 = _p1_dados.get("premissas", [])
                                _fatos_p1_saved = _p1_dados.get("fatos_cliente", {})
                                _p2_entry = _steps_data.get(2) or _steps_data.get("2") or {}
                                _p2_dados = _p2_entry.get("dados") or {}
                                _riscos_p2 = _p2_dados.get("riscos", [])
                                resp = _api_post(
                                    f"{API_BASE}/v1/analyze",
                                    json={
                                        "query": query_analise,
                                        "excluir_tipos": [] if incluir_outros else ["Outro"],
                                        "case_id": case_id_input,
                                        "user_id": st.session_state.get("user_id"),
                                        "metodos_selecionados": _metodos_p1,
                                        "criticidade": _criticidade_p1,
                                        "premissas": _premissas_p1,
                                        "riscos_fiscais": _riscos_p2,
                                        "fatos_cliente": _fatos_p1_saved,
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
                                if analise.get("contra_tese"):
                                    _forca_p3 = analise.get("forca_corrente_contraria", "")
                                    _forca_p3_label = {"Alta": "🔴 Alta", "Média": "🟡 Média", "Baixa": "🟢 Baixa"}.get(_forca_p3, _forca_p3)
                                    with st.expander(f"⚖️ Contra-tese {'— Força ' + _forca_p3_label if _forca_p3_label else ''}"):
                                        st.write(_sanitize_latex(analise["contra_tese"]))
                                        if analise.get("risco_adocao"):
                                            st.warning(f"**Risco de adotar:** {_sanitize_latex(analise['risco_adocao'])}")
                                if analise.get("disclaimer"):
                                    st.warning(analise["disclaimer"])

                                exibir_painel_governanca(
                                    grau=analise.get("grau_consolidacao", ""),
                                    forca_contra_tese=analise.get("forca_corrente_contraria", ""),
                                    risco=analise.get("risco_adocao", ""),
                                    scoring_confianca=analise.get("scoring_confianca", ""),
                                )

                                _av_p3 = analise.get("alertas_vigencia", [])
                                if _av_p3:
                                    with st.expander(f"⚠️ Alertas de Vigência ({len(_av_p3)})", expanded=True):
                                        for _av in _av_p3:
                                            if _av.get("status") == "revogada":
                                                st.error(_av["mensagem"])
                                            else:
                                                st.warning(_av["mensagem"])

                                # Salvar P3 (avança passo_atual → 4)
                                step_resp = _api_post(
                                    f"{API_BASE}/v1/cases/{case_id_input}/steps/3",
                                    json={"dados": {"query_analise": query_analise, "analise_result": analise}, "acao": "avancar"},
                                    timeout=30.0,
                                )
                                step_resp.raise_for_status()

                                # Salvar P4 com hipótese já capturada (avança passo_atual → 5)
                                hip_resp = _api_post(
                                    f"{API_BASE}/v1/cases/{case_id_input}/steps/4",
                                    json={"dados": {"hipotese_gestor": hipotese_p4.strip()}, "acao": "avancar"},
                                    timeout=30.0,
                                )
                                hip_resp.raise_for_status()

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
                        # Passo 1: Registrar & Classificar (merged old P1 + P2)
                        _lbl("Nome do caso (mín. 10 chars)", "Identificação única do caso. Deve ter no mínimo 10 caracteres.")
                        dados_passo["titulo"] = st.text_input("Nome do caso", value=step_dados_salvos.get("titulo", caso["titulo"]), label_visibility="collapsed")
                        _lbl("Descreva o problema tributário", "Explique a questão tributária que precisa ser analisada, incluindo o contexto e as dúvidas principais.")
                        dados_passo["descricao"] = st.text_area("Descreva o problema", value=step_dados_salvos.get("descricao", ""), label_visibility="collapsed")
                        _lbl("Situação atual da empresa", "Regime tributário, porte, setor de atuação e outras informações relevantes sobre a empresa.")
                        dados_passo["contexto_fiscal"] = st.text_input("Situação atual", value=step_dados_salvos.get("contexto_fiscal", ""), label_visibility="collapsed")
                        _MIN_PREMISSAS = 3
                        _prem_salvas = step_dados_salvos.get("premissas", [])
                        _lbl("Premissas regulatórias ✱ (mín. 3)",
                             "Declare o que você assume como verdadeiro sobre a legislação aplicável. "
                             "Mínimo de 3 premissas obrigatórias antes de avançar para a análise. "
                             "Ex: 'Assumo alíquota de referência do IBS de X% conforme art. Y da LC 214/2025'")
                        _premissa_placeholders = [
                            "Ex: Assumo que a alíquota de CBS é de 8,8% conforme LC 214/2025",
                            "Ex: O crédito de IBS na entrada é aproveitável neste caso",
                            "Ex: A operação se enquadra no regime geral, sem regimes diferenciados",
                            "Ex: Assumo regulamentação do Comitê Gestor (LC 227/2026) permitindo o procedimento",
                            "Ex: O split payment já está ativo para este tipo de operação",
                        ]
                        _premissas_inputs = []
                        for _pi in range(5):
                            _req_mark = " ✱" if _pi < _MIN_PREMISSAS else " (opcional)"
                            _lbl_text = f"Premissa {_pi + 1}{_req_mark}"
                            _pv = _prem_salvas[_pi] if _pi < len(_prem_salvas) else ""
                            _premissas_inputs.append(
                                st.text_input(
                                    _lbl_text,
                                    value=_pv,
                                    placeholder=_premissa_placeholders[_pi],
                                    label_visibility="visible",
                                )
                            )
                        dados_passo["premissas"] = [p for p in _premissas_inputs if p.strip()]
                        if len(dados_passo["premissas"]) < _MIN_PREMISSAS:
                            st.warning(
                                f"⚠️ Declare ao menos {_MIN_PREMISSAS} premissas regulatórias. "
                                f"Preenchidas: {len(dados_passo['premissas'])} de {_MIN_PREMISSAS}."
                            )
                        _lbl("Período de referência", "Intervalo de tempo ao qual o caso se refere (mês/ano de início e fim).")
                        dados_passo["periodo_fiscal"] = st.text_input("Período", value=step_dados_salvos.get("periodo_fiscal", ""), label_visibility="collapsed")

                        # ── Criticidade + Métodos de análise ──────────────────
                        st.divider()
                        _CRITICIDADE_OPCOES = {
                            "🟢 Baixa — impacto reduzido, sem risco de autuação": "baixa",
                            "🟡 Média — impacto moderado ou dúvida interpretativa": "media",
                            "🔴 Alta — risco de autuação ou contingência relevante": "alta",
                            "⛔ Extrema — litígio iminente ou impacto material": "extrema",
                        }
                        _crit_salva = step_dados_salvos.get("criticidade", "media")
                        _crit_label_salva = next(
                            (k for k, v in _CRITICIDADE_OPCOES.items() if v == _crit_salva),
                            list(_CRITICIDADE_OPCOES.keys())[1],
                        )
                        _lbl("Criticidade do caso", "Avalie o nível de risco e impacto financeiro. Casos extremos ativam métodos de análise mais robustos.")
                        _crit_label_sel = st.selectbox(
                            "Criticidade",
                            options=list(_CRITICIDADE_OPCOES.keys()),
                            index=list(_CRITICIDADE_OPCOES.keys()).index(_crit_label_salva),
                            label_visibility="collapsed",
                        )
                        _crit_val = _CRITICIDADE_OPCOES[_crit_label_sel]
                        dados_passo["criticidade"] = _crit_val

                        _sugestao = sugerir_metodos(_crit_val)
                        _metodos_opcoes = {m["nome"]: mid for mid, m in METODOS_ANALISE.items()}
                        _metodos_salvo_ids = step_dados_salvos.get("metodos_selecionados", _sugestao)
                        _metodos_salvo_nomes = [METODOS_ANALISE[mid]["nome"] for mid in _metodos_salvo_ids if mid in METODOS_ANALISE]
                        _lbl(
                            f"Métodos de análise (máx. {MAX_METODOS})",
                            "Selecione os métodos que o Tribus-AI deve aplicar na análise. "
                            "Métodos sugeridos pela criticidade são pré-selecionados automaticamente.",
                        )
                        _metodos_sel_nomes = st.multiselect(
                            "Métodos",
                            options=list(_metodos_opcoes.keys()),
                            default=_metodos_salvo_nomes,
                            max_selections=MAX_METODOS,
                            label_visibility="collapsed",
                        )
                        dados_passo["metodos_selecionados"] = [_metodos_opcoes[n] for n in _metodos_sel_nomes]
                        for _mid in dados_passo["metodos_selecionados"]:
                            st.caption(f"**{METODOS_ANALISE[_mid]['nome']}** — {METODOS_ANALISE[_mid]['quando_usar']}")

                        # ── Qualificação Fática (G23) ──────────────────────────
                        st.divider()
                        _qf_ini_p1 = step_dados_salvos.get("fatos_cliente", {})
                        _fatos_p1 = coletar_qualificacao_fatica(
                            key_prefix=f"p1_{case_id_input}",
                            valores_iniciais=_qf_ini_p1,
                        )
                        dados_passo["fatos_cliente"] = _fatos_p1

                    elif passo_atual == 2:
                        # Passo 2: Estruturar riscos e dados (G02 — mín. 3 riscos obrigatórios)
                        _MIN_RISCOS = 3
                        _riscos_salvas = step_dados_salvos.get("riscos", [])
                        _lbl("Riscos fiscais ✱ (mín. 3)",
                             "Declare o que pode dar errado — riscos de autuação, divergência interpretativa, "
                             "mudança regulatória ou inadimplência. Mínimo de 3 riscos obrigatórios. "
                             "Ex: 'Glosa de créditos por divergência interpretativa do Fisco'")
                        _risco_placeholders = [
                            "Ex: Glosa de créditos por divergência interpretativa do Fisco",
                            "Ex: Mudança de alíquota durante o período de transição",
                            "Ex: Divergência entre apuração CBS (federal) e IBS (estadual/municipal)",
                            "Ex: Inadimplência do comprador em vendas parceladas com split payment",
                            "Ex: Regulamentação do Comitê Gestor ainda pendente para este caso",
                        ]
                        _riscos_inputs = []
                        for _ri in range(5):
                            _req_mark = " ✱" if _ri < _MIN_RISCOS else " (opcional)"
                            _lbl_text = f"Risco {_ri + 1}{_req_mark}"
                            _rv = _riscos_salvas[_ri] if _ri < len(_riscos_salvas) else ""
                            _riscos_inputs.append(
                                st.text_input(
                                    _lbl_text,
                                    value=_rv,
                                    placeholder=_risco_placeholders[_ri],
                                    label_visibility="visible",
                                )
                            )
                        dados_passo["riscos"] = [r for r in _riscos_inputs if r.strip()]
                        if len(dados_passo["riscos"]) < _MIN_RISCOS:
                            st.warning(
                                f"⚠️ Declare ao menos {_MIN_RISCOS} riscos fiscais. "
                                f"Preenchidos: {len(dados_passo['riscos'])} de {_MIN_RISCOS}."
                            )
                        st.divider()
                        qualidade_opcoes = {
                            "🟢 Verde — dados completos e consistentes": "verde",
                            "🟡 Amarelo — dados parciais, análise com ressalva": "amarelo",
                            "🔴 Vermelho — dados insuficientes, análise bloqueada": "vermelho",
                        }
                        _lbl("Avaliação dos dados disponíveis", "Avalie se os dados e documentos disponíveis são suficientes para uma análise confiável. Verde = tudo completo, Amarelo = parcialmente disponível, Vermelho = faltam dados essenciais.")
                        qualidade_label = st.selectbox(
                            "Avaliação",
                            options=list(qualidade_opcoes.keys()),
                            index=0,
                            label_visibility="collapsed",
                        )
                        dados_passo["dados_qualidade"] = qualidade_opcoes[qualidade_label]

                    elif passo_atual == 4:
                        # Passo 4: Posição do gestor — hipótese (old P5)
                        st.info("Esta é a sua posição — registre ANTES de ver a recomendação do Tribus-AI (Passo 5).")
                        _lbl("Nossa posição antes da análise", "Registre aqui a posição do gestor tributário ANTES de ver a recomendação da IA. Isso garante independência decisória e permite comparação posterior.")
                        dados_passo["hipotese_gestor"] = st.text_area(
                            "Hipótese",
                            height=120,
                            value=step_dados_salvos.get("hipotese_gestor", ""),
                            label_visibility="collapsed",
                        )

                    elif passo_atual == 5:
                        # Passo 5: Decidir — comparação lado a lado P4 vs P3
                        # Restaurar dados pendentes (guardados pelo pre-check de carimbo)
                        _pending_carimbo = st.session_state.pop(
                            f"_carimbo_pending_{case_id_input}", {}
                        )

                        # ── Comparação: hipótese do gestor (P4) × análise IA (P3) ──
                        _p3_entry = _steps_data.get(3) or _steps_data.get("3") or {}
                        _p3_dados  = _p3_entry.get("dados") or {}
                        _analise_p3 = _p3_dados.get("analise_result") or {}
                        _p3_resposta = _sanitize_latex(_analise_p3.get("resposta") or "—")

                        _p4_entry = _steps_data.get(4) or _steps_data.get("4") or {}
                        _p4_dados  = _p4_entry.get("dados") or {}
                        _hipotese_p4_salva = _p4_dados.get("hipotese_gestor") or "—"

                        st.subheader("🔍 Comparação — sua posição × recomendação da IA")
                        _col_hip, _col_ia = st.columns(2)
                        with _col_hip:
                            st.markdown("**📌 Sua posição (P4)**")
                            st.info(_hipotese_p4_salva)
                        with _col_ia:
                            st.markdown("**🤖 Análise do Tribus-AI (P3)**")
                            st.info(_p3_resposta[:800] + ("..." if len(_p3_resposta) > 800 else ""))

                        exibir_painel_governanca(
                            grau=_analise_p3.get("grau_consolidacao", ""),
                            forca_contra_tese=_analise_p3.get("forca_corrente_contraria", ""),
                            risco=_analise_p3.get("risco_adocao", ""),
                            scoring_confianca=_analise_p3.get("scoring_confianca", ""),
                        )

                        st.divider()

                        # Auto-preencher recomendacao com análise do Passo 3 se campo vazio
                        _rec_salva = step_dados_salvos.get("recomendacao", "")
                        if not _rec_salva:
                            _partes = []
                            if _analise_p3.get("resposta"):
                                _partes.append(_analise_p3["resposta"])
                            if _analise_p3.get("acao_recomendada"):
                                _partes.append(f"Ação recomendada: {_analise_p3['acao_recomendada']}")
                            if _analise_p3.get("impacto_financeiro"):
                                _partes.append(f"Impacto financeiro: {_analise_p3['impacto_financeiro']}")
                            if _analise_p3.get("fundamento_legal"):
                                _partes.append(f"Base legal: {', '.join(_analise_p3['fundamento_legal'])}")
                            if not _partes:
                                if _analise_p3.get("contra_tese"):
                                    _partes.append(_analise_p3["contra_tese"])
                                if _analise_p3.get("disclaimer"):
                                    _partes.append(_analise_p3["disclaimer"])
                            _rec_salva = "\n\n".join(_partes)

                        if _rec_salva:
                            st.info("Recomendação gerada automaticamente pelo Tribus-AI com base na análise do Passo 3. Edite se necessário antes de avançar.")
                        else:
                            st.warning("Não foi possível recuperar a análise do Passo 3. Preencha a recomendação manualmente ou volte ao Passo 3 e refaça a análise.")
                        _lbl("Recomendação Tribus-AI", "Recomendação gerada automaticamente pela IA com base na análise do Passo 3. Revise e edite se necessário antes de registrar sua decisão.")
                        dados_passo["recomendacao"] = st.text_area(
                            "Recomendação",
                            height=200,
                            value=_pending_carimbo.get("recomendacao") or _rec_salva,
                            label_visibility="collapsed",
                        )
                        st.divider()
                        st.warning("⚠️ A decisão final será comparada com a recomendação da IA para verificação de independência decisória.")
                        _lbl("Decisão tomada", "Registre a decisão efetivamente tomada pela equipe. Será comparada com a recomendação da IA para verificar independência decisória.")
                        dados_passo["decisao_final"] = st.text_area(
                            "Decisão",
                            height=120,
                            value=_pending_carimbo.get("decisao_final") or step_dados_salvos.get("decisao_final", ""),
                            label_visibility="collapsed",
                        )
                        _lbl("Responsável pela decisão", "Nome do profissional ou gestor que tomou a decisão final sobre este caso.")
                        dados_passo["decisor"] = st.text_input(
                            "Decisor",
                            value=_pending_carimbo.get("decisor") or step_dados_salvos.get("decisor", ""),
                            label_visibility="collapsed",
                        )

                    elif passo_atual == 6:
                        # Passo 6: Ciclo Pós-Decisão (merged old P8 + P9)
                        _lbl("O que aconteceu na prática", "Descreva o resultado efetivo após a implementação da decisão. Isso alimenta o aprendizado para casos futuros.")
                        dados_passo["resultado_real"] = st.text_area("Resultado", height=80, value=step_dados_salvos.get("resultado_real", ""), label_visibility="collapsed")
                        _lbl("Data para revisão", "Data futura para reavaliação do caso. Formato: dd-mm-aaaa.")
                        dados_passo["data_revisao"] = st.text_input(
                            "Data revisão",
                            value=step_dados_salvos.get("data_revisao", ""),
                            label_visibility="collapsed",
                        )
                        _lbl("O que aprendemos com este caso", "Registre lições aprendidas, erros a evitar e boas práticas identificadas. Este registro será útil para decisões similares no futuro.")
                        dados_passo["aprendizado_extraido"] = st.text_area(
                            "Aprendizado",
                            height=100,
                            value=step_dados_salvos.get("aprendizado_extraido", ""),
                            label_visibility="collapsed",
                        )

                    # BUG-13 — botão diferente no passo terminal (Passo 6)
                    PASSO_TERMINAL = 6
                    col_av, col_vo = st.columns([2, 1])
                    with col_av:
                        _label_btn = "✅ Concluir Caso" if passo_atual == PASSO_TERMINAL else "Avançar →"
                        btn_avancar = st.form_submit_button(_label_btn, type="primary")
                    with col_vo:
                        btn_voltar = st.form_submit_button("← Voltar", disabled=(passo_atual == PASSO_TERMINAL))

                if not _caso_concluido and (btn_avancar or btn_voltar):
                    acao = "avancar" if btn_avancar else "voltar"

                    # G02 — validar mínimo de premissas no P1
                    if btn_avancar and passo_atual == 1:
                        if len(dados_passo.get("premissas", [])) < 3:
                            st.error(
                                "🔒 **P1 incompleto.** Declare ao menos 3 premissas regulatórias "
                                "antes de avançar. "
                                "'O maior erro tributário é o erro de premissa não declarada.'"
                            )
                            st.stop()

                    # G02 — validar mínimo de riscos no P2
                    if btn_avancar and passo_atual == 2:
                        if len(dados_passo.get("riscos", [])) < 3:
                            st.error(
                                "🔒 **P2 incompleto.** Declare ao menos 3 riscos fiscais "
                                "antes de avançar para a análise."
                            )
                            st.stop()

                    # G05 — Detector de Carimbo: pre-check antes de salvar P5
                    if btn_avancar and passo_atual == 5:
                        _ack_key = f"_carimbo_ack_{case_id_input}"
                        if not st.session_state.get(_ack_key):
                            _dec_txt = dados_passo.get("decisao_final", "")
                            _rec_txt = dados_passo.get("recomendacao", "")
                            if _dec_txt and _rec_txt:
                                _cr = _detectar_carimbo(_dec_txt, _rec_txt)
                                if _cr["carimbo_detectado"]:
                                    # Guardar dados para restaurar após confirmação
                                    st.session_state[f"_carimbo_pending_{case_id_input}"] = dict(dados_passo)
                                    st.warning(_cr["mensagem"])
                                    _cc1, _cc2 = st.columns(2)
                                    with _cc1:
                                        if st.button(
                                            "✅ Confirmar — considerei alternativas",
                                            key=f"_carimbo_ack_btn_{case_id_input}",
                                        ):
                                            st.session_state[_ack_key] = True
                                            st.rerun()
                                    with _cc2:
                                        if st.button(
                                            "🔄 Revisar minha decisão",
                                            key=f"_carimbo_rev_btn_{case_id_input}",
                                        ):
                                            st.session_state.pop(f"_carimbo_pending_{case_id_input}", None)
                                            st.info(
                                                "Revise sua decisão no formulário acima, "
                                                "considerando alternativas ao caminho sugerido pela IA."
                                            )
                                    st.stop()
                        else:
                            # Confirmação usada — limpar para próxima verificação
                            st.session_state.pop(_ack_key, None)

                    # BUG-12 — validar data em Passo 6 antes de chamar API
                    if btn_avancar and passo_atual == 6:
                        _data_rev = dados_passo.get("data_revisao", "")
                        if _data_rev and not re.match(r"^\d{2}-\d{2}-\d{4}$", _data_rev):
                            st.error("Data inválida. Use o formato dd-mm-aaaa")
                            st.stop()

                    try:
                        r2 = _api_post(
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

                        if passo_atual == 6:
                            st.success("✅ **Caso concluído com sucesso!**")
                            st.balloons()
                            st.info(
                                "**Próximos passos:**\n\n"
                                "- Acesse a aba **Documentos** para gerar o Dossiê de Decisão ou outros documentos formais\n"
                                "- Volte à aba **Consultar** para fazer novas análises\n"
                                "- Ou crie um **novo caso** no Protocolo de Decisão"
                            )
                            # Ativar monitoramento P6 automaticamente
                            try:
                                _user_id_p6 = st.session_state.get("user_id")
                                ativar_monitoramento_p6(
                                    case_id=case_id_input,
                                    user_id=_user_id_p6,
                                )
                                st.info(
                                    "**P6 ativado:** esta decisão está sendo monitorada. "
                                    "Você será alertado se mudanças legislativas afetarem suas premissas."
                                )
                            except Exception as _p6_err:
                                pass  # P6 é best-effort — não bloqueia conclusão do caso
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
                                        rc = _api_post(
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

    # ------------------------------------------------------------------
    # P6 — Ciclo Pós-Decisão (sub-tab ao final do Protocolo)
    # ------------------------------------------------------------------
    st.divider()
    _tab_protocolo_fin, _tab_p6 = st.tabs(["P1–P5 (acima)", "P6 — Ciclo Pós-Decisão"])
    with _tab_p6:
        render_ciclo_pos_decisao()
    with _tab_protocolo_fin:
        st.caption("O conteúdo do Protocolo P1–P5 está acima nesta mesma aba.")


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
        "Gere, aprove e compartilhe documentos tributários estruturados vinculados ao Protocolo de Decisão. "
        "Aviso legal obrigatório e não removível em toda saída."
    )

    # --- Carregar lista de cases do backend ---
    _cases_list = []
    try:
        _resp_cases = _api_get(f"{API_BASE}/v1/cases", timeout=10)
        if _resp_cases.status_code == 200:
            _cases_list = _resp_cases.json()
    except Exception:
        pass

    # --- Seleção de caso ---
    _STATUS_LABEL = {
        "rascunho": "Rascunho", "em_analise": "Em Análise",
        "aguardando_hipotese": "Aguardando Hipótese", "decidido": "Decidido",
        "em_monitoramento": "Monitoramento", "aprendizado_extraido": "Concluído",
    }
    if _cases_list:
        _case_options = {
            f"#{c['case_id']}  |  {c['titulo'][:55]}  |  P{c['passo_atual']} — {_STATUS_LABEL.get(c['status'], c['status'])}": c["case_id"]
            for c in _cases_list
        }
        _lbl("Selecione o caso", "Escolha o caso do Protocolo de Decisão para o qual deseja gerar ou visualizar documentos.")
        _case_sel = st.selectbox(
            "Selecione o caso",
            options=list(_case_options.keys()),
            key="out_case_select",
            label_visibility="collapsed",
        )
        case_id_out = _case_options[_case_sel]
    else:
        st.info("Nenhum caso encontrado. Crie um caso na aba **Protocolo de Decisão**.")
        case_id_out = 1

    st.divider()

    col_esq, col_dir = st.columns([1, 3])

    with col_esq:
        st.subheader("Filtros")

        _lbl("Tipo de documento", "Filtre por tipo: Alerta, Nota de Trabalho, Recomendação Formal, Dossiê de Decisão ou Material para Compartilhamento.")
        filtro_classe = st.multiselect(
            "Tipo", options=CLASSES_OPCOES,
            format_func=lambda x: CLASSE_LABEL.get(x, x),
            default=CLASSES_OPCOES, key="out_filtro_classe",
            label_visibility="collapsed",
        )
        _lbl("Status", "Filtre por estado do documento. Gerado = aguardando revisão, Aprovado = validado, Publicado = compartilhado.")
        filtro_status = st.multiselect(
            "Status", options=["rascunho", "gerado", "aprovado", "publicado", "revogado"],
            default=["gerado", "aprovado", "publicado"],
            label_visibility="collapsed",
        )
        carregar_outputs = st.button("Carregar Documentos", type="primary")

        st.divider()
        st.subheader("Gerar Documento")

        # Seleção de classe FORA do form para permitir campos condicionais
        _lbl("Tipo de documento", "Alerta (urgente), Nota de Trabalho (análise interna), Recomendação Formal (parecer completo), Dossiê de Decisão (consolidado do caso) ou Material para Compartilhamento (versão executiva).")
        classe_sel = st.selectbox(
            "Tipo",
            options=CLASSES_OPCOES,
            format_func=lambda x: CLASSE_LABEL.get(x, x),
            key="out_classe_sel",
            label_visibility="collapsed",
        )

        with st.form("form_gerar_output"):
            _lbl("Público-alvo", "Selecione para quem o documento será direcionado. O sistema adapta a linguagem e o nível de detalhe para cada público.")
            stk_sel = st.multiselect(
                "Público-alvo",
                options=STAKEHOLDERS_OPCOES,
                format_func=lambda x: STAKEHOLDER_LABEL.get(x, x),
                label_visibility="collapsed",
            )

            # Campos condicionais — só mostra o que é relevante para a classe
            query_out = ""
            titulo_out = ""
            contexto_out = ""
            mat_out = 3
            base_id_out = 0

            if classe_sel in ("nota_trabalho", "recomendacao_formal"):
                _tipo_label = CLASSE_LABEL.get(classe_sel, classe_sel)
                _lbl(f"Consulta ({_tipo_label})", f"Pergunta tributária que será analisada para gerar a {_tipo_label}. O sistema buscará na legislação e produzirá o documento.")
                query_out = st.text_area("Consulta", height=60, label_visibility="collapsed")
            elif classe_sel == "alerta":
                _lbl("Título", "Título curto e descritivo para o alerta tributário.")
                titulo_out = st.text_input("Título", label_visibility="collapsed")
                _lbl("Contexto", "Descreva a situação que motivou o alerta e as informações relevantes para compreensão.")
                contexto_out = st.text_area("Contexto", height=60, label_visibility="collapsed")
                _lbl("Nível de prioridade", "De 1 (baixa) a 5 (crítica). Indica a urgência e o impacto potencial do alerta.")
                mat_out = st.slider("Prioridade", min_value=1, max_value=5, value=3, label_visibility="collapsed")
            elif classe_sel == "dossie_decisao":
                st.info("O Dossiê de Decisão é gerado automaticamente a partir do caso (requer Passo 5 — Decidir concluído).")
            elif classe_sel == "material_compartilhavel":
                _lbl("ID do documento base", "Informe o número (ID) de uma Recomendação Formal ou Dossiê de Decisão já aprovado. O material compartilhável será gerado a partir desse documento.")
                base_id_out = st.number_input("ID base", min_value=0, step=1, value=0, label_visibility="collapsed")

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
                    st.error(f"O campo **Consulta** é obrigatório para {_tipo_label}. Informe a pergunta que o Tribus-AI deve analisar.")
                    st.stop()
            elif classe_sel == "material_compartilhavel":
                if base_id_out <= 0:
                    st.error("Informe o **ID do documento base** (Recomendação Formal ou Dossiê aprovado) para gerar o Material Compartilhável.")
                    st.stop()
                if not stk_sel:
                    st.error("Selecione ao menos um **público-alvo** para o Material Compartilhável.")
                    st.stop()

            body: dict = {"case_id": case_id_out, "classe": classe_sel, "user_id": st.session_state.get("user_id")}
            if stk_sel:
                body["stakeholders"] = stk_sel
            if classe_sel == "alerta":
                body.update({"titulo": titulo_out, "contexto": contexto_out, "materialidade": mat_out})
            elif classe_sel in ("nota_trabalho", "recomendacao_formal"):
                body["query"] = query_out
            elif classe_sel == "material_compartilhavel":
                body["output_base_id"] = base_id_out if base_id_out > 0 else None

            try:
                rg = _api_post(f"{API_BASE}/v1/outputs", json=body, timeout=120)
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
                ro = _api_get(f"{API_BASE}/v1/cases/{case_id_out}/outputs", timeout=10)
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
                                def _escape_latex(txt: str) -> str:
                                    """Escapa $ para evitar renderização LaTeX no Streamlit."""
                                    if not isinstance(txt, str):
                                        return str(txt)
                                    return txt.replace("$", r"\$")

                                for chave in ["recomendacao_principal", "resposta", "decisao_final",
                                              "contexto", "hipotese_gestor"]:
                                    if conteudo.get(chave):
                                        st.markdown(f"**{_CHAVE_LABEL.get(chave, chave)}**")
                                        st.markdown(_escape_latex(conteudo[chave]))
                                        break

                                if conteudo.get("fundamento_legal"):
                                    st.markdown("**Base legal**")
                                    for art in conteudo["fundamento_legal"]:
                                        st.markdown(f"- {_escape_latex(art)}")

                                # Aviso legal em destaque (não colapsável)
                                st.warning(f"⚠️ **Aviso legal:**\n\n{_escape_latex(out['disclaimer'])}")

                                # Views por público-alvo
                                views = out.get("stakeholder_views", [])
                                if views:
                                    st.markdown("**Visões por público-alvo**")
                                    tabs_labels = [STAKEHOLDER_LABEL.get(v["stakeholder"], v["stakeholder"].upper()) for v in views]
                                    stk_tabs = st.tabs(tabs_labels)
                                    for tab, view in zip(stk_tabs, views):
                                        with tab:
                                            st.markdown(_escape_latex(view["resumo"]))

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
                                                    ra = _api_post(
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
                                                    rc5 = _api_post(
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
# ABA 5 — Qualidade do Sistema (oculta — uso interno)
# ===========================================================================
# MODEL_DEV_UI = "claude-haiku-4-5-20251001"
# PROMPT_VERSION_UI = "v1.0.0-sprint2"
#
# Para reativar, descomentar o bloco abaixo e restaurar aba5 na linha de st.tabs()

if False:  # noqa: Aba oculta durante fase de testes com usuários
    aba5 = None  # placeholder
    st.title("Qualidade do Sistema")
    st.caption("Monitoramento contínuo, detecção de variações e validação automática do Tribus-AI.")

    # ------ Linha 1 — KPIs ------
    st.subheader("Indicadores — Últimos 7 dias")
    try:
        rm = _api_get(f"{API_BASE}/v1/observability/metrics", params={"days": 7}, timeout=5)
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
            rm30 = _api_get(f"{API_BASE}/v1/observability/metrics", params={"days": 30}, timeout=5)
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
        rd = _api_get(f"{API_BASE}/v1/observability/drift",
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
                            rr = _api_post(
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

    # ------ Budget de Contexto ------
    st.subheader("Budget de Contexto — Pressão por Tipo de Query")
    try:
        rbp = _api_get(f"{API_BASE}/v1/observability/budget-pressure", timeout=5)
        if rbp.status_code == 200:
            bp_data = rbp.json()
            if bp_data:
                import pandas as pd
                df_bp = pd.DataFrame(bp_data)
                st.dataframe(df_bp, use_container_width=True, hide_index=True)
            else:
                st.info("Sem dados de budget disponíveis ainda.")
        else:
            st.info("Endpoint de budget não disponível.")
    except httpx.ConnectError:
        st.error("API offline.")
    except Exception:
        st.info("Dados de budget não disponíveis ainda.")

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
                rr = _api_post(
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
            rb = _api_post(
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

# ===========================================================================
# ABA 5 — Simuladores (MP-01 Carga RT + MP-05 Split Payment)
# ===========================================================================
with aba5:
    sim_tab1, sim_tab2, sim_tab3 = st.tabs(["Carga RT", "Split Payment", "Créditos IBS/CBS"])
    with sim_tab1:
        render_simulador_carga()
    with sim_tab2:
        render_simulador_split_payment()
    with sim_tab3:
        render_monitor_creditos()

# ===========================================================================
# ABA ADMIN — Painel de Gerenciamento de Usuários (apenas ADMIN)
# ===========================================================================
if is_admin and tab_admin is not None:
    with tab_admin:
        try:
            from admin import render_painel_admin
            render_painel_admin()
        except ImportError:
            st.info("Painel administrativo será habilitado no próximo passo.")
