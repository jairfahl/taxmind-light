"""
src/observability/tracer.py — tracing estruturado do pipeline RAG.

Cada request recebe um TraceContext com interaction_id único. As etapas
do pipeline registram spans via context manager trace.span(name).
Ao final, trace.emit() serializa todos os spans como NDJSON no stdout via logging.

Uso:
    trace = TraceContext.create(query)
    with trace.span("retrieve", metadata={"top_k": 5}) as sp:
        chunks = retrieve(query)
        sp.metadata["output_count"] = len(chunks)
    trace.emit()

O parâmetro trace é SEMPRE opcional (default None) — código existente não quebra.
"""

import hashlib
import json
import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Span:
    name: str
    interaction_id: str
    query_hash: str
    start_ms: float = field(default_factory=lambda: time.time() * 1000)
    end_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def duration_ms(self) -> int:
        if self.end_ms is None:
            return 0
        return int(self.end_ms - self.start_ms)

    def to_dict(self) -> dict:
        return {
            "ts": datetime.fromtimestamp(self.start_ms / 1000, tz=timezone.utc).isoformat(),
            "level": "ERROR" if self.error else "INFO",
            "interaction_id": self.interaction_id,
            "query_hash": self.query_hash,
            "span": self.name,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "error": self.error,
        }


class TraceContext:
    """Contexto de tracing para um request de análise."""

    def __init__(self, interaction_id: str, query_hash: str) -> None:
        self.interaction_id = interaction_id
        self.query_hash = query_hash
        self._spans: List[Span] = []

    @classmethod
    def create(cls, query: str) -> "TraceContext":
        interaction_id = uuid.uuid4().hex[:16]
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:12]
        return cls(interaction_id=interaction_id, query_hash=query_hash)

    @contextmanager
    def span(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Generator[Span, None, None]:
        """Context manager que registra um span com timing e captura de erro."""
        sp = Span(
            name=name,
            interaction_id=self.interaction_id,
            query_hash=self.query_hash,
            metadata=metadata or {},
        )
        self._spans.append(sp)
        try:
            yield sp
        except Exception as exc:
            sp.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            sp.end_ms = time.time() * 1000

    def record(self, name: str, duration_ms: int, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Registra um span já finalizado diretamente (útil para wrapping de blocos)."""
        sp = Span(
            name=name,
            interaction_id=self.interaction_id,
            query_hash=self.query_hash,
            metadata=metadata or {},
        )
        sp.end_ms = sp.start_ms + duration_ms
        self._spans.append(sp)

    def emit(self) -> None:
        """Emite todos os spans como linhas NDJSON via logger.info."""
        for sp in self._spans:
            logger.info(json.dumps(sp.to_dict(), ensure_ascii=False))
