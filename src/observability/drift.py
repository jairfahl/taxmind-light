"""
observability/drift.py — DriftDetector.

Detecta desvio estatístico de métricas em relação ao baseline.
Alerta quando |valor_atual - baseline| > DRIFT_THRESHOLD_SIGMA * σ.
"""

import logging
import math
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DRIFT_THRESHOLD_SIGMA = 2.0
JANELA_DIAS = 7

METRICAS_MONITORADAS = [
    "avg_latencia_ms",
    "pct_scoring_alto",
    "pct_contra_tese",
    "pct_grounding_presente",
    "taxa_bloqueio_m1",
    "taxa_bloqueio_m2",
    "taxa_bloqueio_m3",
    "taxa_bloqueio_m4",
]


@dataclass
class DriftAlert:
    metrica: str
    valor_baseline: float
    valor_atual: float
    desvios_padrao: float
    alert_id: int


class DriftDetectorError(ValueError):
    pass


def _get_conn() -> psycopg2.extensions.connection:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL não definida")
    return psycopg2.connect(url)


def _stddev(valores: list[float]) -> float:
    n = len(valores)
    if n < 2:
        return 0.0
    mean = sum(valores) / n
    variance = sum((v - mean) ** 2 for v in valores) / (n - 1)
    return math.sqrt(variance)


