# Phase 12 Report

**Date:** 2026-09-02
**Scope:** Local Ollama adapter behind the existing `LLMProvider` / `ProviderConfig` path.

Ollama was **not** live-tested against a daemon in this run unless the operator set
`AI_ANALYTICS_OLLAMA_LIVE_TEST=true`. Adapter code existing is not a live pass.

---

## Implementation summary

Ollama is a named HTTP adapter (`ollama`) that reuses `OpenAICompatibleProvider` against
`/v1/chat/completions`. Loopback hosts only; redirects disabled; model name required;
placeholder key `ollama` allowed for this adapter only. Enable remains
`AI_ANALYTICS_LLM_ENABLE=true`. Mock remains the default.

No second pipeline, RAG, SQL, tool-calling, or calculator path was added.
`engine/llm_interface.py`, the Trust Gate, Answer Contract, execution, structured-output
validation, and the verbalization guard were not redesigned.

Health now reports `destination`: `none` | `local_loopback` | `external`. Local Ollama is
not described as sending data off-machine.

---

## Exact Ollama configuration

```
AI_ANALYTICS_LLM_ENABLE=true
AI_ANALYTICS_LLM_MODE=http
AI_ANALYTICS_LLM_ADAPTER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=<installed local model tag>
```

Optional: `AI_ANALYTICS_LLM_TIMEOUT` (seconds, 1–300, default 60).

---

## Local vs external privacy

| Mode | Destination | Prompts leave this machine? |
|---|---|---|
| Default mock | none | No |
| `ADAPTER=ollama` + enable | local_loopback | No (loopback Ollama process only) |
| `ADAPTER=groq` / `openai-compatible` + enable | external | Yes, if that adapter is explicitly enabled |

External adapters remain separately controlled. The Ollama adapter refuses their hosts.

---

## Quarantine (live Ollama)

Until a daemon answers on loopback with `OLLAMA_MODEL` pulled **and**
`AI_ANALYTICS_OLLAMA_LIVE_TEST=true` (or an operator run) succeeds, live Ollama is
**QUARANTINED**. Remaining requirement: install Ollama, `ollama pull <tag>`, set the
env block above, confirm `/v1/chat/completions` responds locally.

Offline trust-boundary tests do not need that daemon.

---

## Verification

| Gate | Result |
|---|---|
| Source CSV SHA-256 | Matches baseline `aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26` |
| Metric / conflict / DQ registries | Unchanged (validator SHA match) |
| `pytest` Phases 1–12 | **922 passed**, **1 skipped** (live Ollama, flag unset) |
| Phase 11 baseline | 894 passed. Delta is the new Phase 12 offline suite; no regressions. |
| `validate_phase7` … `validate_phase12` | 0 problems |
| Live Ollama daemon (`127.0.0.1:11434`) | **Not running** (connection timeout). Live path **QUARANTINED**. |
| Live Ollama model test | **Not claimed.** `AI_ANALYTICS_OLLAMA_LIVE_TEST` was not set. |

Phase 12 is **implementation-complete with honest live quarantine**. Offline loopback pin, opt-in, mock default, and trust-boundary tests passed. No Ollama model was exercised.

## Next step for live Ollama verification

1. Install Ollama and `ollama pull <tag>`.
2. Confirm `http://127.0.0.1:11434/v1/chat/completions` responds locally.
3. Set:

```
AI_ANALYTICS_LLM_ENABLE=true
AI_ANALYTICS_LLM_MODE=http
AI_ANALYTICS_LLM_ADAPTER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=<the pulled tag>
AI_ANALYTICS_OLLAMA_LIVE_TEST=true
```

4. Run `python -m pytest tests/test_phase12_ollama.py::test_live_ollama_roundtrip_if_explicitly_flagged -q` and a few `/api/ask` questions through the existing chat. Expect extraction JSON to be validated and verbalization to be guarded; failures must still fall back to the skeleton, never invent numbers.
