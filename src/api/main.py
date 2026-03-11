"""
api/main.py — FastAPI: 17 endpoints do motor cognitivo TaxMind Light.

POST /v1/analyze                                  — análise tributária completa
GET  /v1/chunks                                   — busca RAG direta
GET  /v1/health                                   — status do sistema
POST /v1/ingest/upload                            — ingestão de PDF adicional
POST /v1/cases                                    — criar caso protocolo
GET  /v1/cases/{case_id}                          — estado do caso
POST /v1/cases/{case_id}/steps/{passo}            — submeter passo
POST /v1/cases/{case_id}/carimbo/confirmar        — confirmar alerta carimbo
POST /v1/outputs                                  — gerar output acionável
GET  /v1/outputs/{output_id}                      — detalhe do output
POST /v1/outputs/{output_id}/aprovar              — aprovar output
GET  /v1/cases/{case_id}/outputs                  — listar outputs do caso
GET  /v1/observability/metrics                    — métricas diárias agregadas
GET  /v1/observability/drift                      — drift alerts ativos
POST /v1/observability/drift/{alert_id}/resolver  — resolver drift alert
POST /v1/observability/baseline                   — registrar baseline
POST /v1/observability/regression                 — executar regression testing
"""

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.cognitive.engine import MODEL_DEV, AnaliseResult, analisar
from src.ingest.chunker import chunkar_documento
from src.protocol.carimbo import CarimboConfirmacaoError, DetectorCarimbo
from src.protocol.engine import CaseEstado, ProtocolError, ProtocolStateEngine
from src.ingest.embedder import gerar_e_persistir_embeddings
from src.ingest.loader import DocumentoNorma, extrair_texto_pdf
from src.outputs.engine import OutputClass, OutputEngine, OutputError, OutputResult
from src.outputs.stakeholders import StakeholderTipo
from src.quality.engine import QualidadeStatus
from src.rag.retriever import ChunkResultado, retrieve

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TaxMind Light API",
    description="Motor cognitivo para análise da Reforma Tributária brasileira",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas de entrada ---

class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Consulta tributária")
    norma_filter: Optional[list[str]] = Field(None, description="Filtrar por normas: EC132_2023, LC214_2025, LC227_2026")
    excluir_tipos: Optional[list[str]] = Field(["Outro"], description="Tipos de norma a excluir do RAG (padrão: [\"Outro\"])")
    top_k: int = Field(3, ge=1, le=10)
    model: str = Field(MODEL_DEV)


# --- Serialização de AnaliseResult para dict ---

def _analise_to_dict(resultado: AnaliseResult) -> dict:
    return {
        "query": resultado.query,
        "qualidade": {
            "status": resultado.qualidade.status.value,
            "regras_ok": resultado.qualidade.regras_ok,
            "bloqueios": resultado.qualidade.bloqueios,
            "ressalvas": resultado.qualidade.ressalvas,
            "disclaimer": resultado.qualidade.disclaimer,
        },
        "fundamento_legal": resultado.fundamento_legal,
        "grau_consolidacao": resultado.grau_consolidacao,
        "contra_tese": resultado.contra_tese,
        "scoring_confianca": resultado.scoring_confianca,
        "resposta": resultado.resposta,
        "disclaimer": resultado.disclaimer,
        "anti_alucinacao": {
            "m1_existencia": resultado.anti_alucinacao.m1_existencia,
            "m2_validade": resultado.anti_alucinacao.m2_validade,
            "m3_pertinencia": resultado.anti_alucinacao.m3_pertinencia,
            "m4_consistencia": resultado.anti_alucinacao.m4_consistencia,
            "bloqueado": resultado.anti_alucinacao.bloqueado,
            "flags": resultado.anti_alucinacao.flags,
        },
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "norma_codigo": c.norma_codigo,
                "artigo": c.artigo,
                "texto": c.texto,
                "score_vetorial": c.score_vetorial,
                "score_bm25": c.score_bm25,
                "score_final": c.score_final,
            }
            for c in resultado.chunks
        ],
        "prompt_version": resultado.prompt_version,
        "model_id": resultado.model_id,
        "latencia_ms": resultado.latencia_ms,
    }


# --- Endpoints ---

