# TRAMA — Architecture Overview (Initial Build)

Monorepo simples: `apps/web` (Next.js) → `apps/api` (FastAPI) → PostgreSQL.

```
[ web :3000 ] --NEXT_PUBLIC_API_URL--> [ api :8000 ] --> [ postgres :5432 ]
     |                                      |
 packages/shared                     packages/domain
                                     packages/connectors (interfaces)
                                     packages/ai (interfaces)
```

Decisões: sem microserviços, sem K8s, sem filas. Apenas base executável.
Evolução prevista: conectores reais, motor de contexto, timeline/mapa.
