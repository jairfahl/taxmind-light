"""
cognitive/engine.py — CognitiveEngine: motor de análise tributária com anti-alucinação.

Pipeline: RAG → QualityEngine → LLM (claude-haiku) → Anti-Alucinação → AnaliseResult
"""

import json
import logging
import os
import re as _re_mod
import time
from dataclasses import dataclass, field, replace
from typing import Literal, Optional

import anthropic
import psycopg2
from dotenv import load_dotenv

from src.db.pool import get_conn, put_conn

from src.quality.engine import QualidadeResult, QualidadeStatus, avaliar_qualidade
from src.rag.adaptive import classificar_query, obter_params_adaptativos
from src.rag.corrector import CorrectorRAG
from src.rag.decomposer import QueryDecomposer
from src.integrity.lockfile_manager import (
    LockfileMode,
    LockfileStatus,
    carregar_lockfile_ativo,
    verificar_integridade,
)
from src.observability.budget_log import ContextBudgetLog, contar_tokens
from src.rag.prompt_loader import carregar_secoes_prompt
from src.rag.ptf import extrair_data_referencia, is_future_scenario, resolver_regime
from src.rag.hyde import executar_hyde_fallback
from src.rag.multi_query import executar_multi_query_fallback
from src.rag.retriever import ChunkResultado, retrieve
from src.rag.step_back import executar_step_back_fallback
from src.rag.spd import (
    SPDRoutingDecision,
    SPDStrategy,
    decidir_estrategia,
    listar_normas_ativas,
    spd_retrieve,
)
from src.cognitive.metodos import formatar_metodos_para_prompt
from src.cognitive.qualificacao_fatica import calcular_semaforo, formatar_fatos_para_contexto
from src.rag.vigencia_checker import AlertaVigencia, alertas_para_dict, verificar_vigencia_resposta
from src.outputs.stakeholders_inline import gerar_resumos_stakeholders, resumos_para_dict
from src.outputs.disclaimer import validar_disclaimer_presente, DISCLAIMER_TEXTO
from src.cognitive.criticidade import classificar_criticidade

load_dotenv()

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1.0.0-sprint2"
MODEL_DEV = "claude-haiku-4-5-20251001"
MODEL_PROD = "claude-sonnet-4-6"

MODEL_OUTPUT_LIMITS = {
    "claude-haiku-4-5-20251001": 8192,
    "claude-sonnet-4-6": 16384,
}

SYSTEM_PROMPT = """## [SUMMARY]
Você é um especialista em tributação da Reforma Tributária brasileira
(EC 132/2023, LC 214/2025, LC 227/2026), com foco em impacto operacional
e financeiro para empresas.

Seu papel é responder consultas de profissionais das áreas fiscal, contábil
e financeira — não de advogados. Use linguagem direta, objetiva e orientada
a negócios.

REGRAS ESSENCIAIS:
1. Comece sempre pelo impacto prático para a empresa.
2. Base legal como suporte à conclusão — não como ponto de partida.
3. Nunca invente artigos ou alíquotas. Se não houver base legal nos trechos
   recuperados, declare: "Não há base legal suficiente na base de
   conhecimento para responder com segurança."
4. Encerre com uma linha de ação clara para a empresa.
5. NUNCA usar notação LaTeX, MathJax ou símbolos como $, \\(, \\), \\[, \\].
   Escrever valores monetários por extenso: "R$ 100 mil", "R$ 1,2 milhão".

FORMATO DE RESPOSTA (JSON estrito):
{
  "resposta": "string — resposta principal em linguagem de negócios",
  "impacto_financeiro": "string — estimativa de impacto em termos de custo,
                         carga tributária ou fluxo de caixa",
  "fundamento_legal": ["lista de artigos e normas que suportam a resposta"],
  "grau_consolidacao": "consolidado | em_disputa | sem_precedente",
  "scoring_confianca": "alto | medio | baixo",
  "contra_tese": "string — argumento principal da corrente contrária (OBRIGATÓRIO, mesmo para temas consolidados)",
  "forca_corrente_contraria": "Alta | Média | Baixa",
  "risco_adocao": "string — risco concreto de adotar a posição recomendada",
  "acao_recomendada": "string — próximo passo concreto para a empresa"
}

REGRA G11 — CONTRA-TESE OBRIGATÓRIA:
Toda resposta DEVE incluir "contra_tese", "forca_corrente_contraria" e "risco_adocao".
Mesmo quando o tema é consolidado, existe uma corrente minoritária ou risco de mudança
regulatória. Se o tema for verdadeiramente sem precedente, indique isso explicitamente.
Nunca retorne null para "contra_tese" — use "Não há corrente contrária consolidada, mas
o tema ainda não foi testado pelo Comitê Gestor." como fallback mínimo.

## [FULL]
LINGUAGEM CORPORATIVA — substituições obrigatórias:
- "dispositivo legal" → "regra"
- "hermenêutica" → "interpretação"
- "posição doutrinária" → "entendimento de mercado"
- "contribuinte" → "empresa" ou "seu negócio"
- "fato gerador" → "momento em que o imposto incide"

Quando o tema for controverso, apresente os dois lados em termos de risco
financeiro e de compliance — não de tese jurídica.

ESTILO DO CAMPO "resposta":
- Máximo 4 frases. Direto ao ponto.
- Primeira frase: impacto concreto para a empresa (financeiro ou operacional).
- Segunda frase: o que muda na prática (alíquota, regime, obrigação).
- Terceira frase (opcional): risco ou atenção específica.
- Quarta frase: ação recomendada.
- Referências legais APENAS no campo "fundamento_legal".
- Proibido: enumerações "(1), (2), (3)", linguagem passiva, parênteses
  explicativos longos, citações literais de artigos no corpo da resposta.
- Escrever fórmulas em texto corrido, sem formatação matemática.

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

## [FULL:antialucinacao]
MECANISMOS ANTI-ALUCINAÇÃO — aplique rigorosamente:

M1-EXISTÊNCIA: Cite APENAS artigos que aparecem nos trechos recuperados.
Se um artigo não está nos trechos, NÃO o mencione.

M2-VALIDADE: Verifique se a norma citada está vigente. EC 132/2023, LC 214/2025
e LC 227/2026 são as normas ativas da Reforma Tributária.

M3-PERTINÊNCIA: Se os trechos recuperados não são diretamente relevantes
para a consulta (score baixo ou tema tangencial), declare explicitamente
a limitação e reduza scoring_confianca.

M4-CONSISTÊNCIA: scoring_confianca e grau_consolidacao devem ser coerentes.
Se a evidência é fraca (poucos trechos, scores baixos), NÃO declare
scoring_confianca = "alto". Se o tema é consolidado, NÃO declare grau "sem_precedente".

REGRA DE BLOQUEIO: se não encontrar fundamento legal nos trechos, retorne
scoring_confianca = "baixo" e grau_consolidacao = "sem_precedente"."""

