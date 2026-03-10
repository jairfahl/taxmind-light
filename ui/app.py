"""
ui/app.py — Interface Streamlit para TaxMind Light.
Aba 1: Consultar · Aba 2: Carregar Documento
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
aba1, aba2 = st.tabs(["Consultar", "Carregar Documento"])


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
