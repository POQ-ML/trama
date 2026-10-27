# MVP local: descoberta, worker e monitoramento

Esta rodada implementa a API e um worker local para o contrato de
[descoberta](discovery-contract.md). A fila, os resultados, as avaliações e os
avisos residem no PostgreSQL. Reiniciar a API não depende de manter uma tarefa
em memória. Não há Redis, Celery ou outro broker.

## Execução reproduzível

Use primeiro um PostgreSQL descartável/configuração local controlada. Escolha as
variáveis de banco em `.env` a partir de `.env.example`, sem versionar segredos.
A imagem da API usa Python 3.11; API e worker usam a mesma imagem e variáveis.
São necessários Docker Engine e Docker Compose. O Dockerfile da API usa `RUN`
comum e cache de camada; não exige BuildKit/buildx nem cache mounts. O build
precisa acessar o registry e o índice de dependências quando não houver cache.

Na raiz:

```sh
docker compose up --build -d postgres api worker web
docker compose logs -f api worker
```

Em instalações sem buildx/BuildKit, construa explicitamente com o builder
clássico antes de iniciar os serviços:

```sh
DOCKER_BUILDKIT=0 docker compose build api web
docker compose up -d postgres api worker web
```

A imagem `trama-api:local` construída pelo serviço `api` também executa o
worker; não há um segundo Dockerfile ou instalação de dependências para ele.
Para validar a configuração sem iniciar/recriar serviços, use
`docker compose config --quiet`. Para verificar a inicialização, use
`docker compose ps` e `docker compose logs --tail=100 api worker`.

A API aplica `alembic upgrade head` antes de iniciar. Seu healthcheck só passa
quando o servidor está disponível; o worker depende da API saudável e do
PostgreSQL saudável. A migration atual é `006_discovery_runtime`. O frontend
é construído com contexto da raiz para incluir os tipos compartilhados. Arquivos
`.env`, variantes locais, cobertura e caches ficam fora do contexto Docker.

Endereços padrão: web `http://localhost:3000`, API `http://localhost:8000`.
O worker não publica porta. Não execute uma segunda stack sobre o banco do
usuário para validar migrations. A migration 006 recusa downgrade com estado
novo incompatível, em vez de apagar resultados e avisos.

Para portas alternativas, defina em seu arquivo de ambiente local, por exemplo:

```dotenv
POSTGRES_PORT=55462
API_PORT=18052
WEB_PORT=3301
NEXT_PUBLIC_API_URL=http://localhost:18052
BACKEND_CORS_ORIGINS=["http://localhost:3301"]
```

Escolha portas livres e um nome de projeto Compose exclusivo para uma nova
instância. `-p` separa os volumes e nomes, mas não evita colisões de portas.
Com um arquivo externo, use os mesmos argumentos em todos os comandos, como
`docker compose --env-file /caminho/runtime.env -p trama-local build api web`
e `docker compose --env-file /caminho/runtime.env -p trama-local up -d postgres api worker web`.
Mantenha as credenciais de banco e fontes nesse arquivo não versionado.
Dentro dos containers, API e worker acessam `postgres:5432`; `POSTGRES_PORT`
é somente a porta publicada no host.

`NEXT_PUBLIC_API_URL` é o endereço da API acessível pelo **navegador**, embutido
no build do frontend. Alterá-lo exige reconstruir `web`, não apenas reiniciar
o container. `BACKEND_CORS_ORIGINS` é uma lista JSON de origens completas
(protocolo, host e porta, sem caminho). `localhost` e `127.0.0.1` são origens
distintas; inclua ambas explicitamente se alternar entre elas. A mesma origem
deve corresponder ao endereço usado para abrir a UI.

Alternativa sem Compose para API/worker, com dependências já instaladas:

```sh
cd apps/api
# Defina DATABASE_URL externamente com seu banco local escolhido.
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Em outro terminal, com o MESMO DATABASE_URL e configuração:
python -m scripts.discovery_worker
```

`python scripts/discovery_worker.py --once` e
`python -m scripts.discovery_worker --once` processam no máximo um job/check.
O modo contínuo verifica a fila e, quando não há análise elegível, um monitor
vencido. Por padrão aguarda 2 segundos quando ocioso e 50 ms entre trabalhos.
A execução de cada trabalho permanece limitada pelo deadline. Interrupções
podem deixar leases até o prazo; o worker retomado ou uma leitura HTTP de run
expirado registra `failed`/`partial` com `timeout`. Reenvio/reanálise cria ou
reutiliza um job ativo, sem reabrir uma execução terminal.

