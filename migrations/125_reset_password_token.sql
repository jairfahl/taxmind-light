-- Migration 125: colunas para reset de senha via e-mail
-- Referência: fluxo "Recuperar senha" (forgot-password / reset-password)

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS reset_token           TEXT,
  ADD COLUMN IF NOT EXISTS reset_token_expires_at TIMESTAMPTZ;

-- Índice parcial para lookup rápido por token (apenas linhas com token ativo)
CREATE INDEX IF NOT EXISTS idx_users_reset_token
  ON users(reset_token)
  WHERE reset_token IS NOT NULL;
