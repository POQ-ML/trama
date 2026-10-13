# Camada de Persistência — Fase 1 (MVP)

> Data: 2026-10-12 | Status: implementado

---

## O que foi feito

Implementação da camada de persistência do TRAMA para o MVP, cobrindo fontes, itens importados, entidades do mapa, relações e evidências.

### Modelos SQLAlchemy (`apps/api/app/models/`)

| Arquivo | Tabela | Responsabilidade |
|---|---|---|
| `source.py` | `sources` | Instância de integração (GitHub, Moodle, OpenAlex) |
| `academic_item.py` | `academic_items` | Registro normalizado importado de uma fonte |
| `entity.py` | `entities` | Nó canônico do mapa (person, project, topic, event, source) |
| `relationship.py` | `relationships` | Aresta tipada entre entidades |
| `evidence.py` | `evidences` | Material rastreável que sustenta uma relação |
| `types.py` | — | Tipo `TsVector` compatível com Postgres e SQLite |

**Restrições implementadas no banco:**

- `CHECK` para enums fechados: `provider`, `item_type`, `entity_type`, `relationship_type`, `status`
- `CHECK source_id <> target_id` em `relationships` (sem auto-loops)
- `UNIQUE (provider, canonical_id)` em `sources`
- `UNIQUE (source_id, external_id)` em `academic_items`
- `UNIQUE (entity_type, label)` em `entities`
- `UNIQUE (source_id, target_id, relationship_type)` em `relationships`
- FKs com `RESTRICT` (academic_items → sources, evidences → academic_items) e `CASCADE` (relationships → entities, evidences → relationships)
- `owner_id` em `sources`: FK nullable para `users` — preparado para auth futura, sem enforçar prematuramente

**Tipos de relação (PD-0002, conjunto fechado):**
```
topic_source   — topic ↔ source
project_event  — project ↔ event
project_topic  — project ↔ topic
```

**Status de relação:** `pending | confirmed | rejected` — `silenced` é explicitamente excluído.

### Migrations (`database/migrations/versions/`)

| Arquivo | Revisão | O que faz |
|---|---|---|
| `001_initial.py` | `001_initial` | Tabela `users` + extensão `pgcrypto` (existente) |
| `002_pgvector.py` | `002_pgvector` | Habilita extensão `vector` (pgvector) |
| `003_persistence_layer.py` | `003_persistence_layer` | Cria as 5 tabelas com todos os constraints |

Cadeia: `001 → 002 → 003`

### pgvector (ADR-0004)

- Imagem Docker alterada de `postgres:16` para `pgvector/pgvector:pg16`
- Extensão habilitada via migration `002`
- Coluna `vector` **não adicionada** — dimensão e modelo de embeddings são decisão em aberto (ADR-0004)
- Fallback FTS: coluna `search_vector TSVECTOR` com índice GIN em `academic_items`
- Dependência adicionada: `pgvector>=0.3.5` em `requirements.txt`

### Testes (`apps/api/tests/`)

| Arquivo | Tipo | Testes |
|---|---|---|
| `test_models_persistence.py` | Unitário (SQLite in-memory) | 46 testes |
| `test_health.py` | Unitário | 2 testes (sem regressão) |
| `test_migrations_integration.py` | Integração (Postgres real) | 18 testes, auto-skip sem Docker |

**Cobertura unitária:** criação dos 5 modelos, associações ORM, integridade referencial, rejeição de FKs inválidas, cascade/restrict, unicidade, constantes `VALID_*`, pares de tipos de entidade (9 combinações parametrizadas), múltiplas evidências por relação, status default, score nullable.

**Cobertura de integração (requer Postgres):** cadeia de migrations em base limpa, CHECK constraints no DB, pgvector disponível, unicidade, self-loop via CHECK no banco.

---

## Por que as migrations são tão grandes

A pergunta é legítima. A `003_persistence_layer.py` tem ~200 linhas para criar 5 tabelas, e há uma razão concreta para isso.

