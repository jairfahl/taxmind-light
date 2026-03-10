"""
retriever.py — motor de retrieval híbrido (vetorial + BM25).

retrieve() combina busca vetorial pgvector com re-ranking BM25 em memória.
Score final = 0.7 * cosine + 0.3 * bm25_normalizado
"""

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import psycopg2
import voyageai
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

load_dotenv()

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3")
TOP_K_DEFAULT = int(os.getenv("TOP_K", "3"))
RERANK_TOP_N_DEFAULT = int(os.getenv("RERANK_TOP_N", "10"))

_voyage_client: Optional[voyageai.Client] = None
_db_conn: Optional[psycopg2.extensions.connection] = None


class QueryVaziaError(ValueError):
    """Levantada quando a query está vazia ou contém apenas espaços."""


def _get_voyage_client() -> voyageai.Client:
    global _voyage_client
    if _voyage_client is None:
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key or api_key in ("<PREENCHER>", ""):
            raise EnvironmentError(
                "VOYAGE_API_KEY não configurada no .env. "
                "Obter em https://dash.voyageai.com"
            )
        _voyage_client = voyageai.Client(api_key=api_key)
    return _voyage_client


def _get_db_conn() -> psycopg2.extensions.connection:
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise EnvironmentError("DATABASE_URL não definida no .env")
        _db_conn = psycopg2.connect(url)
    return _db_conn


def _embed_query(query: str) -> list[float]:
    """Gera embedding da query via voyage-3 com retry em rate limit."""
    client = _get_voyage_client()
    delays = [30, 60, 90]
    for tentativa in range(3):
        try:
            result = client.embed([query], model=EMBEDDING_MODEL)
            return result.embeddings[0]
        except voyageai.error.RateLimitError as e:
            if tentativa < 2:
                logger.warning("Rate limit na query. Aguardando %ds...", delays[tentativa])
                time.sleep(delays[tentativa])
            else:
                raise RuntimeError(f"Rate limit persistente ao embeddar query: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Erro ao gerar embedding da query: {e}") from e
    return []


@dataclass
class ChunkResultado:
    chunk_id: int
    norma_codigo: str
    artigo: Optional[str]
    texto: str
    score_vetorial: float
    score_bm25: float
    score_final: float


def retrieve(
    query: str,
    top_k: int = TOP_K_DEFAULT,
    rerank_top_n: int = RERANK_TOP_N_DEFAULT,
    norma_filter: Optional[list[str]] = None,
) -> list[ChunkResultado]:
    """
    Recupera os chunks mais relevantes para a query.

    Args:
        query: Texto da consulta (não pode ser vazio).
        top_k: Número de resultados finais a retornar.
        rerank_top_n: Candidatos buscados vetorialmente antes do re-ranking.
        norma_filter: Lista de códigos de norma para filtrar (ex: ["LC214_2025"]).

    Returns:
        Lista de ChunkResultado ordenada por score_final DESC.

    Raises:
        QueryVaziaError: Se query for vazia ou apenas espaços.
        RuntimeError: Em caso de falha de API ou banco.
    """
    if not query or not query.strip():
        raise QueryVaziaError("A query não pode ser vazia")

    query = query.strip()

    # 1. Embedding da query
    logger.info("Gerando embedding para query: %s", query[:80])
    vetor_query = _embed_query(query)
    vetor_str = "[" + ",".join(str(v) for v in vetor_query) + "]"

    # 2. Busca vetorial pgvector
    conn = _get_db_conn()
    cur = conn.cursor()

    sql_base = """
        SELECT
            e.chunk_id,
            n.codigo    AS norma_codigo,
            c.artigo,
            c.texto,
            1 - (e.vetor <=> %s::vector) AS score_cosine
        FROM embeddings e
        JOIN chunks  c ON c.id = e.chunk_id
        JOIN normas  n ON n.id = c.norma_id
        WHERE e.modelo = %s
    """
    params: list = [vetor_str, EMBEDDING_MODEL]

    if norma_filter:
        placeholders = ",".join(["%s"] * len(norma_filter))
        sql_base += f" AND n.codigo IN ({placeholders})"
        params.extend(norma_filter)

    sql_base += " ORDER BY e.vetor <=> %s::vector LIMIT %s"
    params.extend([vetor_str, rerank_top_n])

    try:
        cur.execute(sql_base, params)
        rows = cur.fetchall()
    except psycopg2.Error as e:
        raise RuntimeError(f"Erro na busca vetorial: {e}") from e
    finally:
        cur.close()

    if not rows:
        logger.warning("Nenhum resultado encontrado para a query")
        return []

    # 3. Re-ranking BM25 em memória
    textos = [row[3] for row in rows]
    tokenized_corpus = [t.lower().split() for t in textos]
    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = query.lower().split()
    bm25_scores_raw = bm25.get_scores(query_tokens)

    # Normalizar BM25 para [0, 1]
    bm25_max = max(bm25_scores_raw) if max(bm25_scores_raw) > 0 else 1.0
    bm25_scores = [s / bm25_max for s in bm25_scores_raw]

    # 4. Score híbrido e ordenação
    resultados: list[ChunkResultado] = []
    for i, row in enumerate(rows):
        chunk_id, norma_codigo, artigo, texto, score_cosine = row
        score_cosine = float(score_cosine)
        score_bm25 = float(bm25_scores[i])
        score_final = 0.7 * score_cosine + 0.3 * score_bm25

        resultados.append(ChunkResultado(
            chunk_id=chunk_id,
            norma_codigo=norma_codigo,
            artigo=artigo,
            texto=texto,
            score_vetorial=score_cosine,
            score_bm25=score_bm25,
            score_final=score_final,
        ))

    resultados.sort(key=lambda r: r.score_final, reverse=True)
    top = resultados[:top_k]

    logger.info("Retrieve concluído: %d resultados (de %d candidatos)", len(top), len(rows))
    for r in top:
        logger.info("  chunk_id=%d norma=%s artigo=%s score=%.4f",
                    r.chunk_id, r.norma_codigo, r.artigo, r.score_final)

    return top
