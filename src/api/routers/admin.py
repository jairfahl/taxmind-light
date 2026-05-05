"""
src/api/routers/admin.py — Endpoints administrativos.

GET   /v1/admin/metricas
PATCH /v1/admin/tenants/{tenant_id}/desconto
GET   /v1/admin/users
POST  /v1/admin/users
PATCH /v1/admin/users/{user_id}
POST  /v1/admin/users/{user_id}/reset-senha
GET   /v1/admin/mailing
GET   /v1/admin/mailing/export
GET   /v1/admin/consumo
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.api.auth_api import verificar_admin
from src.db.pool import get_conn, put_conn

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Shared validator ---

def _validar_senha_forte(v: str) -> str:
    """Valida força de senha: mín 8 chars, maiúscula, minúscula, dígito e especial."""
    erros = []
    if len(v) < 8:
        erros.append("mínimo de 8 caracteres")
    if not re.search(r"[A-Z]", v):
        erros.append("ao menos uma letra maiúscula")
    if not re.search(r"[a-z]", v):
        erros.append("ao menos uma letra minúscula")
    if not re.search(r"\d", v):
        erros.append("ao menos um número")
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", v):
        erros.append("ao menos um caractere especial (!@#$%...)")
    if erros:
        raise ValueError("Senha fraca. Requisitos: " + "; ".join(erros) + ".")
    return v


# --- Schemas ---

class DescontoRequest(BaseModel):
    desconto_percentual: float = Field(..., ge=0, le=100)


class AdminCreateUserRequest(BaseModel):
    nome:      str = Field(..., min_length=2, max_length=100)
    email:     str = Field(..., description="E-mail do usuário")
    senha:     str = Field(..., min_length=8, max_length=128)
    perfil:    str = Field("USER", description="ADMIN ou USER")
    tenant_id: Optional[str] = Field(None, description="UUID do tenant; None cria tenant próprio")

    @field_validator("senha")
    @classmethod
    def senha_forte(cls, v: str) -> str:
        return _validar_senha_forte(v)

    @field_validator("perfil")
    @classmethod
    def validar_perfil(cls, v: str) -> str:
        if v not in ("ADMIN", "USER"):
            raise ValueError("perfil deve ser ADMIN ou USER.")
        return v

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, v: str) -> str:
        return v.lower().strip()


class AdminUpdateUserRequest(BaseModel):
    nome:   Optional[str]  = Field(None, min_length=2, max_length=100)
    perfil: Optional[str]  = Field(None)
    ativo:  Optional[bool] = Field(None)

    @field_validator("perfil")
    @classmethod
    def validar_perfil(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("ADMIN", "USER"):
            raise ValueError("perfil deve ser ADMIN ou USER.")
        return v


class AdminResetSenhaRequest(BaseModel):
    nova_senha: str = Field(..., min_length=8, max_length=128)

    @field_validator("nova_senha")
    @classmethod
    def nova_senha_forte(cls, v: str) -> str:
        return _validar_senha_forte(v)


# --- Endpoints ---

@router.get("/v1/admin/metricas", dependencies=[Depends(verificar_admin)])
def admin_metricas():
    """Resumo agregado para o painel admin."""
    logger.info("GET /v1/admin/metricas")
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM users)                                    AS total_usuarios,
                (SELECT COUNT(*) FROM ai_interactions)                          AS total_analises,
                (SELECT COUNT(*) FROM outputs WHERE classe = 'dossie_decisao')  AS total_dossies,
                (SELECT COUNT(DISTINCT user_id) FROM mau_records
                  WHERE active_month = DATE_TRUNC('month', CURRENT_DATE)::date)  AS mau_atual
        """)
        row = cur.fetchone()
        cur.close()
        return {
            "total_usuarios": row[0] or 0,
            "total_analises": row[1] or 0,
            "total_dossies":  row[2] or 0,
            "mau_atual":      row[3] or 0,
        }
    except Exception as e:
        logger.error("Erro em /v1/admin/metricas: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.patch("/v1/admin/tenants/{tenant_id}/desconto", dependencies=[Depends(verificar_admin)])
def admin_set_desconto(tenant_id: str, req: DescontoRequest):
    """Define desconto percentual para o tenant (0–100%). Admin only."""
    logger.info("PATCH /v1/admin/tenants/%s/desconto pct=%.1f", tenant_id, req.desconto_percentual)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE tenants SET desconto_percentual = %s WHERE id = %s RETURNING id",
            (req.desconto_percentual, tenant_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Tenant não encontrado.")
        conn.commit()
        cur.close()
        return {"ok": True, "desconto_percentual": req.desconto_percentual}
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/admin/tenants/desconto: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno.")
    finally:
        if conn:
            put_conn(conn)


@router.get("/v1/admin/users", dependencies=[Depends(verificar_admin)])
def admin_list_users(
    perfil: Optional[str] = Query(None, description="Filtrar por perfil (ADMIN/USER)"),
    ativo:  Optional[bool] = Query(None, description="Filtrar por status ativo"),
):
    """Lista todos os usuários com filtros opcionais."""
    logger.info("GET /v1/admin/users perfil=%s ativo=%s", perfil, ativo)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        conditions = []
        params = []
        if perfil is not None:
            conditions.append("u.perfil = %s")
            params.append(perfil.upper())
        if ativo is not None:
            conditions.append("u.ativo = %s")
            params.append(ativo)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cur.execute(f"""
            SELECT u.id, u.email, u.nome, u.perfil, u.ativo,
                   u.criado_em, u.primeiro_uso, u.email_verificado,
                   t.razao_social, t.subscription_status, t.trial_ends_at
            FROM users u
            LEFT JOIN tenants t ON t.id = u.tenant_id
            {where}
            ORDER BY u.criado_em DESC
        """, params)

        rows = cur.fetchall()
        cur.close()

        agora = datetime.now(timezone.utc)
        users = []
        for r in rows:
            trial_ends = r[10]
            sub_status = r[9]
            if sub_status == "trial" and trial_ends is not None:
                te = trial_ends if trial_ends.tzinfo else trial_ends.replace(tzinfo=timezone.utc)
                if agora > te:
                    sub_status = "trial_expired"
            users.append({
                "id":                 str(r[0]),
                "email":              r[1],
                "nome":               r[2],
                "perfil":             r[3],
                "ativo":              r[4],
                "criado_em":          r[5].isoformat() if r[5] else None,
                "primeiro_uso":       r[6].isoformat() if r[6] else None,
                "email_verificado":   r[7],
                "empresa":            r[8],
                "subscription_status": sub_status,
                "trial_ends_at":      trial_ends.isoformat() if trial_ends else None,
            })
        return {"users": users, "total": len(users)}

    except Exception as e:
        logger.error("Erro em /v1/admin/users GET: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.post("/v1/admin/users", dependencies=[Depends(verificar_admin)])
def admin_create_user(req: AdminCreateUserRequest):
    """Cria usuário diretamente pelo admin (sem validação de domínio, sem e-mail de verificação)."""
    import uuid
    from auth import gerar_hash_senha

    logger.info("POST /v1/admin/users email=%s", req.email)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (req.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

        user_id    = str(uuid.uuid4())
        senha_hash = gerar_hash_senha(req.senha)
        tenant_id  = req.tenant_id

        if tenant_id is None:
            tenant_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO tenants (id, cnpj_raiz, razao_social, status, plano,
                                     trial_starts_at, trial_ends_at, subscription_status)
                VALUES (%s, %s, %s, 'active', 'starter',
                        NOW(), NOW() + INTERVAL '5 days', 'trial')
            """, (tenant_id, str(uuid.uuid4().hex[:8]), req.nome))

        cur.execute("""
            INSERT INTO users (id, email, nome, senha_hash, perfil, ativo, tenant_id,
                               email_verificado, lgpd_consent)
            VALUES (%s, %s, %s, %s, %s, TRUE, %s, TRUE, FALSE)
        """, (user_id, req.email, req.nome, senha_hash, req.perfil, tenant_id))

        conn.commit()
        cur.close()

        return {"id": user_id, "email": req.email, "nome": req.nome, "perfil": req.perfil}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/admin/users POST: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.patch("/v1/admin/users/{user_id}", dependencies=[Depends(verificar_admin)])
def admin_update_user(user_id: str, req: AdminUpdateUserRequest):
    """Atualiza nome, perfil ou status ativo de um usuário."""
    logger.info("PATCH /v1/admin/users/%s", user_id)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE id = %s LIMIT 1", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        fields, params = [], []
        if req.nome is not None:
            fields.append("nome = %s")
            params.append(req.nome)
        if req.perfil is not None:
            fields.append("perfil = %s")
            params.append(req.perfil)
        if req.ativo is not None:
            fields.append("ativo = %s")
            params.append(req.ativo)

        if not fields:
            raise HTTPException(status_code=422, detail="Nenhum campo para atualizar.")

        params.append(user_id)
        cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", params)
        conn.commit()
        cur.close()
        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/admin/users PATCH: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.post("/v1/admin/users/{user_id}/reset-senha", dependencies=[Depends(verificar_admin)])
def admin_reset_senha(user_id: str, req: AdminResetSenhaRequest):
    """Redefine a senha de um usuário."""
    from auth import gerar_hash_senha

    logger.info("POST /v1/admin/users/%s/reset-senha", user_id)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE id = %s LIMIT 1", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        novo_hash = gerar_hash_senha(req.nova_senha)
        cur.execute("UPDATE users SET senha_hash = %s WHERE id = %s", (novo_hash, user_id))
        conn.commit()
        cur.close()
        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/admin/users reset-senha: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.get("/v1/admin/mailing", dependencies=[Depends(verificar_admin)])
def admin_mailing(
    status: Optional[str] = Query(None, description="Filtrar: trial_ativo, trial_expirado, convertido, cancelado"),
):
    """
    Lista todos os usuários com lgpd_consent=true para uso como mailing.
    Inclui status do trial para identificar não-convertidos.
    """
    logger.info("GET /v1/admin/mailing status=%s", status)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        status_filter = ""
        params: list = []

        if status == "trial_ativo":
            status_filter = "AND t.subscription_status = 'trial' AND t.trial_ends_at >= NOW()"
        elif status == "trial_expirado":
            status_filter = "AND t.subscription_status = 'trial' AND t.trial_ends_at < NOW()"
        elif status == "convertido":
            status_filter = "AND t.subscription_status = 'active'"
        elif status == "cancelado":
            status_filter = "AND t.subscription_status IN ('canceled', 'past_due')"

        cur.execute(f"""
            SELECT u.id, u.email, u.nome, u.criado_em,
                   t.razao_social, t.subscription_status, t.trial_ends_at, t.trial_starts_at,
                   t.id AS tenant_id, COALESCE(t.desconto_percentual, 0) AS desconto_percentual
            FROM users u
            JOIN tenants t ON t.id = u.tenant_id
            WHERE u.marketing_consent = TRUE
            {status_filter}
            ORDER BY u.criado_em DESC
        """, params)

        rows = cur.fetchall()
        cur.close()

        records = []
        for r in rows:
            trial_ends = r[6]
            trial_expired = trial_ends is not None and trial_ends < datetime.now(trial_ends.tzinfo)
            records.append({
                "id":                   str(r[0]),
                "email":                r[1],
                "nome":                 r[2],
                "criado_em":            r[3].isoformat() if r[3] else None,
                "empresa":              r[4],
                "subscription_status":  r[5],
                "trial_ends_at":        trial_ends.isoformat() if trial_ends else None,
                "trial_expirado":       trial_expired,
                "tenant_id":            str(r[8]) if r[8] else None,
                "desconto_percentual":  float(r[9]) if r[9] is not None else 0.0,
            })
        return {"records": records, "total": len(records)}

    except Exception as e:
        logger.error("Erro em /v1/admin/mailing: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.get("/v1/admin/mailing/export", dependencies=[Depends(verificar_admin)])
def admin_mailing_export():
    """Exporta lista de mailing em CSV (lgpd_consent=true)."""
    import csv
    import io

    logger.info("GET /v1/admin/mailing/export")
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.nome, u.email, t.razao_social,
                   u.criado_em, t.trial_ends_at, t.subscription_status
            FROM users u
            JOIN tenants t ON t.id = u.tenant_id
            WHERE u.marketing_consent = TRUE
            ORDER BY u.criado_em DESC
        """)
        rows = cur.fetchall()
        cur.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["nome", "email", "empresa", "cadastrado_em", "trial_expira_em", "status"])
        for r in rows:
            writer.writerow([
                r[0], r[1], r[2],
                r[3].isoformat() if r[3] else "",
                r[4].isoformat() if r[4] else "",
                r[5] or "",
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=mailing_tribus.csv"},
        )

    except Exception as e:
        logger.error("Erro em /v1/admin/mailing/export: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.get("/v1/admin/consumo", dependencies=[Depends(verificar_admin)])
def admin_consumo(
    dias: int = Query(30, ge=1, le=365, description="Período em dias"),
):
    """Dashboard de consumo de API: resumo, por dia, por tenant, por serviço."""
    logger.info("GET /v1/admin/consumo dias=%d", dias)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            """SELECT COALESCE(SUM(estimated_cost), 0),
                      COUNT(*),
                      MIN(created_at)::date,
                      MAX(created_at)::date
               FROM api_usage
               WHERE created_at >= NOW() - INTERVAL '%s days'""",
            (dias,),
        )
        row = cur.fetchone()
        resumo = {
            "total_gasto": round(float(row[0]), 4),
            "total_chamadas": int(row[1]),
            "periodo_inicio": row[2].isoformat() if row[2] else None,
            "periodo_fim": row[3].isoformat() if row[3] else None,
        }

        cur.execute(
            """SELECT created_at::date AS dia,
                      COALESCE(SUM(estimated_cost), 0) AS custo,
                      COUNT(*) AS chamadas
               FROM api_usage
               WHERE created_at >= NOW() - INTERVAL '%s days'
               GROUP BY dia
               ORDER BY dia DESC""",
            (dias,),
        )
        por_dia = [
            {"dia": r[0].isoformat(), "custo": round(float(r[1]), 4), "chamadas": int(r[2])}
            for r in cur.fetchall()
        ]

        cur.execute(
            """SELECT a.tenant_id,
                      COALESCE(t.razao_social, 'Sistema (sem tenant)') AS razao_social,
                      COALESCE(SUM(a.estimated_cost), 0) AS custo,
                      COUNT(*) AS chamadas
               FROM api_usage a
               LEFT JOIN tenants t ON t.id = a.tenant_id
               WHERE a.created_at >= NOW() - INTERVAL '%s days'
               GROUP BY a.tenant_id, t.razao_social
               ORDER BY custo DESC""",
            (dias,),
        )
        por_tenant = [
            {
                "tenant_id": str(r[0]) if r[0] else None,
                "razao_social": r[1],
                "custo": round(float(r[2]), 4),
                "chamadas": int(r[3]),
            }
            for r in cur.fetchall()
        ]

        cur.execute(
            """SELECT service, model,
                      COALESCE(SUM(estimated_cost), 0) AS custo,
                      COUNT(*) AS chamadas
               FROM api_usage
               WHERE created_at >= NOW() - INTERVAL '%s days'
               GROUP BY service, model
               ORDER BY custo DESC""",
            (dias,),
        )
        por_servico = [
            {"service": r[0], "model": r[1], "custo": round(float(r[2]), 4), "chamadas": int(r[3])}
            for r in cur.fetchall()
        ]

        cur.close()
        return {
            "resumo": resumo,
            "por_dia": por_dia,
            "por_tenant": por_tenant,
            "por_servico": por_servico,
        }

    except Exception as e:
        logger.error("Erro em /v1/admin/consumo: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)
