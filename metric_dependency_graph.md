# Metric Dependency Graph

Traces how every semantic metric is built up from raw evidence, and — critically — how an
upstream conflict or data-quality issue **propagates** to downstream metrics, KPIs, and
eventually AI answers. Every edge in this graph corresponds to a join/aggregation already
documented in `business_logic.md`/`metric_reconstruction.md`; **no dependency is asserted here
that isn't already established in an earlier deliverable.**

**Layer model** (per the brief):

```
Raw tables
   -> Business logic / functions (triggers, posting logic)
   -> Accounting/operational intermediate concepts (ledger balances, occupancy state)
   -> Semantic metrics (metric_registry.csv rows)
   -> Business KPIs (composite/derived, used in dashboards)
   -> AI insights (trend/anomaly/driver analysis — framework only, not implemented yet)
```

---

## 1. Financial spine: invoices/receipts/expenses/owner_payments → ledger → P&L

```
invoices (source table)
   |  trg_invoice_journal_post (reverse-and-repost on material edit;
   |  build_invoice_lines composition NOT exported -- account/amount detail unverified)
   v
journal_entries + journal_lines  <---------------------------+
   |                                                          |
   | (reversal-excluded convention, v_account_balances)       | (reversal-included convention,
   v                                                          |  raw journal_lines direct)
v_pnl.revenue (M.REV.001) --------------------------+         |
   |                                                 |         |
   v                                                 v         v
v_pnl.expenses (M.EXP.001)                  M.PNL.001 (P&L by month)   M.TB.001 (trial balance,
   ^                                          [SAFE]                     BOTH conventions exact)
   |                                                                     [SAFE]
expenses (source table)
   |  trg_expense_journal_post (hard-delete only, no is_deleted column)
   v
(feeds journal_lines above)

receipts (source table)
   |  trg_receipt_journal_post (soft-delete -> reversal; hard-delete -> cascade-delete JE,
   |  wins by alphabetical trigger order over the reversal branch)
   v
journal_entries + journal_lines
   |
   +--> M.COL.003 (Collections, ledger-derived) [DISCLOSE, C.014]
   |
   +--> (also feeds v_pnl.revenue's account-4xxx postings when receipt_type='booking')

owner_payments (source table)
   |  trg_owner_payment_journal_post (body NOT exported -- account composition unverified;
   |  normalize_owner_payment_journal_dates forces entry_date := bill_date)
   v
journal_entries (owner_rent bucket, account 510%)  --PROVEN PERFECT match to source, H.001--
   |
   +--> M.OWN.002 (owner rent, 3 definitions) [SHOW_BOTH, C.010/C.011]
   |         |
   |         v
   +--> M.PROFIT.001 (profit, 3 definitions) [BLOCK, C.010/C.011, DQ.016 CRITICAL]
             |
             v
     Business KPI: "Net Margin %", "Owner-rent-adjusted profitability"
             |
             v
     AI insight: "why did profit fall" -- CANNOT be answered without first resolving
     WHICH profit definition the question means (see ai_trust_policy.md)
```

**Key propagation finding (already proven in `metric_reconstruction.md`):** `M.OWN.002`'s
Def-i-vs-Def-iii gap is the **entire mechanism** behind `M.PROFIT.001`'s Def-B-vs-Def-C gap
(36.63% profit overstatement) — this is not two independent conflicts, it is **one conflict
(owner-rent inclusion) manifesting at two dependent layers.**

---

## 2. The AR conflict propagation chain (explicit worked example, as required)

This is the brief's own named example. Traced exactly through the layers actually present in
this package:

