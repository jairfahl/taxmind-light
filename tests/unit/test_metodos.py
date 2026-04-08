"""
tests/unit/test_metodos.py — Testes unitários da biblioteca de métodos de análise.
"""

import pytest
from src.cognitive.metodos import (
    METODOS_ANALISE,
    MAX_METODOS,
    SUGESTAO_POR_CRITICIDADE,
    formatar_metodos_para_prompt,
    sugerir_metodos,
)


class TestMetodosBasicos:
    def test_dez_metodos_definidos(self):
        assert len(METODOS_ANALISE) == 10

    def test_max_metodos_e_quatro(self):
        assert MAX_METODOS == 4

    def test_cada_metodo_tem_campos_obrigatorios(self):
        campos = {"nome", "descricao", "quando_usar"}
        for mid, m in METODOS_ANALISE.items():
            assert campos.issubset(m.keys()), f"Método {mid!r} faltando campo"
            assert m["nome"], f"Método {mid!r} com nome vazio"
            assert m["descricao"], f"Método {mid!r} com descricao vazia"
            assert m["quando_usar"], f"Método {mid!r} com quando_usar vazio"


class TestSugestao:
    def test_sugestao_criticidade_extrema(self):
        sugestao = sugerir_metodos("extrema")
        assert len(sugestao) > 0
        for mid in sugestao:
            assert mid in METODOS_ANALISE

    def test_sugestao_criticidade_baixa(self):
        sugestao = sugerir_metodos("baixa")
        assert len(sugestao) > 0

    def test_sugestao_criticidade_invalida_retorna_media(self):
        sugestao = sugerir_metodos("nao_existe")
        assert sugestao == SUGESTAO_POR_CRITICIDADE["media"]

    @pytest.mark.parametrize("criticidade", ["baixa", "media", "alta", "extrema"])
    def test_sugestao_nao_excede_max_metodos(self, criticidade):
        sugestao = sugerir_metodos(criticidade)
        assert len(sugestao) <= MAX_METODOS

    def test_todos_niveis_cobertos(self):
        for nivel in ["baixa", "media", "alta", "extrema"]:
            assert nivel in SUGESTAO_POR_CRITICIDADE


class TestFormatarParaPrompt:
    def test_lista_vazia_retorna_string_vazia(self):
        resultado = formatar_metodos_para_prompt([])
        assert resultado == ""

    def test_metodo_valido_gera_bloco(self):
        resultado = formatar_metodos_para_prompt(["cenarios"])
        assert "Análise de Cenários" in resultado
        assert "MÉTODOS DE ANÁLISE" in resultado

    def test_metodo_invalido_ignorado(self):
        resultado = formatar_metodos_para_prompt(["nao_existe"])
        assert resultado == "" or "nao_existe" not in resultado

    def test_multiplos_metodos(self):
        ids = ["cenarios", "matriz_risco", "arvore_decisao"]
        resultado = formatar_metodos_para_prompt(ids)
        assert "Análise de Cenários" in resultado
        assert "Matriz de Risco" in resultado
        assert "Árvore de Decisão" in resultado

    def test_instrucao_obrigatoria_presente(self):
        resultado = formatar_metodos_para_prompt(["benchmarking"])
        assert "obrigatoriamente" in resultado.lower()

    def test_none_equivale_a_lista_vazia(self):
        assert formatar_metodos_para_prompt(None) == ""  # type: ignore[arg-type]
