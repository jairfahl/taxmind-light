"""
observability/usage.py — Rastreamento de consumo de creditos de API.

Registra tokens consumidos (LLM + embeddings) e estima custo em USD.
Emite alerta quando o saldo restante fica abaixo de US$0.50.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Precos por 1M tokens (USD) — atualizar conforme pricing vigente
PRICING: dict[str, dict[str, float]] = {
    # Anthropic — input / output por MTok
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
    # VoyageAI — preco unico por MTok (so input)
    "voyage-3":                  {"input": 0.06, "output": 0.00},
}

# Limite de creditos configuravel via .env
CREDIT_LIMIT_USD = float(os.getenv("API_CREDIT_LIMIT_USD", "10.00"))
ALERT_THRESHOLD_USD = 0.50


@dataclass
class CreditStatus:
    total_gasto: float
    limite: float
    saldo_restante: float
    alerta: bool
    mensagem: Optional[str]


def _get_conn() -> psycopg2.extensions.connection:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL nao definida")
    return psycopg2.connect(url)


def estimar_custo(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    """Estima custo em USD para uma chamada de API."""
    pricing = PRICING.get(model)
    if not pricing:
        # Modelo desconhecido — usar pricing mais caro como fallback seguro
        logger.warning("Pricing desconhecido para modelo '%s', usando fallback conservador", model)
        pricing = {"input": 3.00, "output": 15.00}

    custo = (input_tokens / 1_000_000) * pricing["input"]
    custo += (output_tokens / 1_000_000) * pricing["output"]
    return custo


def registrar_uso(
    service: str,
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
) -> None:
    """Registra consumo de tokens no banco."""
    custo = estimar_custo(model, input_tokens, output_tokens)
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO api_usage (service, model, input_tokens, output_tokens, estimated_cost)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (service, model, input_tokens, output_tokens, custo),
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.debug(
            "Uso registrado: %s/%s input=%d output=%d custo=$%.6f",
            service, model, input_tokens, output_tokens, custo,
        )
    except Exception as e:
        logger.warning("Falha ao registrar uso de API: %s", e)


def obter_status_creditos() -> CreditStatus:
    """Retorna status atual de creditos com alerta se saldo <= $0.50."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(estimated_cost), 0) FROM api_usage")
        total_gasto = float(cur.fetchone()[0])
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning("Falha ao consultar uso de API: %s", e)
        return CreditStatus(
            total_gasto=0,
            limite=CREDIT_LIMIT_USD,
            saldo_restante=CREDIT_LIMIT_USD,
            alerta=False,
            mensagem=None,
        )

    saldo = CREDIT_LIMIT_USD - total_gasto
    alerta = saldo <= ALERT_THRESHOLD_USD

    mensagem = None
    if saldo <= 0:
        mensagem = (
            f"Creditos esgotados! Consumo total: US$ {total_gasto:.2f} "
            f"(limite: US$ {CREDIT_LIMIT_USD:.2f}). "
            "Recarregue seus creditos para continuar usando o sistema."
        )
    elif alerta:
        mensagem = (
            f"Atencao: restam apenas US$ {saldo:.2f} em creditos de API. "
            f"Consumo ate agora: US$ {total_gasto:.2f} de US$ {CREDIT_LIMIT_USD:.2f}."
        )

    return CreditStatus(
        total_gasto=round(total_gasto, 4),
        limite=CREDIT_LIMIT_USD,
        saldo_restante=round(max(0, saldo), 4),
        alerta=alerta,
        mensagem=mensagem,
    )


def obter_detalhamento() -> list[dict]:
    """Retorna consumo agregado por servico/modelo."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT service, model,
                   SUM(input_tokens) AS total_input,
                   SUM(output_tokens) AS total_output,
                   SUM(estimated_cost) AS total_cost,
                   COUNT(*) AS chamadas
            FROM api_usage
            GROUP BY service, model
            ORDER BY total_cost DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "service": r[0],
                "model": r[1],
                "input_tokens": int(r[2]),
                "output_tokens": int(r[3]),
                "estimated_cost": float(r[4]),
                "chamadas": int(r[5]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("Falha ao consultar detalhamento: %s", e)
        return []
