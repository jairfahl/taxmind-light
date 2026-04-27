# Quality Scorecard — Orbis.tax

## Dimensões e Thresholds

| Dimensão | Métrica | Threshold | Onde Medir | Automatizado? |
|----------|---------|-----------|-----------|---------------|
| Citação | precisao_citacao | >= 0.90 | `regression.py` | ✅ linter |
| Alucinação | taxa_alucinacao | <= 0.05 | `regression.py` | ✅ pytest |
| Recomendação | acuracia_recomendacao | >= 0.80 | `regression.py` | ✅ pytest |
| Latência | latencia_p95 | <= 15.0s | `regression.py` | ✅ pytest |
| Contra-tese | cobertura_contra_tese | >= 0.80 | `regression.py` | ✅ pytest |
| Linter Python | ruff violations | 0 | `pyproject.toml` | ✅ CI / pre-deploy |
| Embedding Lock | default model | "voyage-3" | `test_embedding_lock.py` | ✅ linter |
| P4 Guard | hipotese_gestor fonte | humana | `test_p4_guard.py` | ✅ linter |
| PTF | data_referencia | presente | `test_ptf_enforcement.py` | ✅ linter |
| Testes | suite passando | 667+ | pytest | ✅ CI / pre-deploy |
| Lockfile | hash prompt | match baseline | `lockfile_manager.py` | ✅ runtime |

---

## Como Gerar o Scorecard

```bash
bash scripts/quality_scorecard.sh
```

Saída: tabela markdown com status de cada dimensão (PASS/FAIL/WARN).

---

## Módulos de Qualidade

| Módulo | Arquivo | Responsabilidade |
|--------|---------|-----------------|
| Quality Gate | `src/quality/engine.py` | Avalia M1-M4 em tempo real |
| Regression Suite | `src/observability/regression.py` | Testes batch de qualidade |
| Drift Detector | `src/observability/` | Detecção de drift semântico |
| Lockfile | `src/integrity/lockfile_manager.py` | Integridade de prompts |

---

## Métricas no Banco

| Tabela | Conteúdo |
|--------|---------|
| `ai_metrics_daily` | Métricas agregadas por dia |
| `regression_results` | Resultados de testes de regressão |
| `drift_alerts` | Alertas de drift semântico |
| `prompt_lockfiles` | Lockfiles de integridade |
| `avaliacoes` | Validação manual de qualidade |

---

## Feedback Loop

Quando uma métrica falha → seguir processo em `docs/FEEDBACK_LOOP.md`.
