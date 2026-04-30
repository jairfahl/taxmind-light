-- migration 133 — Row Level Security: habilitação + políticas de isolamento multi-tenant
--
-- FASE 1: Habilita RLS nas tabelas com tenant_id direto.
-- As políticas permitem acesso quando:
--   (a) app.tenant_id não está definido na sessão (consultas de serviço/admin — backward compatible)
--   (b) tenant_id da linha corresponde ao app.tenant_id da sessão
--   (c) tenant_id da linha é NULL (dados globais/compartilhados)
--
-- FASE 2 (trabalho futuro): criar role app_user sem privilégios de dono de tabela,
--   habilitar FORCE ROW LEVEL SECURITY, e injetar app.tenant_id via middleware FastAPI.
--
-- Tabelas com tenant_id direto:
--   users, cases, mau_records, api_usage

-- ─────────────────────────────────────────────────────────────────────────────
-- HELPER: função para verificar se tenant_id da sessão está definido
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION app_tenant_id() RETURNS UUID AS $$
BEGIN
    RETURN NULLIF(current_setting('app.tenant_id', true), '')::UUID;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE SECURITY INVOKER;


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: users
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Permite acesso quando: sessão não tem tenant_id (admin/serviço)
--                    OU: usuário pertence ao tenant da sessão
--                    OU: usuário não tem tenant_id (usuário global)
CREATE POLICY rls_users_tenant ON users
    USING (
        app_tenant_id() IS NULL
        OR tenant_id = app_tenant_id()
        OR tenant_id IS NULL
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: cases
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE cases ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_cases_tenant ON cases
    USING (
        app_tenant_id() IS NULL
        OR tenant_id = app_tenant_id()
        OR tenant_id IS NULL
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: mau_records
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE mau_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_mau_records_tenant ON mau_records
    USING (
        app_tenant_id() IS NULL
        OR tenant_id = app_tenant_id()
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: api_usage
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE api_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_api_usage_tenant ON api_usage
    USING (
        app_tenant_id() IS NULL
        OR tenant_id = app_tenant_id()
        OR tenant_id IS NULL
    );
