# LESSONS_LEARNED.md
# Tribus-AI — Lições Aprendidas
**Versão:** 1.0
**Atualizado em:** Abril 2026
**Autor:** PO (Jair Fahl) + Claude
**Localização:** `/Users/jairfahl/Downloads/tribus-ai-light/LESSONS_LEARNED.md`

> **Como usar este arquivo:**
> Consultar antes de decisões arquiteturais, antes de deploys em produção,
> e ao iniciar qualquer nova feature relevante.
> Atualizar imediatamente após qualquer incidente ou decisão que gere aprendizado.
> Este documento não duplica o CLAUDE.md — captura o *porquê* das regras, não as regras em si.

---

## 1. GOVERNANÇA DE PRODUTO

### ✅ O que funciona

**Conceito antes de código — sem exceção.**
Toda vez que a implementação precedeu a especificação, houve retrabalho inevitável.
A regra "somente após termos os conceitos melhor estruturados" não é preferência pessoal —
é a política que evita desperdício de ciclos de Claude Code e de tokens.

**Decisões que desviam do score precisam de registro explícito.**
DEC-08 (MAU vs. Fixo) e DEC-09 são exemplos corretos: o desvio do score está documentado
com justificativa. Isso é rastreabilidade real.
Decisões sem registro viram "achei que era assim" — e esse "achei" custa caro.

**Versão semântica para documentos.**
Mudança estrutural (persona, arquitetura, fluxo) → bump de major (v7 → v8).
Mudança aditiva (novo campo, nova seção) → bump de minor (v7 → v7.1).
Ignorar isso gera confusão sobre o que mudou e por quê.

### ❌ O que causou problemas

**Discrepância de numeração P1→P6 vs P1→P9.**
O protocolo oscilou entre 6 e 9 passos por meses. ESP-07 tinha `CHECK (1-9)`.
ESP-15 mencionava "wizard de 9 passos". A UI implementava P1→P6.
Três documentos, três realidades.
Custo: inconsistência em testes, confusão em casos de uso, debate recorrente em cada sessão.
**Regra derivada:** toda referência a número de passos do protocolo deve ser verificada
em DC, ESP-07 e ESP-15 antes de qualquer implementação. A versão canônica é P1→P6.

**Débito conceitual não resolvido cresce — nunca some.**
Itens deixados como "resolver depois" em decisões de produto acumulam
como juros compostos: cada sessão nova os toca, ninguém os fecha.
**Regra derivada:** todo item com status "pendente" em sessão de conceituação
recebe um responsável e uma data. Sem data, não existe.

---

## 2. GOVERNANÇA DO CORPUS

### ✅ O que funciona

**Normas revogadas nunca deletar.**
O PTF depende de `vigencia_fim` para filtrar temporalmente.
Deletar normas revogadas quebra consultas retrospectivas — erro silencioso,
difícil de diagnosticar, impossível de reverter sem backup.
Marcar sempre com `vigencia_fim`. Jamais DELETE.

**Metadados obrigatórios antes da indexação.**
Sem `vigencia_inicio`, `regime`, `grau_consolidacao` corretos,
o PTF funciona com dados incorretos e o sistema entrega análise errada com confiança alta.
Pior que não responder.

### ❌ O que causou problemas

**Corpus Manager sem responsável definido é risco estrutural, não operacional.**
O PO como Corpus Manager provisional funciona até ~20 usuários.
A partir daí, é gargalo de produto. 53 normas tributárias por dia útil.
Sem curadoria ativa, o maior risco do produto não é técnico.
**Regra derivada:** quando o produto atingir 10 clientes pagantes,
iniciar processo de designação ou contratação de Corpus Manager.
Esse gatilho está no CORPUS_GOVERNANCE.md — não mover sem atualizar os dois arquivos.

**Corpus desatualizado com confiança alta é pior que corpus vazio.**
O sistema entrega respostas com badge "Consolidado" sobre normas desatualizadas.
O usuário não sabe que está errado — acredita e decide.
**Regra derivada:** a rotina semanal do Corpus Manager não é opcional mesmo durante
períodos de desenvolvimento intenso. 2h por semana. Sem exceção.

---

## 3. ARQUITETURA E ENGENHARIA

### ✅ O que funciona

**Diagnóstico antes de correção — sempre.**
O episódio da aba Consultar vs. Protocolo de Decisão é o exemplo mais claro.
A tentação de "provavelmente é X" foi resistida — um prompt de diagnóstico foi gerado
antes de qualquer fix. Isso precisa ser norma, não exceção.
**Regra derivada:** toda inconsistência de comportamento gera um prompt de diagnóstico
antes de qualquer alteração de código. Exceção zero.

