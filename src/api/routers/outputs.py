"""
src/api/routers/outputs.py — Endpoints de outputs acionáveis (C1–C5) e exportação PDF.

POST /v1/outputs
GET  /v1/outputs/{output_id}
POST /v1/outputs/{output_id}/aprovar
POST /v1/export/pdf
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.api.auth_api import verificar_acesso_tenant
from src.api.helpers import _verificar_acesso_output
from src.api.limiter import limiter
from src.db.pool import get_conn, put_conn
from src.cognitive.engine import MODEL_DEV, analisar
from src.outputs.engine import OutputClass, OutputEngine, OutputError, OutputResult
from src.outputs.stakeholders import StakeholderTipo

logger = logging.getLogger(__name__)

router = APIRouter()

_output_engine = OutputEngine()


# --- Schemas ---

class GerarOutputRequest(BaseModel):
    case_id: str
    classe: str = Field(..., description="alerta|nota_trabalho|recomendacao_formal|dossie_decisao|material_compartilhavel")
    stakeholders: Optional[list[str]] = Field(None, description="Lista de stakeholder_tipo")
    # Para alerta (C1)
    titulo: Optional[str] = None
    contexto: Optional[str] = None
    materialidade: Optional[int] = Field(None, ge=1, le=5)
    # Para C2/C3 — AnaliseResult embutido
    query: Optional[str] = None
    # Para C5 — base output_id
    output_base_id: Optional[str] = None
    # Para C2/C3 — modelo a usar na análise
    model: str = Field(MODEL_DEV)
    user_id: Optional[str] = Field(None, description="UUID do usuário autenticado (tenant isolation)")


class AprovarOutputRequest(BaseModel):
    aprovado_por: str = Field(..., min_length=2)
    observacao: Optional[str] = None


# --- Serialização ---

def _output_result_to_dict(r: OutputResult) -> dict:
    return {
        "id": r.id,
        "case_id": r.case_id,
        "passo_origem": r.passo_origem,
        "classe": r.classe.value,
        "status": r.status.value,
        "titulo": r.titulo,
        "conteudo": r.conteudo,
        "materialidade": r.materialidade,
        "disclaimer": r.disclaimer,
        "versao_prompt": r.versao_prompt,
        "versao_base": r.versao_base,
        "created_at": r.created_at,
        "stakeholder_views": [
            {
                "stakeholder": v.stakeholder.value,
                "resumo": v.resumo,
                "campos_visiveis": v.campos_visiveis,
            }
            for v in r.stakeholder_views
        ],
    }


# --- Endpoints ---

@router.post("/v1/outputs", status_code=201, dependencies=[Depends(verificar_acesso_tenant)])
def gerar_output(req: GerarOutputRequest):
    """
    Gera um output acionável (C1–C5).
    - C1 (alerta): requer titulo, contexto, materialidade
    - C2 (nota_trabalho): requer query — executa análise cognitiva internamente
    - C3 (recomendacao_formal): requer query
    - C4 (dossie_decisao): requer Step 5 (Decidir) concluído no caso
    - C5 (material_compartilhavel): requer output_base_id com C3/C4 aprovado
    """
    logger.info("POST /v1/outputs case_id=%s classe=%s", req.case_id, req.classe)

    try:
        classe = OutputClass(req.classe)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"classe inválida: {req.classe}")

    stk_list: Optional[list[StakeholderTipo]] = None
    if req.stakeholders:
        try:
            stk_list = [StakeholderTipo(s) for s in req.stakeholders]
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"stakeholder inválido: {e}")

    try:
        if classe == OutputClass.ALERTA:
            if not req.titulo or not req.contexto or req.materialidade is None:
                raise HTTPException(
                    status_code=422,
                    detail="C1 (alerta) requer titulo, contexto e materialidade"
                )
            result = _output_engine.gerar_alerta(
                case_id=req.case_id,
                passo=2,
                titulo=req.titulo,
                contexto=req.contexto,
                materialidade=req.materialidade,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.NOTA_TRABALHO:
            if not req.query:
                raise HTTPException(status_code=422, detail="C2 requer query")
            analise = analisar(query=req.query, top_k=3, model=req.model, user_id=req.user_id)
            result = _output_engine.gerar_nota_trabalho(
                case_id=req.case_id,
                analise_result=analise,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.RECOMENDACAO_FORMAL:
            if not req.query:
                raise HTTPException(status_code=422, detail="C3 requer query")
            analise = analisar(query=req.query, top_k=3, model=req.model, user_id=req.user_id)
            result = _output_engine.gerar_recomendacao_formal(
                case_id=req.case_id,
                analise_result=analise,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.DOSSIE_DECISAO:
            result = _output_engine.gerar_dossie(
                case_id=req.case_id,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.MATERIAL_COMPARTILHAVEL:
            if not req.output_base_id:
                raise HTTPException(status_code=422, detail="C5 requer output_base_id")
            if not stk_list:
                raise HTTPException(status_code=422, detail="C5 requer ao menos um stakeholder")
            result = _output_engine.gerar_material_compartilhavel(
                output_id=req.output_base_id,
                stakeholders=stk_list,
            )
        else:
            raise HTTPException(status_code=422, detail="Classe não suportada")

    except HTTPException:
        raise
    except OutputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro em POST /v1/outputs: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")

    return _output_result_to_dict(result)


@router.get("/v1/outputs/{output_id}")
def get_output(output_id: str, current_user: dict = Depends(verificar_acesso_tenant)):
    """Retorna output completo com views por stakeholder."""
    logger.info("GET /v1/outputs/%s", output_id)
    _verificar_acesso_output(output_id, current_user.get("sub"), current_user.get("perfil"))
    try:
        from src.outputs.engine import _load_output
        conn = get_conn()
        try:
            result = _load_output(conn, output_id)
        finally:
            put_conn(conn)
    except OutputError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em GET /v1/outputs/%s: %s", output_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return _output_result_to_dict(result)


@router.post("/v1/outputs/{output_id}/aprovar", dependencies=[Depends(verificar_acesso_tenant)])
def aprovar_output(output_id: str, req: AprovarOutputRequest):
    """
    Aprova um output. Status gerado → aprovado.
    C3 e C5 exigem aprovação antes de publicação.
    """
    logger.info("POST /v1/outputs/%s/aprovar por=%s", output_id, req.aprovado_por)
    try:
        result = _output_engine.aprovar(
            output_id=output_id,
            aprovado_por=req.aprovado_por,
            observacao=req.observacao,
        )
    except OutputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro em aprovar_output: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return _output_result_to_dict(result)


# --- Export PDF ---

class ExportPDFRequest(BaseModel):
    source_type: Literal["analysis", "dossie"]
    source_id: Optional[str] = None
    analysis_data: Optional[dict] = None


@router.post("/v1/export/pdf", dependencies=[Depends(verificar_acesso_tenant)])
@limiter.limit("10/minute")
async def export_pdf(
    request: Request,
    body: ExportPDFRequest,
    current_user: dict = Depends(verificar_acesso_tenant),
):
    """Gera e retorna PDF para análise livre ou dossiê."""
    from asyncio import get_event_loop
    from functools import partial
    from src.export.pdf_generator import generate_pdf, pdf_filename

    logger.info("POST /v1/export/pdf source_type=%s", body.source_type)

    if body.source_type == "dossie":
        if not body.source_id:
            raise HTTPException(status_code=422, detail="source_id obrigatório para source_type=dossie")
        _verificar_acesso_output(body.source_id, current_user.get("sub"), current_user.get("perfil"))
        try:
            from src.outputs.engine import _load_output
            conn = get_conn()
            try:
                result = _load_output(conn, body.source_id)
            finally:
                put_conn(conn)
        except OutputError as e:
            raise HTTPException(status_code=404, detail=str(e))
        data = _output_result_to_dict(result)
        classe = data.get("classe")
    else:
        if not body.analysis_data:
            raise HTTPException(status_code=422, detail="analysis_data obrigatório para source_type=analysis")
        data = body.analysis_data
        classe = data.get("classe", "nota_trabalho")

    tenant_info: dict = {}
    user_id = current_user.get("sub")
    if user_id:
        try:
            conn = get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT t.nome, t.cnpj, u.perfil FROM users u "
                        "LEFT JOIN tenants t ON t.id = u.tenant_id "
                        "WHERE u.id = %s LIMIT 1",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        tenant_info = {"nome": row[0] or "Orbis.tax", "cnpj": row[1], "plano": row[2]}
            finally:
                put_conn(conn)
        except Exception:
            pass

    try:
        loop = get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None, partial(generate_pdf, body.source_type, data, classe, tenant_info)
        )
    except Exception as e:
        logger.error("Erro na geração de PDF: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar PDF. Tente novamente.")

    filename = pdf_filename(body.source_type, classe)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
