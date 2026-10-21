# Ingestão de Dados — OpenAlex e GitHub

> Documentação do pipeline de ingestão do TRAMA.
> Data: 2026-10-19 | Status: implementado e validado

---

## Variáveis de ambiente

| Variável | Obrigatória | Comportamento quando ausente | Onde obter |
|---|---|---|---|
| `DATABASE_URL` | **Sim** | Falha imediata com mensagem clara | `docker-compose.yml` / DBA |
| `OPENALEX_API_KEY` | Não | Funciona com 10 req/s e paginação básica (≤10 000 resultados); log de aviso | https://openalex.org/settings/api |
| `OPENALEX_EMAIL` | Não | Não entra no "polite pool" da OpenAlex; log de aviso | Seu e-mail de contato |
| `GITHUB_TOKEN` | Não | 60 req/h em vez de 5 000 req/h; log de aviso | https://github.com/settings/tokens (escopo `public_repo`) |
| `TRAMA_INGESTION_LIVE_TEST` | Não (opt-in) | Testes de integração com APIs reais não executam | Setar para `1` para habilitá-los |

**Nunca passe credenciais como argumentos de linha de comando.** Configure-as em `.env` (fora do Git).

---

## Passo a passo — ambiente local com Docker

### 1. Subir serviços

```bash
docker compose up -d postgres
docker compose exec postgres pg_isready -U trama
```

### 2. Aplicar migrations

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
  python -m alembic upgrade head
python -m alembic current   # deve mostrar: 004_add_repository_item_type (head)
```

### 3. Configurar variáveis

Edite `.env` na raiz do projeto (nunca commite este arquivo):

```
OPENALEX_API_KEY=sua_chave_aqui
OPENALEX_EMAIL=seu_email@exemplo.com
GITHUB_TOKEN=ghp_seu_token_aqui
```

As variáveis opcionais — sem elas a ingestão funciona com limites menores.

### 4. Executar ingestão — OpenAlex

```bash
cd apps/api

# Filtrar por DOI específico (1 resultado, bom para teste)
DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
  python scripts/ingest.py openalex --filter "doi:10.7717/peerj.4375" --max-pages 1

# Busca livre (limitar páginas em teste)
DATABASE_URL=... python scripts/ingest.py openalex --query "machine learning" --max-pages 2

# Filtrar por instituição (ID OpenAlex)
DATABASE_URL=... python scripts/ingest.py openalex --filter "institution.id:I4390" --max-pages 5
```

### 5. Executar ingestão — GitHub

```bash
# Repositório explícito
DATABASE_URL=... python scripts/ingest.py github --repos "octocat/Hello-World"

# Múltiplos repositórios
DATABASE_URL=... python scripts/ingest.py github --repos "fastapi/fastapi,tiangolo/sqlmodel"

# Busca por tópico
DATABASE_URL=... python scripts/ingest.py github --query "topic:fastapi language:python" --max-pages 1

# Todos os repos públicos de uma org
DATABASE_URL=... python scripts/ingest.py github --org "fastapi" --max-pages 2
```

### 6. Verificar idempotência (re-executar com os mesmos dados)

A segunda execução idêntica deve mostrar `unchanged=N, created=0`:

```bash
DATABASE_URL=... python scripts/ingest.py openalex --filter "doi:10.7717/peerj.4375" --max-pages 1
# Esperado: [openalex] fetched=1 created=0 updated=0 unchanged=1 skipped=0 errors=0
```

### 7. Verificar no banco

```sql
-- Registros criados
SELECT item_type, COUNT(*) FROM academic_items GROUP BY item_type;

-- Procedência de um artigo
SELECT external_id, title, original_url, captured_at, metadata_->>'doi'
FROM academic_items WHERE item_type = 'article' LIMIT 5;

-- Procedência de um repositório
SELECT external_id, title, original_url, captured_at, metadata_->>'language'
FROM academic_items WHERE item_type = 'repository' LIMIT 5;

-- Fontes registradas
SELECT provider, name, canonical_id FROM sources;
```

### 8. Rodar testes

```bash
cd apps/api

# Apenas unitários (sem rede, sem banco obrigatório)
python -m pytest tests/test_ingestion_openalex.py tests/test_ingestion_github.py tests/test_ingestion_persistence.py -v

# Suíte completa (com banco)
DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
TEST_DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
  python -m pytest tests/ -v