**Connection pool centralizado.**
Antes do pool unificado (pós-auditoria), cada função abria e fechava conexão.
Sob carga, isso gerava timeout e comportamento errático.
O pool em `src/db/pool.py` é a única fonte de conexões — nunca instanciar `psycopg2.connect`
diretamente nas camadas de negócio.

**Ferramentas RAG avançadas são mutuamente exclusivas.**
Multi-Query, Step-Back e HyDE operam em paralelo causa resultados não-determinísticos
e consumo de tokens não-controlado. A flag `_tool_activated` em `engine.py` é
uma restrição de arquitetura — nunca remover.

### ❌ O que causou problemas

**Migrations sem verificação de dependência geram erro silencioso em runtime.**
O episódio `mau_records` antes de `tenants` existir: FK sem referência passa na migration
e só falha em operação real. O sistema sobe, parece ok, falha em produção.
**Regra derivada:** antes de qualquer migration que cria FK, verificar se a tabela-pai existe
com `\d <tabela>` no container. Sequência obrigatória no TASKS antes de qualquer migration.

**BYPASS_AUTH é faca de dois gumes.**
Viabilizou testes sem fricção. Criou dependências ocultas (UUID hardcoded, FK violation,
lógica de trial sem efeito) que custaram tempo na ativação de produção.
**Regra derivada:** SEC-09 (BYPASS_AUTH=False) é pré-requisito para qualquer usuário
real com dados reais no sistema. Não negociável. Não postergar após o lançamento.

**Variáveis de ambiente com caracteres especiais quebram o docker compose silenciosamente.**
`$` em valores de `.env.prod` é interpretado como variável pelo docker compose.
`ASAAS_API_KEY=$aact_...` vira string vazia. Solução: `$$aact_...`.
**Regra derivada:** todo `.env.prod.example` deve ter este comentário nas linhas com `$`:
`# ATENÇÃO: se o valor começa com $, usar $$ no arquivo .env.prod (escape docker compose)`

**`LOCKFILE_MODE=ENFORCE` não é valor válido — levanta ValueError no boot.**
O Python falha ao importar o módulo. A API não sobe. O nginx retorna 502.
O browser não diz nada sobre o enum.
**Regra derivada:** validar todas as variáveis de ambiente críticas no startup com
`if LOCKFILE_MODE not in ("WARN", "BLOCK"): raise ValueError(...)`.
Mensagem de erro explícita no boot vale mais que horas de debug.

---

## 4. DEPLOY E INFRAESTRUTURA

### ✅ O que funciona

**Scripts são superiores a comandos manuais em produção.**
`redeploy.sh`, `fix_hash.py` — cada script criado reduziu chance de erro humano.
Todo procedimento repetível vira script versionado no repositório. Sem exceção.

**SCP para transferir secrets — nunca copy-paste de terminal.**
Heredoc quebra linhas. Nano via SSH tem comportamento errático.
Copy-paste de terminal SSH gera erros de caractere invisível.
O arquivo é criado localmente (onde o editor é confiável), SCP para o servidor.

**`--env-file` e `env_file:` são mecanismos distintos.**
`env_file: .env.prod` → injeta variáveis dentro do container (runtime).
`--env-file .env.prod` → resolve interpolação `${VAR}` no próprio compose file (parse time).
Sem `--env-file`, variáveis como `${POSTGRES_PASSWORD}` ficam em branco silenciosamente.
O sistema sobe e parece ok até falhar em runtime.

### ❌ O que causou problemas

**`git status` antes de qualquer deploy não era regra — deveria ser.**
Arquivos críticos do frontend nunca foram commitados. O VPS recebeu app incompleto via git pull.
O login funcionava mas redirecionava para rota inexistente — causando o comportamento
"pisca e limpa" que tomou horas para diagnosticar.
**Regra derivada:** checklist pré-deploy:
```
[ ] git status: zero arquivos ?? (untracked) relevantes
[ ] git log --oneline -5: confirmar que o commit esperado está no topo
[ ] npm run build: zero erros antes de push
[ ] pytest tests/ -q: zero regressões antes de push
```

**`docker compose restart` não relê `env_file`.**
Só `up -d --force-recreate` recria o container com variáveis corretas.
**Regra derivada:** após qualquer alteração de `.env.prod` no VPS:
`docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate`
Nunca usar `restart` para mudança de variável de ambiente.

**O volume `taxmind_pgdata` é o ativo mais crítico — sem backup é risco existencial.**
Contém todos os embeddings e o histórico de decisões dos clientes.
**Regra derivada:** backup automatizado via `pg_dump` para storage externo é
pré-requisito para o primeiro cliente pagante. Não após. Antes.

