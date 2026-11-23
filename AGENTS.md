# AGENTS.md — TRAMA Engineering Guide

Concise operational rules and engineering practices for AI agents working on the **TRAMA** repository.

## 1. Repository Overview

- `apps/web`: Next.js + TypeScript + Tailwind frontend.
- `apps/api`: FastAPI backend, SQLAlchemy models/repositories, services, and the durable worker (`scripts/discovery_worker.py`).
- `packages/shared`: shared TypeScript/Python contracts and types.
- `packages/{domain, connectors, ai}`: domain abstractions and connector interfaces.
- `database/migrations`: Alembic migrations (PostgreSQL + `pgvector`).

## 2. Git Workflow & Commits

- **Language**: all commit messages, branch names, PR titles/descriptions, and code comments must be written in **English**.
- **Branches**: use descriptive prefixes — `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `refactor/<topic>`, `chore/<topic>`. Never commit directly to `main`.
- **Commits**: follow **Conventional Commits** (`<type>(<scope>): <short imperative summary>`), e.g.:
  - `feat(projects): add project rename endpoint`
  - `fix(worker): release lease on deadline expiry`
  - `refactor(web): simplify source monitor polling`
  - `chore(deps): bump fastapi patch version`
- Keep commits focused, atomic, and free of untracked scratch files or temporary artifacts.

## 3. Documentation & Tests Policy

- **No standalone documentation**: do **not** create ad-hoc `.md` files, handoff notes, or reports in this repository. TRAMA's documentation and knowledge base live externally in **`trama-knowledge`**. Only edit existing repo docs (`README.md`, `AGENTS.md`, or files under `docs/`) when explicitly requested.
- **No standalone/ad-hoc tests**: do **not** leave scratch test scripts, temporary harnesses, or one-off validation scripts in the repository. Add or update tests strictly inside the existing suites (`apps/api/tests/` and `apps/web/tests/`) and only when they directly cover the change.

## 4. Core Development Practices

### Architecture & Execution Boundaries
- **FastAPI handlers stay fast and DB-only**: never perform external HTTP calls (GitHub, OpenAlex) or LLM calls inside HTTP request handlers. Enqueue work in PostgreSQL and let the durable worker (`apps/api/scripts/discovery_worker.py` / `app/services/execution.py`) execute it.
- **No DB sessions across `await` or network I/O**: keep SQLAlchemy transactions short and bounded; close/commit transactions before external I/O.
- **PostgreSQL is the durable queue**: respect existing lease, lock, deadline, and idempotency semantics. Do not introduce Redis/Celery or in-memory background tasks as a replacement.

### Data, Migrations & Contracts
- **Additive, safe migrations**: new Alembic migrations must be additive whenever possible and protect against accidental data loss on downgrade.
- **Keep shared contracts in sync**: when changing API payloads or status enums, update Pydantic schemas (`apps/api/app/schemas/`), shared types (`packages/shared/src/`), and frontend adapters (`apps/web/lib/`) together.
- **Never run tests against the local demo/user database**: backend integration and migration tests must target an isolated, disposable PostgreSQL database/schema.

### AI, Evidence & Security
- **Preserve epistemic transparency**: AI-generated prose is a reviewable hypothesis, never evidence. Always preserve literal source excerpts, locators, hashes, and timestamps separately, and keep LLM usage opt-in (`DISCOVERY_LLM_ENABLED`) with explicit fallback labeling and abstention support.
- **Never leak sensitive data**: never log credentials, API keys, `GITHUB_TOKEN`, raw external payloads, SQL parameters, or raw SDK errors. Return safe, structured error codes (`{error: {code, message, retryable}}`).
- **Validate external inputs strictly**: sanitize and validate external URLs, redirects, payload sizes, and timeouts.

### Code Quality & Verification
- Make minimal, surgical changes aligned with existing patterns and naming conventions.
- Before finishing a task, run the relevant checks for the touched stack:
  - **Frontend**: `node --test apps/web/tests/*.test.cjs` and `cd apps/web && npx tsc --noEmit`
  - **Backend**: targeted `pytest` in `apps/api/tests/` using a disposable test database.
- Never claim a check or build passed unless you ran it and observed it pass.
