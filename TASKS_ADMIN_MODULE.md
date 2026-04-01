# TASKS — Admin & User Management Module
**Data:** 2026-04
**Responsável:** PO (Jair)
**Status:** [x] Concluído

---

## 1. Descrição

Módulo de autenticação e gestão de usuários com dois perfis (ADMIN e USER).
Inclui login com JWT/bcrypt, banner de trial de 30 dias, painel admin com
gestão de usuários e monitoramento de consumo de API (custo estimado em USD).
Nenhuma funcionalidade existente do protocolo P1→P6 foi alterada.

---

## 2. Gate de entrada

```
[x] ARCHITECTURE.md lido
[x] Migration 100 disponível para execução
[x] Suite de testes passando antes da implementação
```

---

## 3. Escopo de arquivos

### Arquivos CRIADOS
```
- migrations/100_users_table.sql     ← tabela users + user_id em ai_interactions
- auth.py                            ← JWT, bcrypt, autenticação completa
- pages/login.py                     ← tela de login Streamlit
- components/trial_banner.py         ← banner de trial com contagem regressiva
- admin.py                           ← painel admin (usuários + consumo API)
- tests/test_auth.py                 ← 19 testes de autenticação e isolamento
```

### Arquivos MODIFICADOS
```
- ui/app.py → guard de sessão no início + aba "⚙️ Admin" condicional para ADMIN
- migrations/100_users_table.sql → colunas input_tokens + output_tokens em ai_interactions
- src/cognitive/engine.py → INSERT em ai_interactions inclui user_id + param user_id em analisar()
- src/api/main.py → AnalyzeRequest e GerarOutputRequest recebem user_id; repassado ao engine
```

### Arquivos que NÃO foram tocados
```
- src/rag/*.py — pipeline RAG inalterado
- src/integrity/lockfile_manager.py — inalterado
- src/outputs/ — inalterado
- src/protocol/ — inalterado
- Specs ESP-*.docx — inalterados
```

---

## 4. Ordem de execução dos prompts

```
1. PROMPT_ADMIN_01_MIGRATION.md          ← tabela users + migration 100
2. PROMPT_ADMIN_02_AUTH.md               ← auth.py completo
3. PROMPT_ADMIN_03_LOGIN_BANNER.md       ← login.py + trial_banner.py
4. PROMPT_ADMIN_04_APP_GUARD.md          ← guard de sessão em ui/app.py
5. PROMPT_ADMIN_05_PAINEL_USUARIOS.md    ← admin.py Seção A (gestão de usuários)
6. PROMPT_ADMIN_06_CONSUMO_API.md        ← admin.py Seção B (consumo de API)
7. PROMPT_ADMIN_07_ISOLAMENTO_TESTES.md  ← isolamento tenant + tests/test_auth.py
```

---

## 5. Critérios de aceite

```
[x] Login com email + senha funcional
[x] JWT com expiração de 8 horas
[x] Banner de trial visível após login com contagem regressiva
[x] Trial expirado bloqueia acesso com st.stop()
[x] Aba "⚙️ Admin" visível apenas para perfil ADMIN
[x] Gestão de usuários: criar, ativar, desativar, redefinir senha
[x] Monitoramento de consumo: tokens + custo estimado USD por usuário
[x] USER não acessa dados de outro usuário (isolamento de tenant via user_id)
[x] pytest tests/test_auth.py → 19 testes passando
[x] pytest tests/ → suite completa sem regressão (354 passed)
[x] ARCHITECTURE.md criado e atualizado
```

---

## 6. Registro de execução

| Step | Prompt | Status | Observações |
|---|---|---|---|
| 1 | PROMPT_ADMIN_01_MIGRATION | ✅ | Admin padrão: admin@tribus-ai.com.br / hash bcrypt regenerado |
| 2 | PROMPT_ADMIN_02_AUTH | ✅ | JWT_SECRET via os.getenv; 5/5 testes de verificação OK |
| 3 | PROMPT_ADMIN_03_LOGIN_BANNER | ✅ | Arquivos já existiam do Step 01; validados |
| 4 | PROMPT_ADMIN_04_APP_GUARD | ✅ | ui/app.py (não app.py na raiz); tabs com 4+1 abas |
| 5 | PROMPT_ADMIN_05_PAINEL_USUARIOS | ✅ | 10/10 testes de verificação OK |
| 6 | PROMPT_ADMIN_06_CONSUMO_API | ✅ | Colunas input_tokens/output_tokens não existiam — adicionadas via migration |
| 7 | PROMPT_ADMIN_07_ISOLAMENTO_TESTES | ✅ | 19/19 testes; 354 passed suite completa |

---

## 7. Decisões tomadas durante execução

- `primeiro_uso` registrado no primeiro login (não no cadastro) — dispara timer real de uso
- Admin não pode desativar a si mesmo — proteção implementada em admin.py
- Saldo real Anthropic não acessível via API — painel exibe estimativa por tokens registrados
- `user_id` nullable em `ai_interactions` — não quebra registros históricos anteriores
- Preços de referência como constantes em admin.py — atualizar manualmente se mudarem
- Entry point correto é `ui/app.py`, não `app.py` na raiz — os prompts tinham caminho errado
- Hash bcrypt do prompt original era inválido — regenerado durante Step 01
- Colunas `input_tokens`/`output_tokens` não existiam em `ai_interactions` — adicionadas no Step 06
