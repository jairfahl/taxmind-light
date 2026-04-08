BEGIN;

ALTER TABLE ai_interactions
    ADD COLUMN IF NOT EXISTS criticidade        VARCHAR(15) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS criticidade_motivo TEXT        DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_ai_criticidade
    ON ai_interactions (criticidade)
    WHERE criticidade IS NOT NULL;

COMMIT;
