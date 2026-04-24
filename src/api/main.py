"""
api/main.py — FastAPI: 18 endpoints do motor cognitivo Tribus-AI.

POST /v1/analyze                                  — análise tributária completa
GET  /v1/chunks                                   — busca RAG direta
GET  /v1/health                                   — status do sistema
POST /v1/ingest/check-duplicate                   — verificar duplicidade antes de ingestão
POST /v1/ingest/upload                            — ingestão assíncrona de PDF (retorna job_id)
GET  /v1/ingest/jobs/{job_id}                     — polling de status do job de ingestão
POST /v1/cases                                    — criar caso protocolo
GET  /v1/cases                                    — listar todos os casos
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
GET  /v1/billing/mau                              — MAU por tenant/mês (metering)
POST /v1/webhooks/asaas                           — webhook de billing Asaas
"""

# === VALIDAÇÃO DE STARTUP — deve ser a primeira coisa a executar ===
# Falha com mensagem clara antes de qualquer import de negócio.
# Evita o padrão: ValueError silencioso → API não sobe → nginx 502.
from dotenv import load_dotenv as _load_dotenv_early
_load_dotenv_early()
from src.startup_validation import validate_env as _validate_env
_validate_env()
# ====================================================================

import hashlib
import logging
import os
import re
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import psycopg2
from dotenv import load_dotenv

from src.db.pool import get_conn, put_conn
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from src.api.auth_api import verificar_token_api, verificar_sessao
from auth import autenticar, buscar_usuario_por_email, gerar_hash_senha, gerar_token
from src.email_service import (
    enviar_email_confirmacao,
    enviar_email_falha_pagamento,
)

from src.cognitive.engine import MODEL_DEV, AnaliseResult, analisar
from src.cognitive.detector_carimbo import detectar_carimbo as _detectar_carimbo_lexico
from src.rag.vigencia_checker import alertas_para_dict
from src.ingest.chunker import chunkar_documento
from src.protocol.carimbo import CarimboConfirmacaoError, DetectorCarimbo
from src.protocol.engine import CaseEstado, ProtocolError, ProtocolStateEngine
from src.ingest.embedder import gerar_e_persistir_embeddings
from src.ingest.loader import EXTENSOES_SUPORTADAS, DocumentoNorma, extrair_texto_bytes
from src.outputs.engine import OutputClass, OutputEngine, OutputError, OutputResult
from src.outputs.stakeholders import StakeholderTipo
from src.quality.engine import QualidadeStatus
from src.rag.retriever import ChunkResultado, retrieve
from src.billing.mau_tracker import registrar_evento_mau

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"

_ingest_jobs: dict[str, dict] = {}

# --- SEC-07: MIME validation via magic bytes ---
_MAGIC_BYTES: dict[str, list[bytes]] = {
    ".pdf":  [b"%PDF"],
    ".docx": [b"PK\x03\x04"],
    ".xlsx": [b"PK\x03\x04"],
    ".html": [b"<!DOCTYPE", b"<html", b"<HTML", b"<!doctype"],
    ".txt":  [],  # sem magic bytes — qualquer texto é aceito
    ".md":   [],
    ".csv":  [],
}

def _validar_mime_bytes(header: bytes, ext: str) -> bool:
    """Valida os magic bytes do arquivo contra a extensão declarada. SEC-07."""
    permitidos = _MAGIC_BYTES.get(ext)
    if permitidos is None:
        return False  # extensão não mapeada
    if not permitidos:
        return True   # formatos texto (txt, md, csv) não têm magic bytes
    return any(header.startswith(magic) for magic in permitidos)

@asynccontextmanager
async def lifespan(app):
    from src.tasks.scheduler import create_scheduler
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Tribus-AI API",
    description="Motor cognitivo para análise da Reforma Tributária brasileira",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://orbis.tax", "https://www.orbis.tax", "http://localhost:8521", "http://localhost:3000", "http://localhost:3001", "http://localhost:3002"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rate limiting (slowapi) ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.on_event("shutdown")
def _shutdown_pool():
    from src.db.pool import close_pool
    close_pool()


# --- Schemas de entrada ---

class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Consulta tributária")
    norma_filter: Optional[list[str]] = Field(None, description="Filtrar por normas: EC132_2023, LC214_2025, LC227_2026")
    excluir_tipos: Optional[list[str]] = Field(["Outro"], description="Tipos de norma a excluir do RAG (padrão: [\"Outro\"])")
    top_k: int = Field(5, ge=1, le=10)
    model: str = Field(MODEL_DEV)
    decompose: bool = Field(False, description="Ativar decomposição de sub-perguntas para queries complexas")
    case_id: Optional[int] = Field(None, description="ID do caso (steps 1→6) para injetar contexto dos passos anteriores")
    user_id: Optional[str] = Field(None, description="UUID do usuário autenticado (tenant isolation)")
    metodos_selecionados: list[str] = Field([], description="IDs dos métodos de análise selecionados no P1 (máx. 4)")
    criticidade: str = Field("media", description="Nível de criticidade do caso: baixa | media | alta | extrema")
    premissas: list[str] = Field([], description="Premissas regulatórias declaradas no P2 (mín. 3)")
    riscos_fiscais: list[str] = Field([], description="Riscos fiscais declarados no P2 (mín. 3)")
    fatos_cliente: dict = Field({}, description="Qualificação fática do cliente (G23): cnae, regime, UFs, tipo operação, faturamento")


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
        "forca_corrente_contraria": resultado.forca_corrente_contraria,
        "risco_adocao": resultado.risco_adocao,
        "scoring_confianca": resultado.scoring_confianca,
        "alertas_vigencia": alertas_para_dict(resultado.alertas_vigencia),
        "vigencia_ok": len(resultado.alertas_vigencia) == 0,
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
        "retrieval_strategy": resultado.retrieval_strategy,
        "saidas_stakeholders": resultado.saidas_stakeholders,
        "criticidade": resultado.criticidade,
        "criticidade_justificativa": resultado.criticidade_justificativa,
        "criticidade_impacto": resultado.criticidade_impacto,
    }


# --- Endpoints ---

def _carregar_contexto_caso(case_id: int) -> Optional[dict]:
    """Carrega dados dos passos anteriores do caso para injeção no LLM."""
    try:
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT passo, dados FROM case_steps WHERE case_id = %s AND concluido = TRUE ORDER BY passo",
                (case_id,),
            )
            rows = cur.fetchall()
            cur.close()
        finally:
            put_conn(conn)
        if not rows:
            return None
        import json as _json
        contexto: dict = {}
        for passo, dados_raw in rows:
            if isinstance(dados_raw, str):
                dados_raw = _json.loads(dados_raw)
            contexto[passo] = dados_raw
        logger.info("Contexto do caso %d carregado: passos %s", case_id, list(contexto.keys()))
        return contexto
    except Exception as e:
        logger.warning("Falha ao carregar contexto do caso %d: %s", case_id, e)
        return None


def _buscar_casos_similares(query: str, case_id_atual: Optional[int] = None, top_k: int = 3) -> list[dict]:
    """Busca casos concluídos similares para retroalimentação do LLM.

    Critérios de qualidade:
    - Caso com status 'aprendizado_extraido' (Passo 6 completo)
    - dados_qualidade = 'verde' no Passo 2
    - Exclui o caso atual (se informado)

    Usa embedding Voyage da query para similaridade cosine contra
    a concatenação de titulo+descricao dos casos concluídos.
    """
    try:
        from src.rag.retriever import _embed_query, EMBEDDING_MODEL
        import json as _json

        vetor_query = _embed_query(query)
        vetor_str = "[" + ",".join(str(v) for v in vetor_query) + "]"

        conn = get_conn()
        try:
            cur = conn.cursor()
            # Buscar casos concluídos com qualidade verde
            # Usa similaridade cosine entre o embedding da query e
            # o embedding gerado on-the-fly do titulo+descricao do caso
            sql = """
                WITH casos_concluidos AS (
                    SELECT
                        c.id AS case_id,
                        c.titulo,
                        s1.dados AS dados_step1,
                        s2.dados AS dados_step2,
                        s5.dados AS dados_step5,
                        s6.dados AS dados_step6
                    FROM cases c
                    JOIN case_steps s1 ON s1.case_id = c.id AND s1.passo = 1 AND s1.concluido = TRUE
                    JOIN case_steps s2 ON s2.case_id = c.id AND s2.passo = 2 AND s2.concluido = TRUE
                    JOIN case_steps s5 ON s5.case_id = c.id AND s5.passo = 5 AND s5.concluido = TRUE
                    JOIN case_steps s6 ON s6.case_id = c.id AND s6.passo = 6 AND s6.concluido = TRUE
                    WHERE c.status = 'aprendizado_extraido'
                      AND (s2.dados->>'dados_qualidade') = 'verde'
            """
            params: list = []
            if case_id_atual:
                sql += "      AND c.id != %s\n"
                params.append(case_id_atual)
            sql += """
                )
                SELECT case_id, titulo, dados_step1, dados_step2, dados_step5, dados_step6
                FROM casos_concluidos
                ORDER BY case_id DESC
                LIMIT %s
            """
            params.append(top_k * 3)  # fetch more, rank below

            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()
        finally:
            put_conn(conn)

        if not rows:
            logger.info("Nenhum caso concluído com qualidade verde encontrado para retroalimentação.")
            return []

        # Ranking por similaridade textual simples (sem embedding extra para evitar latência)
        # Usa overlap de palavras-chave entre query e titulo+descricao do caso
        import re as _re
        query_words = set(_re.findall(r'\w{4,}', query.lower()))

        scored = []
        for case_id, titulo, d1, d2, d5, d6 in rows:
            if isinstance(d1, str):
                d1 = _json.loads(d1)
            if isinstance(d2, str):
                d2 = _json.loads(d2)
            if isinstance(d5, str):
                d5 = _json.loads(d5)
            if isinstance(d6, str):
                d6 = _json.loads(d6)

            caso_text = f"{titulo} {d1.get('descricao', '')} {' '.join(d1.get('premissas', []))}".lower()
            caso_words = set(_re.findall(r'\w{4,}', caso_text))
            overlap = len(query_words & caso_words)
            if overlap < 2:
                continue

            scored.append({
                "case_id": case_id,
                "titulo": titulo,
                "score": overlap,
                "premissas": d1.get("premissas", []),
                "riscos": d2.get("riscos", []),
                "decisao_final": d5.get("decisao_final", ""),
                "resultado_real": d6.get("resultado_real", ""),
                "aprendizado": d6.get("aprendizado_extraido", ""),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        resultado = scored[:top_k]
        logger.info("Retroalimentação: %d caso(s) similar(es) encontrado(s) para query.", len(resultado))
        return resultado

    except Exception as e:
        logger.warning("Falha na busca de casos similares (não-bloqueante): %s", e)
        return []


@app.post("/v1/analyze", dependencies=[Depends(verificar_token_api)])
@limiter.limit("20/minute")
def analyze(request: Request, req: AnalyzeRequest):
    """
    Análise tributária completa (Steps 1→3).
    Retorna 400 se a qualidade for VERMELHO (bloqueado).
    Quando case_id é informado, injeta dados dos passos anteriores como contexto.
    """
    logger.info("POST /v1/analyze query=%s case_id=%s", req.query[:80], req.case_id)

    contexto_caso = None
    if req.case_id:
        contexto_caso = _carregar_contexto_caso(req.case_id)

    # Retroalimentação: buscar casos concluídos similares
    casos_similares = _buscar_casos_similares(req.query, case_id_atual=req.case_id)

    try:
        resultado = analisar(
            query=req.query,
            top_k=req.top_k,
            norma_filter=req.norma_filter,
            excluir_tipos=req.excluir_tipos if req.excluir_tipos is not None else ["Outro"],
            model=req.model,
            decompose=req.decompose,
            contexto_caso=contexto_caso,
            casos_similares=casos_similares,
            user_id=req.user_id,
            metodos_selecionados=req.metodos_selecionados,
            criticidade=req.criticidade,
            premissas=req.premissas,
            riscos_fiscais=req.riscos_fiscais,
            fatos_cliente=req.fatos_cliente or {},
        )
    except Exception as e:
        logger.error("Erro interno em /v1/analyze: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")

    if resultado.qualidade.status == QualidadeStatus.VERMELHO:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Consulta bloqueada pelo DataQualityEngine",
                "bloqueios": resultado.qualidade.bloqueios,
                "qualidade_status": "vermelho",
            },
        )

    # Metering MAU (G26, DEC-08) — falha silenciosa, nunca bloqueia a análise
    try:
        registrar_evento_mau(user_id=req.user_id)
    except Exception:
        pass

    return _analise_to_dict(resultado)


