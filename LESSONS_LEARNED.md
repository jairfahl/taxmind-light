# LESSONS_LEARNED.md
# Orbis.tax — Lições Aprendidas
**Versão:** 1.3
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

**Cores de texto no frontend devem usar variáveis CSS semânticas.**
Usar `style={{ color: "#0f2040" }}` hardcoded quebra o dark mode silenciosamente —
o background escurece mas o texto permanece dark, criando baixo contraste.
**Regra derivada:** sempre usar `className="text-foreground"` ou `text-muted-foreground`
(que mapeiam para CSS vars `--foreground` / `--muted-foreground` que o `@media prefers-color-scheme: dark`
sobrescreve). Nunca `style={{ color }}` para texto que deve adaptar ao tema.

**`useSearchParams()` no Next.js 16 exige Suspense boundary.**
Páginas com `useSearchParams()` em componentes "use client" quebram o build de produção
se não estiverem envoltas em `<Suspense>`. O erro aparece apenas no `next build`, não em dev.
**Regra derivada:** qualquer componente que use `useSearchParams()` deve estar em sub-componente
(ex: `VerifyEmailContent`) envolto por `<Suspense fallback={...}>` no componente exportado default.

**VARCHAR muito curto + ausência de catch block = UX travada sem feedback.**
O OnboardingModal chamava `PATCH /v1/auth/onboarding`. A coluna `tipo_atuacao VARCHAR(20)`
rejeitava "Empresa (uso interno)" (21 chars) com `DataError` do PostgreSQL → API retornava 500.
O frontend não tinha `catch` — a promise rejeitada não tinha handler, o botão voltava a "Confirmar e entrar"
sem mensagem alguma. O usuário ficava preso no modal sem saber o motivo.
**Regra derivada (dupla):**
1. Toda coluna que armazena labels vindas diretamente do frontend deve ter VARCHAR larga o suficiente
   para o label mais longo da UI — usar VARCHAR(100) como padrão seguro para campos de seleção.
2. Todo handler `async` no frontend que chama a API DEVE ter `catch` explícito com estado de erro visível.
   `try { await api... ; onComplete() } finally { setLoading(false) }` sem `catch` é armadilha silenciosa.

**"Migration aplicada em prod" no CLAUDE.md não garante que foi aplicada.**
A migration 122 constava como ✅ aplicada no CLAUDE.md, mas a consulta direta ao banco em produção
mostrou `tipo_atuacao VARCHAR(20)` — a migration foi commitada mas nunca executada no VPS.
**Regra derivada:** ao registrar migration como aplicada em prod, anexar a saída do `SELECT column_name,
character_maximum_length FROM information_schema.columns WHERE table_name='...'` como evidência.
Declarar ✅ sem evidência empírica é risco real.

**Diagnóstico de schema deve ser feito na camada correta: no banco, não no código.**
Horas foram gastas rastreando o bug no código (React state, interceptors, CORS, auth)
antes de consultar diretamente `information_schema.columns` no banco.
A resposta estava a um `docker exec psql` de distância.
**Regra derivada:** ao investigar falha silenciosa em PATCH/PUT que atualiza o banco,
o primeiro passo é verificar o schema atual das colunas relevantes no container DB,
não o código da API.

### ❌ O que causou problemas

**Migrations sem verificação de dependência geram erro silencioso em runtime.**
O episódio `mau_records` antes de `tenants` existir: FK sem referência passa na migration
e só falha em operação real. O sistema sobe, parece ok, falha em produção.
**Regra derivada:** antes de qualquer migration que cria FK, verificar se a tabela-pai existe
com `\d <tabela>` no container. Sequência obrigatória no TASKS antes de qualquer migration.

**Migrations locais não commitadas não chegam ao VPS via git pull.**
Migrations 119–124 foram aplicadas localmente (ALTER TABLE direto no banco) para resolver
um bug urgente em produção, mas nunca commitadas. O VPS nunca as recebeu.
Resultado: produção com schema diferente do repositório, causando erros 500 em registro.
**Regra derivada:** qualquer ALTER TABLE executado diretamente no banco DEVE ter um arquivo
`migrations/NNN_descricao.sql` correspondente criado e commitado imediatamente.

