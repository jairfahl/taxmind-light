"""
observability/regression.py — RegressionRunner.

Executa dataset de avaliação contra o CognitiveEngine e verifica se
métricas de qualidade estão dentro dos thresholds definidos.

ATENÇÃO: RegressionRunner faz chamadas reais ao CognitiveEngine.
Testar apenas em tests/e2e/ ou manualmente. Nunca mockar em tests/unit/.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DATASET_AVALIACAO = [
    {
        "query": "Qual a alíquota padrão do IBS para serviços conforme LC 214/2025?",
        "artigos_esperados": ["214"],
        "resposta_referencia": "A LC 214/2025 estabelece alíquota de referência definida pelo Comitê Gestor",
        "deve_ter_grounding": True,
        "deve_ter_contra_tese": False,
    },
    {
        "query": "Como funciona o período de transição do IBS entre 2026 e 2032?",
        "artigos_esperados": ["214", "132"],
        "resposta_referencia": "Transição gradual com redução progressiva de ICMS/ISS conforme EC 132/2023",
        "deve_ter_grounding": True,
        "deve_ter_contra_tese": False,
    },
    {
        "query": "Qual o tratamento da CBS para operações de exportação?",
        "artigos_esperados": ["214"],
        "resposta_referencia": "Exportações são imunes à CBS conforme princípio do destino",
        "deve_ter_grounding": True,
        "deve_ter_contra_tese": False,
    },
    {
        "query": "Existe diferença de alíquota de IBS para serviços de saúde?",
        "artigos_esperados": ["214"],
        "resposta_referencia": "Serviços de saúde têm redução de 60% conforme Art. 138 LC 214/2025",
        "deve_ter_grounding": True,
        "deve_ter_contra_tese": True,
    },
    {
        "query": "O que é o Imposto Seletivo e quais bens são tributados?",
        "artigos_esperados": ["132", "214"],
        "resposta_referencia": "IS incide sobre bens e serviços prejudiciais à saúde e ao meio ambiente",
        "deve_ter_grounding": True,
        "deve_ter_contra_tese": False,
    },
]

THRESHOLDS_REGRESSAO = {
    "precisao_citacao":      0.90,
    "taxa_alucinacao":       0.05,
    "acuracia_recomendacao": 0.80,
    "latencia_p95":          15.0,
    "cobertura_contra_tese": 0.80,
}


@dataclass
class RegressionResult:
    aprovado: bool
    precisao_citacao: float
    taxa_alucinacao: float
    acuracia_recomendacao: float
    latencia_p95: float
    cobertura_contra_tese: float
    detalhes: dict = field(default_factory=dict)


def _get_conn() -> psycopg2.extensions.connection:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL não definida")
    return psycopg2.connect(url)


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    sorted_v = sorted(valores)
    idx = (p / 100) * (len(sorted_v) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_v) - 1)
    frac = idx - lo
    return sorted_v[lo] + frac * (sorted_v[hi] - sorted_v[lo])


def _citar_norma(fundamento_legal: list[str], artigos_esperados: list[str]) -> bool:
    """Verifica se pelo menos uma norma esperada é citada no fundamento legal."""
    if not fundamento_legal:
        return False
    fl_str = " ".join(str(a) for a in fundamento_legal).lower()
    return any(art.lower() in fl_str for art in artigos_esperados)


class RegressionRunner:

    def executar(
        self,
        prompt_version: str,
        model_id: str,
        baseline_version: str,
    ) -> RegressionResult:
        """
        Executa DATASET_AVALIACAO contra CognitiveEngine.
        Calcula métricas e persiste em regression_results.
        """
        from src.cognitive.engine import analisar

        casos_citacao_ok = 0
        casos_alucinacao = 0
        casos_grounding_ok = 0
        casos_contra_tese_ok = 0
        casos_contra_tese_esperada = 0
        latencias: list[float] = []
        detalhes_casos: list[dict] = []

        for caso in DATASET_AVALIACAO:
            t0 = time.time()
            try:
                resultado = analisar(query=caso["query"], top_k=3, model=model_id)
                latencia = (time.time() - t0) * 1000

                citou = _citar_norma(resultado.fundamento_legal or [], caso["artigos_esperados"])
                alucinacao = resultado.anti_alucinacao.bloqueado or bool(resultado.anti_alucinacao.flags)
                grounding = bool(resultado.fundamento_legal)
                contra_tese = resultado.contra_tese is not None

                if citou:
                    casos_citacao_ok += 1
                if alucinacao:
                    casos_alucinacao += 1
                if caso["deve_ter_grounding"] and grounding:
                    casos_grounding_ok += 1
                if caso["deve_ter_contra_tese"]:
                    casos_contra_tese_esperada += 1
                    if contra_tese:
                        casos_contra_tese_ok += 1

                latencias.append(latencia)
                detalhes_casos.append({
                    "query": caso["query"][:60],
                    "citou_norma": citou,
                    "alucinacao": alucinacao,
                    "grounding": grounding,
                    "contra_tese": contra_tese,
                    "latencia_ms": round(latencia),
                })
                logger.info("Regression caso OK: '%s' citou=%s latência=%dms",
                            caso["query"][:50], citou, latencia)

            except Exception as e:
                logger.error("Regression caso falhou: %s — %s", caso["query"][:50], e)
                latencias.append(30_000)  # penalidade de timeout
                detalhes_casos.append({"query": caso["query"][:60], "erro": str(e)})

        n = len(DATASET_AVALIACAO)
        n_grounding_esperado = sum(1 for c in DATASET_AVALIACAO if c["deve_ter_grounding"])

        precisao_citacao = casos_citacao_ok / n if n else 0.0
        taxa_alucinacao = casos_alucinacao / n if n else 0.0
        acuracia_recomendacao = casos_grounding_ok / n_grounding_esperado if n_grounding_esperado else 0.0
        latencia_p95 = _percentil(latencias, 95) / 1000  # em segundos
        cobertura_contra_tese = (
            casos_contra_tese_ok / casos_contra_tese_esperada
            if casos_contra_tese_esperada > 0 else 1.0
        )

        aprovado = (
            precisao_citacao      >= THRESHOLDS_REGRESSAO["precisao_citacao"] and
            taxa_alucinacao       <= THRESHOLDS_REGRESSAO["taxa_alucinacao"] and
            acuracia_recomendacao >= THRESHOLDS_REGRESSAO["acuracia_recomendacao"] and
            latencia_p95          <= THRESHOLDS_REGRESSAO["latencia_p95"] and
            cobertura_contra_tese >= THRESHOLDS_REGRESSAO["cobertura_contra_tese"]
        )

        resultado_reg = RegressionResult(
            aprovado=aprovado,
            precisao_citacao=precisao_citacao,
            taxa_alucinacao=taxa_alucinacao,
            acuracia_recomendacao=acuracia_recomendacao,
            latencia_p95=latencia_p95,
            cobertura_contra_tese=cobertura_contra_tese,
            detalhes={"casos": detalhes_casos, "thresholds": THRESHOLDS_REGRESSAO},
        )

        # Persistir
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO regression_results
                    (prompt_version, model_id, baseline_version, precisao_citacao,
                     taxa_alucinacao, acuracia_recomendacao, latencia_p95,
                     cobertura_contra_tese, aprovado, detalhes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (prompt_version, model_id, baseline_version,
                 precisao_citacao, taxa_alucinacao, acuracia_recomendacao,
                 latencia_p95, cobertura_contra_tese, aprovado,
                 json.dumps(resultado_reg.detalhes, ensure_ascii=False)),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error("Falha ao persistir regression_result: %s", e)

        status = "APROVADO" if aprovado else "REPROVADO"
        logger.info(
            "Regression %s: precisao=%.2f aluc=%.2f grounding=%.2f p95=%.1fs",
            status, precisao_citacao, taxa_alucinacao, acuracia_recomendacao, latencia_p95,
        )
        return resultado_reg