@app.post("/v1/analyze")
async def analyze(req: AnalyzeRequest):
    """
    Análise tributária completa P1→P4.
    Retorna 400 se a qualidade for VERMELHO (bloqueado).
    """
    logger.info("POST /v1/analyze query=%s", req.query[:80])
    try:
        resultado = analisar(
            query=req.query,
            top_k=req.top_k,
            norma_filter=req.norma_filter,
            excluir_tipos=req.excluir_tipos if req.excluir_tipos is not None else ["Outro"],
            model=req.model,
        )
    except Exception as e:
        logger.error("Erro interno em /v1/analyze: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if resultado.qualidade.status == QualidadeStatus.VERMELHO:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Consulta bloqueada pelo DataQualityEngine",
                "bloqueios": resultado.qualidade.bloqueios,
                "qualidade_status": "vermelho",
            },
        )

    return _analise_to_dict(resultado)


@app.get("/v1/chunks")
async def get_chunks(
    q: str = Query(..., description="Texto da busca"),
    top_k: int = Query(3, ge=1, le=10),
    norma: Optional[str] = Query(None, description="Código da norma para filtrar"),
):
    """Busca RAG direta sem análise cognitiva."""
    logger.info("GET /v1/chunks q=%s top_k=%d norma=%s", q[:60], top_k, norma)
    try:
        norma_filter = [norma] if norma else None
        chunks = retrieve(q, top_k=top_k, norma_filter=norma_filter, excluir_tipos=["Outro"])
    except Exception as e:
        logger.error("Erro em /v1/chunks: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return [
        {
            "chunk_id": c.chunk_id,
            "norma_codigo": c.norma_codigo,
            "artigo": c.artigo,
            "texto": c.texto,
            "score_vetorial": c.score_vetorial,
            "score_bm25": c.score_bm25,
            "score_final": c.score_final,
        }
        for c in chunks
    ]


@app.get("/v1/health")
async def health():
    """Status do sistema com contagens e lista de normas disponíveis."""
    try:
        url = os.getenv("DATABASE_URL")
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM chunks")
        chunks_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM embeddings")
        embeddings_total = cur.fetchone()[0]
        cur.execute("SELECT codigo, nome FROM normas WHERE vigente = TRUE ORDER BY ano, codigo")
        normas = [{"codigo": r[0], "nome": r[1]} for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Banco inacessível: {e}")

    return {
        "status": "ok",
        "chunks_total": chunks_total,
        "embeddings_total": embeddings_total,
        "normas": normas,
    }


@app.post("/v1/ingest/upload")
async def ingest_upload(
    file: UploadFile = File(..., description="Arquivo PDF a ingerir"),
    nome: str = Form(..., description="Nome do documento (ex: IN RFB 2184/2024)"),
    tipo: str = Form(..., description="Tipo: IN | Resolucao | Parecer | Manual | Outro"),
):
    """
    Ingestão de PDF adicional (INs, Resoluções, Pareceres, Manuais).
    O PDF é processado em /tmp e não é persistido no disco após ingestão.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    logger.info("POST /v1/ingest/upload nome=%s tipo=%s", nome, tipo)

    # Gerar código único a partir do nome
    codigo = re.sub(r"[^A-Za-z0-9]", "_", nome)[:30].strip("_")

    conteudo = await file.read()

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(conteudo)
            tmp.flush()
            tmp_path = Path(tmp.name)

            # Extrair texto
            texto = extrair_texto_pdf(tmp_path)
            if not texto.strip():
                raise HTTPException(status_code=400, detail="PDF sem texto extraível (pode ser imagem)")

            doc = DocumentoNorma(
                codigo=codigo,
                nome=nome,
                tipo=tipo,
                numero="0",
                ano=2024,
                arquivo=file.filename,
                texto=texto,
            )

            # Persistir norma + chunks + embeddings
            url = os.getenv("DATABASE_URL")
            conn = psycopg2.connect(url)
            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO normas (codigo, nome, tipo, numero, ano, arquivo)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo) DO UPDATE SET
                    nome = EXCLUDED.nome, arquivo = EXCLUDED.arquivo, vigente = TRUE
                RETURNING id
                """,
                (doc.codigo, doc.nome, doc.tipo, doc.numero, doc.ano, doc.arquivo),
            )
            norma_id = cur.fetchone()[0]
            conn.commit()

            chunks = chunkar_documento(doc.texto)

            chunk_ids: list[int] = []
            for chunk in chunks:
                cur.execute(
                    """
                    INSERT INTO chunks (norma_id, chunk_index, texto, artigo, secao, titulo, tokens)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (norma_id, chunk_index) DO NOTHING
                    RETURNING id
                    """,
                    (norma_id, chunk.chunk_index, chunk.texto, chunk.artigo,
                     chunk.secao, chunk.titulo, chunk.tokens),
                )
                row = cur.fetchone()
                if row:
                    chunk_ids.append(row[0])
                else:
                    cur.execute(
                        "SELECT id FROM chunks WHERE norma_id=%s AND chunk_index=%s",
                        (norma_id, chunk.chunk_index),
                    )
                    chunk_ids.append(cur.fetchone()[0])
            conn.commit()

            n_emb = gerar_e_persistir_embeddings(conn, chunk_ids, chunks)
            cur.close()
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro em /v1/ingest/upload: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    logger.info("Upload ingerido: %s | chunks=%d | embeddings=%d", nome, len(chunks), n_emb)
    return {
        "norma_id": norma_id,
        "nome": nome,
        "codigo": codigo,
        "chunks": len(chunks),
        "embeddings": n_emb,
    }


