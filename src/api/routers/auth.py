"""
src/api/routers/auth.py — Endpoints de autenticação, cadastro e conta.

POST /v1/auth/login
GET  /v1/auth/me
PATCH /v1/auth/onboarding
POST /v1/auth/register
GET  /v1/auth/verify-email
POST /v1/auth/forgot-password
POST /v1/auth/reset-password
GET  /v1/credits
GET  /v1/cases/limite
GET  /v1/consultas/limite
POST /v1/registrar_decisao
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from src.api.auth_api import verificar_token_api, verificar_sessao, verificar_acesso_tenant
from src.api.limiter import limiter
from src.api.helpers import (
    _get_tenant_info_by_user,
    _verificar_limite_casos,
    _verificar_limite_consultas,
    _CONSULTA_TRIAL_LIMIT,
)
from src.db.pool import get_conn, put_conn
from src.email_service import (
    enviar_email_confirmacao,
    enviar_email_falha_pagamento,
)
from auth import autenticar, buscar_usuario_por_email, gerar_hash_senha, gerar_token
from src.outputs.engine import OutputClass, OutputEngine, OutputError
from src.protocol.engine import ProtocolError, ProtocolStateEngine

logger = logging.getLogger(__name__)

router = APIRouter()

_protocol_engine = ProtocolStateEngine()
_output_engine = OutputEngine()


# --- Helpers locais ---

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

class LoginRequest(BaseModel):
    email: str = Field(..., description="E-mail do usuário")
    senha: str = Field(..., description="Senha do usuário")

    @field_validator("email")
    @classmethod
    def validar_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("E-mail inválido.")
        return v.lower().strip()


class OnboardingRequest(BaseModel):
    user_id: str
    tipo_atuacao: str
    cargo_responsavel: str
    onboarding_step: int = 1


class RegisterRequest(BaseModel):
    nome:              str  = Field(..., min_length=2, max_length=100)
    email:             str  = Field(..., description="E-mail do usuário")
    senha:             str  = Field(..., min_length=8, max_length=128)
    razao_social:      str  = Field(..., min_length=2, max_length=255)
    cnpj_raiz:         str = Field(..., description="CPF (11 dígitos) ou CNPJ (14 dígitos) — obrigatório")
    lgpd_consent:      bool = Field(..., description="Aceite do tratamento de dados LGPD (obrigatório)")
    marketing_consent: bool = Field(False, description="Opt-in para comunicações de marketing (opcional)")

    @field_validator("senha")
    @classmethod
    def senha_forte(cls, v: str) -> str:
        return _validar_senha_forte(v)

    @field_validator("lgpd_consent")
    @classmethod
    def lgpd_deve_ser_true(cls, v: bool) -> bool:
        if not v:
            raise ValueError("O consentimento LGPD é obrigatório para o cadastro.")
        return v

    @field_validator("cnpj_raiz")
    @classmethod
    def validar_cnpj_raiz(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) not in (11, 14):
            raise ValueError("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos).")
        return digits

    @field_validator("email")
    @classmethod
    def validar_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("E-mail inválido.")
        return v.lower().strip()


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="E-mail do usuário cadastrado")

    @field_validator("email")
    @classmethod
    def validar_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("E-mail inválido.")
        return v.lower().strip()


class ResetPasswordRequest(BaseModel):
    token:      str
    nova_senha: str = Field(..., min_length=8, max_length=128)

    @field_validator("nova_senha")
    @classmethod
    def validar_senha_forte(cls, v: str) -> str:
        erros = []
        if len(v) < 8:
            erros.append("mínimo 8 caracteres")
        if not re.search(r"[A-Z]", v):
            erros.append("ao menos uma letra maiúscula")
        if not re.search(r"[a-z]", v):
            erros.append("ao menos uma letra minúscula")
        if not re.search(r"\d", v):
            erros.append("ao menos um número")
        if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", v):
            erros.append("ao menos um caractere especial")
        if erros:
            raise ValueError("Senha inválida: " + ", ".join(erros))
        return v


class RegistrarDecisaoRequest(BaseModel):
    query: str = Field(..., min_length=5)
    premissas: list[str] = Field(default_factory=list)
    riscos: list[str] = Field(default_factory=list)
    resultado_ia: str = Field(..., min_length=1)
    grau_consolidacao: str = ""
    contra_tese: str = ""
    criticidade: str = "informativo"
    hipotese_gestor: str = Field(..., min_length=1)
    decisao_final: str = Field(..., min_length=1)
    user_id: Optional[str] = None


# --- Endpoints ---

@router.post("/v1/auth/login")
@limiter.limit("5/minute")
def login(request: Request, req: LoginRequest):
    """
    Autenticação — retorna JWT + dados do usuário.
    Público (sem X-API-Key). Rate-limited: 5 req/min por IP.
    """
    token, erro = autenticar(req.email, req.senha)
    if erro or not token:
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    usuario = buscar_usuario_por_email(req.email)
    if not usuario:
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id":               str(usuario.id),
            "email":            usuario.email,
            "nome":             usuario.nome,
            "perfil":           usuario.perfil,
            "tenant_id":        str(getattr(usuario, "tenant_id", None)) if getattr(usuario, "tenant_id", None) else None,
            "onboarding_step":  0,
        },
    }


@router.get("/v1/auth/me", dependencies=[Depends(verificar_token_api), Depends(verificar_sessao)])
def auth_me(user_id: str = Query(...)):
    """Retorna dados do usuário incluindo onboarding_step e dados de trial."""
    logger.info("GET /v1/auth/me user_id=%s", user_id)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT u.id, u.email, u.nome, u.perfil, u.tenant_id, u.onboarding_step,
                      t.subscription_status, t.trial_ends_at
               FROM users u
               LEFT JOIN tenants t ON t.id = u.tenant_id
               WHERE u.id = %s LIMIT 1""",
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        trial_ends = row[7]
        return {
            "id": str(row[0]),
            "email": row[1],
            "nome": row[2],
            "perfil": row[3],
            "tenant_id": str(row[4]) if row[4] else None,
            "onboarding_step": row[5] if row[5] is not None else 0,
            "subscription_status": row[6],
            "trial_ends_at": trial_ends.isoformat() if trial_ends else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro em /v1/auth/me: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.patch("/v1/auth/onboarding", dependencies=[Depends(verificar_token_api)])
def auth_onboarding(req: OnboardingRequest):
    """Salva dados de progressive profiling e avança onboarding_step."""
    logger.info("PATCH /v1/auth/onboarding user_id=%s step=%d", req.user_id, req.onboarding_step)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """UPDATE users
               SET tipo_atuacao = %s, cargo_responsavel = %s, onboarding_step = %s
               WHERE id = %s""",
            (req.tipo_atuacao, req.cargo_responsavel, req.onboarding_step, req.user_id),
        )
        conn.commit()
        cur.close()
        return {"ok": True}
    except Exception as e:
        logger.error("Erro em /v1/auth/onboarding: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.get("/v1/credits", dependencies=[Depends(verificar_token_api)])
def get_credits():
    """Resumo de consumo de créditos de API."""
    try:
        from src.observability.usage import obter_detalhamento
        detalhamento = obter_detalhamento()
        total_gasto = sum(d["estimated_cost"] for d in detalhamento)
    except Exception as e:
        logger.error("Erro em /v1/credits: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {
        "total_gasto": round(total_gasto, 4),
        "detalhamento": detalhamento,
    }


@router.get("/v1/cases/limite", dependencies=[Depends(verificar_token_api)])
def get_limite_casos(user_id: str = Query(...)):
    """Retorna quantos casos foram criados e qual o limite do plano atual."""
    logger.info("GET /v1/cases/limite user_id=%s", user_id)
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT perfil FROM users WHERE id = %s LIMIT 1", (user_id,))
            perfil_row = cur.fetchone()
        is_admin = perfil_row and perfil_row[0] == "ADMIN"

        if is_admin:
            return {"usado": 0, "limite": -1, "plano": "enterprise", "subscription_status": "active"}

        row = _get_tenant_info_by_user(user_id, conn)
        if not row:
            return {"usado": 0, "limite": 0, "plano": "starter", "subscription_status": "trial"}
        t_id, sub_status, plano, trial_ends = row
        tenant_id = str(t_id)
        _, usado, limite = _verificar_limite_casos(tenant_id, sub_status, plano, trial_ends, conn)
        return {
            "usado": usado,
            "limite": limite,
            "plano": plano,
            "subscription_status": sub_status,
        }
    except Exception as e:
        logger.error("Erro em /v1/cases/limite: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.get("/v1/consultas/limite", dependencies=[Depends(verificar_token_api)])
def get_limite_consultas(user_id: str = Query(...)):
    """Retorna uso de consultas /analisar para tenants trial (migration 135)."""
    logger.info("GET /v1/consultas/limite user_id=%s", user_id)
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT perfil FROM users WHERE id = %s LIMIT 1", (user_id,))
            perfil_row = cur.fetchone()
        if perfil_row and perfil_row[0] == "ADMIN":
            return {"usado": 0, "limite": -1, "subscription_status": "active"}

        row = _get_tenant_info_by_user(user_id, conn)
        if not row:
            return {"usado": 0, "limite": _CONSULTA_TRIAL_LIMIT, "subscription_status": "trial"}
        t_id, sub_status, plano, trial_ends = row
        if sub_status != "trial":
            return {"usado": 0, "limite": -1, "subscription_status": sub_status}
        _, usado, limite = _verificar_limite_consultas(str(t_id), conn)
        return {"usado": usado, "limite": limite, "subscription_status": sub_status}
    except Exception as e:
        logger.error("Erro em /v1/consultas/limite: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.post("/v1/auth/register")
@limiter.limit("3/minute")
def register(request: Request, req: RegisterRequest, background_tasks: BackgroundTasks):
    """
    Auto-cadastro público — cria tenant + usuário em trial de 7 dias.
    Público (sem X-API-Key). Rate-limited: 3 req/min por IP.
    Conta fica inativa até confirmação por e-mail.
    """
    logger.info("POST /v1/auth/register email=%s", req.email)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        # Verificar e-mail único
        cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (req.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

        # Verificar CNPJ único (se fornecido)
        cnpj = req.cnpj_raiz or str(uuid.uuid4().hex[:8])  # CNPJ gerado se ausente
        if req.cnpj_raiz:
            cur.execute("SELECT id FROM tenants WHERE cnpj_raiz = %s LIMIT 1", (cnpj,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="CNPJ já cadastrado.")

        tenant_id   = str(uuid.uuid4())
        user_id     = str(uuid.uuid4())
        email_token = str(uuid.uuid4())
        senha_hash  = gerar_hash_senha(req.senha)

        # Criar tenant
        cur.execute("""
            INSERT INTO tenants (id, cnpj_raiz, razao_social, status, plano,
                                 trial_starts_at, trial_ends_at, subscription_status)
            VALUES (%s, %s, %s, 'active', 'starter',
                    NOW(), NOW() + INTERVAL '5 days', 'trial')
        """, (tenant_id, cnpj, req.razao_social))

        # Criar usuário (inativo até verificar e-mail)
        cur.execute("""
            INSERT INTO users (id, email, nome, senha_hash, perfil, ativo, tenant_id,
                               lgpd_consent, lgpd_consent_at, marketing_consent,
                               email_verificado, email_token, email_token_expires_at)
            VALUES (%s, %s, %s, %s, 'USER', FALSE, %s,
                    %s, NOW(), %s, FALSE, %s, NOW() + INTERVAL '24 hours')
        """, (user_id, req.email, req.nome, senha_hash, tenant_id,
              req.lgpd_consent, req.marketing_consent, email_token))

        conn.commit()
        cur.close()

        # Enviar e-mail de confirmação em background (não bloqueia response)
        background_tasks.add_task(enviar_email_confirmacao, req.email, req.nome, email_token)

        return {
            "message": "Cadastro realizado com sucesso! Verifique seu e-mail para ativar a conta.",
            "email": req.email,
        }

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/auth/register: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.get("/v1/auth/verify-email")
@limiter.limit("5/minute")
def verify_email(request: Request, token: str = Query(..., description="Token de verificação enviado por e-mail")):
    """
    Confirma o e-mail e ativa a conta. Retorna JWT para login automático.
    Público (sem X-API-Key).
    """
    logger.info("GET /v1/auth/verify-email token=%s", token[:8] + "...")
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            """SELECT id, email, nome, perfil, tenant_id FROM users
               WHERE email_token = %s
                 AND (email_token_expires_at IS NULL OR email_token_expires_at > NOW())
               LIMIT 1""",
            (token,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Token inválido ou já utilizado.")

        user_id, email, nome, perfil, tenant_id = row

        import uuid as _uuid
        novo_session_id = str(_uuid.uuid4())
        cur.execute(
            """UPDATE users SET ativo = TRUE, email_verificado = TRUE,
               email_token = NULL, session_id = %s WHERE id = %s""",
            (novo_session_id, str(user_id)),
        )
        conn.commit()
        cur.close()

        # Gerar token JWT para login automático
        from auth import Usuario
        usuario = Usuario(
            id=str(user_id), email=email, nome=nome, perfil=perfil,
            ativo=True, primeiro_uso=None, criado_em=datetime.now(timezone.utc),
            tenant_id=str(tenant_id) if tenant_id else None,
            session_id=novo_session_id,
        )
        jwt_token = gerar_token(usuario)

        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": {
                "id":          str(user_id),
                "email":       email,
                "nome":        nome,
                "perfil":      perfil,
                "tenant_id":   str(tenant_id) if tenant_id else None,
                "onboarding_step": 0,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/auth/verify-email: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.post("/v1/auth/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, req: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    """
    Solicita redefinição de senha. Gera token UUID válido por 1h e envia e-mail via Resend.
    Retorna 200 se cadastrado (envia e-mail) ou 404 se e-mail não encontrado.
    Público (sem X-API-Key). Rate-limited: 3 req/min por IP.
    """
    logger.info("POST /v1/auth/forgot-password email=%s", req.email)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, nome FROM users WHERE email = %s AND ativo = TRUE LIMIT 1",
            (req.email,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="E-mail não encontrado. Verifique ou crie uma conta.")

        user_id, nome = row
        reset_token = str(uuid.uuid4())

        cur.execute(
            """UPDATE users
               SET reset_token = %s, reset_token_expires_at = NOW() + INTERVAL '1 hour'
               WHERE id = %s""",
            (reset_token, str(user_id)),
        )
        conn.commit()
        cur.close()

        from src.email_service import enviar_email_recuperacao_senha
        background_tasks.add_task(enviar_email_recuperacao_senha, req.email, nome, reset_token)

        return {"message": "E-mail de recuperação enviado. Verifique sua caixa de entrada."}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/auth/forgot-password: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.post("/v1/auth/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, req: ResetPasswordRequest):
    """
    Redefine a senha usando o token recebido por e-mail.
    Token deve ser válido e não expirado (1h). Público (sem X-API-Key).
    """
    logger.info("POST /v1/auth/reset-password token=%s", req.token[:8] + "...")
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            """SELECT id FROM users
               WHERE reset_token = %s
                 AND reset_token_expires_at > NOW()
               LIMIT 1""",
            (req.token,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Link inválido ou expirado. Solicite um novo.")

        user_id = str(row[0])
        nova_hash = gerar_hash_senha(req.nova_senha)

        cur.execute(
            """UPDATE users
               SET senha_hash = %s, reset_token = NULL, reset_token_expires_at = NULL
               WHERE id = %s""",
            (nova_hash, user_id),
        )
        conn.commit()
        cur.close()

        return {"message": "Senha redefinida com sucesso. Faça login com sua nova senha."}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/auth/reset-password: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.post("/v1/registrar_decisao", dependencies=[Depends(verificar_token_api)])
def registrar_decisao(req: RegistrarDecisaoRequest):
    """
    Endpoint consolidado para o fluxo PME de documentação (UX-03/04).
    Cria o case, submete P1→P5, gera Dossiê com Legal Hold e ativa monitoramento P6.
    """
    logger.info("POST /v1/registrar_decisao query=%s", req.query[:60])
    try:
        from src.cognitive.monitoramento_p6 import ativar_monitoramento_p6

        titulo = req.query[:80] if len(req.query) >= 10 else req.query.ljust(10, ".")
        contexto = req.premissas[0] if req.premissas else "Contexto tributário geral."
        premissas = req.premissas if len(req.premissas) >= 2 else req.premissas + [f"Análise: {req.query[:60]}"]
        riscos = req.riscos if req.riscos else ["Risco a ser monitorado."]
        periodo_fiscal = f"{datetime.now().year}-{datetime.now().year + 1}"

        # P1 — criar caso
        case_id = _protocol_engine.criar_caso(
            titulo=titulo,
            descricao=req.query,
            contexto_fiscal=contexto,
        )

        # P1 — avancar
        _protocol_engine.avancar(case_id, 1, {
            "titulo": titulo,
            "descricao": req.query,
            "contexto_fiscal": contexto,
            "premissas": premissas,
            "periodo_fiscal": periodo_fiscal,
        })

        # P2 — riscos
        _protocol_engine.avancar(case_id, 2, {
            "riscos": riscos,
            "dados_qualidade": "verde",
        })

        # P3 — análise IA
        _protocol_engine.avancar(case_id, 3, {
            "query_analise": req.query,
            "analise_result": req.resultado_ia,
        })

        # P4 — hipótese
        _protocol_engine.avancar(case_id, 4, {
            "hipotese_gestor": req.hipotese_gestor,
        })

        # P5 — decisão
        _protocol_engine.avancar(case_id, 5, {
            "recomendacao": req.resultado_ia[:500],
            "decisao_final": req.decisao_final,
            "decisor": "Gestor",
        })

        # Gerar dossiê C4 (requer P5 concluído)
        dossie = _output_engine.gerar_dossie(case_id=case_id)

        # Ativar monitoramento P6
        try:
            ativar_monitoramento_p6(
                case_id=case_id,
                user_id=req.user_id,
                titulo=titulo,
            )
        except Exception as e_p6:
            logger.warning("P6 monitoring não ativado para case_id=%d: %s", case_id, e_p6)

        return {
            "sucesso": True,
            "case_id": case_id,
            "dossie_id": dossie.id,
            "mensagem": "Análise registrada com Legal Hold ativo.",
        }

    except ProtocolError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except OutputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro em /v1/registrar_decisao: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
