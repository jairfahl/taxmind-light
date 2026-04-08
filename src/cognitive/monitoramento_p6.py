"""
src/cognitive/monitoramento_p6.py — P6 Ciclo Pós-Decisão.
DC v7, Seção: O Protocolo Decisório — Passo 6.

Fase MVP: registro de resultado + verificação de premissas + alertas básicos.
Motor de Aprendizado Institucional completo: Onda C (C6).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2


# ---------------------------------------------------------------------------
# Termos RT que indicam premissa sensível a mudanças legislativas
# ---------------------------------------------------------------------------

_TERMOS_IMPACTO_RT = [
    "alíquota", "aliquota",
    "cbs", "ibs", "is ",
    "crédito", "credito",
    "split payment",
    "não cumulatividade", "nao cumulatividade",
    "comitê gestor", "cgibs",
    "transição", "transicao",
    "vigência", "vigencia",
]


# ---------------------------------------------------------------------------
# Helpers de banco
# ---------------------------------------------------------------------------

def _get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


# ---------------------------------------------------------------------------
# Funções principais
# ---------------------------------------------------------------------------

def ativar_monitoramento_p6(
    case_id: int,
    user_id: Optional[str],
    titulo: Optional[str] = None,
    interaction_id: Optional[int] = None,
) -> dict:
    """
    Ativa o monitoramento P6 para um caso concluído no P5/P6.
    Chamado automaticamente ao concluir o passo 6 do protocolo.
    """
    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO monitoramento_p6
                        (case_id, interaction_id, user_id, titulo, status)
                    VALUES (%s, %s, %s, %s, 'ativo')
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    (case_id, interaction_id, user_id, titulo),
                )
                row = cur.fetchone()

                # Marcar a interação como monitorada (se fornecida)
                if interaction_id:
                    cur.execute(
                        """
                        UPDATE ai_interactions
                        SET p6_ativo = TRUE, p6_criado_em = NOW()
                        WHERE id = %s
                        """,
                        (interaction_id,),
                    )

        return {"sucesso": True, "monitoramento_id": str(row[0]) if row else None}
    finally:
        conn.close()


def registrar_resultado_real(
    monitoramento_id: str,
    resultado_real: str,
) -> dict:
    """Gestor registra o que efetivamente aconteceu após a decisão."""
    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE monitoramento_p6
                    SET resultado_real = %s,
                        resultado_em   = NOW(),
                        status         = 'encerrado',
                        atualizado_em  = NOW()
                    WHERE id = %s
                    """,
                    (resultado_real, monitoramento_id),
                )
        return {"sucesso": True}
    finally:
        conn.close()


def verificar_premissas_ativas(
    monitoramento_id: str,
    premissas_originais: list,
    normas_novas: list,
) -> dict:
    """
    Verifica se premissas do P2 ainda são válidas após novas normas na base.

    Retorna dict com premissas potencialmente afetadas e alertas gerados.
    """
    premissas_afetadas = []
    for premissa in premissas_originais:
        p_lower = premissa.lower()
        for termo in _TERMOS_IMPACTO_RT:
            if termo in p_lower:
                premissas_afetadas.append(premissa)
                break

    alertas = []
    if premissas_afetadas and normas_novas:
        for norma in normas_novas:
            alertas.append({
                "tipo": "premissa_potencialmente_afetada",
                "norma_nova": norma,
                "premissas": premissas_afetadas,
                "mensagem": (
                    f"A norma '{norma}' foi adicionada à base. "
                    "Verifique se impacta as premissas declaradas nesta decisão."
                ),
                "gerado_em": datetime.now(timezone.utc).isoformat(),
            })

    if alertas:
        conn = _get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE monitoramento_p6
                        SET alertas_gerados      = alertas_gerados || %s::jsonb,
                            ultimo_alerta_em     = NOW(),
                            status               = 'revisao_pendente',
                            premissas_invalidas  = %s,
                            atualizado_em        = NOW()
                        WHERE id = %s
                        """,
                        (json.dumps(alertas), premissas_afetadas, monitoramento_id),
                    )
        finally:
            conn.close()

    return {
        "premissas_afetadas": premissas_afetadas,
        "alertas": alertas,
        "requer_revisao": len(alertas) > 0,
    }


def listar_decisoes_ativas(user_id: Optional[str]) -> list:
    """Lista decisões ativas em monitoramento P6 para o usuário."""
    if not user_id:
        return []

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m.id,
                    m.case_id,
                    m.interaction_id,
                    m.status,
                    m.ultimo_alerta_em,
                    m.premissas_invalidas,
                    m.criado_em,
                    COALESCE(m.titulo, c.titulo, ai.query_texto, '(sem descrição)') AS query,
                    m.resultado_real
                FROM monitoramento_p6 m
                LEFT JOIN cases c ON m.case_id = c.id
                LEFT JOIN ai_interactions ai ON m.interaction_id = ai.id
                WHERE m.user_id = %s
                  AND m.status != 'encerrado'
                ORDER BY m.atualizado_em DESC
                LIMIT 50
                """,
                (user_id,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
