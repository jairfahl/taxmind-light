"""
src/resilience/backoff.py — retry com exponential backoff para chamadas externas.

Cobre Anthropic (429/500/503/529) e Voyage AI (429) com jitter e timeout configuráveis.
"""

import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class BackoffConfig:
    max_retries: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    timeout_s: Optional[float] = None  # None = não injeta timeout na chamada
    jitter_s: float = 0.5


def _is_retryable(exc: Exception) -> bool:
    """Retorna True se a exceção justifica retry (erro transitório de API)."""
    # Anthropic SDK
    try:
        import anthropic
        if isinstance(exc, (anthropic.RateLimitError, anthropic.InternalServerError)):
            return True
        if isinstance(exc, anthropic.APIStatusError) and getattr(exc, "status_code", 0) == 529:
            return True
        if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
            return True
    except ImportError:
        pass

    # Voyage AI
    try:
        import voyageai
        if isinstance(exc, voyageai.error.RateLimitError):
            return True
    except (ImportError, AttributeError):
        pass

    # Built-ins e httpx
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    try:
        import httpx
        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
            return True
    except ImportError:
        pass

    return False


def resilient_call(fn: Callable, *args: Any, config: Optional[BackoffConfig] = None, **kwargs: Any) -> Any:
    """
    Chama fn(*args, **kwargs) com retry exponencial em falhas retryable.

    Se config.timeout_s não for None e 'timeout' não estiver em kwargs,
    injeta timeout=config.timeout_s na chamada (compatível com Anthropic SDK).

    Delay por tentativa: min(base * 2^attempt, max) ± jitter
    """
    if config is None:
        config = BackoffConfig()

    call_kwargs = dict(kwargs)
    if config.timeout_s is not None and "timeout" not in call_kwargs:
        call_kwargs["timeout"] = config.timeout_s

    last_exc: Optional[Exception] = None
    for attempt in range(config.max_retries + 1):
        try:
            return fn(*args, **call_kwargs)
        except Exception as exc:
            if not _is_retryable(exc) or attempt >= config.max_retries:
                raise
            last_exc = exc
            delay = min(config.base_delay_s * (2 ** attempt), config.max_delay_s)
            jitter = random.uniform(-config.jitter_s, config.jitter_s)
            actual_delay = max(0.0, delay + jitter)
            status = getattr(exc, "status_code", type(exc).__name__)
            fn_module = getattr(fn, "__module__", None) or ""
            api_label = fn_module.split(".")[0] if fn_module else "api"
            logger.warning(
                "RETRY api=%s attempt=%d/%d status=%s delay=%.1fs err=%s",
                api_label,
                attempt + 1,
                config.max_retries,
                status,
                actual_delay,
                exc,
            )
            time.sleep(actual_delay)

    # Nunca deveria chegar aqui, mas garantimos raise
    if last_exc:
        raise last_exc
    raise RuntimeError("resilient_call: max retries exceeded")


# ---------------------------------------------------------------------------
# Configurações pré-definidas por API
# ---------------------------------------------------------------------------

ANTHROPIC_LLM_CONFIG = BackoffConfig(
    max_retries=3,
    base_delay_s=1.0,
    max_delay_s=30.0,
    timeout_s=90.0,
    jitter_s=0.5,
)

ANTHROPIC_REFLECTION_CONFIG = BackoffConfig(
    max_retries=2,
    base_delay_s=1.0,
    max_delay_s=20.0,
    timeout_s=30.0,
    jitter_s=0.5,
)

# Voyage: timeout_s=None pois o SDK não aceita timeout como kwarg
VOYAGE_QUERY_CONFIG = BackoffConfig(
    max_retries=3,
    base_delay_s=2.0,
    max_delay_s=15.0,
    timeout_s=None,
    jitter_s=0.5,
)

VOYAGE_INGEST_CONFIG = BackoffConfig(
    max_retries=3,
    base_delay_s=60.0,
    max_delay_s=180.0,
    timeout_s=None,
    jitter_s=2.0,
)

VOYAGE_CARIMBO_CONFIG = BackoffConfig(
    max_retries=3,
    base_delay_s=30.0,
    max_delay_s=60.0,
    timeout_s=None,
    jitter_s=1.0,
)
