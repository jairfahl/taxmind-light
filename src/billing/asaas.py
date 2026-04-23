"""
Cliente Asaas para billing MAU do Tribus-AI.
Documentação: https://docs.asaas.com/
"""

import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://sandbox.asaas.com/api/v3")
ASAAS_API_KEY  = os.getenv("ASAAS_API_KEY", "")


def _headers() -> dict:
    return {
        "access_token": ASAAS_API_KEY,
        "Content-Type": "application/json",
    }


def criar_customer(tenant_id: str, razao_social: str, email: str, cnpj: str) -> dict:
    """
    Cria um customer no Asaas para o tenant.
    Retorna o objeto customer com o campo 'id' (customer_id Asaas).
    """
    payload = {
        "name": razao_social,
        "email": email,
        "cpfCnpj": cnpj,
        "externalReference": tenant_id,  # nosso tenant_id como referência cruzada
        "notificationDisabled": False,
    }
    resp = httpx.post(f"{ASAAS_BASE_URL}/customers", json=payload, headers=_headers())
    resp.raise_for_status()
    return resp.json()


def criar_assinatura(
    customer_id: str,
    tenant_id: str,
    plano: str,
    valor: float,
    ciclo: str = "MONTHLY",
    billing_type: str = "CREDIT_CARD",
    desconto_valor: Optional[float] = None,
    desconto_ciclos: Optional[int] = None,
) -> dict:
    """
    Cria uma assinatura recorrente mensal no Asaas.

    Args:
        customer_id    : ID do customer no Asaas
        tenant_id      : UUID do tenant (referência externa)
        plano          : nome do plano ('starter', 'professional', 'enterprise')
        valor          : valor mensal cheio em reais (ex: 497.00)
        ciclo          : periodicidade (default MONTHLY)
        billing_type   : forma de pagamento — "CREDIT_CARD" | "PIX" | "BOLETO"
        desconto_valor : desconto fixo em reais por ciclo (ex: 200.00)
        desconto_ciclos: quantos ciclos o desconto se aplica (ex: 2)

    Retorna o objeto subscription com o campo 'id' (subscription_id Asaas).
    """
    from datetime import date
    payload = {
        "customer":          customer_id,
        "billingType":       billing_type,
        "value":             valor,
        "nextDueDate":       date.today().isoformat(),
        "cycle":             ciclo,
        "description":       f"Orbis.tax — Plano {plano.capitalize()}",
        "externalReference": tenant_id,
    }
    if desconto_valor is not None and desconto_ciclos is not None:
        payload["discount"] = {
            "value":          desconto_valor,
            "duracaoMeses":   desconto_ciclos,
            "type":           "FIXED",
        }
    resp = httpx.post(f"{ASAAS_BASE_URL}/subscriptions", json=payload, headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def buscar_pagamentos_assinatura(subscription_id: str) -> dict:
    """
    Retorna as cobranças geradas por uma assinatura.
    data[0]['invoiceUrl'] é o link de pagamento da primeira cobrança.
    """
    resp = httpx.get(
        f"{ASAAS_BASE_URL}/subscriptions/{subscription_id}/payments",
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def cancelar_assinatura(subscription_id: str) -> dict:
    """Cancela uma assinatura no Asaas."""
    resp = httpx.delete(
        f"{ASAAS_BASE_URL}/subscriptions/{subscription_id}",
        headers=_headers()
    )
    resp.raise_for_status()
    return resp.json()


def buscar_assinatura(subscription_id: str) -> dict:
    """Retorna dados de uma assinatura."""
    resp = httpx.get(
        f"{ASAAS_BASE_URL}/subscriptions/{subscription_id}",
        headers=_headers()
    )
    resp.raise_for_status()
    return resp.json()
