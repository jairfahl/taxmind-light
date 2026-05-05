"""
src/api/routers/billing.py — Endpoints de billing e assinatura.

GET  /v1/billing/mau
GET  /v1/webhooks/asaas  (ping)
POST /v1/webhooks/asaas
POST /v1/billing/subscribe
POST /v1/billing/cancel
"""

import hmac
import logging
import os
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.auth_api import verificar_token_api
from src.db.pool import get_conn, put_conn
from src.email_service import enviar_email_falha_pagamento

logger = logging.getLogger(__name__)

router = APIRouter()

ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN", "")

_ASAAS_STATUS_MAP = {
    "PAYMENT_RECEIVED":         "active",
    "PAYMENT_CONFIRMED":        "active",
    "SUBSCRIPTION_RENEWED":     "active",
    "PAYMENT_OVERDUE":          "past_due",
    "PAYMENT_DELETED":          "past_due",
    "SUBSCRIPTION_INACTIVATED": "canceled",
    "SUBSCRIPTION_DELETED":     "canceled",
}


# --- Schemas ---

class SubscribeRequest(BaseModel):
    tenant_id:    str
    billing_type: str = Field("CREDIT_CARD", pattern="^(CREDIT_CARD|PIX)$")
    cpf_cnpj:     Optional[str] = None


class CancelRequest(BaseModel):
    tenant_id: str
    motivo: Optional[str] = None


# --- Helpers ---

def _notificar_falha_pagamento(tenant_id: str, conn) -> None:
    """Busca o e-mail do admin do tenant e envia notificação de falha de pagamento."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.email, u.nome FROM users u WHERE u.tenant_id = %s AND u.perfil = 'ADMIN' LIMIT 1",
                (tenant_id,),
            )
            row = cur.fetchone()
        if row:
            enviar_email_falha_pagamento(row[0], row[1])
    except Exception as exc:
        logger.error("Erro ao notificar falha de pagamento para tenant %s: %s", tenant_id, exc)


def _notificar_novo_assinante_wa(razao_social: str, tenant_id: str, valor) -> None:
    """Envia WA ao admin quando um novo tenant confirma pagamento pela primeira vez."""
    from src.notifications.whatsapp import enviar_whatsapp_admin
    try:
        mensagem = (
            f"🎉 *Novo assinante Orbis!*\n\n"
            f"Empresa: {razao_social}\n"
            f"Tenant: {tenant_id}\n"
            f"Valor confirmado: R$ {valor}"
        )
        enviar_whatsapp_admin(mensagem)
    except Exception as exc:
        logger.error("Erro ao notificar novo assinante via WA: %s", exc)


# --- Endpoints ---

@router.get("/v1/billing/mau", dependencies=[Depends(verificar_token_api)])
def get_mau(
    tenant_id: str,
    month: Optional[str] = None,
):
    """
    Retorna o total de usuários ativos (MAU) de um tenant em um mês.

    Parâmetros:
        tenant_id: UUID do tenant
        month: mês no formato YYYY-MM (opcional, default: mês corrente)
    """
    logger.info("GET /v1/billing/mau tenant_id=%s month=%s", tenant_id, month)

    if month:
        try:
            year, mon = map(int, month.split("-"))
            active_month = date(year, mon, 1)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Formato de month inválido. Use YYYY-MM.")
    else:
        active_month = date.today().replace(day=1)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(DISTINCT user_id) AS active_users
                   FROM mau_records
                   WHERE tenant_id = %s AND active_month = %s""",
                (tenant_id, active_month),
            )
            row = cur.fetchone()
            active_users = row[0] if row else 0
    except Exception as e:
        logger.error("Erro em /v1/billing/mau: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao consultar MAU: {str(e)}")
    finally:
        put_conn(conn)

    return {
        "tenant_id": tenant_id,
        "month": active_month.strftime("%Y-%m"),
        "active_users": active_users,
        "active_month_start": active_month.isoformat(),
    }


@router.get("/v1/webhooks/asaas")
async def asaas_webhook_ping():
    """Validação de conectividade do Asaas (GET health check)."""
    return {"status": "ok"}


