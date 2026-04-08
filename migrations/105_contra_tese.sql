-- Migration 105: campos de contra-tese em ai_interactions.
--
-- G11: Contra-Tese Explícita — toda análise inclui posição contrária obrigatória.
-- Registra força da corrente contrária e presença de contra-tese na resposta da IA.
-- Nota: grau_consolidacao já existe desde sprint anterior — não recriar.
--
BEGIN;

ALTER TABLE ai_interactions
    ADD COLUMN IF NOT EXISTS forca_corrente_contraria  VARCHAR(10)  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS contra_tese_presente      BOOLEAN      DEFAULT NULL;

COMMENT ON COLUMN ai_interactions.forca_corrente_contraria IS
    'Força da corrente contrária à posição recomendada: Alta | Média | Baixa';
COMMENT ON COLUMN ai_interactions.contra_tese_presente IS
    'True se a resposta da IA incluiu contra-tese explícita (G11)';

COMMIT;

-- Verificação pós-migration
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ai_interactions' AND column_name = 'forca_corrente_contraria'
    ) THEN
        RAISE EXCEPTION 'Migration 105 falhou: coluna forca_corrente_contraria não encontrada.';
    END IF;
    RAISE NOTICE 'Migration 105 aplicada com sucesso.';
END;
$$;
