"""
tests/unit/test_grau_consolidacao.py — Testes unitários do componente Grau de Consolidação (G10).

Verifica configuração dos 4 graus DC v7, mapeamento de aliases e campos obrigatórios.
Nenhuma chamada ao Streamlit — testa apenas a camada de dados do componente.
"""

from ui.components.grau_consolidacao import (
    GRAU_CONFIG,
    GRAU_DESCONHECIDO,
    _normalizar_grau,
)


def test_quatro_graus_definidos():
    assert len(GRAU_CONFIG) == 4


def test_graus_corretos():
    assert "Consolidada" in GRAU_CONFIG
    assert "Majoritária" in GRAU_CONFIG
    assert "Divergente" in GRAU_CONFIG
    assert "Emergente" in GRAU_CONFIG


def test_cada_grau_tem_campos():
    for grau, config in GRAU_CONFIG.items():
        assert "emoji" in config, f"{grau} sem emoji"
        assert "risco_label" in config, f"{grau} sem risco_label"
        assert "descricao" in config, f"{grau} sem descricao"


def test_grau_desconhecido_tem_campos():
    assert "emoji" in GRAU_DESCONHECIDO
    assert "risco_label" in GRAU_DESCONHECIDO
    assert "descricao" in GRAU_DESCONHECIDO


def test_emojis_distintos():
    emojis = [c["emoji"] for c in GRAU_CONFIG.values()]
    assert len(emojis) == len(set(emojis)), "Emojis duplicados entre graus"


def test_consolidada_risco_minimo():
    assert "mínimo" in GRAU_CONFIG["Consolidada"]["risco_label"].lower()


def test_emergente_risco_alto():
    assert "alto" in GRAU_CONFIG["Emergente"]["risco_label"].lower()


# ---------------------------------------------------------------------------
# Aliases do engine → graus DC v7
# ---------------------------------------------------------------------------

def test_alias_consolidado():
    assert _normalizar_grau("consolidado") == "Consolidada"


def test_alias_em_disputa():
    assert _normalizar_grau("em_disputa") == "Divergente"


def test_alias_sem_precedente():
    assert _normalizar_grau("sem_precedente") == "Emergente"


def test_alias_indefinido():
    assert _normalizar_grau("indefinido") == "Emergente"


def test_alias_case_insensitive():
    assert _normalizar_grau("CONSOLIDADO") == "Consolidada"


def test_alias_grau_canonico_preservado():
    assert _normalizar_grau("Divergente") == "Divergente"


def test_alias_vazio_retorna_vazio():
    assert _normalizar_grau("") == ""
