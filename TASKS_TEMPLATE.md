# TASKS — [Nome da Feature / RDM-XXX]
**Data:** AAAA-MM-DD
**Responsável:** PO (Jair)
**Status:** [ ] Planejado | [ ] Em execução | [ ] Concluído | [ ] Bloqueado

---

## 1. Descrição

[Descrever em 2–3 linhas o que esta feature entrega e qual problema resolve.]

---

## 2. Gate de entrada

Condições que devem ser verdadeiras ANTES de iniciar:

```
[ ] ARCHITECTURE.md lido
[ ] [Pré-requisito 1]
[ ] [Pré-requisito 2]
[ ] Suite de testes passando: pytest tests/ → X testes OK
```

---

## 3. Escopo de arquivos

### Arquivos que serão CRIADOS
```
- migrations/NNN_descricao.sql
- src/[domínio]/[modulo].py
- tests/unit/test_[modulo].py
```

### Arquivos que serão MODIFICADOS
```
- [arquivo.py] → [seção ou função específica]
- [arquivo.py] → [seção ou função específica]
```

### Arquivos que NÃO devem ser tocados
```
- [arquivo.py] — motivo
- [arquivo.py] — motivo
```

> Se durante a execução surgir necessidade de tocar arquivo fora deste escopo:
> PARAR e reportar ao PO antes de prosseguir.

---

## 4. Ordem de execução dos prompts

```
1. [PROMPT_XXX_01_nome.md] — [o que faz]
2. [PROMPT_XXX_02_nome.md] — [o que faz]
3. [PROMPT_XXX_03_nome.md] — [o que faz]
```

---

## 5. Critérios de aceite da feature completa

```
[ ] [Critério funcional 1]
[ ] [Critério funcional 2]
[ ] [Critério de segurança]
[ ] pytest tests/ — suite completa sem regressão
[ ] ARCHITECTURE.md atualizado se necessário
```

---

## 6. Registro de execução

| Step | Prompt | Status | Observações |
|---|---|---|---|
| 1 | PROMPT_XXX_01 | | |
| 2 | PROMPT_XXX_02 | | |

---

## 7. Decisões tomadas durante execução

[Registrar aqui qualquer desvio do plano, decisão tomada em campo, ou descoberta
que impacte o ARCHITECTURE.md ou próximas features.]
