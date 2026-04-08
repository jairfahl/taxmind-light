"""
src/cognitive/proatividade.py — Proatividade Customizada (DC v7, G25, RDM-008 MVP).

Detecta padrões de uso e sugere monitoramento de temas frequentes.
Transforma o Tribus-AI de ferramenta reativa para assistente antecipativo.

Fase MVP: detecção por frequência de tags.
Recálculo automático de cenários: Onda 2+.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from src.db.pool import get_conn, put_conn

logger = logging.getLogger(__name__)

# Threshold: N análises sobre o mesmo tema em 90 dias → sugerir monitoramento
THRESHOLD_SUGESTAO = 3
JANELA_DIAS = 90
SILENCIO_PADRAO_DIAS = 30

_BYPASS_UUID = "00000000-0000-0000-0000-000000000000"

# Temas mapeados a partir das tags de aprendizado_institucional
TEMAS_CONFIG: dict[str, str] = {
    "creditamento":       "Creditamento IBS/CBS",
    "cbs":                "CBS — Contribuição sobre Bens e Serviços",
    "ibs":                "IBS — Imposto sobre Bens e Serviços",
    "split_payment":      "Split Payment",
    "is_seletivo":        "Imposto Seletivo (IS)",
    "transicao":          "Regime de Transição 2026–2033",
    "regime_tributario":  "Regime Tributário",
    "aliquota":           "Alíquotas e Incidência",
    "capex":              "Créditos sobre CAPEX",
    "nao_cumulatividade": "Não-Cumulatividade Plena",
}


# ── DETECÇÃO DE PADRÕES ───────────────────────────────────────────────────────

def registrar_tags_analise(
    user_id: Optional[str],
    tags: list[str],
) -> None:
    """
    Registra as tags de uma análise para detecção de padrões.
    Chamado após cada análise — incrementa contagem por tema.
    Tags desconhecidas (fora de TEMAS_CONFIG) são ignoradas.
    """
    if not user_id or user_id == _BYPASS_UUID or not tags:
        return

    temas_validos = [t for t in tags if t in TEMAS_CONFIG]
    if not temas_validos:
        return

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                for tema in temas_validos:
                    cur.execute(
                        """
                        INSERT INTO padroes_uso
                            (user_id, tema, contagem, primeira_vez, ultima_vez)
                        VALUES (%s, %s, 1, NOW(), NOW())
                        ON CONFLICT (user_id, tema)
                        DO UPDATE SET
                            contagem   = padroes_uso.contagem + 1,
                            ultima_vez = NOW()
                        """,
                        (user_id, tema),
                    )
    except Exception as e:
        logger.warning("Proatividade: erro ao registrar tags para user %s: %s", user_id, e)
    finally:
        put_conn(conn)


def detectar_padroes(user_id: Optional[str]) -> list[dict]:
    """
    Detecta temas com frequência >= THRESHOLD nos últimos JANELA_DIAS dias.
    Exclui temas silenciados e temas com sugestão já desativada.
    Retorna no máximo 3 padrões ordenados por frequência.
    """
    if not user_id or user_id == _BYPASS_UUID:
        return []

    janela_inicio = date.today() - timedelta(days=JANELA_DIAS)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.tema, p.contagem, p.ultima_vez
                FROM padroes_uso p
                WHERE p.user_id = %s
                  AND p.contagem >= %s
                  AND p.ultima_vez >= %s
                  AND p.sugestao_ativa = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM sugestoes_silenciadas s
                      WHERE s.user_id = %s
                        AND s.tema = p.tema
                        AND s.silenciado_ate >= CURRENT_DATE
                  )
                ORDER BY p.contagem DESC
                LIMIT 3
                """,
                (user_id, THRESHOLD_SUGESTAO, janela_inicio, user_id),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.warning("Proatividade: erro ao detectar padrões para user %s: %s", user_id, e)
        return []
    finally:
        put_conn(conn)


# ── GERADOR DE SUGESTÕES ──────────────────────────────────────────────────────

@dataclass
class SugestaoProativa:
    tema: str
    tema_label: str
    contagem: int
    mensagem: str
    acao_sugerida: str


def gerar_sugestoes(user_id: Optional[str]) -> list[SugestaoProativa]:
    """
    Gera sugestões proativas baseadas nos padrões detectados.
    Retorna lista vazia se sem histórico suficiente.
    """
    padroes = detectar_padroes(user_id)
    sugestoes = []

    for padrao in padroes:
        tema = padrao["tema"]
        label = TEMAS_CONFIG.get(tema, tema)
        contagem = padrao["contagem"]

        sugestoes.append(
            SugestaoProativa(
                tema=tema,
                tema_label=label,
                contagem=contagem,
                mensagem=(
                    f"Identificamos {contagem} análise(s) sobre **{label}** "
                    f"nos últimos {JANELA_DIAS} dias."
                ),
                acao_sugerida=(
                    f"Deseja que o sistema monitore automaticamente mudanças "
                    f"normativas sobre {label}?"
                ),
            )
        )

    return sugestoes


# ── SILENCIAMENTO ─────────────────────────────────────────────────────────────

def silenciar_sugestao(
    user_id: str,
    tema: str,
    dias: int = SILENCIO_PADRAO_DIAS,
) -> bool:
    """Silencia sugestão para o tema por N dias."""
    silenciado_ate = date.today() + timedelta(days=dias)
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sugestoes_silenciadas
                        (user_id, tema, silenciado_ate)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, tema)
                    DO UPDATE SET silenciado_ate = EXCLUDED.silenciado_ate
                    """,
                    (user_id, tema, silenciado_ate),
                )
        return True
    except Exception as e:
        logger.warning("Proatividade: erro ao silenciar tema %s: %s", tema, e)
        return False
    finally:
        put_conn(conn)


def ativar_monitoramento_tema(user_id: str, tema: str) -> bool:
    """
    Usuário confirma monitoramento do tema.
    Marca sugestao_ativa = FALSE — não mostrar mais como sugestão.
    """
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE padroes_uso
                       SET sugestao_ativa = FALSE
                     WHERE user_id = %s AND tema = %s
                    """,
                    (user_id, tema),
                )
        logger.info("Proatividade: monitoramento ativado para tema '%s' user %s", tema, user_id)
        return True
    except Exception as e:
        logger.warning("Proatividade: erro ao ativar monitoramento: %s", e)
        return False
    finally:
        put_conn(conn)
