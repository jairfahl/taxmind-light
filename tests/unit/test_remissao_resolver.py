"""
tests/unit/test_remissao_resolver.py — Testes unitários do RAR (C4, G12).

Não faz chamadas ao banco: apenas lógica pura do módulo.
"""

from src.rag.remissao_resolver import (
    MAX_CHUNKS_POR_REMISSAO,
    MAX_REMISSOES_POR_QUERY,
    ChunkRemissao,
    ResultadoRAR,
    _extrair_artigo_da_remissao,
    formatar_chunks_rar_para_contexto,
    resolver_remissoes,
)


def test_extrair_artigo_padrao_simples():
    texto = "conforme disposto no art. 28 da LC 214/2025"
    artigo = _extrair_artigo_da_remissao(texto)
    assert artigo == "28"


def test_extrair_artigo_paragrafo():
    texto = "nos termos do § 3º deste artigo"
    artigo = _extrair_artigo_da_remissao(texto)
    # Captura "3º" (com ordinal) — esperado pelo regex \d+[°º]?
    assert artigo is not None and "3" in artigo


def test_extrair_artigo_sem_referencia():
    texto = "texto sem referência a artigo específico"
    artigo = _extrair_artigo_da_remissao(texto)
    assert artigo is None


def test_resolver_sem_remissoes():
    chunks = [
        {"chunk_id": 1, "norma_id": 1, "texto": "texto a", "remissao_norm_id": None, "score_final": 0.9},
        {"chunk_id": 2, "norma_id": 2, "texto": "texto b", "remissao_norm_id": None, "score_final": 0.8},
    ]
    resultado = resolver_remissoes(chunks)
    assert resultado.remissoes_resolvidas == 0
    assert resultado.chunks_remissoes == []
    assert resultado.remissoes_nao_encontradas == []


def test_formatar_contexto_vazio():
    resultado = ResultadoRAR(chunks_originais=[], chunks_remissoes=[])
    ctx = formatar_chunks_rar_para_contexto(resultado)
    assert ctx == ""


def test_limite_remissoes_por_query():
    assert MAX_REMISSOES_POR_QUERY == 3


def test_limite_chunks_por_remissao():
    assert MAX_CHUNKS_POR_REMISSAO == 2


def test_formatar_contexto_com_remissoes():
    resultado = ResultadoRAR(
        chunks_originais=[],
        chunks_remissoes=[
            ChunkRemissao(
                chunk_id=99,
                norma_id=1,
                norma_codigo="EC_132_2023",
                artigo="Art. 149-B",
                texto="Conteúdo do artigo referenciado.",
            )
        ],
        remissoes_resolvidas=1,
    )
    ctx = formatar_chunks_rar_para_contexto(resultado)
    assert "NORMAS REFERENCIADAS" in ctx
    assert "EC_132_2023" in ctx
    assert "Art. 149-B" in ctx
    assert "Conteúdo do artigo referenciado." in ctx


def test_resolver_chunks_sem_campo_remissao_nao_falha():
    # Chunks sem o campo remissao_norm_id nem geram erro nem chamam o banco
    chunks = [
        {"chunk_id": 1, "texto": "texto sem campo remissao", "score_final": 0.9},
    ]
    resultado = resolver_remissoes(chunks)
    assert resultado.remissoes_resolvidas == 0
    assert resultado.chunks_remissoes == []
