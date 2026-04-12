#!/bin/bash
set -e

echo "==> Pulling latest code..."
git pull origin main

echo "==> Building and restarting containers..."
docker compose --env-file .env.prod -f docker-compose.prod.yml build --no-cache
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

echo "==> Waiting for DB to be healthy..."
sleep 5

echo "==> Checking running containers..."
docker compose --env-file .env.prod -f docker-compose.prod.yml ps

echo "==> Deploy completo."
