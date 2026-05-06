"""
tests/stress/config.py — Configuração centralizada para stress testing.

Todas as credenciais via variáveis de ambiente — nunca hardcoded.
"""
import os

# ---------------------------------------------------------------------------
# Servidor alvo
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("STRESS_BASE_URL", "https://orbis.tax")

# ---------------------------------------------------------------------------
# Conta de teste (deve ser conta PRO/Starter para não bater trial limit)
# ---------------------------------------------------------------------------
TEST_EMAIL    = os.getenv("STRESS_TEST_EMAIL", "")
TEST_PASSWORD = os.getenv("STRESS_TEST_PASSWORD", "")

# Conta secundária para testes IDOR (tenant diferente)
TEST_EMAIL_B    = os.getenv("STRESS_TEST_EMAIL_B", "")
TEST_PASSWORD_B = os.getenv("STRESS_TEST_PASSWORD_B", "")

# ---------------------------------------------------------------------------
# Thresholds Gate U2 (piped-humming-bengio.md §Thresholds)
# ---------------------------------------------------------------------------
THRESHOLDS = {
    # Latências (ms)
    "p50_analyze_ms":   8_000,   # RAG + LLM é lento por natureza
    "p95_analyze_ms":  20_000,
    "p50_chunks_ms":      500,   # Retrieval puro
    "p95_chunks_ms":    1_500,
    "p50_cases_ms":       300,   # DB puro
    # Taxas
    "error_rate_pct":     1.0,   # < 1% com 10 users
    # Recursos VPS
    "cpu_pct":           80.0,
    "ram_pct":           85.0,
    # Cache
    "cache_hit_rate_pct": 70.0,  # > 70% com queries repetidas
}

# ---------------------------------------------------------------------------
# Queries tributárias realistas (usadas no locustfile.py)
# ---------------------------------------------------------------------------
QUERIES_FISCAIS = [
    "Como funciona o crédito de IBS para empresas do regime não-cumulativo?",
    "Qual é a alíquota padrão do CBS para serviços de TI?",
    "Como a EC 132/2023 afeta o aproveitamento de créditos de PIS/Cofins?",
    "O Split Payment se aplica a operações de exportação de serviços?",
    "Quais são as regras de transição do ISS para o IBS para municípios?",
    "Como calcular o Imposto Seletivo sobre bebidas alcoólicas após a LC 214?",
    "Uma empresa do Simples Nacional pode optar pelo regime não-cumulativo do IBS?",
    "Qual o tratamento do IBS nas operações com imóveis?",
    "Como funciona a devolução do IBS para pessoas físicas de baixa renda?",
    "Quais setores têm alíquota diferenciada no CBS conforme a LC 214/2025?",
]