@router.post("/v1/webhooks/asaas")
async def asaas_webhook(request: Request):
    """
    Recebe eventos de billing do Asaas e atualiza subscription_status do tenant.
    Autenticação: token fixo no header asaas-access-token.
    """
    token = request.headers.get("asaas-access-token", "")
    if not ASAAS_WEBHOOK_TOKEN or not hmac.compare_digest(token, ASAAS_WEBHOOK_TOKEN):
        logger.warning("Webhook Asaas: token inválido recebido.")
        raise HTTPException(status_code=401, detail="Token inválido.")

    payload = await request.json()
    evento       = payload.get("event", "")
    payment      = payload.get("payment", {})
    external_ref = payment.get("externalReference")

    logger.info("Webhook Asaas recebido: evento=%s tenant=%s", evento, external_ref)

    novo_status = _ASAAS_STATUS_MAP.get(evento)
    if not novo_status or not external_ref:
        return {"received": True}

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT subscription_status, razao_social FROM tenants WHERE id = %s LIMIT 1",
                (external_ref,),
            )
            row_antes = cur.fetchone()
            status_anterior = row_antes[0] if row_antes else None
            razao_social    = row_antes[1] if row_antes else external_ref

            cur.execute(
                "UPDATE tenants SET subscription_status = %s, updated_at = NOW() WHERE id = %s",
                (novo_status, external_ref),
            )
        conn.commit()
        logger.info("Tenant %s → subscription_status='%s' via webhook Asaas.", external_ref, novo_status)

        if novo_status == "past_due":
            _notificar_falha_pagamento(external_ref, conn)

        if novo_status == "active" and status_anterior != "active":
            valor = payment.get("value", "?")
            _notificar_novo_assinante_wa(razao_social, external_ref, valor)

    except Exception as e:
        logger.error("Erro ao atualizar tenant via webhook: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno.")
    finally:
        put_conn(conn)

    return {"received": True}


