"""
tests/unit/test_protocol_engine.py — Testes unitários do ProtocolStateEngine.
Executa com: pytest tests/unit/test_protocol_engine.py -v

Requer banco rodando (DATABASE_URL no .env).
"""

import json

import pytest
from unittest.mock import MagicMock, patch, call

from src.protocol.engine import (
    CAMPOS_OBRIGATORIOS,
    PASSO_STATUS,
    TRANSICOES_VALIDAS,
    CaseEstado,
    CaseStep,
    ProtocolError,
    ProtocolStateEngine,
    _validar_dados_passo,
)


# ---------------------------------------------------------------------------
# 1. Transições válidas definidas corretamente
# ---------------------------------------------------------------------------
def test_transicoes_cobertura_completa():
    """Todos os passos 1-9 devem ter entradas no mapa de transições."""
    for passo in range(1, 10):
        assert passo in TRANSICOES_VALIDAS, f"Passo {passo} ausente em TRANSICOES_VALIDAS"


def test_p9_e_terminal():
    assert TRANSICOES_VALIDAS[9] == [], "P9 deve ser terminal (lista vazia)"


def test_p1_avanca_para_p2():
    assert 2 in TRANSICOES_VALIDAS[1]


def test_p7_nao_permite_voltar():
    """P7 avança para P8 mas não permite voltar."""
    assert len(TRANSICOES_VALIDAS[7]) == 1
    assert TRANSICOES_VALIDAS[7][0] == 8


# ---------------------------------------------------------------------------
# 2. Validação de dados por passo
# ---------------------------------------------------------------------------
def test_validar_dados_p1_valido():
    dados = {"titulo": "Caso tributário válido", "descricao": "desc", "contexto_fiscal": "ctx"}
    _validar_dados_passo(1, dados)  # não deve lançar


def test_validar_dados_p1_titulo_curto():
    dados = {"titulo": "Curto", "descricao": "desc", "contexto_fiscal": "ctx"}
    with pytest.raises(ProtocolError, match="título deve ter no mínimo"):
        _validar_dados_passo(1, dados)


def test_validar_dados_p1_campo_ausente():
    dados = {"titulo": "Titulo longo suficiente", "descricao": "desc"}
    with pytest.raises(ProtocolError, match="campos obrigatórios ausentes"):
        _validar_dados_passo(1, dados)


def test_validar_dados_p2_premissas_insuficientes():
    dados = {"premissas": ["só uma premissa"], "periodo_fiscal": "2025"}
    with pytest.raises(ProtocolError, match="pelo menos 2 premissas"):
        _validar_dados_passo(2, dados)


def test_validar_dados_p2_valido():
    dados = {"premissas": ["premissa 1", "premissa 2"], "periodo_fiscal": "2025-01 a 2025-12"}
    _validar_dados_passo(2, dados)  # não deve lançar


def test_validar_dados_p3_sem_risco():
    dados = {"riscos": [], "dados_qualidade": "ok"}
    with pytest.raises(ProtocolError, match="pelo menos 1 risco"):
        _validar_dados_passo(3, dados)


def test_validar_dados_p3_valido():
    dados = {"riscos": ["Risco de autuação fiscal"], "dados_qualidade": "Dados completos"}
    _validar_dados_passo(3, dados)  # não deve lançar


# ---------------------------------------------------------------------------
# 3. ProtocolStateEngine — criar_caso
# ---------------------------------------------------------------------------
def test_criar_caso_retorna_int():
    """criar_caso deve retornar um inteiro (case_id)."""
    engine = ProtocolStateEngine()
    case_id = engine.criar_caso(
        titulo="Teste unitário protocolo engine",
        descricao="Descrição do caso de teste",
        contexto_fiscal="Lucro Presumido",
    )
    assert isinstance(case_id, int)
    assert case_id > 0


def test_criar_caso_estado_inicial():
    """Estado inicial deve ser passo=1 / status=rascunho."""
    engine = ProtocolStateEngine()
    case_id = engine.criar_caso(
        titulo="Caso estado inicial validar",
        descricao="desc",
        contexto_fiscal="ctx",
    )
    estado = engine.get_estado(case_id)
    assert estado.passo_atual == 1
    assert estado.status == "rascunho"
    assert estado.case_id == case_id