# --- Protocol schemas ---

class CriarCasoRequest(BaseModel):
    titulo: str = Field(..., min_length=10, description="Título do caso (mín. 10 chars)")
    descricao: str = Field(..., min_length=1)
    contexto_fiscal: str = Field(..., min_length=1)


class SubmeterPassoRequest(BaseModel):
    dados: dict = Field(..., description="Dados do passo conforme campos obrigatórios")
    acao: str = Field("avancar", description="'avancar' ou 'voltar'")


class ConfirmarCarimboRequest(BaseModel):
    alert_id: int
    justificativa: str = Field(..., min_length=20)


_protocol_engine = ProtocolStateEngine()
_carimbo_detector = DetectorCarimbo()


def _case_estado_to_dict(estado: CaseEstado) -> dict:
    return {
        "case_id": estado.case_id,
        "titulo": estado.titulo,
        "status": estado.status,
        "passo_atual": estado.passo_atual,
        "steps": {
            str(p): {"dados": v["dados"], "concluido": v["concluido"]}
            for p, v in estado.steps.items()
        },
        "historico": estado.historico,
        "created_at": estado.created_at,
        "updated_at": estado.updated_at,
    }


# --- Protocol endpoints ---

@app.post("/v1/cases", status_code=201)
async def criar_caso(req: CriarCasoRequest):
    """Cria um novo caso protocolar em P1/rascunho."""
    logger.info("POST /v1/cases titulo=%s", req.titulo[:60])
    try:
        case_id = _protocol_engine.criar_caso(
            titulo=req.titulo,
            descricao=req.descricao,
            contexto_fiscal=req.contexto_fiscal,
        )
    except ProtocolError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Erro em /v1/cases: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return {"case_id": case_id, "status": "rascunho", "passo_atual": 1}


@app.get("/v1/cases/{case_id}")
async def get_caso(case_id: int):
    """Retorna o estado completo do caso com histórico."""
    logger.info("GET /v1/cases/%d", case_id)
    try:
        estado = _protocol_engine.get_estado(case_id)
    except ProtocolError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em GET /v1/cases/%d: %s", case_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return _case_estado_to_dict(estado)


@app.post("/v1/cases/{case_id}/steps/{passo}")
async def submeter_passo(case_id: int, passo: int, req: SubmeterPassoRequest):
    """
    Submete dados de um passo e avança/retrocede o protocolo.
    No P6, executa DetectorCarimbo automaticamente se dados contiverem
    'texto_decisao' e 'texto_recomendacao'.
    """
    logger.info("POST /v1/cases/%d/steps/%d acao=%s", case_id, passo, req.acao)
    try:
        if req.acao == "voltar":
            step = _protocol_engine.voltar(case_id, passo)
            return {
                "case_id": case_id,
                "passo": step.passo,
                "concluido": step.concluido,
                "proximo_passo": step.proximo_passo,
                "carimbo": None,
            }

        step = _protocol_engine.avancar(case_id, passo, req.dados)

        # Detector de carimbo ativado no P7 (decisão final vs recomendação P6)
        carimbo_result = None
        if passo == 7:
            texto_decisao = req.dados.get("decisao_final", "")
            # Buscar recomendação do P6 para comparação
            try:
                estado = _protocol_engine.get_estado(case_id)
                p6_dados = estado.steps.get(6, {}).get("dados", {})
                if isinstance(p6_dados, dict):
                    texto_recomendacao = p6_dados.get("recomendacao", "")
                else:
                    texto_recomendacao = ""
            except Exception:
                texto_recomendacao = ""

            if texto_decisao and texto_recomendacao:
                try:
                    cr = _carimbo_detector.verificar(
                        case_id=case_id,
                        passo=passo,
                        texto_decisao=texto_decisao,
                        texto_recomendacao=texto_recomendacao,
                    )
                    carimbo_result = {
                        "score_similaridade": cr.score_similaridade,
                        "alerta": cr.alerta,
                        "mensagem": cr.mensagem,
                        "alert_id": cr.alert_id,
                    }
                except Exception as e:
                    logger.warning("Carimbo check falhou (não bloqueante): %s", e)

        return {
            "case_id": case_id,
            "passo": step.passo,
            "concluido": step.concluido,
            "proximo_passo": step.proximo_passo,
            "carimbo": carimbo_result,
        }

    except ProtocolError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Erro em POST /v1/cases/%d/steps/%d: %s", case_id, passo, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/cases/{case_id}/carimbo/confirmar")
