"""
tests/integration/test_api.py — testes de integração da FastAPI.
Requer banco rodando e embeddings populados.
Executa com: pytest tests/integration/test_api.py -v
"""

import time

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


# -----------------------------------------------------------------------
# 1. POST /v1/analyze com query válida → 200 + AnaliseResult completo
# -----------------------------------------------------------------------
def test_analyze_query_valida():
    resp = client.post(
        "/v1/analyze",
        json={"query": "Qual é a alíquota de referência do IBS conforme a LC 214/2025?"},
    )
    assert resp.status_code == 200, f"Esperado 200, obtido {resp.status_code}: {resp.text[:300]}"
    data = resp.json()
    # Campos obrigatórios
    for campo in ["query", "qualidade", "fundamento_legal", "grau_consolidacao",
                  "scoring_confianca", "resposta", "anti_alucinacao", "chunks",
                  "prompt_version", "model_id", "latencia_ms"]:
        assert campo in data, f"Campo ausente: {campo}"
    # Qualidade não pode ser vermelho (seria 400)
    assert data["qualidade"]["status"] in ("verde", "amarelo")
    # Latência dentro do limite p95
    assert data["latencia_ms"] < 30_000, f"Latência excessiva: {data['latencia_ms']}ms"


# -----------------------------------------------------------------------
# 2. POST /v1/analyze com query bloqueada → 400
# -----------------------------------------------------------------------
def test_analyze_query_bloqueada_curta():
    resp = client.post("/v1/analyze", json={"query": "oi"})
    assert resp.status_code == 400
    err = resp.json()
    assert "bloqueios" in err["detail"]


def test_analyze_query_sem_contexto_tributario():
    resp = client.post("/v1/analyze", json={"query": "Qual é a capital do Brasil e sua história?"})
    assert resp.status_code == 400


# -----------------------------------------------------------------------
# 3. GET /v1/health → 200 + contagens + lista de normas
# -----------------------------------------------------------------------
def test_health_ok():
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["chunks_total"] > 0
    assert data["embeddings_total"] > 0
    assert data["chunks_total"] == data["embeddings_total"]
    # Novo campo: lista de normas
    assert "normas" in data
    assert isinstance(data["normas"], list)
    assert len(data["normas"]) >= 3
    assert all("codigo" in n and "nome" in n for n in data["normas"])


# -----------------------------------------------------------------------
# 4. POST /v1/ingest/upload com PDF válido → 200 + chunks > 0
# -----------------------------------------------------------------------
def test_ingest_upload_pdf_valido():
    # Cria um PDF mínimo in-memory com texto tributário
    import io
    # PDF mínimo válido com texto extraível via reportlab ou bytes raw
    # Usamos um PDF gerado via fpdf2 (instalado como dep do pdfplumber)
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, "Art. 1o Este manual trata do regime de apuracao do IBS e CBS.")
        pdf.cell(0, 10, "Art. 2o A aliquota de referencia sera fixada pelo CGIBS.")
        pdf_bytes = pdf.output()
    except ImportError:
        pytest.skip("fpdf2 não instalado — pulando teste de upload")

    time.sleep(25)  # rate limit voyage
    resp = client.post(
        "/v1/ingest/upload",
        files={"file": ("manual_teste.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"nome": "Manual Teste Sprint2", "tipo": "Manual"},
    )
    assert resp.status_code == 200, f"Upload falhou: {resp.text[:300]}"
    data = resp.json()
    assert data["chunks"] > 0
    assert "norma_id" in data
    assert data["nome"] == "Manual Teste Sprint2"


def test_ingest_upload_arquivo_nao_pdf():
    resp = client.post(
        "/v1/ingest/upload",
        files={"file": ("doc.txt", b"conteudo texto", "text/plain")},
        data={"nome": "Teste TXT", "tipo": "Outro"},
    )
    assert resp.status_code == 400


# -----------------------------------------------------------------------
# Extra: GET /v1/chunks retorna lista de chunks
# -----------------------------------------------------------------------
def test_chunks_endpoint():
    time.sleep(25)  # Rate limit voyage entre chamadas de integração
    resp = client.get("/v1/chunks", params={"q": "fato gerador IBS", "top_k": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 3
    if data:
        assert "chunk_id" in data[0]
        assert "score_final" in data[0]
