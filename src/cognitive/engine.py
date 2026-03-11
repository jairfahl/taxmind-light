"""
cognitive/engine.py — CognitiveEngine: motor de análise tributária com anti-alucinação.

Pipeline: RAG → QualityEngine → LLM (claude-haiku) → Anti-Alucinação → AnaliseResult
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import anthropic
import psycopg2
from dotenv import load_dotenv

from src.quality.engine import QualidadeResult, QualidadeStatus, avaliar_qualidade
from src.rag.retriever import ChunkResultado, retrieve

load_dotenv()

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1.0.0-sprint2"
MODEL_DEV = "claude-haiku-4-5-20251001"
MODEL_PROD = "claude-sonnet-4-6"

SYSTEM_PROMPT = """Você é um especialista em direito tributário brasileiro, com foco na
Reforma Tributária (EC 132/2023, LC 214/2025, LC 227/2026).

RESTRIÇÕES ABSOLUTAS:
- Nunca afirme nada sem citar o dispositivo legal específico (artigo, parágrafo, inciso e norma).
- Nunca emita parecer jurídico formal.
- Nunca recomende ação sem grounding verificado na legislação fornecida.
- Se os trechos fornecidos forem insuficientes, declare explicitamente.

FORMATO DE RESPOSTA (JSON obrigatório, sem markdown):
{
  "fundamento_legal": ["Art. X da LC 214/2025", ...],
  "grau_consolidacao": "consolidado|divergente|indefinido",
  "contra_tese": "string ou null",
  "scoring_confianca": "alto|medio|baixo",
  "resposta": "análise em linguagem técnica",
  "disclaimer": "string ou null"
}

