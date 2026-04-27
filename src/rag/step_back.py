"""
rag/step_back.py — Step-Back Prompting (RDM-025).

Para queries de alta especificidade (CNAE, NCM, regime específico), gera
versão abstrata da query para recuperar princípios gerais, depois funde
com retrieval da query original.

Referência: arXiv:2310.06117
"""

import logging
import os
import re
from datetime import date
from typing import Optional

import anthropic

from src.rag.retriever import ChunkResultado, retrieve

logger = logging.getLogger(__name__)

STEP_BACK_TIPOS_ELEGIVEIS = {"INTERPRETATIVA", "COMPARATIVA"}

INDICADORES_ALTA_ESPECIFICIDADE = [
    r'\bCNAE\s+\d{4}[-./]?\d{0,2}\b',
    r'\bCNAE\b.*\b\d{4}\b',
    r'\bNCM\s+\d{4}\b',
    r'\bNCM\b.*\b\d{8}\b',
    r'\blucro (real|presumido|arbitrado)\b',
    r'\bSimples Nacional\b.*\b(Anexo|faixa)\b',
    r'\b(importa[cç][aã]o|exporta[cç][aã]o)\b.*\b(produto|mercadoria)\b.*específic',
    r'\bopera[cç][aã]o interestad',
    r'\bpessoa física\b.*\b(IBS|CBS)\b',
    r'\bmicroempresa\b.*\balíquota\b',
]


def detectar_alta_especificidade(query: str, tipo_query: str) -> bool:
    """Detecta se a query é de alta especificidade (CNAE, NCM, regime específico).

    Ativação: tipo INTERPRETATIVA ou COMPARATIVA + indicador de especificidade.
    """
    if tipo_query.upper() not in STEP_BACK_TIPOS_ELEGIVEIS:
        return False

    for padrao in INDICADORES_ALTA_ESPECIFICIDADE:
        if re.search(padrao, query, re.IGNORECASE):
            return True

    return False


def gerar_step_back_query(
    query: str,
    model: str,
    data_referencia: Optional[date] = None,
    regime: Optional[str] = None,
    tenant_id: str | None = None,
) -> str:
    """Gera versão abstrata da query para retrieval de princípios gerais.

    Temperatura baixíssima (0.1) para abstração determinística.
    """
    contexto_temporal = ""
    if data_referencia and regime:
        contexto_temporal = (
            f"Período: {data_referencia.strftime('%Y-%m')}. "
            f"Regime: {regime}. "
        )

    system_sb = (
        "Você é um especialista em direito tributário brasileiro. "
        "Receba uma pergunta muito específica e reescreva-a de forma mais abstrata, "
        "focando no princípio geral ou conceito jurídico-tributário subjacente — "
        "sem mencionar o caso específico (CNAE, NCM, empresa, produto). "
        f"{contexto_temporal}\n\n"
        "FORMATO: retorne APENAS a pergunta reformulada, sem explicação, sem markdown.\n\n"
        "Exemplos:\n"
        "Original: 'Empresa com CNAE 4711-3/02 (supermercado) no lucro real deve pagar CBS "
        "sobre transferência entre filiais em 2028?'\n"
        "Step-back: 'Como incide CBS sobre transferências entre estabelecimentos do mesmo "
        "contribuinte no regime de transição IBS/CBS?'\n\n"
        "Original: 'NCM 8471.30.19 importado da China tem crédito de IBS em 2033?'\n"
        "Step-back: 'Quais são as regras de aproveitamento de crédito de IBS em operações "
        "de importação no regime definitivo?'"
    )

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY não configurada")
    client = anthropic.Anthropic(api_key=key)

    resp = client.messages.create(
        model=model,
        max_tokens=100,
        temperature=0.1,
        system=system_sb,
        messages=[{"role": "user", "content": query}],
    )

    # Registrar consumo
    try:
        from src.observability.usage import registrar_uso
        registrar_uso(
            service="anthropic",
            model=model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            tenant_id=tenant_id,
        )
    except Exception:
        pass

    sb_query = resp.content[0].text.strip()
    logger.info("Step-Back: query abstrata gerada (%d chars)", len(sb_query))
    return sb_query


