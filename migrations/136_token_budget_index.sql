-- migration 136 — índice parcial para queries de token budget diário por tenant.
-- Usado por verificar_budget_tenant() e obter_uso_diario_tenant() em src/billing/token_budget.py.
-- Operação segura: CREATE INDEX IF NOT EXISTS, não bloqueia o banco.

CREATE INDEX IF NOT EXISTS idx_api_usage_tenant_daily
    ON api_usage (tenant_id, created_at)
    WHERE tenant_id IS NOT NULL;