```
LAYER: Raw tables
  tenant_allotments.balance_due (application column, writer NOT exported)
  tenant_transactions (frozen legacy table, unwired since 2026-04)
  journal_lines / journal_entries (account 1200, two reversal conventions)

LAYER: Business logic / functions
  (no function reconciles these three -- confirmed: none of the 25 exported bodies
   writes to tenant_allotments.balance_due or tenant_transactions)

LAYER: Accounting intermediate concepts
  v_account_balances (reversal-excluded AR)  <-- proven IDENTICAL total to -->  raw journal_lines AR (reversal-included)

LAYER: Semantic metrics  [THIS IS WHERE THE CONFLICT SURFACES]
  M.AR.001A (v_outstanding_receivables)   SHOW_BOTH
  M.AR.001B (v_tenant_current_dues)        SHOW_BOTH
  M.AR.001C (application balance_due)      BLOCK   <- Rs.1,009,125.78 (12.1x the ledger figure)
  M.AR.001D (tenant_transactions)          BLOCK   <- Rs.9.97M-10.5M (~120x the ledger figure)
       |
       v  (M.AR.002 = same 4-way conflict, tenant grain; M.AR.003 = same, property grain)
       v
  M.RISK.001 "Outstanding dues"            BLOCK   <- Risk/DQ framing of the identical conflict
       |
       v
LAYER: Business KPI
  "Collection efficiency" (would need: dues collected / dues billed --
   NOT A METRIC IN THIS REGISTRY. Not determinable from exported evidence which of the
   4 AR definitions "dues billed" should use -- so collection efficiency itself
   INHERITS the BLOCK status and cannot be computed as a single number.)
       |
       v
  "Cash-flow interpretation" (would combine M.CASH.001 [SAFE] with outstanding dues
   [BLOCK] -- the cash side is trustworthy, the receivables side is not, so any
   combined cash-flow-plus-receivables statement must disclose that only half of it
   is reliable)
       |
       v
LAYER: AI insight / recommendation
  "Which tenants are overdue" / "should we chase collections" -- MUST disclose the
  4-way conflict before naming any tenant or dollar amount (ai_trust_policy.md).
  A recommendation built silently on M.AR.001D (tenant_transactions) would overstate
  the collections opportunity by ~120x -- a fabricated business risk.
```

**This chain demonstrates the rule the brief states explicitly:** a single upstream conflict
(AR definition) invalidates a **naive** single-number answer at every downstream layer, all the
way to the recommendation layer, unless each layer explicitly disclosures the conflict rather
than silently resolving it by picking one upstream source.

---

## 3. Occupancy / tenant lifecycle spine

```
tenant_allotments (staying_status, onboarding_date, actual_exit_date)
 + beds (status) + apartments (status)
       |
       | sync_tenant_staying_status / _on_delete (both exported, tenants.staying_status
       | is DERIVED, never independent)
       v
  M.LIFE.001 (tenant lifecycle status)  [SAFE]
       |
       +--> M.TEN.001/002/003 (Staying/On-Notice/Booked counts)  [SAFE]
       |
       +--> M.LIFE.002/003 (move-ins/move-outs, v_tenant_lifecycle_events)  [SAFE]
       |         |
       |         v
       |    M.LIFE.004 (exit reconciliation -- ALSO depends on M.AR.001B, so it
       |    inherits M.AR.001B's reversal-included convention specifically, NOT
       |    M.AR.001A's)  [SAFE]
       |
       v
  M.OCC.001 (current occupancy, 5+ definitions)  [SHOW_BOTH, C.006-C.009, DQ.004/005]
       |
       +--> M.OCC.002 (by property) [SHOW_BOTH] -- degenerate, 1 property in this dataset
       +--> M.OCC.003 (by apartment) [NOT_DETERMINABLE] -- get_occupancy_intelligence,
       |         no exported output to validate
       +--> M.OCC.004 (by bed) [NOT_DETERMINABLE] -- same reason
       +--> M.OCC.005 (historical occupancy) [SHOW_BOTH] -- Def E / day-weighted family
             |
             v
       Business KPI: "Vacancy rate", "Bed utilization %"
             |
             v
       AI insight: "what is current occupancy" -- MUST name which of 5+ definitions
       backs the answer (a 9.4-percentage-point spread exists between them)
```

**Special case, fully traced:** `v_occupancy`'s `on_notice`/`vacant` output columns are a
**proven SQL defect** (`C.009`/`DQ.005`), not a competing definition — 7 beds vanish from all 4
of its buckets. This is the one occupancy-family issue that does **not** get SHOW_BOTH treatment
downstream — it gets excluded outright (`ai_trust_policy.md` treats it as BLOCK for that
specific column, not SHOW_BOTH, because one side is proven wrong, not merely different).

---

## 4. EB / electricity spine

