# Phase 11 Observability Spec

## 1. Correlation

Every request carries `X-Request-ID`. If the client sends one (printable, ≤ 128
chars), it is reused; otherwise a UUID is generated. The id is returned on the
response and written on every audit line.

## 2. Audit line (JSON)

Emitted for `/api/*` after the handler returns:

```
request_id, method, path, status, subject, role_id,
metric_ids, intent, trust_level, validation_status,
source_name, source_status, outcome,
llm_fallback, guard_violations_count
```

**Not logged:** question text, answer text, metric values, tokens, SQL, paths,
authorization headers, API keys.

## 3. Counters (process-local)

- `trust.BLOCK` / `trust.SHOW_BOTH` / `trust.NOT_DETERMINABLE` / `trust.SAFE` / `trust.DISCLOSE`
- `source.quarantine` / `source.revalidation_pass` / `source.revalidation_fail`
- `llm.fallback_to_deterministic` (guard fired or provider unavailable)
- `http.401` / `http.429`

Exposed on `/health` under `observability.counters` so an operator can see them
without a second pipeline.

## 4. Data-source posture

`/health` already reports source status and revalidation summary. Phase 11 adds
`remaining_requirement` when quarantined, and increments quarantine counters when
`bind_source` refuses.

## 5. What "outcome" means

`answered` | `refused` | `clarification` | `unauthorized` | `error` — never a
paraphrase of the business answer.
