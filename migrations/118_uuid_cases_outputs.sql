-- =============================================================
-- Migration 118: Converter IDs de cases e outputs para UUID
-- Sequência: LL-07 (D-03 — SEC-10)
-- Data: Abril 2026
-- Autor: Tribus-AI / PO
--
-- PRÉ-REQUISITOS OBRIGATÓRIOS:
--   1. Backup recente do banco (LL-06 executado)
--   2. Janela de manutenção confirmada com PO
--   3. Testes passando antes da aplicação
--
-- IMPACTO (FKs afetadas):
--   cases.id  → 5 tabelas: case_steps, case_state_history, carimbo_alerts,
--               outputs (case_id), monitoramento_p6
--   outputs.id → 3 tabelas: output_stakeholders, output_aprovacoes, heuristicas
--
-- IMPACTO DE CÓDIGO (exige alteração após migration):
--   src/api/main.py:   8 endpoints com case_id: int / output_id: int
--   src/protocol/engine.py: case_id: int em toda a engine
--   frontend/store/protocolo.ts: caseId: number | null → string | null
--   frontend/components/protocolo/P*.tsx: case_id: number → string
--   frontend/app/(app)/documentos/page.tsx: case_id: number → string
--
-- ESTRATÉGIA: ADD COLUMN UUID → POPULATE → SWAP PK/FK → DROP INTEGER
-- Executar com ROLLBACK para teste seguro. Remover ROLLBACK apenas após
-- validação completa e aprovação do PO.
-- =============================================================

BEGIN;

-- ════════════════════════════════════════════════════════════
-- PARTE 1 — CASES
-- ════════════════════════════════════════════════════════════

-- 1.1 Adicionar coluna UUID a cases
ALTER TABLE cases ADD COLUMN IF NOT EXISTS id_uuid UUID DEFAULT gen_random_uuid();
UPDATE cases SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL;
ALTER TABLE cases ALTER COLUMN id_uuid SET NOT NULL;

-- 1.2 Propagar UUID para FKs dependentes de cases.id
ALTER TABLE case_steps         ADD COLUMN IF NOT EXISTS case_id_uuid UUID;
ALTER TABLE case_state_history ADD COLUMN IF NOT EXISTS case_id_uuid UUID;
ALTER TABLE carimbo_alerts     ADD COLUMN IF NOT EXISTS case_id_uuid UUID;
ALTER TABLE outputs            ADD COLUMN IF NOT EXISTS case_id_uuid UUID;
ALTER TABLE monitoramento_p6   ADD COLUMN IF NOT EXISTS case_id_uuid UUID;

UPDATE case_steps cs
  SET case_id_uuid = c.id_uuid FROM cases c WHERE cs.case_id = c.id;

UPDATE case_state_history csh
  SET case_id_uuid = c.id_uuid FROM cases c WHERE csh.case_id = c.id;

UPDATE carimbo_alerts ca
  SET case_id_uuid = c.id_uuid FROM cases c WHERE ca.case_id = c.id;

UPDATE outputs o
  SET case_id_uuid = c.id_uuid FROM cases c WHERE o.case_id = c.id;

UPDATE monitoramento_p6 m
  SET case_id_uuid = c.id_uuid FROM cases c WHERE m.case_id = c.id;

-- 1.3 Verificar integridade (zero órfãos)
DO $$
DECLARE
  orphans INTEGER;
BEGIN
  SELECT COUNT(*) INTO orphans FROM case_steps
    WHERE case_id IS NOT NULL AND case_id_uuid IS NULL;
  IF orphans > 0 THEN
    RAISE EXCEPTION 'INTEGRIDADE: % registros órfãos em case_steps (case_id_uuid NULL)', orphans;
  END IF;

  SELECT COUNT(*) INTO orphans FROM case_state_history
    WHERE case_id IS NOT NULL AND case_id_uuid IS NULL;
  IF orphans > 0 THEN
    RAISE EXCEPTION 'INTEGRIDADE: % registros órfãos em case_state_history (case_id_uuid NULL)', orphans;
  END IF;

  SELECT COUNT(*) INTO orphans FROM outputs
    WHERE case_id IS NOT NULL AND case_id_uuid IS NULL;
  IF orphans > 0 THEN
    RAISE EXCEPTION 'INTEGRIDADE: % registros órfãos em outputs (case_id_uuid NULL)', orphans;
  END IF;

  RAISE NOTICE 'INTEGRIDADE OK: todos os case_id_uuid propagados sem órfãos.';
END $$;

-- ════════════════════════════════════════════════════════════
-- PARTE 2 — OUTPUTS
-- ════════════════════════════════════════════════════════════

-- 2.1 Adicionar coluna UUID a outputs
ALTER TABLE outputs ADD COLUMN IF NOT EXISTS id_uuid UUID DEFAULT gen_random_uuid();
UPDATE outputs SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL;
ALTER TABLE outputs ALTER COLUMN id_uuid SET NOT NULL;

