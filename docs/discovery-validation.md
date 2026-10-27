# Validação da descoberta e das análises legíveis

Consolidação em 27/10/2026 da entrega iniciada após a base `628486c`.
Este registro separa testes automatizados, cenário controlado, uso de fontes
públicas e avaliação manual. As rodadas abaixo não são somadas como uma suíte.

## O que foi implementado

- API de descoberta assíncrona: enfileirar/recuperar análise, feedback,
  configuração de monitor, checagem, reanálise, histórico e leitura de avisos.
- Fila e resultados no PostgreSQL, worker contínuo, leases/fencing,
  idempotência, deadlines e preservação dos snapshots de evidência/feedback.
- Coleta GitHub limitada, redirecionamento inicial canônico restrito,
  descompressão correta e busca OpenAlex limitada; rejeição semântica opcional.
- Mapa orbital e lista com os mesmos IDs/dados, seleção, evidências e monitor.
- Análise redigida pelo modelo em quatro partes em português, com evidências
  originais separadas. Fallback explícito quando geração falha ou acaba o
  orçamento. Validação de formato/IDs não prova interpretação correta.

Setup, rotas, configuração e limites: [discovery-runtime.md](discovery-runtime.md).
Contrato de persistência: [discovery-contract.md](discovery-contract.md).

## Como foi testado

| Rodada | Ambiente e fronteiras | Resultado e limite |
| --- | --- | --- |
| Regressão anterior ao fix gzip, 25/10 | Python 3.11/PostgreSQL, mesmas dependências da baseline | 338 passed + 52 subtestes; mesmos oito failed históricos, zero errors/skips. Não é resultado do hash final posterior. |
| Delta gzip, 25/10 | QA independente offline | Sete passed; repo/README gzip, reconstrução de headers, 304/hash e limite de bytes decodificados. |
| Integração controlada, 25/10 | HTTP/PG/runtime reais, somente fontes/provider sintéticos | 22/22 checks, 13 processos de worker: fila, idempotência, evidências/feedback, mudanças A-B-A-B, stale/ack, reanálise e fila com monitor ocupado. Não é qualidade de fontes/LLM reais. |
| Migração 006 | PostgreSQL exclusivo e probes independentes | Quatro checks de guards/downgrade/reupgrade aprovados; demais roundtrips e dados legados cobertos no teste runtime. Não executados no banco do usuário. |
| Análise legível final, 26/10 | Imagem worker Python 3.11, rede none, código da própria imagem | 92 passed + 58 subtestes, zero skips; busca/explicação/evidência, provider, cancelamento e factory runtime. Sobrepõe focais AI/Backend. |
| QA independente da análise legível | Python 3.11, rede none, providers fake | 16 passed, zero skips; JSON estrito, referências, fallback/abstenção, caps, cancelamento, contexto Markdown/RST e offsets. |
| Frontend final | TypeScript, testes Node, production build Docker | Typecheck/build aprovados, dez testes focais; mapa/lista/detalhe em desktop e mobile390 com dados persistidos, sem interceptação. |

As oito falhas históricas envolvem testes de constraints que executam SQL antes
do bloco de expectativa de erro/flush. Não foram escondidas com skip/xfail nem
corrigidas nesta entrega. Não foi repetida uma suíte geral após cada delta.

Correções tiveram reprodução anterior: fila ocupada bloqueando segundo job;
ConfigParser com URL percent-encoded; redirect 301; dupla descompressão gzip;
cancelamento convertido em erro unknown; título selecionado em empate apesar
de resumo substantivo disponível. Testes locais demonstraram falha antes e
aprovação após as correções respectivas; isso não é benchmark semântico.

## Comandos para reprodução offline

Na raiz, com dependências de desenvolvimento disponíveis, o conjunto focal
sem rede externa pode ser executado na imagem construída para a API/worker:

