"""
cognitive/reflection.py — ReflectionLoop: auto-avaliação iterativa de recomendações.

Gera uma recomendação via CognitiveEngine, depois submete a uma Crítica LLM
que avalia 4 dimensões. Se reprovada, re-gera com feedback. Max 2 iterações.

Inspirado em: Reflection Agent (LangGraph), Self Evaluation Loop (CrewAI).
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from dotenv import load_dotenv

from src.cognitive.engine import AnaliseResult

load_dotenv()
logger = logging.getLogger(__name__)

MODEL_DEV = os.getenv("MODEL_DEV", "claude-haiku-4-5-20251001")
MAX_ITERACOES = 2

_PROMPT_CRITICA = """\
Você é um revisor sênior de análises tributárias. Avalie a recomendação abaixo \
em relação à consulta e aos trechos legislativos fornecidos.

CONSULTA ORIGINAL:
{query}

TRECHOS LEGISLATIVOS USADOS:
{contexto_chunks}

RECOMENDAÇÃO GERADA:
{recomendacao}

FUNDAMENTO LEGAL CITADO:
{fundamento_legal}

SCORING CONFIANÇA: {scoring_confianca}
GRAU CONSOLIDAÇÃO: {grau_consolidacao}

Avalie a recomendação em 4 dimensões:
1. GROUNDING LEGAL: A fundamentação legal citada está presente nos trechos recuperados?
2. AÇÃO CONCRETA: A recomendação propõe uma ação executável pela empresa?
3. CONSISTÊNCIA DE SCORING: O nível de confiança é compatível com a evidência?
4. RISCOS/CONTRA-TESE: Riscos ou interpretações divergentes foram endereçados?

Retorne EXCLUSIVAMENTE um JSON válido:
{{
  "aprovado": true|false,
  "dimensoes": {{
    "grounding_legal": {{"ok": true|false, "critica": "..."}},
    "acao_concreta": {{"ok": true|false, "critica": "..."}},
    "consistencia_scoring": {{"ok": true|false, "critica": "..."}},
    "riscos_contra_tese": {{"ok": true|false, "critica": "..."}}
  }},
  "sugestoes": ["lista de melhorias específicas, se reprovado"]
}}

