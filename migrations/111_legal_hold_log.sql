-- Migration 111: Legal Hold audit log + campos de expiração (G14).
--
-- C2 — Legal Hold: imutabilidade de registros sob demanda.
-- documento_id é INTEGER (outputs.id e ai_interactions.id são SERIAL).
-- Expiração padrão: 5 anos (CTN art. 150, §4º — prescrição tributária).
--
BEGIN;

-- Audit log de operações de Legal Hold
CREATE TABLE IF NOT EXISTS legal_hold_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    documento_id    INTEGER     NOT NULL,   -- outputs.id ou ai_interactions.id
    tabela_origem   VARCHAR(50) NOT NULL,   -- 'outputs' | 'ai_interactions'
    operacao        VARCHAR(20) NOT NULL,   -- 'ativar' | 'desativar' | 'expirar'
    realizado_por   UUID        REFERENCES users(id),
    justificativa   TEXT        DEFAULT NULL,
    hold_ate        DATE        DEFAULT NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lh_log_doc  ON legal_hold_log (documento_id);
CREATE INDEX IF NOT EXISTS idx_lh_log_user ON legal_hold_log (realizado_por);

-- Campos de expiração e motivo em outputs
ALTER TABLE outputs
    ADD COLUMN IF NOT EXISTS legal_hold_ate    DATE DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS legal_hold_motivo TEXT DEFAULT NULL;

-- Campos de Legal Hold em ai_interactions
ALTER TABLE ai_interactions
    ADD COLUMN IF NOT EXISTS legal_hold     BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS legal_hold_ate DATE    DEFAULT NULL;

-- Expiração padrão: 5 anos a partir da criação para outputs com legal_hold=TRUE
UPDATE outputs
SET legal_hold_ate = (created_at + INTERVAL '5 years')::DATE
WHERE legal_hold = TRUE AND legal_hold_ate IS NULL;

COMMIT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'legal_hold_log'
    ) THEN
        RAISE EXCEPTION 'Migration 111 falhou: tabela legal_hold_log não encontrada.';
    END IF;
    RAISE NOTICE 'Migration 111 aplicada com sucesso.';
END;
$$;
