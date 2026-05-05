"""
src/billing/token_budget.py — limite de consumo de tokens por tenant por dia.

O limite primário é por custo estimado (USD/dia). Tokens são secundários.
Fail-open: se a query ao DB falhar, a análise prossegue (log warning).

Planos e limites diários:
  trial:        $1.00 / 500K input / 100K output
  starter:      $5.00 / 2M input / 500K output
  professional: $25.00 / 10M input / 2M output
  enterprise:   ilimitado
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Limites por plano
# ---------------------------------------------------------------------------

PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    "trial": {
        "daily_cost_usd": 1.00,
        "daily_input_tokens": 500_000,
        "daily_output_tokens": 100_000,
    },
    "starter": {
        "daily_cost_usd": 5.00,
        "daily_input_tokens": 2_000_000,
        "daily_output_tokens": 500_000,
    },
    "professional": {
        "daily_cost_usd": 25.00,
        "daily_input_tokens": 10_000_000,
        "daily_output_tokens": 2_000_000,
    },
    "enterprise": {
        "daily_cost_usd": None,   # None = ilimitado
        "daily_input_tokens": None,
        "daily_output_tokens": None,
    },
}

_UNLIMITED = {"daily_cost_usd": None, "daily_input_tokens": None, "daily_output_tokens": None}


# ---------------------------------------------------------------------------
# Exceção
# ---------------------------------------------------------------------------

class TokenBudgetExceeded(Exception):
    """Levantada quando tenant atinge o limite diário de tokens."""

    def __init__(self, tenant_id: str, usage: Dict[str, Any], limit: float, plan: str) -> None:
        self.tenant_id = tenant_id
        self.usage = usage
        self.limit = limit
        self.plan = plan
        super().__init__(
            f"Daily token budget exceeded: tenant={tenant_id} plan={plan} "
            f"cost={usage.get('estimated_cost', 0):.4f} limit={limit}"
        )


# ---------------------------------------------------------------------------
# Consulta de uso diário
# ---------------------------------------------------------------------------

def obter_uso_diario_tenant(tenant_id: str, conn) -> Dict[str, Any]:
    """
    Retorna consumo agregado do tenant no dia corrente (UTC).

    Returns:
        {"input_tokens": int, "output_tokens": int, "estimated_cost": float}
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0)  AS total_input,
                COALESCE(SUM(output_tokens), 0) AS total_output,
                COALESCE(SUM(estimated_cost), 0) AS total_cost
            FROM api_usage
            WHERE tenant_id = %s
              AND created_at >= CURRENT_DATE
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
    if row:
        return {
            "input_tokens": int(row[0]),
            "output_tokens": int(row[1]),
            "estimated_cost": float(row[2]),
        }
    return {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0}


# ---------------------------------------------------------------------------
# Verificação de budget
# ---------------------------------------------------------------------------

def verificar_budget_tenant(
    tenant_id: Optional[str],
    plano: Optional[str],
    conn,
) -> bool:
    """
    Verifica se o tenant ainda está dentro do budget diário.

    Fail-open: se a query ao DB falhar, retorna True (análise prossegue).

    Returns:
        True se dentro do limite, False se excedido.

    Raises:
        TokenBudgetExceeded: quando o limite é atingido (não quando há erro de DB).
    """
    if not tenant_id:
        return True  # sem tenant, sem limite

    _plano = (plano or "trial").lower()
    limits = PLAN_LIMITS.get(_plano, PLAN_LIMITS["trial"])

    # Enterprise: sem limite
    if limits.get("daily_cost_usd") is None:
        return True

    try:
        uso = obter_uso_diario_tenant(tenant_id, conn)
    except Exception as exc:
        logger.warning(
            "Token budget: falha ao consultar uso do tenant %s — fail-open: %s",
            tenant_id, exc,
        )
        return True  # fail-open

    limite_custo = limits["daily_cost_usd"]
    if uso["estimated_cost"] >= limite_custo:
        raise TokenBudgetExceeded(
            tenant_id=tenant_id,
            usage=uso,
            limit=limite_custo,
            plan=_plano,
        )

    return True