COT_INSTRUCTION = """
Antes de responder, raciocine passo a passo:
1. Qual é o impacto direto para a empresa?
2. Qual regra da Reforma Tributária se aplica?
3. Existe risco de interpretação divergente?
4. Qual é a ação concreta recomendada?
"""

# ---------------------------------------------------------------------------
# Prompt Integrity Lockfile (RDM-029)
# ---------------------------------------------------------------------------

LOCKFILE_MODE = LockfileMode(os.getenv("LOCKFILE_MODE", "WARN"))
_lockfile_id_ativo: Optional[str] = None  # UUID do lockfile verificado no boot


def _obter_prompts_sistema() -> dict[str, str]:
    """Retorna mapeamento {nome: conteúdo} de todos os prompts do sistema."""
    prompts = {"cognitive_system_prompt": SYSTEM_PROMPT}
    try:
        from src.outputs.engine import PROMPT_VERSION as _out_ver, DISCLAIMER_PADRAO
        prompts["outputs_disclaimer"] = DISCLAIMER_PADRAO
    except ImportError:
        pass
    return prompts


def verificar_lockfile_boot() -> Optional[str]:
    """Verifica integridade dos prompts no boot. Retorna lockfile_id ou None.

    Modo BLOCK: levanta RuntimeError se divergência detectada.
    Modo WARN: loga warning e continua.
    Sem lockfile ativo: loga info e retorna None.
    """
    global _lockfile_id_ativo
    try:
        conn = _get_db_conn()
        try:
            lockfile = carregar_lockfile_ativo(conn)
        finally:
            put_conn(conn)

        if lockfile is None:
            logger.info("[LOCKFILE] Nenhum lockfile ativo — executando sem verificação.")
            return None

        prompts = _obter_prompts_sistema()
        resultado = verificar_integridade(prompts, lockfile["lockfile_json"], LOCKFILE_MODE)

        if resultado["status"] == LockfileStatus.VALID:
            logger.info("[LOCKFILE OK] %s", resultado["mensagem"])
            _lockfile_id_ativo = lockfile["id"]
            return lockfile["id"]

        # WARN mode: divergência logada mas execução continua
        _lockfile_id_ativo = lockfile["id"]
        return lockfile["id"]

    except RuntimeError:
        raise  # BLOCK mode — propagar
    except Exception as e:
        logger.warning("[LOCKFILE] Verificação ignorada por erro: %s", e)
        return None


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
    forca_corrente_contraria: Optional[str] = None
    risco_adocao: Optional[str] = None
    alertas_vigencia: list[AlertaVigencia] = field(default_factory=list)
    saidas_stakeholders: list[dict] = field(default_factory=list)
    criticidade: str = "informativo"
    criticidade_justificativa: str = ""
    criticidade_impacto: str = ""
    quality_iterations: int = 1  # nº iterações do quality gate loop (observability)


# ---------------------------------------------------------------------------
# Loop Depth Quality Gate — ACT-inspired (OpenMythos concept)
# Queries FACTUAL não iteram (velocidade). INTERPRETATIVA: até 2. COMPARATIVA: até 3.
# ---------------------------------------------------------------------------
_QUALITY_MAX_ITER: dict[str, int] = {
    "factual": 1,
    "interpretativa": 2,
    "comparativa": 3,
}
_QUALITY_TOPK_SCALE: dict[int, float] = {1: 1.0, 2: 1.7, 3: 2.5}


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
    """Obtém conexão do pool centralizado."""
    return get_conn()


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


# ---------------------------------------------------------------------------
# Context Budget Manager (RDM-028)
# ---------------------------------------------------------------------------

ModoContexto = Literal["SUMMARY", "FULL"]

BUDGET_CONFIG: dict[str, dict] = {
    "FACTUAL": {
        "modo": "SUMMARY",
        "max_tokens_contexto": 4_000,
        "max_chunks": 5,
    },
    "INTERPRETATIVA": {
        "modo": "FULL",
        "max_tokens_contexto": 12_000,
        "max_chunks": 10,
    },
    "COMPARATIVA": {
        "modo": "FULL",
        "max_tokens_contexto": 14_000,
        "max_chunks": 12,
    },
}

BUDGET_PRESSAO_THRESHOLD = 85.0


def compactar_chunk(chunk: ChunkResultado, modo: ModoContexto) -> str:
    """Retorna representação do chunk conforme modo de contexto.

    SUMMARY: primeiras 2 sentenças + metadados.
    FULL: chunk completo com metadados.
    """
    artigo_label = chunk.artigo or "artigo não identificado"
    norma = chunk.norma_codigo
    score = chunk.score_final

    if modo == "FULL":
        return (
            f"[{norma} | {artigo_label} | score={score:.3f}]\n"
            f"{chunk.texto}"
        )

    # SUMMARY: primeiras 2 sentenças
    sentencas = _re_mod.split(r'(?<=[.!?])\s+', chunk.texto.strip())
    resumo = " ".join(sentencas[:2])
    return (
        f"[RESUMO | {norma} | {artigo_label} | score={score:.3f}]\n"
        f"{resumo}"
    )


