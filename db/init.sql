CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE normas (
    id         SERIAL PRIMARY KEY,
    codigo     VARCHAR(20)  NOT NULL UNIQUE,
    nome       VARCHAR(200) NOT NULL,
    tipo       VARCHAR(10)  NOT NULL,
    numero     VARCHAR(10)  NOT NULL,
    ano        INTEGER      NOT NULL,
    arquivo    VARCHAR(500),
    vigente    BOOLEAN      DEFAULT TRUE,
    created_at TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE chunks (
    id          SERIAL PRIMARY KEY,
    norma_id    INTEGER      NOT NULL REFERENCES normas(id),
    chunk_index INTEGER      NOT NULL,
    texto       TEXT         NOT NULL,
    artigo      VARCHAR(50),
    secao       VARCHAR(200),
    titulo      VARCHAR(200),
    tokens      INTEGER,
    created_at  TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (norma_id, chunk_index)
);

CREATE TABLE embeddings (
    id         SERIAL PRIMARY KEY,
    chunk_id   INTEGER      NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    modelo     VARCHAR(100) NOT NULL,
    vetor      vector(1024) NOT NULL,
    created_at TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (chunk_id, modelo)
);

CREATE INDEX ON embeddings USING hnsw (vetor vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE TABLE consultas (
    id          SERIAL PRIMARY KEY,
    query_texto TEXT         NOT NULL,
    chunks_ids  INTEGER[],
    scores      FLOAT[],
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE avaliacoes (
    id              SERIAL PRIMARY KEY,
    query_texto     TEXT    NOT NULL,
    top3_pertinente BOOLEAN,
    nota            INTEGER CHECK (nota BETWEEN 1 AND 5),
    observacao      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
