BEGIN;

-- Estender mau_records com campos de metering detalhado
ALTER TABLE mau_records
    ADD COLUMN IF NOT EXISTS total_eventos  INT         NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS ultimo_evento  TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Índice adicional por mês (já existe idx_mau_tenant_month)
CREATE INDEX IF NOT EXISTS idx_mau_user       ON mau_records (user_id);
CREATE INDEX IF NOT EXISTS idx_mau_month      ON mau_records (active_month DESC);

-- View de MAU mensal agregado (por todos os tenants)
CREATE OR REPLACE VIEW vw_mau_mensal AS
SELECT
    active_month,
    COUNT(DISTINCT user_id)  AS total_mau,
    SUM(total_eventos)       AS total_eventos_mes
FROM mau_records
GROUP BY active_month
ORDER BY active_month DESC;

-- View de MAU por usuário (últimos 6 meses)
CREATE OR REPLACE VIEW vw_mau_por_usuario AS
SELECT
    u.id                    AS user_id,
    u.nome,
    u.email,
    u.perfil,
    COUNT(m.user_id)        AS meses_ativo,
    MAX(m.active_month)     AS ultimo_mes_ativo,
    SUM(m.total_eventos)    AS total_eventos
FROM users u
LEFT JOIN mau_records m
    ON u.id = m.user_id
    AND m.active_month >= DATE_TRUNC('month', NOW() - INTERVAL '6 months')::DATE
GROUP BY u.id, u.nome, u.email, u.perfil
ORDER BY total_eventos DESC NULLS LAST;

COMMIT;
