-- Migration 109: Monitoramento P6 — Ciclo Pós-Decisão (G06, G07).
--
-- Cria tabela monitoramento_p6 e adiciona colunas p6_ativo em ai_interactions.
--
BEGIN;

CREATE TABLE IF NOT EXISTS monitoramento_p6 (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_id       INTEGER     REFERENCES ai_interactions(id) ON DELETE CASCADE,  -- nullable
    case_id              INTEGER     REFERENCES cases(id) ON DELETE CASCADE,
    titulo               TEXT        DEFAULT NULL,
    user_id              UUID        REFERENCES users(id) ON DELETE SET NULL,

    -- Status
    status               VARCHAR(20) NOT NULL DEFAULT 'ativo',
    -- 'ativo' | 'revisao_pendente' | 'encerrado'

    -- Resultado real registrado pelo gestor
    resultado_real       TEXT        DEFAULT NULL,
    resultado_em         TIMESTAMPTZ DEFAULT NULL,

    -- Alertas gerados
    alertas_gerados      JSONB       DEFAULT '[]'::jsonb,
    ultimo_alerta_em     TIMESTAMPTZ DEFAULT NULL,

    -- Premissas que precisam ser revisadas
    premissas_invalidas  TEXT[]      DEFAULT '{}',

    -- Controle
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_monit_p6_interaction
    ON monitoramento_p6 (interaction_id);
CREATE INDEX IF NOT EXISTS idx_monit_p6_user
    ON monitoramento_p6 (user_id);
CREATE INDEX IF NOT EXISTS idx_monit_p6_status
    ON monitoramento_p6 (status);

-- Flag em ai_interactions: decisão está sendo monitorada
ALTER TABLE ai_interactions
    ADD COLUMN IF NOT EXISTS p6_ativo     BOOLEAN     DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS p6_criado_em TIMESTAMPTZ DEFAULT NULL;

COMMIT;

-- Verificação pós-migration
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'monitoramento_p6'
    ) THEN
        RAISE EXCEPTION 'Migration 109 falhou: tabela monitoramento_p6 não encontrada.';
    END IF;
    RAISE NOTICE 'Migration 109 aplicada com sucesso.';
END;
$$;