CRITÉRIOS DE SCORING:
- alto: legislação vigente, sem ambiguidade, jurisprudência consolidada
- medio: legislação vigente, com margem interpretativa ou sem jurisprudência
- baixo: norma recente sem regulamentação, analogia, ou dados insuficientes"""

COT_INSTRUCTION = """
Antes de responder, raciocine passo a passo (chain-of-thought interno):
1. Identifique os dispositivos legais relevantes nos trechos fornecidos
2. Verifique se há conflito entre normas
3. Analise a posição mais conservadora e a mais expansiva
4. Formule a contra-tese antes da tese principal
Após o raciocínio, produza APENAS o JSON de resposta."""


@dataclass
class AntiAlucinacaoResult:
    m1_existencia: bool = True
    m2_validade: bool = True
    m3_pertinencia: bool = True
    m4_consistencia: bool = True
    bloqueado: bool = False
    flags: list[str] = field(default_factory=list)


@dataclass
class AnaliseResult:
    query: str
    chunks: list[ChunkResultado]
    qualidade: QualidadeResult
    fundamento_legal: list[str]
    grau_consolidacao: str
    contra_tese: Optional[str]
    scoring_confianca: str
    resposta: str
    disclaimer: Optional[str]
    anti_alucinacao: AntiAlucinacaoResult
    prompt_version: str
    model_id: str
    latencia_ms: int


_anthropic_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise EnvironmentError("ANTHROPIC_API_KEY não configurada")
        _anthropic_client = anthropic.Anthropic(api_key=key)
    return _anthropic_client


def _get_db_conn() -> psycopg2.extensions.connection:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL não definida")
    return psycopg2.connect(url)


def _precisa_cot(qualidade: QualidadeResult, dados: dict) -> bool:
    """Determina se Chain-of-Thought deve ser ativado."""
    if "RS-05" in qualidade.ressalvas:
        return True
    if dados.get("grau_consolidacao") == "divergente":
        return True
    if dados.get("scoring_confianca") == "baixo":
        return True
    return False


def _montar_contexto(chunks: list[ChunkResultado]) -> str:
    partes = []
    for i, c in enumerate(chunks, 1):
        artigo_label = c.artigo or "artigo não identificado"
        partes.append(
            f"[Trecho {i}] {c.norma_codigo} | {artigo_label} | score={c.score_final:.3f}\n"
            f"{c.texto}"
        )
    return "\n\n".join(partes)


def _chamar_llm(
    query: str,
    contexto: str,
    temperatura: float = 0.1,
    usar_cot: bool = False,
    model: str = MODEL_DEV,
) -> dict:
    """Chama o LLM e retorna o JSON parseado."""
    client = _get_client()
    system = SYSTEM_PROMPT + (COT_INSTRUCTION if usar_cot else "")

    user_msg = (
        f"TRECHOS LEGISLATIVOS RECUPERADOS:\n{contexto}\n\n"
        f"CONSULTA: {query}\n\n"
        "Responda APENAS com o JSON especificado."
    )

    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=temperatura,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = resp.content[0].text.strip()
    # Remover possível markdown ```json ... ```
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    return json.loads(raw)


import re


def _verificar_m1(fundamento_legal: list[str], conn: psycopg2.extensions.connection) -> tuple[bool, list[str]]:
    """M1 — Existência: artigos citados existem na base?"""
    flags = []
    cur = conn.cursor()
    for dispositivo in fundamento_legal:
        # Extrair "Art. X" do texto como "Art. 10." ou "Art. 10"
        match = re.search(r'Art\.\s*\d+[º°]?\.?', dispositivo, re.IGNORECASE)
        if not match:
            continue
        artigo_ref = match.group(0).strip().rstrip(".")
        cur.execute(
            "SELECT 1 FROM chunks WHERE artigo ILIKE %s LIMIT 1",
            (f"%{artigo_ref}%",),
        )
        if not cur.fetchone():
            flags.append(f"M1:FALHA:{dispositivo}")
    cur.close()
    return len(flags) == 0, flags


def _verificar_m2(fundamento_legal: list[str], conn: psycopg2.extensions.connection) -> tuple[bool, list[str]]:
    """M2 — Validade: normas citadas estão vigentes?"""
    flags = []
    normas_mencionadas = []
    for d in fundamento_legal:
        if "EC 132" in d or "EC132" in d:
            normas_mencionadas.append("EC132_2023")
        if "LC 214" in d or "LC214" in d:
            normas_mencionadas.append("LC214_2025")
        if "LC 227" in d or "LC227" in d:
            normas_mencionadas.append("LC227_2026")

    cur = conn.cursor()
    for codigo in set(normas_mencionadas):
        cur.execute("SELECT vigente FROM normas WHERE codigo = %s", (codigo,))
        row = cur.fetchone()
        if row and not row[0]:
            flags.append(f"M2:ALERTA:{codigo}")
    cur.close()
    return True, flags  # M2 não bloqueia, apenas alerta


def _verificar_m3_pertinencia(chunks: list[ChunkResultado]) -> tuple[bool, list[str]]:
    """M3 — Pertinência: score dos chunks (proxy sem re-embedding da resposta)."""
    if not chunks:
        return False, ["M3:BAIXA_PERTINENCIA"]
    max_score = max(c.score_final for c in chunks)
    if max_score < 0.40:
        return False, ["M3:BAIXA_PERTINENCIA"]
    return True, []


def _verificar_m4_consistencia(dados: dict) -> tuple[bool, list[str]]:
    """M4 — Consistência: scoring alto + grau indefinido é incoerente."""
    if dados.get("scoring_confianca") == "alto" and dados.get("grau_consolidacao") == "indefinido":
        return False, ["M4:INCONSISTENCIA"]
    return True, []


def _registrar_interacao(
    conn: psycopg2.extensions.connection,
    query: str,
    chunks: list[ChunkResultado],
    qualidade: QualidadeResult,
    anti: AntiAlucinacaoResult,
    dados: dict,
    model_id: str,
    latencia_ms: int,
) -> None:
    """Registra em ai_interactions."""
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ai_interactions (
                query_texto, chunks_ids, qualidade_status, scoring_confianca,
                grau_consolidacao, m1_existencia, m2_validade, m3_pertinencia,
                m4_consistencia, bloqueado, prompt_version, model_id, latencia_ms
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                query,
                [c.chunk_id for c in chunks],
                qualidade.status.value,
                dados.get("scoring_confianca"),
                dados.get("grau_consolidacao"),
                anti.m1_existencia,
                anti.m2_validade,
                anti.m3_pertinencia,
                anti.m4_consistencia,
                anti.bloqueado,
                PROMPT_VERSION,
                model_id,
                latencia_ms,
            ),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        logger.warning("Falha ao registrar interação: %s", e)


def analisar(
    query: str,
    top_k: int = 3,
    rerank_top_n: int = 10,
    norma_filter: Optional[list[str]] = None,
    excluir_tipos: Optional[list[str]] = None,
    model: str = MODEL_DEV,
) -> AnaliseResult:
    """
    Pipeline completo de análise tributária P1→P4.

    P1: Retrieve (RAG)
    P2: Quality gate (semáforo)
    P3: LLM + CoT + anti-alucinação
    P4: Retorno estruturado
    """
    t0 = time.time()
    conn = _get_db_conn()

    # P1 — Retrieve
    _excluir = excluir_tipos if excluir_tipos is not None else ["Outro"]
    chunks = retrieve(query, top_k=top_k, rerank_top_n=rerank_top_n, norma_filter=norma_filter, excluir_tipos=_excluir)

    # P2 — Quality Gate
    qualidade = avaliar_qualidade(query, chunks)

    if qualidade.status == QualidadeStatus.VERMELHO:
        latencia_ms = int((time.time() - t0) * 1000)
        anti = AntiAlucinacaoResult(bloqueado=True, flags=["BLOQUEADO_POR_QUALIDADE"] + qualidade.bloqueios)
        resultado = AnaliseResult(
            query=query,
            chunks=chunks,
            qualidade=qualidade,
            fundamento_legal=[],
            grau_consolidacao="indefinido",
            contra_tese=None,
            scoring_confianca="baixo",
            resposta=f"Consulta bloqueada: {'; '.join(qualidade.bloqueios)}",
            disclaimer=None,
            anti_alucinacao=anti,
            prompt_version=PROMPT_VERSION,
            model_id=model,
            latencia_ms=latencia_ms,
        )
        _registrar_interacao(conn, query, chunks, qualidade, anti, {}, model, latencia_ms)
        conn.close()
        return resultado

    # P3 — LLM
    contexto = _montar_contexto(chunks)

    # Determinar temperatura baseada em contexto inicial
    temperatura = 0.1  # análise interpretativa por padrão

    # Primeira chamada
    dados = _chamar_llm(query, contexto, temperatura=temperatura, usar_cot=False, model=model)

    # Ativar CoT se necessário e re-chamar
    if _precisa_cot(qualidade, dados):
        logger.info("Ativando Chain-of-Thought para query: %s", query[:60])
        dados = _chamar_llm(query, contexto, temperatura=0.3, usar_cot=True, model=model)

    # P4 — Anti-alucinação
    anti = AntiAlucinacaoResult()
    all_flags: list[str] = []

    m1_ok, m1_flags = _verificar_m1(dados.get("fundamento_legal", []), conn)
    anti.m1_existencia = m1_ok
    all_flags.extend(m1_flags)

    m2_ok, m2_flags = _verificar_m2(dados.get("fundamento_legal", []), conn)
    anti.m2_validade = m2_ok
    all_flags.extend(m2_flags)

    m3_ok, m3_flags = _verificar_m3_pertinencia(chunks)
    anti.m3_pertinencia = m3_ok
    all_flags.extend(m3_flags)

    m4_ok, m4_flags = _verificar_m4_consistencia(dados)
    if not m4_ok:
        logger.info("M4 inconsistência detectada — reprocessando com instrução corretiva")
        instrucao_corretiva = (
            "\n\nAVISO: scoring_confianca='alto' e grau_consolidacao='indefinido' são incompatíveis. "
            "Ajuste para scoring='medio' ou grau='consolidado'/'divergente' conforme a evidência."
        )
        dados_corrigido = _chamar_llm(
            query, contexto + instrucao_corretiva,
            temperatura=0.0, usar_cot=False, model=model
        )
        m4_ok2, m4_flags2 = _verificar_m4_consistencia(dados_corrigido)
        if m4_ok2:
            dados = dados_corrigido
            m4_flags = []
        else:
            m4_flags = ["M4:INCONSISTENCIA"]
            anti.bloqueado = True
    anti.m4_consistencia = m4_ok or (not anti.bloqueado)
    all_flags.extend(m4_flags)

    # M1 bloqueia a resposta
    if not m1_ok:
        anti.bloqueado = True

    anti.flags = all_flags

    # Disclaimer final: combinar qualidade + M2
    disclaimer = dados.get("disclaimer")
    if qualidade.disclaimer:
        disclaimer = (f"{qualidade.disclaimer} | {disclaimer}" if disclaimer else qualidade.disclaimer)
    for flag in m2_flags:
        norma = flag.split(":")[-1]
        aviso = f"Atenção: {norma} pode não estar vigente."
        disclaimer = f"{disclaimer} | {aviso}" if disclaimer else aviso

    latencia_ms = int((time.time() - t0) * 1000)

    if anti.bloqueado:
        resposta = f"Resposta bloqueada por anti-alucinação: {'; '.join(all_flags)}"
    else:
        resposta = dados.get("resposta", "")

    resultado = AnaliseResult(
        query=query,
        chunks=chunks,
        qualidade=qualidade,
        fundamento_legal=dados.get("fundamento_legal", []),
        grau_consolidacao=dados.get("grau_consolidacao", "indefinido"),
        contra_tese=dados.get("contra_tese"),
        scoring_confianca=dados.get("scoring_confianca", "baixo"),
        resposta=resposta,
        disclaimer=disclaimer,
        anti_alucinacao=anti,
        prompt_version=PROMPT_VERSION,
        model_id=model,
        latencia_ms=latencia_ms,
    )

    _registrar_interacao(conn, query, chunks, qualidade, anti, dados, model, latencia_ms)
    conn.close()
    logger.info("Análise concluída: status=%s score=%s latência=%dms flags=%s",
                qualidade.status, dados.get("scoring_confianca"), latencia_ms, all_flags)

    # Observability — não propaga exceções
    try:
        from src.observability.collector import MetricsCollector
        MetricsCollector().registrar_interacao(resultado, query)
    except Exception as _obs_err:
        logger.debug("MetricsCollector ignorado: %s", _obs_err)

    return resultado