```
electricity_readings + eb_tenant_shares (billing_month = 'Mon-YY' TEXT, PROVEN 0% conformant
 to the 'YYYY-MM' format every other billing-period column uses)
       |
       | Formula (reverse-engineered, no exported function; PROVEN exact over
       | full 801-row population): per_day_rate = ROUND(bill/tenant_days);
       | tenant_eb_charge = per_day_rate * stay_days
       v
  M.EB.002 (EB tenant allocation)  [DISCLOSE, DQ.028]
       |
       | (relationship to invoices.electricity_amount -- Not determinable from exported
       | evidence whether these are meant to be the same figure computed twice; no
       | view/function joins the two)
       v
  M.EB.001 (EB usage and cost)  [DISCLOSE, DQ.021/DQ.028]
       |
       v
  Business KPI: "EB cost per bed", "EB cost trend"
       |
       v
  AI insight: EB-to-invoice reconciliation, EB cost trend -- BOTH blocked from a clean
  join without an explicit billing_month format-conversion step; EB trend limited to
  2-5 months of coverage, YoY EXPLICITLY PROHIBITED (insufficient depth)
```

`eb_payments` (2-month coverage) and `eb_monitoring_readings` (1-day snapshot) are **dead-end
nodes** — they feed no downstream semantic metric in the current registry beyond `M.EB.001`
itself, and specifically cannot support a trend or YoY KPI.

---

## 5. Maintenance spine

```
maintenance_tickets (created_at IS the business date -- no other date column exists here)
       |
       +---------------------------+
       |                           |
       v (Path A)                  v (Path B)
ticket_resolutions            expenses.issue_type_id (direct FK, independent of
       |                       the ticket's own issue type)
       v
expenses.ticket_resolution_id
       |                           |
       v                           v
  v_maintenance_metrics       v_maintenance_by_issue_type
  (F.015, dated by ticket      (F.016, dated by expense_date)
   creation month)
       |                           |
       +-------------+-------------+
                     |
                     v
            M.MAINT.002 (maintenance cost, 2 paths)  [SAFE -- PROVEN, for this
            dataset, that both paths agree exactly, Rs.28,796.00 both]
                     |
                     v
            Business KPI: "Maintenance cost per ticket", "cost by issue type"
                     |
                     v
            AI insight: safe to answer directly today; if a future data load makes
            an expense's issue_type_id diverge from its ticket's issue type, the
            two paths WOULD diverge (structural risk, not currently realized)
```

`H.019`'s 1613-vs-1611 gap is now a **fully explained, closed** node: 2 tickets with 2
resolutions each fan out +2 rows on the `maintenance_tickets JOIN ticket_resolutions` edge — it
does not propagate as an unresolved risk to `M.MAINT.001`/`002`, both of which are validated
against the correct 1611-row live-table basis.

---

## 6. DQ-metric → trust-level propagation table

Every metric's trust level in `metric_registry.csv`/`semantic_metric_registry.csv` is a
**function of which DQ/conflict IDs it inherits** — this table makes that function explicit so
the semantic layer's trust assignment is auditable, not arbitrary.

