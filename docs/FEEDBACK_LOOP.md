# Feedback Loop — Erro → Regra → Linter

## Processo

Quando um bug, regressão ou incidente ocorre:

```
1. Root cause documentado em LESSONS_LEARNED.md
2. "Regra derivada" extraída da lição
3. Verificar se é mecanicamente forçável:
   a. SIM → criar teste em tests/linters/ + adicionar ao scorecard
   b. NÃO → adicionar a AGENTS.md (se universal) ou docs/ relevante (se domínio)
```

## Critério: Mecanicamente Forçável?

Uma regra é mecanicamente forçável se pode ser verificada por:
- Scan AST (padrões de código proibidos)
- Grep de string (defaults hardcoded, padrões obrigatórios)
- Verificação de estrutura de arquivo (campos obrigatórios em dataclasses)
- Threshold numérico (≥ 0.90, ≤ 15s)

**Não é mecanicamente forçável:** regras de processo, decisões arquiteturais, julgamentos de qualidade.

## Linters Existentes

| Linter | Arquivo | Lesson Associada |
|--------|---------|-----------------|
| Embedding Lock | `test_embedding_lock.py` | Troca acidental de modelo = vetores incompatíveis |
| P4 Guard Rail | `test_p4_guard.py` | P4/P5 são 100% humanos — nunca automatizar |
| Citation Contract | `test_citation_contract.py` | fundamento_legal vazio = alucinação jurídica |
| PTF Enforcement | `test_ptf_enforcement.py` | Sem filtro temporal = normas revogadas como vigentes |

## Candidatos a Novos Linters (Sprint 4)

| Regra | Origem | Implementação |
|-------|--------|---------------|
| `style={{ color: "#` proibido em TSX | UI Upgrade | Grep em frontend/**/*.tsx |
| `useSearchParams` sem `<Suspense>` | Next.js build failure | AST ou grep padrão |
| `docker-compose.prod.yml` em tests | Segurança | Grep em tests/ |

## Template de Novo Linter

```python
"""
Linter: [Nome]
Verifica [invariante].

Lesson: [O que aconteceu quando a regra foi violada]
"""
import pytest
from tests.linters.conftest import PROJECT_ROOT, SRC_DIR

def test_[nome_descritivo]():
    """[O que verifica e por quê é importante]"""
    violations = []
    # ... scan
    assert not violations, f"[Mensagem de erro clara]:\n" + "\n".join(violations)
```

## Adicionando ao Scorecard

Após criar o linter, ele é automaticamente incluído pelo `quality_scorecard.sh`
(o script roda `pytest tests/linters/` inteiro).

Não é necessário editar `quality_scorecard.sh` para cada novo linter.
