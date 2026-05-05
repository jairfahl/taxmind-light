"""
tests/unit/test_query_cache.py — testes para src/resilience/cache.py
"""

import time
from unittest.mock import patch

import pytest

from src.resilience.cache import CacheConfig, QueryCache, make_cache_key


def _make_cache(**kwargs) -> QueryCache:
    return QueryCache(CacheConfig(**kwargs))


# ---------------------------------------------------------------------------
# Comportamento básico
# ---------------------------------------------------------------------------

def test_cache_hit_returns_stored_value():
    cache = _make_cache()
    cache.put("key1", {"resposta": "ok"})
    result = cache.get("key1")
    assert result == {"resposta": "ok"}


def test_cache_miss_returns_none():
    cache = _make_cache()
    assert cache.get("inexistente") is None


# ---------------------------------------------------------------------------
# TTL
# ---------------------------------------------------------------------------

def test_ttl_expiration():
    cache = _make_cache(ttl_s=0.05)  # 50ms TTL
    cache.put("key1", "valor")
    time.sleep(0.1)
    assert cache.get("key1") is None  # expirado


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------

def test_lru_eviction_at_max_entries():
    cache = _make_cache(max_entries=3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    # "a" é o mais antigo (LRU)
    cache.put("d", 4)  # deve evictar "a"
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("d") == 4


# ---------------------------------------------------------------------------
# Invalidação
# ---------------------------------------------------------------------------

def test_invalidate_all_clears_store():
    cache = _make_cache()
    cache.put("x", 1)
    cache.put("y", 2)
    cache.invalidate_all()
    assert cache.get("x") is None
    assert cache.get("y") is None
    assert cache.stats["size"] == 0


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------

def test_cache_key_deterministic():
    key1 = make_cache_key("alíquota IBS", ["LC214_2025"], "claude-haiku", "v1")
    key2 = make_cache_key("alíquota IBS", ["LC214_2025"], "claude-haiku", "v1")
    assert key1 == key2
    assert len(key1) == 32


def test_cache_key_different_for_different_filters():
    key_a = make_cache_key("query", ["LC214_2025"], "model", "v1")
    key_b = make_cache_key("query", ["EC132_2023"], "model", "v1")
    assert key_a != key_b


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_stats_track_hits_and_misses():
    cache = _make_cache()
    cache.put("k", "v")
    cache.get("k")       # hit
    cache.get("k")       # hit
    cache.get("miss1")   # miss

    stats = cache.stats
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hit_rate_pct"] == pytest.approx(66.7, abs=0.1)


# ---------------------------------------------------------------------------
# Disabled cache
# ---------------------------------------------------------------------------

def test_cache_disabled_always_miss():
    cache = _make_cache(enabled=False)
    cache.put("k", "v")
    result = cache.get("k")
    assert result is None
    assert cache.stats["misses"] == 1
