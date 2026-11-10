# Contrato e persistência da descoberta

Etapa autorizada em 2026-10-23 pela PD-0003 do vault. Runtime em
`apps/api/app`, migration `005_discovery_contract` e tipos cliente em
`packages/shared/src/discovery.ts`. A etapa inicial documentada abaixo implementou contrato/persistência. A rodada
seguinte acrescenta API, worker e monitoramento descritos em
[discovery-runtime.md](discovery-runtime.md), mantendo a semântica histórica.

## Semântica e identidade

- `Entity.project` referencia um `AcademicItem.repository` do GitHub;
  `Entity.article` referencia um `AcademicItem.article` OpenAlex.
- A identidade é `(entity_type, origin_item_id)`, com índice único parcial:
  títulos homônimos são permitidos e renomear preserva o UUID da entidade.
  Entidades legadas/manuais e outros tipos mantêm a regra de rótulo único.
- `Relationship.project_article` tem orientação projeto → artigo. `pending`
  é sugestão com evidências; `confirmed`/`rejected` são avaliações humanas de
  relevância. Nenhum desses estados comprova uso, implementação ou autoria.
- Temas são classificações OpenAlex do **artigo**, congeladas no resultado
  da execução. Não há relação `article_topic` persistida nesta etapa.

## Contrato público para os futuros handlers

Os schemas Pydantic em `apps/api/app/schemas/discovery.py` são a referência
de campos, validação e nullability. Os tipos TypeScript espelham o JSON;
não validam fontes, URLs ou instantes em runtime.

| Operação futura | Entrada | Saída planejada |
| --- | --- | --- |
| `POST /api/v1/discoveries` | `DiscoveryCreate {repo_url}` | `RunRead` |
| `GET /api/v1/discoveries/{id}` | `DiscoveryQuery {limit?, cursor?}` | `DiscoveryPage` |
| `PATCH /api/v1/relationships/{id}/feedback` | `FeedbackUpdate {status}` | `FeedbackRead {id,status,updated_at}` |

As rotas acima foram registradas na rodada de runtime; veja o setup no documento ligado acima. O futuro handler serializará a `Relationship` atualizada retornada pelo repositório
em `FeedbackRead`; a resposta HTTP está implementada na rodada de runtime. `EvidenceInput`, `SuggestionInput` e `RunUpdate`
são contratos internos, nunca corpos de requests com evidências confiadas ao
cliente ou ao LLM.

`DiscoveryPage` contém `run`, `suggestions`, `total_suggestions`, `limit` e
`next_cursor`. Cada sugestão tem ID da relação, projeto, artigo, explicação,
score, temas, evidências e timestamps. Lista e mapa usarão os mesmos IDs.
O cursor público deve ser mapeado ao parâmetro interno `after`.

## Execução e transações

`DiscoveryRun` persiste `queued → running → completed|partial|failed`;
uma execução também pode falhar antes de iniciar. Erros usam códigos seguros
fechados; `partial` e `failed` exigem erro. Prazo padrão de cinco minutos é
calculado pelo servidor; `deadline_at` não pertence ao corpo de cadastro.

O futuro orquestrador deve executar `expire_run` explicitamente na recuperação
de execuções interrompidas: é idempotente, marca `partial` quando há resultados
persistidos e `failed` quando não há, com erro `timeout`. Na etapa inicial, leituras não escreviam. Na rodada atual há worker e a leitura
HTTP pode recuperar um run cujo prazo venceu; a leitura de repositório isolada
continua sem esse efeito. Esse mecanismo não cancela chamadas externas;
o próximo pipeline precisará aplicar seu próprio orçamento de tempo.

O chamador controla transações curtas com `with session.begin():`. O novo
repositório faz flush, sem commit por item; a gravação do lote usa savepoint
para rollback integral em caso de evidência inválida ou prazo excedido.
A ingestão existente continua com commit por item; concluir a ingestão antes
da transação de descoberta. Erros de transação externos exigem rollback
pelo chamador. Bloqueios seguem ordem estável e as leituras críticas atualizam
o identity map para não validar objetos antigos após commits concorrentes.

## Evidências e reprocessamento

O adaptador confiável reconstrói `SourceSnapshot` de item/provedor persistidos.
Cliente/LLM podem propor seleções, mas não determinar texto de origem, URL,
hash ou data confiáveis. O helper valida trecho literal, campo e offsets
Unicode `[start,end)`, ambos os lados e URLs canônicas permitidas.

`Evidence` preserva excerpt imutável, URL, locator, versão `sha256:<item_hash>`,
data e metadados internos com hash do campo, offsets e método. Isso evita
duplicar o README inteiro por evidência. Hashes identificam conteúdo; não são
assinaturas nem prova independente de inclusão. Dois trechos válidos não
provam relevância semântica: a seleção e explicação serão etapas posteriores.

**Precisão temporal:** na ingestão atual, `metadata.last_seen_at` é a última
observação na persistência. Não é o instante exato do fetch nem um timestamp
de commit Git. As evidências usam essa definição explícita; coletar SHA do
README ou timestamp exato de fetch é evolução separada.

`DiscoverySuggestion` associa execução e relação ao par exato de evidências,
explicação, score e temas daquela execução. Reprocessar pode criar outra
execução, sem duplicar a relação nem sobrescrever `confirmed`/`rejected`.
Uma nova observação pode justificar novo snapshot; evidências antigas são
preservadas. O rótulo retornado é o da entidade na última sincronização;
a URL original vem do item atual. Ingestão isolada não atualiza o rótulo da
entidade. Trechos, explicação e temas históricos continuam congelados por execução.

## Performance e migration

- Leitura limitada: padrão 20, máximo 50; cursor por UUID, sem `OFFSET`.
  A ordenação é estável por UUID da relação, **não ranking por score**.
- Página não vazia usa quatro `SELECTs`: cabeçalho, total, resultados com joins
  e par de evidências em lote. Página vazia pode dispensar a última consulta.
  A quantidade de consultas não cresce por artigo; isso não é benchmark de
  latência ou throughput de produção.
- Inserções em lote e `ON CONFLICT`, índices únicos de identidade/snapshot
  e PK `(run_id, relationship_id)` atendem às consultas concretas.
- Nenhum banco, broker, cache, biblioteca de grafo ou dependência de runtime
  adicional foi introduzido.
- Migration 005 preserva registros legados e recusa identidades de projeto
  ambíguas, sem escolher um merge silencioso. Downgrade recusa dados novos
  ou rótulos incompatíveis antes de DDL, evitando exclusão implícita.

## Validação

Testes da etapa: `test_discovery_contract.py`, `test_discovery_evidence.py` e
`test_discovery_persistence.py` e `test_discovery_migration.py`. Usar PostgreSQL descartável dedicado com nome
`qa_discovery_*` e dependências do projeto; não usar banco com dados de usuário.
Resultados executados, hashes do snapshot e limites devem constar no relatório
da entrega. Uma suíte sem URL de banco pode pular integrações e não comprova
persistência. Falhas históricas devem ser separadas de regressões desta etapa.
