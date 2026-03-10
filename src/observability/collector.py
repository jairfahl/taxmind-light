"""
observability/collector.py — MetricsCollector.

Coleta métricas de cada interação com o CognitiveEngine e agrega
em ai_metrics_daily. Integrado no analisar() via chamada não-bloqueante.
"""

import logging
import os
import statistics
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _get_conn() -> psycopg2.extensions.connection:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL não definida")
    return psycopg2.connect(url)


@dataclass
class DailyMetrics:
    data_referencia: date
    prompt_version: str
    model_id: str
    total_interacoes: int
    avg_response_length: Optional[float]
    avg_latencia_ms: Optional[float]
    p95_latencia_ms: Optional[float]
    pct_scoring_alto: Optional[float]
    pct_contra_tese: Optional[float]
    pct_grounding_presente: Optional[float]
    taxa_alucinacao: Optional[float]
    taxa_bloqueio_m1: Optional[float]
    taxa_bloqueio_m2: Optional[float]
    taxa_bloqueio_m3: Optional[float]
    taxa_bloqueio_m4: Optional[float]


def _percentil(valores: list[float], p: float) -> float:
    """Calcula percentil p (0-100) de uma lista."""
    if not valores:
        return 0.0
    sorted_v = sorted(valores)
    idx = (p / 100) * (len(sorted_v) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_v) - 1)
    frac = idx - lo
    return sorted_v[lo] + frac * (sorted_v[hi] - sorted_v[lo])