**"Funciona local" não significa "está commitado".**
O ambiente local pode ter arquivos que nunca passaram pelo git.
O VPS só tem o que está no repositório.
**Regra derivada:** antes de qualquer deploy relevante, testar a partir de um clone limpo
em diretório separado: `git clone <repo> /tmp/test-deploy && cd /tmp/test-deploy && npm run build`.

---

## 5. DEBUGGING E DIAGNÓSTICO

### ✅ O que funciona

**Testar camadas de forma isolada, de dentro para fora.**
A ordem correta em sistemas em camadas:
1. DB → `psql` direto, verificar dados e schema
2. API → `curl` direto no container, sem nginx
3. nginx → verificar `access.log`, testar proxy isolado
4. Frontend → DevTools Network, verificar requests e status codes

Pular etapas multiplica o tempo de diagnóstico.

**DevTools Network antes de qualquer especulação sobre auth.**
Ao debugar problema de login: abrir aba Network antes de qualquer outra coisa.
Status code exato (401, 404, 500, 502) elimina horas de especulação.

### ❌ O que causou problemas

**"Pisca e limpa" em SPA React tem causa específica, não é bug misterioso.**
Indica: (a) redirect programático após o request, ou (b) reload de página.
Ambos têm causas rastreáveis. Diagnosticar com Network tab, não com especulação.

**Interceptors globais de axios sem guard causam loop.**
O interceptor de 401 que redirecionava para `/login` mesmo quando já estava em `/login`
causou horas de confusão.
**Regra derivada:** todo interceptor de status code deve ter guard:
```typescript
if (error.response?.status === 401 && !window.location.pathname.includes('/login')) {
  router.push('/login');
}
```

**Erros de enum no boot geram 502 no nginx sem mensagem clara.**
Python levanta `ValueError` ao importar módulo com enum inválido.
API não sobe. nginx retorna 502. Nada indica o enum.
**Regra derivada:** `docker compose logs api --tail 50` é o **primeiro** comando
após qualquer 502. Sempre. Antes de tocar nginx, antes de tocar qualquer outra coisa.

---

## 6. PROCESSO DE TRABALHO COM CLAUDE CODE

### ✅ O que funciona

**Prompts estruturados em markdown com critérios de aceite reduzem retrabalho.**
Prompts com: contexto, ações numeradas, verificação, critérios de aceite binários
permitem que o Claude Code execute sem ambiguidade e que o PO valide sem interpretação.
Sem critérios de aceite, a entrega é subjetiva.

**Shorthand funciona, mas contexto entre sessões não é automático.**
"prox prompt", "idem", "ok" — o ritmo de trabalho é eficiente.
Mas cada chat começa do zero internamente.
O CLAUDE.md e o CORPUS_GOVERNANCE.md existem precisamente para resolver isso.
Mantê-los atualizados é tão importante quanto o código.

**"Não consigo verificar isso" vale mais que uma resposta fluente errada.**
Claude afirmou que o Roadmap estava indisponível quando estava presente no projeto.
Custo: trabalho baseado em premissa falsa.
**Regra derivada:** antes de afirmar que um arquivo está ausente, perguntar.
Antes de afirmar qualquer conteúdo de arquivo, ler o arquivo.

### ❌ O que causou problemas

**Prompts com mais de 300 linhas aumentam risco de alucinação e desvio de escopo.**
Claude Code se perde em prompts longos — começa a inferir, extrapola escopo,
gera código não solicitado.
**Regra derivada:** máximo 300 linhas por prompt. Um entregável por prompt.
Se o escopo exige mais, quebrar em sequência numerada.

**Inferência sem verificação gera trabalho baseado em premissa falsa.**
Claude não deve — e não vai — afirmar conteúdo de arquivo sem tê-lo lido.
Qualquer afirmação sobre estado do código, schema do banco, ou conteúdo de documento
deve ser precedida de leitura direta.

---

## 7. SEGURANÇA

### ✅ O que funciona

**JWT sem fallback para modo permissivo.**
A auditoria SEC-02 eliminou o padrão "se JWT falhar, aceitar sem auth".
Sem fallback, a segurança não degrada silenciosamente.

**Rate limit (slowapi) e validação de MIME no upload.**
SEC-06 e SEC-07 eliminaram dois vetores de abuso sem custo operacional relevante.
Implementar cedo é mais barato que remediar após incidente.

### ❌ O que causou problemas

