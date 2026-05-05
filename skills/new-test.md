# Skill: Novo Teste Unitário

## Regra Permanente

Testes unitários **nunca** fazem chamadas externas (LLM, embeddings, banco real).
Todos os mocks vêm de `tests/unit/conftest.py` via `autouse=True` — não reinventar.

## Categorias de Teste

| Categoria | Local | Quando rodar |
|-----------|-------|--------------|
| Unit | `tests/unit/` | Sempre (CI + local) |
| Integration | `tests/integration/` | Com DB container ativo |
| Linters AST | `tests/linters/` | Sempre (CI + local) |
| Adversarial | `tests/unit/test_prompt_sanitizer.py` | Sempre |
| E2E | `tests/e2e/` | **Manualmente apenas** |

## Template: `tests/unit/test_[modulo].py`

```python
"""
tests/unit/test_[modulo].py — Testes unitários para src/[caminho]/[modulo].py
REGRA: zero chamadas externas. Todos os mocks aplicados via conftest.py autouse.
"""
import pytest
from src.[caminho].[modulo] import MinhaClasse, minha_funcao


class TestMinhaFuncao:
    def test_caso_base(self):
        resultado = minha_funcao("input válido")
        assert resultado is not None

    def test_caso_invalido(self):
        with pytest.raises(ValueError):
            minha_funcao("")
```

## Fixtures Disponíveis no conftest.py (autouse=True)

| Fixture | O que mocka |
|---------|-------------|
| `mock_llm_calls` | `CognitiveEngine.analisar()` e `_chamar_llm()` |
| `mock_embedding_calls` | `get_embedding()` e `embed_texts()` |
| `mock_materialidade` | `MaterialidadeCalculator.calcular()` |
| `mock_stakeholder_adaptar` | `adaptar_para_stakeholder()` |
| `mock_usage_tracking` | `registrar_uso()` |
| `mock_spd_normas` | `buscar_normas_spd()` |
| `mock_analise_result` | Retorna `AnaliseResult` preenchido |

## Checklist Obrigatório

- [ ] Nenhum `psycopg2.connect()` direto no teste
- [ ] Nenhum `httpx.get/post` ou `requests.get/post`
- [ ] Nenhum `os.getenv("ANTHROPIC_API_KEY")` ou `os.getenv("VOYAGE_API_KEY")`
- [ ] Nenhum `from anthropic import Anthropic` no teste
- [ ] Se precisar de nova dependência externa → adicionar fixture autouse ao conftest.py
- [ ] Mensagens de assert em português descritivo

## Novo Mock Necessário?

Se o módulo testado chama uma dependência externa não coberta pelas fixtures acima:

```python
# Em tests/unit/conftest.py, adicionar:
@pytest.fixture(autouse=True)
def mock_nova_dependencia():
    with patch("src.modulo.nova_dependencia") as mock:
        mock.return_value = <valor_esperado>
        yield mock
```

## Rodar

```bash
# Só o arquivo novo
.venv/bin/python -m pytest tests/unit/test_[modulo].py -v --tb=short

# Suite completa
.venv/bin/python -m pytest tests/ -v --tb=short
```
