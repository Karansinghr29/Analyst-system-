# Phase 11 Data Activation Spec

## 1. Inversion (unchanged)

A live source starts QUARANTINED. `bind_source()` is the only path onto the engine.
Passing a connection string is not a pass.

## 2. Connector

`LiveDataSource` is filled in with a read-only transport:

- **Supabase REST** (`SUPABASE_URL` + `SUPABASE_ANON_KEY` or `SUPABASE_READONLY_KEY`): HTTP GET only. No POST/PATCH/DELETE method exists on the class.
- **Postgres** (`DATABASE_URL` / `SUPABASE_DB_URL`): session `default_transaction_read_only=on`. Any SQL matching write/DDL verbs is refused before execution.

Service-role keys that can write are not used for writes because the interface has no write method. Prefer a read-only key.

Logical names from `evidence/file_manifest.csv` (`public.journal_entries`, …) map to live relations. That mapping is the evidence contract. No ad-hoc table names.

## 3. What the harness must do before bind

Against the **candidate source**:

1. **80 validation checks** — every `validation_summary.csv` row still has a recorded status in `{MATCH, DIFFERS, NOT_DETERMINABLE}`. For a live source that can be queried, each mapped metric is re-executed through `MetricExecutor` and compared to the export baseline trust posture. A status that is no longer one of the three recorded outcomes is a divergence.
2. **12 conflicted metrics** (`conflict_disclosure_registry.csv`) — each must still produce competing definitions or a documented NOT_DETERMINABLE. A conflict that stops reproducing is an **owner decision**, never a silent registry edit.
3. **32 DQ findings** — every `dq_id` in `data_quality_registry.csv` is still present. A missing id is a divergence.
4. **Metric regression** — all 49 `metric_id`s: effective trust from the live gate path equals the export gate path. A trust change quarantines the source.
5. **Schema / row-count** — live relation columns and counts vs the export manifest. Any mismatch is a row-count or schema anomaly → quarantine + owner decision.
6. **As-of** — a live source must declare its own as-of. It may not inherit `2026-08-29`.
7. **Partial-period / snapshot vs historical** — unchanged: snapshot metrics still cannot answer historical questions; incomplete periods stay named.

The engine keeps reading the export until bind succeeds. After a trusted live bind, `engine.evidence_loader` reads through the live source **only**. Unbind restores the export.

## 4. Owner decisions

The harness never writes `semantic_metric_registry.csv`. Divergences are listed as
`required_owner_decisions`. Until an owner records a decision and the registry is
updated in a later, explicit change, the live source stays QUARANTINED.

## 5. If credentials are missing

Status `UNAVAILABLE` / `QUARANTINED`. Remaining requirement: `AI_ANALYTICS_LIVE_ENABLE=true`,
a read-only connection string or Supabase URL+key, the live as-of date, then a harness pass
with no owner-decision divergences. The export continues to serve.

A URL or key in the environment is not consent to bind. Enable must be explicit, matching
the LLM activation switch.
