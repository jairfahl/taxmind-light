"""
Linter: P4 Guard Rail
Verifica que hipotese_gestor e decisao_final nunca são populados por output de LLM.

Lesson: P4/P5 são passos 100% humanos. Qualquer automação destes campos viola
o protocolo de decisão e compromete a auditabilidade P1→P6.
"""
import ast
from pathlib import Path

import pytest

from tests.linters.conftest import SRC_DIR, PROJECT_ROOT, get_python_files, parse_ast

# Nomes de funções que produzem output de LLM
LLM_CALL_NAMES = {"analisar", "_chamar_llm", "completions", "messages"}

# Campos que NUNCA devem ser atribuídos via LLM
PROTECTED_FIELDS = {"hipotese_gestor", "decisao_final"}


def _is_llm_call(node: ast.expr) -> bool:
    """Verifica se uma expressão é uma chamada ao LLM."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    # Chamada direta: analisar(...), _chamar_llm(...)
    if isinstance(func, ast.Name) and func.id in LLM_CALL_NAMES:
        return True
    # Método: obj.analisar(...), engine.analisar(...), client.messages(...)
    if isinstance(func, ast.Attribute) and func.attr in LLM_CALL_NAMES:
        return True
    # anthropic.Anthropic().messages.create(...)
    if isinstance(func, ast.Attribute):
        val = func.value
        if isinstance(val, ast.Name) and val.id == "anthropic":
            return True
        if isinstance(val, ast.Attribute) and val.attr in {"messages", "completions"}:
            return True
    return False


def _contains_llm_call(node: ast.expr) -> bool:
    """Verifica recursivamente se uma expressão contém chamada ao LLM."""
    for child in ast.walk(node):
        if _is_llm_call(child):
            return True
    return False


def test_hipotese_gestor_not_assigned_from_llm():
    """hipotese_gestor nunca deve receber valor de chamada ao LLM."""
    violations = []
    for filepath in get_python_files(SRC_DIR):
        try:
            tree = parse_ast(filepath)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                continue

            # Verifica se o target é hipotese_gestor
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and node.value:
                targets = [node.target]
                value = node.value
            else:
                continue

            target_names = set()
            for tgt in targets:
                if isinstance(tgt, ast.Name):
                    target_names.add(tgt.id)
                elif isinstance(tgt, ast.Attribute):
                    target_names.add(tgt.attr)
                elif isinstance(tgt, ast.Subscript):
                    if isinstance(tgt.slice, ast.Constant):
                        target_names.add(tgt.slice.value)

            for field in PROTECTED_FIELDS:
                if field in target_names and _contains_llm_call(value):
                    rel_path = filepath.relative_to(PROJECT_ROOT)
                    violations.append(
                        f"{rel_path}:{node.lineno}: '{field}' atribuído via chamada ao LLM"
                    )

    assert not violations, (
        "P4/P5 Guard Rail violado! hipotese_gestor/decisao_final devem ser preenchidos pelo gestor:\n"
        + "\n".join(violations)
    )


def test_protected_fields_not_in_analise_result():
    """
    AnaliseResult não deve ter campos hipotese_gestor ou decisao_final.
    Estes campos pertencem a case_steps (preenchidos pelo humano).
    """
    engine_file = SRC_DIR / "cognitive" / "engine.py"
    if not engine_file.exists():
        pytest.skip("engine.py não encontrado")

    tree = parse_ast(engine_file)
    analise_result_fields = set()

    for node in ast.walk(tree):
        # Procura class AnaliseResult ou dataclass AnaliseResult
        if isinstance(node, ast.ClassDef) and node.name == "AnaliseResult":
            for item in ast.walk(node):
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    analise_result_fields.add(item.target.id)

    violations = PROTECTED_FIELDS & analise_result_fields
    assert not violations, (
        f"AnaliseResult não deve ter campos de decisão humana: {violations}"
    )
