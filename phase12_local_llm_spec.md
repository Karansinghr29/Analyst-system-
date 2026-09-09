# Phase 12 Local LLM Spec

Ollama is a **named adapter** behind the existing `LLMProvider` / `ProviderConfig`
abstraction. It is not a second analytics path.

## 1. Roles (unchanged from Phase 4)

Ollama may only:

1. Propose a concept and intent (validated; invalid never executes)
2. Re-word a finished answer skeleton (guarded; violations discard the prose)

The deterministic engine remains the sole authority for calculation, definitions,
filtering, aggregation, trust, conflicts, validation, evidence, and recommendations.

## 2. Transport

Reuse `OpenAICompatibleProvider`. Destination:

`{OLLAMA_BASE_URL}/chat/completions` with `OLLAMA_BASE_URL=http://127.0.0.1:11434/v1`

There is no native `/api/chat` client, no RAG, no tool calling, no SQL.

## 3. Opt-in

All of:

- `AI_ANALYTICS_LLM_ENABLE=true` (exact string)
- `AI_ANALYTICS_LLM_MODE=http`
- `AI_ANALYTICS_LLM_ADAPTER=ollama`
- `OLLAMA_BASE_URL` (loopback)
- `OLLAMA_MODEL` (installed tag)

`OLLAMA_API_KEY` may be the placeholder `ollama`. A running daemon is not consent.

## 4. Loopback pin

Allowed hosts: `127.0.0.1`, `localhost`, `::1`.
Cloud hosts (OpenAI, Groq, …) and any other host are refused.
HTTP redirects are disabled on this adapter.

## 5. Destination reporting

| Adapter | `destination` | `local_loopback` | `network_access` |
|---|---|---|---|
| mock / disabled | `none` | false | false |
| `ollama` enabled | `local_loopback` | true | false |
| `groq` / `openai-compatible` enabled | `external` | false | true |

Local Ollama is **not** described as sending data off-machine.

## 6. Failure

Extraction failure → no execution, existing NOT_DETERMINABLE / clarification.
Verbalization failure or guard violation → deterministic skeleton, `llm_fallback`.

## 7. Tests

CI never requires an Ollama process. Optional live test:
`AI_ANALYTICS_OLLAMA_LIVE_TEST=true`.
