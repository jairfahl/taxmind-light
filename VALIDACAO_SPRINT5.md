# VALIDACAO_SPRINT5.md — Observability de IA

**Data:** 2026-03-10
**Sprint:** 5 — Observability: Métricas, Drift Detection, Regression Testing
**Critério de aceite:** MetricsCollector + DriftDetector + RegressionRunner implementados; testes unitários e integração passando

---

## Componentes Implementados

### src/observability/collector.py — MetricsCollector

| Funcionalidade | Status |
|---|---|
| `registrar_interacao()` — não-bloqueante, exceções logadas | ✅ |
| `agregar_diario()` — upsert em `ai_metrics_daily`, calcula p95 | ✅ |
| `calcular_taxa_alucinacao()` — proxy via `bloqueado=TRUE` | ✅ |
| `_percentil()` — interpolação linear | ✅ |
| Integrado em `CognitiveEngine.analisar()` (try/except) | ✅ |

### src/observability/drift.py — DriftDetector

| Funcionalidade | Status |
|---|---|
| `verificar_drift()` — janela 7 dias, threshold 2σ (strict >) | ✅ |
| `registrar_baseline()` — requer ≥ 3 dias, persiste em `prompt_baselines` | ✅ |
| `resolver_alert()` — UPDATE `resolvido=TRUE, resolvido_em=NOW()` | ✅ |
| `_stddev()` — desvio padrão amostral | ✅ |
| 8 métricas monitoradas (METRICAS_MONITORADAS) | ✅ |
| sigma=0 → ignorar (sem contexto estatístico) | ✅ (fix) |

### src/observability/regression.py — RegressionRunner

| Funcionalidade | Status |
|---|---|
| 5 casos no DATASET_AVALIACAO | ✅ |
| 5 thresholds: precisão_citação ≥90%, alucinação ≤5%, grounding ≥80%, p95 ≤15s, contra_tese ≥80% | ✅ |
| `executar()` — chama CognitiveEngine real, persiste em `regression_results` | ✅ |
| Penalidade de 30s para casos com exceção | ✅ |

---

## Endpoints FastAPI (5)

| Endpoint | Método | Status |
|---|---|---|
| `/v1/observability/metrics` | GET | ✅ 200 |
| `/v1/observability/drift` | GET | ✅ 200 |
| `/v1/observability/drift/{id}/resolver` | POST | ✅ 200/404 |
| `/v1/observability/baseline` | POST | ✅ 201/400 |
| `/v1/observability/regression` | POST | ✅ (requer LLM real) |

---

## Testes — Resultado Final

```
pytest tests/unit/ tests/integration/ -v
137 passed, 1 skipped, 0 failures
Tempo total: 1m53s
```

### Sprint 5 — Unitários (29 testes)

| Arquivo | Testes | Status |
|---|---|---|
| test_metrics_collector.py | 10 | ✅ PASS |
| test_drift_detector.py | 11 | ✅ PASS |
| test_regression_runner.py | 8 | ✅ PASS |

### Sprint 5 — Integração (8 testes)

| Arquivo | Testes | Status |
|---|---|---|
| test_observability_api.py | 8 | ✅ PASS |

### Suites Anteriores (mantidas)

| Módulo | Testes | Status |
|---|---|---|
| Sprint 1 (retriever) | 9 | ✅ PASS |
| Sprint 2 (cognitive, quality) | 13 | ✅ PASS |
| Sprint 3 (protocol, carimbo, API) | 28 | ✅ PASS |
| Sprint 4 (outputs, stakeholders, API) | 20 | ✅ PASS |

---

## Schema — Tabelas Sprint 5 (db/migration_sprint5.sql)

```sql
prompt_baselines    -- valores de referência por (prompt_version, model_id)
ai_metrics_daily    -- agrega ai_interactions diariamente por (data, pv, model_id)
drift_alerts        -- alertas de desvio > 2σ, com resolução
regression_results  -- histórico de testes de regressão
-- ALTER TABLE ai_interactions ADD COLUMN: contra_tese_gerada, grounding_presente, response_length
```

---

## Bug Corrigido

**Drift com sigma=0**: quando todos os valores da janela eram idênticos (sigma=0), qualquer desvio do baseline disparava `desvios=inf`, gerando falsos positivos. Correção: quando sigma=0, o detector agora ignora a métrica (`continue`) pois não há variabilidade histórica suficiente para computar z-score significativo.

---

## Critério de Aceite

| Critério | Resultado |
|---|---|
| MetricsCollector implementado e não-bloqueante | ✅ |
| DriftDetector com threshold 2σ (strict >) | ✅ |
| RegressionRunner com 5 casos e 5 thresholds | ✅ |
| 5 endpoints FastAPI de observability | ✅ |
| Aba 5 Streamlit com KPIs, gráficos, drift e regression | ✅ |
| ≥ 14 testes unitários Sprint 5 (obtido: 29) | ✅ |
| ≥ 3 testes integração Sprint 5 (obtido: 8) | ✅ |
| Suite completa verde (137 passed) | ✅ |
