-- migration_consolidate_6steps.sql
-- Consolidates the 9-step protocol into 6 steps.
--
-- Step mapping (old → new):
--   1 → 1  (merged with old 2)
--   2 → 1
--   3 → 2
--   4 → 3
--   5 → 4
--   6 → 5  (merged with old 7)
--   7 → 5
--   8 → 6  (merged with old 9)
--   9 → 6
--
-- Tables affected:
--   case_steps        — merge dados JSONB, renumber passo, update CHECK constraint
--   cases             — remap passo_atual
--   case_state_history — remap passo_de and passo_para
--   carimbo_alerts    — remap passo
--   outputs           — remap passo_origem, update CHECK constraint
--
-- Execute: psql $DATABASE_URL -f db/migration_consolidate_6steps.sql

BEGIN;

-- ============================================================
-- STEP 1: Merge case_steps rows for paired old steps
-- ============================================================
-- We process the three merge pairs (1+2, 6+7, 8+9) one at a time.
-- Strategy for each pair (A, B) → target new_passo:
--   a) For cases that have BOTH A and B: update row A with merged dados
--      and merged concluido, then delete row B.
--   b) For cases that have ONLY B (no A): update row B's passo to the
--      new number in a temp value first to avoid UNIQUE collision, then
--      finalise.
--   c) For cases that have ONLY A: row A stays; passo will be renumbered
--      in the bulk renumber pass below.
--
-- The renumber pass for simple remappings (3→2, 4→3, 5→4) runs AFTER
-- the merge deletions so the UNIQUE constraint is never violated.
-- ============================================================

-- ------------------------------------------------------------
-- 1A. Merge old steps 1 + 2 → new step 1
-- ------------------------------------------------------------

-- When BOTH old 1 and old 2 exist: absorb old 2 into old 1.
UPDATE case_steps AS t1
SET
    dados     = t1.dados || t2.dados,
    concluido = t1.concluido AND t2.concluido,
    updated_at = NOW()
FROM case_steps AS t2
WHERE t1.case_id  = t2.case_id
  AND t1.passo    = 1
  AND t2.passo    = 2;

-- Delete the now-redundant old step 2 rows (only where old 1 also existed).
DELETE FROM case_steps
WHERE passo = 2
  AND case_id IN (
      SELECT case_id FROM case_steps WHERE passo = 1
  );

-- When ONLY old step 2 exists (no old step 1): rename it to passo = 1.
-- No UNIQUE conflict because passo = 1 does not exist for these cases.
UPDATE case_steps
SET   passo      = 1,
      updated_at = NOW()
WHERE passo   = 2
  AND case_id NOT IN (
      SELECT case_id FROM case_steps WHERE passo = 1
  );

-- ------------------------------------------------------------
-- 1B. Merge old steps 6 + 7 → new step 5
--     (use temp value 56 to avoid collision with existing passo = 5
--      while we are still working in the 1-9 space)
-- ------------------------------------------------------------

-- When BOTH old 6 and old 7 exist: absorb old 7 into old 6.
UPDATE case_steps AS t6
SET
    dados     = t6.dados || t7.dados,
    concluido = t6.concluido AND t7.concluido,
    updated_at = NOW()
FROM case_steps AS t7
WHERE t6.case_id = t7.case_id
  AND t6.passo   = 6
  AND t7.passo   = 7;

-- Delete redundant old step 7 rows (only where old 6 also existed).
DELETE FROM case_steps
WHERE passo = 7
  AND case_id IN (
      SELECT case_id FROM case_steps WHERE passo = 6
  );

-- When ONLY old step 7 exists (no old step 6): park it at passo = 6
-- so the bulk renumber below can convert it to 5 in one pass.
UPDATE case_steps
SET   passo      = 6,
      updated_at = NOW()
WHERE passo   = 7
  AND case_id NOT IN (
      SELECT case_id FROM case_steps WHERE passo = 6
  );

-- ------------------------------------------------------------
-- 1C. Merge old steps 8 + 9 → new step 6
-- ------------------------------------------------------------

-- When BOTH old 8 and old 9 exist: absorb old 9 into old 8.
UPDATE case_steps AS t8
SET
    dados     = t8.dados || t9.dados,
    concluido = t8.concluido AND t9.concluido,
    updated_at = NOW()
