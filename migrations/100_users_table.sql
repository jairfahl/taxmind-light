-- Migration: 100_users_table.sql
-- Tribus-AI — User Management Module
-- Criado em: Abril 2026

BEGIN;

-- ─── TABELA USERS ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    nome          VARCHAR(100) NOT NULL,
    senha_hash    VARCHAR(255) NOT NULL,          -- bcrypt hash
    perfil        VARCHAR(10)  NOT NULL
                    CHECK (perfil IN ('ADMIN', 'USER')),
    ativo         BOOLEAN      NOT NULL DEFAULT TRUE,
    primeiro_uso  TIMESTAMPTZ,                    -- NULL até 1º login; dispara timer de trial
    criado_em     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_users_email  ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_perfil ON users (perfil);
CREATE INDEX IF NOT EXISTS idx_users_ativo  ON users (ativo);

-- ─── INSERIR ADMIN PADRÃO ──────────────────────────────────────────────────────
-- Senha padrão: Tribus@2026!
-- Hash bcrypt gerado para esse valor exato.
-- TROCAR EM PRODUÇÃO via painel admin.

INSERT INTO users (email, nome, senha_hash, perfil)
VALUES (
    'admin@tribus-ai.com.br',
    'Administrador',
    '$2b$12$inGAr2VadNykko8N0a0L4uhw68ziktoSE9L4oy6LiexsKJG4iie/u',
    'ADMIN'
)
ON CONFLICT (email) DO NOTHING;

-- ─── ALTERAR AI_INTERACTIONS ───────────────────────────────────────────────────

ALTER TABLE ai_interactions
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id);

-- Índice para queries filtradas por usuário
CREATE INDEX IF NOT EXISTS idx_ai_interactions_user_id
    ON ai_interactions (user_id);

-- ─── COLUNAS DE TOKENS PARA ESTIMATIVA DE CONSUMO ────────────────────────────

ALTER TABLE ai_interactions
    ADD COLUMN IF NOT EXISTS input_tokens  INTEGER;

ALTER TABLE ai_interactions
    ADD COLUMN IF NOT EXISTS output_tokens INTEGER;

COMMIT;