**BYPASS_AUTH é faca de dois gumes.**
Viabilizou testes sem fricção. Criou dependências ocultas (UUID hardcoded, FK violation,
lógica de trial sem efeito) que custaram tempo na ativação de produção.
**Regra derivada:** SEC-09 (BYPASS_AUTH=False) é pré-requisito para qualquer usuário
real com dados reais no sistema. Não negociável. Não postergar após o lançamento.

**Variáveis de ambiente com `$` quebram o docker compose silenciosamente.**
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

### ❌ O que custou caro

**VPS compartilhada entre projetos cria dependências ocultas no nginx.**
O nginx do orbis.tax roda no mesmo VPS e mesmo container que o virameta.com.br.
Esse fato não estava documentado. Ao tentar corrigir os redirects do tribus-ai.com.br,
quase foi feito `git reset --hard` sobrescrevendo os blocos do virameta — o que derrubaria
outro SaaS em produção. O erro foi evitado apenas porque o nginx.conf do VPS foi lido
*antes* de executar. Qualquer sessão anterior que não lesse o arquivo teria causado o incidente.
**Regra derivada:** antes de qualquer operação em nginx/docker no VPS, ler o estado real
do servidor (`cat nginx.conf`, `docker ps`, `git status`) — nunca assumir que o VPS
reflete o repositório. Projetos compartilhando infraestrutura DEVEM estar documentados
no ARCHITECTURE.md com nota explícita de risco.

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
Após adicionar `RESEND_API_KEY` ao `.env.prod` e rodar `restart api`, a variável
ainda não estava disponível no container — o e-mail continuava falhando silenciosamente.
**Regra derivada:** após qualquer alteração de `.env.prod` no VPS:
`docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate api`
Nunca usar `restart` para mudança de variável de ambiente.

**O volume `taxmind_pgdata` é o ativo mais crítico — sem backup é risco existencial.**
Contém todos os embeddings e o histórico de decisões dos clientes.
**Regra derivada:** backup automatizado via `pg_dump` para storage externo é
pré-requisito para o primeiro cliente pagante. Não após. Antes. ✅ Implementado (scripts/backup_db.sh).

**"Funciona local" não significa "está commitado".**
O ambiente local pode ter arquivos que nunca passaram pelo git.
O VPS só tem o que está no repositório.
**Regra derivada:** antes de qualquer deploy relevante, testar a partir de um clone limpo
em diretório separado: `git clone <repo> /tmp/test-deploy && cd /tmp/test-deploy && npm run build`.

**APP_URL corrompida por colagem de dois comandos na mesma linha.**
Ao adicionar `APP_URL=https://orbis.tax` ao `.env.prod` via terminal, o usuário colou
dois comandos na mesma linha sem separador. O resultado foi
`APP_URL=https://orbis.tax docker compose --env-file...` — tudo como valor de string.
Os e-mails de verificação chegavam com link corrompido (Google safe browse alertava).
**Regra derivada:** após adicionar variável ao `.env.prod`, sempre verificar com
`grep '^APP_URL=' .env.prod` antes de recriar o container. A linha deve conter apenas `KEY=value`,
sem espaços ou outros comandos.

**RESEND_API_KEY ausente do `.env.prod` bloqueou e-mails em produção silenciosamente.**
O log mostrava `RESEND_API_KEY não configurada` mas o registro retornava HTTP 200.
O usuário criava conta, recebia tela de sucesso, não recebia e-mail — e não conseguia logar.
**Regra derivada:** ao implementar qualquer novo serviço que exige env var, adicionar
à checklist pré-deploy e ao `.env.prod.example` imediatamente, antes de commitar.

---

## 5. DNS E DOMÍNIO

### ✅ O que funciona

**Verificar domínio Resend via DNS TXT — processo lento mas confiável.**
A propagação DNS pode levar de 30 minutos a 24 horas. O botão "Verify Records" no painel
Resend só funciona após propagação completa. Tentar antes gera falso negativo.
**Regra derivada:** após configurar registros DNS, aguardar pelo menos 1 hora antes de
tentar verificar. Usar `dig TXT _dmarc.orbis.tax @8.8.8.8` para checar propagação externamente.

### ❌ O que causou problemas

