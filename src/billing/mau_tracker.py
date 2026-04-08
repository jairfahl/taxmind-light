"""
src/billing/mau_tracker.py — MAU Tracker por análise (DEC-08, ESP-15, G26).

Definição DC v7: usuário ativo = gerou ao menos uma análise no mês.
Login passivo não conta. Alinha billing com valor entregue.

Diferença do mau.py (login-based):
  mau.py        → conta login (ON CONFLICT DO NOTHING — 1 registro por mês)
  mau_tracker.py → conta análises (ON CONFLICT DO UPDATE — acumula eventos)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from src.db.pool import get_conn, put_conn

logger = logging.getLogger(__name__)

_BYPASS_UUID = "00000000-0000-0000-0000-000000000000"


def _primeiro_dia_mes(referencia: Optional[date] = None) -> date:
    """Retorna o primeiro dia do mês da data de referência (default: hoje)."""
    d = referencia or date.today()
    return d.replace(day=1)


def _obter_tenant_id(conn, user_id: str) -> Optional[str]:
    """Busca o tenant_id do usuário. Retorna None se não encontrado."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id FROM users WHERE id = %s AND tenant_id IS NOT NULL",
                (user_id,),
            )
            row = cur.fetchone()
            return str(row[0]) if row else None
    except Exception as e:
        logger.debug("MAU: falha ao buscar tenant_id para user %s: %s", user_id, e)
        return None


def registrar_evento_mau(user_id: Optional[str]) -> bool:
    """
    Registra um evento de ativação MAU para o usuário no mês atual.

    - BYPASS user (000...000) ou None: ignorado silenciosamente
    - Usuário sem tenant_id: ignorado (tenant isolation requerido)
    - Primeiro evento do mês: INSERT novo registro
    - Eventos subsequentes: DO UPDATE — incrementa total_eventos

    Returns:
        True se registrado com sucesso, False caso contrário.
    """
    if not user_id or user_id == _BYPASS_UUID:
        return False

    active_month = _primeiro_dia_mes()

    conn = get_conn()
    try:
        tenant_id = _obter_tenant_id(conn, user_id)
        if not tenant_id:
            logger.debug("MAU: user %s sem tenant_id — não registrado", user_id)
            return False

        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mau_records
                        (user_id, tenant_id, active_month, recorded_at,
                         total_eventos, ultimo_evento)
                    VALUES (%s, %s, %s, NOW(), 1, NOW())
                    ON CONFLICT (user_id, tenant_id, active_month)
                    DO UPDATE SET
                        total_eventos = mau_records.total_eventos + 1,
                        ultimo_evento = NOW()
                    """,
                    (user_id, tenant_id, active_month),
                )
        logger.debug("MAU registrado: user=%s tenant=%s month=%s", user_id, tenant_id, active_month)
        return True
    except Exception as e:
        logger.warning("MAU: erro ao registrar evento para user %s: %s", user_id, e)
        return False
    finally:
        put_conn(conn)


def obter_mau_mes(mes: Optional[date] = None) -> int:
    """Retorna o total de MAU (usuários únicos) para o mês especificado."""
    active_month = _primeiro_dia_mes(mes)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT user_id) FROM mau_records WHERE active_month = %s",
                (active_month,),
            )
            row = cur.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.warning("MAU: erro ao consultar mau_mes: %s", e)
        return 0
    finally:
        put_conn(conn)


def obter_serie_mau(meses: int = 6) -> list[dict]:
    """
    Série histórica de MAU dos últimos N meses.
    Retorna lista de dicts: {active_month, mau, eventos}.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    active_month,
                    COUNT(DISTINCT user_id) AS mau,
                    COALESCE(SUM(total_eventos), 0) AS eventos
                FROM mau_records
                WHERE active_month >= DATE_TRUNC(
                    'month', NOW() - (%s || ' months')::INTERVAL
                )::DATE
                GROUP BY active_month
                ORDER BY active_month DESC
                """,
                (str(meses),),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.warning("MAU: erro ao obter série: %s", e)
        return []
    finally:
        put_conn(conn)


def obter_detalhamento_usuarios(mes: Optional[date] = None) -> list[dict]:
    """
    Detalhamento de usuários ativos no mês — usado no painel admin.
    """
    active_month = _primeiro_dia_mes(mes)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.nome,
                    u.email,
                    u.perfil,
                    m.total_eventos,
                    m.recorded_at  AS primeiro_evento,
                    m.ultimo_evento
                FROM mau_records m
                JOIN users u ON m.user_id = u.id
                WHERE m.active_month = %s
                ORDER BY m.total_eventos DESC
                """,
                (active_month,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.warning("MAU: erro ao obter detalhamento: %s", e)
        return []
    finally:
        put_conn(conn)
