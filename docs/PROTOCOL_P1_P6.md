# Protocolo de Decisão P1→P6

## Os 6 Passos — Imutáveis

| Passo | Nome | Natureza | Responsável |
|-------|------|----------|-------------|
| P1 | Registrar & Classificar | Automático (LLM + SPD) | Sistema |
| P2 | Estruturar | Automático | Sistema |
| P3 | Analisar | Automático (RAG + LLM) | Sistema |
| P4 | Hipotetizar | **100% humano** | Gestor |
| P5 | Decidir | **100% humano** | Gestor |
| P6 | Ciclo Pós-Decisão | Misto | Sistema + Gestor |

**P7, P8, P9 não existem.** Qualquer referência a eles é erro da fase de design (protocolo foi de 9→6 passos na consolidação).

---

## Nota Histórica: Consolidação 9→6

O protocolo original tinha 9 passos. Em consolidação arquitetural (Onda B), P7/P8/P9 foram fundidos em P6 (Ciclo Pós-Decisão). Referências históricas a "P7", "P8", "P9" em `LESSONS_LEARNED.md` são corretas — não alterar.

Decisão registrada em `ARCHITECTURE.md §10`: "Protocolo 9→6 passos | ✅ Consolidado | P7/P8/P9 fundidos em P6".

---

## Campos Obrigatórios por Passo

### P1 — Registrar & Classificar
- `titulo`: string (obrigatório)
- `descricao`: string (obrigatório)
- `premissas`: list[str] (obrigatório — mínimo 1 premissa)
- `tipo_query`: FACTUAL | INTERPRETATIVA | COMPARATIVA (classificado pelo SPD)

### P2 — Estruturar
- `estrutura`: dict com perguntas de esclarecimento

### P3 — Analisar
- `analise_rag`: resultado do pipeline cognitivo
- `fundamento_legal`: lista de artigos (não pode ser vazia)

### P4 — Hipotetizar (HUMANO)
- `hipotese_gestor`: string (min_length=1) — **preenchido pelo gestor, nunca pelo LLM**

### P5 — Decidir (HUMANO)
- `decisao_final`: string — **preenchido pelo gestor, nunca pelo LLM**

### P6 — Ciclo Pós-Decisão
- `monitoramento_ativo`: bool
- `revisao_em`: date
- `heuristicas_extraidas`: list[str]

---

## P4 Guard Rail

**Invariante crítica:** `hipotese_gestor` e `decisao_final` NUNCA podem ser populados por output de LLM.

Teste de linter: `tests/linters/test_p4_guard.py` — scan AST de `src/` verifica que nenhum assignment de `hipotese_gestor` usa retorno de `analisar()`, `_chamar_llm()` ou `anthropic.`.

---

## Módulos do Protocolo

| Componente | Arquivo |
|-----------|---------|
| Engine do protocolo | `src/protocol/engine.py` |
| Carimbo de alerta | `src/protocol/carimbo.py` |
| Monitoramento P6 | `src/cognitive/monitoramento_p6.py` |
| Aprendizado institucional | `src/cognitive/aprendizado_institucional.py` |

---

## Endpoints

| Ação | Endpoint |
|------|----------|
| Criar case | `POST /v1/protocol/cases` |
| Avançar passo | `POST /v1/protocol/cases/{id}/steps` |
| Monitoramento P6 | `GET /v1/protocol/cases/{id}/monitoring` |
| Heurísticas | `GET /v1/protocol/heuristicas` |

---

## Carimbo de Terceirização Cognitiva

Alerta disparado quando o sistema detecta que o usuário está delegando ao LLM decisões que deveriam ser humanas (P4/P5). Módulo: `src/protocol/carimbo.py`. Tabela: `carimbo_alerts`.