# ---------------------------------------------------------------------------
# 4. ProtocolStateEngine — avancar
# ---------------------------------------------------------------------------
def test_avancar_p1_para_p2():
    engine = ProtocolStateEngine()
    case_id = engine.criar_caso(
        titulo="Caso avancar p1 para p2",
        descricao="desc",
        contexto_fiscal="ctx",
    )
    dados_p1 = {
        "titulo": "Caso avancar p1 para p2",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
    }
    step = engine.avancar(case_id, 1, dados_p1)
    assert step.passo == 2
    estado = engine.get_estado(case_id)
    assert estado.passo_atual == 2
    assert estado.status == "em_analise"


def test_avancar_passo_invalido():
    engine = ProtocolStateEngine()
    case_id = engine.criar_caso(
        titulo="Caso passo invalido teste",
        descricao="desc",
        contexto_fiscal="ctx",
    )
    with pytest.raises(ProtocolError):
        engine.avancar(case_id, 99, {})


def test_avancar_p9_dados_vazios_valida():
    """P9 com dados vazios deve lançar ProtocolError de validação (aprendizado_extraido obrigatório)."""
    engine = ProtocolStateEngine()
    with pytest.raises(ProtocolError, match="aprendizado_extraido"):
        engine.avancar(1, 9, {})


# ---------------------------------------------------------------------------
# 5. ProtocolStateEngine — voltar
# ---------------------------------------------------------------------------
def test_voltar_p1_nao_permitido():
    """P1 não permite retroceder."""
    engine = ProtocolStateEngine()
    with pytest.raises(ProtocolError, match="não permite retroceder"):
        engine.voltar(1, 1)


def test_voltar_p2_para_p1():
    """P2 permite voltar para P1."""
    engine = ProtocolStateEngine()
    case_id = engine.criar_caso(
        titulo="Caso voltar p2 para p1",
        descricao="desc",
        contexto_fiscal="ctx",
    )
    # Avançar para P2 primeiro
    engine.avancar(case_id, 1, {
        "titulo": "Caso voltar p2 para p1",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
    })
    step = engine.voltar(case_id, 2)
    assert step.passo == 1


# ---------------------------------------------------------------------------
# 6. ProtocolStateEngine — P5 → P6 bloqueio
# ---------------------------------------------------------------------------
def test_p6_requer_p5_concluido():
    """Avançar de P5 para P6 sem P5 concluído deve lançar ProtocolError."""
    engine = ProtocolStateEngine()
    # Simular caso já em P5 sem P5 concluído
    # Criar caso e avançar até P4 → P5
    case_id = engine.criar_caso(
        titulo="Caso bloqueio P6 sem P5",
        descricao="desc",
        contexto_fiscal="ctx",
    )
    engine.avancar(case_id, 1, {
        "titulo": "Caso bloqueio P6 sem P5",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
    })
    engine.avancar(case_id, 2, {
        "premissas": ["p1", "p2"],
        "periodo_fiscal": "2025",
    })
    engine.avancar(case_id, 3, {
        "riscos": ["risco fiscal"],
        "dados_qualidade": "ok",
    })
    engine.avancar(case_id, 4, {
        "query_analise": "query",
        "analise_result": "resultado",
    })
    # Agora estamos em P5 — tentar avançar direto para P6 SEM concluir P5
    # verificar que pode_avancar retorna False
    pode, motivo = engine.pode_avancar(case_id, 5)
    assert not pode
    assert "P5" in motivo or "hipótese" in motivo.lower() or "concluído" in motivo.lower()


# ---------------------------------------------------------------------------
# 7. ProtocolStateEngine — get_estado caso inexistente
# ---------------------------------------------------------------------------
def test_get_estado_caso_inexistente():
    engine = ProtocolStateEngine()
    with pytest.raises(ProtocolError, match="não encontrado"):
        engine.get_estado(999999)


# ---------------------------------------------------------------------------
# 8. Campos obrigatórios cobrem todos os passos 1-9
# ---------------------------------------------------------------------------
def test_campos_obrigatorios_todos_passos():
    for passo in range(1, 10):
        assert passo in CAMPOS_OBRIGATORIOS, f"Passo {passo} sem campos obrigatórios"
        assert len(CAMPOS_OBRIGATORIOS[passo]) >= 1
