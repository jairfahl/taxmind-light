# Skill: Nova Migration SQL

## Convenções

- **Formato:** `migrations/NNN_descricao.sql` (NNN = número sequencial de 3 dígitos)
- **Última migration:** `127_churn_email_tracking.sql` → próxima: `128_...`
- **Regra absoluta:** qualquer ALTER TABLE no banco DEVE ter arquivo migration correspondente

## Passos

```bash
# 1. Verificar última migration
ls migrations/ | sort | tail -5

# 2. Criar arquivo migration
# migrations/128_descricao.sql

# 3. Verificar tabela existente antes de FK
docker exec tribus-ai-db psql -U taxmind -d taxmind_db -c "\d <tabela>"

# 4. Executar migration
docker exec -i tribus-ai-db \
    psql -U taxmind -d taxmind_db \
    < migrations/128_descricao.sql

# 5. Verificar aplicação
docker exec tribus-ai-db psql -U taxmind -d taxmind_db -c "\d <tabela_alterada>"

# 6. Commitar o arquivo de migration
git add migrations/128_descricao.sql
git commit -m "feat: migration 128 — descricao"
```

## Armadilhas Conhecidas

- `cases.id` e `outputs.id` são **UUID** (não integer) — migration 126
- `tipo_atuacao` é VARCHAR(100) — migration 122 (era VARCHAR(20), bug silencioso)
- Não usar `CASCADE` em DELETE sem aprovação do PO
- `ai_interactions` não tem `tenant_id` — joins por tenant passam por `users`

## Atualizar CLAUDE.md e ARCHITECTURE.md

Após nova migration, atualizar:
- `ARCHITECTURE.md §7` — descrição da tabela se nova
- `docs/SCHEMA_REFERENCE.md` — linha da tabela
- `CLAUDE.md` — "Última migration:" no estado atual
