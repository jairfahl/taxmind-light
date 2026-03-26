"""
tests/unit/test_protocol_engine.py — Testes unitários do ProtocolStateEngine.
Executa com: pytest tests/unit/test_protocol_engine.py -v

Protocolo de 6 passos:
  Step 1 — Registrar & Classificar  (titulo, descricao, contexto_fiscal, premissas, periodo_fiscal)
  Step 2 — Estruturar               (riscos, dados_qualidade)
  Step 3 — Analisar                 (query_analise, analise_result)
  Step 4 — Hipotetizar              (hipotese_gestor)
  Step 5 — Decidir                  (recomendacao, decisao_final, decisor)
  Step 6 — Ciclo Pós-Decisão        (resultado_real, data_revisao, aprendizado_extraido)

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
    """Todos os passos 1-6 devem ter entradas no mapa de transições."""
    for passo in range(1, 7):
        assert passo in TRANSICOES_VALIDAS, f"Passo {passo} ausente em TRANSICOES_VALIDAS"


def test_p6_e_terminal():
    assert TRANSICOES_VALIDAS[6] == [], "Step 6 deve ser terminal (lista vazia)"


def test_p1_avanca_para_p2():
    assert 2 in TRANSICOES_VALIDAS[1]


def test_p1_nao_permite_voltar():
    """Step 1 não tem transições de retorno — é o passo inicial."""
    assert 0 not in TRANSICOES_VALIDAS[1]
    # Step 1 só avança para 2; nenhuma transição backward existe
    assert all(t >= 1 for t in TRANSICOES_VALIDAS[1])


# ---------------------------------------------------------------------------
# 2. Validação de dados por passo
# ---------------------------------------------------------------------------
# Step 1 — Registrar & Classificar (absorve antigos P1+P2)
def test_validar_dados_step1_valido():
    dados = {
        "titulo": "Caso tributário válido",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
        "premissas": ["premissa 1", "premissa 2"],
        "periodo_fiscal": "2025-01 a 2025-12",
    }
    _validar_dados_passo(1, dados)  # não deve lançar


def test_validar_dados_step1_titulo_curto():
    dados = {
        "titulo": "Curto",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
        "premissas": ["p1", "p2"],
        "periodo_fiscal": "2025",
    }
    with pytest.raises(ProtocolError, match="nome do caso deve ter pelo menos 10"):
        _validar_dados_passo(1, dados)


def test_validar_dados_step1_campo_ausente():
    dados = {"titulo": "Titulo longo suficiente", "descricao": "desc"}
    with pytest.raises(ProtocolError, match="Preencha todos os campos obrigatórios"):
        _validar_dados_passo(1, dados)


def test_validar_dados_step1_premissas_insuficientes():
    dados = {
        "titulo": "Caso tributário válido",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
        "premissas": ["só uma premissa"],
        "periodo_fiscal": "2025",
    }
    with pytest.raises(ProtocolError, match="pelo menos 2 premissas"):
        _validar_dados_passo(1, dados)


# Step 2 — Estruturar (antigo P3)
def test_validar_dados_step2_sem_risco():
    dados = {"riscos": [], "dados_qualidade": "ok"}
    with pytest.raises(ProtocolError, match="Identifique pelo menos 1 risco"):
        _validar_dados_passo(2, dados)


def test_validar_dados_step2_valido():
    dados = {"riscos": ["Risco de autuação fiscal"], "dados_qualidade": "Dados completos"}
    _validar_dados_passo(2, dados)  # não deve lançar


# Step 3 — Analisar (antigo P4)
def test_validar_dados_step3_valido():
    dados = {"query_analise": "SELECT * FROM nf WHERE ...", "analise_result": "Resultado da análise"}
    _validar_dados_passo(3, dados)  # não deve lançar


def test_validar_dados_step3_campo_ausente():
    dados = {"query_analise": "SELECT 1"}
    with pytest.raises(ProtocolError, match="Preencha todos os campos obrigatórios"):
        _validar_dados_passo(3, dados)


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
        premissas=["premissa 1", "premissa 2"],
        periodo_fiscal="2025-01 a 2025-12",
    )
    assert isinstance(case_id, int)
    assert case_id > 0


def test_criar_caso_estado_inicial():
    """Estado inicial deve ser step=1 / status=rascunho."""
    engine = ProtocolStateEngine()
    case_id = engine.criar_caso(
        titulo="Caso estado inicial validar",
        descricao="desc",
        contexto_fiscal="ctx",
        premissas=["premissa 1", "premissa 2"],
        periodo_fiscal="2025",
    )
    estado = engine.get_estado(case_id)
    assert estado.passo_atual == 1
    assert estado.status == "rascunho"
    assert estado.case_id == case_id


# ---------------------------------------------------------------------------
# 4. ProtocolStateEngine — avancar
# ---------------------------------------------------------------------------
def test_avancar_step1_para_step2():
    engine = ProtocolStateEngine()
    case_id = engine.criar_caso(
        titulo="Caso avancar step1 para step2",
        descricao="desc",
        contexto_fiscal="ctx",
        premissas=["premissa 1", "premissa 2"],
        periodo_fiscal="2025",
    )
    dados_step1 = {
        "titulo": "Caso avancar step1 para step2",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
        "premissas": ["premissa 1", "premissa 2"],
        "periodo_fiscal": "2025",
    }
    step = engine.avancar(case_id, 1, dados_step1)
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
        premissas=["p1", "p2"],
        periodo_fiscal="2025",
    )
    with pytest.raises(ProtocolError):
        engine.avancar(case_id, 99, {})


def test_avancar_step6_dados_vazios_valida():
    """Step 6 com dados vazios deve lançar ProtocolError de validação (aprendizado_extraido obrigatório)."""
    engine = ProtocolStateEngine()
    with pytest.raises(ProtocolError, match="aprendizado_extraido"):
        engine.avancar(1, 6, {})


# ---------------------------------------------------------------------------
# 5. ProtocolStateEngine — voltar
# ---------------------------------------------------------------------------
def test_voltar_step1_nao_permitido():
    """Step 1 não permite retroceder — é o passo inicial."""
    engine = ProtocolStateEngine()
    with pytest.raises(ProtocolError, match="não permite retroceder"):
        engine.voltar(1, 1)


def test_voltar_step6_nao_permitido():
    """Step 6 é terminal — não permite retroceder."""
    engine = ProtocolStateEngine()
    with pytest.raises(ProtocolError, match="não permite retroceder"):
        engine.voltar(1, 6)


def test_voltar_step2_para_step1():
    """Step 2 permite voltar para Step 1."""
    engine = ProtocolStateEngine()
    case_id = engine.criar_caso(
        titulo="Caso voltar step2 para step1",
        descricao="desc",
        contexto_fiscal="ctx",
        premissas=["p1", "p2"],
        periodo_fiscal="2025",
    )
    # Avançar para Step 2 primeiro
    engine.avancar(case_id, 1, {
        "titulo": "Caso voltar step2 para step1",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
        "premissas": ["p1", "p2"],
        "periodo_fiscal": "2025",
    })
    step = engine.voltar(case_id, 2)
    assert step.passo == 1


# ---------------------------------------------------------------------------
# 6. ProtocolStateEngine — Step 4 → Step 5 bloqueio (hipótese gating)
# ---------------------------------------------------------------------------
def test_step5_requer_step4_concluido():
    """Avançar de Step 4 para Step 5 sem hipotese_gestor preenchido deve lançar ProtocolError."""
    engine = ProtocolStateEngine()
    # Criar caso e avançar até Step 3 → Step 4
    case_id = engine.criar_caso(
        titulo="Caso bloqueio Step5 sem Step4",
        descricao="desc",
        contexto_fiscal="ctx",
        premissas=["p1", "p2"],
        periodo_fiscal="2025",
    )
    engine.avancar(case_id, 1, {
        "titulo": "Caso bloqueio Step5 sem Step4",
        "descricao": "desc",
        "contexto_fiscal": "ctx",
        "premissas": ["p1", "p2"],
        "periodo_fiscal": "2025",
    })
    engine.avancar(case_id, 2, {
        "riscos": ["risco fiscal"],
        "dados_qualidade": "ok",
    })
    engine.avancar(case_id, 3, {
        "query_analise": "SELECT 1",
        "analise_result": "resultado",
    })
    # Agora estamos em Step 4 (Hipotetizar) — tentar avançar para Step 5 SEM concluir hipotese_gestor
    pode, motivo = engine.pode_avancar(case_id, 4)
    assert not pode
    assert (
        "4" in motivo
        or "hipótese" in motivo.lower()
        or "hipotese" in motivo.lower()
        or "concluído" in motivo.lower()
    )


# ---------------------------------------------------------------------------
# 7. ProtocolStateEngine — get_estado caso inexistente
# ---------------------------------------------------------------------------
def test_get_estado_caso_inexistente():
    engine = ProtocolStateEngine()
    with pytest.raises(ProtocolError, match="não encontrado"):
        engine.get_estado(999999)


# ---------------------------------------------------------------------------
# 8. Campos obrigatórios cobrem todos os passos 1-6
# ---------------------------------------------------------------------------
def test_campos_obrigatorios_todos_passos():
    for passo in range(1, 7):
        assert passo in CAMPOS_OBRIGATORIOS, f"Passo {passo} sem campos obrigatórios"
        assert len(CAMPOS_OBRIGATORIOS[passo]) >= 1


def test_campos_obrigatorios_step1_tem_campos_merged():
    """Step 1 deve conter campos de ambos os antigos P1 e P2."""
    campos = CAMPOS_OBRIGATORIOS[1]
    assert "titulo" in campos
    assert "descricao" in campos
    assert "contexto_fiscal" in campos
    assert "premissas" in campos
    assert "periodo_fiscal" in campos


def test_campos_obrigatorios_step5_tem_campos_decisao():
    """Step 5 deve conter campos de decisão (antigos P6+P7)."""
    campos = CAMPOS_OBRIGATORIOS[5]
    assert "recomendacao" in campos
    assert "decisao_final" in campos
    assert "decisor" in campos


def test_campos_obrigatorios_step6_tem_campos_pos_decisao():
    """Step 6 deve conter campos de ciclo pós-decisão (antigos P8+P9)."""
    campos = CAMPOS_OBRIGATORIOS[6]
    assert "resultado_real" in campos
    assert "data_revisao" in campos
    assert "aprendizado_extraido" in campos