@app.get("/v1/chunks", dependencies=[Depends(verificar_token_api)])
def get_chunks(
    q: str = Query(..., description="Texto da busca"),
    top_k: int = Query(5, ge=1, le=10),
    norma: Optional[str] = Query(None, description="Código da norma para filtrar"),
):
    """Busca RAG direta sem análise cognitiva."""
    logger.info("GET /v1/chunks q=%s top_k=%d norma=%s", q[:60], top_k, norma)
    try:
        norma_filter = [norma] if norma else None
        chunks = retrieve(q, top_k=top_k, norma_filter=norma_filter, excluir_tipos=["Outro"])
    except Exception as e:
        logger.error("Erro em /v1/chunks: %s", e)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")

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
def health():
    """Status do sistema com contagens e lista de normas disponíveis."""
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM chunks")
        chunks_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM embeddings")
        embeddings_total = cur.fetchone()[0]
        cur.execute("SELECT codigo, nome FROM normas WHERE vigente = TRUE ORDER BY ano, codigo")
        normas = [{"codigo": r[0], "nome": r[1]} for r in cur.fetchall()]
        cur.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Banco inacessível: {e}")
    finally:
        if conn:
            put_conn(conn)

    return {
        "status": "ok",
        "chunks_total": chunks_total,
        "embeddings_total": embeddings_total,
        "normas": normas,
    }


class LoginRequest(BaseModel):
    email: str = Field(..., description="E-mail do usuário")
    senha: str = Field(..., description="Senha do usuário")


@app.post("/v1/auth/login")
@limiter.limit("5/minute")
def login(request: Request, req: LoginRequest):
    """
    Autenticação — retorna JWT + dados do usuário.
    Público (sem X-API-Key). Rate-limited: 5 req/min por IP.
    """
    token, erro = autenticar(req.email, req.senha)
    if erro or not token:
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    usuario = buscar_usuario_por_email(req.email)
    if not usuario:
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id":               str(usuario.id),
            "email":            usuario.email,
            "nome":             usuario.nome,
            "perfil":           usuario.perfil,
            "tenant_id":        str(getattr(usuario, "tenant_id", None)) if getattr(usuario, "tenant_id", None) else None,
            "onboarding_step":  0,
        },
    }


@app.get("/v1/auth/me", dependencies=[Depends(verificar_token_api), Depends(verificar_sessao)])
def auth_me(user_id: str = Query(...)):
    """Retorna dados do usuário incluindo onboarding_step e dados de trial."""
    logger.info("GET /v1/auth/me user_id=%s", user_id)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT u.id, u.email, u.nome, u.perfil, u.tenant_id, u.onboarding_step,
                      t.subscription_status, t.trial_ends_at
               FROM users u
               LEFT JOIN tenants t ON t.id = u.tenant_id
               WHERE u.id = %s LIMIT 1""",
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        trial_ends = row[7]
        return {
            "id": str(row[0]),
            "email": row[1],
            "nome": row[2],
            "perfil": row[3],
            "tenant_id": str(row[4]) if row[4] else None,
            "onboarding_step": row[5] if row[5] is not None else 0,
            "subscription_status": row[6],
            "trial_ends_at": trial_ends.isoformat() if trial_ends else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro em /v1/auth/me: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


class OnboardingRequest(BaseModel):
    user_id: str
    tipo_atuacao: str
    cargo_responsavel: str
    onboarding_step: int = 1


@app.patch("/v1/auth/onboarding", dependencies=[Depends(verificar_token_api)])
def auth_onboarding(req: OnboardingRequest):
    """Salva dados de progressive profiling e avança onboarding_step."""
    logger.info("PATCH /v1/auth/onboarding user_id=%s step=%d", req.user_id, req.onboarding_step)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """UPDATE users
               SET tipo_atuacao = %s, cargo_responsavel = %s, onboarding_step = %s
               WHERE id = %s""",
            (req.tipo_atuacao, req.cargo_responsavel, req.onboarding_step, req.user_id),
        )
        conn.commit()
        cur.close()
        return {"ok": True}
    except Exception as e:
        logger.error("Erro em /v1/auth/onboarding: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.get("/v1/credits", dependencies=[Depends(verificar_token_api)])
def get_credits():
    """Status de creditos de API com alerta quando saldo <= US$0.50."""
    try:
        from src.observability.usage import obter_detalhamento, obter_status_creditos
        status = obter_status_creditos()
        detalhamento = obter_detalhamento()
    except Exception as e:
        logger.error("Erro em /v1/credits: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {
        "total_gasto": status.total_gasto,
        "limite": status.limite,
        "saldo_restante": status.saldo_restante,
        "alerta": status.alerta,
        "mensagem": status.mensagem,
        "detalhamento": detalhamento,
    }


def _processar_ingest_background(job_id: str, conteudo: bytes, filename: str,
                                  nome: str, tipo: str, codigo: str):
    """Processa ingestão de documento em background (extração + chunking + embeddings)."""
    try:
        _ingest_jobs[job_id]["status"] = JobStatus.PROCESSING
        file_hash = hashlib.md5(conteudo).hexdigest()

        try:
            texto = extrair_texto_bytes(conteudo, filename)
        except ValueError as e:
            _ingest_jobs[job_id]["status"] = JobStatus.ERROR
            _ingest_jobs[job_id]["message"] = str(e)
            return

        if not texto.strip():
            _ingest_jobs[job_id]["status"] = JobStatus.ERROR
            _ingest_jobs[job_id]["message"] = "Documento sem texto extraível"
            return

        doc = DocumentoNorma(
            codigo=codigo,
            nome=nome,
            tipo=tipo,
            numero="0",
            ano=2024,
            arquivo=filename,
            texto=texto,
        )

        conn = get_conn()
        try:
            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO normas (codigo, nome, tipo, numero, ano, arquivo, file_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo) DO UPDATE SET
                    nome = EXCLUDED.nome, arquivo = EXCLUDED.arquivo,
                    file_hash = EXCLUDED.file_hash, vigente = TRUE
                RETURNING id
                """,
                (doc.codigo, doc.nome, doc.tipo, doc.numero, doc.ano, doc.arquivo, file_hash),
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
        finally:
            put_conn(conn)

        logger.info("Upload ingerido: %s | chunks=%d | embeddings=%d", nome, len(chunks), n_emb)
        _ingest_jobs[job_id]["status"] = JobStatus.DONE
        _ingest_jobs[job_id]["message"] = "Documento incluído com sucesso"
        _ingest_jobs[job_id]["result"] = {
            "norma_id": norma_id,
            "nome": nome,
            "codigo": codigo,
            "chunks": len(chunks),
            "embeddings": n_emb,
        }
    except Exception as e:
        logger.error("Erro em ingest background job=%s: %s", job_id, e, exc_info=True)
        _ingest_jobs[job_id]["status"] = JobStatus.ERROR
        _ingest_jobs[job_id]["message"] = str(e)


@app.post("/v1/ingest/check-duplicate", dependencies=[Depends(verificar_token_api)])
def check_duplicate(file: UploadFile = File(...)):
    """Verifica se arquivo já foi ingestado por nome ou hash MD5."""
    conteudo = file.file.read()
    file_hash = hashlib.md5(conteudo).hexdigest()
    filename = file.filename or ""

    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id, nome, arquivo FROM normas WHERE file_hash = %s", (file_hash,))
        row_hash = cur.fetchone()

        cur.execute("SELECT id, nome, arquivo FROM normas WHERE arquivo ILIKE %s", (f"%{filename}%",))
        row_nome = cur.fetchone()

        cur.close()
    finally:
        put_conn(conn)

    if row_hash:
        return {
            "duplicado": True,
            "tipo": "conteudo",
            "mensagem": f"Este documento já está na base como '{row_hash[1]}'.",
            "norma_id": row_hash[0],
        }
    if row_nome:
        return {
            "duplicado": True,
            "tipo": "nome",
            "mensagem": f"Um arquivo com este nome já foi incluído como '{row_nome[1]}'.",
            "norma_id": row_nome[0],
        }

    return {"duplicado": False, "mensagem": ""}