-- 2.2 Propagar UUID para FKs dependentes de outputs.id
ALTER TABLE output_stakeholders ADD COLUMN IF NOT EXISTS output_id_uuid UUID;
ALTER TABLE output_aprovacoes   ADD COLUMN IF NOT EXISTS output_id_uuid UUID;
ALTER TABLE heuristicas         ADD COLUMN IF NOT EXISTS dossie_id_uuid UUID;

UPDATE output_stakeholders os
  SET output_id_uuid = o.id_uuid FROM outputs o WHERE os.output_id = o.id;

UPDATE output_aprovacoes oa
  SET output_id_uuid = o.id_uuid FROM outputs o WHERE oa.output_id = o.id;

UPDATE heuristicas h
  SET dossie_id_uuid = o.id_uuid FROM outputs o WHERE h.dossie_id = o.id;

-- 2.3 Verificar integridade outputs
DO $$
DECLARE
  orphans INTEGER;
BEGIN
  SELECT COUNT(*) INTO orphans FROM output_stakeholders
    WHERE output_id IS NOT NULL AND output_id_uuid IS NULL;
  IF orphans > 0 THEN
    RAISE EXCEPTION 'INTEGRIDADE: % registros órfãos em output_stakeholders', orphans;
  END IF;

  RAISE NOTICE 'INTEGRIDADE OK: todos os output_id_uuid propagados sem órfãos.';
END $$;

-- ════════════════════════════════════════════════════════════
-- CHECKPOINT — Validação até aqui (seguro executar com ROLLBACK)
-- As colunas *_uuid foram adicionadas e populadas.
-- Nenhuma constraint foi alterada ainda.
-- Verificar:
--   SELECT id, id_uuid FROM cases LIMIT 5;
--   SELECT id, id_uuid FROM outputs LIMIT 5;
--   SELECT case_id, case_id_uuid FROM case_steps LIMIT 5;
-- ════════════════════════════════════════════════════════════

-- ════════════════════════════════════════════════════════════
-- PARTE 3 — SWAP PK/FK (ALTO RISCO — executar em janela de manutenção)
-- Remover o ROLLBACK da Parte 2 antes de executar esta parte.
-- Confirmar com PO antes de prosseguir.
-- ════════════════════════════════════════════════════════════

-- 3.1 Remover FKs antigas (constraints nomeadas)
-- ALTER TABLE case_steps         DROP CONSTRAINT case_steps_case_id_fkey;
-- ALTER TABLE case_state_history DROP CONSTRAINT case_state_history_case_id_fkey;
-- ALTER TABLE carimbo_alerts     DROP CONSTRAINT carimbo_alerts_case_id_fkey;
-- ALTER TABLE outputs            DROP CONSTRAINT outputs_case_id_fkey;
-- ALTER TABLE monitoramento_p6   DROP CONSTRAINT monitoramento_p6_case_id_fkey;
-- ALTER TABLE output_stakeholders DROP CONSTRAINT output_stakeholders_output_id_fkey;
-- ALTER TABLE output_aprovacoes  DROP CONSTRAINT output_aprovacoes_output_id_fkey;
-- (heuristicas.dossie_id pode não ter FK formal — verificar com \d heuristicas)

-- 3.2 Trocar PK de cases
-- ALTER TABLE cases DROP CONSTRAINT cases_pkey;
-- ALTER TABLE cases RENAME COLUMN id TO id_int_deprecated;
-- ALTER TABLE cases RENAME COLUMN id_uuid TO id;
-- ALTER TABLE cases ADD PRIMARY KEY (id);

-- 3.3 Trocar PK de outputs
-- ALTER TABLE outputs DROP CONSTRAINT outputs_pkey;
-- ALTER TABLE outputs RENAME COLUMN id TO id_int_deprecated;
-- ALTER TABLE outputs RENAME COLUMN id_uuid TO id;
-- ALTER TABLE outputs ADD PRIMARY KEY (id);

-- 3.4 Renomear colunas FK nas tabelas filhas e recriar constraints
-- (repetir para cada tabela filha)
-- ALTER TABLE case_steps RENAME COLUMN case_id TO case_id_int_deprecated;
-- ALTER TABLE case_steps RENAME COLUMN case_id_uuid TO case_id;
-- ALTER TABLE case_steps ADD CONSTRAINT case_steps_case_id_fkey
--   FOREIGN KEY (case_id) REFERENCES cases(id);

-- 3.5 Remover colunas inteiras antigas (após validação)
-- ALTER TABLE cases DROP COLUMN id_int_deprecated;
-- ALTER TABLE outputs DROP COLUMN id_int_deprecated;
-- ALTER TABLE case_steps DROP COLUMN case_id_int_deprecated;
-- ... (repetir para todas as tabelas filhas)

-- 3.6 Remover SEQUENCE antigas (opcional — não causa erro se mantidas)
-- DROP SEQUENCE IF EXISTS cases_id_seq;
-- DROP SEQUENCE IF EXISTS outputs_id_seq;

-- ════════════════════════════════════════════════════════════
-- ROLLBACK de segurança — remover apenas após aprovação do PO
-- e execução confirmada em staging
-- ════════════════════════════════════════════════════════════
ROLLBACK;
