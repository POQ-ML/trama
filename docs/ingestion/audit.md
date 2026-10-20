# Auditoria de Persistência — Pipeline de Ingestão

> Data: 2026-10-19 | Status: concluída | Autora: pipeline de ingestão (FASE 1)

---

## 1. Estruturas existentes reutilizadas

| Modelo | Tabela | Papel na ingestão |
|---|---|---|
| `Source` | `sources` | Uma instância por fonte (ex.: `openalex/polite-pool`, `github/search`). Reutilizado diretamente. |
| `AcademicItem` | `academic_items` | Registro normalizado de cada publicação (OpenAlex) ou repositório (GitHub). Chave natural: `(source_id, external_id)`. |
| `Entity` | `entities` | Nós canônicos do mapa. Criados pelos conectores apenas para autores/tópicos quando relevante (escopo do Relationship Engine, não do pipeline de ingestão). |
| `Relationship`, `Evidence` | `relationships`, `evidences` | Fora do escopo do pipeline de ingestão — responsabilidade do Relationship Engine. |

**Constraint de unicidade já existente e reutilizada:**
- `UNIQUE (source_id, external_id)` em `academic_items` — garante idempotência sem migration adicional.
- `UNIQUE (provider, canonical_id)` em `sources` — garante que a fonte não seja duplicada.

---

## 2. Mapeamento de campos por fonte

### 2.1 OpenAlex → AcademicItem

| Campo OpenAlex | Campo normalizado | Destino | Observação |
|---|---|---|---|
| `id` (URL) | `external_id` | `academic_items.external_id` | Ex.: `W2741809807` extraído da URL `https://openalex.org/W...` |
| `title` / `display_name` | `title` | `academic_items.title` | `title` preferido; fallback `display_name` |
| `doi` (URL) | `metadata_.doi` | `academic_items.metadata` JSONB | URL completa; normalizada como `10.xxxx/yyy` |
| `publication_date` | `original_date` | `academic_items.original_date` | ISO 8601 → datetime UTC |
| `primary_location.landing_page_url` | `original_url` | `academic_items.original_url` | URL canônica do trabalho |
| `authorships[].author` | `metadata_.authors` | `academic_items.metadata` JSONB | Lista `{id, display_name, orcid}` |
| `topics[]` | `metadata_.topics` | `academic_items.metadata` JSONB | `{id, display_name, score}` |
| `concepts[]` | `metadata_.concepts` | `academic_items.metadata` JSONB | `{id, display_name, score}` |
| `keywords[]` | `metadata_.keywords` | `academic_items.metadata` JSONB | `{id, display_name, score}` |
| `abstract_inverted_index` | `description` | `academic_items.description` | Reconstruído de índice invertido; `None` se ausente |
| `type` | `metadata_.work_type` | `academic_items.metadata` JSONB | Ex.: `article`, `book-chapter` |
| `cited_by_count` | `metadata_.cited_by_count` | `academic_items.metadata` JSONB | Contagem de citações |
| `open_access` | `metadata_.open_access` | `academic_items.metadata` JSONB | Objeto OA completo |
| — | `item_type` | `academic_items.item_type` | Fixo: `"article"` |
| — | `captured_at` | `academic_items.captured_at` | UTC no momento da coleta |
| — | `content_hash` | `academic_items.content_hash` | SHA-256 de campos de conteúdo |

### 2.2 GitHub → AcademicItem

| Campo GitHub | Campo normalizado | Destino | Observação |
|---|---|---|---|
| `id` (int) | `external_id` | `academic_items.external_id` | Convertido para `str` |
| `full_name` | `title` | `academic_items.title` | Ex.: `fastapi/fastapi` |
| `description` | `description` | `academic_items.description` | `None` quando ausente |
| `html_url` | `original_url` | `academic_items.original_url` | URL pública do repositório |
| `pushed_at` / `updated_at` | `original_date` | `academic_items.original_date` | `pushed_at` preferido |
| README decodificado | `metadata_.readme` | `academic_items.metadata` JSONB | Truncado em 50 000 chars se muito longo |
| `topics[]` | `metadata_.topics` | `academic_items.metadata` JSONB | Lista de strings |
| `language` | `metadata_.language` | `academic_items.metadata` JSONB | Linguagem principal |
| `owner.login`, `owner.type` | `metadata_.owner` | `academic_items.metadata` JSONB | `{login, type}` |
| `created_at` | `metadata_.created_at` | `academic_items.metadata` JSONB | ISO 8601 UTC |
| `stargazers_count` | `metadata_.stargazers_count` | `academic_items.metadata` JSONB | Contagem de estrelas |
| `name` | `metadata_.name` | `academic_items.metadata` JSONB | Nome simples do repo |
| — | `item_type` | `academic_items.item_type` | Fixo: `"repository"` (migration 004) |
| — | `captured_at` | `academic_items.captured_at` | UTC no momento da coleta |
| — | `content_hash` | `academic_items.content_hash` | SHA-256 de campos de conteúdo |

