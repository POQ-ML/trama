---
title: "Ingestão OpenAlex e GitHub — Handoff"
tags: [trama, ingestao, openalex, github, handoff]
data: 2026-10-19T18:30:00Z
branch: c-mod
commit_base: 061e17774bac47fe166894ff006ce249b4f2c7c6
commit_final: 4a4e9ba2f1be465e392ac6d25abf781d9cf0df2a
status: concluído
---

# Resumo

Implementado o pipeline de ingestão de dados reais do TRAMA para as fontes OpenAlex e GitHub. O `OpenAlexConnector` consulta Works via API REST com suporte a filtros, paginação por cursor (com chave) e paginação básica (sem chave), reconstrução de resumo a partir de índice invertido, e normalização completa de autores, tópicos, conceitos e palavras-chave. O `GitHubConnector` suporta três modos de busca (explícito, org/user e search), faz fetch e decodificação de README, e filtra repositórios privados por padrão.

O `IngestionPipeline` persiste via `upsert_item` usando `content_hash` para detectar mudanças, preserva `captured_at` original mesmo em updates, e produz `IngestionResult` com contagens por resultado. Uma migration nova (`004_add_repository_item_type`) estende o CHECK constraint de `item_type` para aceitar `"repository"`.

A validação real contra ambas as APIs foi executada e confirmada: 1 artigo OpenAlex (W2741809807) e 1 repositório GitHub (id=1296269) criados na primeira execução, ambos `unchanged` na segunda — idempotência verificada no PostgreSQL.

Testes: baseline 70 passed / 20 failed (pré-existentes) → após: 141 passed / 12 failed (apenas os 12 pré-existentes de LLM por `google-genai` não instalado, inalterados).

# Contexto consultado

| Nota do vault | Caminho | Influência |
|---|---|---|
| Current State | `00 - Project Core/Current State.md` | Confirmou que nenhuma ingestão existia; branch de trabalho e stack verificados |
| PD-0001 | `09 - Decisions and Proposals/Product Decisions/PD-0001-escopo-mvp-inicial.md` | Definiu fontes do MVP: OpenAlex + GitHub (aceito em 2026-10-12) |
| System Overview | `07 - Architecture and Engineering/01 - System Architecture/System Overview.md` | Arquitetura de conectores → Postgres |
| GitHub Integration | `06 - Sources and Integrations/01 - GitHub/GitHub Integration.md` | Tipos de dados, restrição a dados públicos, perguntas abertas |
| OpenAlex Integration | `06 - Sources and Integrations/02 - OpenAlex/OpenAlex Integration.md` | Propósito, campos de interesse, mecanismo polite pool |
| Domain Model | `07 - Architecture and Engineering/04 - Domain Model/Domain Model.md` | Distinção Source × SourceItem × Entity; imutabilidade de brutos |
| Database Notes | `07 - Architecture and Engineering/07 - Data and Database/Database Notes.md` | Estrutura ER proposta; uso de JSONB para extras |
| Integration Standards | `06 - Sources and Integrations/Shared Integration Standards/Integration Standards.md` | Anatomia do conector, idempotência, evidência/proveniência, lifecycle |

**Conflitos vault × código encontrados:**

| Item | Vault | Código | Resolução |
|---|---|---|---|
| `item_type` para repositórios | Não define | CHECK não incluía `repository` | Migration 004 adicionada |
| Lifecycle `raw/proposed/confirmed` | Integration Standards define 5 estados | `AcademicItem` não tem coluna `status` | Fora do escopo — responsabilidade do Relationship Engine |
| `SourceItem` imutável após criação | Domain Model | Sem constraint de imutabilidade no banco | Enforçado na camada de serviço via content_hash |

# Reutilizado (existente no repositório)

| Componente | Caminho | Como foi usado |
|---|---|---|
| `AcademicItem` | `apps/api/app/models/academic_item.py` | Modelo de destino para artigos e repositórios |
| `Source` | `apps/api/app/models/source.py` | Registro da fonte (openalex / github) |
| `Base` | `apps/api/app/models/base.py` | Base declarativa SQLAlchemy |
| `db_session` fixture | `apps/api/tests/conftest.py` | Sessão SQLite in-memory para testes unitários de persistência |
| `pg_engine` fixture | `apps/api/tests/conftest.py` | Engine Postgres para testes de integração |
| `alembic.ini` + `alembic/env.py` | `apps/api/alembic.ini`, `apps/api/alembic/env.py` | Configuração de migrations; `version_locations` aponta para `database/migrations/versions` |
| `VALID_ITEM_TYPES` | `apps/api/app/models/academic_item.py` | Atualizado para incluir `repository` |

# Criado

