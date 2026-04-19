"""
src/cognitive/detector_carimbo.py — Detector de Carimbo léxico (SequenceMatcher).

DC v7 — Mecanismos Anti-Terceirização Cognitiva:
"Se a decisão replica a IA (>70% sobreposição), o sistema questiona:
'Você considerou alternativas?' O gestor pode confirmar —
mas o incômodo deliberado quebra o automatismo."

Implementação: difflib.SequenceMatcher (stdlib) — zero dependências externas.
Threshold: 0.70 (70% de sobreposição de sequência de caracteres normalizados).

Complemento ao src/protocol/carimbo.py (que usa Voyage embeddings + cosseno).
Este módulo é o check pré-save na UI e fallback quando Voyage não está disponível.
"""

import re
from difflib import SequenceMatcher

THRESHOLD_CARIMBO = 0.70  # 70% de sobreposição = alerta


def _normalizar(texto: str) -> str:
    """Normaliza texto para comparação: minúsculas, sem pontuação, espaços únicos."""
    texto = texto.lower().strip()
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def calcular_similaridade(texto_gestor: str, texto_ia: str) -> float:
    """
    Calcula similaridade léxica entre decisão do gestor e recomendação da IA.

    Usa SequenceMatcher (stdlib) — não requer API externa.

    Returns:
        float entre 0.0 (nenhuma sobreposição) e 1.0 (idênticos).
    """
    if not texto_gestor or not texto_ia:
        return 0.0

    a = _normalizar(texto_gestor)
    b = _normalizar(texto_ia)

    return SequenceMatcher(None, a, b).ratio()


def detectar_carimbo(decisao_gestor: str, recomendacao_ia: str) -> dict:
    """
    Verifica se a decisão do gestor é um 'carimbo' da recomendação da IA.

    Args:
        decisao_gestor: texto da decisão registrada pelo gestor no P5.
        recomendacao_ia: texto da recomendação gerada pela IA no P3.

    Returns:
        dict com:
          - similaridade: float (0.0 a 1.0)
          - carimbo_detectado: bool (True se similaridade >= THRESHOLD_CARIMBO)
          - mensagem: str (mensagem a exibir se carimbo detectado, '' caso contrário)
    """
    similaridade = calcular_similaridade(decisao_gestor, recomendacao_ia)
    carimbo = similaridade >= THRESHOLD_CARIMBO

    if carimbo:
        mensagem = (
            f"**Detector de Carimbo ativado** ({similaridade:.0%} de sobreposição com a IA)\n\n"
            "Sua decisão é muito similar à recomendação do Orbis.tax. "
            "Isso não é necessariamente um problema — mas precisamos garantir "
            "que foi uma escolha consciente.\n\n"
            "**Você considerou alternativas?** Confirme abaixo que esta é sua "
            "posição independente."
        )
    else:
        mensagem = ""

    return {
        "similaridade": round(similaridade, 4),
        "carimbo_detectado": carimbo,
        "mensagem": mensagem,
    }
