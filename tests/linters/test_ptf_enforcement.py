"""
Linter: PTF Enforcement (Princípio Temporal Fiscal)
Verifica que retrieve() aceita data_referencia e que a SQL filtra por vigência.

Lesson: Respostas sem filtro temporal podem citar normas revogadas como vigentes,
causando parecer tributário com base em legislação desatualizada.
"""
import ast
from pathlib import Path

import pytest

from tests.linters.conftest import SRC_DIR, PROJECT_ROOT, parse_ast

RETRIEVER_FILE = SRC_DIR / "rag" / "retriever.py"


def test_retrieve_accepts_data_referencia():
    """
    A função retrieve() (ou buscar()) em retriever.py deve aceitar parâmetro data_referencia.
    """
    if not RETRIEVER_FILE.exists():
        pytest.skip("retriever.py não encontrado")

    tree = parse_ast(RETRIEVER_FILE)

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name not in ("retrieve", "buscar", "buscar_chunks"):
            continue
        # Verifica se data_referencia está nos argumentos
        arg_names = [arg.arg for arg in node.args.args]
        arg_names += [arg.arg for arg in node.args.kwonlyargs]
        if node.args.vararg:
            pass  # *args não tem nome fixo
        if "data_referencia" in arg_names:
            return  # Encontrado — teste passa

    pytest.fail(
        "Função retrieve()/buscar() em retriever.py não aceita 'data_referencia' — "
        "PTF desabilitado: sistema pode retornar normas revogadas"
    )


def test_retriever_sql_filters_vigencia():
    """
    O SQL em retriever.py deve conter filtros de vigencia_inicio e vigencia_fim.
    """
    if not RETRIEVER_FILE.exists():
        pytest.skip("retriever.py não encontrado")

    content = RETRIEVER_FILE.read_text(encoding="utf-8")

    assert "vigencia_inicio" in content, (
        "retriever.py não filtra por vigencia_inicio — PTF incompleto"
    )
    assert "vigencia_fim" in content, (
        "retriever.py não filtra por vigencia_fim — PTF incompleto"
    )


def test_ptf_module_exists():
    """src/rag/ptf.py deve existir com extrair_data_referencia."""
    ptf_file = SRC_DIR / "rag" / "ptf.py"
    if not ptf_file.exists():
        pytest.fail("src/rag/ptf.py não encontrado — PTF não implementado")

    content = ptf_file.read_text(encoding="utf-8")
    assert "extrair_data_referencia" in content, (
        "ptf.py não define extrair_data_referencia()"
    )
