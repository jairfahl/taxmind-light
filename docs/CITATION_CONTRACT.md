# Contrato de Citação e Anti-Alucinação

## Contrato JSON de Resposta (AnaliseResult)

Todo output do engine deve seguir este schema:

```python
class AnaliseResult:
    resposta: str              # Texto da análise
    fundamento_legal: list     # OBRIGATÓRIO — lista de artigos citados
    confianca: float           # Score de confiança [0.0–1.0]
    contra_tese: str           # Argumentos contrários (quando aplicável)
    qualidade: str             # VERDE / AMARELO / VERMELHO
    quality_iterations: int    # Número de iterações do Loop Depth QG
    # ... demais campos
```

**Regra crítica:** `fundamento_legal` nunca pode ser lista vazia em respostas que citam normas.

---

## Checks Anti-Alucinação (M1–M4)

Definidos em `src/cognitive/engine.py`, executados pelo Quality Gate:

| Métrica | Função | Descrição |
|---------|--------|-----------|
| M1 | `_verificar_m1()` | Artigos citados existem na base (chunks reais) |
| M2 | `_verificar_m2()` | Artigos citados pertencem a normas vigentes na `data_referencia` |
| M3 | `_verificar_m3()` | Coerência entre texto da resposta e fundamento_legal |
| M4 | `_verificar_m4()` | Contra-tese presente quando query é INTERPRETATIVA ou COMPARATIVA |

---

## Thresholds de Regressão

Definidos em `src/observability/regression.py`:

```python
THRESHOLDS_REGRESSAO = {
    "precisao_citacao":      0.90,   # >= 90% das citações devem ser válidas
    "taxa_alucinacao":       0.05,   # <= 5% de respostas com alucinação
    "acuracia_recomendacao": 0.80,   # >= 80% das recomendações corretas
    "latencia_p95":          15.0,   # <= 15s no P95
    "cobertura_contra_tese": 0.80,   # >= 80% quando aplicável
}
```

Teste de linter: `tests/linters/test_citation_contract.py` verifica que estes thresholds existem e que `precisao_citacao >= 0.90`.

---

## SYSTEM_PROMPT

O SYSTEM_PROMPT em `engine.py` deve conter explicitamente:
- Campo `"fundamento_legal"` na spec JSON de resposta
- Instrução: "Referências legais APENAS no campo fundamento_legal"
- Proibição de inventar artigos não presentes nos chunks recuperados

---

## Lockfile de Integridade (RDM-029)

Módulo: `src/integrity/lockfile_manager.py`
Tabelas: `prompt_lockfiles`, `prompt_baselines`
Modo: `.env` `LOCKFILE_MODE=WARN` (nunca `ENFORCE` — valor inválido)

O lockfile detecta alterações não autorizadas no SYSTEM_PROMPT comparando hash SHA-256 com o baseline registrado.
