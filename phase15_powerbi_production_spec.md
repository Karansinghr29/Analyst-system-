# Phase 15 — Power BI production specification

Power BI is presentation only. The analytics engine remains the only authority for numbers;
the Trust Gate remains the only authority for refusal posture. This file is the production
dataset/page contract. It does **not** claim that Power BI Desktop or Power BI Service was
published from this environment.

## Data authority

```
Analytics Engine  →  API / production dataset contract  →  Power BI
```

- Bind visuals to existing authorized payloads: `engine/bi_contract.py` cards, `/api/owner/home`,
  `/api/analytics/{section}`, `/api/metrics/{id}`, `/api/metrics/{id}/conflict`, `/api/trust`.
- Do **not** author DAX/M measures that recompute revenue, receivables, occupancy, profit, or
  any other of the 49 registry metrics.
- `powerbi_dataset_descriptor.json` remains the measure catalog (registry-derived).
- `owner_dashboard_registry.csv` remains the owner tile list. Headline-forbidden metrics stay
  off KPI cards.
- Live Supabase is **QUARANTINED**. Pages are source-agnostic: they consume the API, so a later
  trusted live bind does not require rebuilding the dashboard.

## Pages

See `powerbi_production_pages.json` for the six required areas and their API bindings.

| Page | Must not |
|---|---|
| Executive Overview | Profit headline card; single occupancy %; single tenant-dues figure |
| Financial | SQL; calculator internals; a picked “primary” AR definition |
| Operations | Collapsing M.OCC.001 to one percentage |
| Risk & Data Quality | Rendering NOT_DETERMINABLE as 0 |
| Insights / Attention | Invented materiality thresholds |
| Trust / disclosures | A winner among competing definitions |

## Trust presentation (bind these fields, do not reinterpret them)

| Trust | Visual |
|---|---|
| SAFE | KPI / card using `value` |
| DISCLOSE | Same, with `caveat` beside the number (not tooltip-only) |
| SHOW_BOTH | Multi-definition table from `definitions[]`; `headline_permitted=false` |
| BLOCK | Conflict panel; no `value`; named `conflict_ids` |
| NOT_DETERMINABLE | Exact sentence *Not determinable from exported evidence.* No chart, no zero |

`validate_card()` in `engine/bi_contract.py` is the machine check a report author must not
violate.

## Role visibility

Reuse `/api/roles/{role_id}/workspace` and `role_view_registry.csv`. Do not duplicate
permissions in Power BI RLS unless they are a mirror of that API response. Do not hardcode
role-to-metric lists in the report.

## Refresh / source strategy

1. Authenticate to the existing API with the existing bearer identity (never service-role,
   never a database DSN).
2. Import or DirectQuery the JSON payloads listed in `powerbi_production_pages.json`.
3. Schedule refresh against the API. Until a live source is TRUSTED, the payload is the
   trusted export.
4. Never connect Power BI to Postgres/Supabase SQL for these metrics.

## Secrets

Power BI must not embed `SUPABASE_*`, `AI_ANALYTICS_AUTH_SECRET`, API keys, or database URLs
in report measures or query strings. Credentials live in the Power BI Service gateway/data
source settings, not in this repository.

## Remaining external Power BI Service steps

This environment does not operate Power BI Desktop or Power BI Service. Deployment is **not**
complete until an operator:

1. Creates a Power BI workspace.
2. Creates a dataset that calls the production API (no SQL).
3. Builds the six pages per `powerbi_production_pages.json`.
4. Binds each visual to `headline_permitted` / `definitions` / `trust_level`.
5. Maps workspace audiences to existing API roles (not a new permission model).
6. Runs the UAT checklist below against a running API.
7. Confirms no report measure recalculates a registry metric.

## UAT checklist

- [ ] Revenue card shows the engine value and SAFE posture.
- [ ] Profit is not a headline number; conflict panel lists every definition.
- [ ] Tenant dues shows all four definitions; no average/default.
- [ ] Occupancy shows every labelled definition; no single %.
- [ ] NOT_DETERMINABLE tiles show the exact unavailable sentence.
- [ ] Restricted role workspace hides unauthorized metrics.
- [ ] Refresh succeeds using API credentials only.
- [ ] No SQL or calculator text is visible to the owner.
- [ ] `/health` still reports export TRUSTED and live QUARANTINED.
