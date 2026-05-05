"""
src/api/helpers.py — Funções auxiliares compartilhadas pelos routers.

Inclui:
- _carregar_contexto_caso
- _buscar_casos_similares
- _get_tenant_info_by_user
- _verificar_acesso_caso
- _verificar_acesso_output
- _verificar_limite_casos
- _verificar_limite_consultas
- Constantes de limite
"""

import json
import logging
import re
from typing import Optional

from fastapi import HTTPException

from src.db.pool import get_conn, put_conn

logger = logging.getLogger(__name__)

# --- Limites por plano ---

_CONSULTA_TRIAL_LIMIT = 5  # consultas /analisar durante o trial (migration 135)

_CASE_LIMITS: dict[str, int] = {
    "trial":        1,   # total durante o período de trial
    "starter":      10,  # por mês calendário
    "professional": 50,  # por mês calendário
    "enterprise":   -1,  # ilimitado
}


def _carregar_contexto_caso(case_id: str) -> Optional[dict]:
    """Carrega dados dos passos anteriores do caso para injeção no LLM."""
    try:
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT passo, dados FROM case_steps WHERE case_id = %s AND concluido = TRUE ORDER BY passo",
                (case_id,),
            )
            rows = cur.fetchall()
            cur.close()
        finally:
            put_conn(conn)
        if not rows:
            return None
        import json as _json
        contexto: dict = {}
        for passo, dados_raw in rows:
            if isinstance(dados_raw, str):
                dados_raw = _json.loads(dados_raw)
            contexto[passo] = dados_raw
        logger.info("Contexto do caso %s carregado: passos %s", case_id, list(contexto.keys()))
        return contexto
    except Exception as e:
        logger.warning("Falha ao carregar contexto do caso %s: %s", case_id, e)
        return None


