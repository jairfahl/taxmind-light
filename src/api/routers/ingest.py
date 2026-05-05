"""
src/api/routers/ingest.py — Endpoints de ingestão de documentos.

POST /v1/ingest/check-duplicate
POST /v1/ingest/upload
GET  /v1/ingest/jobs/{job_id}
GET  /v1/ingest/normas
DELETE /v1/ingest/normas/{norma_id}
"""

import hashlib
import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile

from src.api.auth_api import verificar_token_api, verificar_admin
from src.api.limiter import limiter
from src.db.pool import get_conn, put_conn
from src.ingest.chunker import chunkar_documento
from src.ingest.embedder import gerar_e_persistir_embeddings
from src.ingest.loader import EXTENSOES_SUPORTADAS, DocumentoNorma, extrair_texto_bytes

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Job status ---

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


def _job_set(job_id: str, status: str, message: str = "", result: dict | None = None) -> None:
    """Persiste ou atualiza status de job de ingestão no banco."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ingest_jobs (job_id, status, message, result, updated_at)
            VALUES (%s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (job_id) DO UPDATE SET
                status = EXCLUDED.status,
                message = EXCLUDED.message,
                result = EXCLUDED.result,
                updated_at = NOW()
            """,
            (job_id, status, message, json.dumps(result) if result else None),
        )
        conn.commit()
        cur.close()
    finally:
        put_conn(conn)


def _job_get(job_id: str) -> dict | None:
    """Retorna dados do job ou None se não existir."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status, message, result FROM ingest_jobs WHERE job_id = %s",
            (job_id,),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        put_conn(conn)
    if not row:
        return None
    return {"status": row[0], "message": row[1], "result": row[2]}


# --- SEC-07: MIME validation via magic bytes ---

_MAGIC_BYTES: dict[str, list[bytes]] = {
    ".pdf":  [b"%PDF"],
    ".docx": [b"PK\x03\x04"],
    ".xlsx": [b"PK\x03\x04"],
    ".html": [b"<!DOCTYPE", b"<html", b"<HTML", b"<!doctype"],
    ".txt":  [],  # sem magic bytes — qualquer texto é aceito
    ".md":   [],
    ".csv":  [],
}


def _validar_mime_bytes(header: bytes, ext: str) -> bool:
    """Valida os magic bytes do arquivo contra a extensão declarada. SEC-07."""
    permitidos = _MAGIC_BYTES.get(ext)
    if permitidos is None:
        return False  # extensão não mapeada
    if not permitidos:
        return True   # formatos texto (txt, md, csv) não têm magic bytes
    return any(header.startswith(magic) for magic in permitidos)


# --- Background task ---

def _processar_ingest_background(job_id: str, conteudo: bytes, filename: str,
                                  nome: str, tipo: str, codigo: str):
    """Processa ingestão de documento em background (extração + chunking + embeddings)."""
    try:
        _job_set(job_id, JobStatus.PROCESSING)
        file_hash = hashlib.md5(conteudo).hexdigest()

        try:
            texto = extrair_texto_bytes(conteudo, filename)
        except ValueError as e:
            _job_set(job_id, JobStatus.ERROR, str(e))
            return

        if not texto.strip():
            _job_set(job_id, JobStatus.ERROR, "Documento sem texto extraível")
            return

        doc = DocumentoNorma(
            codigo=codigo,
            nome=nome,
            tipo=tipo,
            numero="0",
            ano=2024,
            arquivo=filename,
            texto=texto,
        )

        conn = get_conn()
        try:
            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO normas (codigo, nome, tipo, numero, ano, arquivo, file_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo) DO UPDATE SET
                    nome = EXCLUDED.nome, arquivo = EXCLUDED.arquivo,
                    file_hash = EXCLUDED.file_hash, vigente = TRUE
                RETURNING id
                """,
                (doc.codigo, doc.nome, doc.tipo, doc.numero, doc.ano, doc.arquivo, file_hash),
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
        finally:
            put_conn(conn)

        logger.info("Upload ingerido: %s | chunks=%d | embeddings=%d", nome, len(chunks), n_emb)
        _job_set(job_id, JobStatus.DONE, "Documento incluído com sucesso", {
            "norma_id": norma_id,
            "nome": nome,
            "codigo": codigo,
            "chunks": len(chunks),
            "embeddings": n_emb,
        })
    except Exception as e:
        logger.error("Erro em ingest background job=%s: %s", job_id, e, exc_info=True)
        _job_set(job_id, JobStatus.ERROR, str(e))


# --- Endpoints ---

@router.post("/v1/ingest/check-duplicate", dependencies=[Depends(verificar_token_api)])
def check_duplicate(file: UploadFile = File(...)):
    """Verifica se arquivo já foi ingestado por nome ou hash MD5."""
    conteudo = file.file.read()
    file_hash = hashlib.md5(conteudo).hexdigest()
    filename = file.filename or ""

    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id, nome, arquivo FROM normas WHERE file_hash = %s", (file_hash,))
        row_hash = cur.fetchone()

        cur.execute("SELECT id, nome, arquivo FROM normas WHERE arquivo ILIKE %s", (f"%{filename}%",))
        row_nome = cur.fetchone()

        cur.close()
    finally:
        put_conn(conn)

    if row_hash:
        return {
            "duplicado": True,
            "tipo": "conteudo",
            "mensagem": f"Este documento já está na base como '{row_hash[1]}'.",
            "norma_id": row_hash[0],
        }
    if row_nome:
        return {
            "duplicado": True,
            "tipo": "nome",
            "mensagem": f"Um arquivo com este nome já foi incluído como '{row_nome[1]}'.",
            "norma_id": row_nome[0],
        }

    return {"duplicado": False, "mensagem": ""}


