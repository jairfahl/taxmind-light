# Skill: Pré-Deploy

## Sequência Obrigatória

```bash
# 1. Rodar checklist automático
bash scripts/pre_deploy_check.sh

# 2. Verificar scorecard de qualidade
bash scripts/quality_scorecard.sh
```

Zero erros = pode prosseguir. Qualquer erro = corrigir antes.

## O Que o Script Verifica

1. **Git** — arquivos não rastreados, modificações não commitadas
2. **Testes Backend** — suite deve passar (667+ testes)
3. **Build Frontend** — `npm run build` deve ter sucesso
4. **Variáveis de Ambiente** — LOCKFILE_MODE válido (WARN ou BLOCK)
5. **Secrets** — nenhum .env no staging, nenhuma API key hardcoded
6. **Linters** — ruff check + linters AST

## Deploy no VPS

```bash
# No VPS (após push para main)
cd /opt/tribus-ai-light && bash redeploy.sh

# Se alterou .env.prod (NUNCA usar restart — não relê variáveis)
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate api
```

## Armadilhas de Deploy

- `docker compose restart` NÃO relê `.env.prod` — usar `force-recreate`
- `ASAAS_API_KEY` com `$` em `.env.prod` deve usar `$$` (escape docker compose)
- Arquivos não commitados não chegam ao VPS (redeploy.sh faz `git pull`)
- `LOCKFILE_MODE=ENFORCE` é valor inválido — usar `WARN`
