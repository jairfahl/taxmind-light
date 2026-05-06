"""
src/api/routers/cases.py — Endpoints do protocolo P1→P6.

POST /v1/cases
GET  /v1/cases
GET  /v1/cases/{case_id}
POST /v1/cases/{case_id}/steps/{passo}
POST /v1/cases/{case_id}/carimbo/confirmar
GET  /v1/cases/{case_id}/outputs
"""

import logging
import uuid as _uuid_mod
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_api import verificar_token_api, verificar_acesso_tenant
from src.api.helpers import (
    _get_tenant_info_by_user,
    _verificar_acesso_caso,
    _verificar_limite_casos,
)
from src.db.pool import get_conn, put_conn
from src.cognitive.detector_carimbo import detectar_carimbo as _detectar_carimbo_lexico
from src.protocol.carimbo import CarimboConfirmacaoError, DetectorCarimbo
from src.protocol.engine import CaseEstado, ProtocolError, ProtocolStateEngine
from src.outputs.engine import OutputEngine, OutputResult

logger = logging.getLogger(__name__)

router = APIRouter()

_protocol_engine = ProtocolStateEngine()
_carimbo_detector = DetectorCarimbo()
_output_engine = OutputEngine()


# --- Schemas ---

class CriarCasoRequest(BaseModel):
    titulo: str = Field(..., min_length=10, description="Título do caso (mín. 10 chars)")
    descricao: str = Field(..., min_length=1)
    contexto_fiscal: str = Field(..., min_length=1)
    user_id: Optional[str] = Field(None, description="ID do usuário — necessário para rastreamento de tenant e verificação de limite")


class SubmeterPassoRequest(BaseModel):
    dados: dict = Field(..., description="Dados do passo conforme campos obrigatórios")
    acao: str = Field("avancar", description="'avancar' ou 'voltar'")


class ConfirmarCarimboRequest(BaseModel):
    alert_id: int
    justificativa: str = Field(..., min_length=20)


# --- Serialização ---

def _case_estado_to_dict(estado: CaseEstado) -> dict:
    return {
        "case_id": estado.case_id,
        "titulo": estado.titulo,
        "status": estado.status,
        "passo_atual": estado.passo_atual,
        "steps": {
            str(p): {"dados": v["dados"], "concluido": v["concluido"]}
            for p, v in estado.steps.items()
        },
        "historico": estado.historico,
        "created_at": estado.created_at,
        "updated_at": estado.updated_at,
    }


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

@router.post("/v1/cases", status_code=201, dependencies=[Depends(verificar_acesso_tenant)])
def criar_caso(req: CriarCasoRequest):
    """Cria um novo caso protocolar em Step 1/rascunho. Verifica limite por plano quando user_id fornecido."""
    logger.info("POST /v1/cases titulo=%s user_id=%s", req.titulo[:60], req.user_id)
    conn = None
    tenant_id = None
    try:
        # Verificar limite se user_id fornecido
        if req.user_id:
            conn = get_conn()
            row = _get_tenant_info_by_user(req.user_id, conn)
            if row:
                t_id, sub_status, plano, trial_ends = row
                tenant_id = str(t_id)
                permitido, usado, limite = _verificar_limite_casos(
                    tenant_id, sub_status, plano, trial_ends, conn
                )
                if not permitido:
                    limite_str = str(limite)
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            f"Limite de casos atingido ({usado}/{limite_str}). "
                            "Faça upgrade do plano para criar mais casos."
                        ),
                    )
            put_conn(conn)
            conn = None

        # Criar caso via protocol engine (faz commit internamente)
        case_id = _protocol_engine.criar_caso(
            titulo=req.titulo,
            descricao=req.descricao,
            contexto_fiscal=req.contexto_fiscal,
        )

        # Vincular tenant_id ao caso recem criado
        if tenant_id:
            conn2 = get_conn()
            try:
                cur = conn2.cursor()
                cur.execute("UPDATE cases SET tenant_id = %s WHERE id = %s", (tenant_id, case_id))
                conn2.commit()
                cur.close()
            finally:
                put_conn(conn2)

        return {"case_id": case_id, "status": "rascunho", "passo_atual": 1}

    except HTTPException:
        raise
    except ProtocolError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Erro em /v1/cases: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.get("/v1/cases", dependencies=[Depends(verificar_token_api)])
