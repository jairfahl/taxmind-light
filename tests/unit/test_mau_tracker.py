"""
tests/unit/test_mau_tracker.py — Testes unitários do MAU Tracker (D4, G26).
Apenas lógica pura — sem chamadas ao banco.
"""

from datetime import date

from src.billing.mau_tracker import _primeiro_dia_mes


def test_primeiro_dia_mes_atual():
    d = _primeiro_dia_mes()
    assert d.day == 1
    assert d.month == date.today().month
    assert d.year == date.today().year


def test_primeiro_dia_mes_referencia():
    ref = date(2026, 7, 15)
    d = _primeiro_dia_mes(ref)
    assert d == date(2026, 7, 1)


def test_bypass_uuid_nao_registra():
    from src.billing.mau_tracker import registrar_evento_mau
    BYPASS = "00000000-0000-0000-0000-000000000000"
    resultado = registrar_evento_mau(BYPASS)
    assert resultado is False


def test_none_nao_registra():
    from src.billing.mau_tracker import registrar_evento_mau
    resultado = registrar_evento_mau(None)
    assert resultado is False


def test_primeiro_dia_janeiro():
    ref = date(2026, 1, 31)
    d = _primeiro_dia_mes(ref)
    assert d == date(2026, 1, 1)


def test_primeiro_dia_dezembro():
    ref = date(2025, 12, 15)
    d = _primeiro_dia_mes(ref)
    assert d == date(2025, 12, 1)


def test_vazio_nao_registra():
    from src.billing.mau_tracker import registrar_evento_mau
    resultado = registrar_evento_mau("")
    assert resultado is False
