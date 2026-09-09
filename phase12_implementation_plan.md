# Phase 12 Implementation Plan

Activation of a local Ollama provider behind the existing Phase 4/9/11 LLM
boundary. No redesign.

## 1. What changes

| File | Change |
|---|---|
| `engine/llm_provider.py` | Loopback URL pin, redirect refusal, `loopback_only` / `require_model` on `OpenAICompatibleProvider` |
| `api/provider_config.py` | Named `ollama` adapter; local vs external `describe()` |
| `frontend/views/workspace.js` | Display destination / loopback / external (health only; `/api/ask` unchanged) |
| tests, validator, this spec family | Offline proofs |

## 2. What does not change

`llm_interface.py`, `gate.py`, `contract.py`, `execution.py`, `structured_output.py`,
`answer_renderer.py`, calculators, registries, source CSVs, chat `api.ask` routing.

## 3. Order

1. Loopback helpers + HTTP client flags
2. Adapter spec + `build_provider` branch
3. Health destination fields
4. Offline tests
5. Validator + report (honest quarantine if no daemon)

## 4. Exit

Phase 12 is complete when offline trust-boundary and Phase 1–11 regressions pass,
the loopback pin is enforced, mock remains default, and live Ollama is either
verified against a real daemon **or** honestly QUARANTINED with the remaining
requirement named.
