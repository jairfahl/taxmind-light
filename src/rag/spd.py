"""
rag/spd.py — SPD-RAG: retrieval por norma com roteamento inteligente.

Inspirado em SPD-RAG (arXiv:2603.08329). Quando a query exige informacoes
cruzadas de multiplas normas, faz retrieval per-document e merge, evitando
concentracao em fonte unica (RS-02).

Reutiliza retrieve() existente com norma_filter — zero mudanca de infra.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

import psycopg2
from dotenv import load_dotenv

from src.db.pool import get_conn, put_conn

from src.rag.retriever import ChunkResultado, retrieve

load_dotenv()

logger = logging.getLogger(__name__)


class SPDStrategy(str, Enum):
    STANDARD = "standard"
    SPD = "spd"
    SPD_REACTIVE = "spd_reactive"


@dataclass
class SPDRoutingDecision:
    strategy: SPDStrategy
    reason: str


@dataclass
class SPDResult:
    chunks_merged: list[ChunkResultado]
    chunks_por_norma: dict[str, list[ChunkResultado]]
    normas_consultadas: int
    strategy_used: SPDStrategy


def listar_normas_ativas() -> list[str]:
    """Retorna codigos de normas vigentes do banco."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT codigo FROM normas WHERE vigente = TRUE ORDER BY codigo")
        codigos = [row[0] for row in cur.fetchall()]
        cur.close()
    finally:
        put_conn(conn)
    logger.info("Normas ativas: %s", codigos)
    return codigos


def decidir_estrategia(
    query_tipo: str,
    norma_filter: Optional[list[str]],
    num_normas: int,
) -> SPDRoutingDecision:
    """
    Decide se usar retrieval SPD ou standard.

    Logica pura — sem LLM, sem DB.

    Args:
        query_tipo: Valor do QueryTipo (ex: "comparativa", "factual", "interpretativa").
        norma_filter: Filtro de norma definido pelo usuario (None = sem filtro).
        num_normas: Numero de normas ativas no banco.
    """
    # Usuario escolheu norma especifica
    if norma_filter:
        return SPDRoutingDecision(
            strategy=SPDStrategy.STANDARD,
            reason="norma_filter definido pelo usuario",
        )

    # SPD nao faz sentido com menos de 2 normas
    if num_normas < 2:
        return SPDRoutingDecision(
            strategy=SPDStrategy.STANDARD,
            reason=f"apenas {num_normas} norma(s) ativa(s)",
        )

    # Comparativa: cross-document por natureza
    if query_tipo == "comparativa":
        return SPDRoutingDecision(
            strategy=SPDStrategy.SPD,
            reason="query comparativa — beneficio de cobertura multi-norma",
        )

    # Interpretativa com >= 3 normas: beneficio de cobertura
    if query_tipo == "interpretativa" and num_normas >= 3:
        return SPDRoutingDecision(
            strategy=SPDStrategy.SPD,
            reason="query interpretativa com >=3 normas — beneficio de cobertura",
        )

    # Default: standard
    return SPDRoutingDecision(
        strategy=SPDStrategy.STANDARD,
        reason="query nao requer retrieval multi-norma",
    )


def _retrieve_para_norma(
    norma: str,
    query: str,
    top_k_por_norma: int,
    rerank_top_n: int,
    excluir_tipos: Optional[list[str]],
    cosine_weight: float,
    bm25_weight: float,
    data_referencia: Optional[date] = None,
    tenant_id: str | None = None,
) -> tuple[str, list[ChunkResultado]]:
    """Wrapper para retrieve() com norma_filter para uso em ThreadPoolExecutor."""
    try:
        chunks = retrieve(
            query=query,
            top_k=top_k_por_norma,
            rerank_top_n=rerank_top_n,
            norma_filter=[norma],
            excluir_tipos=excluir_tipos,
            cosine_weight=cosine_weight,
            bm25_weight=bm25_weight,
            data_referencia=data_referencia,
            tenant_id=tenant_id,
        )
        return norma, chunks
    except Exception as e:
        logger.warning("SPD retrieve falhou para norma %s: %s", norma, e)
        return norma, []


def spd_retrieve(
    query: str,
    normas: list[str],
    top_k_por_norma: int = 3,
    rerank_top_n: int = 15,
    excluir_tipos: Optional[list[str]] = None,
    cosine_weight: float = 0.7,
    bm25_weight: float = 0.3,
    data_referencia: Optional[date] = None,
    tenant_id: str | None = None,
) -> SPDResult:
    """
    Retrieval per-document: chama retrieve() uma vez por norma e faz merge.

    Args:
        query: Texto da consulta.
        normas: Lista de codigos de norma para buscar.
        top_k_por_norma: Numero de chunks por norma.
        rerank_top_n: Candidatos para re-ranking por norma.
        excluir_tipos: Tipos de norma a excluir.
        cosine_weight: Peso cosine no score hibrido.
        bm25_weight: Peso BM25 no score hibrido.

    Returns:
        SPDResult com chunks merged, chunks por norma, e metadata.
    """
    chunks_por_norma: dict[str, list[ChunkResultado]] = {}

    # Paralelizar chamadas (I/O-bound: Voyage API + pgvector)
    with ThreadPoolExecutor(max_workers=min(len(normas), 2)) as executor:
        futures = {
            executor.submit(
                _retrieve_para_norma,
                norma, query, top_k_por_norma, rerank_top_n,
                excluir_tipos, cosine_weight, bm25_weight,
                data_referencia, tenant_id,
            ): norma
            for norma in normas
        }
        for future in as_completed(futures):
            norma, chunks = future.result()
            chunks_por_norma[norma] = chunks

    # Merge: dedup por chunk_id, manter maior score_final
    seen_chunks: dict[int, ChunkResultado] = {}
    for norma_chunks in chunks_por_norma.values():
        for chunk in norma_chunks:
            existing = seen_chunks.get(chunk.chunk_id)
            if existing is None or chunk.score_final > existing.score_final:
                seen_chunks[chunk.chunk_id] = chunk

    # Ordenar por score_final DESC
    chunks_merged = sorted(seen_chunks.values(), key=lambda c: c.score_final, reverse=True)

    normas_com_resultado = sum(1 for v in chunks_por_norma.values() if v)
    logger.info(
        "SPD retrieve: %d normas consultadas, %d com resultado, %d chunks merged",
        len(normas), normas_com_resultado, len(chunks_merged),
    )

    return SPDResult(
        chunks_merged=chunks_merged,
        chunks_por_norma=chunks_por_norma,
        normas_consultadas=normas_com_resultado,
        strategy_used=SPDStrategy.SPD,
    )
