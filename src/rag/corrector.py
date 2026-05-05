"""
rag/corrector.py — Corrective RAG (CRAG): filtragem semântica de chunks antes do LLM.

Avalia relevância individual de cada chunk recuperado via chamada LLM leve (haiku),
remove irrelevantes e dispara re-retrieval com query reformulada quando necessário.

Inspirado em: Corrective RAG (LangGraph) — 500-AI-Agents-Projects.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import anthropic
from dotenv import load_dotenv

from src.rag.retriever import ChunkResultado
from src.rag.vigencia_checker import AlertaVigencia, verificar_vigencia_chunks

load_dotenv()
logger = logging.getLogger(__name__)

MODEL_CORRECTOR = os.getenv("MODEL_DEV", "claude-haiku-4-5-20251001")
MIN_CHUNKS_RELEVANTES = 2

_PROMPT_AVALIAR = """\
Você é um avaliador de relevância de trechos legislativos para consultas tributárias.

CONSULTA DO USUÁRIO:
{query}

TRECHOS RECUPERADOS:
{trechos}

Para cada trecho, avalie se ele é RELEVANTE, PARCIAL ou IRRELEVANTE para responder \
a consulta acima.

Retorne EXCLUSIVAMENTE um JSON válido no formato:
{{
  "avaliacoes": [
    {{"id": 1, "relevancia": "relevante|parcial|irrelevante"}},
    ...
  ],
  "query_reformulada": "<string ou null — se todos os trechos forem irrelevantes, \
sugira uma reformulação da query para melhorar a busca>"
}}

Critérios:
- RELEVANTE: o trecho contém informação diretamente útil para responder a consulta.
- PARCIAL: o trecho tem relação com o tema mas não responde diretamente a consulta.
- IRRELEVANTE: o trecho não tem relação com a consulta.

Responda SOMENTE com o JSON, sem texto adicional."""


@dataclass
class CorrectorResult:
    """Resultado da correção de chunks."""
    chunks_filtrados: list[ChunkResultado]
    chunks_removidos: int
    query_reformulada: Optional[str]
    usou_reformulacao: bool
    alertas_vigencia: list[AlertaVigencia] = field(default_factory=list)


class CorrectorRAG:

    def __init__(self, model: str = MODEL_CORRECTOR):
        self._model = model
        self._client: Optional[anthropic.Anthropic] = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key or key == "<PREENCHER>":
                raise EnvironmentError("ANTHROPIC_API_KEY não configurada")
            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def _formatar_trechos(self, chunks: list[ChunkResultado]) -> str:
        partes = []
        for i, c in enumerate(chunks, 1):
            artigo = c.artigo or "artigo não identificado"
            partes.append(
                f"[Trecho {i}] {c.norma_codigo} | {artigo} | score={c.score_final:.3f}\n"
                f"{c.texto[:500]}"
            )
        return "\n\n".join(partes)

    def _chamar_llm(self, query: str, chunks: list[ChunkResultado]) -> dict:
        """Chama o LLM para avaliar relevância dos chunks."""
        client = self._get_client()
        trechos = self._formatar_trechos(chunks)
        prompt = _PROMPT_AVALIAR.format(query=query, trechos=trechos)

        resp = client.messages.create(
            model=self._model,
            max_tokens=512,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)

    def corrigir(
        self,
        query: str,
        chunks: list[ChunkResultado],
        retrieve_fn=None,
        trace=None,
    ) -> CorrectorResult:
        """
        Filtra chunks por relevância semântica.

        Args:
            query: Texto da consulta original.
            chunks: Chunks recuperados pelo retriever.
            retrieve_fn: Função de retrieval para re-busca (opcional).
                         Assinatura: retrieve_fn(query: str) -> list[ChunkResultado]

        Returns:
            CorrectorResult com chunks filtrados e metadados.
        """
        if not chunks:
            return CorrectorResult(
                chunks_filtrados=[],
                chunks_removidos=0,
                query_reformulada=None,
                usou_reformulacao=False,
            )

        try:
            resultado_llm = self._chamar_llm(query, chunks)
        except Exception as e:
            logger.warning("CRAG: falha na avaliação LLM (%s) — retornando chunks originais", e)
            return CorrectorResult(
                chunks_filtrados=chunks,
                chunks_removidos=0,
                query_reformulada=None,
                usou_reformulacao=False,
            )

        avaliacoes = resultado_llm.get("avaliacoes", [])
        query_reformulada = resultado_llm.get("query_reformulada")

        # Mapear avaliações por ID (1-indexed)
        relevancia_map: dict[int, str] = {}
        for av in avaliacoes:
            relevancia_map[av.get("id", 0)] = av.get("relevancia", "relevante")

        # Filtrar: manter relevantes e parciais
        filtrados = []
        removidos = 0
        for i, chunk in enumerate(chunks, 1):
            rel = relevancia_map.get(i, "relevante")  # default: manter
            if rel == "irrelevante":
                removidos += 1
                logger.info("CRAG: chunk %d removido (irrelevante) — %s %s",
                            chunk.chunk_id, chunk.norma_codigo, chunk.artigo)
            else:
                filtrados.append(chunk)

        logger.info("CRAG: %d/%d chunks mantidos, %d removidos",
                    len(filtrados), len(chunks), removidos)

        # Re-retrieval se poucos chunks relevantes restaram
        usou_reformulacao = False
        if len(filtrados) < MIN_CHUNKS_RELEVANTES and query_reformulada and retrieve_fn:
            logger.info("CRAG: poucos chunks relevantes (%d) — re-retrieval com: %s",
                        len(filtrados), query_reformulada[:80])
            try:
                novos_chunks = retrieve_fn(query_reformulada)
                # Merge: adicionar novos que não estão nos filtrados
                ids_existentes = {c.chunk_id for c in filtrados}
                for nc in novos_chunks:
                    if nc.chunk_id not in ids_existentes:
                        filtrados.append(nc)
                        ids_existentes.add(nc.chunk_id)
                usou_reformulacao = True
                logger.info("CRAG: re-retrieval adicionou %d chunks novos",
                            len(filtrados) - len(ids_existentes) + len(novos_chunks))
            except Exception as e:
                logger.warning("CRAG: falha no re-retrieval (%s)", e)

        # Verificação de vigência dos chunks mantidos
        norma_codigos = list({c.norma_codigo for c in filtrados})
        alertas_vig = verificar_vigencia_chunks(norma_codigos, data_analise=date.today())
        if alertas_vig:
            logger.info("CRAG: %d alerta(s) de vigência detectados: %s",
                        len(alertas_vig), [a.codigo for a in alertas_vig])

        return CorrectorResult(
            chunks_filtrados=filtrados,
            chunks_removidos=removidos,
            query_reformulada=query_reformulada,
            usou_reformulacao=usou_reformulacao,
            alertas_vigencia=alertas_vig,
        )