```

---

## Mapeamento de campos

### OpenAlex → AcademicItem

| Campo OpenAlex | Destino no modelo | Observação |
|---|---|---|
| `id` (URL) | `external_id` | Ex.: `W2741809807` (extraído da URL) |
| `title` / `display_name` | `title` | `title` preferido |
| `doi` (URL) | `metadata_['doi']` | Normalizado para `10.xxxx/yyy` |
| `publication_date` | `original_date` | UTC |
| `primary_location.landing_page_url` | `original_url` | URL canônica |
| `authorships[].author` | `metadata_['authors']` | `{id, display_name, orcid}` |
| `topics[]` | `metadata_['topics']` | `{id, display_name, score}` |
| `concepts[]` | `metadata_['concepts']` | `{id, display_name, score}` |
| `keywords[]` | `metadata_['keywords']` | `{id, display_name, score}` |
| `abstract_inverted_index` | `description` | Reconstruído de índice invertido |
| `cited_by_count` | `metadata_['cited_by_count']` | — |
| `open_access` | `metadata_['open_access']` | Objeto OA completo |
| — | `item_type` | Fixo: `"article"` |
| — | `captured_at` | UTC no momento da coleta |

### GitHub → AcademicItem

| Campo GitHub | Destino no modelo | Observação |
|---|---|---|
| `id` (int) | `external_id` | Convertido para `str` |
| `full_name` | `title` | Ex.: `fastapi/fastapi` |
| `description` | `description` | `None` quando ausente |
| `html_url` | `original_url` | URL pública |
| `pushed_at` / `updated_at` | `original_date` | `pushed_at` preferido |
| README decodificado | `metadata_['readme']` | Truncado em 50 000 chars |
| `topics[]` | `metadata_['topics']` | Lista de strings |
| `language` | `metadata_['language']` | Linguagem principal |
| `owner.login`, `owner.type` | `metadata_['owner']` | `{login, type}` |
| `created_at` | `metadata_['created_at']` | ISO 8601 UTC |
| `stargazers_count` | `metadata_['stargazers_count']` | — |
| — | `item_type` | Fixo: `"repository"` |
| — | `captured_at` | UTC no momento da coleta |

---

## Deduplicação e atualização

**Chave natural:** `(source_id, external_id)` — enforçada por `UNIQUE` constraint no banco (`migration 003`).

**Regra de update:** um registro existente é atualizado **somente** quando seu `content_hash` (SHA-256 de campos de conteúdo) muda. Campos voláteis como `captured_at` não disparam update.

**Preservação de proveniência:** o `captured_at` original (primeira captura) é preservado em `metadata_['captured_at']` mesmo após updates. `metadata_['last_seen_at']` registra a última vez que o item foi observado.

**Granularidade transacional:** por item. Falha em um item não desfaz os anteriores já commitados.

---

## Política de retry e rate limit

### OpenAlex
- HTTP 429 com `Retry-After`: aguarda o valor do header (máx. 60s)
- HTTP 429 sem header: backoff exponencial (1s → 2s → 4s … → 16s)
- HTTP 5xx / timeout / conexão: backoff exponencial, máx. 3 tentativas
- HTTP 4xx (não-429): erro permanente, não retenta

### GitHub
- HTTP 429 ou 403 com `Retry-After`: aguarda o header
- HTTP 403 sem `Retry-After`: aguarda até reset via `X-RateLimit-Reset`
- HTTP 404 / 451: repositório inacessível — skipa sem abortar os demais
- HTTP 5xx / timeout: backoff exponencial, máx. 3 tentativas
- Repositório privado retornado: ignorado com aviso em log

---

## Limitações conhecidas e decisões pendentes

1. **Cursor paging OpenAlex sem chave**: sem `OPENALEX_API_KEY`, paginação limitada a 10 000 resultados (restrição da API).
2. **Status do lifecycle** (`raw/proposed/confirmed`): definido no vault (Integration Standards) mas não implementado no `AcademicItem` — fora do escopo do pipeline; responsabilidade do Relationship Engine.
3. **Criação de entidades canônicas**: o pipeline persiste apenas `AcademicItem`. A criação de `Entity` (autores, tópicos) é responsabilidade do Relationship Engine.
4. **Moodle**: fora do escopo desta entrega (requer credenciais do usuário — PD-0001).
5. **Rate limit do GitHub sem token**: 60 req/h para operações core + requisição extra de README por repo — em buscas grandes, pode esgotar rapidamente sem token.

### Execução direta e detecção de alterações

A partir de `apps/api`, tanto `python scripts/ingest.py github --repos owner/repo`
quanto `python -m scripts.ingest github --repos owner/repo` funcionam sem configurar
`PYTHONPATH`. Defina `DATABASE_URL` antes da execução.

Os hashes incluem URL e data originais e os metadados de conteúdo normalizados,
incluindo README (também quando antes ausente), idioma, tópicos e demais campos
descritivos. Excluem `captured_at`, `last_seen_at` e contadores de popularidade
(`stargazers_count`, `forks_count`, `cited_by_count`). Alterações apenas nesses
contadores não disparam atualização. A primeira coleta após esta correção pode
atualizar hashes antigos uma vez; a primeira captura continua preservada.

`--org LOGIN` tenta a organização e, apenas após 404 na primeira página, tenta
os repositórios públicos do usuário. Falhas de autenticação, rede, limite de taxa
ou retries esgotados são contabilizadas em `errors` e retornam código CLI 1.
Falhas por repositório, inclusive na coleta do README, permitem continuar os demais;
falhas de página encerram a paginação. Itens já commitados são preservados.
404/451 de repositórios e README ausente continuam sendo skips legítimos.
