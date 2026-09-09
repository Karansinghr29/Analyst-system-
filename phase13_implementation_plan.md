# Phase 13 Implementation Plan

Live overlay activation against the trusted 2026-08-29 export freeze. No second engine,
no calculator edits, no registry mutation, no Phase 12 changes.

## Files

| File | Role |
|---|---|
| `api/live_connector.py` | GET-only REST pagination, allowlist, schema profile, service-role refuse |
| `api/live_replay.py` | 80-check script replay, 12 conflicts, DQ re-measure, 49-metric value compare |
| `api/owner_decisions.py` | Read-only decision loader (no waivers in v1) |
| `api/data_source.py` | Freeze as-of, view+column compare, overlay-only live pass |
| `api/security.py` | `SUPABASE_URL` in secret collection |
| `engine/evidence_loader.py` | Clear ledger/validator caches on overlay (formulas unchanged) |
| `tests/test_phase13_live.py` | Offline contract + optional live flag |
| `scripts/validate_phase13_consistency.py` | Anti-drift |
| `phase13_*.md` | Spec / plan / report |

Untouched: calculators, Trust Gate, propagation, Answer Contract, structured output, Phase 12,
registries, export CSVs, `file_manifest.csv`, frontend `/api/ask`.

## Sequence

enable → credentials → as-of=2026-08-29 → complete fetch → schema/views → 80 checks →
12 conflicts → 32 DQ → 49 value+trust → `bind_source` → `bind_trusted_source`.

Any failure: QUARANTINED, export serves.

## Tests

Default `pytest` uses export evidence. `AI_ANALYTICS_LIVE_TEST=true` runs the real-Supabase
class; missing credentials fail closed (quarantine), they do not skip.
