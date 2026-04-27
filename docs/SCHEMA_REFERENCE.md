# Schema do Banco — 31 Tabelas

**Banco:** PostgreSQL 16 + pgvector | **Container:** `tribus-ai-db`
**Última migration:** `129_api_usage_tenant.sql` → próxima: `130_...`

---

## Corpus

| Tabela | Descrição |
|--------|-----------|
| `normas` | Documentos fonte (EC, LC) + `file_hash` para dedup |
| `chunks` | Trechos das normas com metadados jurídicos |
| `embeddings` | Vetores voyage-3 (1024 dim) + índice HNSW |

## Consultas e IA

| Tabela | Descrição |
|--------|-----------|
| `consultas` | Log de buscas |
| `avaliacoes` | Validação manual de qualidade |
| `ai_interactions` | Log de chamadas ao LLM + `user_id` + criticidade + tokens (**sem tenant_id**) |
| `ai_metrics_daily` | Métricas agregadas por dia |
| `api_usage` | Consumo de API: service, model, tokens, estimated_cost, `tenant_id` NULL-able (m129) |

## Protocolo P1→P6

| Tabela | Descrição |
|--------|-----------|
| `cases` | Casos protocolares, 6 passos — **id é UUID** (m126); `tenant_id` UUID FK tenants (m128) |
| `case_steps` | Dados de cada passo por caso |
| `case_state_history` | Audit trail de transições |
| `carimbo_alerts` | Alertas de terceirização cognitiva |

## Outputs e Documentos

| Tabela | Descrição |
|--------|-----------|
| `outputs` | Documentos acionáveis (5 classes) + `legal_hold` — **id é UUID** (migration 126) |
| `output_aprovacoes` | Histórico de aprovações |
| `output_stakeholders` | Visões por público-alvo |
| `legal_hold_log` | Audit trail de ativações/desativações de Legal Hold |

## RAG e Integridade

| Tabela | Descrição |
|--------|-----------|
| `prompt_lockfiles` | Lockfiles de integridade de prompts (RDM-029) |
| `prompt_baselines` | Baselines para comparação |

## Observability

| Tabela | Descrição |
|--------|-----------|
| `drift_alerts` | Alertas de drift semântico |
| `regression_results` | Resultados de testes de regressão |

## Monitor de Fontes

| Tabela | Descrição |
|--------|-----------|
| `monitor_fontes` | Fontes DOU/PGFN monitoradas |
| `monitor_documentos` | Documentos detectados pelo monitor |

## Simulações

| Tabela | Descrição |
|--------|-----------|
| `simulacoes_carga` | Simulações de carga tributária |

## Ciclo Pós-Decisão e Aprendizado

| Tabela | Descrição |
|--------|-----------|
| `monitoramento_p6` | Monitoramento ativo de decisões tomadas |
| `heuristicas` | Heurísticas extraídas de casos (6 meses validade) |
| `metricas_aprendizado` | Métricas mensais por usuário |

## Proatividade e Padrões

| Tabela | Descrição |
|--------|-----------|
| `padroes_uso` | Frequência de temas por usuário (G25) |
| `sugestoes_silenciadas` | Silenciamentos de sugestões proativas |

## Auth e Billing

| Tabela | Descrição |
|--------|-----------|
| `tenants` | Tenants com plano, trial, status pagamento, `desconto_percentual` (m124), churn tracking (m127); referenciado em `cases.tenant_id` (m128) e `api_usage.tenant_id` (m129) |
| `users` | Usuários + onboarding + lgpd_consent + email_verificado + reset_token (m125) + tipo_atuacao VARCHAR(100) (m122) |
| `mau_records` | Monthly Active Users por tenant/mês (DEC-08) |

---

## Notas de Schema

- `cases.id` e `outputs.id` são **UUID** desde migration 126 (não integer)
- `ai_interactions` usa `user_id` (não `tenant_id`) — join via `users` para filtrar por tenant
- `tipo_atuacao` é VARCHAR(100) desde migration 122 (era VARCHAR(20) — bug silencioso corrigido)
- `cases.tenant_id` adicionado em m128 (NULL-able, FK tenants) — enforcement de limites por plano
- `api_usage.tenant_id` adicionado em m129 (NULL-able UUID) — chamadas de ingestão/regression podem ser NULL; índices em (tenant_id) e (tenant_id, created_at)
