-- Migration 101: converter cases.id e outputs.id de SERIAL para UUID
-- SEC-10: IDs sequenciais permitem enumeração de recursos de outros tenants.
--
-- ATENÇÃO: Esta migration é DESTRUTIVA.
-- Executar SOMENTE com backup do banco:
--   docker exec tribus-ai-db pg_dump -U taxmind taxmind_db > backup_pre_101.sql
--
-- Estratégia:
--   1. Adicionar coluna uuid em cada tabela
--   2. Popular uuid com gen_random_uuid() para registros existentes
--   3. Atualizar FKs nas tabelas dependentes
--   4. Remover old id, renomear uuid → id
--   5. Recriar PKs e FKs
--
-- Dependências de cases.id:
--   case_steps.case_id
--   carimbo_alerts.case_id
--   outputs.case_id
--
-- Dependências de outputs.id:
--   (nenhuma FK documentada)
--
-- Executar dentro de uma transação:
BEGIN;

-- ─── 1. CASOS ──────────────────────────────────────────────────────────────────

-- Adicionar coluna uuid em cases
ALTER TABLE cases ADD COLUMN uuid UUID DEFAULT gen_random_uuid();
UPDATE cases SET uuid = gen_random_uuid() WHERE uuid IS NULL;
ALTER TABLE cases ALTER COLUMN uuid SET NOT NULL;

-- Adicionar coluna uuid em tabelas dependentes
ALTER TABLE case_steps ADD COLUMN case_uuid UUID;
ALTER TABLE carimbo_alerts ADD COLUMN case_uuid UUID;
ALTER TABLE outputs ADD COLUMN case_uuid UUID;

-- Popular FKs com UUIDs correspondentes
UPDATE case_steps cs
SET case_uuid = c.uuid
FROM cases c
WHERE cs.case_id = c.id;

UPDATE carimbo_alerts ca
SET case_uuid = c.uuid
FROM cases c
WHERE ca.case_id = c.id;

UPDATE outputs o
SET case_uuid = c.uuid
FROM cases c
WHERE o.case_id = c.id;

-- Remover constraints antigas
ALTER TABLE case_steps DROP CONSTRAINT IF EXISTS case_steps_case_id_fkey;
ALTER TABLE carimbo_alerts DROP CONSTRAINT IF EXISTS carimbo_alerts_case_id_fkey;
ALTER TABLE outputs DROP CONSTRAINT IF EXISTS outputs_case_id_fkey;

-- Remover colunas antigas
ALTER TABLE case_steps DROP COLUMN case_id;
ALTER TABLE carimbo_alerts DROP COLUMN case_id;
ALTER TABLE outputs DROP COLUMN case_id;

-- Renomear colunas uuid → id / case_id
ALTER TABLE case_steps RENAME COLUMN case_uuid TO case_id;
ALTER TABLE carimbo_alerts RENAME COLUMN case_uuid TO case_id;
ALTER TABLE outputs RENAME COLUMN case_uuid TO case_id;

-- Trocar PK de cases
ALTER TABLE cases DROP CONSTRAINT cases_pkey;
ALTER TABLE cases DROP COLUMN id;
ALTER TABLE cases RENAME COLUMN uuid TO id;
ALTER TABLE cases ADD PRIMARY KEY (id);

-- Recriar FKs
ALTER TABLE case_steps
    ADD CONSTRAINT case_steps_case_id_fkey
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;

ALTER TABLE carimbo_alerts
    ADD CONSTRAINT carimbo_alerts_case_id_fkey
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE;

ALTER TABLE outputs
    ADD CONSTRAINT outputs_case_id_fkey
    FOREIGN KEY (case_id) REFERENCES cases(id);

-- ─── 2. OUTPUTS ───────────────────────────────────────────────────────────────

-- Adicionar coluna uuid em outputs
ALTER TABLE outputs ADD COLUMN uuid UUID DEFAULT gen_random_uuid();
UPDATE outputs SET uuid = gen_random_uuid() WHERE uuid IS NULL;
ALTER TABLE outputs ALTER COLUMN uuid SET NOT NULL;

-- Trocar PK de outputs
ALTER TABLE outputs DROP CONSTRAINT outputs_pkey;
ALTER TABLE outputs DROP COLUMN id;
ALTER TABLE outputs RENAME COLUMN uuid TO id;
ALTER TABLE outputs ADD PRIMARY KEY (id);

-- ─── 3. ATUALIZAR case_state_history (se referenciar case_id INTEGER) ─────────

-- Verificar e adaptar se houver FK em case_state_history
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'case_state_history'
          AND column_name = 'case_id'
          AND data_type = 'integer'
    ) THEN
        ALTER TABLE case_state_history ADD COLUMN case_uuid UUID;
        UPDATE case_state_history csh
        SET case_uuid = c.id
        FROM cases c
        WHERE csh.case_id = c.id::text::integer
           OR csh.case_id::text = c.id::text;
        ALTER TABLE case_state_history DROP COLUMN case_id;
        ALTER TABLE case_state_history RENAME COLUMN case_uuid TO case_id;
    END IF;
END;
$$;

COMMIT;

-- Verificação pós-migration
DO $$
DECLARE
    v_type TEXT;
BEGIN
    SELECT data_type INTO v_type
    FROM information_schema.columns
    WHERE table_name = 'cases' AND column_name = 'id';
    IF v_type <> 'uuid' THEN
        RAISE EXCEPTION 'Migration 101 falhou: cases.id não é UUID (tipo encontrado: %)', v_type;
    END IF;

    SELECT data_type INTO v_type
    FROM information_schema.columns
    WHERE table_name = 'outputs' AND column_name = 'id';
    IF v_type <> 'uuid' THEN
        RAISE EXCEPTION 'Migration 101 falhou: outputs.id não é UUID (tipo encontrado: %)', v_type;
    END IF;

    RAISE NOTICE 'Migration 101 aplicada com sucesso. cases.id e outputs.id são agora UUID.';
END;
$$;
