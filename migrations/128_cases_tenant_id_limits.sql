-- Migration 128: Vincula cases ao tenant + permite enforcement de limites por plano
-- Executar: docker exec -i tribus-ai-db psql -U taxmind -d taxmind_db < migrations/128_cases_tenant_id_limits.sql

ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_cases_tenant_id ON cases(tenant_id);
CREATE INDEX IF NOT EXISTS idx_cases_tenant_created ON cases(tenant_id, created_at);

COMMENT ON COLUMN cases.tenant_id IS 'Tenant dono do caso — preenchido na criação via API (migration 128)';