FROM case_steps AS t9
WHERE t8.case_id = t9.case_id
  AND t8.passo   = 8
  AND t9.passo   = 9;

-- Delete redundant old step 9 rows (only where old 8 also existed).
DELETE FROM case_steps
WHERE passo = 9
  AND case_id IN (
      SELECT case_id FROM case_steps WHERE passo = 8
  );

-- When ONLY old step 9 exists (no old step 8): park it at passo = 8
-- so the bulk renumber below converts it to 6.
UPDATE case_steps
SET   passo      = 8,
      updated_at = NOW()
WHERE passo   = 9
  AND case_id NOT IN (
      SELECT case_id FROM case_steps WHERE passo = 8
  );

-- ============================================================
-- STEP 2: Bulk renumber case_steps to new 1-6 space
-- ============================================================
-- At this point the surviving passo values are: 1, 3, 4, 5, 6, 8.
-- (Old 2, 7, 9 have been deleted or already re-parked above.)
-- Mapping: 3→2, 4→3, 5→4, 6→5, 8→6.
-- passo = 1 stays as 1 — no action needed.
--
-- We must renumber in descending order to avoid transient UNIQUE
-- collisions: 8→6 first, then 6→5, then 5→4, then 4→3, then 3→2.
-- ============================================================

-- Temporarily disable the CHECK constraint so we can pass through
-- intermediate values safely. We will re-add the corrected one at
-- the end of this migration.
ALTER TABLE case_steps DROP CONSTRAINT IF EXISTS case_steps_passo_check;

-- Use negative temp values to avoid UNIQUE(case_id, passo) collisions.
-- Phase 1: move all to negative temps
UPDATE case_steps SET passo = -2, updated_at = NOW() WHERE passo = 3;
UPDATE case_steps SET passo = -3, updated_at = NOW() WHERE passo = 4;
UPDATE case_steps SET passo = -4, updated_at = NOW() WHERE passo = 5;
UPDATE case_steps SET passo = -5, updated_at = NOW() WHERE passo = 6;
UPDATE case_steps SET passo = -6, updated_at = NOW() WHERE passo = 8;

-- Phase 2: flip negatives to final positive values
UPDATE case_steps SET passo = 2, updated_at = NOW() WHERE passo = -2;
UPDATE case_steps SET passo = 3, updated_at = NOW() WHERE passo = -3;
UPDATE case_steps SET passo = 4, updated_at = NOW() WHERE passo = -4;
UPDATE case_steps SET passo = 5, updated_at = NOW() WHERE passo = -5;
UPDATE case_steps SET passo = 6, updated_at = NOW() WHERE passo = -6;

-- ============================================================
-- STEP 3: Update cases.passo_atual
-- ============================================================
-- Mapping: 1→1, 2→1, 3→2, 4→3, 5→4, 6→5, 7→5, 8→6, 9→6
-- ============================================================

UPDATE cases
SET
    passo_atual = CASE passo_atual
        WHEN 1 THEN 1
        WHEN 2 THEN 1
        WHEN 3 THEN 2
        WHEN 4 THEN 3
        WHEN 5 THEN 4
        WHEN 6 THEN 5
        WHEN 7 THEN 5
        WHEN 8 THEN 6
        WHEN 9 THEN 6
        ELSE passo_atual  -- safety: leave unknown values untouched
    END,
    updated_at = NOW()
WHERE passo_atual BETWEEN 1 AND 9;

-- ============================================================
-- STEP 4: Update case_state_history (passo_de and passo_para)
-- ============================================================
-- Historical records are preserved; only the step numbers are remapped.
-- ============================================================

UPDATE case_state_history
SET passo_de = CASE passo_de
    WHEN 1 THEN 1
    WHEN 2 THEN 1
    WHEN 3 THEN 2
    WHEN 4 THEN 3
    WHEN 5 THEN 4
    WHEN 6 THEN 5
    WHEN 7 THEN 5
    WHEN 8 THEN 6
    WHEN 9 THEN 6
    ELSE passo_de
END
WHERE passo_de IS NOT NULL
  AND passo_de BETWEEN 1 AND 9;

