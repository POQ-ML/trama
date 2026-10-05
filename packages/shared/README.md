# shared

Pacote bilíngue (proposital, ainda sem build unificado):

- Python (`config.py`, `logging.py`, `types.py`): helpers stdlib,
  zero-dependência — `get_env(key, default)`, `get_logger(name)`,
  aliases `EntityId`/`ISODateTime` + `Page` genérica.
- TypeScript (`src/index.ts`, pacote `@trama/shared`): tipos
  compartilhados com o frontend (ex: `HealthStatus`).

A unificação do build (workspaces) fica para o MVP.
