"""
embedder.py — gera embeddings voyage-3 via Voyage AI e persiste em embeddings.

Respeita rate limits da conta free tier: 3 RPM / 10K TPM.
- Batch conservador: 8 chunks por chamada (~4K tokens max)
- Espera 22s entre chamadas (< 3 RPM)
- Retry com backoff agressivo em rate limit: 60s → 120s → 180s
- Resumível: pula chunks que já têm embedding
"""

import logging
import os
import time
from typing import Optional

import psycopg2
import voyageai
from dotenv import load_dotenv

from src.ingest.chunker import ChunkNorma

load_dotenv()

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3")

# Free tier: 3 RPM → 1 req / 20s. Usamos 22s por segurança.
BATCH_SIZE = 8
INTER_BATCH_DELAY = 22   # segundos entre chamadas bem-sucedidas
RATELIMIT_DELAYS = [60, 120, 180]  # backoff agressivo em rate limit
MAX_RETRIES = 3

_client: Optional[voyageai.Client] = None


def _get_client() -> voyageai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key or api_key in ("<PREENCHER>", ""):
            raise EnvironmentError(
                "VOYAGE_API_KEY não configurada no .env. "
                "Obter em https://dash.voyageai.com"
            )
        _client = voyageai.Client(api_key=api_key)
    return _client


def _embed_batch_com_retry(textos: list[str]) -> list[list[float]]:
    """Gera embeddings com retry agressivo em rate limit."""
    from src.resilience.backoff import resilient_call, VOYAGE_INGEST_CONFIG
    client = _get_client()
    result = resilient_call(client.embed, textos, model=EMBEDDING_MODEL, config=VOYAGE_INGEST_CONFIG)
    try:
        from src.observability.usage import registrar_uso
        total_tokens = getattr(result, "total_tokens", 0) or sum(len(t.split()) * 2 for t in textos)
        registrar_uso(
            service="voyageai",
            model=EMBEDDING_MODEL,
            input_tokens=total_tokens,
        )
    except Exception:
        pass
    return result.embeddings


def _chunks_ja_com_embedding(conn: psycopg2.extensions.connection, chunk_ids: list[int]) -> set[int]:
    """Retorna IDs de chunks que já possuem embedding no banco."""
    if not chunk_ids:
        return set()
    cur = conn.cursor()
    cur.execute(
        "SELECT chunk_id FROM embeddings WHERE chunk_id = ANY(%s) AND modelo = %s",
        (chunk_ids, EMBEDDING_MODEL),
    )
    existentes = {row[0] for row in cur.fetchall()}
    cur.close()
    return existentes


def gerar_e_persistir_embeddings(
    conn: psycopg2.extensions.connection,
    chunk_ids: list[int],
    chunks: list[ChunkNorma],
) -> int:
    """
    Gera embeddings para os chunks e persiste em embeddings.
    Pula chunks que já têm embedding (resumível).
    Retorna número de embeddings inseridos nesta execução.
    """
    if len(chunk_ids) != len(chunks):
        raise ValueError("chunk_ids e chunks devem ter o mesmo tamanho")

    # Filtrar já processados
    ja_existentes = _chunks_ja_com_embedding(conn, chunk_ids)
    pendentes = [(cid, c) for cid, c in zip(chunk_ids, chunks) if cid not in ja_existentes]

    if ja_existentes:
        logger.info("  %d chunks já tinham embedding — pulando", len(ja_existentes))
    if not pendentes:
        logger.info("  Nenhum chunk pendente.")
        return 0

    logger.info("  %d chunks para embeddar (batch=%d, delay=%ds)", len(pendentes), BATCH_SIZE, INTER_BATCH_DELAY)

    total_inseridos = 0
    cursor = conn.cursor()
    total_batches = (len(pendentes) + BATCH_SIZE - 1) // BATCH_SIZE
    t_inicio = time.time()

    for batch_num, batch_start in enumerate(range(0, len(pendentes), BATCH_SIZE), 1):
        batch = pendentes[batch_start: batch_start + BATCH_SIZE]
        batch_ids = [item[0] for item in batch]
        textos = [item[1].texto for item in batch]

        eta_s = (total_batches - batch_num) * (INTER_BATCH_DELAY + 2)
        logger.info(
            "  [%d/%d] Embeddando %d chunks... (ETA restante: ~%dm%ds)",
            batch_num, total_batches, len(textos),
            eta_s // 60, eta_s % 60,
        )

        vetores = _embed_batch_com_retry(textos)

        for chunk_id, vetor in zip(batch_ids, vetores):
            vetor_str = "[" + ",".join(str(v) for v in vetor) + "]"
            cursor.execute(
                """
                INSERT INTO embeddings (chunk_id, modelo, vetor)
                VALUES (%s, %s, %s::vector)
                ON CONFLICT (chunk_id, modelo) DO NOTHING
                """,
                (chunk_id, EMBEDDING_MODEL, vetor_str),
            )
            if cursor.rowcount > 0:
                total_inseridos += 1

        conn.commit()
        logger.info("  Batch %d commitado (%d inseridos no total)", batch_num, total_inseridos)

        # Esperar entre chamadas para respeitar RPM (exceto após o último batch)
        if batch_num < total_batches:
            time.sleep(INTER_BATCH_DELAY)

    elapsed = time.time() - t_inicio
    logger.info("  Embedding concluído: %d inseridos em %.1fs", total_inseridos, elapsed)
    cursor.close()

    # Invalidar cache de queries após nova ingestão
    if total_inseridos > 0:
        try:
            from src.resilience.cache import _query_cache
            _query_cache.invalidate_all()
        except Exception as _ce:
            logger.debug("Cache invalidation ignorada: %s", _ce)

    return total_inseridos
