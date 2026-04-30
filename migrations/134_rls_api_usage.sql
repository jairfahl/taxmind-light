-- migration 134 — RLS para api_usage (depende de migration 129: tenant_id adicionado)

ALTER TABLE api_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_api_usage_tenant ON api_usage
    USING (
        app_tenant_id() IS NULL
        OR tenant_id = app_tenant_id()
        OR tenant_id IS NULL
    );
