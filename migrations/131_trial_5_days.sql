-- Migration 131: Trial de 7 → 5 dias + limite de 1 protocolo
-- Graceful: tenants cujo trial começou há mais de 5 dias mantêm prazo original

BEGIN;

-- Recalcular trial_ends_at para tenants cujo trial ainda cabe em 5 dias
UPDATE tenants
SET    trial_ends_at = trial_starts_at + INTERVAL '5 days'
WHERE  subscription_status = 'trial'
  AND  trial_ends_at IS NOT NULL
  AND  trial_starts_at IS NOT NULL
  AND  trial_starts_at + INTERVAL '5 days' > NOW();

-- Atualizar comment semântico da coluna de email D-3 → D-2
COMMENT ON COLUMN tenants.trial_d3_email_sent_at
  IS 'Primeiro aviso de trial expirando (D-2). Coluna reutilizada — nome legado D-3.';

COMMIT;
