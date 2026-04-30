"""
src/api/auth_api.py — Dependencies de autenticação da FastAPI.

verificar_token_api       : valida X-API-Key interno (todos os endpoints protegidos)
verificar_sessao          : valida X-API-Key + session_id do JWT (usado em /v1/auth/me)
                            — garante sessão única: novo login invalida sessão anterior.
verificar_usuario_autenticado : valida X-API-Key + JWT válido; retorna payload JWT
verificar_admin           : valida X-API-Key + JWT com perfil ADMIN (endpoints admin)
verificar_acesso_tenant   : valida X-API-Key + JWT + billing do tenant (endpoints de negócio)
                            — retorna 402 se trial expirado ou assinatura cancelada/inadimplente.
                            — ADMIN bypassa a verificação de billing.
"""

import hmac
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import Header, HTTPException

from auth import decodificar_token
from src.db.pool import get_conn, put_conn

# Deadline: JWTs emitidos após esta data DEVEM ter session_id.
# JWTs mais antigos ainda são tolerados para não forçar logout geral.
_SESSION_ID_REQUIRED_AFTER = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _validar_api_key(x_api_key: str) -> None:
    """Valida X-API-Key via comparação constant-time (evita timing attack)."""
    api_key = os.getenv("API_INTERNAL_KEY")
    if not api_key:
        raise RuntimeError("API_INTERNAL_KEY não configurada no ambiente.")
    if not hmac.compare_digest(x_api_key, api_key):
        raise HTTPException(status_code=401, detail="Não autorizado.")


def _extrair_payload_jwt(authorization: str) -> dict:
    """
    Extrai e valida o payload do JWT no header Authorization.

    Raises HTTPException 401 se ausente, malformado ou expirado.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autenticação ausente.")
    token = authorization.split(" ", 1)[1]
    payload = decodificar_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")
    return payload


def verificar_token_api(x_api_key: str = Header(...)):
    """
    FastAPI dependency: valida o header X-API-Key.

    Levanta 401 se a chave estiver ausente ou incorreta.
    Levanta RuntimeError (500) se API_INTERNAL_KEY não estiver configurada no ambiente.
    """
    _validar_api_key(x_api_key)


def verificar_usuario_autenticado(
    authorization: str = Header(...),
    x_api_key: str = Header(...),
) -> dict:
    """
    FastAPI dependency: valida X-API-Key + JWT válido.

    Retorna o payload JWT (inclui sub, email, perfil, session_id).
    Usado em endpoints que precisam identificar o usuário/tenant chamador.
    """
    _validar_api_key(x_api_key)
    return _extrair_payload_jwt(authorization)


def verificar_admin(
    authorization: str = Header(...),
    x_api_key: str = Header(...),
) -> dict:
    """
    FastAPI dependency: valida X-API-Key + JWT com perfil ADMIN.

    Retorna o payload JWT se válido e perfil == 'ADMIN'.
    Levanta 403 se o usuário não for ADMIN.
    Usado em todos os endpoints /v1/admin/* e DELETE /v1/ingest/normas/.
    """
    _validar_api_key(x_api_key)
    payload = _extrair_payload_jwt(authorization)
    if payload.get("perfil") != "ADMIN":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
    return payload


def verificar_acesso_tenant(
    authorization: str = Header(...),
    x_api_key: str = Header(...),
) -> dict:
    """
    FastAPI dependency: valida X-API-Key + JWT + billing do tenant.

    Levanta 402 se o trial expirou ou a assinatura está cancelada/inadimplente.
    ADMIN bypassa a verificação de billing.
    Usado em todos os endpoints de negócio (analyze, cases, outputs).
    """
    from src.billing.access import tenant_tem_acesso

    _validar_api_key(x_api_key)
    payload = _extrair_payload_jwt(authorization)

    if payload.get("perfil") == "ADMIN":
        return payload

    user_id = payload.get("sub")
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT t.subscription_status, t.trial_ends_at
                   FROM users u JOIN tenants t ON t.id = u.tenant_id
                   WHERE u.id = %s LIMIT 1""",
                (user_id,),
            )
            row = cur.fetchone()
    finally:
        if conn:
            put_conn(conn)

    if row is None:
        return payload  # tenant ainda não associado (onboarding incompleto) — deixar passar

    tenant = {
        "subscription_status": row[0],
        "trial_ends_at": row[1].isoformat() if row[1] else None,
    }
    tem_acesso, motivo = tenant_tem_acesso(tenant)
    if not tem_acesso:
        raise HTTPException(status_code=402, detail=motivo)

    return payload


def verificar_sessao(
    authorization: Optional[str] = Header(None),
    x_api_key: str = Header(...),
):
    """
    FastAPI dependency: valida X-API-Key + session_id do JWT.

    Usado em /v1/auth/me para garantir sessão única por usuário.
    Se um segundo login ocorrer, o session_id do banco muda e o JWT antigo
    retorna 401 com detail='session_expired' na próxima chamada a este endpoint.

    Tolerância de transição: JWTs emitidos antes de 2026-05-01 sem session_id
    ainda são aceitos. JWTs mais novos sem session_id → 401.
    """
    # 1. Validar X-API-Key (constant-time)
    _validar_api_key(x_api_key)

    # 2. Se não há JWT no header Authorization, tolerar (best-effort)
    if not authorization or not authorization.startswith("Bearer "):
        return

    # 3. Decodificar JWT
    token = authorization.split(" ", 1)[1]
    payload = decodificar_token(token)
    if not payload or not payload.get("session_id"):
        # Tolerância: aceitar apenas JWTs emitidos antes do deadline
        iat = payload.get("iat", 0) if payload else 0
        issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
        if issued_at > _SESSION_ID_REQUIRED_AFTER:
            raise HTTPException(status_code=401, detail="Sessão inválida. Faça login novamente.")
        return  # JWT antigo sem session_id — tolerar

    # 4. Comparar session_id do JWT com o session_id atual no banco
    user_id = payload.get("sub")
    jwt_session_id = payload.get("session_id")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id FROM users WHERE id = %s LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
        if row and str(row[0]) != jwt_session_id:
            raise HTTPException(status_code=401, detail="session_expired")
    finally:
        if conn:
            put_conn(conn)