def listar_casos(user_id: Optional[str] = Query(None)):
    """Lista casos do tenant (filtrado por user_id quando fornecido). Exclui casos de testes."""
    logger.info("GET /v1/cases user_id=%s", user_id)
    conn = None
    try:
        conn = get_conn()

        # Resolver tenant_id a partir do user_id
        tenant_id = None
        if user_id:
            row = _get_tenant_info_by_user(user_id, conn)
            if row:
                tenant_id = str(row[0])

        cur = conn.cursor()
        exclusoes = [
            "%%teste%%", "%%test%%", "%%smoke%%", "%%validar%%",
            "%%bloqueio%%", "%%invalido%%", "%%retrocesso%%", "%%avancar%%",
            "%%voltar%%", "%%submeter%%", "%%integração%%", "%%integracao%%",
            "%%output ja%%", "%%listar outputs%%", "%%aprovacao%%",
            "%%get estado%%", "%%get output%%",
        ]
        not_ilike_placeholders = " ".join("AND titulo NOT ILIKE %s" for _ in exclusoes)
        not_ilike_params = tuple(exclusoes)

        if tenant_id:
            cur.execute(
                f"""SELECT DISTINCT ON (titulo) id, titulo, status, passo_atual, created_at
                   FROM cases
                   WHERE tenant_id = %s
                     {not_ilike_placeholders}
                   ORDER BY titulo, id DESC""",
                (tenant_id,) + not_ilike_params,
            )
        else:
            not_ilike_no_and = " AND ".join("titulo NOT ILIKE %s" for _ in exclusoes)
            cur.execute(
                f"""SELECT DISTINCT ON (titulo) id, titulo, status, passo_atual, created_at
                   FROM cases
                   WHERE {not_ilike_no_and}
                   ORDER BY titulo, id DESC""",
                not_ilike_params,
            )
        rows = cur.fetchall()
        cur.close()
        rows.sort(key=lambda r: r[0], reverse=True)
        return [
            {
                "case_id": r[0],
                "titulo": r[1],
                "status": r[2],
                "passo_atual": r[3],
                "created_at": str(r[4]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("Erro em GET /v1/cases: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


def _validar_uuid(case_id: str) -> None:
    try:
        _uuid_mod.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Caso não encontrado.")


@router.get("/v1/cases/{case_id}")
def get_caso(case_id: str, current_user: dict = Depends(verificar_acesso_tenant)):
    """Retorna o estado completo do caso com histórico."""
    logger.info("GET /v1/cases/%s", case_id)
    _validar_uuid(case_id)
    _verificar_acesso_caso(case_id, current_user.get("sub"), current_user.get("perfil"))
    try:
        estado = _protocol_engine.get_estado(case_id)
    except ProtocolError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em GET /v1/cases/%s: %s", case_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return _case_estado_to_dict(estado)


@router.post("/v1/cases/{case_id}/steps/{passo}", dependencies=[Depends(verificar_acesso_tenant)])
def submeter_passo(case_id: str, passo: int, req: SubmeterPassoRequest):
    """
    Submete dados de um passo e avança/retrocede o protocolo.
    No Step 5 (Decidir), executa DetectorCarimbo automaticamente se dados contiverem
    'decisao_final' e 'recomendacao'.
    """
    _validar_uuid(case_id)
    logger.info("POST /v1/cases/%s/steps/%d acao=%s", case_id, passo, req.acao)
    try:
        if req.acao == "voltar":
            step = _protocol_engine.voltar(case_id, passo)
            return {
                "case_id": case_id,
                "passo": step.passo,
                "concluido": step.concluido,
                "proximo_passo": step.proximo_passo,
                "carimbo": None,
            }

        step = _protocol_engine.avancar(case_id, passo, req.dados)

        # Detector de carimbo ativado no Step 5 — Decidir (decisao_final vs recomendacao no mesmo passo)
        carimbo_result = None
        if passo == 5:
            texto_decisao = req.dados.get("decisao_final", "")
            # recomendacao e decisao_final estão ambos no Step 5 (Decidir)
            texto_recomendacao = req.dados.get("recomendacao", "")

            if texto_decisao and texto_recomendacao:
                try:
                    cr = _carimbo_detector.verificar(
                        case_id=case_id,
                        passo=passo,
                        texto_decisao=texto_decisao,
                        texto_recomendacao=texto_recomendacao,
                    )
                    carimbo_result = {
                        "score_similaridade": cr.score_similaridade,
                        "alerta": cr.alerta,
                        "mensagem": cr.mensagem,
                        "alert_id": cr.alert_id,
                    }
                except Exception as e:
                    logger.warning("Carimbo Voyage falhou, usando fallback léxico: %s", e)
                    try:
                        _cr_lite = _detectar_carimbo_lexico(texto_decisao, texto_recomendacao)
                        carimbo_result = {
                            "score_similaridade": _cr_lite["similaridade"],
                            "alerta": _cr_lite["carimbo_detectado"],
                            "mensagem": _cr_lite["mensagem"] or None,
                            "alert_id": None,
                        }
                    except Exception as e2:
                        logger.warning("Carimbo fallback léxico também falhou: %s", e2)

        return {
            "case_id": case_id,
            "passo": step.passo,
            "concluido": step.concluido,
            "proximo_passo": step.proximo_passo,
            "carimbo": carimbo_result,
        }

    except ProtocolError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Erro em POST /v1/cases/%s/steps/%d: %s", case_id, passo, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


@router.post("/v1/cases/{case_id}/carimbo/confirmar", dependencies=[Depends(verificar_acesso_tenant)])
def confirmar_carimbo(case_id: str, req: ConfirmarCarimboRequest):
    """Confirma alerta de carimbo com justificativa do gestor (mín. 20 chars)."""
    _validar_uuid(case_id)
    logger.info("POST /v1/cases/%s/carimbo/confirmar alert_id=%d", case_id, req.alert_id)
    try:
        _carimbo_detector.confirmar(req.alert_id, req.justificativa)
    except CarimboConfirmacaoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em confirmar_carimbo: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {"confirmado": True, "alert_id": req.alert_id}


@router.get("/v1/cases/{case_id}/outputs")
def listar_outputs_caso(case_id: str, current_user: dict = Depends(verificar_acesso_tenant)):
    """Lista todos os outputs de um caso, ordenados por materialidade DESC."""
    _validar_uuid(case_id)
    logger.info("GET /v1/cases/%s/outputs", case_id)
    _verificar_acesso_caso(case_id, current_user.get("sub"), current_user.get("perfil"))
    try:
        outputs = _output_engine.listar_por_caso(case_id)
    except Exception as e:
        logger.error("Erro em GET /v1/cases/%s/outputs: %s", case_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return [_output_result_to_dict(r) for r in outputs]
