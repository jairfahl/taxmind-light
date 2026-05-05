"""
protocol/carimbo.py — DetectorCarimbo: detecta terceirização cognitiva.

Compara embedding da decisão do gestor com a recomendação da IA.
Se similaridade cosseno >= 0.70 → alerta obrigatório.
"""

import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Optional

import psycopg2
import voyageai
from dotenv import load_dotenv

from src.db.pool import get_conn, put_conn

load_dotenv()
logger = logging.getLogger(__name__)

THRESHOLD_COSSENO = 0.70
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3")

_voyage_client: Optional[voyageai.Client] = None


def _get_voyage() -> voyageai.Client:
    global _voyage_client
    if _voyage_client is None:
        key = os.getenv("VOYAGE_API_KEY")
        if not key or key == "<PREENCHER>":
            raise EnvironmentError("VOYAGE_API_KEY não configurada")
        _voyage_client = voyageai.Client(api_key=key)
    return _voyage_client


def _embed(texto: str) -> list[float]:
    from src.resilience.backoff import resilient_call, VOYAGE_CARIMBO_CONFIG
    client = _get_voyage()
    result = resilient_call(client.embed, [texto], model=EMBEDDING_MODEL, config=VOYAGE_CARIMBO_CONFIG)
    return result.embeddings[0]


def _cosseno(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


@dataclass
class CarimboResult:
    score_similaridade: float
    alerta: bool
    mensagem: Optional[str]
    alert_id: Optional[int]


class CarimboConfirmacaoError(ValueError):
    """Justificativa insuficiente para confirmar o carimbo."""


class DetectorCarimbo:

    def verificar(
        self,
        case_id: str,
        passo: int,
        texto_decisao: str,
        texto_recomendacao: str,
    ) -> CarimboResult:
        """
        Calcula similaridade cosseno entre decisão e recomendação.
        Persiste alerta em carimbo_alerts se score >= THRESHOLD.
        """
        v_decisao = _embed(texto_decisao)
        time.sleep(22)  # rate limit voyage
        v_recomendacao = _embed(texto_recomendacao)

        score = _cosseno(v_decisao, v_recomendacao)
        # Clamp para [0, 1] por segurança numérica
        score = max(0.0, min(1.0, score))

        alerta = score >= THRESHOLD_COSSENO
        alert_id = None

        if alerta:
            mensagem = (
                f"Sua decisão apresenta alta similaridade com a recomendação da IA "
                f"(score: {score:.0%}). Confirme que esta é sua posição independente e justifique."
            )
            conn = get_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO carimbo_alerts
                        (case_id, passo, score_similaridade, texto_decisao, texto_recomendacao)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (case_id, passo, score, texto_decisao, texto_recomendacao),
                )
                alert_id = cur.fetchone()[0]
                conn.commit()
                cur.close()
            finally:
                put_conn(conn)
            logger.warning("Carimbo detectado: case=%s passo=%d score=%.3f alert_id=%d",
                           case_id, passo, score, alert_id)
        else:
            mensagem = None
            logger.info("Carimbo OK: case=%s passo=%d score=%.3f", case_id, passo, score)

        return CarimboResult(
            score_similaridade=score,
            alerta=alerta,
            mensagem=mensagem,
            alert_id=alert_id,
        )

    def confirmar(self, alert_id: int, justificativa: str) -> None:
        """
        Confirma o alerta de carimbo com justificativa do gestor.
        Requer justificativa com no mínimo 20 caracteres.
        """
        if not justificativa or len(justificativa.strip()) < 20:
            raise CarimboConfirmacaoError(
                "Justificativa deve ter no mínimo 20 caracteres"
            )
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE carimbo_alerts SET confirmado=TRUE, justificativa=%s WHERE id=%s",
                (justificativa.strip(), alert_id),
            )
            if cur.rowcount == 0:
                cur.close()
                raise ValueError(f"alert_id {alert_id} não encontrado")
            conn.commit()
            cur.close()
        finally:
            put_conn(conn)
        logger.info("Carimbo confirmado: alert_id=%d", alert_id)
