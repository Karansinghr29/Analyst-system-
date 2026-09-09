# Phase 13 Live Data Spec

## Inversion (unchanged)

A live source starts QUARANTINED. `bind_source()` is the only path onto the engine.
A connection string is not a pass. Growing production data is not automatically trusted.

## Trusted export baseline

- `EXPORT_SNAPSHOT_DATE = 2026-08-29`
- `EXPORT_BASELINE_SHA = aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26`

Phase 13 first activation requires `AI_ANALYTICS_LIVE_AS_OF=2026-08-29`. Any other as-of stays
QUARANTINED. Temporal modules (`time_resolution.py`, `change_detection.py`, `execution.py`,
aging calculators) are not retargeted.

## Connector

`SupabaseRestTransport` is HTTP GET only, Range/Content-Range paginated. Fetched row count must
equal the server-reported total. Missing or `*` totals, truncated pages, and order/column
ambiguity fail closed.

`PostgresReadOnlyTransport` remains session read-only with write/DDL refused before execute.

Relations are limited to **public** `base_table` and `view` names in `evidence/file_manifest.csv`.
Non-public schemas (including `market`, `auth`) are refused. Diagnostics stay on export CSVs.

Service-role keys are refused. Prefer `SUPABASE_READONLY_KEY`.

## Harness before bind

Against the live overlay, in order:

1. Explicit enable (`AI_ANALYTICS_LIVE_ENABLE=true`)
2. Credentials (read-only)
3. As-of freeze `2026-08-29`
4. Complete fetch (pagination integrity)
5. Schema + row-count for required public tables **and** views; required export columns present
6. All 80 Phase E checks replayed via the existing `scripts/validation/validate_*.py` formulas
   (in memory; `validation_summary.csv` is not written). Known baseline statuses that must hold:
   - DIFFERS: `REV.02`, `AR.04c`, `DQ.003`, `DQ.026`
   - NOT_DETERMINABLE: `PROFIT.02`, `AR.04b`, `DEP.07`
7. 12 conflicted metrics still produce competing definitions (or documented NOT_DETERMINABLE)
8. 32 DQ ids still present; replayable findings (`DQ.001`, `DQ.003`, `DQ.013`, `DQ.026`) re-measured;
   others recorded as limitations (registry + 49-metric trust), not silently claimed measured
9. All 49 metrics: same executor on export vs live overlay; compare metric id, trust, blocked /
   NOT_DETERMINABLE posture, competing definition labels, and values (abs 0.015 or 0.5%)

The harness never writes metric/trust/conflict/DQ registries.

## Owner decisions

`phase13_owner_decisions.json` is read-only. The process never writes it. `ALLOWED_KINDS` is empty:
no waiver converts numeric drift or row-count growth into equivalence. Default = QUARANTINED.

## PASS vs QUARANTINED

**ACTIVATED / TRUSTED** only if `bind_source()` accepts the live source after the full chain above
and `/health` `data_source.kind` is `live` with status `TRUSTED`.

**QUARANTINED** otherwise. The export remains the serving path. Connectors existing is not a pass.