UPDATE case_state_history
SET passo_para = CASE passo_para
    WHEN 1 THEN 1
    WHEN 2 THEN 1
    WHEN 3 THEN 2
    WHEN 4 THEN 3
    WHEN 5 THEN 4
    WHEN 6 THEN 5
    WHEN 7 THEN 5
    WHEN 8 THEN 6
    WHEN 9 THEN 6
    ELSE passo_para
END
WHERE passo_para BETWEEN 1 AND 9;

-- ============================================================
-- STEP 5: Update carimbo_alerts.passo
-- ============================================================

UPDATE carimbo_alerts
SET passo = CASE passo
    WHEN 1 THEN 1
    WHEN 2 THEN 1
    WHEN 3 THEN 2
    WHEN 4 THEN 3
    WHEN 5 THEN 4
    WHEN 6 THEN 5
    WHEN 7 THEN 5
    WHEN 8 THEN 6
    WHEN 9 THEN 6
    ELSE passo
END
WHERE passo BETWEEN 1 AND 9;

-- ============================================================
-- STEP 6: Update outputs.passo_origem and its CHECK constraint
-- ============================================================

-- Drop the existing CHECK constraint (named generically by Postgres
-- when created inline; pattern: outputs_passo_origem_check).
ALTER TABLE outputs DROP CONSTRAINT IF EXISTS outputs_passo_origem_check;

UPDATE outputs
SET passo_origem = CASE passo_origem
    WHEN 1 THEN 1
    WHEN 2 THEN 1
    WHEN 3 THEN 2
    WHEN 4 THEN 3
    WHEN 5 THEN 4
    WHEN 6 THEN 5
    WHEN 7 THEN 5
    WHEN 8 THEN 6
    WHEN 9 THEN 6
    ELSE passo_origem
END
WHERE passo_origem BETWEEN 1 AND 9;

-- Re-add CHECK constraint reflecting 6-step range.
ALTER TABLE outputs
    ADD CONSTRAINT outputs_passo_origem_check
    CHECK (passo_origem BETWEEN 1 AND 6);

-- ============================================================
-- STEP 7: Restore CHECK constraint on case_steps.passo (1-6)
-- ============================================================

-- Verify no out-of-range values remain before adding the constraint.
DO $$
DECLARE
    bad_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO bad_count
    FROM case_steps
    WHERE passo NOT BETWEEN 1 AND 6;

    IF bad_count > 0 THEN
        RAISE EXCEPTION
            'migration_consolidate_6steps: % row(s) in case_steps have passo outside 1-6 after renumber. Rolling back.',
            bad_count;
    END IF;
END $$;

ALTER TABLE case_steps
    ADD CONSTRAINT case_steps_passo_check
    CHECK (passo BETWEEN 1 AND 6);

-- ============================================================
-- STEP 8: Verify data consistency post-migration
-- ============================================================

DO $$
DECLARE
    bad_cases    INTEGER;
    bad_history  INTEGER;
    bad_carimbo  INTEGER;
    bad_outputs  INTEGER;
BEGIN
    SELECT COUNT(*) INTO bad_cases
    FROM cases
    WHERE passo_atual NOT BETWEEN 1 AND 6;

    SELECT COUNT(*) INTO bad_history
    FROM case_state_history
    WHERE passo_para NOT BETWEEN 1 AND 6
       OR (passo_de IS NOT NULL AND passo_de NOT BETWEEN 1 AND 6);

    SELECT COUNT(*) INTO bad_carimbo
    FROM carimbo_alerts
    WHERE passo NOT BETWEEN 1 AND 6;

    SELECT COUNT(*) INTO bad_outputs
    FROM outputs
    WHERE passo_origem NOT BETWEEN 1 AND 6;

    IF bad_cases > 0 OR bad_history > 0 OR bad_carimbo > 0 OR bad_outputs > 0 THEN
        RAISE EXCEPTION
            'migration_consolidate_6steps: post-migration check failed — '
            'cases=%, case_state_history=%, carimbo_alerts=%, outputs=%',
            bad_cases, bad_history, bad_carimbo, bad_outputs;
    END IF;

    RAISE NOTICE 'migration_consolidate_6steps: all consistency checks passed.';
END $$;

COMMIT;

