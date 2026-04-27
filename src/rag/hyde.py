"""
rag/hyde.py — HyDE: Hypothetical Document Embeddings (RDM-020).

Gera documento hipotético via LLM e usa seu embedding para re-retrieval
quando queries INTERPRETATIVAS têm baixo score de similaridade.

Referência: arXiv:2212.10496
"""

import logging
import os
from datetime import date
from typing import Optional

import anthropic

from src.rag.retriever import ChunkResultado, retrieve, _embed_query

logger = logging.getLogger(__name__)

HYDE_THRESHOLD_SCORE = 0.72
HYDE_TIPOS_ELEGIVEIS = {"INTERPRETATIVA"}
HYDE_MAX_TOKENS_HIPOT = 300


def deve_ativar_hyde(
    tipo_query: str,
    chunks: list[ChunkResultado],
) -> bool:
    """Decide se HyDE deve ser ativado.

    Ativação: tipo_query == INTERPRETATIVA AND max(score_vetorial) < threshold.
    """
    if tipo_query.upper() not in HYDE_TIPOS_ELEGIVEIS:
        return False

    if not chunks:
        return True

    max_score = max(c.score_vetorial for c in chunks)
    return max_score < HYDE_THRESHOLD_SCORE


def gerar_documento_hipotetico(
    query: str,
    model: str,
    data_referencia: Optional[date] = None,
    regime: Optional[str] = None,
    tenant_id: str | None = None,
) -> str:
    """Gera documento hipotético via LLM que responderia à query.

    O documento NÃO é exibido ao usuário — serve apenas para re-embedding.
    Temperatura baixa (0.2) para minimizar alucinação.
    """
    contexto_temporal = ""
    if data_referencia and regime:
        contexto_temporal = (
            f"Considere o período {data_referencia.strftime('%Y-%m')} "
            f"no regime tributário '{regime}' da Reforma Tributária brasileira (LC 214/2025). "
        )

    system_hyde = (
        "Você é um redator de normas tributárias brasileiras. "
        "Gere um fragmento de norma tributária denso e específico que conteria a resposta "
        "para a pergunta fornecida. Estrutura obrigatória: "
        "artigo/dispositivo → regra → vigência → relação com fato gerador. "
        "Use terminologia técnica densa: IBS, CBS, IS, fato gerador, base de cálculo, "
        "alíquota de referência, não cumulatividade, regimes de apuração, "
        "SPED, EFD, DANFE, Comitê Gestor. "
        "Cite artigos e incisos quando relevante (ex: art. 12, §3º, inciso II). "
        "Sem introdução, sem explicação, sem markdown. "
        f"{contexto_temporal}"
        f"Limite: {HYDE_MAX_TOKENS_HIPOT} tokens."
    )

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY não configurada")
    client = anthropic.Anthropic(api_key=key)

    resp = client.messages.create(
        model=model,
        max_tokens=HYDE_MAX_TOKENS_HIPOT,
        temperature=0.2,
        system=system_hyde,
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

    hipotetico = resp.content[0].text.strip()
    logger.info("HyDE: documento hipotético gerado (%d chars)", len(hipotetico))
    return hipotetico


def retrieve_com_hyde(
    documento_hipotetico: str,
    top_k: int = 5,
    rerank_top_n: int = 15,
    norma_filter: Optional[list[str]] = None,
    excluir_tipos: Optional[list[str]] = None,
    cosine_weight: float = 0.7,
    bm25_weight: float = 0.3,
    data_referencia: Optional[date] = None,
    tenant_id: str | None = None,
) -> list[ChunkResultado]:
    """Executa retrieval usando embedding do documento hipotético.

    Reutiliza o pipeline completo de retrieve() — o documento hipotético
    é tratado como se fosse a query, gerando embedding via Voyage-3.
    """
    return retrieve(
        query=documento_hipotetico,
        top_k=top_k,
        rerank_top_n=rerank_top_n,
        norma_filter=norma_filter,
        excluir_tipos=excluir_tipos,
        cosine_weight=cosine_weight,
        bm25_weight=bm25_weight,
        data_referencia=data_referencia,
        tenant_id=tenant_id,
    )


def executar_hyde_fallback(
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
) -> tuple[list[ChunkResultado], bool]:
    """Executa HyDE fallback se condições forem atendidas.

    Returns:
        (chunks_finais, hyde_ativado)
    """
    if not deve_ativar_hyde(tipo_query, chunks_iniciais):
        return chunks_iniciais, False

    logger.info("HyDE ativado: tipo=%s max_score=%.3f < threshold=%.3f",
                tipo_query,
                max((c.score_vetorial for c in chunks_iniciais), default=0.0),
                HYDE_THRESHOLD_SCORE)

    try:
        hipotetico = gerar_documento_hipotetico(query, model, data_referencia, regime, tenant_id=tenant_id)

        chunks_hyde = retrieve_com_hyde(
            documento_hipotetico=hipotetico,
            top_k=top_k,
            rerank_top_n=rerank_top_n,
            norma_filter=norma_filter,
            excluir_tipos=excluir_tipos,
            cosine_weight=cosine_weight,
            bm25_weight=bm25_weight,
            data_referencia=data_referencia,
            tenant_id=tenant_id,
        )

        if not chunks_hyde:
            logger.info("HyDE: re-retrieval retornou vazio, mantendo resultado inicial")
            return chunks_iniciais, False

        max_score_hyde = max(c.score_vetorial for c in chunks_hyde)
        max_score_inicial = max((c.score_vetorial for c in chunks_iniciais), default=0.0)

        if max_score_hyde > max_score_inicial:
            logger.info("HyDE: melhoria detectada (%.3f > %.3f), usando chunks HyDE",
                        max_score_hyde, max_score_inicial)
            return chunks_hyde, True
        else:
            logger.info("HyDE: sem melhoria (%.3f <= %.3f), mantendo resultado inicial",
                        max_score_hyde, max_score_inicial)
            return chunks_iniciais, False

    except Exception as e:
        logger.warning("HyDE falhou, mantendo resultado inicial: %s", e)
        return chunks_iniciais, False
