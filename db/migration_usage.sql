-- Rastreamento de consumo de créditos de API (LLM + embeddings)
CREATE TABLE IF NOT EXISTS api_usage (
    id              SERIAL PRIMARY KEY,
    service         VARCHAR(20)  NOT NULL,  -- 'anthropic' | 'voyageai'
    model           VARCHAR(100) NOT NULL,
    input_tokens    INTEGER      NOT NULL DEFAULT 0,
    output_tokens   INTEGER      NOT NULL DEFAULT 0,
    estimated_cost  NUMERIC(10,6) NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_usage_created ON api_usage (created_at);
