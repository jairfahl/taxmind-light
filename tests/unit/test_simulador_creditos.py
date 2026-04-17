"""
tests/unit/test_simulador_creditos.py — Testes unitários do MP-02 Monitor de Créditos IBS/CBS.

Verifica categorias de creditamento, cálculos e conformidade com LC 214/2025 arts. 28, 57.
Nenhuma chamada externa — matemática pura.
"""

import pytest

from src.simuladores.creditos_ibs_cbs import (
    ItemAquisicao,
    ResultadoMonitorCreditos,
    TipoCreditamento,
    mapear_creditos,
    _calcular_credito_item,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def item_insumo():
    return ItemAquisicao(categoria="insumos_diretos", valor_mensal=100_000.0)


@pytest.fixture
def item_capex():
    return ItemAquisicao(categoria="ativo_imobilizado", valor_mensal=200_000.0)


@pytest.fixture
def item_simples():
    return ItemAquisicao(categoria="fornecedor_simples", valor_mensal=50_000.0)


@pytest.fixture
def item_uso_consumo():
    return ItemAquisicao(categoria="uso_consumo", valor_mensal=30_000.0)


@pytest.fixture
def item_imune():
    return ItemAquisicao(categoria="operacoes_imunes_isentas", valor_mensal=20_000.0)


# ---------------------------------------------------------------------------
# Insumos diretos — crédito integral
# ---------------------------------------------------------------------------

def test_insumos_diretos_creditamento_integral(item_insumo):
    r = _calcular_credito_item(item_insumo)
    assert r.creditamento == TipoCreditamento.INTEGRAL
    esperado = 100_000.0 * (0.088 + 0.177)
    assert r.credito_estimado_mensal == pytest.approx(esperado)


# ---------------------------------------------------------------------------
# CR-1 fix: uso_consumo deve gerar crédito integral (art. 28 + art. 57 LC 214/2025)
# ---------------------------------------------------------------------------

def test_uso_consumo_agora_integral(item_uso_consumo):
    """Despesas gerais de negócio SÃO creditáveis (art. 28); art. 57 só exclui uso pessoal."""
    r = _calcular_credito_item(item_uso_consumo)
    assert r.creditamento == TipoCreditamento.INTEGRAL, (
        "uso_consumo não deve ser INDEFINIDO — art. 28 LC 214/2025 garante crédito amplo; "
        "art. 57 define taxativamente as exceções (uso pessoal)"
    )
    assert r.credito_estimado_mensal > 0


def test_uso_consumo_base_legal_correta(item_uso_consumo):
    """Base legal deve referenciar arts. 28 e 57, não 'regulamentação pendente'."""
    r = _calcular_credito_item(item_uso_consumo)
    assert "57" in r.base_legal, "art. 57 deve constar na base legal do uso_consumo"


def test_uso_consumo_alerta_menciona_excecoes(item_uso_consumo):
    """Alerta deve orientar sobre as exceções do art. 57 (uso pessoal)."""
    r = _calcular_credito_item(item_uso_consumo)
    assert r.alerta != "", "alerta de uso_consumo não deve ser vazio"


# ---------------------------------------------------------------------------
# Fornecedor Simples Nacional — crédito presumido
# ---------------------------------------------------------------------------

def test_fornecedor_simples_presumido(item_simples):
    r = _calcular_credito_item(item_simples)
    assert r.creditamento == TipoCreditamento.PRESUMIDO
    esperado = 50_000.0 * 0.04
    assert r.credito_estimado_mensal == pytest.approx(esperado)


def test_fornecedor_simples_ressalva_presente(item_simples):
    r = _calcular_credito_item(item_simples)
    assert any("estimativa" in s.lower() for s in r.ressalvas)


# ---------------------------------------------------------------------------
# Operações imunes/isentas — sem crédito
# ---------------------------------------------------------------------------

def test_operacoes_imunes_sem_credito(item_imune):
    r = _calcular_credito_item(item_imune)
    assert r.creditamento == TipoCreditamento.NENHUM
    assert r.credito_estimado_mensal == 0.0


def test_operacoes_imunes_alerta_sem_sinief_inventado(item_imune):
    """Referência 'Ajuste SINIEF 49/2025' não verificável deve ter sido removida."""
    r = _calcular_credito_item(item_imune)
    assert "SINIEF 49" not in r.alerta, "Referência 'Ajuste SINIEF 49/2025' não verificável não deve aparecer"


# ---------------------------------------------------------------------------
# CAPEX — crédito integral + oportunidade destacada
# ---------------------------------------------------------------------------

def test_capex_creditamento_integral(item_capex):
    r = _calcular_credito_item(item_capex)
    assert r.creditamento == TipoCreditamento.INTEGRAL
    assert r.credito_estimado_mensal > 0


# ---------------------------------------------------------------------------
# CR-2 fix: prazo de restituição padrão deve ser 180 dias
# ---------------------------------------------------------------------------

def test_prazo_restituicao_padrao_180_dias():
    """Prazo padrão de ressarcimento de créditos é 180 dias (art. 39 LC 214/2025)."""
    itens = [ItemAquisicao(categoria="insumos_diretos", valor_mensal=100_000.0)]
    resultado = mapear_creditos(itens)
    assert resultado.prazo_restituicao_dias == 180, (
        f"prazo_restituicao_dias deve ser 180 (padrão art. 39 LC 214/2025), "
        f"não {resultado.prazo_restituicao_dias}"
    )


# ---------------------------------------------------------------------------
# mapear_creditos — totais e alertas
# ---------------------------------------------------------------------------

def test_mapear_totais_corretos(item_insumo, item_capex, item_simples):
    resultado = mapear_creditos([item_insumo, item_capex, item_simples])
    assert isinstance(resultado, ResultadoMonitorCreditos)
    assert resultado.total_aquisicoes_mensal == pytest.approx(350_000.0)
    assert resultado.total_credito_mensal > 0
    assert resultado.total_credito_anual == pytest.approx(resultado.total_credito_mensal * 12)


def test_mapear_oportunidade_capex(item_capex):
    resultado = mapear_creditos([item_capex])
    assert resultado.oportunidade_capex > 0


def test_mapear_alertas_presentes():
    itens = [
        ItemAquisicao(categoria="uso_consumo", valor_mensal=10_000.0),
        ItemAquisicao(categoria="fornecedor_simples", valor_mensal=5_000.0),
    ]
    resultado = mapear_creditos(itens)
    assert len(resultado.alertas) >= 1


def test_categoria_invalida_retorna_indefinido():
    item = ItemAquisicao(categoria="categoria_inexistente", valor_mensal=10_000.0)
    r = _calcular_credito_item(item)
    assert r.creditamento == TipoCreditamento.INDEFINIDO
    assert r.credito_estimado_mensal == 0.0
