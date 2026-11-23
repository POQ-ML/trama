# Dashboard → Projeto → Fonte

## Organização e identidade

Um projeto acadêmico agrupa fontes cadastradas pelo usuário. Ele é distinto da
entidade `project` do diagnóstico, que continua representando o repositório
GitHub. Neste MVP, `source_type` aceita somente `github`.

O ambiente atual é local e compartilhado, sem autenticação. A dependência de
proprietário do backend usa o workspace local; não aceita identidade enviada
pelo cliente. Os novos handlers verificam o escopo do projeto e da fonte,
mas isso não constitui autenticação ou isolamento multiusuário. As rotas
legadas continuam sujeitas ao mesmo limite operacional.

Um mesmo repositório pode ser vinculado a projetos diferentes e compartilhar
monitor, diagnósticos e feedback. Repositórios diferentes conservam identidades
e resultados separados. O vínculo no mapa significa apenas participação no
projeto acadêmico; não é uma descoberta de relação científica entre fontes.

## Fluxo local

1. Abra a página inicial e crie dois projetos, com nome e descrição opcional.
2. Abra um projeto, use **Adicionar fonte**, mantenha o tipo **GitHub** e
   cadastre duas URLs de repositórios diferentes.
3. Confira as duas fontes no mapa e na lista. O cadastro apenas persiste o
   vínculo e não faz coleta nem cria trabalho de análise.
4. Abra uma fonte para consultar seu diagnóstico existente ou solicitar um
   novo pelo fluxo de descoberta. O worker existente processa a fila; ele
   precisa estar em execução para que um pedido novo seja concluído.
5. Volte ao projeto e abra a segunda fonte. Seus resultados são independentes
   dos da primeira. Recarregue as páginas para verificar a persistência.

A aplicação usa as variáveis, portas e configuração do ambiente local existente.
Consulte [discovery-runtime.md](discovery-runtime.md) antes de iniciar serviços.
Não inicie outra stack sobre o mesmo banco para executar os testes.

## Migração e legado

A migration `007_academic_projects` é aditiva. Ela cria os projetos e vínculos
necessários e organiza fontes GitHub anteriores recuperáveis no projeto
**Fontes anteriores**, sem reescrever as análises e evidências históricas.
O acesso direto ao diagnóstico antigo permanece disponível por `/discoveries`
e pelos links `/?run=<id>`.

URLs antigas inválidas ou não suportadas não são transformadas em novas fontes
fictícias; seus diagnósticos continuam acessíveis pelas rotas legadas. No merge
de um rename, os IDs dos vínculos são preservados. Se os dois aliases já
estavam no mesmo projeto, ambos os vínculos históricos permanecem no monitor
canônico; um novo cadastro da URL canônica reutiliza um vínculo existente.

A migração não dispara coleta ou geração. Seu downgrade recusa a remoção de
tabelas populadas, evitando apagar projetos e vínculos silenciosamente. Faça
backup e examine os dados antes de qualquer operação de reversão.

## Validação desta entrega

Verificações de 14/11/2026 sobre a cópia reconstruída da base `194a8f9`:

| Rodada | Resultado | Alcance |
| --- | --- | --- |
| Backend, novos testes `test_projects.py` | 8 passed, 4,26 s | HTTP ASGI, PostgreSQL real e schemas exclusivos |
| Harness independente escrito/revisado pelo QA, executado pelo Orchestrator | 24 passed, 8,71 s, zero skips/errors | Navegação/API, escopo, concorrência, runtime com fronteiras falsas, migrações 005/006→007 e downgrade protegido |
| Regressão do fluxo anterior | 31 passed, 7,64 s | Runtime, persistência e migração do diagnóstico, em schema exclusivo |
| Frontend `node --test apps/web/tests/*.test.cjs` | 21 passed, zero skips | Adapters, cancelamento, payloads, componentes e compatibilidade legada |
| Typecheck e build Next.js | PASS | Build configurado com a API isolada de validação |