## Configuração e limites

| Variável | Padrão | Limite/comportamento |
| --- | --- | --- |
| `DISCOVERY_DEADLINE_SECONDS` | `120` | 30–300 s, prazo total persistido por run |
| `DISCOVERY_TOP_K` | `5` | 1–10 candidatos selecionados |
| `MONITOR_FETCH_SECONDS` | `20` | 2–30 s para coleta de contexto |
| `WORKER_POLL_SECONDS` | `2` | 0,2–30 s ocioso |
| `DISCOVERY_LLM_ENABLED` | `false` | opt-in para explicador configurado |
| `LLM_PROVIDER`, `LLM_MODEL`, `GEMINI_API_KEY` | config existente | só no servidor/worker |
| `GITHUB_TOKEN` | ausente | token opcional para cota GitHub; nunca enviado ao navegador |
| `OPENALEX_API_KEY`, `OPENALEX_EMAIL` | ausentes | config existente da fonte |

A busca padrão faz até duas consultas sequenciais, uma página de até 12 itens
por consulta, no máximo 24 candidatos e 25 s totais de busca. Cada request de
busca tem teto de 8 s e não faz retries do conector. O adaptador AI permite até
dois sockets OpenAlex por processo. O scan lexical é limitado a 20 mil caracteres
por campo; o helper de evidência aceita campos de até 100 mil caracteres e
extratos de até 2 mil. Esses limites podem causar abstenção ou ressalvas.

O explicador é novo por run, com até três operações de geração, até 20 s
por chamada (ou `LLM_TIMEOUT_SECONDS`, se menor) e até 1.024 tokens de saída
por request de análise. Provider e explicador usam o mesmo limite por chamada;
o prazo persistido da run continua em 120 s por padrão e pode encerrar uma
operação antes desse teto. O provider configurado é reutilizado no worker;
retries do adapter são zero e o SDK Gemini recebe `attempts=1`. Esses limites
não garantem três explicações aceitas: falha, abstenção e resposta inválida
também consomem a operação. Contadores de provider não comprovam sozinhos
despachos físicos independentes nem relevância semântica.
O client é fechado no shutdown quando a execução alcança o bloco de cleanup.
Um kill abrupto é recuperado por leases/deadlines, sem garantia de cleanup
Python anterior à saída do processo.

Sem opt-in/chave válida, o sistema usa explicação textual de contingência,
explicitamente **exploratória**, produz `partial`/`analysis_warning` e conserva
`explanation_unavailable` em `run.warnings`. Não chama LLM silenciosamente.
Para habilitar, configure `DISCOVERY_LLM_ENABLED=true` e o provider no ambiente
que chega ao worker. Revise a política de dados do provider antes de enviar
extratos reais de fontes. Nenhuma precisão semântica foi demonstrada pelo simples
fato de a busca retornar um artigo; scores são sinais lexicais, não probabilidades.

Respostas LLM válidas podem abster-se: candidatos rejeitados semanticamente não
são evidência inválida nem falha externa. Todos abstidos podem resultar em
`completed` com lista vazia. Contexto insuficiente produz `failed` com
`insufficient_context`; falha externa e timeout são distintos de zero artigos.
Outras ressalvas permanecem em `warnings`, sem respostas ou erros brutos do SDK.

## Texto da análise e evidências

O prompt solicita quatro partes curtas em português brasileiro: **O que o
artigo propõe**, **Relação possível com o projeto**, **Como explorar** e
**Limites e incertezas**. A decisão estruturada pode sugerir ou abster-se.
Cada campo textual aceito tem 20–400 caracteres; o texto persistido completo,
com cabeçalhos, fica limitado a 4000. A aplicação valida chaves, tipos,
comprimentos, referências aos dois lados e termos sustentados pelos extratos.
Essa validação não garante idioma nem interpretação semântica correta.

A prosa é uma hipótese revisável, não evidência. Os trechos originais ficam
separados e expansíveis na interface, preservando texto, offsets, hash e data;
podem continuar em inglês. Análises históricas não são reescritas quando o
formato muda. Fallback tem rótulo explícito e não é apresentado como prosa do
modelo. Os mesmos prefixos em textos antigos não provam geração livre.

Resultados, protocolo, comandos offline e limites da validação estão em
[discovery-validation.md](discovery-validation.md).

## API e recuperação

