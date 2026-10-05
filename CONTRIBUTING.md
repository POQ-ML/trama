# CONTRIBUTING — TRAMA

## Estrutura
- `apps/web`: Next.js
- `apps/api`: FastAPI
- `packages/domain|connectors|ai|shared`: abstrações
- `database/migrations`: Alembic
- `docs/`, `tests/`, `scripts/`, `infrastructure/`

## Branches
`main` estável. Feature: `feat/<tema>`. Fix: `fix/<tema>`.

## Commits
Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).

## PRs
Use o template. Descreva objetivo, alterações, como testar e breaking changes.

## Rodar localmente
```sh
cp .env.example .env
docker compose up --build
```
- Web: http://localhost:3000
- API: http://localhost:8000/health e http://localhost:8000/api/v1/health