| Upstream DQ/Conflict | Severity | Downstream metrics it downgrades | Resulting trust |
|---|---|---|---|
| `DQ.002`/`C.001`/`C.005` (4-way AR conflict) | CRITICAL | `M.AR.001A-D`, `M.AR.002`, `M.AR.003`, `M.RISK.001`, transitively `M.LIFE.004` (via `M.AR.001B`) | `M.AR.001A/B`→SHOW_BOTH; `M.AR.001C/D`→BLOCK; `M.LIFE.004` stays SAFE (single-convention use, disclosed) |
| `DQ.019`/`C.003` (`tenant_transactions` frozen) | CRITICAL | `M.AR.001D` specifically | BLOCK (catastrophic ~120x misuse risk) |
| `DQ.016`/`C.010`/`C.011` (owner-rent omission) | CRITICAL | `M.OWN.002`, `M.PROFIT.001` | SHOW_BOTH / BLOCK |
| `DQ.001` (invoice internal drift, 42.7%) | CRITICAL | `M.INV.001` (individual-invoice trust only; aggregate total unaffected) | DISCLOSE |
| `DQ.004`/`DQ.005`/`C.006`-`C.009` (occupancy family) | HIGH | `M.OCC.001`, `.002`, `.005`, transitively `M.TEN.001-003` (NOT downgraded — they use the unambiguous enum count, not a occupancy-% formula) | SHOW_BOTH for occupancy-% metrics; SAFE preserved for raw status counts |
| `DQ.015`/`C.012`/`C.013` (P&L bucket gap) | HIGH | `M.EXP.002` only (NOT `M.EXP.001`, the total is unaffected — proven) | DISCLOSE |
| `DQ.028` (EB billing_month format) | HIGH | `M.EB.001`, `M.EB.002` | DISCLOSE |
| `DQ.030`/`C.021` (wrong account_code, proven by execution) | HIGH | No metric in the registry currently exposes `get_universal_metrics_series.collections` directly — this finding **pre-emptively blocks** that function's output from ever being added to the registry until fixed | N/A (not yet a registry metric — a guard rail for future additions) |
| `DQ.008`/`C.016` (deposit settlement 2x pattern) | HIGH | `M.DEP.002`, `M.DEP.003` | DISCLOSE |
| `DQ.006`/`C.014`, `DQ.007`/`C.015` (receipt/invoice ledger drift) | MEDIUM | `M.COL.003`, `M.INV.001` (ledger cross-check only, not the source totals) | DISCLOSE |
| `DQ.013`/`C.020` (duplicate invoices, no dedup mechanism) | HIGH | `M.INV.001`, `M.INV.002`, `M.RISK.005`, transitively `M.PROFIT.001` Def B | DISCLOSE / BLOCK (profit) |
| `DQ.011`/`DQ.012` (deposit risk) | HIGH/MEDIUM | `M.DEP.001` (NOT downgraded — the balance total is exact); `M.RISK.003`, `M.RISK.004` | SAFE preserved for `M.DEP.001`; DISCLOSE for the risk-framed metrics |
| `DQ.003` (overlapping allotments) | MEDIUM | `M.OCC.001`-`005` (guarded against by `get_occupancy_intelligence`'s explicit merge, NOT guarded against by the simpler EXISTS-based snapshot definitions — though proven immaterial there too, since `H.013` shows 0 Staying/On-Notice overlap specifically); `M.RISK.007` itself | DISCLOSE (risk metric); no downgrade to the EXISTS-based occupancy snapshot metrics (proven immaterial) |
| `DQ.018`/`C.019` (aging snapshot dependence) | MEDIUM | `M.RISK.002` | DISCLOSE (reproducibility hazard, not a value conflict) |
| `DQ.026` (polymorphic orphan coverage gap) | MEDIUM | No specific registry metric downgraded directly — this is a **verification-coverage caveat** that should attach to any metric relying on `journal_entries.source_id` for `owner_payments`/`tenant_adjustments`/`assets`/`asset_payments`/`eb_payments` specifically (not `invoices`/`receipts`/`expenses`/`deposit_settlements`, which ARE checked) | Caveat only, not a status change |

**No false dependency was created.** Several plausible-looking chains were checked and are
explicitly **not** asserted here because the evidence does not establish them:
- `DQ.003` (overlapping allotments) does **not** downgrade `M.TEN.001`/`002` (Staying/On-Notice
  counts) — `H.013` proves 0 overlap specifically for those two statuses.
- `DQ.028` (EB format) does **not** propagate to `M.PROFIT.001` or `M.EXP.001`/`002` — no
  evidence connects EB's billing_month format to the ledger total or category-bucket
  reconstruction, which use `entry_date`, not `billing_month`, throughout.
- `C.023` (maintenance cost linkage) does **not** downgrade `M.MAINT.001`/`002` to DISCLOSE —
  it was **checked and disproven** for this dataset (both paths agree exactly); it remains
  documented as a structural risk, not an active discrepancy.

---

## 7. Full-stack summary (all six layers, condensed)

```
Raw evidence (253 CSVs, immutable)
   |
Business logic (25 exported trigger/function bodies + 458 signature-only routines)
   |
Accounting/operational concepts:
   v_account_balances | raw journal_lines (2 reversal conventions) | bed/apartment/allotment state
   |
49 semantic metrics (metric_registry.csv / semantic_metric_registry.csv):
   18 SAFE | 17 DISCLOSE | 8 SHOW_BOTH | 4 BLOCK | 2 NOT_DETERMINABLE
   |
Business KPIs (composite, e.g. "collection efficiency", "net margin %", "vacancy rate"):
   EVERY composite KPI inherits the WORST trust level of its inputs -- a KPI combining
   one SAFE and one BLOCK metric is itself effectively BLOCK for that composite view,
   even though its SAFE component may still be quoted on its own.
   |
AI insights (business_insight_framework.md -- specification only, not implemented):
   FACT -> TREND -> ANOMALY -> DRIVER -> IMPACT -> EXPLANATION -> RECOMMENDATION -> CONFIDENCE
   Every stage must carry forward the trust level and caveat text of the metrics it touches.
```
