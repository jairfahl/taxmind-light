"""
Linter: Citation Contract
Verifica integridade do contrato de citação: AnaliseResult.fundamento_legal,
SYSTEM_PROMPT, funções M1-M4, e threshold precisao_citacao.

Lesson: Respostas sem fundamento_legal válido são alucinações jurídicas.
O threshold 0.90 de precisao_citacao é o mínimo para confiabilidade em decisões tributárias.
"""
import ast
import re
from pathlib import Path

import pytest

from tests.linters.conftest import SRC_DIR, PROJECT_ROOT, parse_ast

ENGINE_FILE = SRC_DIR / "cognitive" / "engine.py"
REGRESSION_FILE = SRC_DIR / "observability" / "regression.py"

REQUIRED_THRESHOLD_KEY = "precisao_citacao"
REQUIRED_THRESHOLD_MIN = 0.90


def test_analise_result_has_fundamento_legal():
    """AnaliseResult deve ter campo fundamento_legal."""
    if not ENGINE_FILE.exists():
        pytest.skip("engine.py não encontrado")

    tree = parse_ast(ENGINE_FILE)
    has_field = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AnaliseResult":
            for item in ast.walk(node):
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == "fundamento_legal":
                        has_field = True
                        break

    assert has_field, "AnaliseResult deve ter campo 'fundamento_legal'"


def test_system_prompt_mentions_fundamento_legal():
    """SYSTEM_PROMPT em engine.py deve mencionar 'fundamento_legal'."""
    if not ENGINE_FILE.exists():
        pytest.skip("engine.py não encontrado")

    content = ENGINE_FILE.read_text(encoding="utf-8")
    assert "fundamento_legal" in content, (
        "engine.py não menciona 'fundamento_legal' — contrato JSON de resposta incompleto"
    )


def test_m1_to_m4_functions_exist():
    """Funções _verificar_m1, _verificar_m2, _verificar_m3, _verificar_m4 devem existir."""
    if not ENGINE_FILE.exists():
        pytest.skip("engine.py não encontrado")

    tree = parse_ast(ENGINE_FILE)
    found_functions = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_verificar_m"):
            found_functions.add(node.name)

    # Aceita nomes completos (_verificar_m3_pertinencia, _verificar_m4_consistencia) ou curtos
    required_prefixes = {"_verificar_m1", "_verificar_m2", "_verificar_m3", "_verificar_m4"}
    missing = set()
    for prefix in required_prefixes:
        if not any(name == prefix or name.startswith(prefix + "_") for name in found_functions):
            missing.add(prefix)
    assert not missing, f"Funções anti-alucinação não encontradas (por prefixo): {missing}"


def test_precisao_citacao_threshold_is_at_least_90_percent():
    """THRESHOLDS_REGRESSAO['precisao_citacao'] deve ser >= 0.90."""
    if not REGRESSION_FILE.exists():
        pytest.skip("regression.py não encontrado")

    tree = parse_ast(REGRESSION_FILE)

    # Procura atribuição de THRESHOLDS_REGRESSAO como dict literal
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id == "THRESHOLDS_REGRESSAO":
                if isinstance(node.value, ast.Dict):
                    for key, val in zip(node.value.keys, node.value.values):
                        if isinstance(key, ast.Constant) and key.value == REQUIRED_THRESHOLD_KEY:
                            if isinstance(val, ast.Constant):
                                assert val.value >= REQUIRED_THRESHOLD_MIN, (
                                    f"precisao_citacao={val.value} < {REQUIRED_THRESHOLD_MIN} "
                                    "— threshold mínimo para confiabilidade jurídica"
                                )
                                return

    pytest.fail("THRESHOLDS_REGRESSAO['precisao_citacao'] não encontrado em regression.py")


def test_thresholds_regressao_exists():
    """THRESHOLDS_REGRESSAO deve existir em regression.py."""
    if not REGRESSION_FILE.exists():
        pytest.skip("regression.py não encontrado")

    content = REGRESSION_FILE.read_text(encoding="utf-8")
    assert "THRESHOLDS_REGRESSAO" in content, "THRESHOLDS_REGRESSAO não encontrado em regression.py"
