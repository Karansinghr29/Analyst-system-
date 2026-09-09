# Phase 13 Report

**Date:** 2026-09-03
**Scope:** Live Supabase / production data activation against the trusted export freeze.
Phase 12 Ollama is unchanged. Calculators, Trust Gate, Answer Contract, and registries
were not modified.

This report does **not** claim live ACTIVATED because a connector exists.

## Integrity

| Item | Result |
|---|---|
| Export SHA-256 | `aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26` (must still match) |
| `EXPORT_SNAPSHOT_DATE` | `2026-08-29` (live TRUSTED bind requires this as-of) |
| Registries | Unchanged |
| Phase 12 | Unchanged |

## What was implemented

- REST GET pagination with Content-Range; fail closed on truncation / unknown totals
- Public table+view allowlist from the evidence manifest; non-public schemas refused
- Live harness replays the 12 validation scripts in memory (does not write `validation_summary.csv`)
- 49-metric live-vs-export comparison of trust **and** values
- 12 conflict overlay replay; vanished conflict is an owner decision, not a registry edit
- Replayable DQ re-measured; remaining DQ ids recorded as limitations
- Read-only owner-decision file with no waiver kinds
- `SUPABASE_URL` included in secret collection; service-role keys refused
- Overlay cache-clear for ledger/validator LRU (no formula change)

## Live source status

**QUARANTINED**

No production bind was performed in this implementation pass. Default `/health` continues to
serve the trusted export. `bind_source()` on a live source still requires a real harness pass
against complete live rows at as-of `2026-08-29`.

Remaining requirement: `AI_ANALYTICS_LIVE_ENABLE=true`, `SUPABASE_READONLY_KEY` (not service
role), `SUPABASE_URL`, `AI_ANALYTICS_LIVE_AS_OF=2026-08-29`, then

```
pytest tests/test_phase13_live.py -v
```

with `AI_ANALYTICS_LIVE_TEST=true`. Report ACTIVATED only if that run’s harness passes and
bind succeeds.

## PASS vs QUARANTINED

See `phase13_live_data_spec.md`. Connectors existing is not a pass.

## Verification (2026-09-03)

Offline suite only. No production Supabase credentials were supplied, so the real live
round-trip was not executed.

| Command | Result |
|---|---|
| `validate_phase7_consistency.py` … `validate_phase13_consistency.py` | 0 problems each |
| `pytest -q` (LLM/live flags off) | **943 passed, 2 skipped** (live Supabase + live Ollama; both flag-gated) |

Default `/health` still reports export `TRUSTED` and live `UNAVAILABLE` / `QUARANTINED`.
The export-backed harness simulator (`ManifestCsvTransport`) bound in tests only; that is
not a production bind.