@router.post("/v1/ingest/upload", dependencies=[Depends(verificar_token_api)])
@limiter.limit("10/minute")
def ingest_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Arquivo a ingerir (PDF, DOCX, XLSX, HTML, TXT, MD, CSV)"),
    nome: str = Form(..., description="Nome do documento (ex: IN RFB 2184/2024)"),
    tipo: str = Form(..., description="Tipo: IN | Resolucao | Portaria | Parecer | Manual | Decreto | Lei"),
):
    """
    Ingestão assíncrona de documento. Retorna job_id para polling via GET /v1/ingest/jobs/{job_id}.
    Formatos aceitos: PDF, DOCX, XLSX, HTML, TXT, MD, CSV.
    """
    import uuid
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo ausente")
    ext = Path(file.filename).suffix.lower()
    if ext not in EXTENSOES_SUPORTADAS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato '{ext}' não suportado. Aceitos: {', '.join(sorted(EXTENSOES_SUPORTADAS))}",
        )

    logger.info("POST /v1/ingest/upload nome=%s tipo=%s", nome, tipo)

    # SEC-07: validar magic bytes contra extensão declarada
    header_bytes = file.file.read(512)
    if not _validar_mime_bytes(header_bytes, ext):
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido.")
    file.file.seek(0)

    codigo = re.sub(r"[^A-Za-z0-9]", "_", nome)[:30].strip("_")
    conteudo = file.file.read()

    # SEC-07: limite de tamanho server-side (50 MB)
    if len(conteudo) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande. Máximo: 50 MB.")

    job_id = str(uuid.uuid4())
    _job_set(job_id, JobStatus.PENDING)

    background_tasks.add_task(
        _processar_ingest_background, job_id, conteudo, file.filename, nome, tipo, codigo
    )

    return {"job_id": job_id, "status": JobStatus.PENDING}


@router.get("/v1/ingest/jobs/{job_id}", dependencies=[Depends(verificar_token_api)])
def get_job_status(job_id: str):
    """Polling de status de um job de ingestão."""
    job = _job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    resp = {"job_id": job_id, "status": job["status"], "message": job["message"]}
    if job["result"]:
        resp["result"] = job["result"]
    return resp


@router.get("/v1/ingest/normas", dependencies=[Depends(verificar_token_api)])
def listar_normas():
    """Lista todas as normas na base de conhecimento."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT n.id, n.codigo, n.nome, n.tipo, n.ano, n.vigente, n.created_at,
                   COUNT(c.id) AS total_chunks
            FROM normas n
            LEFT JOIN chunks c ON c.norma_id = n.id
            GROUP BY n.id
            ORDER BY n.created_at DESC
        """)
        rows = cur.fetchall()
        cur.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar normas: {e}")
    finally:
        put_conn(conn)

    return [
        {
            "id": r[0],
            "codigo": r[1],
            "nome": r[2],
            "tipo": r[3],
            "ano": r[4],
            "vigente": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
            "total_chunks": r[7],
        }
        for r in rows
    ]


@router.delete("/v1/ingest/normas/{norma_id}", dependencies=[Depends(verificar_admin)])
def deletar_norma(norma_id: int):
    """
    Remove uma norma e todos os seus chunks/embeddings da base.
    Cascata: embeddings → chunks → norma.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Verificar se a norma existe
        cur.execute("SELECT id, nome, codigo FROM normas WHERE id = %s", (norma_id,))
        norma = cur.fetchone()
        if not norma:
            raise HTTPException(status_code=404, detail="Norma não encontrada")

        nome_norma = norma[1]
        codigo_norma = norma[2]

        # 1. Deletar embeddings (via CASCADE nos chunks, mas fazemos explícito para log)
        cur.execute("""
            DELETE FROM embeddings
            WHERE chunk_id IN (SELECT id FROM chunks WHERE norma_id = %s)
        """, (norma_id,))
        embeddings_removidos = cur.rowcount

        # 2. Deletar chunks
        cur.execute("DELETE FROM chunks WHERE norma_id = %s", (norma_id,))
        chunks_removidos = cur.rowcount

        # 3. Deletar norma
        cur.execute("DELETE FROM normas WHERE id = %s", (norma_id,))

        conn.commit()
        logger.info(
            "Norma removida: id=%d codigo=%s nome=%s (%d chunks, %d embeddings)",
            norma_id, codigo_norma, nome_norma, chunks_removidos, embeddings_removidos,
        )

        return {
            "removido": True,
            "norma_id": norma_id,
            "nome": nome_norma,
            "codigo": codigo_norma,
            "chunks_removidos": chunks_removidos,
            "embeddings_removidos": embeddings_removidos,
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao remover norma: {e}")
    finally:
        cur.close()
        put_conn(conn)
