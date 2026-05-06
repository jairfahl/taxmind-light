"""
src/api/routers/analyze.py — Endpoints de análise cognitiva e RAG direto.

POST /v1/analyze  — análise tributária completa
GET  /v1/chunks   — busca RAG direta
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.api.auth_api import verificar_token_api, verificar_acesso_tenant
from src.api.limiter import limiter
from src.api.helpers import (
    _carregar_contexto_caso,
    _buscar_casos_similares,
    _get_tenant_info_by_user,
    _verificar_limite_consultas,
    _CONSULTA_TRIAL_LIMIT,
)
from src.db.pool import get_conn, put_conn
from src.cognitive.engine import MODEL_DEV, AnaliseResult, analisar
from src.rag.vigencia_checker import alertas_para_dict
from src.rag.retriever import ChunkResultado, retrieve
from src.quality.engine import QualidadeStatus
from src.billing.mau_tracker import registrar_evento_mau

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schema ---

class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Consulta tributária")
    norma_filter: Optional[list[str]] = Field(None, description="Filtrar por normas: EC132_2023, LC214_2025, LC227_2026")
    excluir_tipos: Optional[list[str]] = Field([], description="Tipos de norma a excluir do RAG (padrão: nenhum excluído)")
    top_k: int = Field(5, ge=1, le=10)
    model: str = Field(MODEL_DEV)
    decompose: bool = Field(False, description="Ativar decomposição de sub-perguntas para queries complexas")
    case_id: Optional[str] = Field(None, description="UUID do caso (steps 1→6) para injetar contexto dos passos anteriores")
    user_id: Optional[str] = Field(None, description="UUID do usuário autenticado (tenant isolation)")
    metodos_selecionados: list[str] = Field([], description="IDs dos métodos de análise selecionados no P1 (máx. 4)")
    criticidade: str = Field("media", description="Nível de criticidade do caso: baixa | media | alta | extrema")
    premissas: list[str] = Field([], description="Premissas regulatórias declaradas no P2 (mín. 3)")
    riscos_fiscais: list[str] = Field([], description="Riscos fiscais declarados no P2 (mín. 3)")
    fatos_cliente: dict = Field({}, description="Qualificação fática do cliente (G23): cnae, regime, UFs, tipo operação, faturamento")


# --- Serialização ---

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
        "forca_corrente_contraria": resultado.forca_corrente_contraria,
        "risco_adocao": resultado.risco_adocao,
        "scoring_confianca": resultado.scoring_confianca,
        "alertas_vigencia": alertas_para_dict(resultado.alertas_vigencia),
        "vigencia_ok": len(resultado.alertas_vigencia) == 0,
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
        "retrieval_strategy": resultado.retrieval_strategy,
        "saidas_stakeholders": resultado.saidas_stakeholders,
        "criticidade": resultado.criticidade,
        "criticidade_justificativa": resultado.criticidade_justificativa,
        "criticidade_impacto": resultado.criticidade_impacto,
    }


# --- Endpoints ---

@router.post("/v1/analyze", dependencies=[Depends(verificar_acesso_tenant)])
@limiter.limit("20/minute")
def analyze(request: Request, req: AnalyzeRequest):
    """
    Análise tributária completa (Steps 1→3).
    Retorna 400 se a qualidade for VERMELHO (bloqueado).
    Quando case_id é informado, injeta dados dos passos anteriores como contexto.
    """
    logger.info("POST /v1/analyze query=%s case_id=%s", req.query[:80], req.case_id)

    # Verificar limite de consultas trial (migration 135)
    _tenant_id_para_incremento: Optional[str] = None
    if req.user_id:
        _lim_conn = None
        try:
            _lim_conn = get_conn()
            _tenant_row = _get_tenant_info_by_user(req.user_id, _lim_conn)
            if _tenant_row and _tenant_row[1] == "trial":
                _t_id = str(_tenant_row[0])
                _permitido, _usado, _limite = _verificar_limite_consultas(_t_id, _lim_conn)
                if not _permitido:
                    raise HTTPException(
                        status_code=402,
                        detail={"code": "trial_consulta_limit", "usado": _usado, "limite": _limite},
                    )
                _tenant_id_para_incremento = _t_id
        except HTTPException:
            raise
        except Exception as _e:
            logger.warning("Falha na verificação de limite de consultas trial: %s", _e)
        finally:
            if _lim_conn:
                put_conn(_lim_conn)

    contexto_caso = None
    if req.case_id:
        contexto_caso = _carregar_contexto_caso(req.case_id)

    # Retroalimentação: buscar casos concluídos similares
    casos_similares = _buscar_casos_similares(req.query, case_id_atual=req.case_id)

    try:
        resultado = analisar(
            query=req.query,
            top_k=req.top_k,
            norma_filter=req.norma_filter,
            excluir_tipos=req.excluir_tipos if req.excluir_tipos is not None else [],
            model=req.model,
            decompose=req.decompose,
            contexto_caso=contexto_caso,
            casos_similares=casos_similares,
            user_id=req.user_id,
            metodos_selecionados=req.metodos_selecionados,
            criticidade=req.criticidade,
            premissas=req.premissas,
            riscos_fiscais=req.riscos_fiscais,
            fatos_cliente=req.fatos_cliente or {},
        )
    except Exception as e:
        from src.billing.token_budget import TokenBudgetExceeded
        from src.security.prompt_sanitizer import PromptInjectionError
        if isinstance(e, TokenBudgetExceeded):
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "daily_token_budget_exceeded",
                    "detail": "Limite de análises atingido para hoje. Redefine às 00:00 UTC.",
                    "usage": e.usage,
                    "limit": e.limit,
                    "plan": e.plan,
                },
            )
        if isinstance(e, PromptInjectionError):
            raise HTTPException(
                status_code=400,
                detail={"code": "PROMPT_INJECTION_DETECTED", "message": str(e)},
            )
        logger.error("Erro interno em /v1/analyze: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")

    if resultado.qualidade.status == QualidadeStatus.VERMELHO:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Consulta bloqueada pelo DataQualityEngine",
                "bloqueios": resultado.qualidade.bloqueios,
                "qualidade_status": "vermelho",
            },
        )

    # Metering MAU (G26, DEC-08) — falha silenciosa, nunca bloqueia a análise
    try:
        registrar_evento_mau(user_id=req.user_id)
    except Exception:
        pass

    # Incrementar contador trial (migration 135) — falha silenciosa
    if _tenant_id_para_incremento:
        _inc_conn = None
        try:
            _inc_conn = get_conn()
            with _inc_conn.cursor() as _cur:
                _cur.execute(
                    "UPDATE tenants SET consultas_trial_usadas = consultas_trial_usadas + 1 WHERE id = %s",
                    (_tenant_id_para_incremento,),
                )
            _inc_conn.commit()
        except Exception as _e:
            logger.warning("Falha ao incrementar consultas_trial_usadas: %s", _e)
        finally:
            if _inc_conn:
                put_conn(_inc_conn)

    return _analise_to_dict(resultado)


@router.get("/v1/chunks", dependencies=[Depends(verificar_token_api)])
def get_chunks(
    q: str = Query(..., description="Texto da busca"),
    top_k: int = Query(5, ge=1, le=10),
    norma: Optional[str] = Query(None, description="Código da norma para filtrar"),
):
    """Busca RAG direta sem análise cognitiva."""
    logger.info("GET /v1/chunks q=%s top_k=%d norma=%s", q[:60], top_k, norma)
    try:
        norma_filter = [norma] if norma else None
        chunks = retrieve(q, top_k=top_k, norma_filter=norma_filter, excluir_tipos=[])
    except Exception as e:
        logger.error("Erro em /v1/chunks: %s", e)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")

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