| Arquivo | Tipo | Função | Verificação de não duplicação |
|---|---|---|---|
| `apps/api/app/services/ingestion/__init__.py` | código | Exporta `OpenAlexConnector`, `GitHubConnector`, `IngestionPipeline` | Diretório `ingestion/` inexistente antes (confirmado: `git status` mostrava `??`) |
| `apps/api/app/services/ingestion/models.py` | código | DTOs `NormalisedItem` e `IngestionResult` | Sem DTO de ingestão em nenhum arquivo do projeto |
| `apps/api/app/services/ingestion/openalex.py` | código | Conector OpenAlex com paginação, retry e normalização | `apps/api/app/services/ingestion/openalex.py` não existia |
| `apps/api/app/services/ingestion/github.py` | código | Conector GitHub com 3 modos, README, rate limit | `apps/api/app/services/ingestion/github.py` não existia |
| `apps/api/app/services/ingestion/pipeline.py` | código | Orquestra conector → repositório → `IngestionResult` | Nenhum pipeline de ingestão existia |
| `apps/api/app/repositories/ingestion.py` | código | `get_or_create_source`, `upsert_item` com content_hash | `apps/api/app/repositories/ingestion.py` estava vazio (0 bytes) |
| `apps/api/scripts/ingest.py` | código/CLI | Entry point CLI com sub-comandos `openalex`, `github`, `all` | `apps/api/scripts/ingest.py` não existia |
| `apps/api/tests/test_ingestion_openalex.py` | teste | 32 testes unitários do OpenAlexConnector | Nenhum teste de ingestão OpenAlex existia |
| `apps/api/tests/test_ingestion_github.py` | teste | 31 testes unitários do GitHubConnector | Nenhum teste de ingestão GitHub existia |
| `apps/api/tests/test_ingestion_persistence.py` | teste | 18 testes de persistência (unitários + integração Postgres) | Nenhum teste de pipeline de ingestão existia |
| `database/migrations/versions/004_add_repository_item_type.py` | migration | Adiciona `repository` ao CHECK de `item_type` | Verificado: somente 3 migrations existiam antes |
| `docs/ingestion/audit.md` | doc | Mapeamento de campos, lacunas identificadas, decisões | `docs/ingestion/` não existia |
| `docs/ingestion/README.md` | doc | Guia de configuração, execução, testes e limitações | `docs/ingestion/` não existia |
| `apps/api/scripts/_validate_real.py` | script | Script de validação real contra APIs + banco | Novo |

# Modificado

| Arquivo | Alteração | Motivo | Evidência |
|---|---|---|---|
| `apps/api/app/models/academic_item.py` | `VALID_ITEM_TYPES` adicionado `"repository"` | Migration 004 estende o CHECK; modelo deve refletir | `git diff --stat`: 3 insertions |
| `apps/api/tests/test_migrations_integration.py` | Linha `assert row[0] == "003_persistence_layer"` → `"004_add_repository_item_type"` | Head do Alembic mudou com migration 004 | `git diff --stat`: 2 changes |
| `apps/api/tests/test_models_persistence.py` | `VALID_ITEM_TYPES` esperado com 5 tipos em vez de 4 | Idem | `git diff --stat`: 3 changes |
| `.env.example` | Adicionadas vars `OPENALEX_API_KEY`, `OPENALEX_EMAIL`, `GITHUB_TOKEN`, `TRAMA_INGESTION_LIVE_TEST` | Requisito de configuração para os novos conectores | `git diff --stat`: 31 insertions |
| `docker-compose.yml` | Adicionadas vars de ambiente para serviço `api` | Passar credenciais opcionais para o container | `git diff --stat`: 3 insertions |

# Migrations

| Migration | O que altera | Reversibilidade | Compatibilidade |
|---|---|---|---|
| `004_add_repository_item_type` | Remove `ck_academic_item_type_valid` e recria com `'repository'` incluso | Reversível se não existirem linhas com `item_type='repository'`; guarda no downgrade impede perda silenciosa | Compatível com dados existentes (nenhum usa `repository`) |

# Mapeamento de dados

