# Power BI Analytics Mapping

How this semantic layer maps onto a Power BI (or equivalent) model — and the three places where
the mapping must deliberately **not** use Power BI's native idiom.

**No frontend is built here.** This document specifies what a future implementer receives.

---

## 1. Object mapping

| Power BI concept | Source here | Notes |
|---|---|---|
| Table | manifest-resolved CSV | 253 files, read-only |
| Measure | `metric_id` | 49 measures. **The registry is the only source; no measure is authored in the BI tool** |
| Measure description | `definition` | Surfaced verbatim |
| Dimension | `business_dimensions.md` entry | 22 catalogued |
| Hierarchy | documented grain | org → property → apartment → bed → tenant/allotment |
| Date table | the metric's `date_field` | **Per-metric, not one shared calendar** — see §3 |
| Row-level security | *(not applicable)* | Single org, single property |
| KPI card | `bi_contract.MetricCard` | Includes trust, conflicts, DQ |
| Report page | dashboard section | Business Health / Operations / Risks |

---

## 2. The three anti-idioms

A conventional Power BI model would get each of these wrong by default.

### 2.1 A conflicted measure is not one measure

Profit, tenant dues, owner rent and occupancy each have multiple incompatible definitions. The
natural Power BI move is to author `Profit = SUM(...)` and put it on a card. That silently picks
one definition and presents it as the business's position.

**Mapping rule:** a conflicted concept maps to a **multi-value visual**, never a card. The card
contract carries `headline_permitted = false` and `definitions[]`; a report that renders
`definitions[0]` has violated it.

| Concept | Definitions | Visual |
|---|---|---|
| Profit `M.PROFIT.001` | 3 | conflict panel, no headline |
| Tenant dues `M.AR.001A`–`D` | 4 | multi-definition table |
| Occupancy `M.OCC.001` | 5 | multi-definition table |
| Owner rent `M.OWN.002` | 3 | multi-definition table |

### 2.2 There is no single date table

Power BI convention is one conformed calendar joined to everything. Here, the business date is a
**property of each metric**: `entry_date` for ledger metrics, `settlement_date` for deposit
settlements, `onboarding_date`/`actual_exit_date` for lifecycle, `billing_month` (text) for EB,
and `created_at` for maintenance — the one documented exception, because
`maintenance_tickets` has no other business-open date.

Forcing one calendar would silently re-date metrics onto a field their definition does not use.
**Mapping rule:** one date table per date basis, joined per metric as the registry documents.

### 2.3 Blank is not zero

A NOT_DETERMINABLE measure has no value. Power BI renders blanks as zero in many visuals, which
turns "we cannot measure this" into "we measured it and it was nothing."

**Mapping rule:** NOT_DETERMINABLE measures render the exact sentence
*"Not determinable from exported evidence."* — no chart, no placeholder, no zero.

---

## 3. Trust as a first-class model column

Every measure carries `trust_level`, `conflict_ids`, `dq_ids`, `validation_status` and
`confidence` as model metadata, not as report annotation. Consequences:

- A visual can be **conditionally blocked** by `headline_permitted`.
- A DISCLOSE caveat renders **beside** the number, not in a tooltip.
- Exports carry trust and conflict columns, so a figure pasted into a deck retains them.

---

## 4. Measures that must not be authored in the BI tool

| Tempting measure | Why not |
|---|---|
| `Profit = Revenue - Expenses` | This is `M.PROFIT.001`, which is BLOCK. The combination guard refuses it |
| `Occupancy % = Occupied / Total` | Five definitions differ on both numerator and denominator |
| `Collection Efficiency = Collections / Invoiced` | No such metric exists; `metric_dependency_graph.md` §2 names it as structurally absent |
| `Churn Rate` | No denominator is documented |
| Any YoY over maintenance or EB | 20 months and 1–5 months of coverage |
| Any threshold-coloured KPI | No materiality threshold exists |

The general rule: **if it is not in the 49-metric registry, it is not a measure.** A BI author
adding one has left the semantic layer.

---

## 5. Refresh and coverage

- Coverage differs by domain: ledger ~54 months, occupancy 67, maintenance 20, EB 1–5.
- The export snapshot (`2026-08-29`) is **mid-month**, so the two most recent periods are
  incomplete and are excluded from period comparisons, with the exclusion named.
- Aging is `CURRENT_DATE`-dependent and is reconstructed against a fixed as-of date, not the
  server clock — otherwise the same report yields different numbers on different days.

---

## 6. What a Power BI implementer receives

1. `semantic_metric_registry.csv` — 49 measures with definitions, filters, grain, date basis
2. `owner_dashboard_registry.csv` — 20 tiles with widget type and render directive
3. `role_view_registry.csv` — 334 role/metric views with permitted conclusions
4. `conflict_disclosure_registry.csv` — 12 conflicts that must remain visible everywhere
5. `analysis_capability_registry.csv` — 56 capabilities with implementation status
6. `bi_contract.MetricCard` — the per-tile payload contract, with `validate_card()`

Together these are sufficient to build the model without re-deriving a single business
definition — which is the point.