@dataclass
class ContextoBudgetResult:
    contexto_texto: str
    modo: str
    chunks_utilizados: int
    chunks_descartados: int
    tokens_estimados: int
    pressao_pct: float
    budget_log: str


def montar_contexto_budget(
    chunks: list[ChunkResultado],
    tipo_query: str,
) -> ContextoBudgetResult:
    """Monta bloco de contexto respeitando o budget do tipo de query.

    Args:
        chunks: chunks retornados pelo retriever (já filtrados pelo PTF).
        tipo_query: 'FACTUAL' | 'INTERPRETATIVA' | 'COMPARATIVA'.

    Returns:
        ContextoBudgetResult com texto, modo, contagens e log.
    """
    config = BUDGET_CONFIG.get(tipo_query.upper(), BUDGET_CONFIG["INTERPRETATIVA"])
    modo: ModoContexto = config["modo"]
    max_tokens = config["max_tokens_contexto"]
    max_chunks = config["max_chunks"]

    blocos: list[str] = []
    tokens_acumulados = 0
    descartados = 0

    for i, chunk in enumerate(chunks):
        if i >= max_chunks:
            descartados += len(chunks) - i
            break

        bloco = compactar_chunk(chunk, modo)
        tokens_bloco = len(bloco) // 4  # 1 token ≈ 4 chars (pt técnico)

        if tokens_acumulados + tokens_bloco > max_tokens:
            descartados += len(chunks) - i
            break

        blocos.append(bloco)
        tokens_acumulados += tokens_bloco

    pressao_pct = (tokens_acumulados / max_tokens) * 100 if max_tokens else 100.0
    contexto_texto = "\n\n---\n\n".join(blocos)

    budget_log = (
        f"tipo={tipo_query} | modo={modo} | "
        f"chunks={len(blocos)}/{len(chunks)} | "
        f"tokens≈{tokens_acumulados}/{max_tokens} | "
        f"pressao={pressao_pct:.1f}%"
    )

    if pressao_pct >= BUDGET_PRESSAO_THRESHOLD:
        logger.warning("[BUDGET WARNING] pressao=%.1f%% | %s", pressao_pct, budget_log)

    return ContextoBudgetResult(
        contexto_texto=contexto_texto,
        modo=modo,
        chunks_utilizados=len(blocos),
        chunks_descartados=descartados,
        tokens_estimados=tokens_acumulados,
        pressao_pct=pressao_pct,
        budget_log=budget_log,
    )


def _formatar_contexto_caso(contexto_caso: dict) -> str:
    """Formata dados dos passos anteriores do caso para injeção no prompt."""
    partes: list[str] = []
    # P1 — Identificação do caso
    if p1 := contexto_caso.get(1):
        if titulo := p1.get("titulo"):
            partes.append(f"- Título do caso: {titulo}")
        if desc := p1.get("descricao"):
            partes.append(f"- Descrição: {desc}")
        if ctx := p1.get("contexto_fiscal"):
            partes.append(f"- Contexto fiscal: {ctx}")
    # P2 — Premissas
    if p2 := contexto_caso.get(2):
        if premissas := p2.get("premissas"):
            partes.append(f"- Premissas: {premissas}")
        if periodo := p2.get("periodo_fiscal"):
            partes.append(f"- Período fiscal: {periodo}")
        if regime := p2.get("regime_tributario"):
            partes.append(f"- Regime tributário: {regime}")
        # Capturar campos extras comuns
        for k, v in p2.items():
            if k not in ("premissas", "periodo_fiscal", "regime_tributario") and v:
                partes.append(f"- {k.replace('_', ' ').capitalize()}: {v}")
    # P3 — Riscos mapeados
    if p3 := contexto_caso.get(3):
        if riscos := p3.get("riscos"):
            if isinstance(riscos, list):
                partes.append(f"- Riscos mapeados: {'; '.join(r for r in riscos if r)}")
            else:
                partes.append(f"- Riscos mapeados: {riscos}")
        if qual := p3.get("dados_qualidade"):
            partes.append(f"- Qualidade dos dados: {qual}")
    # P5 — Hipótese do gestor (se disponível)
    if p5 := contexto_caso.get(5):
        if hip := p5.get("hipotese_gestor"):
            partes.append(f"- Posição prévia do gestor: {hip}")
    if not partes:
        return ""
    return (
        "\n\nCONTEXTO DO CASO (informações confirmadas pelo usuário em etapas anteriores — "
        "considere como FATOS ESTABELECIDOS, NÃO elabore cenários que os contradigam):\n"
        + "\n".join(partes)
    )


def _formatar_casos_similares(casos: list[dict]) -> str:
    """Formata casos concluídos similares para injeção no prompt como aprendizado institucional."""
    if not casos:
        return ""
    partes = []
    for i, c in enumerate(casos, 1):
        bloco = [f"Caso #{c['case_id']}: {c['titulo']}"]
        if c.get("premissas"):
            bloco.append(f"  Premissas: {'; '.join(c['premissas'][:3])}")
        if c.get("decisao_final"):
            bloco.append(f"  Decisão tomada: {c['decisao_final'][:200]}")
        if c.get("resultado_real"):
            bloco.append(f"  Resultado real: {c['resultado_real'][:200]}")
        if c.get("aprendizado"):
            bloco.append(f"  Aprendizado: {c['aprendizado'][:200]}")
        partes.append("\n".join(bloco))
    return (
        "\n\nAPRENDIZADO INSTITUCIONAL — Casos concluídos similares (use como referência, "
        "NÃO como fonte legislativa. Mencione se algum padrão ou aprendizado anterior for relevante):\n"
        + "\n---\n".join(partes)
    )