---

## 3. Lacunas identificadas e decisões

### 3.1 `item_type = "repository"` não existia no CHECK constraint

**Lacuna:** `CHECK item_type IN ('article', 'course', 'opportunity', 'activity')` —
sem valor para repositório GitHub.

**Avaliação:** campos genéricos (`metadata_` JSONB) não resolvem isso — a restrição está
no banco, não na camada de aplicação.

**Decisão:** migration `004_add_repository_item_type` adiciona `'repository'` ao CHECK.
Reversível com guarda contra dados existentes.

### 3.2 Autores de publicações OpenAlex

**Lacuna:** não há tabela de autores separada (apenas `Entity.entity_type = 'person'`
no grafo de conhecimento). O pipeline de ingestão **não** cria entidades — isso é
responsabilidade do Relationship Engine.

**Decisão:** autores preservados em `metadata_.authors` JSONB no `AcademicItem`.
O campo genérico resolve para o pipeline; o Relationship Engine pode ler dali.

### 3.3 Resumo em índice invertido (OpenAlex `abstract_inverted_index`)

**Lacuna:** OpenAlex retorna o resumo em formato de índice invertido (`{word: [pos, ...]}`),
não como texto plano.

**Decisão:** reconstruir para texto em ordem de posição no conector. Se ausente (`None`),
`description` fica `None`. Documentado no conector.

### 3.4 README do GitHub (tamanho excessivo)

**Lacuna:** READMEs podem ter centenas de KB.

**Decisão:** truncar em 50 000 caracteres com marcador `[truncated]`. Valor configurável.
Ausência de README (404) tratada com `None` — não aborta a coleta.

### 3.5 Repositórios privados

**Lacuna:** token GitHub pode dar acesso a repos privados.

**Decisão:** filtro explícito `visibility=public` em todas as queries de busca.
Repositório individual acessado via API: se `private=True`, é ignorado com log de aviso.

---

## 4. Estruturas não alteradas (confirmadas suficientes)

- `Source.metadata_` JSONB: absorve config do conector (rate limits, filtros, etc.)
- `AcademicItem.content_hash`: SHA-256 de conteúdo — usado para detectar mudanças sem re-parsear
- `AcademicItem.captured_at`: timestamp UTC de captura — imutável após criação
- `UniqueConstraint("source_id", "external_id")`: garante idempotência no banco

---

## 5. Conflitos vault × código

| Item | Vault | Código | Tratamento |
|---|---|---|---|
| `item_type` para repositórios | Não define | `CHECK` não incluía `repository` | Migration 004 adicionada |
| Estado do lifecycle (`raw/proposed/confirmed/quarentined/retired`) | Integration Standards define 5 estados | `AcademicItem` não tem coluna `status` | Fora do escopo do pipeline — status é gerenciado pelo Relationship Engine via `Entity`/`Relationship`. Registrado como limitação. |
| `SourceItem` imutável após criação | Domain Model / Integration Standards | `AcademicItem` não tem constraint de imutabilidade no banco | Imutabilidade enforçada na camada de serviço (não atualiza título/descrição se hash mudou — cria novo item). |

---

## 6. Notas do vault que influenciaram decisões

- `06 - Sources and Integrations/Shared Integration Standards/Integration Standards.md`: anatomia do conector, idempotência, evidência/proveniência
- `06 - Sources and Integrations/01 - GitHub/GitHub Integration.md`: tipos de dados, restrição a dados públicos
- `06 - Sources and Integrations/02 - OpenAlex/OpenAlex Integration.md`: propósito, campos de interesse
- `07 - Architecture and Engineering/04 - Domain Model/Domain Model.md`: distinção Source × Entity, imutabilidade de brutos
- `07 - Architecture and Engineering/07 - Data and Database/Database Notes.md`: estrutura ER proposta
