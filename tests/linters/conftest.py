"""
Helpers compartilhados para os testes de linter.
"""
import ast
import os
from pathlib import Path

# Raiz do projeto (2 níveis acima de tests/linters/)
PROJECT_ROOT = Path(__file__).parent.parent.parent

SRC_DIR = PROJECT_ROOT / "src"
TESTS_DIR = PROJECT_ROOT / "tests"


def get_python_files(directory: Path, exclude_pycache: bool = True) -> list[Path]:
    """Retorna todos os arquivos .py em um diretório recursivamente."""
    files = []
    for path in directory.rglob("*.py"):
        if exclude_pycache and "__pycache__" in str(path):
            continue
        files.append(path)
    return files


def parse_ast(filepath: Path) -> ast.Module:
    """Faz parse AST de um arquivo Python."""
    source = filepath.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(filepath))


def find_assignments(tree: ast.Module, target_name: str) -> list[ast.Assign]:
    """Encontra todos os assignments de um nome de variável."""
    assignments = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target_name:
                    assignments.append(node)
                elif isinstance(tgt, ast.Attribute) and tgt.attr == target_name:
                    assignments.append(node)
    return assignments


def find_calls(tree: ast.Module, func_names: set[str]) -> list[ast.Call]:
    """Encontra chamadas de função pelo nome."""
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in func_names:
                calls.append(node)
            elif isinstance(node.func, ast.Attribute) and node.func.attr in func_names:
                calls.append(node)
    return calls
