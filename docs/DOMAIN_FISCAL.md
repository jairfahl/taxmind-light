# Domínio Fiscal — Orbis.tax

## Identidade do Sistema

Orbis.tax é um sistema RAG de apoio à **decisão tributária** focado na Reforma Tributária brasileira.

**Não é:** calculadora de tributos, ERP, gerador de obrigações acessórias.
**É:** sistema de apoio à decisão com protocolo de 6 passos (P1→P6) e base jurídica auditável.

---

## Normas Base (Corpus Fechado)

| Norma | Descrição |
|-------|-----------|
| EC 132/2023 | Emenda Constitucional — reforma do sistema tributário brasileiro |
| LC 214/2025 | Lei Complementar — IBS (Imposto sobre Bens e Serviços) e CBS |
| LC 227/2026 | Lei Complementar — complementações e ajustes |

**Regra:** "Adicionar Norma" é exclusivo para normas não presentes na base. EC/LC acima nunca devem ser resubmetidas.

---

## Taxonomia de Tributos da Reforma

| Tributo | Descrição | Competência |
|---------|-----------|-------------|
| IBS | Imposto sobre Bens e Serviços | Estados + Municípios |
| CBS | Contribuição sobre Bens e Serviços | União |
| IS | Imposto Seletivo | União |
| IPI | Imposto sobre Produtos Industrializados | Legado / transição |

**Fato gerador:** operação com bens e serviços (IBS/CBS); consumo de bens prejudiciais (IS).
**SPED:** Sistema Público de Escrituração Digital — obrigação acessória relevante para CBS.

---

## Hierarquia de Fontes

1. Constituição Federal (EC 132/2023)
2. Leis Complementares (LC 214/2025, LC 227/2026)
3. Regulamentações (instruções normativas, portarias)
4. Jurisprudência (STF, STJ — DOU/CGIBS)

---

## PTF — Principio Temporal Fiscal

Toda consulta deve considerar vigência das normas. O sistema extrai `data_referencia` da query e filtra chunks por `vigencia_inicio` e `vigencia_fim`. Consultas sem data explícita usam a data atual.

Módulo: `src/rag/ptf.py` — `extrair_data_referencia()`, `resolver_vigencia()`

---

## Terminologia Obrigatória em Respostas

Ao gerar hipóteses ou análises, o modelo DEVE usar:
- IBS/CBS (não "novo imposto")
- fato gerador (não "incidência" sozinho)
- artigo X da LC 214/2025 (não apenas "a lei diz")
- vigência (datas de início/fim da norma)

---

## Escopo de Consultas

**Dentro do escopo:** qualquer questão sobre IBS, CBS, IS, transição tributária, obrigações acessórias SPED, créditos de IBS/CBS, regimes especiais, operações entre estados.

**Fora do escopo:** IRPJ, CSLL, tributos municipais não relacionados à reforma, planejamento fiscal pré-EC 132.

Consultas fora do escopo retornam HTTP 400 com mensagem amigável — não devem ser respondidas com "não sei".
