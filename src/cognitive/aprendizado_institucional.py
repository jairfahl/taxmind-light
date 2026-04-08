"""
src/cognitive/aprendizado_institucional.py — Motor de Aprendizado Institucional.
DC v7, G24: Fase Inicial (Onda C).

Extrai heurísticas de casos encerrados (P6) e alimenta alertas proativos.

Salvaguardas obrigatórias (DC v7):
- Data de validade por heurística (6 meses)
- Sinalização automática de expiradas
- Auditoria completa: qual caso, quando, dados de origem

Fase Onda C: extração de casos P6 + métricas básicas.
Proatividade Customizada completa (RDM-008): Onda D (D5).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from src.db.pool import get_conn, put_conn

logger = logging.getLogger(__name__)

PRAZO_VALIDADE_HEURISTICA_DIAS = 180  # 6 meses — revisão semestral DC v7


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

_TERMOS_TAG: dict[str, str] = {
    "CBS": "cbs", "IBS": "ibs", "IS ": "is_seletivo",
    "split payment": "split_payment",
    "crédito": "creditamento", "credito": "creditamento",
    "alíquota": "aliquota", "aliquota": "aliquota",
    "transição": "transicao", "transicao": "transicao",
    "regime": "regime_tributario",
    "CAPEX": "capex", "capex": "capex",
}


def _extrair_tags_premissas(premissas: list[str]) -> list[str]:
    """Extrai tags de domínio das premissas para indexação por tag."""
    tags: set[str] = set()
    for premissa in premissas:
        p_lower = premissa.lower()
        for termo, tag in _TERMOS_TAG.items():
            if termo.lower() in p_lower:
                tags.add(tag)
    return list(tags)


def _calcular_metricas_caso(dossie_content: dict) -> dict:
    """
    Calcula métricas de aprendizado de um caso encerrado.
    Usa dados do P2 (premissas/riscos) e P5 (decisão vs IA).
    """
    p2 = dossie_content.get("p2_estruturacao", {})
    p5 = dossie_content.get("p5_decisao", {})

    premissas = p2.get("premissas", []) if isinstance(p2, dict) else []
    riscos    = p2.get("riscos_fiscais", []) if isinstance(p2, dict) else []
    similaridade = p5.get("carimbo_similaridade") if isinstance(p5, dict) else None

    houve_divergencia = (similaridade is not None and similaridade < 0.70)

    return {
        "n_premissas": len(premissas) if isinstance(premissas, list) else 0,
        "n_riscos": len(riscos) if isinstance(riscos, list) else 0,
        "houve_divergencia": houve_divergencia,
        "similaridade_ia": similaridade,
    }


# ---------------------------------------------------------------------------
# Extração de heurísticas
# ---------------------------------------------------------------------------

def extrair_heuristicas_caso(
    monitoramento_id: str,
    resultado_real: str,
    user_id: Optional[str],
) -> list[dict]:
    """
    Extrai heurísticas de um caso encerrado.
    Chamado automaticamente ao registrar_resultado_real() no P6.

    Usa o dossiê associado via case_id do monitoramento.
    Falhas individuais não interrompem o encerramento do caso.

    Returns:
        Lista de heurísticas geradas (pode ser vazia).
    """
    validade = date.today() + timedelta(days=PRAZO_VALIDADE_HEURISTICA_DIAS)
    heuristicas_geradas: list[dict] = []

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Buscar dossiê associado ao monitoramento pelo case_id
            cur.execute(
                """
                SELECT o.id, o.conteudo, o.created_at
                FROM monitoramento_p6 m
                JOIN outputs o ON m.case_id = o.case_id
                    AND o.classe = 'dossie_decisao'
                WHERE m.id = %s
                ORDER BY o.created_at DESC
                LIMIT 1
                """,
                (monitoramento_id,),
            )
            row = cur.fetchone()

        if not row:
            logger.info(
                "Aprendizado: dossiê não encontrado para monitoramento %s "
                "(normal se P6 foi ativado sem protocolo completo)",
                monitoramento_id,
            )
            return []

        dossie_id: int = row[0]
        conteudo: dict = row[1] if isinstance(row[1], dict) else {}

        metricas = _calcular_metricas_caso(conteudo)
        p2 = conteudo.get("p2_estruturacao", {}) or {}
        p3 = conteudo.get("p3_analise", {}) or {}

        premissas: list = p2.get("premissas", []) if isinstance(p2, dict) else []
        normas: list = p3.get("normas_utilizadas", []) if isinstance(p3, dict) else []
        if not isinstance(premissas, list):
            premissas = []

        # ── HEURÍSTICA 1: premissas estáveis ──────────────────────────────────
        if premissas and resultado_real:
            heuristicas_geradas.append({
                "titulo": f"Premissas validadas — {len(premissas)} premissa(s) permaneceram estáveis",
                "descricao": (
                    f"Caso encerrado com {len(premissas)} premissa(s) originais "
                    f"sem necessidade de revisão. Resultado: {resultado_real[:200]}"
                ),
                "tipo": "premissa_estavel",
                "tags": _extrair_tags_premissas(premissas),
                "normas_base": normas,
            })

        # ── HEURÍSTICA 2: divergência do gestor ───────────────────────────────
        if metricas["houve_divergencia"] and resultado_real:
            heuristicas_geradas.append({
                "titulo": "Gestor divergiu da IA — resultado registrado para calibração futura",
                "descricao": (
                    f"Gestor optou por posição diferente da IA "
                    f"(similaridade: {metricas['similaridade_ia']:.0%}). "
                    f"Resultado real: {resultado_real[:200]}"
                ),
                "tipo": "divergencia_gestor_melhor",
                "tags": ["divergencia", "julgamento_humano"],
                "normas_base": normas,
            })

        # Persistir heurísticas
        with conn:
            with conn.cursor() as cur:
                for h in heuristicas_geradas:
                    cur.execute(
                        """
                        INSERT INTO heuristicas (
                            caso_origem_id, dossie_id, user_id,
                            titulo, descricao, tipo,
                            tags, normas_base, valida_ate, status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ativa')
                        """,
                        (
                            monitoramento_id, dossie_id, user_id,
                            h["titulo"], h["descricao"], h["tipo"],
                            h["tags"], h["normas_base"], validade.isoformat(),
                        ),
                    )

                # Atualizar métricas do mês (ON CONFLICT requer UNIQUE user_id+periodo)
                if user_id:
                    cur.execute(
                        """
                        INSERT INTO metricas_aprendizado
                            (user_id, periodo, casos_encerrados, heuristicas_geradas)
                        VALUES (%s, DATE_TRUNC('month', NOW())::DATE, 1, %s)
                        ON CONFLICT (user_id, periodo) DO UPDATE
                        SET casos_encerrados    = metricas_aprendizado.casos_encerrados + 1,
                            heuristicas_geradas = metricas_aprendizado.heuristicas_geradas
                                                  + EXCLUDED.heuristicas_geradas,
                            atualizado_em       = NOW()
                        """,
                        (user_id, len(heuristicas_geradas)),
                    )

        logger.info(
            "Aprendizado: %d heurística(s) gerada(s) do caso %s",
            len(heuristicas_geradas), monitoramento_id,
        )
        return heuristicas_geradas

    finally:
        put_conn(conn)


# ---------------------------------------------------------------------------
# Alertas proativos
# ---------------------------------------------------------------------------

def buscar_heuristicas_relevantes(
    query: str,
    user_id: Optional[str],
    limite: int = 3,
) -> list[dict]:
    """
    Busca heurísticas ativas relevantes para a query atual.
    Usado para exibir alertas proativos antes da análise.
    """
    if not user_id:
        return []

    termos = _extrair_tags_premissas([query])
    if not termos:
        return []

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT titulo, descricao, tipo, valida_ate, criado_em
                FROM heuristicas
                WHERE user_id = %s
                  AND status = 'ativa'
                  AND valida_ate >= CURRENT_DATE
                  AND tags && %s::text[]
                ORDER BY criado_em DESC
                LIMIT %s
                """,
                (user_id, termos, limite),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.debug("buscar_heuristicas_relevantes falhou: %s", e)
        return []
    finally:
        put_conn(conn)


# ---------------------------------------------------------------------------
# Salvaguarda: expiração
# ---------------------------------------------------------------------------

def verificar_heuristicas_expiradas(user_id: Optional[str]) -> int:
    """
    Salvaguarda DC v7: sinaliza heurísticas expiradas.
    Retorna quantidade expirada nesta execução.
    """
    if not user_id:
        return 0

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE heuristicas
                    SET status = 'expirada'
                    WHERE user_id = %s
                      AND status = 'ativa'
                      AND valida_ate < CURRENT_DATE
                    """,
                    (user_id,),
                )
                expiradas = cur.rowcount

        if expiradas > 0:
            logger.info(
                "Aprendizado: %d heurística(s) expirada(s) para user %s",
                expiradas, user_id,
            )
        return expiradas
    except Exception as e:
        logger.debug("verificar_heuristicas_expiradas falhou: %s", e)
        return 0
    finally:
        put_conn(conn)


# ---------------------------------------------------------------------------
# Métricas para painel
# ---------------------------------------------------------------------------

def calcular_metricas_usuario(user_id: Optional[str]) -> dict:
    """Calcula métricas de aprendizado do usuário para o painel."""
    vazio = {
        "total_heuristicas": 0, "ativas": 0, "expiradas": 0,
        "divergencias": 0, "casos_ativos": 0, "casos_encerrados": 0,
    }
    if not user_id:
        return vazio

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_heuristicas,
                    COUNT(*) FILTER (WHERE status = 'ativa')    AS ativas,
                    COUNT(*) FILTER (WHERE status = 'expirada') AS expiradas,
                    COUNT(*) FILTER (WHERE tipo = 'divergencia_gestor_melhor') AS divergencias
                FROM heuristicas
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            heur = dict(zip([d[0] for d in cur.description], row)) if row else {}

            cur.execute(
                "SELECT COUNT(*) FROM monitoramento_p6 WHERE user_id = %s AND status = 'encerrado'",
                (user_id,),
            )
            casos_encerrados = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM monitoramento_p6 WHERE user_id = %s AND status = 'ativo'",
                (user_id,),
            )
            casos_ativos = cur.fetchone()[0]

        return {**heur, "casos_ativos": casos_ativos, "casos_encerrados": casos_encerrados}
    except Exception as e:
        logger.debug("calcular_metricas_usuario falhou: %s", e)
        return vazio
    finally:
        put_conn(conn)
