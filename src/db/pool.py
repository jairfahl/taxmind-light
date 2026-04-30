"""
db/pool.py — ThreadedConnectionPool centralizado para toda a aplicação.

Elimina conexões avulsas (psycopg2.connect()) espalhadas pelo código.
Toda conexão é devolvida ao pool mesmo em caso de erro, evitando vazamento.
"""

import logging
import os

import psycopg2
from psycopg2 import pool as _pg_pool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_pool: _pg_pool.ThreadedConnectionPool | None = None


def _ensure_pool() -> _pg_pool.ThreadedConnectionPool:
    """Inicializa o pool na primeira chamada (lazy init)."""
    global _pool
    if _pool is None or _pool.closed:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise EnvironmentError("DATABASE_URL não definida")
        _pool = _pg_pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=url,
        )
        logger.info("Connection pool criado (min=2, max=20)")
    return _pool


def get_conn() -> psycopg2.extensions.connection:
    """Obtém uma conexão do pool. DEVE ser devolvida com put_conn()."""
    p = _ensure_pool()
    conn = p.getconn()
    return conn


def put_conn(conn: psycopg2.extensions.connection) -> None:
    """Devolve conexão ao pool. Se a conexão estiver em erro, faz rollback antes."""
    if conn is None:
        return
    try:
        if conn.closed:
            return
        # Rollback de transação pendente para limpar estado
        if conn.status != psycopg2.extensions.STATUS_READY:
            conn.rollback()
    except Exception:
        pass
    try:
        p = _ensure_pool()
        p.putconn(conn)
    except Exception as e:
        logger.warning("Erro ao devolver conexão ao pool: %s", e)
        try:
            conn.close()
        except Exception:
            pass


def set_tenant_id(conn: psycopg2.extensions.connection, tenant_id: str | None) -> None:
    """
    Define app.tenant_id na sessão PostgreSQL para enforçar RLS (migration 133).

    Chamar ANTES de executar queries em contexto autenticado.
    Chamar com tenant_id=None (ou '') para limpar ao devolver ao pool.

    Uso:
        conn = get_conn()
        set_tenant_id(conn, payload["tenant_id"])
        try:
            ...queries...
        finally:
            set_tenant_id(conn, None)
            put_conn(conn)
    """
    value = str(tenant_id) if tenant_id else ""
    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.tenant_id = %s", (value,))


def close_pool() -> None:
    """Fecha todas as conexões do pool (usar no shutdown da app)."""
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.closeall()
        logger.info("Connection pool fechado")
    _pool = None