**Registro DKIM no DNS tem limite de 255 caracteres por string.**
A chave DKIM gerada pelo Resend tem ~320 caracteres. Hostinger truncava silenciosamente.
O registro aparecia "salvo" mas estava incompleto — verificação falhava repetidamente.
**Regra derivada:** strings TXT > 255 chars devem ser divididas em múltiplas strings
quoted no campo DNS. Formato correto (sem espaço entre aspas):
`"primeira_parte_com_255_chars" "segunda_parte_restante"`
O DNS concatena automaticamente. Alguns painéis exigem que cada parte tenha suas próprias aspas.

---

## 6. DEBUGGING E DIAGNÓSTICO

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

**Conta com `email_verificado = FALSE` causa 401 no login sem mensagem clara.**
Após registro, se o e-mail de verificação não chega (ex: RESEND_API_KEY ausente),
a conta existe no banco mas não pode fazer login. O usuário não entende por quê.
**Regra derivada:** ao investigar "registro funcionou mas login dá erro":
`SELECT email, email_verificado, ativo FROM users WHERE email = '...'` é o primeiro passo.

---

## 7. PROCESSO DE TRABALHO COM CLAUDE CODE

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

**Dev sênior antevê problemas antes de pedir para o PO testar.**
Pedir ao usuário para testar antes de checar o schema do banco, os logs e o estado do ambiente
gera frustração e ruído desnecessário. O ciclo correto é: diagnosticar → corrigir → confirmar
internamente → só então pedir validação ao PO.

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

## 8. SEGURANÇA

### ✅ O que funciona

**JWT sem fallback para modo permissivo.**
A auditoria SEC-02 eliminou o padrão "se JWT falhar, aceitar sem auth".
Sem fallback, a segurança não degrada silenciosamente.

**Rate limit (slowapi) e validação de MIME no upload.**
SEC-06 e SEC-07 eliminaram dois vetores de abuso sem custo operacional relevante.
Implementar cedo é mais barato que remediar após incidente.

**Validação de senha forte no backend (Pydantic) e no frontend (Zod).**
Validação dupla: o Zod informa o usuário em tempo real (checklist visual),
o `@field_validator` no Pydantic garante que nenhuma senha fraca passe mesmo via API direta.
Regra: validação de segurança crítica sempre no backend, frontend é UX auxiliar.

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

## 9. DECISÕES ARQUITETURAIS QUE NÃO DEVEM SER QUESTIONADAS NOVAMENTE

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
| E-mail transacional | Resend | Não revisar antes de atingir limites de volume |
| Billing | Asaas | Não revisar antes de fechar primeiro contrato pagante |

---

## 10. DÉBITOS ABERTOS — MONITORAR ATIVAMENTE

Estes itens não foram resolvidos e têm risco crescente com o tempo.
Atualizar esta tabela quando um item for fechado.

| # | Débito | Risco | Gatilho para resolver |
|---|---|---|---|
| ~~D-01~~ | ~~SEC-09: BYPASS_AUTH=False~~ | ~~Segurança crítica em produção~~ | ✅ **Fechado Abril 2026** — FastAPI ativo não tem BYPASS_AUTH |
| ~~D-02~~ | ~~Backup automatizado do `taxmind_pgdata`~~ | ~~Perda irreversível de dados~~ | ✅ **Fechado Abril 2026** — `scripts/backup_db.sh` criado |
| D-03 | SEC-10: IDs sequenciais → UUID em cases/outputs | Enumeração e segurança | ⚠️ Migration 118 criada e dry-run validado. Parte 3 (swap PK/FK) requer janela de manutenção + aprovação do PO |
| D-04 | Corpus Manager sem responsável formal | Desatualização silenciosa do corpus | Ao atingir 10 clientes pagantes |
| D-05 | Tab Consultar com resposta mais rasa que Protocolo | Qualidade inconsistente | Aplicar PROMPT_DIAGNOSTICO antes do lançamento |
| D-06 | Billing Asaas produção não contratado | Monetização bloqueada | Antes de aceitar primeiro pagamento |
| D-07 | Staging environment inexistente | Deploys sem validação prévia | Ao iniciar Onda 2 |
| D-08 | Pipeline CI/CD ausente | Deploys manuais com risco de erro humano | Ao iniciar Onda 2 |

---

## 11. O QUE ESTE PROJETO DEMONSTROU

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
- Um débito da Seção 10 for fechado (marcar como ✅ e registrar a data)
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