def retrieve_com_step_back(
    query_original: str,
    step_back_query: str,
    top_k: int = 5,
    rerank_top_n: int = 15,
    norma_filter: Optional[list[str]] = None,
    excluir_tipos: Optional[list[str]] = None,
    cosine_weight: float = 0.7,
    bm25_weight: float = 0.3,
    data_referencia: Optional[date] = None,
    proporcao_step_back: float = 0.6,
    tenant_id: str | None = None,
) -> tuple[list[ChunkResultado], int, int]:
    """Retrieval duplo: step-back (princípio geral) + original (específico).

    Args:
        proporcao_step_back: fração do top_k para step-back (default 60%).

    Returns:
        (chunks_fundidos, n_step_back, n_especifico)
    """
    top_k_sb = max(1, int(top_k * proporcao_step_back))
    top_k_esp = max(1, top_k - top_k_sb)

    # Retrieval step-back (princípio geral)
    chunks_sb = retrieve(
        query=step_back_query,
        top_k=top_k_sb,
        rerank_top_n=rerank_top_n,
        norma_filter=norma_filter,
        excluir_tipos=excluir_tipos,
        cosine_weight=cosine_weight,
        bm25_weight=bm25_weight,
        data_referencia=data_referencia,
        tenant_id=tenant_id,
    )

    # Retrieval original (específico)
    chunks_orig = retrieve(
        query=query_original,
        top_k=top_k_esp,
        rerank_top_n=rerank_top_n,
        norma_filter=norma_filter,
        excluir_tipos=excluir_tipos,
        cosine_weight=cosine_weight,
        bm25_weight=bm25_weight,
        data_referencia=data_referencia,
        tenant_id=tenant_id,
    )

    # Fusão: deduplicar por chunk_id, manter maior score_final
    mapa: dict[int, ChunkResultado] = {}
    for chunk in chunks_sb + chunks_orig:
        existing = mapa.get(chunk.chunk_id)
        if existing is None or chunk.score_final > existing.score_final:
            mapa[chunk.chunk_id] = chunk

    chunks_fundidos = sorted(mapa.values(), key=lambda c: c.score_final, reverse=True)[:top_k]

    logger.info(
        "Step-Back: %d step-back + %d específico → %d fundidos",
        len(chunks_sb), len(chunks_orig), len(chunks_fundidos),
    )

    return chunks_fundidos, len(chunks_sb), len(chunks_orig)


def executar_step_back_fallback(
    query: str,
    chunks_iniciais: list[ChunkResultado],
    tipo_query: str,
    model: str,
    top_k: int = 5,
    rerank_top_n: int = 15,
    norma_filter: Optional[list[str]] = None,
    excluir_tipos: Optional[list[str]] = None,
    cosine_weight: float = 0.7,
    bm25_weight: float = 0.3,
    data_referencia: Optional[date] = None,
    regime: Optional[str] = None,
    tenant_id: str | None = None,
) -> tuple[list[ChunkResultado], bool, Optional[str]]:
    """Executa Step-Back se alta especificidade detectada.

    Returns:
        (chunks_finais, step_back_ativado, step_back_query_texto)
    """
    if not detectar_alta_especificidade(query, tipo_query):
        return chunks_iniciais, False, None

    logger.info("Step-Back ativado: alta especificidade detectada")

    try:
        sb_query = gerar_step_back_query(query, model, data_referencia, regime, tenant_id=tenant_id)

        chunks_sb, n_sb, n_esp = retrieve_com_step_back(
            query_original=query,
            step_back_query=sb_query,
            top_k=top_k,
            rerank_top_n=rerank_top_n,
            norma_filter=norma_filter,
            excluir_tipos=excluir_tipos,
            cosine_weight=cosine_weight,
            bm25_weight=bm25_weight,
            data_referencia=data_referencia,
            tenant_id=tenant_id,
        )

        if not chunks_sb:
            logger.info("Step-Back: sem resultados, mantendo chunks iniciais")
            return chunks_iniciais, False, sb_query

        return chunks_sb, True, sb_query

    except Exception as e:
        logger.warning("Step-Back falhou, mantendo chunks iniciais: %s", e)
        return chunks_iniciais, False, None
