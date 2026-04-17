"""
tests/unit/test_creditos_ibs_cbs.py — Testes unitários do MP-02 Monitor de Créditos (G19).

Verifica categorias, tipos de creditamento, cálculos e alertas.
Nenhuma chamada externa — matemática pura.
"""

from src.simuladores.creditos_ibs_cbs import (
    CATEGORIAS_AQUISICAO,
    ItemAquisicao,
    TipoCreditamento,
    _calcular_credito_item,
    mapear_creditos,
)


def test_seis_categorias_definidas():
    assert len(CATEGORIAS_AQUISICAO) >= 6


def test_insumos_diretos_creditamento_integral():
    item = ItemAquisicao(categoria="insumos_diretos", valor_mensal=100_000.0)
    r = _calcular_credito_item(item)
    assert r.creditamento == TipoCreditamento.INTEGRAL
    assert r.credito_estimado_mensal > 0


def test_operacoes_imunes_sem_credito():
    item = ItemAquisicao(categoria="operacoes_imunes_isentas", valor_mensal=100_000.0)
    r = _calcular_credito_item(item)
    assert r.creditamento == TipoCreditamento.NENHUM
    assert r.credito_estimado_mensal == 0.0


def test_fornecedor_simples_credito_presumido():
    item = ItemAquisicao(categoria="fornecedor_simples", valor_mensal=100_000.0)
    r = _calcular_credito_item(item)
    assert r.creditamento == TipoCreditamento.PRESUMIDO
    assert 0 < r.credito_estimado_mensal < 100_000.0 * 0.265


def test_uso_consumo_integral_art28_57():
    """CR-1 fix: art. 28 LC 214/2025 garante crédito amplo; art. 57 só exclui uso pessoal.
    Despesas gerais de negócio SÃO creditáveis — classificação INDEFINIDO estava errada."""
    item = ItemAquisicao(categoria="uso_consumo", valor_mensal=50_000.0)
    r = _calcular_credito_item(item)
    assert r.creditamento == TipoCreditamento.INTEGRAL
    assert r.credito_estimado_mensal > 0.0


def test_mapear_creditos_soma_correta():
    itens = [
        ItemAquisicao(categoria="insumos_diretos", valor_mensal=200_000.0),
        ItemAquisicao(categoria="servicos_tomados", valor_mensal=100_000.0),
    ]
    r = mapear_creditos(itens)
    assert r.total_aquisicoes_mensal == 300_000.0
    assert r.total_credito_mensal > 0
    assert r.total_credito_anual == r.total_credito_mensal * 12


def test_oportunidade_capex_detectada():
    itens = [ItemAquisicao(categoria="ativo_imobilizado", valor_mensal=500_000.0)]
    r = mapear_creditos(itens)
    assert r.oportunidade_capex > 0


def test_alerta_gerado_para_categorias_risco():
    itens = [
        ItemAquisicao(categoria="uso_consumo", valor_mensal=50_000.0),
        ItemAquisicao(categoria="operacoes_imunes_isentas", valor_mensal=30_000.0),
    ]
    r = mapear_creditos(itens)
    assert len(r.alertas) >= 2
