# Deploy VPS — Referência de Produção

## Informações Gerais

| Item | Valor |
|------|-------|
| Provider | Hostinger |
| IP | `69.62.100.24` |
| Domínio | https://orbis.tax |
| SSL | Let's Encrypt (expira 2026-07-11, renovação automática) |
| Arquivos prod | `/root/tribus-ai-light/` |
| Secrets | `/root/tribus-ai-light/.env.prod` (nunca commitar) |

---

## Stack de Produção

- `docker-compose.prod.yml` + nginx do HOST (`nginx/host-nginx-orbis.tax.conf`) como reverse proxy
- 3 serviços Docker: `db`, `api`, `ui` (nginx é processo do host, não container)
- Portas Docker: `127.0.0.1:8020` (api) e `127.0.0.1:8521` (ui) — somente localhost
- Admin padrão: `admin@orbis.tax` / `Admin2026`

---

## Comandos Essenciais

```bash
# SSH para a VPS (alias configurado em ~/.ssh/config)
ssh orbis

# Redeploy completo
cd /root/tribus-ai-light && bash redeploy.sh

# Recriar serviço (relê .env.prod — USAR SEMPRE, não restart)
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate api

# Logs em tempo real
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f

# Fix de senha via container
docker exec -i tribus-ai-api python3 < /tmp/fix_hash.py

# Verificar variável de ambiente dentro do container
docker exec tribus-ai-api env | grep ASAAS
```

---

## Armadilhas Conhecidas

| Armadilha | Causa | Solução |
|-----------|-------|---------|
| `docker compose up` sem `-f` no VPS | `docker-compose.yml` é guard file — exibe instruções e falha imediatamente | Usar `bash redeploy.sh` (único comando válido em prod) |
| `docker compose restart` não aplica nova env var | `restart` não relê `.env.prod` | Usar `up -d --force-recreate <serviço>` |
| `ASAAS_API_KEY` com `$` no .env.prod | Docker compose interpreta `$` como variável de shell | Usar `$$` no lugar de `$` |
| `ASAAS_BASE_URL` sandbox com chave de produção | Chave `$aact_prod_...` não autentica em `sandbox.asaas.com` → 401 → 500 para o usuário | `ASAAS_BASE_URL=https://api.asaas.com/v3` |
| `LOCKFILE_MODE=ENFORCE` | Valor inválido — causa startup error | Usar `WARN` ou `BLOCK` |
| Arquivos não commitados não chegam ao VPS | `redeploy.sh` faz `git pull` | `git status` + `git log origin/main..HEAD` + push antes de rodar `redeploy.sh` |

---

## Pré-Deploy Obrigatório

```bash
bash scripts/pre_deploy_check.sh
```

Zero erros = pode prosseguir. Qualquer erro = corrigir antes.

O script verifica: git status, testes backend, build frontend, LOCKFILE_MODE válido, secrets hardcoded, linters.

---

## Variáveis Obrigatórias no .env.prod

| Variável | Observação |
|----------|-----------|
| `DATABASE_URL` | Apontar para container `db` na rede Docker |
| `JWT_SECRET` | Sem fallback — RuntimeError se ausente |
| `ANTHROPIC_API_KEY` | Claude API |
| `VOYAGE_API_KEY` | Embeddings voyage-3 |
| `RESEND_API_KEY` | Obrigatória para e-mail de verificação |
| `ASAAS_API_KEY` | Iniciar com `$$` (escape docker compose) |
| `ASAAS_BASE_URL` | **Produção:** `https://api.asaas.com/v3` — NÃO usar sandbox com chave de produção |
| `LOCKFILE_MODE` | `WARN` (não `ENFORCE`) |
| `ZAPI_INSTANCE_ID` | ID da instância no painel Z-API |
| `ZAPI_TOKEN` | Token da instância no painel Z-API |
| `ZAPI_SECURITY_TOKEN` | Token de segurança (opcional, recomendado) |

---

## SSH — Configuração Local

Chave: `~/.ssh/orbis_vps`
Alias configurado em `~/.ssh/config`:

```
Host orbis
  HostName 69.62.100.24
  User root
  IdentityFile ~/.ssh/orbis_vps
```

Uso: `ssh orbis` (sem digitar IP ou credenciais)

---

## SSH — Hardening (30/04/2026)

Configurações aplicadas em `/etc/ssh/sshd_config` na VPS:

```
PermitRootLogin prohibit-password   # root só via chave — sem senha
PasswordAuthentication no           # desabilita senha para todos os usuários
```

**Acesso:** exclusivamente via chave `~/.ssh/orbis_vps`. Senha root desabilitada.
**Validado com:** `sshd -t` antes do reload — zero erros de config.

---

## Checklist P2 — Resultado da Auditoria (30/04/2026)

| Item | Status | Detalhe |
|------|--------|---------|
| F01 BYPASS_AUTH | ✅ Seguro | Não presente em `.env.prod` — `False` hardcoded no código |
| F05 Porta PG exposta | ✅ Seguro | PostgreSQL não acessível externamente em prod (`docker-compose.prod.yml`) |
| F06 Env vars críticas | ✅ Completo | 10 variáveis críticas presentes e corretas |
| F08 Backup VPS | ✅ Ativo | Hostinger Snapshots automáticos diários (~52 GB, VPS completo incluindo volumes Docker); armazenados separadamente; retenção automática |
| F04 SSH hardening | ✅ Aplicado | `PermitRootLogin prohibit-password` + `PasswordAuthentication no` |

---

## Domínios Registrados

- orbis.tax (principal)
- tribus-ai.com.br
- tribus-ia.com.br
