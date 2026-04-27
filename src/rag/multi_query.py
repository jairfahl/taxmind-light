"""
rag/multi_query.py — Multi-Query Retrieval (RDM-024).

Gera N=4 reformulações técnicas de queries coloquiais, executa retrieval
paralelo e funde resultados por score (deduplicação por chunk_id).

Referência: RAG-Fusion / Multi-Query Retrieval patterns.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Optional

import anthropic

from src.rag.retriever import ChunkResultado, retrieve

logger = logging.getLogger(__name__)

MULTI_QUERY_N = 4

# Indicadores de linguagem coloquial ou imprecisa no domínio tributário
INDICADORES_COLOQUIAL = [
    r'\bimposto novo\b',
    r'\btaxa nova\b',
    r'\bimposto do governo\b',
    r'\bcobran[cç]a nova\b',
    r'\btributo novo\b',
    r'\bpagar imposto\b',
    r'\bcobrar imposto\b',
    r'\bpagar taxa\b',
]

TERMOS_TECNICOS = [
    r'\bIBS\b', r'\bCBS\b', r'\bPIS\b', r'\bCOFINS\b',
    r'\balíquota\b', r'\baliquota\b', r'\bbase de cálculo\b',
    r'\bLC 214\b', r'\bLC214\b', r'\bEC 132\b', r'\bEC132\b',
    r'\bLC 227\b', r'\bLC227\b', r'\bnão.cumulatividade\b',
    r'\bcrédito fiscal\b', r'\bfato gerador\b', r'\bcontribuinte\b',
    r'\bsplit payment\b', r'\bcashback\b', r'\bSimples Nacional\b',
]


def detectar_vocabulario_coloquial(query: str) -> bool:
    """Detecta se a query usa vocabulário coloquial ou impreciso.

    Critério 1: presença de indicadores coloquiais.
    Critério 2: ausência total de terminologia técnica em query > 5 palavras.
    """
    query_lower = query.lower()

    for padrao in INDICADORES_COLOQUIAL:
        if re.search(padrao, query_lower):
            return True

    palavras = query_lower.split()
    if len(palavras) > 5:
        tem_tecnico = any(re.search(t, query, re.IGNORECASE) for t in TERMOS_TECNICOS)
        if not tem_tecnico:
            return True

    return False


def gerar_variacoes_query(
    query: str,
    model: str,
    data_referencia: Optional[date] = None,
    regime: Optional[str] = None,
    n: int = MULTI_QUERY_N,
    tenant_id: str | None = None,
) -> list[str]:
    """Gera N reformulações técnicas da query original via LLM.

    Returns:
        list[str] — lista de variações técnicas (sem a query original).
    """
    contexto_temporal = ""
    if data_referencia and regime:
        contexto_temporal = (
            f"Período: {data_referencia.strftime('%Y-%m')}. "
            f"Regime: {regime} (Reforma Tributária brasileira). "
        )

    system_mq = (
        "Você é um especialista em direito tributário brasileiro. "
        "Receba uma pergunta em linguagem coloquial e gere exatamente "
        f"{n} reformulações técnicas da mesma pergunta, "
        "usando terminologia jurídico-tributária precisa. "
        f"{contexto_temporal}\n\n"
        "FORMATO DE RESPOSTA — JSON puro, sem markdown:\n"
        '{"variacoes": ["variacao1", "variacao2", "variacao3", "variacao4"]}\n\n'
        "Regras:\n"
        "- Cada variação deve abordar um ângulo diferente da mesma dúvida\n"
        "- Use termos: IBS, CBS, alíquota, base de cálculo, fato gerador, "
        "contribuinte, não-cumulatividade, crédito fiscal, LC 214/2025, EC 132/2023\n"
        "- Não repita a query original\n"
        "- Máximo 30 palavras por variação"
    )

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY não configurada")
    client = anthropic.Anthropic(api_key=key)

    resp = client.messages.create(
        model=model,
        max_tokens=400,
        temperature=0.3,
        system=system_mq,
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

    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        parsed = json.loads(raw)
        variacoes = parsed.get("variacoes", [])
        logger.info("Multi-Query: %d variações geradas", len(variacoes))
        return variacoes[:n]
    except json.JSONDecodeError:
        logger.warning("Multi-Query: JSON parsing falhou, usando query original")
        return [query]


def retrieve_multi_query(
    variacoes: list[str],
    top_k_por_variacao: int = 5,
    rerank_top_n: int = 15,
    norma_filter: Optional[list[str]] = None,
    excluir_tipos: Optional[list[str]] = None,
    cosine_weight: float = 0.7,
    bm25_weight: float = 0.3,
    data_referencia: Optional[date] = None,
    tenant_id: str | None = None,
) -> tuple[list[ChunkResultado], int, int]:
    """Executa retrieval paralelo para N variações e funde resultados.

    Returns:
        (chunks_fundidos, variacoes_com_resultado, total_bruto)
    """
    def _retrieve_variacao(variacao: str) -> list[ChunkResultado]:
        return retrieve(
            query=variacao,
            top_k=top_k_por_variacao,
            rerank_top_n=rerank_top_n,
            norma_filter=norma_filter,
            excluir_tipos=excluir_tipos,
            cosine_weight=cosine_weight,
            bm25_weight=bm25_weight,
            data_referencia=data_referencia,
            tenant_id=tenant_id,
        )

    todos_chunks: list[ChunkResultado] = []
    variacoes_com_resultado = 0

    with ThreadPoolExecutor(max_workers=min(len(variacoes), 4)) as executor:
        futures = {
            executor.submit(_retrieve_variacao, v): v
            for v in variacoes
        }
        for future in as_completed(futures):
            try:
                chunks = future.result()
                if chunks:
                    todos_chunks.extend(chunks)
                    variacoes_com_resultado += 1
            except Exception as e:
                logger.warning("Multi-Query: erro em variação: %s", e)

    total_bruto = len(todos_chunks)

    # Fusão: deduplicar por chunk_id, manter maior score_final
    mapa: dict[int, ChunkResultado] = {}
    for chunk in todos_chunks:
        existing = mapa.get(chunk.chunk_id)
        if existing is None or chunk.score_final > existing.score_final:
            mapa[chunk.chunk_id] = chunk

    chunks_fundidos = sorted(mapa.values(), key=lambda c: c.score_final, reverse=True)

    logger.info(
        "Multi-Query: %d variações, %d com resultado, %d bruto → %d fundidos",
        len(variacoes), variacoes_com_resultado, total_bruto, len(chunks_fundidos),
    )

    return chunks_fundidos, variacoes_com_resultado, total_bruto


def executar_multi_query_fallback(
    query: str,
    chunks_iniciais: list[ChunkResultado],
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
) -> tuple[list[ChunkResultado], bool, int]:
    """Executa Multi-Query se vocabulário coloquial detectado.

    Returns:
        (chunks_finais, multi_query_ativado, query_variations_count)
    """
    if not detectar_vocabulario_coloquial(query):
        return chunks_iniciais, False, 0

    logger.info("Multi-Query ativado: vocabulário coloquial detectado")

    try:
        variacoes = gerar_variacoes_query(query, model, data_referencia, regime, tenant_id=tenant_id)

        chunks_mq, variacoes_ok, total_bruto = retrieve_multi_query(
            variacoes=variacoes,
            top_k_por_variacao=max(top_k // MULTI_QUERY_N, 3),
            rerank_top_n=rerank_top_n,
            norma_filter=norma_filter,
            excluir_tipos=excluir_tipos,
            cosine_weight=cosine_weight,
            bm25_weight=bm25_weight,
            data_referencia=data_referencia,
            tenant_id=tenant_id,
        )

        if not chunks_mq:
            logger.info("Multi-Query: sem resultados, mantendo chunks iniciais")
            return chunks_iniciais, False, len(variacoes)

        # Limitar ao top_k
        return chunks_mq[:top_k], True, len(variacoes)

    except Exception as e:
        logger.warning("Multi-Query falhou, mantendo chunks iniciais: %s", e)
        return chunks_iniciais, False, 0