-- ============================================================
-- ROLLBACK SECTION (run manually if needed; do NOT execute as
-- part of the forward migration)
-- ============================================================
--
-- NOTE: JSONB merge (||) is NOT reversible without a snapshot.
--       Take a full database backup before running the forward
--       migration so a point-in-time restore is available if
--       needed for the merged dados fields.
--
-- Inverse step mapping (new → original representative):
--   1 → 1  (old 2 data is now inside old 1 dados)
--   2 → 3
--   3 → 4
--   4 → 5
--   5 → 6  (old 7 data is now inside old 6 dados)
--   6 → 8  (old 9 data is now inside old 8 dados)
--
-- -- BEGIN;
-- --
-- -- -- Restore CHECK constraints to 1-9 range
-- -- ALTER TABLE case_steps DROP CONSTRAINT IF EXISTS case_steps_passo_check;
-- -- ALTER TABLE outputs    DROP CONSTRAINT IF EXISTS outputs_passo_origem_check;
-- --
-- -- -- Reverse renumber case_steps (ascending order to avoid collisions)
-- -- UPDATE case_steps SET passo = 3 WHERE passo = 2;
-- -- UPDATE case_steps SET passo = 4 WHERE passo = 3;
-- -- UPDATE case_steps SET passo = 5 WHERE passo = 4;
-- -- UPDATE case_steps SET passo = 6 WHERE passo = 5;
-- -- UPDATE case_steps SET passo = 8 WHERE passo = 6;
-- --
-- -- -- Restore CHECK constraints
-- -- ALTER TABLE case_steps ADD CONSTRAINT case_steps_passo_check  CHECK (passo         BETWEEN 1 AND 9);
-- -- ALTER TABLE outputs    ADD CONSTRAINT outputs_passo_origem_check CHECK (passo_origem BETWEEN 1 AND 9);
-- --
-- -- -- Reverse cases.passo_atual (best-effort; 1 stays as 1, maps to old 1)
-- -- UPDATE cases SET passo_atual = CASE passo_atual
-- --     WHEN 1 THEN 1  -- ambiguous: was 1 or 2
-- --     WHEN 2 THEN 3
-- --     WHEN 3 THEN 4
-- --     WHEN 4 THEN 5
-- --     WHEN 5 THEN 6  -- ambiguous: was 6 or 7
-- --     WHEN 6 THEN 8  -- ambiguous: was 8 or 9
-- --     ELSE passo_atual
-- -- END, updated_at = NOW()
-- -- WHERE passo_atual BETWEEN 1 AND 6;
-- --
-- -- -- Reverse case_state_history
-- -- UPDATE case_state_history SET passo_para = CASE passo_para
-- --     WHEN 1 THEN 1  WHEN 2 THEN 3  WHEN 3 THEN 4
-- --     WHEN 4 THEN 5  WHEN 5 THEN 6  WHEN 6 THEN 8
-- --     ELSE passo_para END
-- -- WHERE passo_para BETWEEN 1 AND 6;
-- --
-- -- UPDATE case_state_history SET passo_de = CASE passo_de
-- --     WHEN 1 THEN 1  WHEN 2 THEN 3  WHEN 3 THEN 4
-- --     WHEN 4 THEN 5  WHEN 5 THEN 6  WHEN 6 THEN 8
-- --     ELSE passo_de END
-- -- WHERE passo_de IS NOT NULL AND passo_de BETWEEN 1 AND 6;
-- --
-- -- -- Reverse carimbo_alerts
-- -- UPDATE carimbo_alerts SET passo = CASE passo
-- --     WHEN 1 THEN 1  WHEN 2 THEN 3  WHEN 3 THEN 4
-- --     WHEN 4 THEN 5  WHEN 5 THEN 6  WHEN 6 THEN 8
-- --     ELSE passo END
-- -- WHERE passo BETWEEN 1 AND 6;
-- --
-- -- -- Reverse outputs.passo_origem
-- -- UPDATE outputs SET passo_origem = CASE passo_origem
-- --     WHEN 1 THEN 1  WHEN 2 THEN 3  WHEN 3 THEN 4
-- --     WHEN 4 THEN 5  WHEN 5 THEN 6  WHEN 6 THEN 8
-- --     ELSE passo_origem END
-- -- WHERE passo_origem BETWEEN 1 AND 6;
-- --
-- -- COMMIT;