- `POST /api/v1/discoveries {repo_url}` → `202 RunRead`. Apenas enfileira;
  não faz HTTP externo/LLM no handler. `Idempotency-Key` opcional aceita 8–128
  caracteres ASCII alfanuméricos, `_` e `-`; mesma chave/outro repo retorna 409.
  Submissões concorrentes do mesmo monitor reutilizam seu job ativo.
- `GET /api/v1/discoveries/{id}?limit=20&cursor=UUID` → `DiscoveryPage`.
  Limite 1–50. Uma leitura após deadline pode registrar a expiração para não
  manter a UI indefinidamente em processamento com o worker ausente.
- `PATCH /api/v1/relationships/{id}/feedback {status}` → `FeedbackRead`.
- Erros HTTP usam `{error:{code,message,retryable}}`, sem ecoar inputs,
  credenciais, parâmetros SQL ou payloads das fontes.

O navegador pode consultar com backoff enquanto `queued`/`running`; o ID permite
recuperar resultados após reload. A paginação de sugestões continua por UUID,
não por ranking. A página não vazia normalmente usa quatro SELECTs; a recuperação
de expiração acrescenta trabalho apenas quando o prazo venceu. As sessões DB
são curtas e nenhuma fica aberta durante coleta/busca/geração. Handlers síncronos
são executados pelo threadpool ASGI; o worker tem processo/event loop separado.

Este recorte é uma demo local sem autenticação multiusuário ou quotas globais de
submissão. Configure origens CORS explícitas para a porta do frontend; não trate
esta configuração como publicação segura de um serviço público.

## Monitoramento e avisos

Por run (resolvido ao monitor único da fonte):

- `PUT /api/v1/discoveries/{id}/monitor` com `enabled` obrigatório,
  `interval_seconds` opcional (300; 60–86.400) e `reanalyze_on_change` opcional
  (false) habilita/desabilita ou altera configuração.
- `GET` no mesmo caminho retorna `MonitorRead`.
- `POST .../monitor/check` agenda uma checagem no worker; requer monitor ativo.
- `POST .../reanalyze` cria/reutiliza uma análise, sem alterar feedback anterior.
- `GET .../changes?limit=20&cursor=UUID` retorna ocorrências mais recentes
  primeiro. O cursor resolve a geração da ocorrência dentro do mesmo monitor;
  ele não é um cursor de outro repositório.
- `POST /api/v1/source-changes/{event_id}/read` marca o aviso como lido,
  idempotentemente. Isso não confirma relações nem elimina `stale`.

O coletor faz lookup do repo exato, nunca varre o owner. Após vincular o ID
numérico GitHub, verifica esse ID mesmo após renomeação. Usa ETags independentes
para metadados e README; `304/304` conserva o hash, inclusive com README truncado.
As respostas têm limite de bytes e prazo. No lookup inicial, aceita-se somente
um 301 para `https://api.github.com/repositories/ID` numérico, sem credenciais,
porta, query ou fragmento, com no máximo um salto e o mesmo deadline. O ID da
resposta deve coincidir. Outros redirects/URLs arbitrárias não são seguidos. README 404 significa ausência; erros de fonte não simulam remoção.

A cobertura é **metadados normalizados do repositório e README limitado**.
O hash existente inclui URL/data de atividade (`pushed_at`); uma atividade sem
mudança no README pode invalidar o contexto por esse critério. Não há leitura
de toda árvore de código, diff ou feed de commits, nem promessa de detectar todo
commit. Reanálise automática é opt-in e pode consumir cota nessas mudanças.

- `source_changed` é uma ocorrência persistida de hash diferente do observado
  anteriormente. A→B→A→B gera três avisos; repetir B não gera novo aviso.
- `stale` compara o hash observado com o da análise bem-sucedida correspondente.
  Falhas não limpam esse estado. Uma fonte ainda não analisada também pode
  estar stale, mesmo sem aviso de mudança inicial.
- `latest_run_id` identifica a última tentativa vinculada. Uma reanálise queued
  não prova que sugestões já foram recalculadas; aguarde `completed`/`partial`.
- Avaliações e evidências históricas permanecem. Falhas mantêm hashes anteriores,
  registram erro seguro e aplicam backoff exponencial limitado a uma hora,
  respeitando `Retry-After` limitado.

Leases e locks serializam observações; o token impede um worker antigo de gravar
após perder a posse. Os jobs são persistidos, mas não há garantia de processamento
sem executar o worker. Reinicie-o para continuar jobs/checks; falhas não viram
sucesso vazio. Consulte os testes e o relatório de execução para evidência de
concorrência, deduplicação, migrations e limites, sem inferir SLA de produção.
