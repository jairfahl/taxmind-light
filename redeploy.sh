#!/bin/bash
# =============================================================
# Orbis.tax — Redeploy de Produção
# Uso: bash redeploy.sh
# =============================================================
set -e

RAIZ="$(cd "$(dirname "$0")" && pwd)"
cd "$RAIZ"

echo "==> Pulling latest code..."
git pull origin main

echo "==> Building and restarting containers..."
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build api ui

echo "==> Waiting for startup..."
sleep 15

docker compose --env-file .env.prod -f docker-compose.prod.yml ps

echo ""
echo "============================================"
echo "Acesse: https://orbis.tax"
echo "Email:  admin@orbis.tax"
echo "Senha:  Admin2026"
echo "============================================"
