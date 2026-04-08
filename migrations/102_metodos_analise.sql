-- Migration 102: adicionar campos criticidade e metodos_selecionados ao schema dos casos.
--
-- Não altera tabelas estruturadas — os campos são armazenados no JSONB case_steps.dados,
-- que já suporta qualquer chave sem migration DDL.
--
-- Esta migration apenas registra a intenção e adiciona um índice GIN para
-- buscas futuras sobre criticidade em case_steps.dados.
--
-- Dependências: migration 100 (users) e migration 101 (UUID cases/outputs).
--
BEGIN;

-- Índice GIN em case_steps.dados para suportar consultas por criticidade e métodos
-- (ex: WHERE dados->>'criticidade' = 'extrema')
CREATE INDEX IF NOT EXISTS idx_case_steps_dados_gin
    ON case_steps USING GIN (dados jsonb_path_ops);

COMMIT;

-- Verificação pós-migration
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'case_steps' AND indexname = 'idx_case_steps_dados_gin'
    ) THEN
        RAISE EXCEPTION 'Migration 102 falhou: índice idx_case_steps_dados_gin não criado.';
    END IF;
    RAISE NOTICE 'Migration 102 aplicada com sucesso.';
END;
$$;
