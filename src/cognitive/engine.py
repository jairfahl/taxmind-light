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
from src.rag.adaptive import classificar_query, obter_params_adaptativos
from src.rag.corrector import CorrectorRAG
from src.rag.decomposer import QueryDecomposer
from src.rag.retriever import ChunkResultado, retrieve
from src.rag.spd import (
    SPDRoutingDecision,
    SPDStrategy,
    decidir_estrategia,
    listar_normas_ativas,
    spd_retrieve,
)

load_dotenv()

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1.0.0-sprint2"
MODEL_DEV = "claude-haiku-4-5-20251001"
MODEL_PROD = "claude-sonnet-4-6"

SYSTEM_PROMPT = """Você é um especialista em tributação da Reforma Tributária
brasileira (EC 132/2023, LC 214/2025, LC 227/2026), com foco em impacto
operacional e financeiro para empresas.

Seu papel é responder consultas de profissionais das áreas fiscal, contábil
e financeira — não de advogados. Use linguagem direta, objetiva e orientada
a negócios.

REGRAS DE RESPOSTA:
1. Comece sempre pelo impacto prático para a empresa (financeiro, operacional
   ou de compliance).
2. Apresente a base legal como suporte à conclusão — não como ponto de
   partida.
3. Substitua jargão jurídico por termos do mundo corporativo:
   - "dispositivo legal" → "regra"
   - "hermenêutica" → "interpretação"
   - "posição doutrinária" → "entendimento de mercado"
   - "contribuinte" → "empresa" ou "seu negócio"
   - "fato gerador" → "momento em que o imposto incide"
4. Quando o tema for controverso, apresente os dois lados em termos de
   risco financeiro e de compliance — não de tese jurídica.
5. Nunca invente artigos ou alíquotas. Se não houver base legal nos trechos
   recuperados, declare explicitamente: "Não há base legal suficiente na
   base de conhecimento para responder com segurança."
6. Encerre sempre com uma linha de ação clara para a empresa.

ESTILO DO CAMPO "resposta":
- Máximo 4 frases. Direto ao ponto.
- Primeira frase: impacto concreto para a empresa (financeiro ou operacional).
- Segunda frase: o que muda na prática (alíquota, regime, obrigação).
- Terceira frase (opcional): risco ou atenção específica.
- Quarta frase: ação recomendada.
- Referências legais (artigos, parágrafos) devem aparecer APENAS no campo
  "fundamento_legal" — nunca intercaladas no corpo da "resposta".
- Proibido: enumerações "(1), (2), (3)", linguagem passiva, parênteses
  explicativos longos, citações literais de artigos no corpo da resposta.
- NUNCA usar notação LaTeX, MathJax ou símbolos como $, \\(, \\), \\[, \\].
  Escrever valores monetários por extenso: "R$ 100 mil", "R$ 1,2 milhão".
  Escrever fórmulas em texto corrido, sem formatação matemática.

EXEMPLO DE RESPOSTA BEM FORMATADA:
"A partir de 2026, sua empresa passa a recolher CBS no lugar do PIS/COFINS,
com alíquota de 0,9% na fase de transição. Para produtos da cesta básica,
a LC 214/2025 prevê redução de alíquota, mas o percentual exato depende de
regulamentação do Comitê Gestor ainda pendente. O risco é planejar com
alíquota cheia e ser surpreendido por regra diferenciada. Recomendamos mapear
o mix de produtos por código NCM e acompanhar as publicações do Comitê Gestor."

EXEMPLO PROIBIDO:
"Com base nos trechos fornecidos, é possível afirmar que: (1) A partir de
1º de janeiro de 2027, o IBS será cobrado à alíquota de 0,05%... (2) O
Art. 344, parágrafo único, inciso I, prevê que... Conclusão: O impacto
exato não pode ser quantificado..."

FORMATO DE RESPOSTA (JSON estrito):
{
  "resposta": "string — resposta principal em linguagem de negócios",
  "impacto_financeiro": "string — estimativa de impacto em termos de custo,
                         carga tributária ou fluxo de caixa",
  "fundamento_legal": ["lista de artigos e normas que suportam a resposta"],
  "posicao_mercado": "consolidado | em_disputa | sem_precedente",
  "nivel_confianca": float entre 0 e 1,
  "posicao_contraria": "string ou null — risco alternativo se tema em disputa",
  "acao_recomendada": "string — próximo passo concreto para a empresa"
}"""

