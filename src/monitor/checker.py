"""
monitor/checker.py — Verifica fontes oficiais e detecta novos documentos.

Compara documentos encontrados contra a tabela monitor_documentos.
Novos documentos sao inseridos com status='novo' para revisao pelo usuario.
"""

import concurrent.futures
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import psycopg2
from dotenv import load_dotenv

from src.db.pool import get_conn, put_conn

from src.monitor.sources import CHECKERS, DocumentoDetectado

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    fonte_nome: str
    fonte_tipo: str
    novos: int
    total_encontrados: int
    erro: Optional[str]


@dataclass
class DocumentoPendente:
    id: int
    titulo: str
    url: Optional[str]
    data_publicacao: Optional[str]
    resumo: Optional[str]
    fonte_nome: str
    fonte_tipo: str
    detectado_em: str
    status: str


def _get_conn() -> psycopg2.extensions.connection:
    return get_conn()


def verificar_fonte(fonte_id: int, nome: str, url: str, tipo: str) -> CheckResult:
    """Verifica uma fonte e insere novos documentos encontrados."""
    checker = CHECKERS.get(tipo)
    if not checker:
        return CheckResult(nome, tipo, 0, 0, f"Tipo de fonte desconhecido: {tipo}")

    try:
        docs = checker(url)
    except Exception as e:
        logger.error("Erro ao verificar fonte %s: %s", nome, e)
        return CheckResult(nome, tipo, 0, 0, str(e))

    if not docs:
        # Atualizar ultimo_check mesmo sem resultados
        conn = None
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE monitor_fontes SET ultimo_check = NOW() WHERE id = %s",
                (fonte_id,),
            )
            conn.commit()
            cur.close()
        except Exception:
            pass
        finally:
            if conn:
                put_conn(conn)
        return CheckResult(nome, tipo, 0, 0, None)

    novos = 0
    conn = None
    try:
        conn = _get_conn()
        cur = conn.cursor()

        for doc in docs:
            if not doc.url:
                continue
            cur.execute(
                """
                INSERT INTO monitor_documentos
                    (fonte_id, titulo, url, data_publicacao, resumo, status)
                VALUES (%s, %s, %s, %s, %s, 'novo')
                ON CONFLICT (url) DO NOTHING
                """,
                (fonte_id, doc.titulo, doc.url, doc.data_publicacao, doc.resumo),
            )
            if cur.rowcount > 0:
                novos += 1

        cur.execute(
            "UPDATE monitor_fontes SET ultimo_check = NOW() WHERE id = %s",
            (fonte_id,),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error("Erro ao persistir documentos de %s: %s", nome, e)
        return CheckResult(nome, tipo, novos, len(docs), str(e))
    finally:
        if conn:
            put_conn(conn)

    logger.info("Fonte %s: %d novos de %d encontrados", nome, novos, len(docs))
    return CheckResult(nome, tipo, novos, len(docs), None)


def verificar_todas_fontes() -> list[CheckResult]:
    """Verifica todas as fontes ativas e retorna resultados."""
    conn = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, url, tipo_fonte FROM monitor_fontes WHERE ativo = TRUE ORDER BY id"
        )
        fontes = cur.fetchall()
        cur.close()
    except Exception as e:
        logger.error("Erro ao listar fontes: %s", e)
        return []
    finally:
        if conn:
            put_conn(conn)

    _PER_SOURCE_TIMEOUT = 30  # seconds — prevents one slow/down source from blocking the endpoint

    resultados: list[CheckResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(fontes) or 1) as executor:
        future_to_fonte = {
            executor.submit(verificar_fonte, fonte_id, nome, url, tipo): (nome, tipo)
            for fonte_id, nome, url, tipo in fontes
        }
        for future in concurrent.futures.as_completed(future_to_fonte, timeout=_PER_SOURCE_TIMEOUT * len(fontes) + 5):
            nome_f, tipo_f = future_to_fonte[future]
            try:
                resultado = future.result(timeout=_PER_SOURCE_TIMEOUT)
            except concurrent.futures.TimeoutError:
                logger.warning("Timeout ao verificar fonte %s (%s)", nome_f, tipo_f)
                resultado = CheckResult(nome_f, tipo_f, 0, 0, "Timeout ao verificar fonte")
            except Exception as e:
                logger.error("Erro ao verificar fonte %s: %s", nome_f, e)
                resultado = CheckResult(nome_f, tipo_f, 0, 0, str(e))
            resultados.append(resultado)

    total_novos = sum(r.novos for r in resultados)
    logger.info("Monitor: %d fontes verificadas, %d documentos novos", len(resultados), total_novos)
    return resultados


def listar_pendentes() -> list[DocumentoPendente]:
    """Retorna documentos com status='novo' para revisao do usuario."""
    conn = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT d.id, d.titulo, d.url, d.data_publicacao, d.resumo,
                   f.nome, f.tipo_fonte, d.detectado_em, d.status
            FROM monitor_documentos d
            JOIN monitor_fontes f ON f.id = d.fonte_id
            WHERE d.status = 'novo'
            ORDER BY d.detectado_em DESC
        """)
        rows = cur.fetchall()
        cur.close()
        return [
            DocumentoPendente(
                id=r[0], titulo=r[1], url=r[2], data_publicacao=r[3],
                resumo=r[4], fonte_nome=r[5], fonte_tipo=r[6],
                detectado_em=r[7].isoformat() if r[7] else "",
                status=r[8],
            )
            for r in rows
        ]
    except Exception as e:
        logger.error("Erro ao listar pendentes: %s", e)
        return []
    finally:
        if conn:
            put_conn(conn)


def contar_pendentes() -> int:
    """Retorna quantidade de documentos novos pendentes de revisao."""
    conn = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM monitor_documentos WHERE status = 'novo'")
        count = cur.fetchone()[0]
        cur.close()
        return count
    except Exception:
        return 0
    finally:
        if conn:
            put_conn(conn)


def atualizar_status(doc_id: int, novo_status: str) -> bool:
    """Atualiza status de um documento (novo → ingerido | descartado)."""
    if novo_status not in ("ingerido", "descartado"):
        return False
    conn = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE monitor_documentos SET status = %s, atualizado_em = NOW() WHERE id = %s",
            (novo_status, doc_id),
        )
        conn.commit()
        ok = cur.rowcount > 0
        cur.close()
        return ok
    except Exception as e:
        logger.error("Erro ao atualizar status do doc %d: %s", doc_id, e)
        return False
    finally:
        if conn:
            put_conn(conn)