**Credenciais reais transitaram pelo chat durante sessão de debug.**
O `.env.prod` foi preenchido com valores reais através do chat.
**Regra derivada:** credenciais nunca transitam por canal de chat, e-mail ou log.
Fluxo correto: criar arquivo localmente → SCP para VPS.
Após qualquer exposição suspeita: rotacionar imediatamente.

**SEC-09 (BYPASS_AUTH=False) foi postergado — não pode ser.**
Auth bypass em produção com dados reais é risco crítico e inaceitável.
**Regra derivada:** SEC-09 é pré-condição para o primeiro usuário real.
Não existe "lançar e ativar depois". Ativar antes do lançamento.

---

## 8. DECISÕES ARQUITETURAIS QUE NÃO DEVEM SER QUESTIONADAS NOVAMENTE

Estas decisões foram tomadas com análise formal (matriz de avaliação) e
estão registradas em ESP-15. Reabrir sem evidência nova é desperdício de ciclo.

| Decisão | Escolha | Quando revisar |
|---|---|---|
| LLM provider | Claude API (Anthropic) | Se COGS inviabilizar ou qualidade degradar significativamente |
| Cloud provider | Hostinger VPS → AWS quando MRR justificar | Gatilho: primeiro cliente enterprise ou >50 usuários simultâneos |
| Framework de orquestração | Implementação própria (sem LangChain) | Se Agentic RAG (RDM-034) for implementado — reavaliar então |
| State management frontend | Zustand + TanStack Query | Se wizard do protocolo mudar fundamentalmente |
| Banco de dados | PostgreSQL 16 + pgvector | Não revisar antes da Onda 3 |
| Embedding model | voyage-3 | Quando RDM-015 (Embedding Refresh) for implementado |
| GraphRAG completo | EXCLUÍDO (RDM-026 descartado) | Não reabrir — RAR (RDM-031) cobre o essencial |
| LangChain / LangGraph | EXCLUÍDO | Não reabrir antes da Onda 3+ |

---

## 9. DÉBITOS ABERTOS — MONITORAR ATIVAMENTE

Estes itens não foram resolvidos e têm risco crescente com o tempo.
Atualizar esta tabela quando um item for fechado.

| # | Débito | Risco | Gatilho para resolver |
|---|---|---|---|
| ~~D-01~~ | ~~SEC-09: BYPASS_AUTH=False~~ | ~~Segurança crítica em produção~~ | ✅ **Fechado Abril 2026** — FastAPI ativo não tem BYPASS_AUTH. Zero UUIDs renomeados para `_NULL_USER_SENTINEL` |
| D-02 | Backup automatizado do `taxmind_pgdata` | Perda irreversível de dados | **Antes do primeiro cliente pagante** |
| D-03 | SEC-10: IDs sequenciais → UUID em cases/outputs | Enumeração e segurança | Antes de dados sensíveis de clientes |
| D-04 | Corpus Manager sem responsável formal | Desatualização silenciosa do corpus | Ao atingir 10 clientes pagantes |
| D-05 | Tab Consultar com resposta mais rasa que Protocolo | Qualidade inconsistente | Aplicar PROMPT_DIAGNOSTICO antes do lançamento |
| D-06 | Billing Asaas produção não contratado | Monetização bloqueada | Antes de aceitar primeiro pagamento |
| D-07 | Staging environment inexistente | Deploys sem validação prévia | Ao iniciar Onda 2 |
| D-08 | Pipeline CI/CD ausente | Deploys manuais com risco de erro humano | Ao iniciar Onda 2 |

---

## 10. O QUE ESTE PROJETO DEMONSTROU

**O maior diferencial de produtividade em operação solo é:**
rigor conceitual antes de qualquer execução + diagnóstico preciso antes de qualquer correção.

**Os únicos débitos que realmente ameaçam o produto são os conceituais**, não os técnicos.
Dívida técnica se paga com refatoração. Dívida conceitual se paga com retrabalho de produto.

**Timing é a vantagem real.**
A Reforma Tributária cria uma janela de 18–36 meses onde incumbentes não conseguem
responder sem canibalizar seu próprio modelo. Nenhuma dívida técnica ameaça isso.
O corpus desatualizado, sim.

---

## ATUALIZAÇÃO DESTE ARQUIVO

Atualizar sempre que:
- Um débito da Seção 9 for fechado (marcar como ✅ e registrar a data)
- Um incidente de produção gerar nova lição
- Uma decisão arquitetural for revertida (documentar por que)
- Um novo padrão de trabalho for estabelecido

Formato de nova entrada:
```markdown
### [DATA] — [TÍTULO CURTO]
**O que aconteceu:** ...
**Custo:** ...
**Regra derivada:** ...
```
