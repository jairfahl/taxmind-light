"""
src/resilience/cache.py — cache LRU + TTL para queries FACTUAL.

Evita re-executar o pipeline completo (8-12s + tokens) para queries idênticas.
Apenas queries FACTUAL sem contexto de caso ou fatos de cliente são cacheadas.

Política de invalidação:
- TTL expira após 1 hora (configurável)
- Ingestão de nova norma chama invalidate_all()
- Reinício do processo limpa automaticamente (in-memory)
- Mudança de modelo: cache miss automático (model incluso na chave)
"""

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    max_entries: int = 256
    ttl_s: float = 3600.0  # 1 hora
    enabled: bool = True


@dataclass
class _CacheEntry:
    value: Any
    stored_at: float = field(default_factory=time.time)


class QueryCache:
    """Cache LRU + TTL thread-safe para resultados de análise."""

    def __init__(self, config: Optional[CacheConfig] = None) -> None:
        self._config = config or CacheConfig()
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        if not self._config.enabled:
            self._misses += 1
            return None

        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        # Verificar TTL
        if time.time() - entry.stored_at > self._config.ttl_s:
            del self._store[key]
            self._misses += 1
            return None

        # LRU: mover para o fim (mais recentemente usado)
        self._store.move_to_end(key)
        self._hits += 1
        return entry.value

    def put(self, key: str, value: Any) -> None:
        if not self._config.enabled:
            return

        # Atualizar entrada existente
        if key in self._store:
            self._store[key] = _CacheEntry(value=value)
            self._store.move_to_end(key)
            return

        # Evictar LRU se no limite
        if len(self._store) >= self._config.max_entries:
            oldest_key, _ = next(iter(self._store.items()))
            del self._store[oldest_key]
            logger.debug("Cache LRU eviction: chave removida")

        self._store[key] = _CacheEntry(value=value)

    def invalidate_all(self) -> None:
        count = len(self._store)
        self._store.clear()
        if count:
            logger.info("Cache invalidado: %d entradas removidas", count)

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._store),
            "hit_rate_pct": round(self._hits / total * 100, 1) if total else 0.0,
        }


# Singleton de módulo
_query_cache = QueryCache()


def make_cache_key(
    query: str,
    norma_filter: Optional[list],
    model: str,
    base_version: str,
) -> str:
    """
    Chave determinística para cache de query.

    sha256(normalize(query) | sorted(norma_filter) | model | base_version)[:32]
    """
    normalized = query.strip().lower()
    filter_str = str(sorted(norma_filter)) if norma_filter else "[]"
    raw = f"{normalized}|{filter_str}|{model}|{base_version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
