"""
api/main.py — FastAPI: 4 endpoints do motor cognitivo TaxMind Light.

POST /v1/analyze        — análise tributária completa
GET  /v1/chunks         — busca RAG direta
GET  /v1/health         — status do sistema (com lista de normas)
POST /v1/ingest/upload  — ingestão de PDF adicional
"""

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.cognitive.engine import MODEL_DEV, AnaliseResult, analisar
from src.ingest.chunker import chunkar_documento
from src.ingest.embedder import gerar_e_persistir_embeddings
from src.ingest.loader import DocumentoNorma, extrair_texto_pdf
from src.quality.engine import QualidadeStatus
from src.rag.retriever import ChunkResultado, retrieve

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TaxMind Light API",
    description="Motor cognitivo para análise da Reforma Tributária brasileira",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas de entrada ---

class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Consulta tributária")
    norma_filter: Optional[list[str]] = Field(None, description="Filtrar por normas: EC132_2023, LC214_2025, LC227_2026")
    top_k: int = Field(3, ge=1, le=10)
    model: str = Field(MODEL_DEV)


# --- Serialização de AnaliseResult para dict ---

def _analise_to_dict(resultado: AnaliseResult) -> dict:
    return {
        "query": resultado.query,
        "qualidade": {
            "status": resultado.qualidade.status.value,
            "regras_ok": resultado.qualidade.regras_ok,
            "bloqueios": resultado.qualidade.bloqueios,
            "ressalvas": resultado.qualidade.ressalvas,
            "disclaimer": resultado.qualidade.disclaimer,
        },
        "fundamento_legal": resultado.fundamento_legal,
        "grau_consolidacao": resultado.grau_consolidacao,
        "contra_tese": resultado.contra_tese,
        "scoring_confianca": resultado.scoring_confianca,
        "resposta": resultado.resposta,
        "disclaimer": resultado.disclaimer,
        "anti_alucinacao": {
            "m1_existencia": resultado.anti_alucinacao.m1_existencia,
            "m2_validade": resultado.anti_alucinacao.m2_validade,
            "m3_pertinencia": resultado.anti_alucinacao.m3_pertinencia,
            "m4_consistencia": resultado.anti_alucinacao.m4_consistencia,
            "bloqueado": resultado.anti_alucinacao.bloqueado,
            "flags": resultado.anti_alucinacao.flags,
        },
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "norma_codigo": c.norma_codigo,
                "artigo": c.artigo,
                "texto": c.texto,
                "score_vetorial": c.score_vetorial,
                "score_bm25": c.score_bm25,
                "score_final": c.score_final,
            }
            for c in resultado.chunks
        ],
        "prompt_version": resultado.prompt_version,
        "model_id": resultado.model_id,
        "latencia_ms": resultado.latencia_ms,
    }


# --- Endpoints ---

@app.post("/v1/analyze")
async def analyze(req: AnalyzeRequest):
    """
    Análise tributária completa P1→P4.
    Retorna 400 se a qualidade for VERMELHO (bloqueado).
    """
    logger.info("POST /v1/analyze query=%s", req.query[:80])
    try:
        resultado = analisar(
            query=req.query,
            top_k=req.top_k,
            norma_filter=req.norma_filter,
            model=req.model,
        )
    except Exception as e:
        logger.error("Erro interno em /v1/analyze: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if resultado.qualidade.status == QualidadeStatus.VERMELHO:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Consulta bloqueada pelo DataQualityEngine",
                "bloqueios": resultado.qualidade.bloqueios,
                "qualidade_status": "vermelho",
            },
        )

    return _analise_to_dict(resultado)


@app.get("/v1/chunks")
async def get_chunks(
    q: str = Query(..., description="Texto da busca"),
    top_k: int = Query(3, ge=1, le=10),
    norma: Optional[str] = Query(None, description="Código da norma para filtrar"),
):
    """Busca RAG direta sem análise cognitiva."""
    logger.info("GET /v1/chunks q=%s top_k=%d norma=%s", q[:60], top_k, norma)
    try:
        norma_filter = [norma] if norma else None
        chunks = retrieve(q, top_k=top_k, norma_filter=norma_filter)
    except Exception as e:
        logger.error("Erro em /v1/chunks: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return [
        {
            "chunk_id": c.chunk_id,
            "norma_codigo": c.norma_codigo,
            "artigo": c.artigo,
            "texto": c.texto,
            "score_vetorial": c.score_vetorial,
            "score_bm25": c.score_bm25,
            "score_final": c.score_final,
        }
        for c in chunks
    ]