As rodadas se sobrepõem e não devem ser somadas como uma suíte única. Python
3.11.17 e PostgreSQL 16 na validação de backend; a execução Node local usou
26.13.0. Os 24 testes independentes foram escritos/revisados pelo agente QA e
executados pelo Orchestrator; isso não é avaliação humana independente.

A primeira tentativa do Backend encontrou oito erros de preparação no guard
do nome do banco, antes de abrir conexão. A primeira execução Node foi
bloqueada pelo sandbox ao iniciar o subprocesso TypeScript; a repetição
com permissão adequada passou. Não foram classificados como bugs do produto.
Os guards originais de banco foram preservados no delta final.

Não foi executada suíte global nesta entrega. As oito falhas históricas
registradas em [discovery-validation.md](discovery-validation.md) não foram
reclassificadas nem ocultadas. Resultados de 12/11 são históricos: seus
artefatos temporários foram perdidos e não são a evidência desta reconstrução.

Os dados da validação integrada são explicitamente controlados: API, PostgreSQL
e Runtime reais; GitHub, OpenAlex e geração substituídos nas fronteiras. Nenhum
request a essas fontes ou ao Gemini foi necessário para esta entrega.

### Comandos focais reproduzíveis

Na raiz, com dependências instaladas:

```sh
node --test apps/web/tests/*.test.cjs
apps/web/node_modules/.bin/tsc --noEmit --incremental false -p apps/web/tsconfig.json
cd apps/web
npm run build
```

Para o backend, use exclusivamente um PostgreSQL descartável cujo nome comece
com `qa_discovery_`, com as dependências de `apps/api/requirements.txt`:

```sh
cd apps/api
TEST_DATABASE_URL="$NAV_TEST_DATABASE_URL" PYTHONPATH=.:tests python -m pytest tests/test_projects.py -q -ra
```

`NAV_TEST_DATABASE_URL` deve apontar para esse banco descartável. A fixture cria
um schema exclusivo. Não use o banco da demonstração ou de produção. Outros
testes antigos de migração exigem isolamento próprio: não os execute contra um
schema populado apenas copiando esse comando. O harness adicional de QA foi
mantido como artefato temporário da rodada, não como dependência da aplicação.

### Navegador

Validação em `http://127.0.0.1:33574`, API isolada `18574`:

- O Orchestrator criou dois projetos pelo formulário e cadastrou duas fontes
  no mesmo projeto. Dashboard, contagens e vínculos continuaram presentes após
  reload. Em viewport 390 px, documento 384 px: mapa com scroll local, lista
  disponível como alternativa.
- O agente QA, em portal próprio, navegou dashboard → projeto → duas fontes;
  mapa e lista tinham os mesmos IDs. Cada fonte abriu seu próprio diagnóstico
  e manteve identidade, partial e GET scoped após reload.
- O link legado `/?run=...` abriu a análise existente, sugestão e monitor.
  Acesso pré-006 foi exercitado na migração; a run aberta no navegador é uma
  run controlada atual, não uma amostra histórica pré-006.

A revisão do navegador usou DOM, árvore de acessibilidade e requests observados,
sem interceptação. O screenshot do Orchestrator falhou por timeout de render do
portal; diagnóstico Maestri indicou conexão ativa. Não se alegam aprovação
visual por screenshot, auditoria de contraste/foco, WCAG ou gesto touch físico.
Não foi feita nova análise pública para esta validação.

## Limites operacionais

O código foi integrado ao repositório, mas a stack local existente não foi
recriada durante esta entrega. Para usá-lo nesse ambiente, reconstrua as imagens
e aplique `alembic upgrade head` com sua configuração atual, seguindo
`discovery-runtime.md`. Não substitua suas portas/overrides por defaults sem
conferência. A demonstração isolada contém dados sintéticos explicitamente
rotulados e não é o seu banco anterior.

Não há exclusão/edição de projeto, novos conectores, autenticação, motor de
relações entre fontes ou sincronização nova nesta entrega. O monitoramento
já existente é reutilizado. A validação focal não mede relevância científica,
resiliência sob carga ou segurança de uma implantação pública.
