-- =============================================================
-- Migration 126: SWAP PK/FK — cases e outputs para UUID
-- Sequência: SEC-10 (continuação da migration 118)
-- Data: Abril 2026
--
-- PRÉ-REQUISITO OBRIGATÓRIO:
--   Migration 118 (Partes 1+2) já executada — colunas *_uuid existem e populadas.
--   Backup recente confirmado.
--   Janela de manutenção ativa.
--
-- ESTRATÉGIA: Drop FKs antigas → Swap PK → Swap FKs → Drop colunas inteiras
-- =============================================================

BEGIN;

-- ════════════════════════════════════════════════════════════
-- PARTE 1 — Remover Foreign Keys antigas
-- ════════════════════════════════════════════════════════════

ALTER TABLE case_steps          DROP CONSTRAINT IF EXISTS case_steps_case_id_fkey;
ALTER TABLE case_state_history  DROP CONSTRAINT IF EXISTS case_state_history_case_id_fkey;
ALTER TABLE carimbo_alerts      DROP CONSTRAINT IF EXISTS carimbo_alerts_case_id_fkey;
ALTER TABLE outputs             DROP CONSTRAINT IF EXISTS outputs_case_id_fkey;
ALTER TABLE monitoramento_p6    DROP CONSTRAINT IF EXISTS monitoramento_p6_case_id_fkey;
ALTER TABLE output_stakeholders DROP CONSTRAINT IF EXISTS output_stakeholders_output_id_fkey;
ALTER TABLE output_aprovacoes   DROP CONSTRAINT IF EXISTS output_aprovacoes_output_id_fkey;

-- ════════════════════════════════════════════════════════════
-- PARTE 2 — Swap PK de cases
-- ════════════════════════════════════════════════════════════

ALTER TABLE cases DROP CONSTRAINT cases_pkey;
ALTER TABLE cases RENAME COLUMN id TO id_int_deprecated;
ALTER TABLE cases RENAME COLUMN id_uuid TO id;
ALTER TABLE cases ADD PRIMARY KEY (id);

-- ════════════════════════════════════════════════════════════
-- PARTE 3 — Swap PK de outputs
-- ════════════════════════════════════════════════════════════

ALTER TABLE outputs DROP CONSTRAINT outputs_pkey;
ALTER TABLE outputs RENAME COLUMN id TO id_int_deprecated;
ALTER TABLE outputs RENAME COLUMN id_uuid TO id;
ALTER TABLE outputs ADD PRIMARY KEY (id);

-- ════════════════════════════════════════════════════════════
-- PARTE 4 — Swap FK case_id nas tabelas filhas
-- ════════════════════════════════════════════════════════════

ALTER TABLE case_steps RENAME COLUMN case_id TO case_id_int_deprecated;
ALTER TABLE case_steps RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE case_steps ADD CONSTRAINT case_steps_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;

ALTER TABLE case_state_history RENAME COLUMN case_id TO case_id_int_deprecated;
ALTER TABLE case_state_history RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE case_state_history ADD CONSTRAINT case_state_history_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES cases(id);

ALTER TABLE carimbo_alerts RENAME COLUMN case_id TO case_id_int_deprecated;
ALTER TABLE carimbo_alerts RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE carimbo_alerts ADD CONSTRAINT carimbo_alerts_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;

ALTER TABLE outputs RENAME COLUMN case_id TO case_id_int_deprecated;
ALTER TABLE outputs RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE outputs ADD CONSTRAINT outputs_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES cases(id);

ALTER TABLE monitoramento_p6 RENAME COLUMN case_id TO case_id_int_deprecated;
ALTER TABLE monitoramento_p6 RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE monitoramento_p6 ADD CONSTRAINT monitoramento_p6_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;

-- ════════════════════════════════════════════════════════════
-- PARTE 5 — Swap FK output_id nas tabelas filhas
-- ════════════════════════════════════════════════════════════

ALTER TABLE output_stakeholders RENAME COLUMN output_id TO output_id_int_deprecated;
ALTER TABLE output_stakeholders RENAME COLUMN output_id_uuid TO output_id;
ALTER TABLE output_stakeholders ADD CONSTRAINT output_stakeholders_output_id_fkey
  FOREIGN KEY (output_id) REFERENCES outputs(id);

ALTER TABLE output_aprovacoes RENAME COLUMN output_id TO output_id_int_deprecated;
ALTER TABLE output_aprovacoes RENAME COLUMN output_id_uuid TO output_id;
ALTER TABLE output_aprovacoes ADD CONSTRAINT output_aprovacoes_output_id_fkey
  FOREIGN KEY (output_id) REFERENCES outputs(id);

ALTER TABLE heuristicas RENAME COLUMN dossie_id TO dossie_id_int_deprecated;
ALTER TABLE heuristicas RENAME COLUMN dossie_id_uuid TO dossie_id;

-- ════════════════════════════════════════════════════════════
-- PARTE 6 — Remover colunas inteiras legadas
-- ════════════════════════════════════════════════════════════

ALTER TABLE cases               DROP COLUMN id_int_deprecated;
ALTER TABLE outputs             DROP COLUMN id_int_deprecated;
ALTER TABLE case_steps          DROP COLUMN case_id_int_deprecated;
ALTER TABLE case_state_history  DROP COLUMN case_id_int_deprecated;
ALTER TABLE carimbo_alerts      DROP COLUMN case_id_int_deprecated;
ALTER TABLE outputs             DROP COLUMN case_id_int_deprecated;
ALTER TABLE monitoramento_p6    DROP COLUMN case_id_int_deprecated;
ALTER TABLE output_stakeholders DROP COLUMN output_id_int_deprecated;
ALTER TABLE output_aprovacoes   DROP COLUMN output_id_int_deprecated;
ALTER TABLE heuristicas         DROP COLUMN dossie_id_int_deprecated;

-- ════════════════════════════════════════════════════════════
-- PARTE 7 — Remover sequences inteiras obsoletas
-- ════════════════════════════════════════════════════════════

DROP SEQUENCE IF EXISTS cases_id_seq;
DROP SEQUENCE IF EXISTS outputs_id_seq;

-- ════════════════════════════════════════════════════════════
-- VALIDAÇÃO FINAL
-- ════════════════════════════════════════════════════════════
DO $$
DECLARE
  col_type TEXT;
BEGIN
  SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'cases' AND column_name = 'id';
  IF col_type != 'uuid' THEN
    RAISE EXCEPTION 'FALHA: cases.id não é UUID — tipo atual: %', col_type;
  END IF;

  SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'outputs' AND column_name = 'id';
  IF col_type != 'uuid' THEN
    RAISE EXCEPTION 'FALHA: outputs.id não é UUID — tipo atual: %', col_type;
  END IF;

  RAISE NOTICE 'SEC-10 CONCLUÍDO: cases.id e outputs.id são UUID. FKs recriadas.';
END $$;

COMMIT;
