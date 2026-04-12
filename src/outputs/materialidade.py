"""
outputs/materialidade.py — MaterialidadeCalculator.

Score 1–5 calculado via LLM (temperatura 0.0) com base no contexto do caso.
5 = impacto crítico imediato · 1 = informativo, sem urgência.
"""

import json
import logging
import os
import re
from dataclasses import dataclass

import anthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

CRITERIOS_MATERIALIDADE = {
    "valor_financeiro":  {"peso": 3, "descricao": "Impacto financeiro estimado"},
    "risco_regulatorio": {"peso": 3, "descricao": "Risco de autuação / multa"},
    "prazo":             {"peso": 2, "descricao": "Urgência do prazo de adequação"},
    "abrangencia":       {"peso": 2, "descricao": "Número de entidades / operações afetadas"},
}

MODEL_DEV = os.getenv("MODEL_DEV", "claude-haiku-4-5-20251001")

_PROMPT_MATERIALIDADE = """\
Você é um analista tributário sênior avaliando a materialidade de uma decisão fiscal.

Contexto do caso:
{contexto}

Critérios de avaliação (pesos):
- valor_financeiro (peso 3): impacto financeiro estimado
- risco_regulatorio (peso 3): risco de autuação / multa
- prazo (peso 2): urgência do prazo de adequação
- abrangencia (peso 2): número de entidades / operações afetadas

Retorne EXCLUSIVAMENTE um JSON válido no formato:
{{
  "score": <inteiro de 1 a 5>,
  "justificativa": "<texto explicando o score>"
}}

Onde:
5 = impacto crítico imediato (valor alto + prazo urgente + risco alto)
4 = impacto alto, ação necessária em curto prazo
3 = impacto moderado, monitoramento recomendado
2 = impacto baixo, informativo com alguma relevância
1 = informativo, sem urgência

Responda SOMENTE com o JSON, sem texto adicional."""


@dataclass
class MaterialidadeResult:
    score: int
    justificativa: str


def _parse_json_safe(raw: str) -> dict:
    """Extrai JSON do texto do LLM, tolerante a markdown fences e texto extra."""
    # Tenta extrair bloco de código markdown
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    # Tenta extrair primeiro objeto JSON no texto
    obj = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if obj:
        return json.loads(obj.group(0))
    return json.loads(raw)


class MaterialidadeCalculator:

    def __init__(self, model: str = MODEL_DEV):
        self._model = model
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key or key == "<PREENCHER>":
                raise EnvironmentError("ANTHROPIC_API_KEY não configurada")
            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def calcular(self, contexto: dict) -> int:
        """
        Calcula score de materialidade 1-5 usando LLM (temperatura 0.0).
        Retorna o score inteiro.
        """
        contexto_str = json.dumps(contexto, ensure_ascii=False, indent=2)
        prompt = _PROMPT_MATERIALIDADE.format(contexto=contexto_str)

        try:
            client = self._get_client()
            msg = client.messages.create(
                model=self._model,
                max_tokens=512,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            parsed = _parse_json_safe(raw)
            score = max(1, min(5, int(parsed["score"])))
            logger.info("Materialidade calculada: score=%d justificativa=%s",
                        score, parsed.get("justificativa", "")[:80])
            return score
        except Exception as e:
            logger.warning("Falha ao calcular materialidade via LLM (%s) — usando fallback 3", e)
            return 3  # fallback conservador

    def calcular_detalhado(self, contexto: dict) -> MaterialidadeResult:
        """Retorna score + justificativa."""
        contexto_str = json.dumps(contexto, ensure_ascii=False, indent=2)
        prompt = _PROMPT_MATERIALIDADE.format(contexto=contexto_str)

        try:
            client = self._get_client()
            msg = client.messages.create(
                model=self._model,
                max_tokens=512,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            parsed = _parse_json_safe(raw)
            score = max(1, min(5, int(parsed["score"])))
            return MaterialidadeResult(
                score=score,
                justificativa=parsed.get("justificativa", ""),
            )
        except Exception as e:
            logger.warning("Falha ao calcular materialidade detalhada (%s)", e)
            return MaterialidadeResult(score=3, justificativa="Calculado por fallback — LLM indisponível")