async def confirmar_carimbo(case_id: int, req: ConfirmarCarimboRequest):
    """Confirma alerta de carimbo com justificativa do gestor (mín. 20 chars)."""
    logger.info("POST /v1/cases/%d/carimbo/confirmar alert_id=%d", case_id, req.alert_id)
    try:
        _carimbo_detector.confirmar(req.alert_id, req.justificativa)
    except CarimboConfirmacaoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em confirmar_carimbo: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return {"confirmado": True, "alert_id": req.alert_id}


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class GerarOutputRequest(BaseModel):
    case_id: int
    classe: str = Field(..., description="alerta|nota_trabalho|recomendacao_formal|dossie_decisao|material_compartilhavel")
    stakeholders: Optional[list[str]] = Field(None, description="Lista de stakeholder_tipo")
    # Para alerta (C1)
    titulo: Optional[str] = None
    contexto: Optional[str] = None
    materialidade: Optional[int] = Field(None, ge=1, le=5)
    # Para C2/C3 — AnaliseResult embutido
    query: Optional[str] = None
    # Para C5 — base output_id
    output_base_id: Optional[int] = None
    # Para C2/C3 — modelo a usar na análise
    model: str = Field(MODEL_DEV)


class AprovarOutputRequest(BaseModel):
    aprovado_por: str = Field(..., min_length=2)
    observacao: Optional[str] = None


def _output_result_to_dict(r: OutputResult) -> dict:
    return {
        "id": r.id,
        "case_id": r.case_id,
        "passo_origem": r.passo_origem,
        "classe": r.classe.value,
        "status": r.status.value,
        "titulo": r.titulo,
        "conteudo": r.conteudo,
        "materialidade": r.materialidade,
        "disclaimer": r.disclaimer,
        "versao_prompt": r.versao_prompt,
        "versao_base": r.versao_base,
        "created_at": r.created_at,
        "stakeholder_views": [
            {
                "stakeholder": v.stakeholder.value,
                "resumo": v.resumo,
                "campos_visiveis": v.campos_visiveis,
            }
            for v in r.stakeholder_views
        ],
    }


_output_engine = OutputEngine()


# ---------------------------------------------------------------------------
# Output endpoints
# ---------------------------------------------------------------------------

