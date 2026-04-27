# Skill: Nova Feature

## Processo Obrigatório (5 passos)

1. **Ler ARCHITECTURE.md** — sem exceção
2. **Copiar TASKS_TEMPLATE.md → TASKS_[nome].md** e preencher
3. **Declarar escopo** antes de codar:
   - Arquivos que serão CRIADOS: [lista explícita]
   - Arquivos que serão MODIFICADOS: [lista explícita + seção]
   - Arquivos que NÃO devem ser tocados: [lista explícita]
4. **Apresentar ao PO** para aprovação
5. **Só então iniciar implementação**

## Checklist por Arquivo

- [ ] Leu o arquivo completo antes de modificar
- [ ] Tem migration SQL se toca o banco
- [ ] Tem `tests/unit/test_[modulo].py` se novo módulo Python
- [ ] Frontend usa `text-foreground`/`text-muted-foreground` (nunca `style={{ color: "#..."}})`)
- [ ] `useSearchParams()` envolto em `<Suspense>` se presente

## Sinais de Alerta — Parar e Reportar ao PO

- Arquivo fora do escopo declarado precisando ser tocado
- Suite de testes com regressão sem solução óbvia
- Dúvida se decisão impacta ARCHITECTURE.md
- Operação irreversível no banco (DROP, DELETE sem WHERE)
- Necessidade de nova dependência

## Após Implementar

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
bash scripts/pre_deploy_check.sh
```