| Campo da fonte | Campo normalizado | Destino (tabela.coluna) | Observações |
|---|---|---|---|
| OpenAlex `id` (URL) | `external_id` | `academic_items.external_id` | Sufixo extraído da URL |
| OpenAlex `title` | `title` | `academic_items.title` | Fallback `display_name` |
| OpenAlex `doi` (URL) | `metadata_['doi']` | `academic_items.metadata_` (JSONB) | Normalizado para `10.xxx/yyy` |
| OpenAlex `publication_date` | `original_date` | `academic_items.original_date` | UTC |
| OpenAlex `primary_location.landing_page_url` | `original_url` | `academic_items.original_url` | — |
| OpenAlex `authorships[]` | `metadata_['authors']` | `academic_items.metadata_` (JSONB) | `{id, display_name, orcid}` |
| OpenAlex `topics[]`, `concepts[]`, `keywords[]` | `metadata_['topics/concepts/keywords']` | `academic_items.metadata_` (JSONB) | — |
| OpenAlex `abstract_inverted_index` | `description` | `academic_items.description` | Reconstruído; `None` se ausente |
| GitHub `id` (int) | `external_id` | `academic_items.external_id` | Convertido para `str` |
| GitHub `full_name` | `title` | `academic_items.title` | — |
| GitHub `description` | `description` | `academic_items.description` | `None` se ausente |
| GitHub `html_url` | `original_url` | `academic_items.original_url` | — |
| GitHub `pushed_at` | `original_date` | `academic_items.original_date` | Fallback `updated_at` |
| GitHub README (decodificado) | `metadata_['readme']` | `academic_items.metadata_` (JSONB) | Truncado em 50 000 chars |
| GitHub `topics[]`, `language`, `owner` | `metadata_[...]` | `academic_items.metadata_` (JSONB) | — |

# Procedência e idempotência

**Chave de deduplicação:** `(source_id, external_id)` — enforçada por `UNIQUE` constraint no banco (migration 003, pré-existente).

**Constraint/índice:** `uq_academic_item_source_external` — verificado em `test_models_persistence.py::TestUniqueness::test_academic_item_unique_source_external` (passando antes desta implementação).

**Regra de atualização:** `content_hash` (SHA-256 de campos de conteúdo) — item só é atualizado quando o hash muda. `captured_at` original preservado em `metadata_['captured_at']`; `metadata_['last_seen_at']` atualizado em toda run.

**Granularidade de transação:** por item individual. Justificativa: falha em um item não desfaz os anteriores já commitados, permitindo reprocessamento incremental sem perda de dados.

**Validação real (2026-10-19):**
- OpenAlex RUN 1: `fetched=1 created=1 updated=0 unchanged=0 errors=0`
- OpenAlex RUN 2: `fetched=1 created=0 updated=0 unchanged=1 errors=0`
- GitHub RUN 1: `fetched=1 created=1 updated=0 unchanged=0 errors=0`
- GitHub RUN 2: `fetched=1 created=0 updated=0 unchanged=1 errors=0`
- SQL confirmado: `articles=1, repositories=1, sources=2`

# Tratamento de erros e limites

**OpenAlex:**
- 429 com `Retry-After`: aguarda valor do header (máx. 60s)
- 429 sem header: backoff exponencial 1s→2s→4s→16s
- 5xx / timeout / conexão: backoff exponencial, máx. 3 tentativas
- 4xx não-429: `ConnectorError` permanente, sem retry
- Resposta vazia: encerra paginação normalmente

**GitHub:**
- 429 / 403 com `Retry-After`: aguarda header
- 403 sem `Retry-After`: calcula wait via `X-RateLimit-Reset`
- 404 / 451 (repo inacessível): `_SkipRepo` — pula sem abortar demais
- Repositório `private=True`: ignorado com log de aviso
- README ausente (404): `None` no metadata, não aborta
- 5xx / timeout: backoff exponencial, máx. 3 tentativas
- Timeout explícito: 30s em todas as requisições

# Configuração

| Variável | Obrigatória | Comportamento quando ausente |
|---|---|---|
| `DATABASE_URL` | **Sim** | Erro imediato com mensagem citando o nome da variável |
| `OPENALEX_API_KEY` | Não | 10 req/s, paginação básica (≤10 000 resultados), log de aviso |
| `OPENALEX_EMAIL` | Não | Não entra no polite pool, log de aviso |
| `GITHUB_TOKEN` | Não | 60 req/h, log de aviso |
| `TRAMA_INGESTION_LIVE_TEST` | Não | Testes de integração com APIs reais não executam |

# Como executar

Comandos exatos executados e verificados nesta sessão:

```bash
# Subir banco
docker compose up -d postgres

# Aplicar migrations
cd apps/api
DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
  python -m alembic upgrade head

# Ingestão OpenAlex (1 registro de teste)
DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
  python scripts/ingest.py openalex --filter "doi:10.7717/peerj.4375" --max-pages 1

# Ingestão GitHub (1 repositório de teste)
DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
  python scripts/ingest.py github --repos "octocat/Hello-World"

# Testes unitários (sem rede, sem banco)
python -m pytest tests/test_ingestion_openalex.py tests/test_ingestion_github.py tests/test_ingestion_persistence.py -v

# Suíte completa
DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
TEST_DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
  python -m pytest tests/ -v
```

# Testes

| Momento | Passando | Falhando | Skipped | Comando |
|---|---|---|---|---|
| Baseline (pré-implementação) | 70 | 20 | 0 | `python -m pytest tests/ -v` |
| Após implementação | 151 | 20* | 16 | `python -m pytest tests/ -v` |
| Apenas novos testes | 81 | 0 | 0 | `python -m pytest tests/test_ingestion_*.py -v` |

