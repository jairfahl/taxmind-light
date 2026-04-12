"""
tests/unit/test_stakeholders.py — Testes unitários do StakeholderDecomposer.
Usa mocks para LLM e banco.
Executa com: pytest tests/unit/test_stakeholders.py -v
"""

import pytest
from unittest.mock import MagicMock, patch

from src.outputs.stakeholders import (
    CAMPOS_INTERNOS_PROIBIDOS_EXTERNO,
    PERFIS_STAKEHOLDER,
    StakeholderDecomposer,
    StakeholderTipo,
    StakeholderView,
    _filtrar_campos_externo,
)


# ---------------------------------------------------------------------------
# 1. Stakeholder EXTERNO: campos internos ausentes na view
# ---------------------------------------------------------------------------
def test_externo_campos_internos_removidos():
    """_filtrar_campos_externo deve remover scoring_confianca, chunks, etc."""
    conteudo = {
        "titulo": "Recomendação teste",
        "recomendacao_principal": "Adotar regime X",
        "scoring_confianca": "alto",         # proibido
        "anti_alucinacao": {"m1": True},     # proibido
        "versao_prompt": "v1.0.0",           # proibido
        "chunks_usados": 3,                  # proibido
        "fundamento_legal": ["Art. 12"],
        "disclaimer": "Disclaimer padrão",
    }
    filtrado = _filtrar_campos_externo(conteudo)
    for campo_proibido in CAMPOS_INTERNOS_PROIBIDOS_EXTERNO:
        assert campo_proibido not in filtrado, f"Campo {campo_proibido} não deveria estar presente para EXTERNO"
    # Campos permitidos devem estar presentes
    assert "titulo" in filtrado
    assert "recomendacao_principal" in filtrado
    assert "disclaimer" in filtrado


# ---------------------------------------------------------------------------
# 2. Stakeholder AUDITORIA: versao_prompt está nos campos_visiveis do perfil
# ---------------------------------------------------------------------------
def test_auditoria_versao_prompt_nos_campos():
    perfil = PERFIS_STAKEHOLDER[StakeholderTipo.AUDITORIA]
    assert "versao_prompt" in perfil["campos_visiveis"]
    assert "versao_base" in perfil["campos_visiveis"]
    assert "scoring_confianca" in perfil["campos_visiveis"]
    assert "anti_alucinacao" in perfil["campos_visiveis"]


# ---------------------------------------------------------------------------
# 3. Decomposição com lista vazia de stakeholders → lista vazia (não erro)
# ---------------------------------------------------------------------------
@patch("src.outputs.stakeholders.psycopg2.connect")
def test_decompor_lista_vazia(mock_connect):
    decomp = StakeholderDecomposer()
    result = decomp.decompor(output_id=1, stakeholders=[], conteudo={})
    assert result == []
    mock_connect.assert_not_called()  # não deve abrir conexão se vazio


# ---------------------------------------------------------------------------
# 4. View CFO contém materialidade e prazo_acao nos campos_visiveis
# ---------------------------------------------------------------------------
def test_cfo_campos_visiveis():
    perfil = PERFIS_STAKEHOLDER[StakeholderTipo.CFO]
    assert "materialidade" in perfil["campos_visiveis"]
    assert "prazo_acao" in perfil["campos_visiveis"]
    assert "risco_financeiro" in perfil["campos_visiveis"]


# ---------------------------------------------------------------------------
# 5. Todos os perfis têm foco, linguagem e campos_visiveis definidos
# ---------------------------------------------------------------------------
def test_todos_perfis_completos():
    for stk, perfil in PERFIS_STAKEHOLDER.items():
        assert "foco" in perfil, f"{stk}: foco ausente"
        assert "linguagem" in perfil, f"{stk}: linguagem ausente"
        assert "campos_visiveis" in perfil, f"{stk}: campos_visiveis ausente"
        assert len(perfil["campos_visiveis"]) >= 1, f"{stk}: campos_visiveis vazio"


# ---------------------------------------------------------------------------
# 6. Decomposição com mock LLM persiste no banco
# ---------------------------------------------------------------------------
@patch.object(StakeholderDecomposer, "_adaptar_conteudo", return_value="Resumo adaptado mock")
def test_decompor_persiste_banco(mock_adaptar):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = (99,)  # db_id

    decomp = StakeholderDecomposer()
    views = decomp.decompor(
        output_id=5,
        stakeholders=[StakeholderTipo.CFO, StakeholderTipo.JURIDICO],
        conteudo={"recomendacao_principal": "Adotar regime X"},
        conn=mock_conn,  # passa conn mockada diretamente, evita FK violation no banco real
    )
    assert len(views) == 2
    assert all(isinstance(v, StakeholderView) for v in views)
    assert views[0].stakeholder == StakeholderTipo.CFO
    assert views[1].stakeholder == StakeholderTipo.JURIDICO
    assert views[0].resumo == "Resumo adaptado mock"


# ---------------------------------------------------------------------------
# 7. EXTERNO não deve ter campos internos nos campos_visiveis do perfil
# ---------------------------------------------------------------------------
def test_externo_campos_visiveis_sem_internos():
    perfil = PERFIS_STAKEHOLDER[StakeholderTipo.EXTERNO]
    for campo in perfil["campos_visiveis"]:
        assert campo not in CAMPOS_INTERNOS_PROIBIDOS_EXTERNO, \
            f"Campo interno {campo} não deveria estar em campos_visiveis do EXTERNO"