@app.post("/v1/ingest/upload", dependencies=[Depends(verificar_token_api)])
@limiter.limit("10/minute")
def ingest_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Arquivo a ingerir (PDF, DOCX, XLSX, HTML, TXT, MD, CSV)"),
    nome: str = Form(..., description="Nome do documento (ex: IN RFB 2184/2024)"),
    tipo: str = Form(..., description="Tipo: IN | Resolucao | Parecer | Manual | Outro"),
):
    """
    Ingestão assíncrona de documento. Retorna job_id para polling via GET /v1/ingest/jobs/{job_id}.
    Formatos aceitos: PDF, DOCX, XLSX, HTML, TXT, MD, CSV.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo ausente")
    ext = Path(file.filename).suffix.lower()
    if ext not in EXTENSOES_SUPORTADAS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato '{ext}' não suportado. Aceitos: {', '.join(sorted(EXTENSOES_SUPORTADAS))}",
        )

    logger.info("POST /v1/ingest/upload nome=%s tipo=%s", nome, tipo)

    # SEC-07: validar magic bytes contra extensão declarada
    header_bytes = file.file.read(512)
    if not _validar_mime_bytes(header_bytes, ext):
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido.")
    file.file.seek(0)

    codigo = re.sub(r"[^A-Za-z0-9]", "_", nome)[:30].strip("_")
    conteudo = file.file.read()

    # SEC-07: limite de tamanho server-side (50 MB)
    if len(conteudo) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande. Máximo: 50 MB.")

    job_id = str(uuid.uuid4())
    _ingest_jobs[job_id] = {"status": JobStatus.PENDING, "message": "", "result": None}

    background_tasks.add_task(
        _processar_ingest_background, job_id, conteudo, file.filename, nome, tipo, codigo
    )

    return {"job_id": job_id, "status": JobStatus.PENDING}


@app.get("/v1/ingest/jobs/{job_id}", dependencies=[Depends(verificar_token_api)])
def get_job_status(job_id: str):
    """Polling de status de um job de ingestão."""
    job = _ingest_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    resp = {"job_id": job_id, "status": job["status"], "message": job["message"]}
    if job["result"]:
        resp["result"] = job["result"]
    return resp


# --- Gerenciamento de normas ---

@app.get("/v1/ingest/normas", dependencies=[Depends(verificar_token_api)])
def listar_normas():
    """Lista todas as normas na base de conhecimento."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT n.id, n.codigo, n.nome, n.tipo, n.ano, n.vigente, n.created_at,
                   COUNT(c.id) AS total_chunks
            FROM normas n
            LEFT JOIN chunks c ON c.norma_id = n.id
            GROUP BY n.id
            ORDER BY n.created_at DESC
        """)
        rows = cur.fetchall()
        cur.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar normas: {e}")
    finally:
        put_conn(conn)

    return [
        {
            "id": r[0],
            "codigo": r[1],
            "nome": r[2],
            "tipo": r[3],
            "ano": r[4],
            "vigente": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
            "total_chunks": r[7],
        }
        for r in rows
    ]


@app.delete("/v1/ingest/normas/{norma_id}", dependencies=[Depends(verificar_token_api)])
def deletar_norma(norma_id: int):
    """
    Remove uma norma e todos os seus chunks/embeddings da base.
    Cascata: embeddings → chunks → norma.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Verificar se a norma existe
        cur.execute("SELECT id, nome, codigo FROM normas WHERE id = %s", (norma_id,))
        norma = cur.fetchone()
        if not norma:
            raise HTTPException(status_code=404, detail="Norma não encontrada")

        nome_norma = norma[1]
        codigo_norma = norma[2]

        # 1. Deletar embeddings (via CASCADE nos chunks, mas fazemos explícito para log)
        cur.execute("""
            DELETE FROM embeddings
            WHERE chunk_id IN (SELECT id FROM chunks WHERE norma_id = %s)
        """, (norma_id,))
        embeddings_removidos = cur.rowcount

        # 2. Deletar chunks
        cur.execute("DELETE FROM chunks WHERE norma_id = %s", (norma_id,))
        chunks_removidos = cur.rowcount

        # 3. Deletar norma
        cur.execute("DELETE FROM normas WHERE id = %s", (norma_id,))

        conn.commit()
        logger.info(
            "Norma removida: id=%d codigo=%s nome=%s (%d chunks, %d embeddings)",
            norma_id, codigo_norma, nome_norma, chunks_removidos, embeddings_removidos,
        )

        return {
            "removido": True,
            "norma_id": norma_id,
            "nome": nome_norma,
            "codigo": codigo_norma,
            "chunks_removidos": chunks_removidos,
            "embeddings_removidos": embeddings_removidos,
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao remover norma: {e}")
    finally:
        cur.close()
        put_conn(conn)


# --- Limites de casos por plano (migration 128) ---

_CASE_LIMITS: dict[str, int] = {
    "trial":        3,   # total durante o período de trial
    "starter":      10,  # por mês calendário
    "professional": 50,  # por mês calendário
    "enterprise":   -1,  # ilimitado
}


def _get_tenant_info_by_user(user_id: str, conn):
    """Retorna (tenant_id, subscription_status, plano, trial_ends_at) ou None."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT t.id, t.subscription_status, t.plano, t.trial_ends_at
               FROM users u JOIN tenants t ON t.id = u.tenant_id
               WHERE u.id = %s LIMIT 1""",
            (user_id,),
        )
        return cur.fetchone()


def _verificar_limite_casos(
    tenant_id: str,
    subscription_status: str,
    plano: str,
    trial_ends_at,
    conn,
) -> tuple:
    """
    Verifica se o tenant pode criar mais casos.

    Returns:
        (permitido: bool, usado: int, limite: int) — limite -1 = ilimitado
    """
    chave = "trial" if subscription_status == "trial" else (plano or "starter")
    limite = _CASE_LIMITS.get(chave, _CASE_LIMITS["starter"])

    if limite == -1:
        return True, 0, -1

    with conn.cursor() as cur:
        if subscription_status == "trial":
            cur.execute(
                "SELECT COUNT(*) FROM cases WHERE tenant_id = %s",
                (tenant_id,),
            )
        else:
            cur.execute(
                """SELECT COUNT(*) FROM cases
                   WHERE tenant_id = %s
                     AND created_at >= date_trunc('month', NOW())""",
                (tenant_id,),
            )
        usado = cur.fetchone()[0]

    return usado < limite, usado, limite


# --- Protocol schemas ---

class CriarCasoRequest(BaseModel):
    titulo: str = Field(..., min_length=10, description="Título do caso (mín. 10 chars)")
    descricao: str = Field(..., min_length=1)
    contexto_fiscal: str = Field(..., min_length=1)
    user_id: Optional[str] = Field(None, description="ID do usuário — necessário para rastreamento de tenant e verificação de limite")


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


# --- Endpoint consolidado PME ---

class RegistrarDecisaoRequest(BaseModel):
    query: str = Field(..., min_length=5)
    premissas: list[str] = Field(default_factory=list)
    riscos: list[str] = Field(default_factory=list)
    resultado_ia: str = Field(..., min_length=1)
    grau_consolidacao: str = ""
    contra_tese: str = ""
    criticidade: str = "informativo"
    hipotese_gestor: str = Field(..., min_length=1)
    decisao_final: str = Field(..., min_length=1)
    user_id: Optional[str] = None


@app.post("/v1/registrar_decisao", dependencies=[Depends(verificar_token_api)])
def registrar_decisao(req: RegistrarDecisaoRequest):
    """
    Endpoint consolidado para o fluxo PME de documentação (UX-03/04).
    Cria o case, submete P1→P5, gera Dossiê com Legal Hold e ativa monitoramento P6.
    """
    logger.info("POST /v1/registrar_decisao query=%s", req.query[:60])
    try:
        from src.cognitive.monitoramento_p6 import ativar_monitoramento_p6

        titulo = req.query[:80] if len(req.query) >= 10 else req.query.ljust(10, ".")
        contexto = req.premissas[0] if req.premissas else "Contexto tributário geral."
        premissas = req.premissas if len(req.premissas) >= 2 else req.premissas + [f"Análise: {req.query[:60]}"]
        riscos = req.riscos if req.riscos else ["Risco a ser monitorado."]
        periodo_fiscal = f"{datetime.now().year}-{datetime.now().year + 1}"

        # P1 — criar caso
        case_id = _protocol_engine.criar_caso(
            titulo=titulo,
            descricao=req.query,
            contexto_fiscal=contexto,
        )

        # P1 — avancar
        _protocol_engine.avancar(case_id, 1, {
            "titulo": titulo,
            "descricao": req.query,
            "contexto_fiscal": contexto,
            "premissas": premissas,
            "periodo_fiscal": periodo_fiscal,
        })

        # P2 — riscos
        _protocol_engine.avancar(case_id, 2, {
            "riscos": riscos,
            "dados_qualidade": "verde",
        })

        # P3 — análise IA
        _protocol_engine.avancar(case_id, 3, {
            "query_analise": req.query,
            "analise_result": req.resultado_ia,
        })

        # P4 — hipótese
        _protocol_engine.avancar(case_id, 4, {
            "hipotese_gestor": req.hipotese_gestor,
        })

        # P5 — decisão
        _protocol_engine.avancar(case_id, 5, {
            "recomendacao": req.resultado_ia[:500],
            "decisao_final": req.decisao_final,
            "decisor": "Gestor",
        })

        # Gerar dossiê C4 (requer P5 concluído)
        dossie = _output_engine.gerar_dossie(case_id=case_id)

        # Ativar monitoramento P6
        try:
            ativar_monitoramento_p6(
                case_id=case_id,
                user_id=req.user_id,
                titulo=titulo,
            )
        except Exception as e_p6:
            logger.warning("P6 monitoring não ativado para case_id=%d: %s", case_id, e_p6)

        return {
            "sucesso": True,
            "case_id": case_id,
            "dossie_id": dossie.id,
            "mensagem": "Análise registrada com Legal Hold ativo.",
        }

    except ProtocolError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except OutputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro em /v1/registrar_decisao: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


# --- Protocol endpoints ---

@app.post("/v1/cases", status_code=201, dependencies=[Depends(verificar_token_api)])
def criar_caso(req: CriarCasoRequest):
    """Cria um novo caso protocolar em Step 1/rascunho. Verifica limite por plano quando user_id fornecido."""
    logger.info("POST /v1/cases titulo=%s user_id=%s", req.titulo[:60], req.user_id)
    conn = None
    tenant_id = None
    try:
        # Verificar limite se user_id fornecido
        if req.user_id:
            conn = get_conn()
            row = _get_tenant_info_by_user(req.user_id, conn)
            if row:
                t_id, sub_status, plano, trial_ends = row
                tenant_id = str(t_id)
                permitido, usado, limite = _verificar_limite_casos(
                    tenant_id, sub_status, plano, trial_ends, conn
                )
                if not permitido:
                    limite_str = str(limite)
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            f"Limite de casos atingido ({usado}/{limite_str}). "
                            "Faça upgrade do plano para criar mais casos."
                        ),
                    )
            put_conn(conn)
            conn = None

        # Criar caso via protocol engine (faz commit internamente)
        case_id = _protocol_engine.criar_caso(
            titulo=req.titulo,
            descricao=req.descricao,
            contexto_fiscal=req.contexto_fiscal,
        )

        # Vincular tenant_id ao caso recem criado
        if tenant_id:
            conn2 = get_conn()
            try:
                cur = conn2.cursor()
                cur.execute("UPDATE cases SET tenant_id = %s WHERE id = %s", (tenant_id, case_id))
                conn2.commit()
                cur.close()
            finally:
                put_conn(conn2)

        return {"case_id": case_id, "status": "rascunho", "passo_atual": 1}

    except HTTPException:
        raise
    except ProtocolError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Erro em /v1/cases: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.get("/v1/cases/limite", dependencies=[Depends(verificar_token_api)])