@router.post("/v1/billing/subscribe", dependencies=[Depends(verificar_token_api)])
def billing_subscribe(req: SubscribeRequest):
    """
    Cria customer + assinatura Starter no Asaas e retorna link de pagamento.
    cpf_cnpj é obrigatório: o Asaas valida o documento e cria o customer.
    Valor base: R$ 497,00 — descontado conforme tenants.desconto_percentual.
    """
    logger.info("POST /v1/billing/subscribe tenant_id=%s billing_type=%s", req.tenant_id, req.billing_type)
    conn = None
    try:
        from src.billing.asaas import criar_customer, criar_assinatura, buscar_pagamentos_assinatura

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT razao_social, asaas_customer_id, asaas_subscription_id,
                      desconto_percentual,
                      (SELECT email FROM users WHERE tenant_id = t.id AND perfil = 'ADMIN' LIMIT 1),
                      cpf_cnpj, subscription_status
               FROM tenants t WHERE t.id = %s LIMIT 1""",
            (req.tenant_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tenant não encontrado.")

        razao_social, asaas_customer_id, asaas_subscription_id, desconto, email_admin, cpf_cnpj_db, sub_status = row

        if asaas_subscription_id and sub_status == "active":
            raise HTTPException(status_code=409, detail="Assinatura já existe para este tenant.")

        if asaas_subscription_id and sub_status != "active":
            try:
                from src.billing.asaas import cancelar_assinatura
                cancelar_assinatura(asaas_subscription_id)
            except Exception as e:
                logger.warning("Falha ao cancelar subscription pendente %s: %s", asaas_subscription_id, e)
            cur.execute(
                "UPDATE tenants SET asaas_subscription_id = NULL WHERE id = %s",
                (req.tenant_id,),
            )
            asaas_subscription_id = None

        cpf_cnpj = req.cpf_cnpj or cpf_cnpj_db or ""
        digits = "".join(c for c in cpf_cnpj if c.isdigit())
        if len(digits) not in (11, 14):
            raise HTTPException(status_code=422, detail="cpf_cnpj_required")

        if req.cpf_cnpj and req.cpf_cnpj != cpf_cnpj_db:
            cur.execute(
                "UPDATE tenants SET cpf_cnpj = %s WHERE id = %s",
                (digits, req.tenant_id),
            )

        if not asaas_customer_id:
            customer = criar_customer(req.tenant_id, razao_social, email_admin or "", digits)
            asaas_customer_id = customer["id"]
            cur.execute(
                "UPDATE tenants SET asaas_customer_id = %s WHERE id = %s",
                (asaas_customer_id, req.tenant_id),
            )

        valor_base   = 497.00
        desconto_pct = float(desconto or 0)
        valor_final  = round(valor_base * (1 - desconto_pct / 100), 2)

        desconto_promo_valor  = round(valor_final - 297.00, 2) if valor_final > 297.00 else None
        desconto_promo_ciclos = 2 if desconto_promo_valor and desconto_promo_valor > 0 else None

        assinatura = criar_assinatura(
            customer_id=asaas_customer_id,
            tenant_id=req.tenant_id,
            plano="starter",
            valor=valor_final,
            billing_type=req.billing_type,
            desconto_valor=desconto_promo_valor,
            desconto_ciclos=desconto_promo_ciclos,
        )
        asaas_subscription_id = assinatura["id"]

        cur.execute(
            "UPDATE tenants SET asaas_subscription_id = %s, plano = 'starter' WHERE id = %s",
            (asaas_subscription_id, req.tenant_id),
        )
        conn.commit()
        cur.close()

        pagamentos = buscar_pagamentos_assinatura(asaas_subscription_id)
        invoice_url = None
        if pagamentos.get("data"):
            invoice_url = pagamentos["data"][0].get("invoiceUrl")

        logger.info(
            "Assinatura criada: tenant=%s subscription=%s valor=%.2f desconto=%.1f%%",
            req.tenant_id, asaas_subscription_id, valor_final, desconto_pct,
        )
        return {
            "invoice_url":        invoice_url,
            "valor":              valor_final,
            "desconto_percentual": desconto_pct,
        }

    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        if conn:
            conn.rollback()
        logger.error("Erro Asaas em /v1/billing/subscribe (HTTP %s): %s", e.response.status_code, e.response.text)
        if e.response.status_code == 401:
            raise HTTPException(status_code=502, detail="Erro de configuração do gateway de pagamento. Entre em contato com o suporte.")
        if e.response.status_code == 400:
            body = e.response.text.lower()
            if "cpfcnpj" in body or "cpf" in body or "cnpj" in body or "document" in body:
                raise HTTPException(status_code=422, detail="cpf_cnpj_invalido")
        raise HTTPException(status_code=502, detail="O serviço de pagamento está temporariamente indisponível. Tente novamente em instantes.")
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/billing/subscribe: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao processar assinatura. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@router.post("/v1/billing/cancel", dependencies=[Depends(verificar_token_api)])
def billing_cancel(req: CancelRequest):
    """
    Cancela a assinatura do tenant no Asaas e atualiza o status interno.
    404 do Asaas (sub já cancelada) é tratado como sucesso silencioso.
    """
    from src.billing.asaas import cancelar_assinatura as _asaas_cancelar

    logger.info("POST /v1/billing/cancel tenant_id=%s", req.tenant_id)
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT asaas_subscription_id FROM tenants WHERE id = %s LIMIT 1",
                (req.tenant_id,),
            )
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Tenant não encontrado.")

        asaas_sub_id = row[0]

        if asaas_sub_id:
            try:
                _asaas_cancelar(asaas_sub_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.warning("Assinatura %s não encontrada no Asaas — prosseguindo com cancelamento local.", asaas_sub_id)
                else:
                    raise

        with conn.cursor() as cur:
            cur.execute(
                """UPDATE tenants
                   SET subscription_status = 'canceled',
                       cancel_reason = %s,
                       updated_at = NOW()
                   WHERE id = %s""",
                (req.motivo, req.tenant_id),
            )
        conn.commit()
        logger.info("Tenant %s cancelado. Motivo: %s", req.tenant_id, req.motivo)
        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/billing/cancel: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao cancelar assinatura. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)
