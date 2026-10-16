# LLM Provider Abstraction (MVP)

Camada de integração com LLM da TRAMA: interface provider-independent,
adapter Gemini Flash (free tier nos testes) e telemetria de uso.
Localização canônica (runtime): `apps/api/app/services/llm/`.

## Por que `app.services.llm` e não `packages/ai`

ADR-0005 (vault `trama-knowledge`) manda isolar o provedor atrás de interface e cita `packages/ai`,
mas `packages/ai` hoje é puro (zero deps, ver `packages/ai/README.md`) e —
decisivo — **não entra na imagem Docker** (`apps/api/Dockerfile` só faz
`COPY apps/api/`) nem no `pytest` (`apps/api/pytest.ini`: `pythonpath = .`).
Colocar o runtime lá o deixaria inimportável. A menor integração consistente
é `app.services.llm`; os contratos foram desenhados para mover a
`packages/ai` sem reescrever consumidores quando ADR-0002 (packaging do
monorepo) for decidida. Decisão registrada na docstring de
`app/services/llm/__init__.py`.

## Abstração (`base.py`) e responsabilidades

| Nome | Papel |
|---|---|
| `LLMProvider` | ABC. `await generate(LLMRequest) -> LLMResponse`. Lógica de negócio depende só dela — nunca do SDK. |
| `LLMRequest` | `user_input` (obrigatório, não-vazio), `system_instruction?`, `max_output_tokens?`, `response_mime_type?` + `response_json_schema?` (saída estruturada), `request_id` auto. |
| `LLMResponse` | `text`, `provider`, `model`, `usage`, `request_id`, `retry_count`. |
| `LLMUsage` | `input/output/total_tokens: int \| None`. `None` = não reportado. **Nunca inventado.** |
| `LLMError` | Falha normalizada e segura: `category` (`auth`, `invalid_request`, `rate_limit`, `quota_exhausted`, `timeout`, `transient`, `empty_response`, `unknown`), `provider`, `model`, `retry_count`, `is_retryable`. Mensagem sem chave, sem prompt/resposta, sem payload bruto. |

`FakeLLMProvider` (`fake.py`): determinístico, sem rede/chave, para testes e
comportamento provider-independent.

## Adapter Gemini (`gemini.py`)

- SDK oficial `google-genai` (`pip install -r requirements.txt`).
- Via estável `client.aio.models.generate_content` (async, `usage_metadata`
  de primeira classe). `temperature/top_p/top_k` **não** são enviados
  (modelos 3.6+ os ignoram).
- Resposta vazia → `LLMError(empty_response)`. Uso extraído de
  `prompt_token_count / candidates_token_count / total_token_count`.
- Classificação: 401/403→`auth`; 400/404/422→`invalid_request`;
  429→`rate_limit` (com retry limitado) ou `quota_exhausted` (mensagem com
  quota/daily/RPD — **sem retry**); timeout→`timeout`; 5xx→`transient`.
- Retry limitado (`LLM_MAX_RETRIES`, default 2) com backoff exponencial
  limitado (≤2s) **só** para `transient`/`timeout`/`rate_limit`. Nunca para
  `auth`, `invalid_request`, `quota_exhausted`, `empty_response`.
- `client_factory` injetável para testes sem rede.

## Configuração

