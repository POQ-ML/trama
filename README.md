# TRAMA — Agente de Contexto Acadêmico

## 1. O que é
Plataforma de IA voltada a estudantes e pesquisadores que organiza projetos acadêmicos, conecta fontes públicas de código à literatura científica e acompanha mudanças de contexto com **rastreabilidade por evidências literais**.

## 2. Status atual
**MVP local funcional** (ambiente local compartilhado, sem autenticação multiusuário).

O fluxo principal já opera de ponta a ponta:
- **Projetos acadêmicos (`/`)**: criação e listagem de projetos + feed de mudanças recentes nas fontes vinculadas.
- **Fontes do projeto (`/projects/{id}`)**: vínculo de repositórios públicos do **GitHub** com visualização em **Mapa** e **Lista** (um mesmo repositório pode ser compartilhado entre projetos).
- **Descoberta com evidências (`/projects/{id}/sources/{sourceId}` e `/discoveries`)**: coleta de metadados e README do GitHub, busca conservadora de artigos no **OpenAlex** e geração de explicações estruturadas em português.
- **Explicações opt-in e transparência**: suporte a LLM via **Gemini** (`DISCOVERY_LLM_ENABLED=true`) ou fallback textual explicitamente rotulado, com possibilidade de abstenção semântica e trechos literais preservados dos dois lados (repositório + artigo).
- **Avaliação humana**: marcação de sugestões como **Relevante** ou **Não relevante**, preservada entre execuções.
- **Monitoramento contínuo**: checagem periódica em segundo plano (com ETags e rastreamento de rename por ID numérico), detecção de mudanças de contexto (`stale` / `source_changed`), histórico de avisos e reanálise.

## 3. Arquitetura
A fila de análises, leases, resultados, avaliações e avisos de monitoramento residem integralmente no **PostgreSQL** (não há Redis, Celery ou outro broker). Os handlers HTTP da API fazem apenas transações curtas de banco; coleta externa, busca e geração rodam no **worker**.

```
┌─────────────┐      ┌─────────────┐      ┌────────────────────────┐
│  web :3000  │ ───▶ │  api :8000  │ ───▶ │ postgres :5432         │
│ Next.js     │ HTTP │ FastAPI     │ SQL  │ pgvector + migrations  │
└─────────────┘      └─────────────┘      │ (001 → 007)            │
                                          └───────────▲────────────┘
                                                      │ leases / fila
                                          ┌───────────┴────────────┐
                                          │ worker (sem porta)     │
                                          │ GitHub · OpenAlex · IA │
                                          └────────────────────────┘
```

- `apps/web`: interface Next.js + TypeScript + Tailwind.
- `apps/api`: API FastAPI + SQLAlchemy + Alembic + worker (`scripts/discovery_worker.py`).
- `packages/shared`: tipos e contratos compartilhados (TS e Python).
- `packages/{domain, connectors, ai}`: abstrações de domínio e contratos futuros (conectores `moodle` e `ufc` ainda são interfaces sem implementação real).

## 4. Stack
Next.js + TypeScript + Tailwind · FastAPI + SQLAlchemy + Alembic · PostgreSQL (`pgvector/pgvector:pg16`) · Gemini SDK (opt-in) · Docker Compose.

## 5. Como executar
Copie o arquivo de ambiente e ajuste variáveis/credenciais locais se necessário:

```sh
cp .env.example .env
docker compose up --build -d postgres api worker web
docker compose logs -f api worker
```

- **Web**: `http://localhost:3000`
- **API health**: `http://localhost:8000/health` e `http://localhost:8000/api/v1/health`
- **Worker**: roda em segundo plano sem porta publicada (necessário para processar análises e checagens de monitor).

> **Observações importantes:**
> - Por padrão, `DISCOVERY_LLM_ENABLED=false` (usa explicação textual de contingência rotulada). Para ativar o Gemini, configure `DISCOVERY_LLM_ENABLED=true`, `LLM_PROVIDER=gemini` e `GEMINI_API_KEY` no ambiente do worker.
> - `NEXT_PUBLIC_API_URL` é embutido no build do `web`; alterá-lo exige reconstruir o serviço `web`.
> - Para portas alternativas, execução sem Docker e detalhes operacionais, consulte [docs/discovery-runtime.md](docs/discovery-runtime.md).

## 6. Como rodar testes
**Frontend:**
```sh
node --test apps/web/tests/*.test.cjs
cd apps/web && npx tsc --noEmit
```

**Backend:**
```sh
cd apps/api && pip install -r requirements.txt && pytest -q
```
*(Testes de integração/migrations exigem um PostgreSQL descartável configurado conforme [docs/project-navigation.md](docs/project-navigation.md).)*

## 7. Limites atuais e próximos passos
- **Fontes suportadas**: apenas repositórios públicos do GitHub (metadados + README) cruzados com OpenAlex. Conectores Moodle e UFC ainda não estão implementados.
- **Gestão de projetos**: ainda não há edição/exclusão de projetos ou remoção de fontes pela interface.
- **Busca**: triagem puramente lexical conservadora (sem busca vetorial ativa em `pgvector` ainda) e sem detecção de relações entre duas fontes do mesmo projeto.
- **Acesso**: workspace local compartilhado, sem autenticação multiusuário.

## 8. Documentação
- [Visão do produto](docs/product/vision.md)
- [Runtime de descoberta, worker e monitoramento](docs/discovery-runtime.md)
- [Navegação Dashboard → Projeto → Fonte](docs/project-navigation.md)
- [Contrato de descoberta](docs/discovery-contract.md)
- [Validação da descoberta](docs/discovery-validation.md)
- [Configuração de provedor LLM](docs/llm-provider.md)