def _comprimir_para_haiku(
    contexto: str,
    casos_similares: Optional[list[dict]],
    usar_cot: bool,
) -> tuple[str, Optional[list[dict]], bool]:
    """Comprime contexto quando usando Haiku para deixar budget suficiente para output.

    Returns:
        (contexto_comprimido, casos_similares_limitados, usar_cot_ajustado)
    """
    # Limitar cada chunk a 1500 chars
    partes = contexto.split("\n\n")
    partes_comprimidas = []
    for parte in partes:
        if len(parte) > 1500:
            partes_comprimidas.append(parte[:1500] + "...")
        else:
            partes_comprimidas.append(parte)
    contexto_comprimido = "\n\n".join(partes_comprimidas)

    # Limitar casos similares a 1 caso com campos truncados
    casos_limitados = None
    if casos_similares:
        caso = casos_similares[0].copy()
        for campo in ("decisao_final", "resultado_real", "aprendizado", "premissas"):
            if campo in caso and isinstance(caso[campo], str) and len(caso[campo]) > 150:
                caso[campo] = caso[campo][:150] + "..."
            elif campo in caso and isinstance(caso[campo], list):
                caso[campo] = caso[campo][:1]
        casos_limitados = [caso]

    # Skip CoT para economizar ~100 tokens de output
    return contexto_comprimido, casos_limitados, False


