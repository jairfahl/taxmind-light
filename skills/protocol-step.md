# Skill: Alterar Protocolo P1→P6

## Regras Absolutas

- **6 passos — imutável.** Nunca adicionar P7/P8/P9
- **P4 e P5 são 100% humanos.** Nunca automatizar `hipotese_gestor` ou `decisao_final`
- **Qualquer mudança no schema de `cases` ou `case_steps` exige migration SQL**

## Arquivos do Protocolo

| Arquivo | Responsabilidade |
|---------|-----------------|
| `src/protocol/engine.py` | Lógica de criação e avanço de passos |
| `src/protocol/carimbo.py` | Carimbo de terceirização cognitiva |
| `src/cognitive/monitoramento_p6.py` | Ciclo pós-decisão P6 |
| `src/cognitive/aprendizado_institucional.py` | Extração de heurísticas |

## Campos Protegidos (nunca automatizar)

```python
# case_steps onde passo=4 ou passo=5:
hipotese_gestor: str  # Preenchido pelo gestor — mínimo 1 char
decisao_final: str    # Preenchido pelo gestor
```

## Teste de Linter Após Modificação

```bash
.venv/bin/python -m pytest tests/linters/test_p4_guard.py -v
.venv/bin/python -m pytest tests/integration/test_protocol_endpoints.py -v
```

## Campos Obrigatórios ao Criar Case

P1 exige `premissas` com mínimo 1 item. A API valida via Pydantic — `min_length=1` em `hipotese_gestor` e `decisao_final` em seus respectivos passos.

## P6 — Monitoramento Pós-Decisão

- Ativo quando `monitoramento_ativo=true` em `case_steps[6]`
- Verificação periódica via `monitoramento_p6.py`
- Frontend exibe alertas de drift ativos via `GET /v1/observability/drift`
- Heurísticas expiram com 6 meses — tabela `heuristicas`
