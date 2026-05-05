"""
src/api/routers/observability.py — Endpoints de observabilidade e monitoramento.

GET  /v1/observability/metrics
GET  /v1/observability/drift
POST /v1/observability/drift/{alert_id}/resolver
POST /v1/observability/baseline
POST /v1/observability/regression
GET  /v1/observability/budget-pressure
POST /v1/monitor/verificar
GET  /v1/monitor/pendentes
GET  /v1/monitor/contagem
PATCH /v1/monitor/documentos/{doc_id}
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_api import verificar_token_api, verificar_admin
from src.db.pool import get_conn, put_conn

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---

class BaselineRequest(BaseModel):
    prompt_version: str
    model_id: str


class RegressionRequest(BaseModel):
    prompt_version: str
    model_id: str
    baseline_version: str


class ResolverDriftRequest(BaseModel):
    observacao: str = Field(..., min_length=1)


class AtualizarDocMonitorRequest(BaseModel):
    status: str = Field(..., description="'ingerido' ou 'descartado'")


# --- Endpoints ---

@router.get("/v1/observability/metrics", dependencies=[Depends(verificar_token_api)])
def get_metrics(
    days: int = Query(7, ge=1, le=90),
    prompt_version: Optional[str] = Query(None),
):
    """Métricas diárias agregadas dos últimos N dias."""
    logger.info("GET /v1/observability/metrics days=%d pv=%s", days, prompt_version)
    conn = get_conn()
    try:
        cur = conn.cursor()
        sql = """
            SELECT data_referencia, prompt_version, model_id, total_interacoes,
                   avg_latencia_ms, p95_latencia_ms, pct_scoring_alto, pct_contra_tese,
                   pct_grounding_presente, taxa_alucinacao,
                   taxa_bloqueio_m1, taxa_bloqueio_m2, taxa_bloqueio_m3, taxa_bloqueio_m4
            FROM ai_metrics_daily
            WHERE data_referencia >= CURRENT_DATE - %s::interval
        """
        params: list = [f"{days} days"]
        if prompt_version:
            sql += " AND prompt_version = %s"
            params.append(prompt_version)
        sql += " ORDER BY data_referencia DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = ["data_referencia", "prompt_version", "model_id", "total_interacoes",
                "avg_latencia_ms", "p95_latencia_ms", "pct_scoring_alto", "pct_contra_tese",
                "pct_grounding_presente", "taxa_alucinacao",
                "taxa_bloqueio_m1", "taxa_bloqueio_m2", "taxa_bloqueio_m3", "taxa_bloqueio_m4"]
        result = [dict(zip(cols, [str(v) if hasattr(v, "isoformat") else v for v in row]))
                  for row in rows]
        if rows:
            def avg(col):
                vals = [r[cols.index(col)] for r in rows if r[cols.index(col)] is not None]
                return sum(vals) / len(vals) if vals else None
            resumo = {
                "total_interacoes": sum(r[3] for r in rows),
                "avg_latencia_ms": avg("avg_latencia_ms"),
                "p95_latencia_ms": avg("p95_latencia_ms"),
                "pct_scoring_alto": avg("pct_scoring_alto"),
                "taxa_alucinacao": avg("taxa_alucinacao"),
            }
        else:
            resumo = {}
        cur.close()
    except Exception as e:
        logger.error("Erro em /v1/observability/metrics: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        put_conn(conn)
    return {"metrics": result, "resumo": resumo, "days": days}


@router.get("/v1/observability/drift", dependencies=[Depends(verificar_token_api)])
def get_drift_alerts(
    prompt_version: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
):
    """Lista drift alerts ativos (resolvido=False)."""
    logger.info("GET /v1/observability/drift pv=%s", prompt_version)
    conn = get_conn()
    try:
        cur = conn.cursor()
        sql = """
            SELECT id, detectado_em, prompt_version, model_id, metrica,
                   valor_baseline, valor_atual, desvios_padrao, resolvido, observacao
            FROM drift_alerts
            WHERE resolvido = FALSE
        """
        params: list = []
        if prompt_version:
            sql += " AND prompt_version = %s"
            params.append(prompt_version)
        if model_id:
            sql += " AND model_id = %s"
            params.append(model_id)
        sql += " ORDER BY detectado_em DESC"
        cur.execute(sql, params)
        cols = ["id", "detectado_em", "prompt_version", "model_id", "metrica",
                "valor_baseline", "valor_atual", "desvios_padrao", "resolvido", "observacao"]
        result = [dict(zip(cols, [str(v) if hasattr(v, "isoformat") else v for v in row]))
                  for row in cur.fetchall()]
        cur.close()
    except Exception as e:
        logger.error("Erro em /v1/observability/drift: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        put_conn(conn)
    return result


@router.post("/v1/observability/drift/{alert_id}/resolver", dependencies=[Depends(verificar_token_api)])
def resolver_drift(alert_id: int, req: ResolverDriftRequest):
    """Resolve um drift alert com observação."""
    logger.info("POST /v1/observability/drift/%d/resolver", alert_id)
    try:
        from src.observability.drift import DriftDetector, DriftDetectorError
        DriftDetector().resolver_alert(alert_id, req.observacao)
    except DriftDetectorError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em resolver_drift: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {"resolvido": True, "alert_id": alert_id}


@router.post("/v1/observability/baseline", status_code=201, dependencies=[Depends(verificar_token_api)])
def registrar_baseline(req: BaselineRequest):
    """Registra baseline de métricas para a versão de prompt/modelo especificada."""
    logger.info("POST /v1/observability/baseline pv=%s model=%s", req.prompt_version, req.model_id)
    try:
        from src.observability.drift import DriftDetector, DriftDetectorError
        result = DriftDetector().registrar_baseline(req.prompt_version, req.model_id)
    except DriftDetectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro em registrar_baseline: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return result


@router.post("/v1/observability/regression", dependencies=[Depends(verificar_token_api)])
def executar_regression(req: RegressionRequest):
    """
    Executa regression testing sobre o dataset de avaliação.
    Timeout do cliente deve ser ≥ 120s — faz chamadas reais ao LLM.
    """
    logger.info("POST /v1/observability/regression pv=%s model=%s", req.prompt_version, req.model_id)
    try:
        from src.observability.regression import RegressionRunner
        result = RegressionRunner().executar(
            prompt_version=req.prompt_version,
            model_id=req.model_id,
            baseline_version=req.baseline_version,
        )
    except Exception as e:
        logger.error("Erro em executar_regression: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {
        "aprovado": result.aprovado,
        "precisao_citacao": result.precisao_citacao,
        "taxa_alucinacao": result.taxa_alucinacao,
        "acuracia_recomendacao": result.acuracia_recomendacao,
        "latencia_p95": result.latencia_p95,
        "cobertura_contra_tese": result.cobertura_contra_tese,
        "detalhes": result.detalhes,
    }


@router.get("/v1/observability/budget-pressure", dependencies=[Depends(verificar_token_api)])
def budget_pressure():
    """Retorna pressão média de budget por query_tipo nos últimos 30 dias."""
    logger.info("GET /v1/observability/budget-pressure")
    try:
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    CASE
                        WHEN context_budget_log LIKE '%%FACTUAL%%' THEN 'FACTUAL'
                        WHEN context_budget_log LIKE '%%COMPARATIVA%%' THEN 'COMPARATIVA'
                        WHEN context_budget_log LIKE '%%INTERPRETATIVA%%' THEN 'INTERPRETATIVA'
                        ELSE 'OUTRO'
                    END AS query_tipo,
                    ROUND(AVG(budget_pressao_pct)::numeric, 1) AS avg_pressao,
                    ROUND(MAX(budget_pressao_pct)::numeric, 1) AS max_pressao,
                    COUNT(*) AS total_analises
                FROM ai_interactions
                WHERE budget_pressao_pct IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '30 days'
                GROUP BY 1
                ORDER BY 2 DESC
            """)
            rows = cur.fetchall()
            cur.close()
        finally:
            put_conn(conn)
        return [
            {
                "query_tipo": r[0],
                "avg_pressao_pct": float(r[1]) if r[1] else 0,
                "max_pressao_pct": float(r[2]) if r[2] else 0,
                "total_analises": r[3],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("Erro em budget-pressure: %s", e, exc_info=True)
        return []


@router.post("/v1/monitor/verificar", dependencies=[Depends(verificar_admin)])
def verificar_fontes():
    """Verifica todas as fontes ativas e detecta novos documentos."""
    logger.info("POST /v1/monitor/verificar")
    try:
        from src.monitor.checker import verificar_todas_fontes
        resultados = verificar_todas_fontes()
    except Exception as e:
        logger.error("Erro em /v1/monitor/verificar: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {
        "fontes_verificadas": len(resultados),
        "total_novos": sum(r.novos for r in resultados),
        "resultados": [
            {
                "fonte": r.fonte_nome,
                "tipo": r.fonte_tipo,
                "novos": r.novos,
                "encontrados": r.total_encontrados,
                "erro": r.erro,
            }
            for r in resultados
        ],
    }


@router.get("/v1/monitor/pendentes", dependencies=[Depends(verificar_admin)])
def listar_docs_pendentes():
    """Lista documentos detectados aguardando revisao do usuario."""
    logger.info("GET /v1/monitor/pendentes")
    try:
        from src.monitor.checker import listar_pendentes
        docs = listar_pendentes()
    except Exception as e:
        logger.error("Erro em /v1/monitor/pendentes: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {
        "total": len(docs),
        "documentos": [
            {
                "id": d.id,
                "titulo": d.titulo,
                "url": d.url,
                "data_publicacao": d.data_publicacao,
                "resumo": d.resumo,
                "fonte": d.fonte_nome,
                "tipo": d.fonte_tipo,
                "detectado_em": d.detectado_em,
            }
            for d in docs
        ],
    }


@router.get("/v1/monitor/contagem", dependencies=[Depends(verificar_admin)])
def contagem_pendentes():
    """Retorna quantidade de documentos novos pendentes."""
    try:
        from src.monitor.checker import contar_pendentes
        return {"pendentes": contar_pendentes()}
    except Exception:
        return {"pendentes": 0}


@router.patch("/v1/monitor/documentos/{doc_id}", dependencies=[Depends(verificar_admin)])
def atualizar_doc_monitor(doc_id: int, req: AtualizarDocMonitorRequest):
    """Atualiza status de um documento monitorado."""
    logger.info("PATCH /v1/monitor/documentos/%d status=%s", doc_id, req.status)
    if req.status not in ("ingerido", "descartado"):
        raise HTTPException(status_code=422, detail="Status deve ser 'ingerido' ou 'descartado'")
    try:
        from src.monitor.checker import atualizar_status
        ok = atualizar_status(doc_id, req.status)
        if not ok:
            raise HTTPException(status_code=404, detail="Documento nao encontrado")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro em PATCH /v1/monitor/documentos/%d: %s", doc_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {"atualizado": True, "doc_id": doc_id, "status": req.status}