```sh
docker run --rm --network none trama-api:local python -m pytest \
  tests/test_discovery_search.py tests/test_discovery_explanations.py \
  tests/test_discovery_evidence.py tests/test_llm.py \
  tests/test_llm_cancellation.py \
  tests/test_runtime_mvp.py::test_runtime_explanation_timeout_respects_server_cap \
  tests/test_runtime_mvp.py::test_runtime_disabled_explainer_keeps_budget_without_provider \
  tests/test_runtime_mvp.py::test_provider_reuse_sdk_budget_and_cleanup \
  -q -ra -p no:cacheprovider
```

Com as dependências Node instaladas em `apps/web`:

```sh
node --test apps/web/tests/*.test.cjs
cd apps/web
npx tsc --noEmit --incremental false
npm run build
```

`npm test` executa somente o adaptador client; para os três arquivos focais,
use o comando `node --test` acima. Testes completos de runtime/migrations
precisam de PostgreSQL exclusivo e descartável e não devem apontar para a demo.
Os comandos documentam reprodução; não afirmam nova execução em 27/10.

## Validação com fontes públicas e Gemini

A autorização do usuário abrangeu trechos públicos GitHub/OpenAlex na conta
Gemini gratuita. Nenhuma chave, prompt bruto ou erro bruto do SDK é registrado
nesta documentação; o modelo configurado permaneceu gemini-3.5-flash-lite.

Após um teste sintético isolado, houve validação focal pública com o worker.
A run final de análise legível `a0000844-21ea-4476-8fa2-80bcfbd7b927`, para
scikit-learn, terminou em 26/10 às 22:09:11.584785Z: 12,27 s desde claim,
cinco sugestões/dez evidências. Três análises redigidas e dois fallbacks,
status `partial`, somente `explanation_budget_reached`. Telemetria: três
resultados de provider bem-sucedidos, retries0, 1340 tokens entrada + 633 saída.
Isso não conta dispatch HTTP independentemente, não comprova faturamento e
não fornece contador de abstenções. Não houve retry para transformar partial
em completed. A latência observada não é SLA.

QA SQL READ ONLY comprovou seis runs, 28 snapshots e 56 evidências anteriores
intactos e todos os status de feedback preservados; duas relações pending
atualizaram somente justificativa/score atuais, como previsto, mantendo os
snapshots históricos. Entraram uma run, cinco memberships, três relações e
dez evidências; totais sete/33/18/66. Configurações de três monitores e seis
avisos/readmarks foram preservadas. Não houve reconhecimento de avisos.

Em 27/10, GET e SQL somente leitura reconfirmaram a presença dos resultados e
33 memberships com ambas evidências encontradas. Essa observação atual não é
nova comparação byte a byte com a baseline anterior perdida.

O usuário depois testou pelo formulário e confirmou que funcionou e fez mais
sentido. Esse aceite é qualitativo de funcionamento/clareza, sem runID informado
para esse teste e sem constituir medição de precisão científica.

## Proveniência e limites

- Os artefatos temporários de 26/10 desapareceram em retomadas. Resultados
  históricos acima vêm dos relatórios inspecionados e da sessão registrada,
  não de logs supostamente disponíveis ou rerodados em 27/10.
- Os testes versionados no repositório permitem reproduzir os casos offline.
  Mantenha metadados de ambiente e resultados novos ao repetir uma validação.
- A busca é lexical e limitada; o contexto do repo pode ser curto demais para
  demonstrar objetivos ou lacunas. Prosa em português continua hipótese para
  revisão humana; não é análise de toda a árvore de código nem prova de uso,
  implementação, autoria ou compatibilidade.
- O teto interno de três operações pode deixar resultados exploratórios; não
  equivale à quota da conta Google. Falhas/abstenções também consomem operação.
- Não foram medidos precisão geral, throughput, p95 ou operação multiusuário.
  Esta entrega é local; autenticação e quotas globais públicas não estão cobertas.
