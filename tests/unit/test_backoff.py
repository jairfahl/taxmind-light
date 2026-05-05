"""
tests/unit/test_backoff.py — testes para src/resilience/backoff.py
"""

from unittest.mock import MagicMock, patch

import pytest

from src.resilience.backoff import BackoffConfig, _is_retryable, resilient_call

# Config sem timeout (não injeta kwarg) e sem jitter para testes determinísticos
_BASE_CFG = BackoffConfig(max_retries=3, base_delay_s=1.0, max_delay_s=60.0, jitter_s=0.0, timeout_s=None)


# ---------------------------------------------------------------------------
# _is_retryable
# ---------------------------------------------------------------------------

def test_is_retryable_timeout_error():
    assert _is_retryable(TimeoutError("t")) is True


def test_is_retryable_value_error():
    assert _is_retryable(ValueError("bad")) is False


# ---------------------------------------------------------------------------
# resilient_call — comportamento básico
# ---------------------------------------------------------------------------

def test_succeeds_first_try():
    fn = MagicMock(return_value="ok")
    result = resilient_call(fn, "arg", key="val", config=_BASE_CFG)
    assert result == "ok"
    fn.assert_called_once_with("arg", key="val")


def test_retries_on_timeout_error():
    fn = MagicMock(side_effect=[TimeoutError("first"), "recovered"])
    with patch("src.resilience.backoff.time.sleep"):
        result = resilient_call(fn, config=_BASE_CFG)
    assert result == "recovered"
    assert fn.call_count == 2


def test_exponential_delay_growth():
    fn = MagicMock(side_effect=[TimeoutError(), TimeoutError(), "ok"])
    cfg = BackoffConfig(max_retries=3, base_delay_s=2.0, max_delay_s=60.0, jitter_s=0.0, timeout_s=None)
    with patch("src.resilience.backoff.time.sleep") as mock_sleep:
        result = resilient_call(fn, config=cfg)
    assert result == "ok"
    delays = [c.args[0] for c in mock_sleep.call_args_list]
    assert delays[0] == pytest.approx(2.0)   # 2 * 2^0
    assert delays[1] == pytest.approx(4.0)   # 2 * 2^1


def test_max_retries_exceeded_raises():
    fn = MagicMock(side_effect=TimeoutError("persistent"))
    cfg = BackoffConfig(max_retries=2, base_delay_s=0.0, jitter_s=0.0, timeout_s=None)
    with patch("src.resilience.backoff.time.sleep"):
        with pytest.raises(TimeoutError):
            resilient_call(fn, config=cfg)
    assert fn.call_count == 3  # 1 inicial + 2 retries


def test_non_retryable_error_raises_immediately():
    fn = MagicMock(side_effect=ValueError("bad input"))
    with pytest.raises(ValueError):
        resilient_call(fn, config=_BASE_CFG)
    fn.assert_called_once()


def test_timeout_triggers_retry():
    fn = MagicMock(side_effect=[TimeoutError("timed out"), "ok"])
    cfg = BackoffConfig(max_retries=1, base_delay_s=0.0, jitter_s=0.0, timeout_s=None)
    with patch("src.resilience.backoff.time.sleep"):
        result = resilient_call(fn, config=cfg)
    assert result == "ok"


def test_jitter_adds_randomness():
    cfg = BackoffConfig(max_retries=3, base_delay_s=1.0, jitter_s=0.5, timeout_s=None)
    captured = []
    for _ in range(15):
        fn = MagicMock(side_effect=[TimeoutError(), "ok"])
        with patch("src.resilience.backoff.time.sleep") as mock_sleep:
            resilient_call(fn, config=cfg)
        captured.append(round(mock_sleep.call_args.args[0], 4))
    # Jitter deve produzir pelo menos 2 valores distintos em 15 tentativas
    assert len(set(captured)) > 1


def test_integration_with_trace_span():
    """kwargs extras (como trace=None) são repassados para fn, não quebram resilient_call."""
    fn = MagicMock(return_value={"result": "ok"})
    cfg = BackoffConfig(timeout_s=None)
    result = resilient_call(fn, model="test-model", trace=None, config=cfg)
    assert result == {"result": "ok"}
    fn.assert_called_once_with(model="test-model", trace=None)