Aprove (aprovado=true) se pelo menos 3 de 4 dimensões estiverem ok.
Responda SOMENTE com o JSON."""


@dataclass
class CriticaResult:
    """Resultado de uma avaliação de crítica."""
    aprovado: bool
    dimensoes: dict
    sugestoes: list[str]


@dataclass
class ReflectionResult:
    """Resultado do loop de reflexão."""
    analise_final: AnaliseResult
    iteracoes: int
    criticas: list[CriticaResult] = field(default_factory=list)
    disclaimer_reflexao: Optional[str] = None


class ReflectionLoop:

    def __init__(self, model: str = MODEL_DEV, max_iteracoes: int = MAX_ITERACOES):
        self._model = model
        self._max_iteracoes = max_iteracoes
        self._client: Optional[anthropic.Anthropic] = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key or key == "<PREENCHER>":
                raise EnvironmentError("ANTHROPIC_API_KEY não configurada")
            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def _formatar_chunks(self, analise: AnaliseResult) -> str:
        if not analise.chunks:
            return "(nenhum trecho disponível)"
        partes = []
        for i, c in enumerate(analise.chunks, 1):
            artigo = c.artigo or "artigo não identificado"
            partes.append(f"[{i}] {c.norma_codigo} | {artigo}\n{c.texto[:400]}")
        return "\n\n".join(partes)

    def _criticar(self, analise: AnaliseResult, trace=None) -> CriticaResult:
        """Submete a recomendação a uma crítica LLM."""
        client = self._get_client()
        prompt = _PROMPT_CRITICA.format(
            query=analise.query,
            contexto_chunks=self._formatar_chunks(analise),
            recomendacao=analise.resposta,
            fundamento_legal=json.dumps(analise.fundamento_legal, ensure_ascii=False),
            scoring_confianca=analise.scoring_confianca,
            grau_consolidacao=analise.grau_consolidacao,
        )

        from src.resilience.backoff import resilient_call, ANTHROPIC_REFLECTION_CONFIG
        resp = resilient_call(
            client.messages.create,
            model=self._model,
            max_tokens=512,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
            config=ANTHROPIC_REFLECTION_CONFIG,
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            dados = json.loads(raw)
            return CriticaResult(
                aprovado=dados.get("aprovado", True),
                dimensoes=dados.get("dimensoes", {}),
                sugestoes=dados.get("sugestoes", []),
            )
        except json.JSONDecodeError:
            logger.warning("Reflection: falha ao parsear crítica — aprovando por default")
            return CriticaResult(aprovado=True, dimensoes={}, sugestoes=[])

    def refletir(
        self,
        analise_inicial: AnaliseResult,
        re_analisar_fn=None,
    ) -> ReflectionResult:
        """
        Executa loop de reflexão sobre uma análise.

        Args:
            analise_inicial: AnaliseResult da primeira geração.
            re_analisar_fn: Função para re-gerar a análise com feedback.
                            Assinatura: re_analisar_fn(query: str, instrucao_extra: str) -> AnaliseResult
                            Se None, retorna a análise inicial sem loop.

        Returns:
            ReflectionResult com a melhor análise e histórico de críticas.
        """
        if analise_inicial.anti_alucinacao.bloqueado:
            return ReflectionResult(
                analise_final=analise_inicial,
                iteracoes=0,
                disclaimer_reflexao="Reflexão não aplicada: análise bloqueada por anti-alucinação.",
            )

        melhor_analise = analise_inicial
        criticas: list[CriticaResult] = []

        for iteracao in range(self._max_iteracoes):
            try:
                critica = self._criticar(melhor_analise)
                criticas.append(critica)

                if critica.aprovado:
                    logger.info("Reflection: aprovada na iteração %d", iteracao + 1)
                    return ReflectionResult(
                        analise_final=melhor_analise,
                        iteracoes=iteracao + 1,
                        criticas=criticas,
                    )

                # Não aprovada — tentar re-gerar se temos a função
                if re_analisar_fn is None:
                    logger.info("Reflection: reprovada mas sem re_analisar_fn — retornando com disclaimer")
                    break

                # Montar instrução com feedback das críticas
                instrucao = self._montar_instrucao_feedback(critica)
                logger.info("Reflection: re-gerando com feedback (iteração %d)", iteracao + 1)

                nova_analise = re_analisar_fn(
                    query=melhor_analise.query,
                    instrucao_extra=instrucao,
                )
                if not nova_analise.anti_alucinacao.bloqueado:
                    melhor_analise = nova_analise

            except Exception as e:
                logger.warning("Reflection: erro na iteração %d (%s) — encerrando loop", iteracao + 1, e)
                break

        # Chegou aqui = não foi aprovada após todas as iterações
        return ReflectionResult(
            analise_final=melhor_analise,
            iteracoes=len(criticas),
            criticas=criticas,
            disclaimer_reflexao=(
                "Recomendação gerada com ressalvas após revisão automática. "
                "Sugestões de melhoria: " + "; ".join(criticas[-1].sugestoes)
                if criticas and criticas[-1].sugestoes
                else "Recomendação gerada com ressalvas após revisão automática."
            ),
        )

    def _montar_instrucao_feedback(self, critica: CriticaResult) -> str:
        """Monta instrução de feedback para re-geração."""
        partes = ["\n\nFEEDBACK DO REVISOR — corrija os seguintes pontos:"]
        for dim, info in critica.dimensoes.items():
            if isinstance(info, dict) and not info.get("ok", True):
                partes.append(f"- {dim}: {info.get('critica', '')}")
        if critica.sugestoes:
            partes.append("\nSugestões específicas:")
            for s in critica.sugestoes:
                partes.append(f"- {s}")
        return "\n".join(partes)
