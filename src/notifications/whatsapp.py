"""
src/notifications/whatsapp.py — Envio de mensagens WhatsApp via Z-API.

Usado para notificações internas ao admin (ex: novo assinante confirmado).
Variáveis obrigatórias: ZAPI_INSTANCE_ID, ZAPI_TOKEN.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

ADMIN_WA_NUMBER = "5511972521970"


def enviar_whatsapp_admin(mensagem: str) -> None:
    """
    Envia mensagem de texto para o número fixo do admin via Z-API.
    Falha silenciosa com log de erro — nunca deve quebrar o fluxo principal.
    """
    instance_id = os.getenv("ZAPI_INSTANCE_ID", "")
    token       = os.getenv("ZAPI_TOKEN", "")

    if not all([instance_id, token]):
        logger.warning("WhatsApp admin: variáveis Z-API não configuradas — mensagem não enviada.")
        return

    url = f"https://api.z-api.io/instances/{instance_id}/token/{token}/send-text"
    payload = {
        "phone": ADMIN_WA_NUMBER,
        "message": mensagem,
    }
    headers = {"Content-Type": "application/json"}

    security_token = os.getenv("ZAPI_SECURITY_TOKEN", "")
    if security_token:
        headers["Client-Token"] = security_token

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logger.info("WhatsApp admin enviado com sucesso para %s.", ADMIN_WA_NUMBER)
    except Exception as exc:
        logger.error("Erro ao enviar WhatsApp admin: %s", exc)
