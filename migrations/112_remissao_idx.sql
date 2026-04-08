BEGIN;

-- Adiciona coluna remissao_norm_id para suportar RAR (G12)
-- FK para normas(id): identifica qual norma este chunk referencia
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS remissao_norm_id INTEGER REFERENCES normas(id);

-- Índice para busca eficiente de chunks por remissao_norm_id
CREATE INDEX IF NOT EXISTS idx_chunks_remissao_norm_id
    ON chunks (remissao_norm_id)
    WHERE remissao_norm_id IS NOT NULL;

-- Índice composto para busca por norma + artigo (resolução direta)
CREATE INDEX IF NOT EXISTS idx_chunks_norma_artigo
    ON chunks (norma_id, artigo)
    WHERE artigo IS NOT NULL;

COMMIT;
