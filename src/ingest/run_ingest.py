"""
run_ingest.py — pipeline principal de ingestão de normas tributárias.

Fluxo:
1. Carrega .env
2. Conecta ao banco
3. Para cada PDF: loader → chunker → embedder → persist
4. Resumo final
"""

import logging
import os
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Adicionar raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.ingest.chunker import chunkar_documento
from src.ingest.embedder import gerar_e_persistir_embeddings
from src.ingest.loader import carregar_normas

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def conectar_banco() -> psycopg2.extensions.connection:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL não definida no .env")
    conn = psycopg2.connect(url)
    logger.info("Conectado ao banco: %s", url.split("@")[-1])
    return conn


def inserir_norma(conn: psycopg2.extensions.connection, doc) -> int:
    """INSERT norma com ON CONFLICT DO UPDATE. Retorna id da norma."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO normas (codigo, nome, tipo, numero, ano, arquivo)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (codigo) DO UPDATE SET
            nome    = EXCLUDED.nome,
            arquivo = EXCLUDED.arquivo,
            vigente = TRUE
        RETURNING id
        """,
        (doc.codigo, doc.nome, doc.tipo, doc.numero, doc.ano, doc.arquivo),
    )
    norma_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return norma_id


def inserir_chunks(conn: psycopg2.extensions.connection, norma_id: int, chunks) -> list[int]:
    """INSERT chunks em batch com ON CONFLICT DO NOTHING. Retorna IDs inseridos/existentes."""
    cur = conn.cursor()
    chunk_ids: list[int] = []

    for chunk in chunks:
        cur.execute(
            """
            INSERT INTO chunks (norma_id, chunk_index, texto, artigo, secao, titulo, tokens)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (norma_id, chunk_index) DO NOTHING
            RETURNING id
            """,
            (norma_id, chunk.chunk_index, chunk.texto, chunk.artigo, chunk.secao, chunk.titulo, chunk.tokens),
        )
        row = cur.fetchone()
        if row:
            chunk_ids.append(row[0])
        else:
            # Já existia — buscar id
            cur.execute(
                "SELECT id FROM chunks WHERE norma_id = %s AND chunk_index = %s",
                (norma_id, chunk.chunk_index),
            )
            existing = cur.fetchone()
            if existing:
                chunk_ids.append(existing[0])

    conn.commit()
    cur.close()
    return chunk_ids


def main() -> None:
    logger.info("=== TaxMind Light — Ingestão Sprint 1 ===")
    t_total_inicio = time.time()

    conn = conectar_banco()

    documentos = carregar_normas()
    if not documentos:
        logger.error("Nenhum documento encontrado. Verifique PDF_SOURCE_DIR no .env")
        sys.exit(1)

    total_chunks_geral = 0
    total_embeddings_geral = 0

    for doc in documentos:
        logger.info("--- Processando norma: %s ---", doc.codigo)
        t_inicio = time.time()

        # 1. Inserir norma
        norma_id = inserir_norma(conn, doc)
        logger.info("  norma_id=%d (%s)", norma_id, doc.codigo)

        # 2. Chunking
        chunks = chunkar_documento(doc.texto)
        logger.info("  Chunks gerados: %d", len(chunks))

        # 3. Inserir chunks
        chunk_ids = inserir_chunks(conn, norma_id, chunks)
        logger.info("  Chunks persistidos: %d", len(chunk_ids))

        # 4. Embeddings
        n_embeddings = gerar_e_persistir_embeddings(conn, chunk_ids, chunks)
        logger.info("  Embeddings gerados: %d", n_embeddings)

        elapsed = time.time() - t_inicio
        logger.info("  Tempo: %.1fs | norma=%s | chunks=%d | embeddings=%d",
                    elapsed, doc.codigo, len(chunks), n_embeddings)

        total_chunks_geral += len(chunks)
        total_embeddings_geral += n_embeddings

    conn.close()
    t_total = time.time() - t_total_inicio

    logger.info("=== RESUMO FINAL ===")
    logger.info("Normas processadas : %d", len(documentos))
    logger.info("Chunks totais      : %d", total_chunks_geral)
    logger.info("Embeddings totais  : %d", total_embeddings_geral)
    logger.info("Tempo total        : %.1fs", t_total)


if __name__ == "__main__":
    main()
