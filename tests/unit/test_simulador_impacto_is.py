"""
tests/unit/test_simulador_impacto_is.py — Testes unitários do MP-04 Impacto IS.

Verifica cálculo do Imposto Seletivo, produtos cobertos, ressalvas obrigatórias
e conformidade com LC 214/2025 arts. 411-453 + Anexo XVII.
Nenhuma chamada externa — matemática pura.
"""

import pytest

from src.simuladores.impacto_is import (
    PRODUTOS_IS,
    CenarioIS,
    ResultadoIS,
    calcular_impacto_is,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cenario_tabaco():
    return CenarioIS(
        produto="tabaco",
        preco_venda_atual=10.0,
        volume_mensal=1000,
        custo_producao=5.0,
        elasticidade="alta",
    )


@pytest.fixture
def cenario_veiculo():
    return CenarioIS(
        produto="veiculos",
        preco_venda_atual=100_000.0,
        volume_mensal=50,
        custo_producao=70_000.0,
        elasticidade="media",
    )


@pytest.fixture
def cenario_apostas():
    return CenarioIS(
        produto="apostas_jogos",
        preco_venda_atual=1_000.0,
        volume_mensal=200,
        custo_producao=200.0,
        elasticidade="media",
    )


@pytest.fixture
def cenario_combustivel():
    return CenarioIS(
        produto="combustiveis",
        preco_venda_atual=5.0,
        volume_mensal=100_000,
        custo_producao=3.5,
        elasticidade="baixa",
    )


# ---------------------------------------------------------------------------
# IS-1 fix: categorias obrigatórias do Anexo XVII LC 214/2025
# ---------------------------------------------------------------------------

def test_produtos_contem_apostas_jogos():
    """Apostas/jogos constam no Anexo XVII LC 214/2025 e devem estar no dicionário."""
    assert "apostas_jogos" in PRODUTOS_IS, (
        "apostas_jogos ausente — categoria do Anexo XVII LC 214/2025 (concursos de prognósticos)"
    )


def test_produtos_contem_combustiveis():
    """Combustíveis fósseis constam no Anexo XVII LC 214/2025."""
    assert "combustiveis" in PRODUTOS_IS, (
        "combustiveis ausente — categoria do Anexo XVII LC 214/2025"
    )


def test_produtos_base_existentes():
    """Produtos originais (tabaco, bebidas, veículos, etc.) devem permanecer."""
    for prod in ("tabaco", "bebidas_alcoolicas", "bebidas_acucaradas", "veiculos", "embarcacoes", "minerais"):
        assert prod in PRODUTOS_IS, f"produto '{prod}' não deve ter sido removido"


# ---------------------------------------------------------------------------
# Cálculo básico
# ---------------------------------------------------------------------------

def test_is_por_fora_aumenta_preco(cenario_tabaco):
    r = calcular_impacto_is(cenario_tabaco)
    assert r.preco_com_is > cenario_tabaco.preco_venda_atual


def test_is_por_unidade_correto(cenario_tabaco):
    aliq = PRODUTOS_IS["tabaco"]["aliquota_base"]
    esperado = cenario_tabaco.preco_venda_atual * aliq
    r = calcular_impacto_is(cenario_tabaco)
    assert r.is_por_unidade == pytest.approx(esperado)


def test_margem_absorvida_menor_que_atual(cenario_tabaco):
    r = calcular_impacto_is(cenario_tabaco)
    assert r.margem_com_is < r.margem_atual


def test_delta_margem_negativo(cenario_tabaco):
    r = calcular_impacto_is(cenario_tabaco)
    assert r.delta_margem < 0


def test_is_total_mensal(cenario_tabaco):
    r = calcular_impacto_is(cenario_tabaco)
    assert r.is_total_mensal == pytest.approx(r.is_por_unidade * cenario_tabaco.volume_mensal)


def test_aliquota_customizada(cenario_veiculo):
    cenario_custom = CenarioIS(
        produto="veiculos",
        preco_venda_atual=100_000.0,
        volume_mensal=10,
        custo_producao=70_000.0,
        elasticidade="baixa",
        aliquota_customizada=0.05,
    )
    r = calcular_impacto_is(cenario_custom)
    assert r.aliquota_usada == pytest.approx(0.05)
    assert r.is_por_unidade == pytest.approx(100_000.0 * 0.05)


# ---------------------------------------------------------------------------
# IS-1 fix: novos produtos calculam corretamente
# ---------------------------------------------------------------------------

def test_apostas_jogos_calculo(cenario_apostas):
    r = calcular_impacto_is(cenario_apostas)
    assert r.is_por_unidade > 0
    assert r.preco_com_is > cenario_apostas.preco_venda_atual


def test_combustiveis_calculo(cenario_combustivel):
    r = calcular_impacto_is(cenario_combustivel)
    assert r.is_por_unidade > 0


# ---------------------------------------------------------------------------
# IS-2 fix: ressalva sobre início em 2027
# ---------------------------------------------------------------------------

def test_ressalva_vigencia_2027(cenario_tabaco):
    """Ressalva deve mencionar que IS inicia em 2027, não 2026."""
    r = calcular_impacto_is(cenario_tabaco)
    textos = " ".join(r.ressalvas).lower()
    assert "2027" in textos, (
        "Ressalva sobre vigência do IS a partir de 2027 obrigatória "
        "(não confundir com a entrada dos CBS/IBS em 2026)"
    )


# ---------------------------------------------------------------------------
# IS-3 fix: ressalva sobre IS monofásico sem crédito
# ---------------------------------------------------------------------------

def test_ressalva_sem_credito_downstream(cenario_tabaco):
    """IS não gera crédito para compradores — ressalva obrigatória."""
    r = calcular_impacto_is(cenario_tabaco)
    textos = " ".join(r.ressalvas).lower()
    assert "crédito" in textos or "credito" in textos, (
        "Ressalva sobre IS não gerar crédito downstream deve estar presente"
    )


def test_ressalva_monofasico(cenario_tabaco):
    r = calcular_impacto_is(cenario_tabaco)
    textos = " ".join(r.ressalvas).lower()
    assert "monofásico" in textos or "monofa" in textos


# ---------------------------------------------------------------------------
# IS-4 fix: ressalva IBS/CBS incide sobre preço + IS
# ---------------------------------------------------------------------------

def test_ressalva_ibs_cbs_sobre_preco_com_is(cenario_tabaco):
    """IBS+CBS incidem sobre preço + IS — ressalva obrigatória para carga total real."""
    r = calcular_impacto_is(cenario_tabaco)
    textos = " ".join(r.ressalvas)
    assert "IBS" in textos or "CBS" in textos, (
        "Ressalva que IBS/CBS incidem sobre preço+IS deve estar presente"
    )


# ---------------------------------------------------------------------------
# Campos estruturais do resultado
# ---------------------------------------------------------------------------

def test_resultado_status_estimada(cenario_tabaco):
    r = calcular_impacto_is(cenario_tabaco)
    assert r.status_aliquota == "estimada"


def test_resultado_repassar_consumidor(cenario_veiculo):
    r = calcular_impacto_is(cenario_veiculo)
    assert "preco_final" in r.repassar_consumidor
    assert r.repassar_consumidor["margem_mantida"] is True


def test_resultado_absorver_margem(cenario_veiculo):
    r = calcular_impacto_is(cenario_veiculo)
    assert "nova_margem" in r.absorver_margem
    assert r.absorver_margem["nova_margem"] < r.margem_atual


def test_produto_nao_cadastrado_usa_aliquota_padrao():
    cenario = CenarioIS(
        produto="produto_nao_cadastrado",
        preco_venda_atual=100.0,
        volume_mensal=10,
        custo_producao=50.0,
        elasticidade="media",
    )
    r = calcular_impacto_is(cenario)
    assert r.aliquota_usada == pytest.approx(0.10)  # fallback
