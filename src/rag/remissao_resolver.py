"""
src/rag/remissao_resolver.py — RAR: Resolução Automática de Remissões (DC v7, G12).

Quando chunks recuperados no retrieval contêm remissao_norm_id preenchido,
busca o conteúdo da norma referenciada e injeta no contexto junto com os chunks originais.

Isso previne alucinações em análises que dependem de remissões cruzadas entre normas
(comum na LC 214/2025 → EC 132/2023).

Princípio: análise que não acessa o texto referenciado pode inventar o que está nele.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)

MAX_REMISSOES_POR_QUERY = 3   # limite para controlar tokens
MAX_CHUNKS_POR_REMISSAO = 2   # máximo de chunks por norma referenciada


def _get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


@dataclass
class ChunkRemissao:
    chunk_id: int
    norma_id: int
    norma_codigo: str
    artigo: str
    texto: str
    score_original: float = 0.0   # score do chunk que originou a remissão
    origem_chunk_id: int = 0      # chunk_id que contém a remissão


@dataclass
class ResultadoRAR:
    chunks_originais: list[dict]
    chunks_remissoes: list[ChunkRemissao] = field(default_factory=list)
    remissoes_resolvidas: int = 0
    remissoes_nao_encontradas: list[int] = field(default_factory=list)


def _buscar_chunks_norma(
    norma_id: int,
    artigo: Optional[str] = None,
    limite: int = MAX_CHUNKS_POR_REMISSAO,
) -> list[dict]:
    """
    Busca chunks de uma norma referenciada.
    Se artigo fornecido, busca chunks daquele artigo específico.
    Retorna dicts com: chunk_id, norma_id, norma_codigo, artigo, texto.
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            if artigo:
                cur.execute(
                    """
                    SELECT c.id, c.norma_id, n.codigo, c.artigo, c.texto
                    FROM chunks c
                    JOIN normas n ON n.id = c.norma_id
                    WHERE c.norma_id = %s
                      AND c.artigo ILIKE %s
                    ORDER BY c.id
                    LIMIT %s
                    """,
                    (norma_id, f"%{artigo}%", limite),
                )
            else:
                cur.execute(
                    """
                    SELECT c.id, c.norma_id, n.codigo, c.artigo, c.texto
                    FROM chunks c
                    JOIN normas n ON n.id = c.norma_id
                    WHERE c.norma_id = %s
                    ORDER BY c.id
                    LIMIT %s
                    """,
                    (norma_id, limite),
                )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _extrair_artigo_da_remissao(conteudo_chunk: str) -> Optional[str]:
    """
    Tenta extrair o artigo referenciado no texto do chunk.
    Ex: "conforme art. 28 da LC 214/2025" → "28"
    Ex: "nos termos do §3º deste artigo" → "3"
    """
    padroes = [
        r'art(?:igo)?\.?\s*(\d+[°º]?)',
        r'§\s*(\d+[°º]?)',
        r'inciso\s+([IVX]+)',
    ]
    for padrao in padroes:
        match = re.search(padrao, conteudo_chunk, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def resolver_remissoes(chunks_retrieval: list[dict]) -> ResultadoRAR:
    """
    Para cada chunk com remissao_norm_id preenchido, busca o conteúdo da norma
    referenciada e prepara para injeção no contexto.

    Args:
        chunks_retrieval: lista de dicts com campos chunk_id, remissao_norm_id,
                          conteudo/texto, score_final — retornados pelo retrieval.

    Returns:
        ResultadoRAR com chunks originais e chunks das remissões resolvidas.
    """
    resultado = ResultadoRAR(chunks_originais=chunks_retrieval)

    chunks_com_remissao = [
        c for c in chunks_retrieval
        if c.get("remissao_norm_id") is not None
    ]

    if not chunks_com_remissao:
        return resultado

    # Limitar para controlar tokens
    chunks_para_resolver = chunks_com_remissao[:MAX_REMISSOES_POR_QUERY]

    normas_ja_resolvidas: set[int] = set()

    for chunk in chunks_para_resolver:
        norma_ref: int = chunk["remissao_norm_id"]

        # Evitar duplicatas por norma
        if norma_ref in normas_ja_resolvidas:
            continue
        normas_ja_resolvidas.add(norma_ref)

        conteudo = chunk.get("conteudo") or chunk.get("texto", "")
        artigo = _extrair_artigo_da_remissao(conteudo)

        try:
            rows = _buscar_chunks_norma(norma_ref, artigo)
            if not rows:
                # Tentar sem filtro de artigo
                rows = _buscar_chunks_norma(norma_ref)

            if rows:
                resultado.remissoes_resolvidas += 1
                score_orig = float(chunk.get("score_final", 0.0))
                for row in rows:
                    resultado.chunks_remissoes.append(ChunkRemissao(
                        chunk_id=row["id"],
                        norma_id=row["norma_id"],
                        norma_codigo=row["codigo"],
                        artigo=row.get("artigo") or "",
                        texto=row["texto"],
                        score_original=score_orig,
                        origem_chunk_id=chunk.get("chunk_id") or chunk.get("id", 0),
                    ))
                logger.info(
                    "RAR: norma_id=%d resolvida — %d chunk(s) adicionados ao contexto",
                    norma_ref, len(rows),
                )
            else:
                resultado.remissoes_nao_encontradas.append(norma_ref)
                logger.warning("RAR: norma_id=%d não encontrada na base", norma_ref)

        except Exception as e:
            logger.error("RAR: erro ao resolver norma_id=%d: %s", norma_ref, e)
            resultado.remissoes_nao_encontradas.append(norma_ref)

    return resultado


def formatar_chunks_rar_para_contexto(resultado: ResultadoRAR) -> str:
    """
    Formata os chunks de remissões para injeção no contexto do LLM.
    Separados dos chunks principais com cabeçalho identificador.
    """
    if not resultado.chunks_remissoes:
        return ""

    linhas = ["\n\n--- NORMAS REFERENCIADAS (RAR) ---"]
    linhas.append(
        f"Os {resultado.remissoes_resolvidas} trecho(s) abaixo são de normas "
        "referenciadas nos trechos principais acima:"
    )
    for cr in resultado.chunks_remissoes:
        linhas.append(f"\n[{cr.norma_codigo} — {cr.artigo}]\n{cr.texto}")

    return "\n".join(linhas)