Fonte canônica: `app.core.config.Settings` (pydantic-settings). `LLMConfig`
(`config.py`) lê os mesmos nomes sem importar `Settings` (evita ciclo,
testável). Validação **só na borda** (`create_provider`/`require_provider`):
sem chave, erro `AUTH` acionável — o boot nunca quebra sem LLM.

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=2
LLM_MAX_OUTPUT_TOKENS=1024
LLM_TELEMETRY_ENABLED=true
```

- `LLM_MODEL` default **`gemini-3.5-flash-lite`**, verificado na lista oficial
  (https://ai.google.dev/gemini-api/docs/models, atualizada em 2026-10-13):
  recomendado para projetos novos, rápido e elegível ao free tier.
  Alternativa documentada: `gemini-3.8-flash`. ADR-0005 citava só
  "Flash/Flash-Lite" genericamente — **discrepância registrada, não nova
  decisão** (ADR-0005 e REQ-0021 vivem no vault `trama-knowledge`, em
  `09 - Decisions and Proposals/`, não neste repo): nenhum modelo final de
  produto é afirmado (eval pendente).
- `.env.example` (raiz) mantém `GEMINI_API_KEY=` vazio; `.env` é gitignored.
  Chave nunca em código frontend, logs ou controle de versão.
- `docker-compose.yml` repassa as sete vars ao serviço `api` com os mesmos
  defaults (sem elas o container não enxergaria a chave do `.env` local).

## Testes

```sh
cd apps/api && pip install -r requirements.txt && pytest -q
# só LLM:
pytest tests/test_llm.py -q
```

`tests/test_llm.py`: config válida, credencial ausente, normalização,
uso presente/ausente, saída vazia, auth, rate-limit (retry→sucesso),
quota (sem retry), timeout/transient com limite de retry, saída estruturada,
telemetria ok/erro, sigilo nos logs, contrato do fake. **Zero rede/chave.**

## Smoke test ao vivo (opt-in, pulado por padrão)

```sh
export GEMINI_API_KEY='<sua-chave>'   # nunca commitar
export TRAMA_LLM_LIVE_TEST=1
python scripts/llm_smoke.py           # dados 100% sintéticos
```

Sem `TRAMA_LLM_LIVE_TEST=1` o script só informa o skip e sai 0.
**Free tier:** presumir que o conteúdo pode ser usado para melhoria dos
produtos (ADR-0005/REQ-0021 no vault `trama-knowledge`) — usar só dados sintéticos/próprios, nunca de
terceiros; sem loops de retry que gastem quota.

## Telemetria (`telemetry.py`)

`await observe(provider, request, sink?) -> LLMResponse` envolve **qualquer**
`LLMProvider` (não só Gemini). Registro por request:

`request_id, provider, model, started_at, duration_ms, input/output/total_tokens, success, error_category?, retry_count, cost_usd=None`.

- `LoggingTelemetrySink` (default): log estruturado só com contagens/ outcome
  via `app.core.logging` (`trama.llm.telemetry`). Nunca prompt, resposta,
  dado acadêmico pessoal ou chave.
- `InMemoryTelemetrySink`: para asserts em testes.
- **Custo: sempre indisponível (`None`), nunca zero** — sem dado confiável
  de preço em runtime (métrica 6 de `Success Metrics` usa fatura+logs, pós-llm
  definido). Métricas ausentes ficam `None`, nunca estimadas.
- Sem tabelas/migrations (requisito da tarefa). Latência alimenta a métrica 7.

## Adicionar outro provedor (ex. Haiku pós-eval)

1. Criar `app/services/llm/<novo>.py` com classe `XLLMProvider(LLMProvider)`
   implementando `generate` (normalizar texto/uso/erros para os contratos).
2. Registrar em `create_provider` (novo valor de `LLM_PROVIDER` + var de chave).
3. Reutilizar `observe()` — telemetria funciona sem mudança.
4. Cobrir com testes via doubles (como `test_llm.py`), sem rede.
Consumidores seguem importando só `LLMProvider/LLMRequest/observe`.

## Limitações conhecidas

- `temperature/top_p/top_k` não configuráveis (ignorados pelos modelos 3.6+).
- Uso depende do que o provedor reporta; `total` pode divergir de `in+out`
  (repasse fiel, sem reconciliação).
- Custo indisponível em runtime (ver acima).
- Free tier: limites (RPM/TPM/RPD) variam e RPD zera à meia-noite do Pacífico;
  `rate_limit` faz backoff limitado, `quota_exhausted` não retenta.
- Sem streaming, multi-turno ou function-calling (fora do escopo).
- Modelo final do produto exige nova decisão pós-eval (ADR-0005 no vault, pergunta aberta).
