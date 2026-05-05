"""
src/api/auth_api.py — Dependencies de autenticação da FastAPI.

verificar_token_api       : aceita X-API-Key (server-to-server) OU JWT válido (browser)
verificar_sessao          : valida session_id do JWT (garante sessão única)
verificar_usuario_autenticado : JWT válido; retorna payload JWT
verificar_admin           : JWT com perfil ADMIN
verificar_acesso_tenant   : JWT + billing do tenant
                            — retorna 402 se trial expirado ou assinatura cancelada/inadimplente.
                            — ADMIN bypassa a verificação de billing.

NOTA DE SEGURANÇA (SEC-08 revisado 2026-05):
X-API-Key era exposta via NEXT_PUBLIC_API_INTERNAL_KEY no bundle JS do browser.
Solução: todas as dependências aceitam X-API-Key OU JWT válido.
- Requests do browser: enviam apenas JWT (X-Api-Key removida do frontend)
- Requests server-to-server (webhooks, scripts): enviam X-Api-Key
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


def _extrair_payload_jwt(authorization: Optional[str]) -> dict:
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


def _jwt_valido(authorization: Optional[str]) -> bool:
    """Retorna True se Authorization contém um JWT decodificável e não expirado."""
    if not authorization or not authorization.startswith("Bearer "):
        return False
    token = authorization.split(" ", 1)[1]
    return decodificar_token(token) is not None


def verificar_token_api(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """
    FastAPI dependency: aceita X-API-Key (server-to-server) OU JWT válido (browser).

    - X-API-Key presente: validado via comparação constant-time.
    - JWT presente (sem X-API-Key): aceito se decodificável e não expirado.
    - Nenhum dos dois: 401.
    """
    if x_api_key:
        _validar_api_key(x_api_key)
        return
    if _jwt_valido(authorization):
        return
    raise HTTPException(status_code=401, detail="Não autorizado.")


def verificar_usuario_autenticado(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> dict:
    """
    FastAPI dependency: valida JWT válido; retorna payload JWT.

    X-API-Key é opcional — validada se presente (server-to-server).
    JWT é obrigatório para identificar o usuário.
    """
    if x_api_key:
        _validar_api_key(x_api_key)
    return _extrair_payload_jwt(authorization)


def verificar_admin(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> dict:
    """
    FastAPI dependency: valida JWT com perfil ADMIN.

    X-API-Key é opcional — validada se presente.
    Levanta 403 se o usuário não for ADMIN.
    Usado em todos os endpoints /v1/admin/* e DELETE /v1/ingest/normas/.
    """
    if x_api_key:
        _validar_api_key(x_api_key)
    payload = _extrair_payload_jwt(authorization)
    if payload.get("perfil") != "ADMIN":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
    return payload


def verificar_acesso_tenant(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> dict:
    """
    FastAPI dependency: valida JWT + billing do tenant.

    Levanta 402 se o trial expirou ou a assinatura está cancelada/inadimplente.
    ADMIN bypassa a verificação de billing.
    X-API-Key é opcional — validada se presente (server-to-server).
    """
    from src.billing.access import tenant_tem_acesso

    if x_api_key:
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
    x_api_key: Optional[str] = Header(None),
):
    """
    FastAPI dependency: valida session_id do JWT.

    Usado em /v1/auth/me para garantir sessão única por usuário.
    Se um segundo login ocorrer, o session_id do banco muda e o JWT antigo
    retorna 401 com detail='session_expired' na próxima chamada a este endpoint.

    X-API-Key é opcional — validada se presente (server-to-server).
    Tolerância de transição: JWTs emitidos antes de 2026-05-01 sem session_id
    ainda são aceitos. JWTs mais novos sem session_id → 401.
    """
    if x_api_key:
        _validar_api_key(x_api_key)

    # Se não há JWT, tolerar (best-effort — verificar_token_api já validou)
    if not authorization or not authorization.startswith("Bearer "):
        return

    # Decodificar JWT
    token = authorization.split(" ", 1)[1]
    payload = decodificar_token(token)
    if not payload or not payload.get("session_id"):
        # Tolerância: aceitar apenas JWTs emitidos antes do deadline
        iat = payload.get("iat", 0) if payload else 0
        issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
        if issued_at > _SESSION_ID_REQUIRED_AFTER:
            raise HTTPException(status_code=401, detail="Sessão inválida. Faça login novamente.")
        return  # JWT antigo sem session_id — tolerar

    # Comparar session_id do JWT com o session_id atual no banco
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