@app.post("/v1/outputs", status_code=201)
async def gerar_output(req: GerarOutputRequest):
    """
    Gera um output acionável (C1–C5).
    - C1 (alerta): requer titulo, contexto, materialidade
    - C2 (nota_trabalho): requer query — executa análise cognitiva internamente
    - C3 (recomendacao_formal): requer query
    - C4 (dossie_decisao): requer P7 concluído no caso
    - C5 (material_compartilhavel): requer output_base_id com C3/C4 aprovado
    """
    logger.info("POST /v1/outputs case_id=%d classe=%s", req.case_id, req.classe)

    try:
        classe = OutputClass(req.classe)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"classe inválida: {req.classe}")

    stk_list: Optional[list[StakeholderTipo]] = None
    if req.stakeholders:
        try:
            stk_list = [StakeholderTipo(s) for s in req.stakeholders]
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"stakeholder inválido: {e}")

    try:
        if classe == OutputClass.ALERTA:
            if not req.titulo or not req.contexto or req.materialidade is None:
                raise HTTPException(
                    status_code=422,
                    detail="C1 (alerta) requer titulo, contexto e materialidade"
                )
            result = _output_engine.gerar_alerta(
                case_id=req.case_id,
                passo=3,
                titulo=req.titulo,
                contexto=req.contexto,
                materialidade=req.materialidade,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.NOTA_TRABALHO:
            if not req.query:
                raise HTTPException(status_code=422, detail="C2 requer query")
            analise = analisar(query=req.query, top_k=3, model=req.model)
            result = _output_engine.gerar_nota_trabalho(
                case_id=req.case_id,
                analise_result=analise,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.RECOMENDACAO_FORMAL:
            if not req.query:
                raise HTTPException(status_code=422, detail="C3 requer query")
            analise = analisar(query=req.query, top_k=3, model=req.model)
            result = _output_engine.gerar_recomendacao_formal(
                case_id=req.case_id,
                analise_result=analise,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.DOSSIE_DECISAO:
            result = _output_engine.gerar_dossie(
                case_id=req.case_id,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.MATERIAL_COMPARTILHAVEL:
            if not req.output_base_id:
                raise HTTPException(status_code=422, detail="C5 requer output_base_id")
            if not stk_list:
                raise HTTPException(status_code=422, detail="C5 requer ao menos um stakeholder")
            result = _output_engine.gerar_material_compartilhavel(
                output_id=req.output_base_id,
                stakeholders=stk_list,
            )
        else:
            raise HTTPException(status_code=422, detail="Classe não suportada")

    except HTTPException:
        raise
    except OutputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro em POST /v1/outputs: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return _output_result_to_dict(result)


@app.get("/v1/outputs/{output_id}")
async def get_output(output_id: int):
    """Retorna output completo com views por stakeholder."""
    logger.info("GET /v1/outputs/%d", output_id)
    try:
        from src.outputs.engine import _get_conn, _load_output
        conn = _get_conn()
        try:
            result = _load_output(conn, output_id)
        finally:
            conn.close()
    except OutputError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em GET /v1/outputs/%d: %s", output_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return _output_result_to_dict(result)


@app.post("/v1/outputs/{output_id}/aprovar")
async def aprovar_output(output_id: int, req: AprovarOutputRequest):
    """
    Aprova um output. Status gerado → aprovado.
    C3 e C5 exigem aprovação antes de publicação.
    """
    logger.info("POST /v1/outputs/%d/aprovar por=%s", output_id, req.aprovado_por)
    try:
        result = _output_engine.aprovar(
            output_id=output_id,
            aprovado_por=req.aprovado_por,
            observacao=req.observacao,
        )
    except OutputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro em aprovar_output: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return _output_result_to_dict(result)


@app.get("/v1/cases/{case_id}/outputs")
async def listar_outputs_caso(case_id: int):
    """Lista todos os outputs de um caso, ordenados por materialidade DESC."""
    logger.info("GET /v1/cases/%d/outputs", case_id)
    try:
        outputs = _output_engine.listar_por_caso(case_id)
    except Exception as e:
        logger.error("Erro em GET /v1/cases/%d/outputs: %s", case_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return [_output_result_to_dict(r) for r in outputs]


# ---------------------------------------------------------------------------
# Observability schemas
# ---------------------------------------------------------------------------

class BaselineRequest(BaseModel):
    prompt_version: str
    model_id: str


class RegressionRequest(BaseModel):
    prompt_version: str
    model_id: str
    baseline_version: str


class ResolverDriftRequest(BaseModel):
    observacao: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Observability endpoints
# ---------------------------------------------------------------------------

@app.get("/v1/observability/metrics")
async def get_metrics(
    days: int = Query(7, ge=1, le=90),
    prompt_version: Optional[str] = Query(None),
):
    """Métricas diárias agregadas dos últimos N dias."""
    logger.info("GET /v1/observability/metrics days=%d pv=%s", days, prompt_version)
    try:
        import psycopg2 as _psycopg2
        url = os.getenv("DATABASE_URL")
        conn = _psycopg2.connect(url)
        cur = conn.cursor()
        sql = """
            SELECT data_referencia, prompt_version, model_id, total_interacoes,
                   avg_latencia_ms, p95_latencia_ms, pct_scoring_alto, pct_contra_tese,
                   pct_grounding_presente, taxa_alucinacao,
                   taxa_bloqueio_m1, taxa_bloqueio_m2, taxa_bloqueio_m3, taxa_bloqueio_m4
            FROM ai_metrics_daily
            WHERE data_referencia >= CURRENT_DATE - %s::interval
        """
        params: list = [f"{days} days"]
        if prompt_version:
            sql += " AND prompt_version = %s"
            params.append(prompt_version)
        sql += " ORDER BY data_referencia DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = ["data_referencia", "prompt_version", "model_id", "total_interacoes",
                "avg_latencia_ms", "p95_latencia_ms", "pct_scoring_alto", "pct_contra_tese",
                "pct_grounding_presente", "taxa_alucinacao",
                "taxa_bloqueio_m1", "taxa_bloqueio_m2", "taxa_bloqueio_m3", "taxa_bloqueio_m4"]
        result = [dict(zip(cols, [str(v) if hasattr(v, "isoformat") else v for v in row]))
                  for row in rows]
        # Resumo agregado
        if rows:
            def avg(col):
                vals = [r[cols.index(col)] for r in rows if r[cols.index(col)] is not None]
                return sum(vals) / len(vals) if vals else None
            resumo = {
                "total_interacoes": sum(r[3] for r in rows),
                "avg_latencia_ms": avg("avg_latencia_ms"),
                "p95_latencia_ms": avg("p95_latencia_ms"),
                "pct_scoring_alto": avg("pct_scoring_alto"),
                "taxa_alucinacao": avg("taxa_alucinacao"),
            }
        else:
            resumo = {}
        cur.close()
        conn.close()
    except Exception as e:
        logger.error("Erro em /v1/observability/metrics: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return {"metrics": result, "resumo": resumo, "days": days}


@app.get("/v1/observability/drift")
async def get_drift_alerts(
    prompt_version: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
):
    """Lista drift alerts ativos (resolvido=False)."""
    logger.info("GET /v1/observability/drift pv=%s", prompt_version)
    try:
        import psycopg2 as _psycopg2
        url = os.getenv("DATABASE_URL")
        conn = _psycopg2.connect(url)
        cur = conn.cursor()
        sql = """
            SELECT id, detectado_em, prompt_version, model_id, metrica,
                   valor_baseline, valor_atual, desvios_padrao, resolvido, observacao
            FROM drift_alerts
            WHERE resolvido = FALSE
        """
        params: list = []
        if prompt_version:
            sql += " AND prompt_version = %s"
            params.append(prompt_version)
        if model_id:
            sql += " AND model_id = %s"
            params.append(model_id)
        sql += " ORDER BY detectado_em DESC"
        cur.execute(sql, params)
        cols = ["id", "detectado_em", "prompt_version", "model_id", "metrica",
                "valor_baseline", "valor_atual", "desvios_padrao", "resolvido", "observacao"]
        result = [dict(zip(cols, [str(v) if hasattr(v, "isoformat") else v for v in row]))
                  for row in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        logger.error("Erro em /v1/observability/drift: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/v1/observability/drift/{alert_id}/resolver")
async def resolver_drift(alert_id: int, req: ResolverDriftRequest):
    """Resolve um drift alert com observação."""
    logger.info("POST /v1/observability/drift/%d/resolver", alert_id)
    try:
        from src.observability.drift import DriftDetector, DriftDetectorError
        DriftDetector().resolver_alert(alert_id, req.observacao)
    except DriftDetectorError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em resolver_drift: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return {"resolvido": True, "alert_id": alert_id}


@app.post("/v1/observability/baseline", status_code=201)
async def registrar_baseline(req: BaselineRequest):
    """Registra baseline de métricas para a versão de prompt/modelo especificada."""
    logger.info("POST /v1/observability/baseline pv=%s model=%s", req.prompt_version, req.model_id)
    try:
        from src.observability.drift import DriftDetector, DriftDetectorError
        result = DriftDetector().registrar_baseline(req.prompt_version, req.model_id)
    except DriftDetectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro em registrar_baseline: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/v1/observability/regression")
async def executar_regression(req: RegressionRequest):
    """
    Executa regression testing sobre o dataset de avaliação.
    Timeout do cliente deve ser ≥ 120s — faz chamadas reais ao LLM.
    """
    logger.info("POST /v1/observability/regression pv=%s model=%s", req.prompt_version, req.model_id)
    try:
        from src.observability.regression import RegressionRunner
        result = RegressionRunner().executar(
            prompt_version=req.prompt_version,
            model_id=req.model_id,
            baseline_version=req.baseline_version,
        )
    except Exception as e:
        logger.error("Erro em executar_regression: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "aprovado": result.aprovado,
        "precisao_citacao": result.precisao_citacao,
        "taxa_alucinacao": result.taxa_alucinacao,
        "acuracia_recomendacao": result.acuracia_recomendacao,
        "latencia_p95": result.latencia_p95,
        "cobertura_contra_tese": result.cobertura_contra_tese,
        "detalhes": result.detalhes,
    }