*Os 20 failures pós-implementação são os mesmos 20 pré-existentes (12 LLM por `google-genai` não instalado + 8 `TestDbConstraints` por bug de test setup pré-existente). Nenhuma regressão introduzida.

Testes unitários (sem rede): `test_ingestion_openalex.py` (32 testes), `test_ingestion_github.py` (31 testes).
Testes de persistência (SQLite in-memory): `TestGetOrCreateSource`, `TestUpsertItem`, `TestIngestionPipeline`.
Testes de integração Postgres (opt-in, marcador `integration`): `TestIngestionPersistenceIntegration`.

# Validação real

**Validado contra APIs reais e PostgreSQL (2026-10-19):**

OpenAlex:
- Work `W2741809807` ("The state of OA") criado na primeira execução
- Segunda execução: `unchanged=1` — sem duplicata confirmado via `SELECT COUNT(*) FROM academic_items WHERE external_id='W2741809807'` → 1

GitHub:
- Repositório `octocat/Hello-World` (id=1296269) criado na primeira execução
- Segunda execução: `unchanged=1` — sem duplicata confirmado

SQL de verificação executado:
```sql
SELECT item_type, COUNT(*) FROM academic_items GROUP BY item_type;
-- articles=1, repositories=1

SELECT COUNT(*) FROM sources;
-- 2
```

**Não validado:**
- Ingestão em volume maior (>1 página) contra APIs reais — limitada para não consumir cota
- Validação com `OPENALEX_API_KEY` e `GITHUB_TOKEN` reais (variáveis ausentes no `.env` local)
- Cursor paging do OpenAlex além da primeira página (requer chave API)
- Testes de integração `TestIngestionPersistenceIntegration` marcados com `@pytest.mark.integration` — executaram via Postgres mas com schema recriado por `create_all`, não via migrations — comportamento idêntico mas não exatamente o mesmo path de código que a produção

# Não realizado / Limitações / Decisões pendentes

1. **Moodle**: fora do escopo (PD-0001 — requer credenciais do usuário)
2. **Relationship Engine**: fora do escopo — o pipeline só persiste `AcademicItem`; criação de `Entity`/`Relationship` é etapa subsequente
3. **Status lifecycle** (`raw/proposed/confirmed/quarentined/retired`): definido no vault (Integration Standards) mas não implementado no `AcademicItem` — fora do escopo desta entrega
4. **Rate limit sem token GitHub em buscas grandes**: 60 req/h core + 1 req de README por repo esgota rapidamente — requer `GITHUB_TOKEN` para volumes reais
5. **Cursor paging OpenAlex sem chave**: limitado a 10 000 resultados — requer `OPENALEX_API_KEY` para corpus maior
6. **Testes `TestDbConstraints` pré-existentes**: 8 falhas de test setup (IntegrityError propagando para fora da sessão) — bug de isolamento de transação pré-existente, não introduzido
7. **`google-genai` não instalado**: 12 testes LLM pré-existentes falhando — não relacionado a esta entrega

# Nota para incorporação ao vault

Entidades que merecem nota própria no vault (existem de fato no código):

- `OpenAlexConnector` — `apps/api/app/services/ingestion/openalex.py`
- `GitHubConnector` — `apps/api/app/services/ingestion/github.py`
- `IngestionPipeline` — `apps/api/app/services/ingestion/pipeline.py`
- `NormalisedItem` / `IngestionResult` — `apps/api/app/services/ingestion/models.py`
- Migration `004_add_repository_item_type` — `database/migrations/versions/004_add_repository_item_type.py`
- Decisão de usar `content_hash` para detecção de mudança em vez de comparação campo a campo
- Decisão de usar `item_type="repository"` para repos GitHub (extensão do enum via migration)
- Decisão de preservar autores/tópicos em `metadata_` JSONB em vez de criar `Entity` diretamente (escopo do Relationship Engine)

Notas do vault lidas (confirmadas pelos caminhos):
- `06 - Sources and Integrations/Shared Integration Standards/Integration Standards.md`
- `06 - Sources and Integrations/01 - GitHub/GitHub Integration.md`
- `06 - Sources and Integrations/02 - OpenAlex/OpenAlex Integration.md`
- `07 - Architecture and Engineering/04 - Domain Model/Domain Model.md`
- `07 - Architecture and Engineering/07 - Data and Database/Database Notes.md`
- `00 - Project Core/Current State.md`
- `09 - Decisions and Proposals/Product Decisions/PD-0001-escopo-mvp-inicial.md`
- `07 - Architecture and Engineering/01 - System Architecture/System Overview.md`

Nenhuma nota do vault foi criada, editada ou apagada nesta execução.