@app.get("/v1/health")
async def health():
    """Status do sistema com contagens e lista de normas disponíveis."""
    try:
        url = os.getenv("DATABASE_URL")
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM chunks")
        chunks_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM embeddings")
        embeddings_total = cur.fetchone()[0]
        cur.execute("SELECT codigo, nome FROM normas WHERE vigente = TRUE ORDER BY ano, codigo")
        normas = [{"codigo": r[0], "nome": r[1]} for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Banco inacessível: {e}")

    return {
        "status": "ok",
        "chunks_total": chunks_total,
        "embeddings_total": embeddings_total,
        "normas": normas,
    }


@app.post("/v1/ingest/upload")
async def ingest_upload(
    file: UploadFile = File(..., description="Arquivo PDF a ingerir"),
    nome: str = Form(..., description="Nome do documento (ex: IN RFB 2184/2024)"),
    tipo: str = Form(..., description="Tipo: IN | Resolucao | Parecer | Manual | Outro"),
):
    """
    Ingestão de PDF adicional (INs, Resoluções, Pareceres, Manuais).
    O PDF é processado em /tmp e não é persistido no disco após ingestão.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    logger.info("POST /v1/ingest/upload nome=%s tipo=%s", nome, tipo)

    # Gerar código único a partir do nome
    codigo = re.sub(r"[^A-Za-z0-9]", "_", nome)[:30].strip("_")

    conteudo = await file.read()

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(conteudo)
            tmp.flush()
            tmp_path = Path(tmp.name)

            # Extrair texto
            texto = extrair_texto_pdf(tmp_path)
            if not texto.strip():
                raise HTTPException(status_code=400, detail="PDF sem texto extraível (pode ser imagem)")

            doc = DocumentoNorma(
                codigo=codigo,
                nome=nome,
                tipo=tipo,
                numero="0",
                ano=2024,
                arquivo=file.filename,
                texto=texto,
            )

            # Persistir norma + chunks + embeddings
            url = os.getenv("DATABASE_URL")
            conn = psycopg2.connect(url)
            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO normas (codigo, nome, tipo, numero, ano, arquivo)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo) DO UPDATE SET
                    nome = EXCLUDED.nome, arquivo = EXCLUDED.arquivo, vigente = TRUE
                RETURNING id
                """,
                (doc.codigo, doc.nome, doc.tipo, doc.numero, doc.ano, doc.arquivo),
            )
            norma_id = cur.fetchone()[0]
            conn.commit()

            chunks = chunkar_documento(doc.texto)

            chunk_ids: list[int] = []
            for chunk in chunks:
                cur.execute(
                    """
                    INSERT INTO chunks (norma_id, chunk_index, texto, artigo, secao, titulo, tokens)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (norma_id, chunk_index) DO NOTHING
                    RETURNING id
                    """,
                    (norma_id, chunk.chunk_index, chunk.texto, chunk.artigo,
                     chunk.secao, chunk.titulo, chunk.tokens),
                )
                row = cur.fetchone()
                if row:
                    chunk_ids.append(row[0])
                else:
                    cur.execute(
                        "SELECT id FROM chunks WHERE norma_id=%s AND chunk_index=%s",
                        (norma_id, chunk.chunk_index),
                    )
                    chunk_ids.append(cur.fetchone()[0])
            conn.commit()

            n_emb = gerar_e_persistir_embeddings(conn, chunk_ids, chunks)
            cur.close()
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro em /v1/ingest/upload: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    logger.info("Upload ingerido: %s | chunks=%d | embeddings=%d", nome, len(chunks), n_emb)
    return {
        "norma_id": norma_id,
        "nome": nome,
        "codigo": codigo,
        "chunks": len(chunks),
        "embeddings": n_emb,
    }
