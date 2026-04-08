"""
src/outputs/legal_hold.py — Legal Hold (DC v7, G14).

Política:
- outputs com classe dossie_decisao/material_compartilhavel: Legal Hold ativo por padrão, 5 anos
- Demais outputs: Legal Hold ativável por ADMIN
- Documentos com Legal Hold NÃO podem ser deletados
- Desativação apenas por ADMIN com justificativa (>= 20 chars) registrada em audit log
- Expiração automática após prazo (padrão 5 anos — CTN art. 150, §4º)
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

import psycopg2

PRAZO_PADRAO_ANOS = 5  # CTN art. 150, §4º — prescrição tributária

# Classes que têm Legal Hold permanente (não desativável)
CLASSES_HOLD_PERMANENTE = {"dossie_decisao", "material_compartilhavel"}


def _get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def _registrar_log(
    cur,
    documento_id: int,
    tabela_origem: str,
    operacao: str,
    realizado_por: Optional[str],
    justificativa: Optional[str] = None,
    hold_ate: Optional[date] = None,
) -> None:
    cur.execute(
        """
        INSERT INTO legal_hold_log
            (documento_id, tabela_origem, operacao,
             realizado_por, justificativa, hold_ate)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (documento_id, tabela_origem, operacao, realizado_por, justificativa, hold_ate),
    )


def ativar_legal_hold(
    documento_id: int,
    tabela_origem: str,
    admin_user_id: str,
    justificativa: str,
    prazo_anos: int = PRAZO_PADRAO_ANOS,
) -> dict:
    """
    Ativa Legal Hold em um documento.
    Apenas ADMIN pode ativar.
    """
    hold_ate = date.today() + timedelta(days=prazo_anos * 365)
    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                if tabela_origem == "outputs":
                    cur.execute(
                        """
                        UPDATE outputs
                        SET legal_hold        = TRUE,
                            legal_hold_ate    = %s,
                            legal_hold_motivo = %s
                        WHERE id = %s
                        """,
                        (hold_ate, justificativa, documento_id),
                    )
                elif tabela_origem == "ai_interactions":
                    cur.execute(
                        """
                        UPDATE ai_interactions
                        SET legal_hold     = TRUE,
                            legal_hold_ate = %s
                        WHERE id = %s
                        """,
                        (hold_ate, documento_id),
                    )
                else:
                    return {"sucesso": False, "erro": f"Tabela '{tabela_origem}' não suportada."}

                _registrar_log(
                    cur, documento_id, tabela_origem,
                    "ativar", admin_user_id, justificativa, hold_ate,
                )
        return {"sucesso": True, "hold_ate": hold_ate.isoformat()}
    finally:
        conn.close()


def desativar_legal_hold(
    documento_id: int,
    tabela_origem: str,
    admin_user_id: str,
    justificativa: str,
) -> dict:
    """
    Desativa Legal Hold.
    APENAS ADMIN. Justificativa obrigatória (>= 20 chars). Registra em audit log.
    Dossiês de Decisão: Legal Hold permanente — não desativável.
    """
    if not justificativa or len(justificativa.strip()) < 20:
        return {
            "sucesso": False,
            "erro": "Justificativa obrigatória (mínimo 20 caracteres) para desativar Legal Hold.",
        }

    # Verificar se é classe com hold permanente
    if tabela_origem == "outputs":
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT classe FROM outputs WHERE id = %s", (documento_id,))
                row = cur.fetchone()
                if row and row[0] in CLASSES_HOLD_PERMANENTE:
                    return {
                        "sucesso": False,
                        "erro": (
                            f"Documentos da classe '{row[0]}' têm Legal Hold permanente. "
                            "Não é possível desativar — DC v7, Rastreabilidade e Legal Hold."
                        ),
                    }
        finally:
            conn.close()

    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                if tabela_origem == "outputs":
                    cur.execute(
                        """
                        UPDATE outputs
                        SET legal_hold = FALSE, legal_hold_ate = NULL
                        WHERE id = %s
                        """,
                        (documento_id,),
                    )
                elif tabela_origem == "ai_interactions":
                    cur.execute(
                        """
                        UPDATE ai_interactions
                        SET legal_hold = FALSE, legal_hold_ate = NULL
                        WHERE id = %s
                        """,
                        (documento_id,),
                    )
                _registrar_log(
                    cur, documento_id, tabela_origem,
                    "desativar", admin_user_id, justificativa,
                )
        return {"sucesso": True}
    finally:
        conn.close()


def verificar_pode_deletar(documento_id: int, tabela_origem: str) -> tuple[bool, str]:
    """
    Verifica se um documento pode ser deletado.
    Returns (pode_deletar, motivo_se_negado).
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            if tabela_origem == "outputs":
                cur.execute(
                    "SELECT legal_hold, legal_hold_ate, classe FROM outputs WHERE id = %s",
                    (documento_id,),
                )
                row = cur.fetchone()
                if not row:
                    return True, ""
                legal_hold, hold_ate, classe = row

                if classe in CLASSES_HOLD_PERMANENTE:
                    return False, (
                        f"Documentos da classe '{classe}' são imutáveis e não podem ser deletados. "
                        "Legal Hold permanente — DC v7, Rastreabilidade e Legal Hold."
                    )
                if legal_hold:
                    ate_str = hold_ate.strftime("%d/%m/%Y") if hold_ate else "prazo indefinido"
                    return False, (
                        f"Documento com Legal Hold ativo até {ate_str}. "
                        "Solicite ao ADMIN a desativação com justificativa."
                    )
                return True, ""

            elif tabela_origem == "ai_interactions":
                cur.execute(
                    "SELECT legal_hold, legal_hold_ate FROM ai_interactions WHERE id = %s",
                    (documento_id,),
                )
                row = cur.fetchone()
                if not row:
                    return True, ""
                legal_hold, hold_ate = row
                if legal_hold:
                    ate_str = hold_ate.strftime("%d/%m/%Y") if hold_ate else "prazo indefinido"
                    return False, (
                        f"Interação com Legal Hold ativo até {ate_str}. "
                        "Solicite ao ADMIN a desativação com justificativa."
                    )
                return True, ""

            return True, ""
    finally:
        conn.close()


def listar_documentos_com_hold(admin_user_id: str) -> list:
    """Lista todos os documentos com Legal Hold ativo (para painel admin)."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    o.id,
                    'outputs'        AS tabela,
                    o.classe::TEXT   AS classe,
                    o.created_at     AS criado_em,
                    o.legal_hold_ate,
                    o.legal_hold_motivo AS motivo,
                    u.nome           AS usuario
                FROM outputs o
                LEFT JOIN users u ON o.user_id = u.id
                WHERE o.legal_hold = TRUE
                UNION ALL
                SELECT
                    ai.id,
                    'ai_interactions' AS tabela,
                    'consulta'        AS classe,
                    ai.created_at     AS criado_em,
                    ai.legal_hold_ate,
                    NULL              AS motivo,
                    u.nome            AS usuario
                FROM ai_interactions ai
                LEFT JOIN users u ON ai.user_id = u.id
                WHERE ai.legal_hold = TRUE
                ORDER BY criado_em DESC
                """,
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
