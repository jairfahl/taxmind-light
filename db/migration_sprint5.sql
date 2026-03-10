-- migration_sprint5.sql — Tabelas de Observability de IA
-- Executar: psql $DATABASE_URL -f db/migration_sprint5.sql

-- Baseline de métricas por versão de prompt/modelo
CREATE TABLE IF NOT EXISTS prompt_baselines (
    id                      SERIAL PRIMARY KEY,
    prompt_version          VARCHAR(50)  NOT NULL,
    model_id                VARCHAR(100) NOT NULL,
    baseline_date           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    avg_response_length     FLOAT,
    avg_latencia_ms         FLOAT,
    p95_latencia_ms         FLOAT,
    pct_scoring_alto        FLOAT,
    pct_contra_tese         FLOAT,
    pct_grounding_presente  FLOAT,
    taxa_bloqueio_m1        FLOAT,
    taxa_bloqueio_m2        FLOAT,
    taxa_bloqueio_m3        FLOAT,
    taxa_bloqueio_m4        FLOAT,
    sample_size             INTEGER NOT NULL DEFAULT 0,
    UNIQUE (prompt_version, model_id)
);

-- Métricas agregadas por dia
CREATE TABLE IF NOT EXISTS ai_metrics_daily (
    id                      SERIAL PRIMARY KEY,
    data_referencia         DATE         NOT NULL,
    prompt_version          VARCHAR(50)  NOT NULL,
    model_id                VARCHAR(100) NOT NULL,
    total_interacoes        INTEGER      NOT NULL DEFAULT 0,
    avg_response_length     FLOAT,
    avg_latencia_ms         FLOAT,
    p95_latencia_ms         FLOAT,
    pct_scoring_alto        FLOAT,
    pct_contra_tese         FLOAT,
    pct_grounding_presente  FLOAT,
    taxa_alucinacao         FLOAT,
    taxa_bloqueio_m1        FLOAT,
    taxa_bloqueio_m2        FLOAT,
    taxa_bloqueio_m3        FLOAT,
    taxa_bloqueio_m4        FLOAT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (data_referencia, prompt_version, model_id)
);

-- Alertas de drift
CREATE TABLE IF NOT EXISTS drift_alerts (
    id              SERIAL PRIMARY KEY,
    detectado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    prompt_version  VARCHAR(50)  NOT NULL,
    model_id        VARCHAR(100) NOT NULL,
    metrica         VARCHAR(100) NOT NULL,
    valor_baseline  FLOAT        NOT NULL,
    valor_atual     FLOAT        NOT NULL,
    desvios_padrao  FLOAT        NOT NULL,
    resolvido       BOOLEAN      NOT NULL DEFAULT FALSE,
    resolvido_em    TIMESTAMPTZ,
    observacao      TEXT
);

-- Resultados de regression testing
CREATE TABLE IF NOT EXISTS regression_results (
    id                      SERIAL PRIMARY KEY,
    executado_em            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    prompt_version          VARCHAR(50)  NOT NULL,
    model_id                VARCHAR(100) NOT NULL,
    baseline_version        VARCHAR(50)  NOT NULL,
    precisao_citacao        FLOAT,
    taxa_alucinacao         FLOAT,
    acuracia_recomendacao   FLOAT,
    latencia_p95            FLOAT,
    cobertura_contra_tese   FLOAT,
    aprovado                BOOLEAN NOT NULL,
    detalhes                JSONB   NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_ai_metrics_daily_data ON ai_metrics_daily (data_referencia DESC);
CREATE INDEX IF NOT EXISTS idx_drift_alerts_resolvido ON drift_alerts (resolvido, detectado_em DESC);
CREATE INDEX IF NOT EXISTS idx_regression_results_pv  ON regression_results (prompt_version, executado_em DESC);
