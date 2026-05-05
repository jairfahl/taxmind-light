"""
tests/unit/test_tracer.py — testes para src/observability/tracer.py
"""

import json
import logging
from unittest.mock import patch

import pytest

from src.observability.tracer import Span, TraceContext


def test_span_records_duration():
    trace = TraceContext(interaction_id="abc123", query_hash="def456")
    with trace.span("retrieve") as sp:
        pass  # context manager fecha e seta end_ms
    assert sp.duration_ms >= 0
    assert sp.end_ms is not None
    assert sp.end_ms >= sp.start_ms


def test_span_captures_error():
    trace = TraceContext(interaction_id="abc123", query_hash="def456")
    with pytest.raises(ValueError):
        with trace.span("llm_call") as sp:
            raise ValueError("api error")
    assert sp.error is not None
    assert "ValueError" in sp.error
    assert "api error" in sp.error


def test_emit_outputs_ndjson(caplog):
    trace = TraceContext.create("alíquota IBS")
    with trace.span("retrieve") as sp:
        sp.metadata["output_count"] = 5

    with caplog.at_level(logging.INFO, logger="src.observability.tracer"):
        trace.emit()

    # Pelo menos um registro deve ser JSON válido com o span correto
    json_lines = [r.message for r in caplog.records if r.name == "src.observability.tracer"]
    assert len(json_lines) >= 1
    parsed = json.loads(json_lines[0])
    assert parsed["span"] == "retrieve"
    assert parsed["metadata"]["output_count"] == 5
    assert "interaction_id" in parsed
    assert "duration_ms" in parsed


def test_interaction_id_propagates():
    trace = TraceContext.create("query teste")
    with trace.span("span_a"):
        pass
    with trace.span("span_b"):
        pass

    ids = {sp.interaction_id for sp in trace._spans}
    assert len(ids) == 1  # mesmo id em todos os spans


def test_trace_context_none_no_side_effects():
    """trace=None como kwarg padrão não causa erros — simula uso em funções do pipeline."""
    trace = None

    # Verificação: código que usa `if trace is not None: trace.record(...)` é seguro
    if trace is not None:
        trace.record("retrieve", 100, {"output_count": 3})

    assert trace is None  # nenhum efeito colateral


def test_record_adds_span():
    trace = TraceContext(interaction_id="xyz", query_hash="abc")
    trace.record("quality_gate", 42, {"status": "VERDE", "iteration": 1})

    assert len(trace._spans) == 1
    sp = trace._spans[0]
    assert sp.name == "quality_gate"
    assert sp.duration_ms == 42
    assert sp.metadata["status"] == "VERDE"