def get_limite_casos(user_id: str = Query(...)):
    """Retorna quantos casos foram criados e qual o limite do plano atual."""
    logger.info("GET /v1/cases/limite user_id=%s", user_id)
    conn = None
    try:
        conn = get_conn()
        row = _get_tenant_info_by_user(user_id, conn)
        if not row:
            return {"usado": 0, "limite": 0, "plano": "starter", "subscription_status": "trial"}
        t_id, sub_status, plano, trial_ends = row
        tenant_id = str(t_id)
        _, usado, limite = _verificar_limite_casos(tenant_id, sub_status, plano, trial_ends, conn)
        return {
            "usado": usado,
            "limite": limite,
            "plano": plano,
            "subscription_status": sub_status,
        }
    except Exception as e:
        logger.error("Erro em /v1/cases/limite: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.get("/v1/cases", dependencies=[Depends(verificar_token_api)])
def listar_casos(user_id: Optional[str] = Query(None)):
    """Lista casos do tenant (filtrado por user_id quando fornecido). Exclui casos de testes."""
    logger.info("GET /v1/cases user_id=%s", user_id)
    conn = None
    try:
        conn = get_conn()

        # Resolver tenant_id a partir do user_id
        tenant_id = None
        if user_id:
            row = _get_tenant_info_by_user(user_id, conn)
            if row:
                tenant_id = str(row[0])

        cur = conn.cursor()
        exclusoes = [
            "%%teste%%", "%%test%%", "%%smoke%%", "%%validar%%",
            "%%bloqueio%%", "%%invalido%%", "%%retrocesso%%", "%%avancar%%",
            "%%voltar%%", "%%submeter%%", "%%integração%%", "%%integracao%%",
            "%%output ja%%", "%%listar outputs%%", "%%aprovacao%%",
            "%%get estado%%", "%%get output%%",
        ]
        not_ilike_clauses = " ".join(f"AND titulo NOT ILIKE '{e}'" for e in exclusoes)

        if tenant_id:
            cur.execute(
                f"""SELECT DISTINCT ON (titulo) id, titulo, status, passo_atual, created_at
                   FROM cases
                   WHERE tenant_id = %s
                     {not_ilike_clauses}
                   ORDER BY titulo, id DESC""",
                (tenant_id,),
            )
        else:
            cur.execute(
                f"""SELECT DISTINCT ON (titulo) id, titulo, status, passo_atual, created_at
                   FROM cases
                   WHERE {not_ilike_clauses[4:]}
                   ORDER BY titulo, id DESC"""
            )
        rows = cur.fetchall()
        cur.close()
        rows.sort(key=lambda r: r[0], reverse=True)
        return [
            {
                "case_id": r[0],
                "titulo": r[1],
                "status": r[2],
                "passo_atual": r[3],
                "created_at": str(r[4]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("Erro em GET /v1/cases: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.get("/v1/cases/{case_id}", dependencies=[Depends(verificar_token_api)])
def get_caso(case_id: str):
    """Retorna o estado completo do caso com histórico."""
    logger.info("GET /v1/cases/%s", case_id)
    try:
        estado = _protocol_engine.get_estado(case_id)
    except ProtocolError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em GET /v1/cases/%s: %s", case_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return _case_estado_to_dict(estado)


@app.post("/v1/cases/{case_id}/steps/{passo}", dependencies=[Depends(verificar_token_api)])
def submeter_passo(case_id: str, passo: int, req: SubmeterPassoRequest):
    """
    Submete dados de um passo e avança/retrocede o protocolo.
    No Step 5 (Decidir), executa DetectorCarimbo automaticamente se dados contiverem
    'decisao_final' e 'recomendacao'.
    """
    logger.info("POST /v1/cases/%s/steps/%d acao=%s", case_id, passo, req.acao)
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

        # Detector de carimbo ativado no Step 5 — Decidir (decisao_final vs recomendacao no mesmo passo)
        carimbo_result = None
        if passo == 5:
            texto_decisao = req.dados.get("decisao_final", "")
            # recomendacao e decisao_final estão ambos no Step 5 (Decidir)
            texto_recomendacao = req.dados.get("recomendacao", "")

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
                    logger.warning("Carimbo Voyage falhou, usando fallback léxico: %s", e)
                    try:
                        _cr_lite = _detectar_carimbo_lexico(texto_decisao, texto_recomendacao)
                        carimbo_result = {
                            "score_similaridade": _cr_lite["similaridade"],
                            "alerta": _cr_lite["carimbo_detectado"],
                            "mensagem": _cr_lite["mensagem"] or None,
                            "alert_id": None,
                        }
                    except Exception as e2:
                        logger.warning("Carimbo fallback léxico também falhou: %s", e2)

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
        logger.error("Erro em POST /v1/cases/%s/steps/%d: %s", case_id, passo, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


@app.post("/v1/cases/{case_id}/carimbo/confirmar", dependencies=[Depends(verificar_token_api)])
def confirmar_carimbo(case_id: str, req: ConfirmarCarimboRequest):
    """Confirma alerta de carimbo com justificativa do gestor (mín. 20 chars)."""
    logger.info("POST /v1/cases/%s/carimbo/confirmar alert_id=%d", case_id, req.alert_id)
    try:
        _carimbo_detector.confirmar(req.alert_id, req.justificativa)
    except CarimboConfirmacaoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em confirmar_carimbo: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {"confirmado": True, "alert_id": req.alert_id}


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class GerarOutputRequest(BaseModel):
    case_id: str
    classe: str = Field(..., description="alerta|nota_trabalho|recomendacao_formal|dossie_decisao|material_compartilhavel")
    stakeholders: Optional[list[str]] = Field(None, description="Lista de stakeholder_tipo")
    # Para alerta (C1)
    titulo: Optional[str] = None
    contexto: Optional[str] = None
    materialidade: Optional[int] = Field(None, ge=1, le=5)
    # Para C2/C3 — AnaliseResult embutido
    query: Optional[str] = None
    # Para C5 — base output_id
    output_base_id: Optional[str] = None
    # Para C2/C3 — modelo a usar na análise
    model: str = Field(MODEL_DEV)
    user_id: Optional[str] = Field(None, description="UUID do usuário autenticado (tenant isolation)")


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

@app.post("/v1/outputs", status_code=201, dependencies=[Depends(verificar_token_api)])
def gerar_output(req: GerarOutputRequest):
    """
    Gera um output acionável (C1–C5).
    - C1 (alerta): requer titulo, contexto, materialidade
    - C2 (nota_trabalho): requer query — executa análise cognitiva internamente
    - C3 (recomendacao_formal): requer query
    - C4 (dossie_decisao): requer Step 5 (Decidir) concluído no caso
    - C5 (material_compartilhavel): requer output_base_id com C3/C4 aprovado
    """
    logger.info("POST /v1/outputs case_id=%s classe=%s", req.case_id, req.classe)

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
                passo=2,
                titulo=req.titulo,
                contexto=req.contexto,
                materialidade=req.materialidade,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.NOTA_TRABALHO:
            if not req.query:
                raise HTTPException(status_code=422, detail="C2 requer query")
            analise = analisar(query=req.query, top_k=3, model=req.model, user_id=req.user_id)
            result = _output_engine.gerar_nota_trabalho(
                case_id=req.case_id,
                analise_result=analise,
                stakeholders=stk_list,
            )

        elif classe == OutputClass.RECOMENDACAO_FORMAL:
            if not req.query:
                raise HTTPException(status_code=422, detail="C3 requer query")
            analise = analisar(query=req.query, top_k=3, model=req.model, user_id=req.user_id)
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
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")

    return _output_result_to_dict(result)


@app.get("/v1/outputs/{output_id}", dependencies=[Depends(verificar_token_api)])
def get_output(output_id: str):
    """Retorna output completo com views por stakeholder."""
    logger.info("GET /v1/outputs/%s", output_id)
    try:
        from src.outputs.engine import _load_output
        conn = get_conn()
        try:
            result = _load_output(conn, output_id)
        finally:
            put_conn(conn)
    except OutputError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em GET /v1/outputs/%s: %s", output_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return _output_result_to_dict(result)


@app.post("/v1/outputs/{output_id}/aprovar", dependencies=[Depends(verificar_token_api)])
def aprovar_output(output_id: str, req: AprovarOutputRequest):
    """
    Aprova um output. Status gerado → aprovado.
    C3 e C5 exigem aprovação antes de publicação.
    """
    logger.info("POST /v1/outputs/%s/aprovar por=%s", output_id, req.aprovado_por)
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
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return _output_result_to_dict(result)


@app.get("/v1/cases/{case_id}/outputs", dependencies=[Depends(verificar_token_api)])
def listar_outputs_caso(case_id: str):
    """Lista todos os outputs de um caso, ordenados por materialidade DESC."""
    logger.info("GET /v1/cases/%s/outputs", case_id)
    try:
        outputs = _output_engine.listar_por_caso(case_id)
    except Exception as e:
        logger.error("Erro em GET /v1/cases/%s/outputs: %s", case_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
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

@app.get("/v1/observability/metrics", dependencies=[Depends(verificar_token_api)])
def get_metrics(
    days: int = Query(7, ge=1, le=90),
    prompt_version: Optional[str] = Query(None),
):
    """Métricas diárias agregadas dos últimos N dias."""
    logger.info("GET /v1/observability/metrics days=%d pv=%s", days, prompt_version)
    conn = get_conn()
    try:
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
    except Exception as e:
        logger.error("Erro em /v1/observability/metrics: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        put_conn(conn)
    return {"metrics": result, "resumo": resumo, "days": days}


@app.get("/v1/observability/drift", dependencies=[Depends(verificar_token_api)])
def get_drift_alerts(
    prompt_version: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
):
    """Lista drift alerts ativos (resolvido=False)."""
    logger.info("GET /v1/observability/drift pv=%s", prompt_version)
    conn = get_conn()
    try:
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
    except Exception as e:
        logger.error("Erro em /v1/observability/drift: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        put_conn(conn)
    return result


@app.post("/v1/observability/drift/{alert_id}/resolver", dependencies=[Depends(verificar_token_api)])
def resolver_drift(alert_id: int, req: ResolverDriftRequest):
    """Resolve um drift alert com observação."""
    logger.info("POST /v1/observability/drift/%d/resolver", alert_id)
    try:
        from src.observability.drift import DriftDetector, DriftDetectorError
        DriftDetector().resolver_alert(alert_id, req.observacao)
    except DriftDetectorError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Erro em resolver_drift: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {"resolvido": True, "alert_id": alert_id}


@app.post("/v1/observability/baseline", status_code=201, dependencies=[Depends(verificar_token_api)])
def registrar_baseline(req: BaselineRequest):
    """Registra baseline de métricas para a versão de prompt/modelo especificada."""
    logger.info("POST /v1/observability/baseline pv=%s model=%s", req.prompt_version, req.model_id)
    try:
        from src.observability.drift import DriftDetector, DriftDetectorError
        result = DriftDetector().registrar_baseline(req.prompt_version, req.model_id)
    except DriftDetectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro em registrar_baseline: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return result


@app.post("/v1/observability/regression", dependencies=[Depends(verificar_token_api)])
def executar_regression(req: RegressionRequest):
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
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {
        "aprovado": result.aprovado,
        "precisao_citacao": result.precisao_citacao,
        "taxa_alucinacao": result.taxa_alucinacao,
        "acuracia_recomendacao": result.acuracia_recomendacao,
        "latencia_p95": result.latencia_p95,
        "cobertura_contra_tese": result.cobertura_contra_tese,
        "detalhes": result.detalhes,
    }


# ---------------------------------------------------------------------------
# Budget pressure
# ---------------------------------------------------------------------------

@app.get("/v1/observability/budget-pressure", dependencies=[Depends(verificar_token_api)])
def budget_pressure():
    """Retorna pressão média de budget por query_tipo nos últimos 30 dias."""
    logger.info("GET /v1/observability/budget-pressure")
    try:
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    CASE
                        WHEN context_budget_log LIKE '%%FACTUAL%%' THEN 'FACTUAL'
                        WHEN context_budget_log LIKE '%%COMPARATIVA%%' THEN 'COMPARATIVA'
                        WHEN context_budget_log LIKE '%%INTERPRETATIVA%%' THEN 'INTERPRETATIVA'
                        ELSE 'OUTRO'
                    END AS query_tipo,
                    ROUND(AVG(budget_pressao_pct)::numeric, 1) AS avg_pressao,
                    ROUND(MAX(budget_pressao_pct)::numeric, 1) AS max_pressao,
                    COUNT(*) AS total_analises
                FROM ai_interactions
                WHERE budget_pressao_pct IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '30 days'
                GROUP BY 1
                ORDER BY 2 DESC
            """)
            rows = cur.fetchall()
            cur.close()
        finally:
            put_conn(conn)
        return [
            {
                "query_tipo": r[0],
                "avg_pressao_pct": float(r[1]) if r[1] else 0,
                "max_pressao_pct": float(r[2]) if r[2] else 0,
                "total_analises": r[3],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("Erro em budget-pressure: %s", e, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Monitor de fontes oficiais
# ---------------------------------------------------------------------------

@app.post("/v1/monitor/verificar", dependencies=[Depends(verificar_token_api)])
def verificar_fontes():
    """Verifica todas as fontes ativas e detecta novos documentos."""
    logger.info("POST /v1/monitor/verificar")
    try:
        from src.monitor.checker import verificar_todas_fontes
        resultados = verificar_todas_fontes()
    except Exception as e:
        logger.error("Erro em /v1/monitor/verificar: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {
        "fontes_verificadas": len(resultados),
        "total_novos": sum(r.novos for r in resultados),
        "resultados": [
            {
                "fonte": r.fonte_nome,
                "tipo": r.fonte_tipo,
                "novos": r.novos,
                "encontrados": r.total_encontrados,
                "erro": r.erro,
            }
            for r in resultados
        ],
    }


# ---------------------------------------------------------------------------
# Billing — MAU (Monthly Active Users)
# ---------------------------------------------------------------------------

@app.get("/v1/billing/mau", dependencies=[Depends(verificar_token_api)])
def get_mau(
    tenant_id: str,
    month: Optional[str] = None,  # formato: "2026-04" — se omitido, usa mês corrente
):
    """
    Retorna o total de usuários ativos (MAU) de um tenant em um mês.

    Parâmetros:
        tenant_id: UUID do tenant
        month: mês no formato YYYY-MM (opcional, default: mês corrente)

    Retorno:
        {"tenant_id": "uuid", "month": "2026-04", "active_users": 3, "active_month_start": "2026-04-01"}
    """
    logger.info("GET /v1/billing/mau tenant_id=%s month=%s", tenant_id, month)

    if month:
        try:
            year, mon = map(int, month.split("-"))
            active_month = date(year, mon, 1)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Formato de month inválido. Use YYYY-MM.")
    else:
        active_month = date.today().replace(day=1)

    sql = """
        SELECT COUNT(DISTINCT user_id) AS active_users
        FROM mau_records
        WHERE tenant_id = %s
          AND active_month = %s;
    """

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id, active_month))
            row = cur.fetchone()
            active_users = row[0] if row else 0
    except Exception as e:
        logger.error("Erro em /v1/billing/mau: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao consultar MAU: {str(e)}")
    finally:
        put_conn(conn)

    return {
        "tenant_id": tenant_id,
        "month": active_month.strftime("%Y-%m"),
        "active_users": active_users,
        "active_month_start": active_month.isoformat(),
    }


# ---------------------------------------------------------------------------
# Billing — Webhook Asaas
# ---------------------------------------------------------------------------

ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN", "")

# Mapeamento de eventos Asaas → subscription_status interno
_ASAAS_STATUS_MAP = {
    "PAYMENT_RECEIVED":         "active",
    "PAYMENT_CONFIRMED":        "active",
    "SUBSCRIPTION_RENEWED":     "active",
    "PAYMENT_OVERDUE":          "past_due",
    "PAYMENT_DELETED":          "past_due",
    "SUBSCRIPTION_INACTIVATED": "canceled",
    "SUBSCRIPTION_DELETED":     "canceled",
}


def _notificar_falha_pagamento(tenant_id: str, conn) -> None:
    """Busca o e-mail do admin do tenant e envia notificação de falha de pagamento."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.email, u.nome FROM users u WHERE u.tenant_id = %s AND u.perfil = 'ADMIN' LIMIT 1",
                (tenant_id,),
            )
            row = cur.fetchone()
        if row:
            enviar_email_falha_pagamento(row[0], row[1])
    except Exception as exc:
        logger.error("Erro ao notificar falha de pagamento para tenant %s: %s", tenant_id, exc)


@app.get("/v1/webhooks/asaas")
async def asaas_webhook_ping():
    """Validação de conectividade do Asaas (GET health check)."""
    return {"status": "ok"}


@app.post("/v1/webhooks/asaas")
async def asaas_webhook(request: Request):
    """
    Recebe eventos de billing do Asaas e atualiza subscription_status do tenant.
    Autenticação: token fixo no header asaas-access-token.
    Eventos: PAYMENT_RECEIVED, PAYMENT_CONFIRMED, PAYMENT_OVERDUE,
             PAYMENT_DELETED, SUBSCRIPTION_INACTIVATED.
    """
    token = request.headers.get("asaas-access-token", "")
    if token != ASAAS_WEBHOOK_TOKEN:
        logger.warning("Webhook Asaas: token inválido recebido.")
        raise HTTPException(status_code=401, detail="Token inválido.")

    payload = await request.json()
    evento       = payload.get("event", "")
    payment      = payload.get("payment", {})
    external_ref = payment.get("externalReference")  # nosso tenant_id

    logger.info("Webhook Asaas recebido: evento=%s tenant=%s", evento, external_ref)

    novo_status = _ASAAS_STATUS_MAP.get(evento)
    if not novo_status or not external_ref:
        return {"received": True}

    sql = """
        UPDATE tenants
        SET subscription_status = %s,
            updated_at = NOW()
        WHERE id = %s;
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (novo_status, external_ref))
        conn.commit()
        logger.info("Tenant %s → subscription_status='%s' via webhook Asaas.", external_ref, novo_status)
        if novo_status == "past_due":
            _notificar_falha_pagamento(external_ref, conn)
    except Exception as e:
        logger.error("Erro ao atualizar tenant via webhook: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno.")
    finally:
        put_conn(conn)

    return {"received": True}


@app.get("/v1/monitor/pendentes", dependencies=[Depends(verificar_token_api)])
def listar_docs_pendentes():
    """Lista documentos detectados aguardando revisao do usuario."""
    logger.info("GET /v1/monitor/pendentes")
    try:
        from src.monitor.checker import listar_pendentes
        docs = listar_pendentes()
    except Exception as e:
        logger.error("Erro em /v1/monitor/pendentes: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {
        "total": len(docs),
        "documentos": [
            {
                "id": d.id,
                "titulo": d.titulo,
                "url": d.url,
                "data_publicacao": d.data_publicacao,
                "resumo": d.resumo,
                "fonte": d.fonte_nome,
                "tipo": d.fonte_tipo,
                "detectado_em": d.detectado_em,
            }
            for d in docs
        ],
    }


@app.get("/v1/monitor/contagem", dependencies=[Depends(verificar_token_api)])
def contagem_pendentes():
    """Retorna quantidade de documentos novos pendentes."""
    try:
        from src.monitor.checker import contar_pendentes
        return {"pendentes": contar_pendentes()}
    except Exception as e:
        return {"pendentes": 0}


class AtualizarDocMonitorRequest(BaseModel):
    status: str = Field(..., description="'ingerido' ou 'descartado'")


@app.patch("/v1/monitor/documentos/{doc_id}", dependencies=[Depends(verificar_token_api)])
def atualizar_doc_monitor(doc_id: int, req: AtualizarDocMonitorRequest):
    """Atualiza status de um documento monitorado."""
    logger.info("PATCH /v1/monitor/documentos/%d status=%s", doc_id, req.status)
    if req.status not in ("ingerido", "descartado"):
        raise HTTPException(status_code=422, detail="Status deve ser 'ingerido' ou 'descartado'")
    try:
        from src.monitor.checker import atualizar_status
        ok = atualizar_status(doc_id, req.status)
        if not ok:
            raise HTTPException(status_code=404, detail="Documento nao encontrado")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro em PATCH /v1/monitor/documentos/%d: %s", doc_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    return {"atualizado": True, "doc_id": doc_id, "status": req.status}


# ─── SIMULADORES ─────────────────────────────────────────────────────────────
# MP-01..MP-05: endpoints expostos ao frontend React (sem cálculo no cliente)

_REGIMES_VALIDOS = {"lucro_real", "lucro_presumido", "simples_nacional"}
_TIPOS_OP_VALIDOS = {"misto", "so_mercadorias", "so_servicos"}


class SimCargaRTRequest(BaseModel):
    faturamento_anual: float = Field(..., gt=0)
    regime_tributario: str = Field("lucro_real", description="lucro_real | lucro_presumido | simples_nacional")
    tipo_operacao: str = Field("misto", description="misto | so_mercadorias | so_servicos")
    percentual_exportacao: float = Field(0.0, ge=0.0, le=1.0)
    percentual_credito_novo: float = Field(1.0, ge=0.0, le=1.0)

    @field_validator("regime_tributario")
    @classmethod
    def _val_regime(cls, v: str) -> str:
        if v not in _REGIMES_VALIDOS:
            raise ValueError(
                f"regime_tributario inválido: {v!r}. "
                f"Valores aceitos: {sorted(_REGIMES_VALIDOS)}"
            )
        return v

    @field_validator("tipo_operacao")
    @classmethod
    def _val_tipo_op(cls, v: str) -> str:
        if v not in _TIPOS_OP_VALIDOS:
            raise ValueError(
                f"tipo_operacao inválido: {v!r}. "
                f"Valores aceitos: {sorted(_TIPOS_OP_VALIDOS)}"
            )
        return v


@app.post("/v1/simuladores/carga-rt", dependencies=[Depends(verificar_token_api)])
def simular_carga_rt(req: SimCargaRTRequest):
    """MP-01 — Simulador Comparativo de Carga RT. Retorna cenários por ano (2024→2033)."""
    try:
        from src.simuladores.carga_rt import CenarioOperacional, simular_multiplos_anos
        import dataclasses
        cenario = CenarioOperacional(
            faturamento_anual=req.faturamento_anual,
            regime_tributario=req.regime_tributario,
            tipo_operacao=req.tipo_operacao,
            percentual_exportacao=req.percentual_exportacao,
            percentual_credito_novo=req.percentual_credito_novo,
        )
        pares = simular_multiplos_anos(cenario)
        resultado = []
        for r in pares:
            resultado.append({
                "ano": r["ano"],
                "atual": {
                    "carga_liquida":    r["carga_liquida_atual"],
                    "aliquota_efetiva": r["aliquota_efetiva_atual"],
                },
                "novo": {
                    "carga_liquida":    r["carga_liquida_nova"],
                    "aliquota_efetiva": r["aliquota_efetiva_nova"],
                },
            })
        return {"resultados": resultado}
    except Exception as e:
        logger.error("Erro em /v1/simuladores/carga-rt: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


class SimSplitPaymentRequest(BaseModel):
    faturamento_mensal: float = Field(..., gt=0)
    pct_vista: float = Field(0.5, ge=0.0, le=1.0)
    pct_prazo: float = Field(0.5, ge=0.0, le=1.0)
    prazo_medio_dias: int = Field(30, ge=1)
    taxa_captacao_am: float = Field(0.02, ge=0.0)
    pct_inadimplencia: float = Field(0.02, ge=0.0, le=1.0)
    aliquota_cbs: float = Field(0.088, ge=0.0)
    aliquota_ibs: float = Field(0.177, ge=0.0)
    pct_creditos: float = Field(0.60, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _val_soma_pct(self) -> "SimSplitPaymentRequest":
        soma = self.pct_vista + self.pct_prazo
        if abs(soma - 1.0) > 0.001:
            raise ValueError(
                f"pct_vista ({self.pct_vista}) + pct_prazo ({self.pct_prazo}) "
                f"deve somar 1.0 — representam a totalidade do faturamento "
                f"(soma atual: {soma:.4f})"
            )
        return self


@app.post("/v1/simuladores/split-payment", dependencies=[Depends(verificar_token_api)])
def simular_split(req: SimSplitPaymentRequest):
    """MP-05 — Simulador de Impacto do Split Payment no Caixa."""
    try:
        from src.simuladores.split_payment import CenarioSplitPayment, simular_split_payment
        import dataclasses
        cenario = CenarioSplitPayment(
            faturamento_mensal=req.faturamento_mensal,
            pct_vista=req.pct_vista,
            pct_prazo=req.pct_prazo,
            prazo_medio_dias=req.prazo_medio_dias,
            taxa_captacao_am=req.taxa_captacao_am,
            pct_inadimplencia=req.pct_inadimplencia,
            aliquota_cbs=req.aliquota_cbs,
            aliquota_ibs=req.aliquota_ibs,
            pct_creditos=req.pct_creditos,
        )
        resultado = simular_split_payment(cenario)
        return dataclasses.asdict(resultado)
    except Exception as e:
        logger.error("Erro em /v1/simuladores/split-payment: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


_CATEGORIAS_CREDITO_VALIDAS = {
    "insumos_diretos", "servicos_tomados", "ativo_imobilizado",
    "fornecedor_simples", "uso_consumo", "operacoes_imunes_isentas", "exportacoes",
}


class ItemAquisicaoInput(BaseModel):
    categoria: str
    valor_mensal: float = Field(..., gt=0)
    aliquota_cbs: float = 0.088
    aliquota_ibs: float = 0.177

    @field_validator("categoria")
    @classmethod
    def _val_categoria(cls, v: str) -> str:
        if v not in _CATEGORIAS_CREDITO_VALIDAS:
            raise ValueError(
                f"categoria inválida: {v!r}. "
                f"Categorias aceitas (LC 214/2025, arts. 28–55): "
                f"{sorted(_CATEGORIAS_CREDITO_VALIDAS)}"
            )
        return v


class SimCreditosRequest(BaseModel):
    itens: list[ItemAquisicaoInput]


@app.post("/v1/simuladores/creditos-ibs", dependencies=[Depends(verificar_token_api)])
def simular_creditos(req: SimCreditosRequest):
    """MP-02 — Monitor de Créditos IBS/CBS."""
    try:
        from src.simuladores.creditos_ibs_cbs import ItemAquisicao, mapear_creditos
        import dataclasses
        itens = [ItemAquisicao(**i.model_dump()) for i in req.itens]
        resultado = mapear_creditos(itens)
        return dataclasses.asdict(resultado)
    except Exception as e:
        logger.error("Erro em /v1/simuladores/creditos-ibs: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


_UFS_VALIDAS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}
_TIPOS_UNIDADE_VALIDOS = {"CD", "planta", "filial", "escritorio"}


class UnidadeInput(BaseModel):
    uf: str
    tipo: str = Field("filial", description="CD | planta | filial | escritorio")
    custo_fixo_anual: float = Field(..., gt=0)
    faturamento_anual: float = Field(..., gt=0)
    beneficio_icms_justifica: bool = True

    @field_validator("uf")
    @classmethod
    def _val_uf(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _UFS_VALIDAS:
            raise ValueError(
                f"UF inválida: {v!r}. "
                "Use a sigla oficial de um dos 27 estados brasileiros."
            )
        return v

    @field_validator("tipo")
    @classmethod
    def _val_tipo_unidade(cls, v: str) -> str:
        if v not in _TIPOS_UNIDADE_VALIDOS:
            raise ValueError(
                f"tipo de unidade inválido: {v!r}. "
                f"Valores aceitos: {sorted(_TIPOS_UNIDADE_VALIDOS)}"
            )
        return v


class SimReestruturacaoRequest(BaseModel):
    unidades: list[UnidadeInput]
    ano_analise: int = 2026


@app.post("/v1/simuladores/reestruturacao", dependencies=[Depends(verificar_token_api)])
def simular_reestruturacao(req: SimReestruturacaoRequest):
    """MP-03 — Simulador de Reestruturação RT."""
    try:
        from src.simuladores.reestruturacao_rt import UnidadeOperacional, analisar_reestruturacao
        import dataclasses
        unidades = [UnidadeOperacional(**u.model_dump()) for u in req.unidades]
        resultado = analisar_reestruturacao(unidades, ano_analise=req.ano_analise)
        return dataclasses.asdict(resultado)
    except Exception as e:
        logger.error("Erro em /v1/simuladores/reestruturacao: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


_PRODUTOS_IS_VALIDOS = {
    "tabaco", "bebidas_alcoolicas", "bebidas_acucaradas",
    "veiculos", "embarcacoes", "minerais", "combustiveis", "apostas_jogos",
}
_ELASTICIDADES_VALIDAS = {"alta", "media", "baixa"}


class SimImpactoISRequest(BaseModel):
    produto: str = Field(
        ...,
        description=(
            "tabaco | bebidas_alcoolicas | bebidas_acucaradas | veiculos | "
            "embarcacoes | minerais | combustiveis | apostas_jogos"
        ),
    )
    preco_venda_atual: float = Field(..., gt=0)
    volume_mensal: int = Field(..., gt=0)
    custo_producao: float = Field(..., gt=0)
    elasticidade: str = Field("media", description="alta | media | baixa")
    aliquota_customizada: Optional[float] = None

    @field_validator("produto")
    @classmethod
    def _val_produto_is(cls, v: str) -> str:
        if v not in _PRODUTOS_IS_VALIDOS:
            raise ValueError(
                f"produto IS inválido: {v!r}. "
                f"Sujeitos ao IS (LC 214/2025, art. 412 + Anexo XVII): "
                f"{sorted(_PRODUTOS_IS_VALIDOS)}"
            )
        return v

    @field_validator("elasticidade")
    @classmethod
    def _val_elasticidade(cls, v: str) -> str:
        if v not in _ELASTICIDADES_VALIDAS:
            raise ValueError(
                f"elasticidade inválida: {v!r}. "
                f"Valores aceitos: {sorted(_ELASTICIDADES_VALIDAS)}"
            )
        return v


@app.get("/v1/admin/metricas", dependencies=[Depends(verificar_token_api)])
def admin_metricas():
    """Resumo agregado para o painel admin."""
    logger.info("GET /v1/admin/metricas")
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM users)                                    AS total_usuarios,
                (SELECT COUNT(*) FROM ai_interactions)                          AS total_analises,
                (SELECT COUNT(*) FROM outputs WHERE classe = 'dossie_decisao')  AS total_dossies,
                (SELECT COUNT(DISTINCT user_id) FROM mau_records
                  WHERE active_month = DATE_TRUNC('month', CURRENT_DATE)::date)  AS mau_atual
        """)
        row = cur.fetchone()
        cur.close()
        return {
            "total_usuarios": row[0] or 0,
            "total_analises": row[1] or 0,
            "total_dossies":  row[2] or 0,
            "mau_atual":      row[3] or 0,
        }
    except Exception as e:
        logger.error("Erro em /v1/admin/metricas: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-CADASTRO E VERIFICAÇÃO DE E-MAIL
# ─────────────────────────────────────────────────────────────────────────────

def _validar_senha_forte(v: str) -> str:
    """Valida força de senha: mín 8 chars, maiúscula, minúscula, dígito e especial."""
    import re
    erros = []
    if len(v) < 8:
        erros.append("mínimo de 8 caracteres")
    if not re.search(r"[A-Z]", v):
        erros.append("ao menos uma letra maiúscula")
    if not re.search(r"[a-z]", v):
        erros.append("ao menos uma letra minúscula")
    if not re.search(r"\d", v):
        erros.append("ao menos um número")
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", v):
        erros.append("ao menos um caractere especial (!@#$%...)")
    if erros:
        raise ValueError("Senha fraca. Requisitos: " + "; ".join(erros) + ".")
    return v


class RegisterRequest(BaseModel):
    nome:              str  = Field(..., min_length=2, max_length=100)
    email:             str  = Field(..., description="E-mail do usuário")
    senha:             str  = Field(..., min_length=8, max_length=128)
    razao_social:      str  = Field(..., min_length=2, max_length=255)
    cnpj_raiz:         Optional[str] = Field(None, description="CPF (11 dígitos) ou CNPJ (14 dígitos)")
    lgpd_consent:      bool = Field(..., description="Aceite do tratamento de dados LGPD (obrigatório)")
    marketing_consent: bool = Field(False, description="Opt-in para comunicações de marketing (opcional)")

    @field_validator("senha")
    @classmethod
    def senha_forte(cls, v: str) -> str:
        return _validar_senha_forte(v)

    @field_validator("lgpd_consent")
    @classmethod
    def lgpd_deve_ser_true(cls, v: bool) -> bool:
        if not v:
            raise ValueError("O consentimento LGPD é obrigatório para o cadastro.")
        return v

    @field_validator("cnpj_raiz")
    @classmethod
    def validar_cnpj_raiz(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        digits = re.sub(r"\D", "", v)
        if len(digits) not in (11, 14):
            raise ValueError("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos).")
        return digits

    @field_validator("email")
    @classmethod
    def validar_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("E-mail inválido.")
        return v.lower().strip()


@app.post("/v1/auth/register")
@limiter.limit("3/minute")
def register(request: Request, req: RegisterRequest, background_tasks: BackgroundTasks):
    """
    Auto-cadastro público — cria tenant + usuário em trial de 7 dias.
    Público (sem X-API-Key). Rate-limited: 3 req/min por IP.
    Conta fica inativa até confirmação por e-mail.
    """
    logger.info("POST /v1/auth/register email=%s", req.email)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        # Verificar e-mail único
        cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (req.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

        # Verificar CNPJ único (se fornecido)
        cnpj = req.cnpj_raiz or str(uuid.uuid4().hex[:8])  # CNPJ gerado se ausente
        if req.cnpj_raiz:
            cur.execute("SELECT id FROM tenants WHERE cnpj_raiz = %s LIMIT 1", (cnpj,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="CNPJ já cadastrado.")

        tenant_id   = str(uuid.uuid4())
        user_id     = str(uuid.uuid4())
        email_token = str(uuid.uuid4())
        senha_hash  = gerar_hash_senha(req.senha)

        # Criar tenant
        cur.execute("""
            INSERT INTO tenants (id, cnpj_raiz, razao_social, status, plano,
                                 trial_starts_at, trial_ends_at, subscription_status)
            VALUES (%s, %s, %s, 'active', 'starter',
                    NOW(), NOW() + INTERVAL '7 days', 'trial')
        """, (tenant_id, cnpj, req.razao_social))

        # Criar usuário (inativo até verificar e-mail)
        cur.execute("""
            INSERT INTO users (id, email, nome, senha_hash, perfil, ativo, tenant_id,
                               lgpd_consent, lgpd_consent_at, marketing_consent,
                               email_verificado, email_token)
            VALUES (%s, %s, %s, %s, 'USER', FALSE, %s,
                    %s, NOW(), %s, FALSE, %s)
        """, (user_id, req.email, req.nome, senha_hash, tenant_id,
              req.lgpd_consent, req.marketing_consent, email_token))

        conn.commit()
        cur.close()

        # Enviar e-mail de confirmação em background (não bloqueia response)
        background_tasks.add_task(enviar_email_confirmacao, req.email, req.nome, email_token)

        return {
            "message": "Cadastro realizado com sucesso! Verifique seu e-mail para ativar a conta.",
            "email": req.email,
        }

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/auth/register: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.get("/v1/auth/verify-email")
def verify_email(token: str = Query(..., description="Token de verificação enviado por e-mail")):
    """
    Confirma o e-mail e ativa a conta. Retorna JWT para login automático.
    Público (sem X-API-Key).
    """
    logger.info("GET /v1/auth/verify-email token=%s", token[:8] + "...")
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, email, nome, perfil, tenant_id FROM users WHERE email_token = %s LIMIT 1",
            (token,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Token inválido ou já utilizado.")

        user_id, email, nome, perfil, tenant_id = row

        import uuid as _uuid
        novo_session_id = str(_uuid.uuid4())
        cur.execute(
            """UPDATE users SET ativo = TRUE, email_verificado = TRUE,
               email_token = NULL, session_id = %s WHERE id = %s""",
            (novo_session_id, str(user_id)),
        )
        conn.commit()
        cur.close()

        # Gerar token JWT para login automático
        from auth import Usuario
        from datetime import timezone
        usuario = Usuario(
            id=str(user_id), email=email, nome=nome, perfil=perfil,
            ativo=True, primeiro_uso=None, criado_em=datetime.now(timezone.utc),
            tenant_id=str(tenant_id) if tenant_id else None,
            session_id=novo_session_id,
        )
        jwt_token = gerar_token(usuario)

        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": {
                "id":          str(user_id),
                "email":       email,
                "nome":        nome,
                "perfil":      perfil,
                "tenant_id":   str(tenant_id) if tenant_id else None,
                "onboarding_step": 0,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/auth/verify-email: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


# ─────────────────────────────────────────────────────────────────────────────
# RECUPERAÇÃO DE SENHA
# ─────────────────────────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="E-mail do usuário cadastrado")


class ResetPasswordRequest(BaseModel):
    token:      str
    nova_senha: str = Field(..., min_length=8, max_length=128)

    @field_validator("nova_senha")
    @classmethod
    def validar_senha_forte(cls, v: str) -> str:
        import re
        erros = []
        if len(v) < 8:
            erros.append("mínimo 8 caracteres")
        if not re.search(r"[A-Z]", v):
            erros.append("ao menos uma letra maiúscula")
        if not re.search(r"[a-z]", v):
            erros.append("ao menos uma letra minúscula")
        if not re.search(r"\d", v):
            erros.append("ao menos um número")
        if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", v):
            erros.append("ao menos um caractere especial")
        if erros:
            raise ValueError("Senha inválida: " + ", ".join(erros))
        return v


@app.post("/v1/auth/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, req: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    """
    Solicita redefinição de senha. Gera token UUID válido por 1h e envia e-mail via Resend.
    Retorna 200 se cadastrado (envia e-mail) ou 404 se e-mail não encontrado.
    Público (sem X-API-Key). Rate-limited: 3 req/min por IP.
    """
    logger.info("POST /v1/auth/forgot-password email=%s", req.email)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, nome FROM users WHERE email = %s AND ativo = TRUE LIMIT 1",
            (req.email,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="E-mail não encontrado. Verifique ou crie uma conta.")

        user_id, nome = row
        reset_token = str(uuid.uuid4())

        cur.execute(
            """UPDATE users
               SET reset_token = %s, reset_token_expires_at = NOW() + INTERVAL '1 hour'
               WHERE id = %s""",
            (reset_token, str(user_id)),
        )
        conn.commit()
        cur.close()

        from src.email_service import enviar_email_recuperacao_senha
        background_tasks.add_task(enviar_email_recuperacao_senha, req.email, nome, reset_token)

        return {"message": "E-mail de recuperação enviado. Verifique sua caixa de entrada."}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/auth/forgot-password: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.post("/v1/auth/reset-password")
def reset_password(req: ResetPasswordRequest):
    """
    Redefine a senha usando o token recebido por e-mail.
    Token deve ser válido e não expirado (1h). Público (sem X-API-Key).
    """
    logger.info("POST /v1/auth/reset-password token=%s", req.token[:8] + "...")
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            """SELECT id FROM users
               WHERE reset_token = %s
                 AND reset_token_expires_at > NOW()
               LIMIT 1""",
            (req.token,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Link inválido ou expirado. Solicite um novo.")

        user_id = str(row[0])
        nova_hash = gerar_hash_senha(req.nova_senha)

        cur.execute(
            """UPDATE users
               SET senha_hash = %s, reset_token = NULL, reset_token_expires_at = NULL
               WHERE id = %s""",
            (nova_hash, user_id),
        )
        conn.commit()
        cur.close()

        return {"message": "Senha redefinida com sucesso. Faça login com sua nova senha."}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/auth/reset-password: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


# ─────────────────────────────────────────────────────────────────────────────
# BILLING — ASSINATURA ASAAS
# ─────────────────────────────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    tenant_id:    str
    billing_type: str = Field("CREDIT_CARD", pattern="^(CREDIT_CARD|PIX)$")


@app.post("/v1/billing/subscribe", dependencies=[Depends(verificar_token_api)])
def billing_subscribe(req: SubscribeRequest):
    """
    Cria customer + assinatura Starter no Asaas e retorna link de pagamento.
    Sandbox: ASAAS_BASE_URL aponta para sandbox.asaas.com.
    Valor base: R$ 497,00 — descontado conforme tenants.desconto_percentual.
    """
    logger.info("POST /v1/billing/subscribe tenant_id=%s billing_type=%s", req.tenant_id, req.billing_type)
    conn = None
    try:
        from src.billing.asaas import criar_customer, criar_assinatura, buscar_pagamentos_assinatura

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT razao_social, asaas_customer_id, asaas_subscription_id,
                      desconto_percentual,
                      (SELECT email FROM users WHERE tenant_id = t.id AND perfil = 'ADMIN' LIMIT 1),
                      cnpj_raiz
               FROM tenants t WHERE t.id = %s LIMIT 1""",
            (req.tenant_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tenant não encontrado.")

        razao_social, asaas_customer_id, asaas_subscription_id, desconto, email_admin, cnpj = row

        if asaas_subscription_id:
            raise HTTPException(status_code=409, detail="Assinatura já existe para este tenant.")

        # Criar customer se ainda não existe
        if not asaas_customer_id:
            customer = criar_customer(req.tenant_id, razao_social, email_admin or "", cnpj or "")
            asaas_customer_id = customer["id"]
            cur.execute(
                "UPDATE tenants SET asaas_customer_id = %s WHERE id = %s",
                (asaas_customer_id, req.tenant_id),
            )

        # Calcular valor com desconto comercial do tenant
        valor_base   = 497.00
        desconto_pct = float(desconto or 0)
        valor_final  = round(valor_base * (1 - desconto_pct / 100), 2)

        # Desconto promocional: R$ 297 nos 2 primeiros meses → desconto de R$ 200 por 2 ciclos
        desconto_promo_valor  = round(valor_final - 297.00, 2) if valor_final > 297.00 else None
        desconto_promo_ciclos = 2 if desconto_promo_valor and desconto_promo_valor > 0 else None

        # Criar assinatura
        assinatura = criar_assinatura(
            customer_id=asaas_customer_id,
            tenant_id=req.tenant_id,
            plano="starter",
            valor=valor_final,
            billing_type=req.billing_type,
            desconto_valor=desconto_promo_valor,
            desconto_ciclos=desconto_promo_ciclos,
        )
        asaas_subscription_id = assinatura["id"]

        cur.execute(
            "UPDATE tenants SET asaas_subscription_id = %s, plano = 'starter' WHERE id = %s",
            (asaas_subscription_id, req.tenant_id),
        )
        conn.commit()
        cur.close()

        # Buscar link de pagamento da primeira cobrança
        pagamentos = buscar_pagamentos_assinatura(asaas_subscription_id)
        invoice_url = None
        if pagamentos.get("data"):
            invoice_url = pagamentos["data"][0].get("invoiceUrl")

        logger.info(
            "Assinatura criada: tenant=%s subscription=%s valor=%.2f desconto=%.1f%%",
            req.tenant_id, asaas_subscription_id, valor_final, desconto_pct,
        )
        return {
            "invoice_url":        invoice_url,
            "valor":              valor_final,
            "desconto_percentual": desconto_pct,
        }

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/billing/subscribe: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao processar assinatura. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


class CancelRequest(BaseModel):
    tenant_id: str
    motivo: Optional[str] = None


@app.post("/v1/billing/cancel", dependencies=[Depends(verificar_token_api)])
def billing_cancel(req: CancelRequest):
    """
    Cancela a assinatura do tenant no Asaas e atualiza o status interno.
    Salva o motivo de cancelamento coletado no exit survey.
    404 do Asaas (sub já cancelada) é tratado como sucesso silencioso.
    """
    from src.billing.asaas import cancelar_assinatura as _asaas_cancelar
    import httpx

    logger.info("POST /v1/billing/cancel tenant_id=%s", req.tenant_id)
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT asaas_subscription_id FROM tenants WHERE id = %s LIMIT 1",
                (req.tenant_id,),
            )
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Tenant não encontrado.")

        asaas_sub_id = row[0]

        if asaas_sub_id:
            try:
                _asaas_cancelar(asaas_sub_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.warning("Assinatura %s não encontrada no Asaas — prosseguindo com cancelamento local.", asaas_sub_id)
                else:
                    raise

        with conn.cursor() as cur:
            cur.execute(
                """UPDATE tenants
                   SET subscription_status = 'canceled',
                       cancel_reason = %s,
                       updated_at = NOW()
                   WHERE id = %s""",
                (req.motivo, req.tenant_id),
            )
        conn.commit()
        logger.info("Tenant %s cancelado. Motivo: %s", req.tenant_id, req.motivo)
        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/billing/cancel: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao cancelar assinatura. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


class DescontoRequest(BaseModel):
    desconto_percentual: float = Field(..., ge=0, le=100)


@app.patch("/v1/admin/tenants/{tenant_id}/desconto", dependencies=[Depends(verificar_token_api)])
def admin_set_desconto(tenant_id: str, req: DescontoRequest):
    """Define desconto percentual para o tenant (0–100%). Admin only."""
    logger.info("PATCH /v1/admin/tenants/%s/desconto pct=%.1f", tenant_id, req.desconto_percentual)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE tenants SET desconto_percentual = %s WHERE id = %s RETURNING id",
            (req.desconto_percentual, tenant_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Tenant não encontrado.")
        conn.commit()
        cur.close()
        return {"ok": True, "desconto_percentual": req.desconto_percentual}
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/admin/tenants/desconto: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno.")
    finally:
        if conn:
            put_conn(conn)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — GESTÃO DE USUÁRIOS (SoD)
# ─────────────────────────────────────────────────────────────────────────────

class AdminCreateUserRequest(BaseModel):
    nome:      str = Field(..., min_length=2, max_length=100)
    email:     str = Field(..., description="E-mail do usuário")
    senha:     str = Field(..., min_length=8, max_length=128)
    perfil:    str = Field("USER", description="ADMIN ou USER")
    tenant_id: Optional[str] = Field(None, description="UUID do tenant; None cria tenant próprio")

    @field_validator("senha")
    @classmethod
    def senha_forte(cls, v: str) -> str:
        return _validar_senha_forte(v)

    @field_validator("perfil")
    @classmethod
    def validar_perfil(cls, v: str) -> str:
        if v not in ("ADMIN", "USER"):
            raise ValueError("perfil deve ser ADMIN ou USER.")
        return v

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, v: str) -> str:
        return v.lower().strip()


class AdminUpdateUserRequest(BaseModel):
    nome:   Optional[str]  = Field(None, min_length=2, max_length=100)
    perfil: Optional[str]  = Field(None)
    ativo:  Optional[bool] = Field(None)

    @field_validator("perfil")
    @classmethod
    def validar_perfil(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("ADMIN", "USER"):
            raise ValueError("perfil deve ser ADMIN ou USER.")
        return v


class AdminResetSenhaRequest(BaseModel):
    nova_senha: str = Field(..., min_length=8, max_length=128)

    @field_validator("nova_senha")
    @classmethod
    def nova_senha_forte(cls, v: str) -> str:
        return _validar_senha_forte(v)


@app.get("/v1/admin/users", dependencies=[Depends(verificar_token_api)])
def admin_list_users(
    perfil: Optional[str] = Query(None, description="Filtrar por perfil (ADMIN/USER)"),
    ativo:  Optional[bool] = Query(None, description="Filtrar por status ativo"),
):
    """Lista todos os usuários com filtros opcionais."""
    logger.info("GET /v1/admin/users perfil=%s ativo=%s", perfil, ativo)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        conditions = []
        params = []
        if perfil is not None:
            conditions.append("u.perfil = %s")
            params.append(perfil.upper())
        if ativo is not None:
            conditions.append("u.ativo = %s")
            params.append(ativo)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cur.execute(f"""
            SELECT u.id, u.email, u.nome, u.perfil, u.ativo,
                   u.criado_em, u.primeiro_uso, u.email_verificado,
                   t.razao_social, t.subscription_status, t.trial_ends_at
            FROM users u
            LEFT JOIN tenants t ON t.id = u.tenant_id
            {where}
            ORDER BY u.criado_em DESC
        """, params)

        rows = cur.fetchall()
        cur.close()

        users = []
        for r in rows:
            trial_ends = r[10]
            users.append({
                "id":                 str(r[0]),
                "email":              r[1],
                "nome":               r[2],
                "perfil":             r[3],
                "ativo":              r[4],
                "criado_em":          r[5].isoformat() if r[5] else None,
                "primeiro_uso":       r[6].isoformat() if r[6] else None,
                "email_verificado":   r[7],
                "empresa":            r[8],
                "subscription_status": r[9],
                "trial_ends_at":      trial_ends.isoformat() if trial_ends else None,
            })
        return {"users": users, "total": len(users)}

    except Exception as e:
        logger.error("Erro em /v1/admin/users GET: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.post("/v1/admin/users", dependencies=[Depends(verificar_token_api)])
def admin_create_user(req: AdminCreateUserRequest):
    """Cria usuário diretamente pelo admin (sem validação de domínio, sem e-mail de verificação)."""
    logger.info("POST /v1/admin/users email=%s", req.email)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (req.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

        user_id    = str(uuid.uuid4())
        senha_hash = gerar_hash_senha(req.senha)
        tenant_id  = req.tenant_id

        if tenant_id is None:
            # Criar tenant mínimo para o usuário admin criado manualmente
            tenant_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO tenants (id, cnpj_raiz, razao_social, status, plano,
                                     trial_starts_at, trial_ends_at, subscription_status)
                VALUES (%s, %s, %s, 'active', 'starter',
                        NOW(), NOW() + INTERVAL '7 days', 'trial')
            """, (tenant_id, str(uuid.uuid4().hex[:8]), req.nome))

        cur.execute("""
            INSERT INTO users (id, email, nome, senha_hash, perfil, ativo, tenant_id,
                               email_verificado, lgpd_consent)
            VALUES (%s, %s, %s, %s, %s, TRUE, %s, TRUE, FALSE)
        """, (user_id, req.email, req.nome, senha_hash, req.perfil, tenant_id))

        conn.commit()
        cur.close()

        return {"id": user_id, "email": req.email, "nome": req.nome, "perfil": req.perfil}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/admin/users POST: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.patch("/v1/admin/users/{user_id}", dependencies=[Depends(verificar_token_api)])
def admin_update_user(user_id: str, req: AdminUpdateUserRequest):
    """Atualiza nome, perfil ou status ativo de um usuário."""
    logger.info("PATCH /v1/admin/users/%s", user_id)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE id = %s LIMIT 1", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        fields, params = [], []
        if req.nome is not None:
            fields.append("nome = %s")
            params.append(req.nome)
        if req.perfil is not None:
            fields.append("perfil = %s")
            params.append(req.perfil)
        if req.ativo is not None:
            fields.append("ativo = %s")
            params.append(req.ativo)

        if not fields:
            raise HTTPException(status_code=422, detail="Nenhum campo para atualizar.")

        params.append(user_id)
        cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", params)
        conn.commit()
        cur.close()
        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/admin/users PATCH: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.post("/v1/admin/users/{user_id}/reset-senha", dependencies=[Depends(verificar_token_api)])
def admin_reset_senha(user_id: str, req: AdminResetSenhaRequest):
    """Redefine a senha de um usuário."""
    logger.info("POST /v1/admin/users/%s/reset-senha", user_id)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE id = %s LIMIT 1", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        novo_hash = gerar_hash_senha(req.nova_senha)
        cur.execute("UPDATE users SET senha_hash = %s WHERE id = %s", (novo_hash, user_id))
        conn.commit()
        cur.close()
        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Erro em /v1/admin/users reset-senha: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — MAILING (trial expirado não convertido + lgpd_consent)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/v1/admin/mailing", dependencies=[Depends(verificar_token_api)])
def admin_mailing(
    status: Optional[str] = Query(None, description="Filtrar: trial_ativo, trial_expirado, convertido, cancelado"),
):
    """
    Lista todos os usuários com lgpd_consent=true para uso como mailing.
    Inclui status do trial para identificar não-convertidos.
    """
    logger.info("GET /v1/admin/mailing status=%s", status)
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        status_filter = ""
        params: list = []

        if status == "trial_ativo":
            status_filter = "AND t.subscription_status = 'trial' AND t.trial_ends_at >= NOW()"
        elif status == "trial_expirado":
            status_filter = "AND t.subscription_status = 'trial' AND t.trial_ends_at < NOW()"
        elif status == "convertido":
            status_filter = "AND t.subscription_status = 'active'"
        elif status == "cancelado":
            status_filter = "AND t.subscription_status IN ('canceled', 'past_due')"

        cur.execute(f"""
            SELECT u.id, u.email, u.nome, u.criado_em,
                   t.razao_social, t.subscription_status, t.trial_ends_at, t.trial_starts_at,
                   t.id AS tenant_id, COALESCE(t.desconto_percentual, 0) AS desconto_percentual
            FROM users u
            JOIN tenants t ON t.id = u.tenant_id
            WHERE u.marketing_consent = TRUE
            {status_filter}
            ORDER BY u.criado_em DESC
        """, params)

        rows = cur.fetchall()
        cur.close()

        records = []
        for r in rows:
            trial_ends = r[6]
            trial_expired = trial_ends is not None and trial_ends < datetime.now(trial_ends.tzinfo)
            records.append({
                "id":                   str(r[0]),
                "email":                r[1],
                "nome":                 r[2],
                "criado_em":            r[3].isoformat() if r[3] else None,
                "empresa":              r[4],
                "subscription_status":  r[5],
                "trial_ends_at":        trial_ends.isoformat() if trial_ends else None,
                "trial_expirado":       trial_expired,
                "tenant_id":            str(r[8]) if r[8] else None,
                "desconto_percentual":  float(r[9]) if r[9] is not None else 0.0,
            })
        return {"records": records, "total": len(records)}

    except Exception as e:
        logger.error("Erro em /v1/admin/mailing: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.get("/v1/admin/mailing/export", dependencies=[Depends(verificar_token_api)])
def admin_mailing_export():
    """Exporta lista de mailing em CSV (lgpd_consent=true)."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    logger.info("GET /v1/admin/mailing/export")
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.nome, u.email, t.razao_social,
                   u.criado_em, t.trial_ends_at, t.subscription_status
            FROM users u
            JOIN tenants t ON t.id = u.tenant_id
            WHERE u.marketing_consent = TRUE
            ORDER BY u.criado_em DESC
        """)
        rows = cur.fetchall()
        cur.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["nome", "email", "empresa", "cadastrado_em", "trial_expira_em", "status"])
        for r in rows:
            writer.writerow([
                r[0], r[1], r[2],
                r[3].isoformat() if r[3] else "",
                r[4].isoformat() if r[4] else "",
                r[5] or "",
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=mailing_tribus.csv"},
        )

    except Exception as e:
        logger.error("Erro em /v1/admin/mailing/export: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
    finally:
        if conn:
            put_conn(conn)


@app.post("/v1/simuladores/impacto-is", dependencies=[Depends(verificar_token_api)])
def simular_impacto_is(req: SimImpactoISRequest):
    """MP-04 — Calculadora de Impacto do Imposto Seletivo."""
    try:
        from src.simuladores.impacto_is import CenarioIS, calcular_impacto_is
        import dataclasses
        cenario = CenarioIS(
            produto=req.produto,
            preco_venda_atual=req.preco_venda_atual,
            volume_mensal=req.volume_mensal,
            custo_producao=req.custo_producao,
            elasticidade=req.elasticidade,
            aliquota_customizada=req.aliquota_customizada,
        )
        resultado = calcular_impacto_is(cenario)
        return dataclasses.asdict(resultado)
    except Exception as e:
        logger.error("Erro em /v1/simuladores/impacto-is: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
