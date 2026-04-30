"""
src/security/prompt_sanitizer.py — Defesa contra prompt injection (OWASP LLM01).

Primeira camada: regex blacklist com normalização Unicode (NFKC).
Entradas tributárias legítimas NÃO são afetadas pelos padrões.
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Padrões de prompt injection. Aplicados após normalização NFKC.
# Regex em lowercase — a comparação é feita com texto em minúsculas.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(previous|above|all|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(previous|above|all|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"forget\s+(previous|above|all|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"\bsystem\s*prompt\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\b.{0,30}\b(assistant|ai|bot|gpt|claude|llm)\b", re.IGNORECASE),
    re.compile(r"\bpretend\s+(to\s+be|you\s+are)\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bDAN\b"),  # "Do Anything Now" jailbreak
    re.compile(r"<\s*/?system\s*>", re.IGNORECASE),  # XML system tags
    re.compile(r"\[\s*INST\s*\]", re.IGNORECASE),     # Llama instruction tags
]

_MAX_INPUT_LENGTH = 8_000  # chars — inputs tributários legítimos não excedem isso


class PromptInjectionError(ValueError):
    """Levantado quando input suspeito de prompt injection é detectado."""
    pass


def sanitize(text: str, field_name: str = "input") -> str:
    """
    Valida que o texto não contém padrões de prompt injection.

    - Normaliza Unicode (NFKC) antes da verificação.
    - Trunca inputs excessivamente longos.
    - Registra WARNING para tentativas detectadas.

    Returns:
        O texto original sem modificação (validação only, não altera conteúdo).

    Raises:
        PromptInjectionError: se padrão de injection for detectado.
    """
    if not text or not isinstance(text, str):
        return text

    # Limite de comprimento
    if len(text) > _MAX_INPUT_LENGTH:
        raise PromptInjectionError(
            f"Campo '{field_name}' excede o limite de {_MAX_INPUT_LENGTH} caracteres."
        )

    # Normalização Unicode (NFKC): resolve homoglyphs e variações de encoding
    normalized = unicodedata.normalize("NFKC", text)

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(normalized):
            logger.warning(
                "[SECURITY] POTENTIAL_INJECTION detectado | field=%s | pattern=%s | text_preview=%.80r",
                field_name,
                pattern.pattern,
                text,
            )
            raise PromptInjectionError(
                f"Input inválido no campo '{field_name}'. Tente reformular a consulta."
            )

    return text
