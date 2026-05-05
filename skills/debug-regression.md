# Skill: Debug de Regressão

## Regra Absoluta

**Nunca** usar `@pytest.mark.skip` ou `@pytest.mark.xfail` para "resolver" uma regressão.
Corrigir a causa antes de entregar.

## Protocolo (5 passos)

### 1. Identificar os testes quebrados
```bash
.venv/bin/python -m pytest tests/ --tb=no -q 2>/dev/null | grep FAILED
```

### 2. Localizar o commit culpado
```bash
git log --oneline -15
# Se necessário, bisect:
git bisect start
git bisect bad HEAD
git bisect good <commit-hash-anterior-ao-problema>
```

### 3. Isolar e inspecionar
```bash
# Rodar só o teste quebrado com traceback completo
.venv/bin/python -m pytest tests/unit/test_[modulo].py::TestClasse::test_caso -v --tb=long

# Ver o erro completo
.venv/bin/python -m pytest tests/unit/test_[modulo].py -v --tb=long -s
```

### 4. Causas mais comuns

| Sintoma | Causa provável | Verificar |
|---------|---------------|-----------|
| `TypeError: got unexpected keyword argument` | Assinatura de função mudou | Diff do arquivo fonte + fixture conftest.py |
| `ValidationError` no Pydantic | Campo novo obrigatório no schema | Modelo Pydantic + fixture `mock_analise_result` |
| `AttributeError: Mock has no attribute X` | Fixture desatualizada com novo atributo | `tests/unit/conftest.py` |
| `ImportError` | Módulo movido ou renomeado | Arquivo de origem + `__init__.py` |
| Teste de linter falha | Novo padrão adicionado sem atualizar AST | `tests/linters/` + arquivo alvo |
| `IntegrityError` banco | Migration não aplicada ou FK faltando | `\d <tabela>` no container |

### 5. Checar conftest.py

Fixtures `autouse=True` mockam comportamentos específicos das classes fonte.
Se a classe fonte mudou interface → atualizar o mock correspondente:

```bash
# Ver fixtures disponíveis
grep -n "def mock_\|@pytest.fixture" tests/unit/conftest.py
```

## Se a Regressão Revela Invariante Nova

Seguir o ciclo em `docs/FEEDBACK_LOOP.md`:

```
Bug encontrado → root cause identificado → regra derivada →
é mecanicamente verificável? → sim → criar linter em tests/linters/
```

Linters existentes de referência:
- `tests/linters/test_embedding_lock.py` — AST + grep
- `tests/linters/test_p4_guard.py` — AST call graph
- `tests/linters/test_citation_contract.py` — AST + threshold
- `tests/linters/test_ptf_enforcement.py` — AST + SQL grep

## Validação Final

```bash
# Suite completa — zero regressões novas toleradas
.venv/bin/python -m pytest tests/ -v --tb=short

# Baseline de referência: ~10 falhas pré-existentes (ref 2026-04-30)
# Qualquer número acima de 10 = regressão nova = não entregar
```
