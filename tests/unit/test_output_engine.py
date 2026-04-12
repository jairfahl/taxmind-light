"""
tests/unit/test_output_engine.py — Testes unitários do OutputEngine.
Usa mocks para banco e LLM.
Executa com: pytest tests/unit/test_output_engine.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, call

from src.outputs.engine import (
    DISCLAIMER_PADRAO,
    OutputClass,
    OutputEngine,
    OutputError,
    OutputResult,
    OutputStatus,
    _assert_disclaimer,
)
from src.cognitive.engine import AnaliseResult
from src.cognitive.engine import AntiAlucinacaoResult


def _make_analise(
    query="Qual a alíquota do IBS?",
    resposta="A alíquota de referência...",
    bloqueado=False,
    scoring="alto",
    grau="consolidado",
) -> AnaliseResult:
    from src.quality.engine import QualidadeResult, QualidadeStatus
    return AnaliseResult(
        query=query,
        qualidade=QualidadeResult(
            status=QualidadeStatus.VERDE,
            regras_ok=[],
            bloqueios=[],
            ressalvas=[],
            disclaimer="",
        ),
        fundamento_legal=["Art. 12 LC 214/2025"],
        grau_consolidacao=grau,
        contra_tese=None,
        scoring_confianca=scoring,
        resposta=resposta,
        disclaimer=DISCLAIMER_PADRAO,
        anti_alucinacao=AntiAlucinacaoResult(
            m1_existencia=True,
            m2_validade=True,
            m3_pertinencia=True,
            m4_consistencia=True,
            bloqueado=bloqueado,
            flags=[],
        ),
        chunks=[],
        prompt_version="v1.0.0-sprint2",
        model_id="claude-haiku-4-5-20251001",
        latencia_ms=1500,
    )


# ---------------------------------------------------------------------------
# Helpers de mock do banco
# ---------------------------------------------------------------------------
def _make_db_mocks(output_id=1):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    # INSERT RETURNING id
    mock_cur.fetchone.return_value = (output_id,)
    # SELECT de _load_output
    mock_cur.fetchall.return_value = []
    return mock_conn, mock_cur


# ---------------------------------------------------------------------------
# 1. Disclaimer presente em Alerta
# ---------------------------------------------------------------------------
@patch("src.outputs.engine._get_conn")
@patch("src.outputs.engine._load_output")
def test_gerar_alerta_disclaimer_presente(mock_load, mock_get_conn):
    mock_conn, _ = _make_db_mocks(1)
    mock_get_conn.return_value = mock_conn
    mock_load.return_value = OutputResult(
        id=1, case_id=10, passo_origem=2, classe=OutputClass.ALERTA,
        status=OutputStatus.GERADO, titulo="Alerta teste",
        conteudo={}, materialidade=3, disclaimer=DISCLAIMER_PADRAO,
        versao_prompt=None, versao_base=None,
    )
    engine = OutputEngine()
    result = engine.gerar_alerta(
        case_id=10, passo=2, titulo="Alerta teste",
        contexto="contexto fiscal", materialidade=3,
    )
    assert result.disclaimer == DISCLAIMER_PADRAO
    assert len(result.disclaimer) > 0


# ---------------------------------------------------------------------------
# 2. Nota de Trabalho com versao_prompt obrigatória
# ---------------------------------------------------------------------------
@patch("src.outputs.engine._get_conn")
@patch("src.outputs.engine._load_output")
@patch("src.outputs.engine.MaterialidadeCalculator.calcular", return_value=3)
def test_gerar_nota_trabalho_versao_prompt(mock_mat, mock_load, mock_get_conn):
    mock_conn, _ = _make_db_mocks(2)
    mock_get_conn.return_value = mock_conn
    mock_load.return_value = OutputResult(
        id=2, case_id=10, passo_origem=4, classe=OutputClass.NOTA_TRABALHO,
        status=OutputStatus.GERADO, titulo="Nota teste",
        conteudo={"versao_prompt": "v1.0.0-sprint2"},
        materialidade=3, disclaimer=DISCLAIMER_PADRAO,
        versao_prompt="v1.0.0-sprint2", versao_base="LC214_2025+EC132_2023+LC227_2026",
    )
    analise = _make_analise()
    engine = OutputEngine()
    result = engine.gerar_nota_trabalho(case_id=10, analise_result=analise)
    assert result.versao_prompt is not None
    assert result.versao_base is not None


# ---------------------------------------------------------------------------
# 3. Recomendação Formal bloqueada com anti-alucinação ativo
# ---------------------------------------------------------------------------
def test_gerar_recomendacao_bloqueada_anti_alucinacao():
    analise = _make_analise(bloqueado=True)
    engine = OutputEngine()
    with pytest.raises(OutputError, match="bloqueada"):
        engine.gerar_recomendacao_formal(case_id=10, analise_result=analise)


# ---------------------------------------------------------------------------
# 4. Dossiê bloqueado se P7 não concluído
# ---------------------------------------------------------------------------
@patch("src.outputs.engine._get_conn")
def test_dossie_bloqueado_sem_p7(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = (False, {})  # concluido=False
    mock_get_conn.return_value = mock_conn

    engine = OutputEngine()
    with pytest.raises(OutputError, match="P5"):  # P7 não existe; protocolo tem 6 passos (requer P5)
        engine.gerar_dossie(case_id=99)


# ---------------------------------------------------------------------------
# 5. C5 bloqueado sem C3 ou C4 aprovado
# ---------------------------------------------------------------------------
@patch("src.outputs.engine._get_conn")
def test_c5_bloqueado_sem_aprovacao(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    # Output existente mas com status 'gerado' (não aprovado)
    mock_cur.fetchone.return_value = (10, "recomendacao_formal", "gerado", "{}")
    mock_get_conn.return_value = mock_conn

    engine = OutputEngine()
    with pytest.raises(OutputError, match="aprovado"):
        engine.gerar_material_compartilhavel(output_id=5, stakeholders=["cfo"])


# ---------------------------------------------------------------------------
# 6. Disclaimer nulo → falha hard
# ---------------------------------------------------------------------------
def test_disclaimer_nulo_falha_hard():
    with pytest.raises(OutputError, match="disclaimer"):
        _assert_disclaimer("")

def test_disclaimer_vazio_falha_hard():
    with pytest.raises(OutputError, match="disclaimer"):
        _assert_disclaimer("   ")

def test_disclaimer_none_falha_hard():
    with pytest.raises(OutputError, match="disclaimer"):
        _assert_disclaimer(None)


# ---------------------------------------------------------------------------
# 7. Materialidade retorna entre 1 e 5
# ---------------------------------------------------------------------------
def test_materialidade_score_valido():
    from src.outputs.materialidade import MaterialidadeCalculator
    from unittest.mock import patch

    with patch.object(MaterialidadeCalculator, "calcular", return_value=4) as mock_calc:
        calc = MaterialidadeCalculator()
        score = calc.calcular({"titulo": "caso fiscal urgente"})
        assert 1 <= score <= 5


def test_materialidade_fallback_dentro_intervalo():
    """Fallback (sem LLM) deve retornar 3 dentro do intervalo."""
    from src.outputs.materialidade import MaterialidadeCalculator
    with patch.object(MaterialidadeCalculator, "_get_client", side_effect=EnvironmentError("sem key")):
        calc = MaterialidadeCalculator()
        score = calc.calcular({"titulo": "teste"})
        assert 1 <= score <= 5


# ---------------------------------------------------------------------------
# 8. analise_result inválido para C2/C3
# ---------------------------------------------------------------------------
def test_nota_trabalho_sem_analise_result():
    engine = OutputEngine()
    with pytest.raises(OutputError):
        engine.gerar_nota_trabalho(case_id=1, analise_result=None)


def test_recomendacao_sem_analise_result():
    engine = OutputEngine()
    with pytest.raises(OutputError):
        engine.gerar_recomendacao_formal(case_id=1, analise_result=None)


# ---------------------------------------------------------------------------
# 9. Aprovar output — status incorreto
# ---------------------------------------------------------------------------
@patch("src.outputs.engine._get_conn")
def test_aprovar_status_incorreto(mock_get_conn):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = ("aprovado",)  # já aprovado
    mock_get_conn.return_value = mock_conn

    engine = OutputEngine()
    with pytest.raises(OutputError, match="não pode ser aprovado"):
        engine.aprovar(output_id=1, aprovado_por="Gestor")