class MetricsCollector:

    def registrar_interacao(self, analise_result, query: str) -> None:
        """
        Chamado após cada CognitiveEngine.analisar().
        Atualiza a linha existente em ai_interactions com campos de observability.
        Exceções são logadas, não propagadas.
        """
        try:
            contra_tese_gerada = analise_result.contra_tese is not None
            grounding_presente = bool(analise_result.fundamento_legal)
            response_length = len(analise_result.resposta) if analise_result.resposta else 0

            conn = _get_conn()
            cur = conn.cursor()
            # Atualiza o registro mais recente para esta query/model
            cur.execute(
                """
                UPDATE ai_interactions
                SET contra_tese_gerada = %s,
                    grounding_presente = %s,
                    response_length = %s
                WHERE id = (
                    SELECT id FROM ai_interactions
                    WHERE query_texto = %s AND model_id = %s
                    ORDER BY created_at DESC LIMIT 1
                )
                """,
                (contra_tese_gerada, grounding_presente, response_length,
                 query, analise_result.model_id),
            )
            conn.commit()
            cur.close()
            conn.close()
            logger.debug("MetricsCollector: interação registrada query=%s", query[:40])
        except Exception as e:
            logger.warning("MetricsCollector.registrar_interacao falhou (não bloqueante): %s", e)

    def agregar_diario(self, data: Optional[date] = None) -> Optional[DailyMetrics]:
        """
        Agrega registros de ai_interactions do dia em ai_metrics_daily.
        Upsert — se já existe registro do dia, atualiza.
        """
        if data is None:
            data = date.today()

        try:
            conn = _get_conn()
            cur = conn.cursor()

            cur.execute(
                """
                SELECT
                    prompt_version, model_id,
                    latencia_ms, scoring_confianca,
                    NOT m1_existencia AS bloqueio_m1,
                    NOT m2_validade AS bloqueio_m2,
                    NOT m3_pertinencia AS bloqueio_m3,
                    NOT m4_consistencia AS bloqueio_m4,
                    bloqueado,
                    contra_tese_gerada,
                    grounding_presente,
                    response_length
                FROM ai_interactions
                WHERE DATE(created_at) = %s
                """,
                (data,),
            )
            rows = cur.fetchall()

            if not rows:
                cur.close()
                conn.close()
                logger.info("Sem interações em %s para agregar", data)
                return None

            # Agrupar por (prompt_version, model_id)
            from collections import defaultdict
            grupos: dict = defaultdict(list)
            for row in rows:
                key = (row[0] or "unknown", row[1] or "unknown")
                grupos[key].append(row)

            last_metrics = None
            for (pv, mid), grupo in grupos.items():
                latencias = [r[2] for r in grupo if r[2] is not None]
                n = len(grupo)

                def pct(field_idx, true_val=None):
                    if true_val is not None:
                        return sum(1 for r in grupo if r[field_idx] == true_val) / n if n else 0.0
                    return sum(1 for r in grupo if r[field_idx]) / n if n else 0.0

                metrics = DailyMetrics(
                    data_referencia=data,
                    prompt_version=pv,
                    model_id=mid,
                    total_interacoes=n,
                    avg_response_length=sum(r[11] or 0 for r in grupo) / n if n else None,
                    avg_latencia_ms=sum(latencias) / len(latencias) if latencias else None,
                    p95_latencia_ms=_percentil(latencias, 95) if latencias else None,
                    pct_scoring_alto=pct(3, "alto"),
                    pct_contra_tese=pct(9),
                    pct_grounding_presente=pct(10),
                    taxa_alucinacao=pct(8),
                    taxa_bloqueio_m1=pct(4),
                    taxa_bloqueio_m2=pct(5),
                    taxa_bloqueio_m3=pct(6),
                    taxa_bloqueio_m4=pct(7),
                )

                cur.execute(
                    """
                    INSERT INTO ai_metrics_daily
                        (data_referencia, prompt_version, model_id, total_interacoes,
                         avg_response_length, avg_latencia_ms, p95_latencia_ms,
                         pct_scoring_alto, pct_contra_tese, pct_grounding_presente,
                         taxa_alucinacao, taxa_bloqueio_m1, taxa_bloqueio_m2,
                         taxa_bloqueio_m3, taxa_bloqueio_m4)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (data_referencia, prompt_version, model_id)
                    DO UPDATE SET
                        total_interacoes    = EXCLUDED.total_interacoes,
                        avg_response_length = EXCLUDED.avg_response_length,
                        avg_latencia_ms     = EXCLUDED.avg_latencia_ms,
                        p95_latencia_ms     = EXCLUDED.p95_latencia_ms,
                        pct_scoring_alto    = EXCLUDED.pct_scoring_alto,
                        pct_contra_tese     = EXCLUDED.pct_contra_tese,
                        pct_grounding_presente = EXCLUDED.pct_grounding_presente,
                        taxa_alucinacao     = EXCLUDED.taxa_alucinacao,
                        taxa_bloqueio_m1    = EXCLUDED.taxa_bloqueio_m1,
                        taxa_bloqueio_m2    = EXCLUDED.taxa_bloqueio_m2,
                        taxa_bloqueio_m3    = EXCLUDED.taxa_bloqueio_m3,
                        taxa_bloqueio_m4    = EXCLUDED.taxa_bloqueio_m4,
                        created_at          = NOW()
                    """,
                    (data, pv, mid, n,
                     metrics.avg_response_length, metrics.avg_latencia_ms,
                     metrics.p95_latencia_ms, metrics.pct_scoring_alto,
                     metrics.pct_contra_tese, metrics.pct_grounding_presente,
                     metrics.taxa_alucinacao, metrics.taxa_bloqueio_m1,
                     metrics.taxa_bloqueio_m2, metrics.taxa_bloqueio_m3,
                     metrics.taxa_bloqueio_m4),
                )
                last_metrics = metrics

            conn.commit()
            cur.close()
            conn.close()
            logger.info("Métricas diárias agregadas para %s: %d grupos", data, len(grupos))
            return last_metrics

        except Exception as e:
            logger.error("MetricsCollector.agregar_diario falhou: %s", e, exc_info=True)
            return None

    def calcular_taxa_alucinacao(
        self,
        data_inicio: date,
        data_fim: date,
    ) -> float:
        """
        Proxy: % interações com bloqueado=TRUE no período.
        [Inferência] — métrica aproximada; avaliação real exige especialista.
        """
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE bloqueado = TRUE) AS bloqueados,
                    COUNT(*) AS total
                FROM ai_interactions
                WHERE DATE(created_at) BETWEEN %s AND %s
                """,
                (data_inicio, data_fim),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            if not row or row[1] == 0:
                return 0.0
            return row[0] / row[1]
        except Exception as e:
            logger.error("calcular_taxa_alucinacao falhou: %s", e)
            return 0.0