def _buscar_casos_similares(query: str, case_id_atual: Optional[str] = None, top_k: int = 3) -> list[dict]:
    """Busca casos concluídos similares para retroalimentação do LLM.

    Critérios de qualidade:
    - Caso com status 'aprendizado_extraido' (Passo 6 completo)
    - dados_qualidade = 'verde' no Passo 2
    - Exclui o caso atual (se informado)

    Usa embedding Voyage da query para similaridade cosine contra
    a concatenação de titulo+descricao dos casos concluídos.
    """
    try:
        from src.rag.retriever import _embed_query, EMBEDDING_MODEL
        import json as _json

        vetor_query = _embed_query(query)
        vetor_str = "[" + ",".join(str(v) for v in vetor_query) + "]"

        conn = get_conn()
        try:
            cur = conn.cursor()
            # Buscar casos concluídos com qualidade verde
            # Usa similaridade cosine entre o embedding da query e
            # o embedding gerado on-the-fly do titulo+descricao do caso
            sql = """
                WITH casos_concluidos AS (
                    SELECT
                        c.id AS case_id,
                        c.titulo,
                        s1.dados AS dados_step1,
                        s2.dados AS dados_step2,
                        s5.dados AS dados_step5,
                        s6.dados AS dados_step6
                    FROM cases c
                    JOIN case_steps s1 ON s1.case_id = c.id AND s1.passo = 1 AND s1.concluido = TRUE
                    JOIN case_steps s2 ON s2.case_id = c.id AND s2.passo = 2 AND s2.concluido = TRUE
                    JOIN case_steps s5 ON s5.case_id = c.id AND s5.passo = 5 AND s5.concluido = TRUE
                    JOIN case_steps s6 ON s6.case_id = c.id AND s6.passo = 6 AND s6.concluido = TRUE
                    WHERE c.status = 'aprendizado_extraido'
                      AND (s2.dados->>'dados_qualidade') = 'verde'
            """
            params: list = []
            if case_id_atual:
                sql += "      AND c.id != %s\n"
                params.append(case_id_atual)
            sql += """
                )
                SELECT case_id, titulo, dados_step1, dados_step2, dados_step5, dados_step6
                FROM casos_concluidos
                ORDER BY case_id DESC
                LIMIT %s
            """
            params.append(top_k * 3)  # fetch more, rank below

            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()
        finally:
            put_conn(conn)

        if not rows:
            logger.info("Nenhum caso concluído com qualidade verde encontrado para retroalimentação.")
            return []

        # Ranking por similaridade textual simples (sem embedding extra para evitar latência)
        # Usa overlap de palavras-chave entre query e titulo+descricao do caso
        import re as _re
        query_words = set(_re.findall(r'\w{4,}', query.lower()))

        scored = []
        for case_id, titulo, d1, d2, d5, d6 in rows:
            if isinstance(d1, str):
                d1 = _json.loads(d1)
            if isinstance(d2, str):
                d2 = _json.loads(d2)
            if isinstance(d5, str):
                d5 = _json.loads(d5)
            if isinstance(d6, str):
                d6 = _json.loads(d6)

            caso_text = f"{titulo} {d1.get('descricao', '')} {' '.join(d1.get('premissas', []))}".lower()
            caso_words = set(_re.findall(r'\w{4,}', caso_text))
            overlap = len(query_words & caso_words)
            if overlap < 2:
                continue

            scored.append({
                "case_id": case_id,
                "titulo": titulo,
                "score": overlap,
                "premissas": d1.get("premissas", []),
                "riscos": d2.get("riscos", []),
                "decisao_final": d5.get("decisao_final", ""),
                "resultado_real": d6.get("resultado_real", ""),
                "aprendizado": d6.get("aprendizado_extraido", ""),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        resultado = scored[:top_k]
        logger.info("Retroalimentação: %d caso(s) similar(es) encontrado(s) para query.", len(resultado))
        return resultado

    except Exception as e:
        logger.warning("Falha na busca de casos similares (não-bloqueante): %s", e)
        return []


def _get_tenant_info_by_user(user_id: str, conn):
    """
    Retorna (tenant_id, subscription_status, plano, trial_ends_at) para um user_id.

    REGRA DE ISOLAMENTO: a unidade de isolamento é o TENANT (CNPJ), não o usuário.
    user_id é apenas o ponto de entrada para resolver tenant_id. Toda query de negócio
    que segue este helper deve filtrar por tenant_id, nunca por user_id diretamente.
    Todos os usuários do mesmo tenant compartilham cases, documentos e limites de plano.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT t.id, t.subscription_status, t.plano, t.trial_ends_at
               FROM users u JOIN tenants t ON t.id = u.tenant_id
               WHERE u.id = %s LIMIT 1""",
            (user_id,),
        )
        return cur.fetchone()


def _verificar_acesso_caso(case_id: str, user_id: Optional[str], perfil: Optional[str]) -> None:
    """
    Verifica se o user tem acesso ao caso pelo tenant.

    - ADMIN: acesso total.
    - USER sem tenant (raro): acesso apenas a casos sem tenant_id.
    - USER com tenant: acesso a casos do mesmo tenant + casos sem tenant_id (legado).

    Levanta HTTPException 404 se acesso negado (não revela existência do recurso).
    """
    if perfil == "ADMIN":
        return  # ADMIN tem acesso total

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            if user_id:
                cur.execute(
                    """SELECT 1 FROM cases
                       WHERE id = %s
                       AND (tenant_id IS NULL
                            OR tenant_id = (SELECT tenant_id FROM users WHERE id = %s LIMIT 1))
                       LIMIT 1""",
                    (case_id, user_id),
                )
            else:
                cur.execute(
                    "SELECT 1 FROM cases WHERE id = %s AND tenant_id IS NULL LIMIT 1",
                    (case_id,),
                )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Caso não encontrado.")
    except HTTPException:
        raise
    except Exception:
        pass  # DB indisponível: deixar o endpoint tratar o erro normalmente
    finally:
        if conn:
            put_conn(conn)


def _verificar_acesso_output(output_id: str, user_id: Optional[str], perfil: Optional[str]) -> None:
    """
    Verifica se o user tem acesso ao output pelo tenant (via cases.tenant_id).

    Levanta HTTPException 404 se acesso negado.
    """
    if perfil == "ADMIN":
        return

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            if user_id:
                cur.execute(
                    """SELECT 1 FROM outputs o
                       JOIN cases c ON c.id = o.case_id
                       WHERE o.id = %s
                       AND (c.tenant_id IS NULL
                            OR c.tenant_id = (SELECT tenant_id FROM users WHERE id = %s LIMIT 1))
                       LIMIT 1""",
                    (output_id, user_id),
                )
            else:
                cur.execute(
                    """SELECT 1 FROM outputs o
                       JOIN cases c ON c.id = o.case_id
                       WHERE o.id = %s AND c.tenant_id IS NULL LIMIT 1""",
                    (output_id,),
                )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Output não encontrado.")
    except HTTPException:
        raise
    except Exception:
        pass
    finally:
        if conn:
            put_conn(conn)


def _verificar_limite_casos(
    tenant_id: str,
    subscription_status: str,
    plano: str,
    trial_ends_at,
    conn,
) -> tuple:
    """
    Verifica se o tenant pode criar mais casos.

    Returns:
        (permitido: bool, usado: int, limite: int) — limite -1 = ilimitado
    """
    chave = "trial" if subscription_status == "trial" else (plano or "starter")
    limite = _CASE_LIMITS.get(chave, _CASE_LIMITS["starter"])

    if limite == -1:
        return True, 0, -1

    with conn.cursor() as cur:
        if subscription_status == "trial":
            cur.execute(
                "SELECT COUNT(*) FROM cases WHERE tenant_id = %s",
                (tenant_id,),
            )
        else:
            cur.execute(
                """SELECT COUNT(*) FROM cases
                   WHERE tenant_id = %s
                     AND created_at >= date_trunc('month', NOW())""",
                (tenant_id,),
            )
        usado = cur.fetchone()[0]

    return usado < limite, usado, limite


def _verificar_limite_consultas(tenant_id: str, conn) -> tuple:
    """
    Retorna (permitido: bool, usado: int, limite: int) para consultas /analisar de tenants trial.
    Consultas de planos pagos são sempre permitidas (limite = -1).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT consultas_trial_usadas FROM tenants WHERE id = %s",
            (tenant_id,),
        )
        row = cur.fetchone()
    usado = row[0] if row else 0
    return usado < _CONSULTA_TRIAL_LIMIT, usado, _CONSULTA_TRIAL_LIMIT
