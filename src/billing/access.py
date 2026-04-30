"""
Controle de acesso por status de subscription do tenant.
"""

from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


def tenant_tem_acesso(tenant: dict) -> tuple[bool, str]:
    """
    Verifica se o tenant tem acesso à plataforma.

    Args:
        tenant: dict com campos trial_ends_at e subscription_status

    Returns:
        (True, "") se tem acesso
        (False, motivo) se não tem acesso
    """
    status = tenant.get("subscription_status", "trial")
    trial_ends_at = tenant.get("trial_ends_at")

    if status == "active":
        return True, ""

    if status == "trial":
        if trial_ends_at is None:
            return True, ""  # trial sem data = acesso liberado (bypass)
        agora = datetime.now(timezone.utc)
        if isinstance(trial_ends_at, str):
            trial_ends_at = datetime.fromisoformat(trial_ends_at)
        if agora <= trial_ends_at:
            return True, ""
        return False, "trial_expired"

    if status == "past_due":
        return False, "payment_failed"

    if status == "canceled":
        return False, "canceled"

    return False, "unknown_status"


def dias_restantes_trial(tenant: dict) -> int | None:
    """
    Retorna dias restantes do trial (5 dias), ou None se não aplicável.
    """
    if tenant.get("subscription_status") != "trial":
        return None
    trial_ends_at = tenant.get("trial_ends_at")
    if not trial_ends_at:
        return None
    agora = datetime.now(timezone.utc)
    if isinstance(trial_ends_at, str):
        trial_ends_at = datetime.fromisoformat(trial_ends_at)
    delta = (trial_ends_at - agora).days
    return max(0, delta)
