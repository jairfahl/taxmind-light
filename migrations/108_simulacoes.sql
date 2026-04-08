-- Migration 108: tabela de simulações de carga RT.
--
-- MP-01: Simulador Comparativo de Carga RT (G18).
-- Persiste simulações salvas pelo usuário para auditoria e comparação futura.
--
BEGIN;

CREATE TABLE IF NOT EXISTS simulacoes_carga (
    id                  SERIAL PRIMARY KEY,
    user_id             UUID REFERENCES users(id) ON DELETE SET NULL,
    criado_em           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Parâmetros do cenário
    faturamento_anual   NUMERIC(18, 2) NOT NULL,
    regime_tributario   VARCHAR(30)    NOT NULL,
    tipo_operacao       VARCHAR(30)    NOT NULL,
    pct_exportacao      NUMERIC(5, 4)  DEFAULT 0,
    pct_credito_novo    NUMERIC(5, 4)  DEFAULT 1,

    -- Resultado pontual (ano de referência)
    ano_referencia      SMALLINT       NOT NULL,
    carga_liquida_atual NUMERIC(18, 2),
    carga_liquida_nova  NUMERIC(18, 2),
    variacao_pct        NUMERIC(8, 4),

    -- Projeção plurianual serializada
    projecao_json       JSONB          DEFAULT '[]'::jsonb
);

COMMENT ON TABLE simulacoes_carga IS
    'Simulações comparativas de carga tributária RT salvas pelo usuário (MP-01 / G18)';

COMMIT;

-- Verificação pós-migration
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'simulacoes_carga'
    ) THEN
        RAISE EXCEPTION 'Migration 108 falhou: tabela simulacoes_carga não encontrada.';
    END IF;
    RAISE NOTICE 'Migration 108 aplicada com sucesso.';
END;
$$;
