# Modelo de Dados e Fronteiras — Orbis.tax

## Isolamento Multi-Tenant

**A unidade de isolamento é o TENANT (CNPJ), não o usuário individual.**

- Um tenant pode ter N usuários; todos compartilham os mesmos cases, documentos e limites.
- **Nunca filtrar** dados de negócio por `user_id` diretamente — sempre resolver para `tenant_id` primeiro.
- Padrão obrigatório:

```python
tenant_id = _get_tenant_info_by_user(user_id, conn)["tenant_id"]
# ... então usar tenant_id no WHERE
```

- **Exceção permitida:** logs de auditoria (`ai_interactions`, `case_state_history`) registram `user_id` para rastreabilidade individual.
- `ai_interactions` **não tem `tenant_id`** — para joins por tenant: `JOIN users u ON u.id = ai.user_id WHERE u.tenant_id = ?`

---

## LGPD

| Requisito | Implementação |
|-----------|---------------|
| Consentimento | `users.lgpd_consent` (boolean + timestamp) |
| Finalidade | Tabela `tenants.tipo_negocio` + onboarding |
| Portabilidade | Export CSV em `/admin/mailing` |
| Exclusão | Não implementado (roadmap) |
| DPO | Jair Fahl — admin@orbis.tax |

---

## Pseudonimização

- Dados de análise armazenados por `tenant_id` (CNPJ hash)
- Logs de LLM em `ai_interactions` com `user_id` — sem PII no conteúdo
- Tokens JWT com expiração — sem session permanente

---

## Legal Hold

Outputs podem ser colocados em **Legal Hold** — protegem documentos contra exclusão por retenção regulatória.

| Componente | Arquivo | Tabelas |
|-----------|---------|---------|
| Módulo | `src/outputs/legal_hold.py` | `outputs.legal_hold`, `legal_hold_log` |
| Ativação | `POST /v1/outputs/{id}/legal-hold` | `legal_hold_log` |
| Auditoria | `GET /v1/outputs/{id}/legal-hold/history` | `legal_hold_log` |

**Regra:** output com `legal_hold=true` não pode ser deletado. Tentativa de deleção retorna 403.

---

## Planos e Billing

| Campo | Tabela | Descrição |
|-------|--------|-----------|
| `plano` | `tenants` | starter / pro / enterprise |
| `trial_expira_em` | `tenants` | Data de expiração do trial |
| `status_pagamento` | `tenants` | active / trial / past_due / cancelled |
| `desconto_percentual` | `tenants` | Desconto aplicado (migration 124) |
| `cancel_reason` | `tenants` | Motivo de cancelamento (migration 127) |

---

## Secrets e Variáveis de Ambiente

| Variável | Uso | Observação |
|----------|-----|-----------|
| `DATABASE_URL` | Conexão PostgreSQL | Nunca hardcoded |
| `JWT_SECRET` | Assinatura tokens | Sem fallback — RuntimeError se ausente |
| `ANTHROPIC_API_KEY` | Claude API | Prefixo `sk-ant-` |
| `VOYAGE_API_KEY` | Embeddings | Prefixo `pa-` |
| `RESEND_API_KEY` | E-mail transacional | Obrigatória para cadastro |
| `ASAAS_API_KEY` | Billing | `.env.prod` deve usar `$$` no lugar de `$` |
| `LOCKFILE_MODE` | Integridade de prompts | Valores válidos: `WARN` ou `BLOCK` |