class DriftDetector:

    # ------------------------------------------------------------------
    # Verificar drift
    # ------------------------------------------------------------------
    def verificar_drift(
        self,
        prompt_version: str,
        model_id: str,
    ) -> list[DriftAlert]:
        """
        1. Busca baseline em prompt_baselines
        2. Busca ai_metrics_daily dos últimos JANELA_DIAS
        3. Para cada métrica: se |atual - baseline| > 2σ → persiste em drift_alerts
        """
        conn = _get_conn()
        cur = conn.cursor()
        alerts: list[DriftAlert] = []

        try:
            # Carregar baseline
            cur.execute(
                f"""
                SELECT {', '.join(METRICAS_MONITORADAS)}
                FROM prompt_baselines
                WHERE prompt_version = %s AND model_id = %s
                """,
                (prompt_version, model_id),
            )
            baseline_row = cur.fetchone()
            if not baseline_row:
                raise DriftDetectorError(
                    f"Baseline não encontrado para prompt_version={prompt_version} model_id={model_id}"
                )
            baseline = dict(zip(METRICAS_MONITORADAS, baseline_row))

            # Buscar métricas dos últimos JANELA_DIAS dias
            data_inicio = date.today() - timedelta(days=JANELA_DIAS)
            cur.execute(
                f"""
                SELECT {', '.join(METRICAS_MONITORADAS)}
                FROM ai_metrics_daily
                WHERE prompt_version = %s AND model_id = %s
                  AND data_referencia >= %s
                ORDER BY data_referencia
                """,
                (prompt_version, model_id, data_inicio),
            )
            rows = cur.fetchall()

            if not rows:
                logger.info("Sem métricas nos últimos %d dias para drift check", JANELA_DIAS)
                return []

            # Para cada métrica verificar drift
            for i, metrica in enumerate(METRICAS_MONITORADAS):
                valores = [r[i] for r in rows if r[i] is not None]
                if not valores:
                    continue

                valor_baseline = baseline.get(metrica)
                if valor_baseline is None:
                    continue

                valor_atual = sum(valores) / len(valores)
                sigma = _stddev(valores)

                if sigma == 0:
                    # Sem variabilidade histórica — z-score indefinido; ignorar
                    continue
                else:
                    desvios = abs(valor_atual - valor_baseline) / sigma

                if desvios > DRIFT_THRESHOLD_SIGMA:
                    cur.execute(
                        """
                        INSERT INTO drift_alerts
                            (prompt_version, model_id, metrica, valor_baseline,
                             valor_atual, desvios_padrao)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (prompt_version, model_id, metrica,
                         valor_baseline, valor_atual, desvios),
                    )
                    alert_id = cur.fetchone()[0]
                    conn.commit()
                    alerts.append(DriftAlert(
                        metrica=metrica,
                        valor_baseline=valor_baseline,
                        valor_atual=valor_atual,
                        desvios_padrao=desvios,
                        alert_id=alert_id,
                    ))
                    logger.warning(
                        "Drift detectado: %s | baseline=%.4f atual=%.4f σ=%.2f",
                        metrica, valor_baseline, valor_atual, desvios,
                    )

        finally:
            cur.close()
            conn.close()

        return alerts

    # ------------------------------------------------------------------
    # Registrar baseline
    # ------------------------------------------------------------------
    def registrar_baseline(
        self,
        prompt_version: str,
        model_id: str,
    ) -> dict:
        """
        Calcula baseline a partir dos últimos 30 dias de ai_metrics_daily.
        Requer pelo menos 3 dias de dados.
        """
        conn = _get_conn()
        cur = conn.cursor()
        try:
            data_inicio = date.today() - timedelta(days=30)
            cur.execute(
                f"""
                SELECT {', '.join(METRICAS_MONITORADAS)}, COUNT(*) as sample_size
                FROM ai_metrics_daily
                WHERE prompt_version = %s AND model_id = %s
                  AND data_referencia >= %s
                """,
                (prompt_version, model_id, data_inicio),
            )
            row = cur.fetchone()
            sample_size = row[-1] if row else 0

            if sample_size < 3:
                raise DriftDetectorError(
                    f"Dados insuficientes para baseline: apenas {sample_size} dia(s) "
                    f"(mínimo: 3). Execute mais consultas antes de registrar baseline."
                )

            medias = {}
            for i, metrica in enumerate(METRICAS_MONITORADAS):
                cur.execute(
                    f"""
                    SELECT AVG({metrica})
                    FROM ai_metrics_daily
                    WHERE prompt_version = %s AND model_id = %s
                      AND data_referencia >= %s
                    """,
                    (prompt_version, model_id, data_inicio),
                )
                r = cur.fetchone()
                medias[metrica] = r[0] if r and r[0] is not None else 0.0

            # Calcular avg_response_length e p95_latencia_ms
            cur.execute(
                """
                SELECT AVG(avg_response_length), AVG(p95_latencia_ms)
                FROM ai_metrics_daily
                WHERE prompt_version = %s AND model_id = %s
                  AND data_referencia >= %s
                """,
                (prompt_version, model_id, data_inicio),
            )
            extra = cur.fetchone()

            cur.execute(
                """
                INSERT INTO prompt_baselines
                    (prompt_version, model_id, avg_response_length, avg_latencia_ms,
                     p95_latencia_ms, pct_scoring_alto, pct_contra_tese,
                     pct_grounding_presente, taxa_bloqueio_m1, taxa_bloqueio_m2,
                     taxa_bloqueio_m3, taxa_bloqueio_m4, sample_size)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (prompt_version, model_id) DO UPDATE SET
                    avg_response_length = EXCLUDED.avg_response_length,
                    avg_latencia_ms     = EXCLUDED.avg_latencia_ms,
                    p95_latencia_ms     = EXCLUDED.p95_latencia_ms,
                    pct_scoring_alto    = EXCLUDED.pct_scoring_alto,
                    pct_contra_tese     = EXCLUDED.pct_contra_tese,
                    pct_grounding_presente = EXCLUDED.pct_grounding_presente,
                    taxa_bloqueio_m1    = EXCLUDED.taxa_bloqueio_m1,
                    taxa_bloqueio_m2    = EXCLUDED.taxa_bloqueio_m2,
                    taxa_bloqueio_m3    = EXCLUDED.taxa_bloqueio_m3,
                    taxa_bloqueio_m4    = EXCLUDED.taxa_bloqueio_m4,
                    sample_size         = EXCLUDED.sample_size,
                    baseline_date       = NOW()
                RETURNING id
                """,
                (
                    prompt_version, model_id,
                    extra[0] if extra else None,
                    medias.get("avg_latencia_ms"),
                    extra[1] if extra else None,
                    medias.get("pct_scoring_alto"),
                    medias.get("pct_contra_tese"),
                    medias.get("pct_grounding_presente"),
                    medias.get("taxa_bloqueio_m1"),
                    medias.get("taxa_bloqueio_m2"),
                    medias.get("taxa_bloqueio_m3"),
                    medias.get("taxa_bloqueio_m4"),
                    sample_size,
                ),
            )
            baseline_id = cur.fetchone()[0]
            conn.commit()
            logger.info("Baseline registrado: id=%d pv=%s model=%s sample=%d",
                        baseline_id, prompt_version, model_id, sample_size)
            return {"id": baseline_id, "prompt_version": prompt_version,
                    "model_id": model_id, "sample_size": sample_size, **medias}
        finally:
            cur.close()
            conn.close()

    # ------------------------------------------------------------------
    # Resolver alert
    # ------------------------------------------------------------------
    def resolver_alert(self, alert_id: int, observacao: str) -> None:
        conn = _get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE drift_alerts
                SET resolvido = TRUE, resolvido_em = NOW(), observacao = %s
                WHERE id = %s
                """,
                (observacao, alert_id),
            )
            if cur.rowcount == 0:
                raise DriftDetectorError(f"alert_id {alert_id} não encontrado")
            conn.commit()
            logger.info("Drift alert %d resolvido", alert_id)
        finally:
            cur.close()
            conn.close()
