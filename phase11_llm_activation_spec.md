# Phase 11 LLM Activation Spec

## 1. What the model may do

Unchanged from `production_ai_architecture.md` and Phase 4:

1. Propose a **concept** and an **intent** (validated; invalid never executes)
2. Re-word a finished skeleton (guarded; violations discard the verbalization)

There is no third place. The model cannot calculate, query, select trust, override a
conflict, invent evidence, or bypass BLOCK/SHOW_BOTH.

## 2. Activation switch

A live adapter is constructed only when **all** of:

- `AI_ANALYTICS_LLM_ENABLE` is the exact string `true`
- `AI_ANALYTICS_LLM_MODE=http` (or an explicit `ProviderConfig(mode=http, explicitly_enabled=True)`)
- a known adapter name is set
- the adapter's credential env var is present

A key sitting in the environment is not consent. `GROQ_API_KEY` / `OPENAI_API_KEY` /
`ANTHROPIC_API_KEY` do not enable anything by themselves.

Default remains `DeterministicMockProvider`. Tests keep using it.

HTTP construction without `explicitly_enabled` still raises `LLMUnavailable`.

## 3. Transport

`OpenAICompatibleProvider` implements `LLMProvider.complete` over HTTPS using the
stdlib. No vendor SDK. Failures raise `LLMUnavailable` (refusal, never a guess).
Request bodies are not written to the audit log (they contain the question).

## 4. Adversarial suite (production path)

The same `LLMInterface` + verbalization guard, with a hostile `CallableProvider`
standing in for a production model (so the suite never requires a network call):

- prompt injection steering metric selection
- fabricated numbers in verbalization
- trust-level manipulation in model output
- PII leakage
- unsupported recommendations
- metric substitution
- BLOCK headline / SHOW_BOTH collapse

A real HTTP adapter, when enabled in a deployment, is still behind this guard. The
suite proves the guard, not the vendor.

## 5. If not enabled

`/health` reports LLM QUARANTINED: remaining requirement is explicit enable plus
credential plus confirmation that sending this data off-machine is intended.
