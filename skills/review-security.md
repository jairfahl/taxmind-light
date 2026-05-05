# Skill: Revisão de Segurança

Executar antes de qualquer deploy. Tempo estimado: 15–20 min.

## 7 Findings de Referência (Sprint Segurança — Abril 2026)

| ID | Finding | Status | Arquivo |
|----|---------|--------|---------|
| SEC-F02 | RLS nas tabelas principais | ✅ Remediado | migrations/133+134 |
| SEC-F03 | Credenciais hardcoded | ✅ Remediado | docker-compose.yml usa `${DOCKER_DATABASE_URL}` |
| SEC-F04 | SSH hardening no VPS | ✅ Remediado | PermitRootLogin prohibit-password |
| SEC-F07 | Prompt injection (OWASP LLM01) | ✅ Remediado | `src/security/prompt_sanitizer.py` |
| SEC-F09 | CI/CD GitHub Actions | ✅ Remediado | `.github/workflows/security.yml` |
| SEC-F11 | CSP Enforce ativo | ✅ Remediado | `nginx.conf` (era Report-Only) |
| SEC-F14 | Swagger desabilitado em prod | ✅ Remediado | `docs_url=None` quando `ENV != dev` |

## Checklist de Revisão

### 1. Credenciais Hardcoded
```bash
grep -r "password\|secret\|api_key\|API_KEY" src/ --include="*.py" | grep -v "os.getenv\|os.environ\|getenv\|#"
grep -r "sk-\|voyage-\|resend_\|asaas_" src/ --include="*.py"
```
Resultado esperado: vazio. Qualquer hit = bloqueio.

### 2. RLS em Tabelas Novas
- Nova tabela com dados de tenant → migration com RLS policy obrigatória
- Padrão: `CREATE POLICY ... USING (tenant_id = app_tenant_id())`
- Referência: `migrations/133_rls_users_cases.sql`, `migrations/134_rls_api_usage.sql`

### 3. Prompt Injection
- Qualquer novo campo de input do usuário que vai para LLM → deve passar por `prompt_sanitizer.sanitize()`
- Verificar: `from src.security.prompt_sanitizer import sanitize`
- Adicionar caso adversarial em `tests/unit/test_prompt_sanitizer.py`

### 4. CORS / Origens
```bash
grep -n "allow_origins\|CORSMiddleware" src/api/main.py
```
Esperado: lista explícita de origens (não `["*"]` em prod).

### 5. Rate Limiting
- Novo endpoint core → `@limiter.limit("N/minute")` + `request: Request`
- Verificar se limite está razoável para o caso de uso

### 6. .env não versionado
```bash
git status | grep -E "\.env|\.env\.prod|\.env\.local"
git diff --cached | grep -E "ANTHROPIC|VOYAGE|ASAAS|RESEND"
```
Resultado esperado: vazio.

### 7. Swagger em Produção
```bash
grep -n "docs_url\|redoc_url" src/api/main.py
```
Esperado: `docs_url=None if ENV != "dev" else "/docs"` (ou similar).

## Ferramentas Automatizadas

```bash
# SAST — detecta padrões inseguros no código Python
.venv/bin/bandit -r src/ -ll

# Dependências com CVEs conhecidos
.venv/bin/pip-audit

# CI equivalente
# ver .github/workflows/security.yml
```

## Pós-Revisão

- [ ] Novo finding → documentar em `LESSONS_LEARNED.md`
- [ ] Finding mecanicamente verificável → criar linter em `tests/linters/` (ver `docs/FEEDBACK_LOOP.md`)
- [ ] Atualizar ARCHITECTURE.md §9 (Segurança) se mudança estrutural