def _chamar_llm(
    query: str,
    contexto: str,
    temperatura: float = 0.1,
    usar_cot: bool = False,
    model: str = MODEL_DEV,
    query_tipo: str = "INTERPRETATIVA",
    quality_gate: str = "VERDE",
    contexto_caso: Optional[dict] = None,
    casos_similares: Optional[list[dict]] = None,
    metodos_selecionados: Optional[list[str]] = None,
    premissas: Optional[list[str]] = None,
    riscos_fiscais: Optional[list[str]] = None,
    fatos_cliente: Optional[dict] = None,
    _escalated: bool = False,
    tenant_id: Optional[str] = None,
) -> dict:
    """Chama o LLM e retorna o JSON parseado.

    Se o modelo truncar a saída (stop_reason=max_tokens) e for Haiku,
    tenta auto-escalar para Sonnet uma vez.
    """
    client = _get_client()

    # Comprimir contexto para Haiku
    if model == MODEL_DEV and not _escalated:
        contexto, casos_similares, usar_cot = _comprimir_para_haiku(
            contexto, casos_similares, usar_cot
        )

    load_result = carregar_secoes_prompt(SYSTEM_PROMPT, query_tipo, quality_gate)
    system = load_result.conteudo_carregado + (COT_INSTRUCTION if usar_cot else "")

    caso_str = _formatar_contexto_caso(contexto_caso) if contexto_caso else ""
    similares_str = _formatar_casos_similares(casos_similares) if casos_similares else ""
    metodos_str = formatar_metodos_para_prompt(metodos_selecionados or [])
    metodos_bloco = f"\n\n{metodos_str}" if metodos_str else ""

    premissas_bloco = ""
    if premissas:
        premissas_bloco = (
            "\n\nPREMISSAS REGULATÓRIAS DECLARADAS PELO GESTOR:\n"
            + "\n".join(f"- {p}" for p in premissas)
            + "\n(Analise à luz dessas premissas. Indique se alguma é contestável ou incorreta.)"
        )

    riscos_bloco = ""
    if riscos_fiscais:
        riscos_bloco = (
            "\n\nRISCOS FISCAIS DECLARADOS PELO GESTOR:\n"
            + "\n".join(f"- {r}" for r in riscos_fiscais)
            + "\n(Avalie se esses riscos se materializam no caso e se há riscos adicionais não declarados.)"
        )

    fatos_bloco = formatar_fatos_para_contexto(fatos_cliente or {})

    user_msg = (
        f"TRECHOS LEGISLATIVOS RECUPERADOS:\n{contexto}\n\n"
        f"CONSULTA: {query}"
        f"{fatos_bloco}"
        f"{caso_str}"
        f"{similares_str}"
        f"{premissas_bloco}"
        f"{riscos_bloco}"
        f"{metodos_bloco}\n\n"
        "Responda APENAS com o JSON especificado."
    )

    max_tokens = MODEL_OUTPUT_LIMITS.get(model, 8192)

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
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
            tenant_id=tenant_id,
        )
    except Exception as _usage_err:
        logger.debug("Registro de uso ignorado: %s", _usage_err)

    # Detectar truncamento antes de tentar parse
    if resp.stop_reason == "max_tokens":
        logger.warning(
            "LLM output truncado: model=%s, output_tokens=%d, stop_reason=max_tokens",
            model, resp.usage.output_tokens,
        )
        # Auto-escalar Haiku → Sonnet (uma vez)
        if model == MODEL_DEV and not _escalated:
            logger.info("Auto-escalando de %s para %s após truncamento", MODEL_DEV, MODEL_PROD)
            return _chamar_llm(
                query=query,
                contexto=contexto,
                temperatura=temperatura,
                usar_cot=usar_cot,
                model=MODEL_PROD,
                query_tipo=query_tipo,
                quality_gate=quality_gate,
                contexto_caso=contexto_caso,
                casos_similares=casos_similares,
                metodos_selecionados=metodos_selecionados,
                premissas=premissas,
                riscos_fiscais=riscos_fiscais,
                fatos_cliente=fatos_cliente,
                _escalated=True,
                tenant_id=tenant_id,
            )
        raise RuntimeError(
            f"LLM output truncado (stop_reason=max_tokens, model={model}, "
            f"output_tokens={resp.usage.output_tokens}). "
            f"Prompt muito longo para capacidade de output do modelo."
        )

    raw = resp.content[0].text.strip()
    # Remover possível markdown ```json ... ```
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(
            "JSON malformado: model=%s, stop_reason=%s, output_tokens=%d, raw=%s... erro=%s",
            model, resp.stop_reason, resp.usage.output_tokens, raw[:200], e,
        )
        raise RuntimeError(
            f"LLM retornou JSON inválido: model={model}, stop_reason={resp.stop_reason}, "
            f"output_tokens={resp.usage.output_tokens}, posição={e.pos}."
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
    context_budget_log: Optional[str] = None,
    budget_pressao_pct: Optional[float] = None,
    data_referencia_utilizado=None,
    is_future_scenario_flag: bool = False,
    chunks_pre_filtro: Optional[int] = None,
    chunks_pos_filtro: Optional[int] = None,
    lockfile_id: Optional[str] = None,
    hyde_activated: bool = False,
    multi_query_activated: bool = False,
    query_variations_count: int = 0,
    step_back_activated: bool = False,
    step_back_query: Optional[str] = None,
    user_id: Optional[str] = None,
    premissas: Optional[list[str]] = None,
    riscos_fiscais: Optional[list[str]] = None,
    forca_corrente_contraria: Optional[str] = None,
    contra_tese_presente: bool = False,
    fatos_cliente: Optional[dict] = None,
    alertas_vigencia: Optional[list] = None,
) -> None:
    """Registra em ai_interactions."""
    # SEC-09: sentinela de integridade — o UUID zero não existe na tabela users.
    # Converte para NULL antes do INSERT para evitar FK violation.
    # NÃO é um bypass de autenticação: toda request já passou pelo JWT/X-Api-Key.
    _NULL_USER_SENTINEL = "00000000-0000-0000-0000-000000000000"
    if user_id == _NULL_USER_SENTINEL:
        user_id = None
    try:
        cur = conn.cursor()
        _premissas_pg = premissas or []
        _riscos_pg = riscos_fiscais or []
        _p2_concluido = len(_premissas_pg) >= 3 and len(_riscos_pg) >= 3
        _fatos = fatos_cliente or {}
        _qf_semaforo = calcular_semaforo(_fatos).semaforo if _fatos else None
        import json as _json
        _alertas_list = alertas_para_dict(alertas_vigencia) if alertas_vigencia else []
        _vigencia_ok = len(_alertas_list) == 0
        cur.execute(
            """
            INSERT INTO ai_interactions (
                query_texto, chunks_ids, qualidade_status, scoring_confianca,
                grau_consolidacao, m1_existencia, m2_validade, m3_pertinencia,
                m4_consistencia, bloqueado, prompt_version, model_id, latencia_ms,
                retrieval_strategy, context_budget_log, budget_pressao_pct,
                data_referencia_utilizado, is_future_scenario,
                chunks_pre_filtro, chunks_pos_filtro, lockfile_id,
                hyde_activated, multi_query_activated, query_variations_count,
                step_back_activated, step_back_query, user_id,
                premissas, riscos_fiscais, p2_concluido,
                forca_corrente_contraria, contra_tese_presente,
                qf_cnae_principal, qf_regime_tributario, qf_ufs_operacao,
                qf_tipo_operacao, qf_faturamento_faixa, qf_semaforo,
                alertas_vigencia, vigencia_ok
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                context_budget_log,
                budget_pressao_pct,
                data_referencia_utilizado,
                is_future_scenario_flag,
                chunks_pre_filtro,
                chunks_pos_filtro,
                lockfile_id,
                hyde_activated,
                multi_query_activated,
                query_variations_count,
                step_back_activated,
                step_back_query,
                user_id,
                _premissas_pg,
                _riscos_pg,
                _p2_concluido,
                forca_corrente_contraria,
                contra_tese_presente,
                _fatos.get("cnae_principal"),
                _fatos.get("regime_tributario"),
                _fatos.get("ufs_operacao"),
                _fatos.get("tipo_operacao"),
                _fatos.get("faturamento_faixa"),
                _qf_semaforo,
                _json.dumps(_alertas_list, ensure_ascii=False) if _alertas_list else "[]",
                _vigencia_ok,
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
    contexto_caso: Optional[dict] = None,
    casos_similares: Optional[list[dict]] = None,
    user_id: Optional[str] = None,
    metodos_selecionados: Optional[list[str]] = None,
    criticidade: str = "media",
    premissas: Optional[list[str]] = None,
    riscos_fiscais: Optional[list[str]] = None,
    fatos_cliente: Optional[dict] = None,
) -> AnaliseResult:
    """
    Pipeline completo de análise tributária (6 Passos).

    Retrieve (RAG) → Quality gate → LLM + CoT + anti-alucinação → Retorno estruturado

    Args:
        contexto_caso: dados dos passos anteriores do caso atual (keyed by passo int).
                       Quando fornecido, o LLM trata essas informações como fatos confirmados.
        casos_similares: lista de casos concluídos similares para retroalimentação.
                         Cada item contém: titulo, premissas, decisao_final, resultado_real, aprendizado.
    """
    t0 = time.time()
    conn = _get_db_conn()
    try:
        return _analisar_inner(conn, query, top_k, rerank_top_n, norma_filter,
                               excluir_tipos, model, decompose, t0, contexto_caso,
                               casos_similares, user_id,
                               metodos_selecionados=metodos_selecionados,
                               premissas=premissas,
                               riscos_fiscais=riscos_fiscais,
                               fatos_cliente=fatos_cliente)
    finally:
        put_conn(conn)


def _analisar_inner(
    conn: psycopg2.extensions.connection,
    query: str,
    top_k: int,
    rerank_top_n: int,
    norma_filter: Optional[list[str]],
    excluir_tipos: Optional[list[str]],
    model: str,
    decompose: bool,
    t0: float,
    contexto_caso: Optional[dict] = None,
    casos_similares: Optional[list[dict]] = None,
    user_id: Optional[str] = None,
    metodos_selecionados: Optional[list[str]] = None,
    premissas: Optional[list[str]] = None,
    riscos_fiscais: Optional[list[str]] = None,
    fatos_cliente: Optional[dict] = None,
) -> AnaliseResult:
    """Corpo interno do pipeline de análise (chamado por analisar com try/finally)."""
    # Resolver tenant_id a partir do user_id para rastreio de consumo
    _tenant_id: Optional[str] = None
    if user_id:
        try:
            with conn.cursor() as _tcur:
                _tcur.execute(
                    "SELECT tenant_id FROM users WHERE id = %s LIMIT 1",
                    (user_id,),
                )
                _trow = _tcur.fetchone()
                if _trow:
                    _tenant_id = str(_trow[0])
        except Exception as _te:
            logger.debug("Falha ao resolver tenant_id para user %s: %s", user_id, _te)

    # PTF — Pre-filter Temporal: extrair data de referência da query
    data_ref = extrair_data_referencia(query)
    _is_future = is_future_scenario(data_ref)
    if data_ref:
        regime = resolver_regime(data_ref)
        logger.info("PTF: data_ref=%s regime=%s future=%s", data_ref, regime, _is_future)

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

    def _do_retrieve(q: str, _p=None) -> list[ChunkResultado]:
        p = _p if _p is not None else params
        return retrieve(q, top_k=p.top_k, rerank_top_n=p.rerank_top_n,
                        norma_filter=norma_filter, excluir_tipos=_excluir,
                        cosine_weight=p.cosine_weight, bm25_weight=p.bm25_weight,
                        data_referencia=data_ref, tenant_id=_tenant_id)

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
            data_referencia=data_ref,
            tenant_id=_tenant_id,
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

    # P1.5-P2 — CRAG + Adaptive Tools + Quality Gate
    # Loop Depth (ACT-inspired): queries complexas recebem até N iterações de retrieval.
    # FACTUAL: 1 iteração (sem loop). INTERPRETATIVA: até 2. COMPARATIVA: até 3.
    _quality_max_iter = _QUALITY_MAX_ITER.get(query_tipo.value, 1)
    _quality_iterations = 1

    # Inicializar flags de ferramentas antes do loop
    _hyde_activated = False
    _multi_query_activated = False
    _query_variations_count = 0
    _step_back_activated = False
    _step_back_query_text = None
    _regime = resolver_regime(data_ref) if data_ref else None
    _qt_upper = query_tipo.value.upper()
    _tool_activated = False
    _alertas_vigencia_crag: list[AlertaVigencia] = []

    for _iter_n in range(1, _quality_max_iter + 1):
        _quality_iterations = _iter_n

        # Nas iterações seguintes: escalar params e re-fazer retrieve
        if _iter_n > 1:
            _iter_params = replace(
                params,
                top_k=round(params.top_k * _QUALITY_TOPK_SCALE[_iter_n]),
                rerank_top_n=round(params.rerank_top_n * _QUALITY_TOPK_SCALE[_iter_n]),
            )
            logger.info(
                "Quality loop iter %d/%d: escalando top_k=%d rerank=%d",
                _iter_n, _quality_max_iter, _iter_params.top_k, _iter_params.rerank_top_n,
            )
            chunks = _do_retrieve(query, _iter_params)
            _tool_activated = False
            _hyde_activated = False
            _multi_query_activated = False
            _step_back_activated = False
        else:
            _iter_params = params

        # P1.5 — Corrective RAG
        _alertas_vigencia_crag = []
        try:
            corrector = CorrectorRAG(model=model)
            crag_result = corrector.corrigir(
                query, chunks, retrieve_fn=lambda q: _do_retrieve(q, _iter_params)
            )
            chunks = crag_result.chunks_filtrados
            _alertas_vigencia_crag = crag_result.alertas_vigencia
        except Exception as e:
            logger.warning("CRAG ignorado: %s", e)

        # P1.6–P1.8 — Adaptive Retrieval Tools (mutuamente exclusivos)
        # Tool 1: Multi-Query (vocabulário coloquial)
        if not _tool_activated:
            try:
                chunks, _multi_query_activated, _query_variations_count = executar_multi_query_fallback(
                    query=query,
                    chunks_iniciais=chunks,
                    model=model,
                    top_k=_iter_params.top_k,
                    rerank_top_n=_iter_params.rerank_top_n,
                    norma_filter=norma_filter,
                    excluir_tipos=_excluir,
                    cosine_weight=_iter_params.cosine_weight,
                    bm25_weight=_iter_params.bm25_weight,
                    data_referencia=data_ref,
                    regime=_regime,
                    tenant_id=_tenant_id,
                )
                _tool_activated = _multi_query_activated
            except Exception as e:
                logger.warning("Multi-Query ignorado: %s", e)

        # Tool 2: Step-Back (alta especificidade)
        if not _tool_activated:
            try:
                chunks, _step_back_activated, _step_back_query_text = executar_step_back_fallback(
                    query=query,
                    chunks_iniciais=chunks,
                    tipo_query=_qt_upper,
                    model=model,
                    top_k=_iter_params.top_k,
                    rerank_top_n=_iter_params.rerank_top_n,
                    norma_filter=norma_filter,
                    excluir_tipos=_excluir,
                    cosine_weight=_iter_params.cosine_weight,
                    bm25_weight=_iter_params.bm25_weight,
                    data_referencia=data_ref,
                    regime=_regime,
                    tenant_id=_tenant_id,
                )
                _tool_activated = _step_back_activated
            except Exception as e:
                logger.warning("Step-Back ignorado: %s", e)

        # Tool 3: HyDE (score baixo em queries interpretativas)
        if not _tool_activated:
            try:
                chunks, _hyde_activated = executar_hyde_fallback(
                    query=query,
                    chunks_iniciais=chunks,
                    tipo_query=_qt_upper,
                    model=model,
                    top_k=_iter_params.top_k,
                    rerank_top_n=_iter_params.rerank_top_n,
                    norma_filter=norma_filter,
                    excluir_tipos=_excluir,
                    cosine_weight=_iter_params.cosine_weight,
                    bm25_weight=_iter_params.bm25_weight,
                    data_referencia=data_ref,
                    regime=_regime,
                    tenant_id=_tenant_id,
                )
            except Exception as e:
                logger.warning("HyDE ignorado: %s", e)

        # P2 — Quality Gate
        qualidade = avaliar_qualidade(query, chunks)

        # RS-02 reactive (apenas na iter 1 — evitar SPD duplo)
        if (_iter_n == 1
                and decisao.strategy == SPDStrategy.STANDARD
                and "RS-02" in qualidade.ressalvas
                and len(normas_ativas) >= 2):
            logger.info("RS-02 detectado — retry com SPD-RAG")
            try:
                spd_result = spd_retrieve(
                    query=query,
                    normas=normas_ativas,
                    top_k_por_norma=3,
                    rerank_top_n=_iter_params.rerank_top_n,
                    excluir_tipos=_excluir,
                    cosine_weight=_iter_params.cosine_weight,
                    bm25_weight=_iter_params.bm25_weight,
                    data_referencia=data_ref,
                    tenant_id=_tenant_id,
                )
                if len({c.norma_codigo for c in spd_result.chunks_merged}) > 1:
                    chunks = spd_result.chunks_merged[:_iter_params.top_k]
                    qualidade = avaliar_qualidade(query, chunks)
                    decisao = SPDRoutingDecision(SPDStrategy.SPD_REACTIVE, "RS-02 fallback")
                    logger.info("SPD reactive: cobertura multi-norma restaurada")
            except Exception as e:
                logger.warning("SPD reactive fallback falhou: %s", e)

        # VERMELHO: bloquear imediatamente (mesmo comportamento original)
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
                quality_iterations=_quality_iterations,
            )
            _registrar_interacao(conn, query, chunks, qualidade, anti, {}, model, latencia_ms,
                                retrieval_strategy=decisao.strategy.value,
                                data_referencia_utilizado=data_ref,
                                is_future_scenario_flag=_is_future,
                                lockfile_id=_lockfile_id_ativo,
                                hyde_activated=_hyde_activated,
                                multi_query_activated=_multi_query_activated,
                                query_variations_count=_query_variations_count,
                                step_back_activated=_step_back_activated,
                                step_back_query=_step_back_query_text,
                                user_id=user_id,
                                premissas=premissas,
                                riscos_fiscais=riscos_fiscais)
            return resultado

        # Halting: VERDE ou última iteração → prosseguir para P3
        if qualidade.status == QualidadeStatus.VERDE or _iter_n == _quality_max_iter:
            if _iter_n > 1:
                logger.info(
                    "Quality loop: status=%s após %d iterações",
                    qualidade.status.value, _iter_n,
                )
            break
        logger.info(
            "Quality Gate %s na iter %d/%d — escalando retrieval para iter %d",
            qualidade.status.value, _iter_n, _quality_max_iter, _iter_n + 1,
        )

    # P3 — LLM + Progressive Loading + Context Budget Manager (RDM-028)
    qt_str = query_tipo.value.upper()
    qg_str = qualidade.status.value.upper()

    ctx_budget = montar_contexto_budget(chunks, qt_str)
    contexto = ctx_budget.contexto_texto
    logger.info(
        "Budget: %s modo=%s chunks=%d/%d tokens≈%d pressao=%.1f%%",
        qt_str, ctx_budget.modo, ctx_budget.chunks_utilizados,
        ctx_budget.chunks_utilizados + ctx_budget.chunks_descartados,
        ctx_budget.tokens_estimados, ctx_budget.pressao_pct,
    )

    # Determinar temperatura baseada em contexto inicial
    temperatura = 0.1  # análise interpretativa por padrão

    # Primeira chamada
    dados = _chamar_llm(query, contexto, temperatura=temperatura, usar_cot=False, model=model,
                        query_tipo=qt_str, quality_gate=qg_str, contexto_caso=contexto_caso,
                        casos_similares=casos_similares,
                        metodos_selecionados=metodos_selecionados,
                        premissas=premissas, riscos_fiscais=riscos_fiscais,
                        fatos_cliente=fatos_cliente, tenant_id=_tenant_id)

    # Ativar CoT se necessário e re-chamar
    if _precisa_cot(qualidade, dados):
        logger.info("Ativando Chain-of-Thought para query: %s", query[:60])
        dados = _chamar_llm(query, contexto, temperatura=0.3, usar_cot=True, model=model,
                            query_tipo=qt_str, quality_gate=qg_str, contexto_caso=contexto_caso,
                            casos_similares=casos_similares,
                            metodos_selecionados=metodos_selecionados,
                            premissas=premissas, riscos_fiscais=riscos_fiscais,
                            fatos_cliente=fatos_cliente, tenant_id=_tenant_id)

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
            temperatura=0.0, usar_cot=False, model=model,
            query_tipo=qt_str, quality_gate=qg_str, contexto_caso=contexto_caso,
            casos_similares=casos_similares,
            metodos_selecionados=metodos_selecionados,
            premissas=premissas, riscos_fiscais=riscos_fiscais,
            fatos_cliente=fatos_cliente, tenant_id=_tenant_id,
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

    # Garantia de disclaimer DC v7 (G15): se a IA omitiu, adicionar automaticamente
    if resposta and not anti.bloqueado and not validar_disclaimer_presente(resposta):
        resposta = resposta + f"\n\n---\n*{DISCLAIMER_TEXTO}*"
        logger.warning("Disclaimer ausente na resposta da IA — adicionado automaticamente (DC v7)")

    # Verificação de vigência legislativa — nível resposta (G08)
    _alertas_vigencia_resposta: list[AlertaVigencia] = []
    try:
        _alertas_vigencia_resposta = verificar_vigencia_resposta(
            resposta,
            data_analise=data_ref if data_ref else None,
        )
    except Exception as _vig_err:
        logger.debug("Vigência checker ignorado: %s", _vig_err)
    _alertas_vigencia_todos = _alertas_vigencia_crag + _alertas_vigencia_resposta

    _contra_tese = dados.get("contra_tese") or (
        "Não há corrente contrária consolidada, mas o tema ainda não foi testado "
        "pelo Comitê Gestor."
    )
    resultado = AnaliseResult(
        query=query,
        chunks=chunks,
        qualidade=qualidade,
        fundamento_legal=dados.get("fundamento_legal", []),
        grau_consolidacao=dados.get("grau_consolidacao", "sem_precedente"),
        contra_tese=_contra_tese,
        scoring_confianca=dados.get("scoring_confianca", "baixo"),
        forca_corrente_contraria=dados.get("forca_corrente_contraria"),
        risco_adocao=dados.get("risco_adocao"),
        alertas_vigencia=_alertas_vigencia_todos,
        resposta=resposta,
        disclaimer=disclaimer,
        anti_alucinacao=anti,
        prompt_version=PROMPT_VERSION,
        model_id=model,
        latencia_ms=latencia_ms,
        retrieval_strategy=decisao.strategy.value,
        quality_iterations=_quality_iterations,
    )

    # Gerar context_budget_log estruturado (inclui chunk budget RDM-028)
    budget_log_str = None
    budget_pct = None
    try:
        _load_result = carregar_secoes_prompt(SYSTEM_PROMPT, qt_str, qg_str)
        _budget = ContextBudgetLog(prompt_codigo=PROMPT_VERSION, query_tipo=qt_str)
        for secao, tokens in _load_result.tokens_por_secao.items():
            comp_map = {
                "SUMMARY": "system_prompt_summary",
                "FULL": "system_prompt_full",
                "FULL:antialucinacao": "system_prompt_antialucinacao",
                "ALL": "system_prompt_summary",
            }
            _budget.adicionar(comp_map.get(secao, "outros"), f"{PROMPT_VERSION} [{secao}]", tokens)
        _budget.adicionar(
            "rag_chunks",
            f"top-{ctx_budget.chunks_utilizados} chunks modo={ctx_budget.modo}",
            contar_tokens(contexto),
        )
        if _precisa_cot(qualidade, dados):
            _budget.adicionar("cot_instruction", "chain-of-thought", contar_tokens(COT_INSTRUCTION))
        if _hyde_activated:
            _budget.adicionar("hyde_doc_hipotetico", "HyDE re-retrieval ativado", 0)
        if _multi_query_activated:
            _budget.adicionar("multi_query_variations", f"Multi-Query {_query_variations_count} variações", 0)
        budget_log_str = _budget.to_log_string() + f"\n  [CHUNK_BUDGET] {ctx_budget.budget_log}"
        budget_pct = round(_budget.pressao_pct, 2)
        if _budget.alerta_pressao():
            logger.warning("Budget pressure alert: %.1f%% usado — %s", _budget.pressao_pct, PROMPT_VERSION)
    except Exception:
        pass

    _registrar_interacao(conn, query, chunks, qualidade, anti, dados, model, latencia_ms,
                        retrieval_strategy=decisao.strategy.value,
                        context_budget_log=budget_log_str,
                        budget_pressao_pct=budget_pct,
                        data_referencia_utilizado=data_ref,
                        is_future_scenario_flag=_is_future,
                        lockfile_id=_lockfile_id_ativo,
                        hyde_activated=_hyde_activated,
                        user_id=user_id,
                        premissas=premissas,
                        riscos_fiscais=riscos_fiscais,
                        forca_corrente_contraria=dados.get("forca_corrente_contraria"),
                        contra_tese_presente=bool(dados.get("contra_tese")),
                        fatos_cliente=fatos_cliente,
                        alertas_vigencia=_alertas_vigencia_todos)
    logger.info("Análise concluída: status=%s score=%s latência=%dms flags=%s",
                qualidade.status, dados.get("scoring_confianca"), latencia_ms, all_flags)

    # Calibração por Criticidade (D3, G17) — classifica e persiste
    try:
        _crit = classificar_criticidade(
            resposta_ia=resultado.resposta,
            grau_consolidacao=dados.get("grau_consolidacao", ""),
            forca_contra_tese=dados.get("forca_corrente_contraria", ""),
            impacto_financeiro_estimado=0.0,
        )
        resultado.criticidade = _crit.nivel.value
        resultado.criticidade_justificativa = _crit.justificativa
        resultado.criticidade_impacto = _crit.impacto_estimado
        # Persistir nos campos adicionados pela migration 114
        try:
            _cur_crit = conn.cursor()
            _cur_crit.execute(
                """
                UPDATE ai_interactions
                   SET criticidade = %s, criticidade_motivo = %s
                 WHERE query_texto = %s AND model_id = %s
                   AND id = (
                       SELECT id FROM ai_interactions
                        WHERE query_texto = %s AND model_id = %s
                        ORDER BY created_at DESC LIMIT 1
                   )
                """,
                (
                    _crit.nivel.value, _crit.justificativa,
                    query, model,
                    query, model,
                ),
            )
            conn.commit()
            _cur_crit.close()
        except Exception as _db_crit_err:
            logger.debug("Criticidade não persistida no banco: %s", _db_crit_err)
    except Exception as _crit_err:
        logger.debug("Calibração de criticidade ignorada: %s", _crit_err)

    # Saídas por Stakeholder (C3, G16) — falhas individuais não bloqueiam retorno
    try:
        _saidas = gerar_resumos_stakeholders(
            analise_original=resultado.resposta,
            client=_get_client(),
            model=model,
        )
        resultado.saidas_stakeholders = resumos_para_dict(_saidas)
    except Exception as _st_err:
        logger.debug("Stakeholder summaries ignorados: %s", _st_err)

    # Observability — não propaga exceções
    try:
        from src.observability.collector import MetricsCollector
        MetricsCollector().registrar_interacao(resultado, query)
    except Exception as _obs_err:
        logger.debug("MetricsCollector ignorado: %s", _obs_err)

    return resultado
