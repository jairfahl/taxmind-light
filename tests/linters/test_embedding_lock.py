"""
Linter: Embedding Model Lock
Verifica que EMBEDDING_MODEL tem default 'voyage-3' em todos os arquivos src/.

Lesson: troca acidental do modelo de embedding produziria vetores incompatíveis
com os 1596 embeddings já indexados (dim 1024, modelo voyage-3).
"""
import ast
from pathlib import Path

import pytest

from tests.linters.conftest import PROJECT_ROOT, SRC_DIR, get_python_files, parse_ast

EXPECTED_DEFAULT = "voyage-3"

# Arquivos conhecidos que definem EMBEDDING_MODEL com default
EXPECTED_FILES = {
    "src/rag/retriever.py",
    "src/ingest/embedder.py",
    "src/protocol/carimbo.py",
}


def _get_embedding_model_defaults(filepath: Path) -> list[str]:
    """
    Extrai os valores default de os.getenv("EMBEDDING_MODEL", <default>)
    em um arquivo Python.
    """
    defaults = []
    try:
        tree = parse_ast(filepath)
    except SyntaxError:
        return defaults

    for node in ast.walk(tree):
        # Procura: os.getenv("EMBEDDING_MODEL", "...")
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_os_getenv = (
            isinstance(func, ast.Attribute)
            and func.attr == "getenv"
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
        )
        if not is_os_getenv:
            continue
        if len(node.args) < 1:
            continue
        first_arg = node.args[0]
        if not (isinstance(first_arg, ast.Constant) and first_arg.value == "EMBEDDING_MODEL"):
            continue
        # Tem o argumento "EMBEDDING_MODEL" — pega o default (2o arg)
        if len(node.args) >= 2:
            second_arg = node.args[1]
            if isinstance(second_arg, ast.Constant):
                defaults.append(second_arg.value)
        elif node.keywords:
            for kw in node.keywords:
                if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                    defaults.append(kw.value.value)

    return defaults


def test_embedding_model_default_is_voyage3_in_all_files():
    """
    Todos os arquivos em src/ que definem EMBEDDING_MODEL via os.getenv()
    devem usar 'voyage-3' como default.
    """
    violations = []
    for filepath in get_python_files(SRC_DIR):
        defaults = _get_embedding_model_defaults(filepath)
        for default in defaults:
            if default != EXPECTED_DEFAULT:
                rel_path = filepath.relative_to(PROJECT_ROOT)
                violations.append(f"{rel_path}: EMBEDDING_MODEL default='{default}' (esperado: '{EXPECTED_DEFAULT}')")

    assert not violations, (
        "Troca de modelo de embedding detectada! Os 1596 vetores indexados usam voyage-3.\n"
        + "\n".join(violations)
    )


def test_expected_files_define_embedding_model():
    """
    Os 3 arquivos conhecidos ainda definem EMBEDDING_MODEL via os.getenv().
    Falha se algum foi removido/refatorado sem atualizar este teste.
    """
    missing = []
    for rel_path in EXPECTED_FILES:
        filepath = PROJECT_ROOT / rel_path
        if not filepath.exists():
            missing.append(f"{rel_path}: arquivo não encontrado")
            continue
        defaults = _get_embedding_model_defaults(filepath)
        if not defaults:
            missing.append(f"{rel_path}: EMBEDDING_MODEL não definido via os.getenv()")

    assert not missing, (
        "Arquivos esperados não definem mais EMBEDDING_MODEL:\n"
        + "\n".join(missing)
    )
