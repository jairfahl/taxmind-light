-- 129_api_usage_tenant.sql — Adiciona tenant_id à tabela api_usage para rastreio por cliente.
-- Coluna NULL-able: chamadas de ingestão/regression não têm tenant.

ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS tenant_id UUID;
CREATE INDEX IF NOT EXISTS idx_api_usage_tenant ON api_usage (tenant_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_tenant_created ON api_usage (tenant_id, created_at);