**Alembic não suporta `ALTER TABLE ADD CONSTRAINT` de forma portável em SQLAlchemy** para constraints nomeadas em `create_table`. Cada `CheckConstraint`, `UniqueConstraint` e `ForeignKey` precisa ser declarado *dentro* do `op.create_table()` como argumentos posicionais — não como chamadas separadas depois. Isso força a definição completa de cada tabela em um único bloco.

Além disso, o projeto escolheu **não usar `autogenerate`** (o Alembic comparando modelos com o banco). O motivo: `autogenerate` não detecta `CheckConstraint` com nomes customizados de forma confiável, e os modelos têm tipos PostgreSQL específicos (`JSONB`, `TSVECTOR`) que precisariam de configuração adicional para o autogenerate funcionar corretamente.

O que aumenta o tamanho:
1. **Cada coluna UUID com FK** precisa de `postgresql.UUID(as_uuid=True)` + `sa.ForeignKey(...)` — verbose mas necessário para o tipo correto no Postgres
2. **Timestamps TIMESTAMPTZ** exigem `sa.DateTime(timezone=True)` + `server_default=sa.func.now()` em cada tabela
3. **Índices separados** via `op.create_index()` — o Alembic não cria índices compostos ou GIN dentro do `create_table`
4. **Docstring longa** que documenta todas as decisões de design — isso é intencional para rastreabilidade, não inchaço de código

**A alternativa** seria dividir em uma migration por tabela (`003_sources`, `004_academic_items`, etc.), mas isso complica o downgrade e fragmenta uma mudança coesa. Para 5 tabelas interdependentes criadas juntas, um único arquivo é mais claro do que 5 arquivos que precisam ser aplicados em ordem específica.

---

## Como rodar

### Pré-requisitos

- Docker Desktop rodando
- Python 3.11+ com `pip`

### 1. Instalar dependências

```bash
cd apps/api
pip install -r requirements.txt
```

### 2. Subir o banco

```bash
# Na raiz do projeto
docker compose up -d postgres
```

Aguarda o healthcheck: `pg_isready -U trama` deve retornar OK.

### 3. Rodar as migrations

```bash
cd apps/api
alembic upgrade head
```

Resultado esperado:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial, Initial minimal schema.
INFO  [alembic.runtime.migration] Running upgrade 001_initial -> 002_pgvector, Enable pgvector extension.
INFO  [alembic.runtime.migration] Running upgrade 002_pgvector -> 003_persistence_layer, Persistence layer ...
```

### 4. Rodar os testes unitários (sem Docker)

```bash
cd apps/api
pytest tests/test_models_persistence.py tests/test_health.py -v
```

Esperado: **48 passed**.

### 5. Rodar os testes de integração (requer Postgres)

```bash
# Postgres já deve estar rodando (passo 2)
cd apps/api
TEST_DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama \
  pytest tests/test_migrations_integration.py -v -m integration
```

Esses testes verificam: cadeia de migrations em base limpa, extensão `vector` disponível, CHECK constraints do banco, unicidade, self-loop.

### 6. Subir a stack completa

```bash
docker compose up
```

A API sobe em `http://localhost:8000`. O comando de startup já inclui `alembic upgrade head` antes do uvicorn.

### Downgrade (dev/CI apenas)

```bash
cd apps/api
alembic downgrade 001_initial   # remove as 5 tabelas, mantém users
alembic downgrade base          # remove tudo incluindo users
```

---

## Pendências em aberto

| Item | Origem | Próximo passo |
|---|---|---|
| Dimensão e modelo de embeddings (coluna `vector`) | ADR-0004 — pergunta aberta | Decidir modelo local vs. OpenAI; criar `004_add_embeddings` |
| Chunking e `top_k` para pgvector | ADR-0004 | Definir na implementação do `RelationshipEngine` |
| `Source.owner_id` como NOT NULL | Auth system não existe | Criar migration quando o sistema de auth for implementado |
| Escolha do LLM para explicação de scoring | PD-0002 Q01 | Análise de custo pendente |
| Validação de pares de tipos por trigger no banco | `VALID_TYPE_PAIRS` hoje só na camada de serviço | Avaliar se CHECK ou trigger é mais adequado |
