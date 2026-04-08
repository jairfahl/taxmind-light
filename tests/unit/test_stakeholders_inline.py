"""
tests/unit/test_stakeholders_inline.py — Testes unitários para Saídas por Stakeholder (C3, G16).
"""

from unittest.mock import MagicMock, patch

from src.outputs.stakeholders_inline import (
    STAKEHOLDERS,
    STAKEHOLDERS_PADRAO,
    ResumoStakeholder,
    SaidasPorStakeholder,
    _gerar_prompt_stakeholder,
    gerar_resumos_stakeholders,
    resumos_para_dict,
)


def test_cinco_stakeholders_definidos():
    assert len(STAKEHOLDERS) == 5
    assert set(STAKEHOLDERS.keys()) == {"cfo", "juridico", "compras", "ti", "tributario"}


def test_stakeholders_padrao_tres():
    assert len(STAKEHOLDERS_PADRAO) == 3
    assert set(STAKEHOLDERS_PADRAO) == {"cfo", "juridico", "tributario"}


def test_prompt_contem_label_e_instrucao():
    prompt = _gerar_prompt_stakeholder("cfo", "análise tributária teste")
    assert "CFO / Direção" in prompt
    assert "impacto em margem operacional" in prompt
    assert "análise tributária teste" in prompt


def test_prompt_trunca_analise_longa():
    # Usar caractere não presente em nenhum texto do template
    analise_longa = "Z" * 5000
    prompt = _gerar_prompt_stakeholder("tributario", analise_longa)
    # analise_original[:3000] → exatamente 3000 "Z"s no prompt
    assert prompt.count("Z") == 3000


def test_gerar_resumos_todos_stakeholders_ativos():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="• Bullet 1\n• Bullet 2")]
    mock_client.messages.create.return_value = mock_response

    resultado = gerar_resumos_stakeholders(
        analise_original="análise de teste",
        client=mock_client,
        model="claude-haiku-4-5-20251001",
        stakeholders_ativos=["cfo", "juridico"],
    )

    assert isinstance(resultado, SaidasPorStakeholder)
    assert len(resultado.resumos) == 2
    assert all(r.gerado_com_sucesso for r in resultado.resumos)
    assert resultado.resumos[0].resumo == "• Bullet 1\n• Bullet 2"


def test_falha_individual_nao_interrompe_outros():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="• OK")]

    def side_effect(*args, **kwargs):
        # Falha na segunda chamada
        if mock_client.messages.create.call_count == 2:
            raise RuntimeError("Erro simulado")
        return mock_response

    mock_client.messages.create.side_effect = side_effect

    resultado = gerar_resumos_stakeholders(
        analise_original="análise",
        client=mock_client,
        model="claude-haiku-4-5-20251001",
        stakeholders_ativos=["cfo", "juridico", "tributario"],
    )

    assert len(resultado.resumos) == 3
    falhos = [r for r in resultado.resumos if not r.gerado_com_sucesso]
    assert len(falhos) == 1
    assert "Erro simulado" in falhos[0].erro


def test_resumos_para_dict_serializa_corretamente():
    saidas = SaidasPorStakeholder(
        resumos=[
            ResumoStakeholder(
                stakeholder_id="cfo",
                label="CFO / Direção",
                emoji="💼",
                foco="impacto financeiro",
                resumo="• Impacto de R$ 100k",
            )
        ],
        analise_base="base",
    )
    resultado = resumos_para_dict(saidas)
    assert isinstance(resultado, list)
    assert resultado[0]["stakeholder_id"] == "cfo"
    assert resultado[0]["emoji"] == "💼"
    assert resultado[0]["gerado_com_sucesso"] is True


def test_stakeholder_invalido_ignorado():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="• OK")]
    mock_client.messages.create.return_value = mock_response

    resultado = gerar_resumos_stakeholders(
        analise_original="análise",
        client=mock_client,
        model="claude-haiku-4-5-20251001",
        stakeholders_ativos=["cfo", "inexistente"],
    )

    assert len(resultado.resumos) == 1
    assert resultado.resumos[0].stakeholder_id == "cfo"
