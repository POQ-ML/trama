# TRAMA — Agente de Contexto Acadêmico

## 1. O que é
Plataforma de IA que conecta fontes acadêmicas (Moodle, GitHub, UFC, OpenAlex)
e constrói contexto com rastreabilidade.

## 2. Objetivo
Ajudar o estudante a visualizar relações, mudanças e informações relevantes.

## 3. Status atual
**Initial Build** — base executável. Nenhuma feature do MVP implementada.

## 4. Arquitetura
```
┌─────────────┐      ┌─────────────┐      ┌──────────────────┐
│  web :3000  │ ───▶ │  api :8000  │ ───▶ │ postgres :5432   │
│ Next.js     │ /api │ FastAPI     │ SQL  │ users (mínimo)   │
└─────────────┘      └─────────────┘      └──────────────────┘
       │                    │  ▲ Alembic migrations
       │        ┌───────────┘  │ (database/migrations)
       ▼        ▼
  packages/{domain, connectors, ai, shared}  (abstrações, sem lógica real)
```

## 5. Stack
Next.js + TS + Tailwind · FastAPI + SQLAlchemy + Alembic · PostgreSQL · Docker Compose.

## 6. Estrutura
`apps/web`, `apps/api`, `packages/{ai,connectors,domain,shared}`,
`infrastructure/`, `database/`, `tests/`, `docs/`, `scripts/`.

## 7. Como executar
```sh
cp .env.example .env
docker compose up --build
```
- Web: http://localhost:3000
- API root: http://localhost:8000/health
- API v1: http://localhost:8000/api/v1/health

## 8. Configurar `.env`
Copie `.env.example`. Ajuste portas/credenciais se necessário.

## 9. Como rodar testes
```sh
cd apps/api && pip install -r requirements.txt && pytest -q
cd apps/web && npm install && npx tsc --noEmit
```

## 10. Roadmap resumido
MVP futuro: conectores reais → motor de contexto → detecção de mudanças →
relações + explicabilidade → timeline/mapa de contexto.
