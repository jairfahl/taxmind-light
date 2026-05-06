# Stress Testing — Orbis.tax (Gate U2)

Infraestrutura de testes de carga, resiliência e segurança para validação pré-launch.

## Pré-requisitos

```bash
pip install -r requirements-dev.txt  # inclui locust>=2.20
```

## Variáveis de Ambiente

| Variável | Descrição | Obrigatória para |
|----------|-----------|-----------------|
| `STRESS_BASE_URL` | URL do servidor alvo (default: `https://orbis.tax`) | Todos |
| `STRESS_TEST_EMAIL` | E-mail da conta de teste (PRO/Starter) | locustfile.py, security |
| `STRESS_TEST_PASSWORD` | Senha da conta de teste | locustfile.py, security |
| `STRESS_TEST_EMAIL_B` | E-mail do tenant B (para testes IDOR) | test_security_manual.py |
| `STRESS_TEST_PASSWORD_B` | Senha do tenant B | test_security_manual.py |
| `STRESS_TEST_TOKEN` | JWT pré-autenticado para stress_baseline.sh | scripts/stress_baseline.sh |

> **Use uma conta PRO/Starter** para load tests — conta trial bate no limite de 5 consultas.

---

## Fase 0 — Baseline (obrigatório antes de qualquer teste)

```bash
# Mede CPU, RAM, disco, latências e conexões PG em repouso
bash scripts/stress_baseline.sh
# Resultados em: results/baseline_YYYYMMDD_HHMMSS.txt
```

---

## Fase 1.2 — Load sem LLM (zero custo de API)

Testa apenas infra: pgvector HNSW, PostgreSQL, nginx, connection pool.

```bash
# 20 users, 10 minutos
locust -f tests/stress/locustfile_mock.py \
  --users 20 --spawn-rate 2 --run-time 10m \
  --headless --csv results/load_mock \
  -H https://orbis.tax

# Ver resultados
cat results/load_mock_stats.csv
```

---

## Fase 1.1 — Load com LLM (~$10-20 USD)

Simula tributarista real com queries fiscais e análise RAG completa.

```bash
STRESS_TEST_EMAIL=user@empresa.com STRESS_TEST_PASSWORD=senha \
locust -f tests/stress/locustfile.py \
  --users 10 --spawn-rate 1 --run-time 25m \
  --headless --csv results/load_llm \
  -H https://orbis.tax
```

**Thresholds Gate U2:**
- P50 `/v1/analyze` < 8s
- P95 `/v1/analyze` < 20s
- P50 `/v1/chunks` < 500ms
- Error rate < 1% com 10 users

---

## Fase 2 — Stress (encontrar o limite)

```bash
# 50 users — identificar saturação
STRESS_TEST_EMAIL=... STRESS_TEST_PASSWORD=... \
locust -f tests/stress/locustfile_mock.py \
  --users 50 --spawn-rate 2 --run-time 15m \
  --headless --csv results/stress_50 \
  -H https://orbis.tax

# 100 users — ponto de quebra
locust -f tests/stress/locustfile_mock.py \
  --users 100 --spawn-rate 5 --run-time 10m \
  --headless --csv results/stress_100 \
  -H https://orbis.tax
```

---

## Fase 3 — Resiliência e Pipeline

```bash
# Testes de mock (sem docker)
pytest tests/integration/test_resilience.py -v -m "resilience and not docker"
pytest tests/integration/test_stress_pipeline.py -v -m pipeline

# Testes com Docker (container kill)
pytest tests/integration/test_resilience.py -v -m docker
```

---

## Fase 4 — Security (OWASP)

```bash
STRESS_BASE_URL=https://orbis.tax \
STRESS_TEST_EMAIL=user@empresa.com STRESS_TEST_PASSWORD=senha \
STRESS_TEST_EMAIL_B=outro@empresa.com STRESS_TEST_PASSWORD_B=senha2 \
pytest tests/integration/test_security_manual.py -v -m security
```

Cobre 13 cenários: auth bypass, IDOR cross-tenant, rate limit, SQL injection,
prompt injection, mass assignment, stack trace, trial bypass, admin escalation,
webhook spoofing, CORS, JWT expirado, UUID inválido.

---

## Fase 5 — Soak (2 horas, detecta memory leak)

```bash
# Terminal 1 — monitoramento
bash scripts/stress_monitor.sh

# Terminal 2 — carga contínua
locust -f tests/stress/locustfile_mock.py \
  --users 5 --spawn-rate 1 --run-time 2h \
  --headless --csv results/soak_2h \
  -H https://orbis.tax
```

---

## Critérios GO/NO-GO

### GO (todos obrigatórios):
- P50 `/v1/analyze` < 8s com 10 users
- P50 `/v1/chunks` < 500ms com 20 users
- Error rate < 1% com 10 users
- 401 para requests sem token
- 404 para IDOR cross-tenant (nunca 200)
- 400 para prompt injection
- Sem stack trace Python em responses
- RAM não cresce durante soak
- Reconexão DB automática < 30s

### NO-GO imediato (qualquer um bloqueia launch):
- Cross-tenant data leak
- Stack trace com paths internos em response body
- OOM kill durante carga ≤ 10 users
- Porta PostgreSQL (5436) acessível externamente