COT_INSTRUCTION = """
Antes de responder, raciocine passo a passo:
1. Qual é o impacto direto para a empresa?
2. Qual regra da Reforma Tributária se aplica?
3. Existe risco de interpretação divergente?
4. Qual é a ação concreta recomendada?
"""


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
    retrieval_strategy: str = "standard"


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
        max_tokens=4096,
        temperature=temperatura,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    # Registrar consumo de tokens
    try:
        from src.observability.usage import registrar_uso
        registrar_uso(
            service="anthropic",
            model=model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
    except Exception as _usage_err:
        logger.debug("Registro de uso ignorado: %s", _usage_err)

    raw = resp.content[0].text.strip()
    # Remover possível markdown ```json ... ```
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON malformado. raw=%s... erro=%s", raw[:200], e)
        raise RuntimeError(
            f"LLM retornou JSON inválido (provável truncamento). "
            f"Posição: {e.pos}. Aumentar max_tokens se recorrente."
        ) from e


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
    retrieval_strategy: str = "standard",
) -> None:
    """Registra em ai_interactions."""
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ai_interactions (
                query_texto, chunks_ids, qualidade_status, scoring_confianca,
                grau_consolidacao, m1_existencia, m2_validade, m3_pertinencia,
                m4_consistencia, bloqueado, prompt_version, model_id, latencia_ms,
                retrieval_strategy
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                retrieval_strategy,
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
    decompose: bool = False,
) -> AnaliseResult:
    """
    Pipeline completo de análise tributária P1→P4.

    P1: Retrieve (RAG) — com adaptive params e decomposição opcional
    P2: Quality gate (semáforo)
    P3: LLM + CoT + anti-alucinação
    P4: Retorno estruturado
    """
    t0 = time.time()
    conn = _get_db_conn()

    # P1 — Retrieve (com parâmetros adaptativos)
    _excluir = excluir_tipos if excluir_tipos is not None else ["Outro"]
    params = obter_params_adaptativos(query, top_k_base=top_k, rerank_top_n_base=rerank_top_n)
    if params.forcar_multi_norma and norma_filter:
        norma_filter = None  # força busca em todas as normas para queries comparativas

    # SPD routing — decidir estratégia antes do retrieve
    try:
        normas_ativas = listar_normas_ativas()
    except Exception as e:
        logger.warning("listar_normas_ativas falhou, fallback standard: %s", e)
        normas_ativas = []

    query_tipo = classificar_query(query)
    decisao = decidir_estrategia(
        query_tipo=query_tipo.value,
        norma_filter=norma_filter,
        num_normas=len(normas_ativas),
    )
    logger.info("SPD routing: strategy=%s reason=%s", decisao.strategy.value, decisao.reason)

    def _do_retrieve(q: str) -> list[ChunkResultado]:
        return retrieve(q, top_k=params.top_k, rerank_top_n=params.rerank_top_n,
                        norma_filter=norma_filter, excluir_tipos=_excluir,
                        cosine_weight=params.cosine_weight, bm25_weight=params.bm25_weight)

    if decisao.strategy == SPDStrategy.SPD:
        # SPD: retrieval per-document
        spd_result = spd_retrieve(
            query=query,
            normas=normas_ativas,
            top_k_por_norma=max(3, params.top_k // len(normas_ativas) + 1),
            rerank_top_n=params.rerank_top_n,
            excluir_tipos=_excluir,
            cosine_weight=params.cosine_weight,
            bm25_weight=params.bm25_weight,
        )
        chunks = spd_result.chunks_merged[:params.top_k]
    elif decompose:
        # Sub-question decomposition (opt-in)
        try:
            decomposer = QueryDecomposer(model=model)
            decomp_result = decomposer.decompor_e_recuperar(query, retrieve_fn=_do_retrieve)
            chunks = decomp_result.chunks_merged
        except Exception as e:
            logger.warning("Decomposer ignorado: %s", e)
            chunks = _do_retrieve(query)
    else:
        chunks = _do_retrieve(query)

    # P1.5 — Corrective RAG: filtrar chunks irrelevantes antes do quality gate
    try:
        corrector = CorrectorRAG(model=model)
        crag_result = corrector.corrigir(query, chunks, retrieve_fn=_do_retrieve)
        chunks = crag_result.chunks_filtrados
    except Exception as e:
        logger.warning("CRAG ignorado: %s", e)

    # P2 — Quality Gate
    qualidade = avaliar_qualidade(query, chunks)

    # RS-02 reactive fallback: se fonte unica detectada, retry com SPD
    if (decisao.strategy == SPDStrategy.STANDARD
            and "RS-02" in qualidade.ressalvas
            and len(normas_ativas) >= 2):
        logger.info("RS-02 detectado — retry com SPD-RAG")
        try:
            spd_result = spd_retrieve(
                query=query,
                normas=normas_ativas,
                top_k_por_norma=3,
                rerank_top_n=params.rerank_top_n,
                excluir_tipos=_excluir,
                cosine_weight=params.cosine_weight,
                bm25_weight=params.bm25_weight,
            )
            if len({c.norma_codigo for c in spd_result.chunks_merged}) > 1:
                chunks = spd_result.chunks_merged[:params.top_k]
                qualidade = avaliar_qualidade(query, chunks)
                decisao = SPDRoutingDecision(SPDStrategy.SPD_REACTIVE, "RS-02 fallback")
                logger.info("SPD reactive: cobertura multi-norma restaurada")
        except Exception as e:
            logger.warning("SPD reactive fallback falhou: %s", e)

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
            retrieval_strategy=decisao.strategy.value,
        )
        _registrar_interacao(conn, query, chunks, qualidade, anti, {}, model, latencia_ms,
                            retrieval_strategy=decisao.strategy.value)
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
        retrieval_strategy=decisao.strategy.value,
    )

    _registrar_interacao(conn, query, chunks, qualidade, anti, dados, model, latencia_ms,
                        retrieval_strategy=decisao.strategy.value)
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
