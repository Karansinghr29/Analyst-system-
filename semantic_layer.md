# Semantic Layer Specification

Canonical semantic layer for the future AI Business Analytics system, built entirely on top of
the already-completed and validated deliverables: `data_inventory.md`, `business_logic.md`,
`conflicts.md`, `data_quality_report.md`/`data_quality_registry.csv`,
`metric_reconstruction.md`/`metric_registry.csv`, and their validation scripts/results. **No new
evidence was gathered for this document** — every fact below traces to one of those files, which
themselves trace to the exported CSV package. Nothing here is invented.

This document does not re-derive numbers. Where a figure is quoted, it is the number already
established and validated in `metric_reconstruction.md`. Where this document says a concept is
"resolved," "conflicting," or "not determinable," that status is inherited unchanged from
`conflicts.md` / `data_quality_report.md` / `metric_registry.csv`'s `ai_trust_status` column —
never re-judged here.

**How this document is organized.** One section per business area (17 areas, per the brief).
Within each area, one entry per **semantic concept** — a concept may correspond to a single
metric (`metric_registry.csv` row) or to a family of competing metrics that must never be
collapsed (e.g. "tenant dues" spans four metric rows, `M.AR.001A`–`D`). Every entry uses the
same field template; a field reads **"Not determinable from exported evidence."** or
**"Conflicting definitions exist."** verbatim where that is the honest state, never a guess.

**Trust classification legend** (identical vocabulary to `metric_registry.csv`/
`data_quality_report.md`, not redefined here):
`SAFE` — canonical, answer directly. `DISCLOSE` — answer, but always attach the caveat.
`SHOW_BOTH` — never state one number; present every competing definition, labelled.
`BLOCK` — never state a single definitive number at all. `NOT_DETERMINABLE` — reconstructable
in principle, but no reference exists to confirm it, and the AI must say so.

---

## Index by trust classification

Every concept in this document, grouped by its trust classification (from
`metric_registry.csv`/`semantic_metric_registry.csv`; counts match those files exactly).

**Canonical / SAFE (18):** Revenue (total), Revenue by month, Expenses (total), P&L by month,
Cash balance, Trial balance, Deposit held, Owner payments (source total), Staying tenants,
On-Notice tenants, Booked beds, Tenant lifecycle status derivation, Move-ins, Move-outs, Exit
reconciliation, Maintenance volume, Maintenance cost, Data-quality score meta-metric.

**Disclose-with-caveat (17):** Collections (application-level and ledger-derived), Collections
by month, Invoice billed amount, Invoice count, Expenses by category, Deposit settlements,
Deposit refunds, EB usage/cost, EB tenant allocation, Aging, Deposit risk, Phantom deposits,
Duplicate invoices, Duplicate receipts, Overlapping allotments, Ledger/source reconciliation.

**Show-both (8):** Tenant dues Def A (`v_outstanding_receivables`), Tenant dues Def B
(`v_tenant_current_dues`), Tenant dues by tenant, Tenant dues by property, Owner rent (3
definitions), Current occupancy (5+ definitions), Occupancy by property, Historical occupancy.

**Blocked (4):** Tenant dues Def C (application `balance_due`), Tenant dues Def D
(`tenant_transactions`), Gross/net profit (3 definitions), Outstanding dues (Risk/DQ framing of
the AR conflict).

**Unverified / not determinable (2):** Occupancy by apartment, Occupancy by bed (both fully
specified from source, neither has an exported reference to validate against).

---

## 1. Revenue

### Revenue (total, ledger-derived) — `M.REV.001`

- **Semantic name:** Revenue (total, ledger-derived)
- **Business meaning:** Total income recognised across all INCOME-type ledger accounts (rental,
  electricity, guest stay, onboarding, late fees, exit charges, other).
- **Exact source evidence:** `journal_lines`, `journal_entries`, `coa_accounts` (raw tables);
  `v_pnl` (`F.001`), `v_revenue_by_period` (`F.003`) as the exported business-view reference.
- **Source tables/views:** See above.
- **Source columns:** `journal_lines.debit/credit/account_id`; `journal_entries.entry_date`,
  `is_reversal_of`; `coa_accounts.account_type`, `normal_balance`.
- **Joins:** `journal_lines JOIN journal_entries ON journal_entry_id`, `JOIN coa_accounts ON
  account_id`.
- **Filters:** `coa_accounts.account_type = 'INCOME'`.
- **Date semantics:** `journal_entries.entry_date` — a fixed historical fact, not
  `CURRENT_DATE`-derived.
- **Aggregation:** `SUM(signed_amount)`, `signed_amount = CASE normal_balance WHEN 'CREDIT' THEN
  credit-debit ELSE debit-credit END`.
- **Grain:** organization (single org in this dataset) × property (`property_id`, including a
  small NULL/"manual" bucket) × month, when time-sliced.
- **Dimensions:** organization, property, time (month), account (chart-of-accounts income
  sub-accounts).
- **Reversal treatment:** EXCLUDED — reversal-excluded convention (`v_account_balances`).
  **Proven** (not assumed) equivalent in total to the reversal-included convention (`conflicts.md`
  C.002; balances net to zero identically either way).
- **Soft-delete treatment:** Not filtered directly — a soft-deleted source row's reversal entry
  is already excluded by the same `is_reversal_of` rule, so its net contribution is zero.
- **Historical vs current:** Historical, fixed. Ledger span 2019-11-03 to 2026-09-20 (54 months
  with ledger activity).
- **Dependencies:** None upstream (foundational metric).
- **Known limitations:** Revenue by individual posting can drift under repeated edits (see
  Collections/Invoices below), but this has NOT been shown to affect the aggregate INCOME total
  (proven exact against `F.001`).
- **Data-quality dependencies:** None.
- **Conflict IDs:** None.
- **Trust classification:** **SAFE.**
- **AI handling rule:** Answer directly. May be time-sliced or property-sliced.

### Revenue by month — `M.REV.002`

Same concept, at monthly grain, GROUP BY `(property_id, month)` — **`property_id` is a required
part of the grain**, not optional: a calendar month with both a real-property posting and a
NULL-property ("manual"/unlinked) posting produces two separate rows in `v_pnl`, and collapsing
that grain undercounts the row set (though not the dollar total). Trust: **SAFE** — validated
exactly against `F.001`'s 57 monthly rows (0 value mismatches). See `M.REV.002` in
`metric_reconstruction.md` for the full template.

---

## 2. Collections

### Collections (application-level) — `M.COL.001`

- **Business meaning:** Cash actually collected from tenants via receipts, as the application
  records it.
- **Exact source evidence:** `receipts` table directly; cross-checked against `H.001`'s
  `legacy_amount` for receipts.
- **Source columns:** `receipts.amount_paid`, `receipt_type`, `payment_date`, `is_deleted`.
- **Filters:** `is_deleted = false` (live rows only).
- **Date semantics:** `payment_date`.
- **Aggregation:** `SUM(amount_paid)`; `deposit_collections` = same, `WHERE receipt_type='booking'`.
- **Grain:** organization × (tenant/allotment for drill-down). Property not directly carried —
  requires a join through `tenant_allotments`.
- **Reversal treatment:** NOT APPLICABLE — a source-table definition, no ledger involvement.
- **Soft-delete treatment:** Live rows only (`is_deleted=false`), matching
  `get_universal_metrics`'s own convention.
- **Historical coverage:** 2022-11-30 to 2026-08-28 (46 months).
- **Known limitations:** Excludes the ~0.15% still-live, undeduplicated flagged-duplicate
  receipts (`DQ.014`); does not reconcile against the ledger by default.
- **Conflict IDs:** `C.014` (vs. the ledger-derived definition below).
- **DQ IDs:** `DQ.006`, `DQ.014`.
- **Trust classification:** **DISCLOSE.**
- **AI handling rule:** Answer with the application-level figure by default (it is the more
  intuitive "what did we collect" number), but always attach: *"a separate, ledger-derived
  collections figure exists and differs by ~6.5% at the aggregate diagnostic level;
  individual-receipt figures can differ further under repeated edits."*

### Collections (ledger-derived) — `M.COL.003`

- **Business meaning:** Cash inflow recognised in the ledger against receipts, on the cash/bank
  accounts (`1110`/`1120`).
- **Source columns:** `journal_lines.debit`, `account_id`; `journal_entries.source_table`,
  `entry_date`, `is_reversal_of`; `coa_accounts.code`.
- **Filters:** `source_table='receipts' AND code IN ('1110','1120')`.
- **Aggregation:** `SUM(CASE WHEN is_reversal_of IS NULL THEN debit ELSE -debit END)` — a THIRD
  reversal convention (sign-inversion netting), distinct from both `v_account_balances` and
  `v_tenant_current_dues`'s conventions (`business_logic.md` §1.3, definition C).
- **Reversal treatment:** INCLUDED via sign-inversion netting.
- **Known limitations:** `H.001` (`v_je_amount_reconciliation`) flags an `INVESTIGATE` gap of
  Rs.5,340,795.62 against `M.COL.001` at the aggregate diagnostic level — a suspected (not
  proven) repost-accumulation artifact concentrated in edited receipts, not shown to affect
  `v_pnl`'s own revenue total (which uses the reversal-excluded convention and is proven exact).
- **Conflict IDs:** `C.014`. **DQ IDs:** `DQ.006`, `DQ.030` (this reconstruction pattern is also
  what proves `get_universal_metrics_series`'s `account_code='1000'` bug returns exactly Rs.0.00).
- **Trust classification:** **DISCLOSE.**
- **AI handling rule:** Only surface this figure when specifically asked about ledger-side
  collections or reconciliation; always disclose the gap vs. `M.COL.001`.

**Collections by month** (`M.COL.002`) — same as `M.COL.001` at monthly grain. **DISCLOSE.**

---

## 3. Invoices

### Invoice billed amount — `M.INV.001` / Invoice count — `M.INV.002`

- **Business meaning:** Total amount charged to tenants via invoices (rent, electricity, other
  charges, late fees), regardless of payment status; and how many invoices were issued.
- **Source columns:** `invoices.total_amount`, `rent_amount`, `electricity_amount`,
  `other_charges`, `late_fee`, `invoice_type`, `status`, `billing_month`, `invoice_date`,
  `is_deleted`.
- **Filters:** `is_deleted = false`.
- **Date semantics:** `COALESCE(invoice_date, (billing_month||'-01')::date, created_at::date)`
  per `get_universal_metrics`'s own construction, or `invoice_date` alone for a simpler
  reconstruction.
- **Aggregation:** `SUM(total_amount)` / `COUNT(*)`.
- **Historical coverage:** 2023-02-05 to 2026-09-20 (44 months, plus a small forward-dated tail).
- **Reversal treatment:** NOT APPLICABLE (source-table). The ledger-derived counterpart (via
  `H.001`/`H.049`) shows an `INVESTIGATE`-flagged Rs.2,423,270.00 aggregate gap, fully row-traced
  to 120 specific, repeatedly-edited invoices (`C.015`/`DQ.007`).
- **Known limitations:** 6.8% of live invoices (356 of 5214, in 322 groups) are duplicate rows
  with **no application-level deduplication mechanism at all** (`C.020`/`DQ.013`). Also
  internally inconsistent at the row level: 42.7% of live invoices show
  `amount_paid+balance ≠ total_amount` (`DQ.001`, CRITICAL).
- **Conflict IDs:** `C.015`, `C.020`. **DQ IDs:** `DQ.007`, `DQ.013`.
- **Trust classification:** **DISCLOSE.**
- **AI handling rule:** Answer with the raw total/count, but always disclose the 6.8%
  duplicate-row population and the 42.7% internal-consistency issue when the question concerns
  an individual invoice's paid/balance status specifically (route those questions to
  `v_invoice_settlement_status`, the ledger-derived settlement view, rather than the invoice
  row's own `amount_paid`/`balance` columns — see `conflicts.md` C.004).

---

## 4. Receivables / tenant dues

**This is the single most consequential SHOW_BOTH/BLOCK family in the entire semantic layer.**
Four structurally different, independently-sourced definitions of "what does a tenant owe"
coexist. **None may ever be silently preferred.**

### Def A — `v_outstanding_receivables` — `M.AR.001A`
- Ledger AR balance only (account `1200`), reversal-**excluded** convention.
- Grain: tenant × allotment. **Trust: SHOW_BOTH.**

### Def B — `v_tenant_current_dues` — `M.AR.001B`
- Ledger AR balance **plus** deposit-held **plus** booking-advance (accounts `1200`/`2100`/`2400`),
  reversal-**included** convention.
- Grain: tenant × allotment. **Trust: SHOW_BOTH.**
- **A total is PROVEN identical to Def A** (Rs.83,297.85 both, `conflicts.md` C.002/`AR.03` in
  `metric_reconstruction.md`) — reversal convention does not move the AR total. Population
  (626 vs. 645 rows) and scope (Def B alone carries deposit/advance) differ.

### Def C — application `tenant_allotments.balance_due` — `M.AR.001C`
- Application-maintained column, writer not among the 25 exported function bodies.
- Sum Rs.1,009,125.78 — ~12× the ledger total, disagreeing with the ledger on 68 allotments
  showing a "phantom" app-side balance where the ledger shows zero, and 24 the reverse.
- **Trust: BLOCK.**

### Def D — `tenant_transactions` (frozen legacy ledger) — `M.AR.001D`
- Frozen: all 16,451 rows loaded in an 11-day 2026-04 migration window, never wired to a live
  posting trigger (`DQ.019`). **Two sub-variants exist and are BOTH preserved** (unclipped sum,
  Rs.9,968,023.32, proven to match `H.052`'s own basis exactly; and a `GREATEST(...,0)`-floored
  sum, Rs.10,517,031.27, matching the separate `v_diag_allotment_balance_drift`/`H.044`
  convention) — ~120× the ledger total either way.
- **Trust: BLOCK.**

**Exact numerical differences:** ledger (A=B) Rs.83,297.85 ↔ app (C) Rs.1,009,125.78 (12.1×) ↔
legacy unclipped (D) Rs.9,968,023.32 (119.7×) ↔ legacy floored (D) Rs.10,517,031.27 (126.3×).

- **Known limitations:** No evidence in the exported package proves which of the four the
  business currently relies on operationally.
- **Conflict IDs:** `C.001`, `C.003`, `C.005`. **DQ IDs:** `DQ.002`, `DQ.019`, `DQ.023`.
- **AI handling rule:** For **any** "what does tenant X owe" or "total outstanding dues"
  question: **BLOCK a single number.** State the ledger figure (A/B, identical) as the
  accounting-system answer, explicitly flag that the application-stored figure (C) and the
  legacy table (D) disagree by one to two orders of magnitude, and never average, blend, or pick
  one without disclosing the others. This is the standing example the brief itself gives
  (`AR definition conflict → tenant dues → collection efficiency → cash-flow interpretation → AI
  recommendations` — see `metric_dependency_graph.md`).

**Tenant dues by tenant** (`M.AR.002`) and **by property** (`M.AR.003`) inherit this exact
four-way conflict at their respective grains. **SHOW_BOTH** (framed as drill-downs of A/B/C/D,
not new definitions).

---

## 5. Deposits

### Deposit held — `M.DEP.001`
- Ledger account `2100` balance, reversal-excluded, tenant-scoped. Validated exact against `F.010`
  (`v_advance_balances`), Rs.4,221,150.00. No competing definition found. **Trust: SAFE.**

### Deposit risk / Phantom deposits — `M.RISK.003` / `M.RISK.004`
- 32 allotments hold a deposit (`tenant_allotments.deposit_paid > 0`) with `staying_status IN
  ('Exited','Cancelled')` and **no matching `deposit_settlements` row at all**. Rs.722,700.00 at
  risk (a figure computed for the first time during `metric_reconstruction.md`, not previously
  stated). Validated exact against `H.045` (`v_diag_deposit_phantom`).
- **Conflict IDs:** none. **DQ IDs:** `DQ.011`, `DQ.012`.
- **Trust classification:** **DISCLOSE.** This is real, unresolved financial exposure — an
  operational gap, not a reporting artifact — and should be surfaced proactively as a risk
  insight (see `business_insight_framework.md`), not merely on request.

---

## 6. Deposit settlements

### Deposit settlements — `M.DEP.002` / Deposit refunds — `M.DEP.003`

- **Business meaning:** Settlement transactions (deductions + refund) processed for exited
  tenants; the ledger-posting gate is `status IN ('completed','approved') AND NOT is_deleted`
  (`trg_settlement_journal_post`, body fully exported).
- **Source columns:** `deposit_settlements.deposit_amount`, `pending_rent/eb/late_fees`,
  `damages`, `other_deductions`, `total_deductions`, `refund_amount`, `status`,
  `settlement_date`, `is_deleted`.
- **Date semantics:** `settlement_date`.
- **Historical coverage:** 2023-04-03 to 2026-09-20 (35 months).
- **Reversal treatment:** Ledger side follows the standard reverse-and-repost mechanism on
  status transitions and amount edits (`business_logic.md` §5.1).
- **Soft-delete treatment:** Source: `NOT is_deleted`. Ledger: a hard-delete triggers a generic
  cascade-delete of the journal entry (physical removal), not a reversal (`business_logic.md`
  §1.4).
- **Known limitations:** Source-vs-ledger gap of Rs.583,495.34 (10.3%), with a **strong**
  suspected (not proven) mechanism — 23 of 43 drifting rows show `ledger_amount` at exactly
  2.0000× `source_amount`, all with `entry_count=3`, consistent with a non-reversal-aware `SUM`
  in the diagnostic query itself (`C.016`/`DQ.008`, the strongest mechanistic lead among the
  three source-vs-ledger conflicts).
- **Conflict IDs:** `C.016`. **DQ IDs:** `DQ.008`, `DQ.012`.
- **Trust classification:** **DISCLOSE.**
- **AI handling rule:** Answer with the source total (`refund_amount`) by default; disclose the
  ledger gap and the 2× pattern only when the question concerns ledger reconciliation
  specifically.

---

## 7. Occupancy

**A second major SHOW_BOTH family — five-plus non-interchangeable definitions.** The brief
requires this document to state which definition an answer uses; the AI must never silently
pick one.

| Def | Basis | Bed universe | Numerator | Result |
|---|---|---|---|---|
| A (`v_occupancy`) | Staying only | Live bed ∩ Live apartment | 168 | 168/195 = 86.15% |
| B | Staying + On-Notice | Live bed ∩ Live apartment | 175 | 175/195 = 89.74% |
| C | Staying + On-Notice | ALL beds (no Live filter) | 175 | 175/203 = 86.21% |
| D (`get_universal_metrics` v1) | Staying only | bed.status=Live only | 168 | 168/195 |
| E (`get_bed_occupancy_timeline`) | Staying+On-Notice+Exited, **historical** | ALL beds | 194 | 194/203 = 95.57% (lifetime, not a snapshot) |

`get_universal_metrics_v2` additionally computes `occupancyPct = (occupied+notice)/total`
(matching Def B's numerator basis) **plus** a sixth metric, `monthOccupancyPct` — a genuinely
distinct day-weighted rate for the current calendar month only. `get_occupancy_intelligence`
adds a **seventh** family: day-weighted, window-bounded, per-bed/apartment/property scoring with
overlap-merged intervals (function body fully exported, but has **no exported output rows** —
`NOT_DETERMINABLE` for validation, though fully reconstructable).

**The 7 unbucketed On-Notice beds (item 8 in the original brief) — resolved, proven mechanism.**
`v_occupancy`'s own `on_notice` output column requires a bed to be simultaneously `Staying` AND
`On-Notice`, which `H.013` proves NEVER happens (0 of 203 beds). The 7 beds whose only allotment
is `On-Notice` therefore fail **all four** of `v_occupancy`'s buckets (`occupied`/`on_notice`/
`booked`/`vacant`) — a **proven SQL defect**, not a legitimate alternative definition.
`get_universal_metrics` (both versions) does **not** share this defect (independently confirmed).

- **Grain:** organization × property × bed (native grain for snapshot Defs A–D); day-range for
  Def E and `get_occupancy_intelligence`.
- **Historical coverage:** `tenant_allotments.onboarding_date` 2019-11-03 to 2026-08-31 (67
  months — the widest span in the package).
- **Snapshot/current-state behavior:** Defs A–D are current-state snapshots (no
  `CURRENT_DATE` dependency in the SQL beyond current allotment state). Def E and
  `get_occupancy_intelligence` are explicitly historical, clamped to `LEAST(p_to, CURRENT_DATE)`
  to never count future days.
- **Duplicate treatment:** `H.056` documents 187 overlapping `tenant_allotments` pairs on the
  same bed. Defs A–D's `EXISTS`-based checks are unaffected (a bed with 2 overlapping `Staying`
  allotments still just registers `has_staying=true`); any occupied-**days** calculation (Def E,
  `get_occupancy_intelligence`) **must** merge overlapping intervals or double-count days —
  `get_occupancy_intelligence`'s SQL is confirmed to do this via an explicit gaps-and-islands
  merge.
- **Conflict IDs:** `C.006`, `C.007`, `C.008`, `C.009`. **DQ IDs:** `DQ.004`, `DQ.005`.
- **Trust classification:** **SHOW_BOTH** for "current occupancy" as a whole (`M.OCC.001`,
  `M.OCC.002`, `M.OCC.005`). `M.OCC.003` (by apartment) and `M.OCC.004` (by bed) are
  **NOT_DETERMINABLE** — reconstructable, unvalidated (no reference output exists).
- **AI handling rule:** "What is current occupancy?" must **name the definition used** in the
  answer (recommend Def B/`get_universal_metrics_v2`'s convention as the semantic layer's
  suggested default, per `conflicts.md`'s recommended handling for `C.007`, since it is the more
  recent convention and avoids the `v_occupancy` defect) and disclose that alternative
  definitions exist and can differ by up to 9.4 percentage points. Never use `v_occupancy`'s
  `on_notice`/`vacant` columns downstream (proven defective).

---

## 8. Tenants

### Staying tenants / On-Notice tenants / Booked beds — `M.TEN.001`/`002`/`003`

Unambiguous `staying_status` enum counts (`tenant_allotments.staying_status IN
('Staying'|'On-Notice'|'Booked')`), validated exactly against `H.013`/`H.014`/`F.022`. **Trust:
SAFE** for all three. The On-Notice count (7) is the exact population that `v_occupancy`'s SQL
defect drops (§7 above; `C.009`).

- **Grain:** organization × property × tenant/allotment (or bed, for the physical count).
- **Historical coverage:** Full `tenant_allotments` history, 2019-11 to 2026-08.
- **Known limitations:** `H.056`'s 187 overlapping-allotment pairs mean a bed can, in general,
  carry two simultaneous allotments of the same status — confirmed **zero** such cases for
  Staying/On-Notice specifically (`H.013`), but not separately checked for the Staying-vs-Staying
  case generally.

---

## 9. Tenant lifecycle

### `staying_status` derivation — `M.LIFE.001`

- **Business meaning:** `tenants.staying_status` is **derived, never independent**: priority
  order Staying(1) > On-Notice(2) > Booked(3) > else(4), tie-broken by most-recently-created
  allotment, kept in sync by `sync_tenant_staying_status` (AFTER INSERT/UPDATE) and
  `sync_tenant_staying_status_on_delete` (AFTER DELETE) — **both trigger bodies fully exported
  and read in full**, not inferred from name.
- **Grain:** tenant (can span properties/allotments).
- **Known limitations:** A tenant with multiple simultaneous allotments is tagged by whichever
  ranks highest, which can mask a lower-priority concurrent allotment's status.
- **Conflict/DQ IDs:** None.
- **Trust classification:** **SAFE** (the derivation rule itself is fully proven from source;
  not independently re-executed as an aggregate check since it is a row-level rule, not a total).

### Move-ins / Move-outs — `M.LIFE.002` / `M.LIFE.003`

- `tenant_allotments.onboarding_date` / `actual_exit_date`, sourced via `v_tenant_lifecycle_events`
  (`F.017`, **2204-row full population**). **Critical:** `H.036` exports only a `LIMIT 500`
  sample of this SAME view — **always use `F.017`, never `H.036`**, for a complete count.
- **Historical coverage:** onboarding 2019-11-03 to 2026-08-31 (67 months); exit 2022-11-20 to
  2026-09-20 (47 months, small forward-dated tail).
- **Trust classification:** **SAFE.**

### Exit reconciliation — `M.LIFE.004`

`v_exit_reconciliation_worklist` (`F.027`) — every currently-Exited allotment with a
nonzero AR balance, deposit, or advance held, joined to AR (Def B convention, reversals
INCLUDED — inherits `M.AR.001B`'s convention, not the reversal-excluded one), plus
EB-already-invoiced and exit-charge-already-invoiced lateral sums, plus the latest settlement
status. **Trust: SAFE** (every component independently validated elsewhere in this layer).

---

## 10. Expenses

### Expenses (total, ledger-derived) — `M.EXP.001`

Mirror of Revenue's construction, `account_type='EXPENSE'`, reversal-excluded. Validated exact
against `F.001`, Rs.20,784,831.96, 0 monthly mismatches. **Trust: SAFE.**

### Expenses by category — `M.EXP.002`

- **Business meaning:** Expense total broken into named categories.
- **Exact source evidence:** `v_pnl_by_category` (`F.002`) uses 9 hand-written
  `account_code LIKE` patterns (`owner_rent '510%'`, `maintenance '52%'`, `housekeeping '53%'`,
  `utilities '54%'`, `property_ops '55%'`, `administrative '56%'`, `salaries '57%'`,
  `marketing '58%'`, `other_expenses '59%'`). `v_expense_composition` (`F.019`) instead uses the
  actual COA parent-child hierarchy — a structurally different, second rollup convention.
- **Known limitation (proven, not suspected):** Account `5150` "Electricity Payments" matches
  **none** of the 9 named patterns. `v_pnl_by_category` computes a **separate, 10th
  `electricity` column** (`'515%'` pattern) that is invisible to the 9-bucket sum. Proven by an
  exact 57-month arithmetic identity: `unbucketed == electricity_column` in every single month
  (Rs.1,030,618.00, 4.96% of total expenses). **`v_expense_composition`'s COA-parent rollup DOES
  include account 5150 — under a shared "Operating Expenses" category with owner rent** — a
  third, different answer to "what category is electricity in." **Do not force electricity into
  utilities or any other named bucket — no evidence supports that mapping** (per the brief's
  explicit instruction); the correct handling is to add electricity as its own 10th named
  category.
- **Conflict IDs:** `C.012`, `C.013`, `C.022`. **DQ IDs:** `DQ.015`.
- **Trust classification:** **DISCLOSE.**
- **AI handling rule:** Any category-level expense breakdown must include electricity as its own
  line; disclose that it is absent from the 9 "named" buckets if a user's own report was built
  from `v_pnl_by_category` directly without electricity added.

---

## 11. Owner payments

### Owner payments (source total) — `M.OWN.001`

`SUM(COALESCE(escalated_amount, base_amount))` from `owner_payments`. **The only one of the 6
source-vs-ledger reconciliations in `H.001` with zero drift** — PROVEN PERFECT match to the
ledger. `owner_payments` has no `is_deleted` column (hard-delete only, cascades the journal
entry). **Historical coverage:** 2022-11-01 to 2026-08-01 (46 months, `bill_date`). **Known
limitation:** all 345 rows were ledger-posted in a single ~82-minute batch on 2026-08-13
(`DQ.020`) — `posted_at`/`created_at` do not reflect when the underlying payment activity
occurred; always use `bill_date`. **Trust: SAFE.**

### Owner rent (3 competing profit-inclusion definitions) — `M.OWN.002`

- Def i (`get_universal_metrics` v1): **excludes owner rent from profit entirely** — no
  `owner_payments` term anywhere in the formula (proven by reading the full function body).
- Def ii (`v_pnl_by_category`'s raw `owner_rent` bucket, `'510%'`): whatever is actually posted
  to the ledger — proven to equal Def i's underlying source exactly at the all-time total
  (Rs.19,019,250.00) but its own account-composition is not independently verified (the posting
  trigger's body is not among the 25 exported).
- Def iii (`get_universal_metrics_v2`): **explicitly substitutes** `SUM(owner_payments.
  escalated_amount)` filtered on `bill_date` for the ledger's owner_rent bucket before computing
  profit — read verbatim from source, not inferred.
- **A date-basis conflict compounds this:** the ledger-posting trigger and Def iii both use
  `bill_date`; `v_diag_owner_rent_missing_from_profit` instead groups by
  `COALESCE(paid_date, due_date)` — 7 of 54 months show a nonzero difference in monthly
  attribution despite the all-time totals agreeing exactly (`DQ.017`).
- **Conflict IDs:** `C.010`, `C.011`. **DQ IDs:** `DQ.016`, `DQ.017`, `DQ.020`.
- **Trust classification:** **SHOW_BOTH.**
- **AI handling rule:** Never quote a profit figure without stating whether owner rent is
  included; this is the direct mechanism behind `M.PROFIT.001`'s BLOCK status (§12).

---

## 12. Profit / P&L

### Gross/net profit — `M.PROFIT.001` — **the highest-severity conflict in the semantic layer**

Three definitions, **proven incompatible**, not interchangeable:
- **Def A** (`v_pnl`, ledger): revenue − expenses, both ledger-derived, whatever owner-rent
  amount happens to be posted.
- **Def B** (`get_universal_metrics` v1): `SUM(invoices.total_amount) − SUM(expenses.amount)`,
  application-table-derived, **no owner_payments term at all** — never touches the ledger.
- **Def C** (`get_universal_metrics_v2`): ledger revenue − (ledger expenses with the owner-rent
  bucket substituted per §11 Def iii) — owner-rent-inclusive by explicit correction.

**Exact, proven numerical consequence:** Def B omits Rs.19,019,250.00 of owner rent, producing
a **36.63% profit overstatement** relative to the owner-rent-inclusive figure (reproduced to
within 0.03 points of `conflicts.md`'s original 36.6% estimate, independently in
`metric_reconstruction.md`'s `PROFIT.06`). `v_diag_owner_rent_missing_from_profit`'s own `note`
column states this in plain text: *"Currently NOT included in get_universal_metrics.totalProfit."*

- **Reversal treatment:** Def A/C EXCLUDED (`v_account_balances` convention); Def B NOT
  APPLICABLE (never touches `journal_entries` — an invoice's ledger reversal has zero effect on
  Def B's profit).
- **Soft-delete treatment:** Def A/C inherited via reversal exclusion. Def B: `is_deleted=false`
  on invoices; `expenses` has no `is_deleted` column (all rows live).
- **Duplicate treatment:** Def B inherits invoices' 6.8% duplicate-row population unless
  de-duplicated; Def A/C do not (ledger-level, not source-row-level).
- **Historical coverage:** Def A/C span the ledger's full 2019-2026 window; Def B is not bounded
  by ledger availability and can include invoices dated beyond the ledger's last posted month (a
  1.06% scope-driven gap was found and explained, not a new defect, when reconstructing Def B
  all-time vs. `H.030`'s ledger-bounded 54-month figure).
- **Conflict IDs:** `C.010`, `C.011`. **DQ IDs:** `DQ.016` (CRITICAL), `DQ.017`.
- **Trust classification:** **BLOCK.**
- **AI handling rule:** **Never state a single profit figure.** "Why did profit fall/rise"
  cannot be answered without first establishing which definition the question concerns — an
  owner-rent posting-timing event (e.g. the 2026-08-13 single batch) moves Def A/C but not Def B
  at all, which alone can produce a fake divergent trend between the two.

### P&L by month — `M.PNL.001`

Revenue and expenses at monthly grain, joined; `net_profit = revenue - expenses`, **ledger-only
(Def A)** — this specific metric does NOT carry the three-way profit conflict, because it is
defined as the ledger figure only. **Trust: SAFE** (0 value mismatches across 57 rows). Category
breakdown at this grain inherits §10's electricity-bucket gap.

---

## 13. Maintenance

### Maintenance volume — `M.MAINT.001` / Maintenance cost — `M.MAINT.002`

- **Business meaning:** Ticket counts and cost of maintenance activity.
- **Historical coverage:** 2025-01-29 to 2026-08-29 (**20 months** — the shortest operational
  domain in the package). **No YoY comparison should be attempted.**
- **Known limitation, RESOLVED mechanism:** `H.019`'s previously-unexplained "1613 vs 1611
  tickets" gap is now **proven**: 2 tickets have 2 resolutions each (`H.018`), so joining
  `maintenance_tickets` to `ticket_resolutions` fans out by exactly +2 rows — 1611 + 2 = 1613
  exactly (a genuine discovery made during `metric_reconstruction.md`, resolving `DQ.027`'s
  previously "not determinable" item).
- **Two cost-linkage paths coexist** (`v_maintenance_metrics`/`F.015`, via
  `ticket_resolutions → expenses.ticket_resolution_id`, dated by ticket creation month; vs.
  `v_maintenance_by_issue_type`/`F.016`, via `expenses.issue_type_id` directly, dated by
  `expense_date`) — **structurally capable of disagreeing**, but **proven, for this dataset, to
  produce the identical total** (Rs.28,796.00, both paths, exact match) — an update to
  `conflicts.md` C.023's original "can disagree" framing worth carrying forward.
- **Conflict IDs:** `C.023`. **DQ IDs:** `DQ.027`.
- **Trust classification:** **SAFE** for both (validated exact against `F.015`/`F.016`).

---

## 14. EB / electricity

### EB usage and cost — `M.EB.001` / EB tenant allocation — `M.EB.002`

- **Business meaning:** Electricity consumption/cost at the property/apartment level, and its
  proportional allocation to tenants who occupied an apartment during a billing period.
- **Source columns:** `electricity_readings.units_consumed/unit_cost/billing_month`;
  `eb_payments.bill_amount/bill_date`; `eb_tenant_shares.total_apartment_bill/
  total_tenant_days/per_day_rate/tenant_stay_days/tenant_eb_charge`.
- **Allocation formula (reverse-engineered from data, not from an exported function body — no
  writer for `eb_tenant_shares` is among the 25 exported):** `per_day_rate =
  ROUND(total_apartment_bill / total_tenant_days)`; `tenant_eb_charge = per_day_rate ×
  tenant_stay_days`. **Proven exact across the FULL 801-row population** (upgraded from
  `business_logic.md`'s original 5-row spot-check).
- **Historical coverage:** `eb_payments` 2026-04-29 to 2026-06-27 — **only 2 months, the
  narrowest coverage of any financial domain in the package.** `electricity_readings` export
  window 5 months; `eb_monitoring_readings` a **single day** (2026-08-18), not a time series.
- **Known limitation, PROVEN, schema-level:** `electricity_readings.billing_month` and
  `eb_tenant_shares.billing_month` use `'Mon-YY'` text format (e.g. `'Apr-25'`) — **0%**
  conformance to `'YYYY-MM'`. Every other billing_month/payment_month column in the schema
  (`invoices`, `expenses`, `owner_payments`) uses `'YYYY-MM'` — **100%** conformance, confirmed
  across full table populations. Any join between EB tables and the rest of the billing system
  on billing_month **requires a format-conversion step first**; a naive `(billing_month ||
  '-01')::date` cast (the pattern used elsewhere in the codebase) would fail or misparse for EB.
- **Reversal treatment:** Source-level: not applicable. Ledger side: **Not determinable from
  exported evidence** — `trg_eb_payment_journal_post`'s body is not among the 25 exported.
- **Conflict IDs:** None. **DQ IDs:** `DQ.021`, `DQ.028`.
- **Trust classification:** **DISCLOSE.**
- **AI handling rule:** Never join EB billing_month to invoice/expense billing_month without
  disclosing the format mismatch; never build a trend from `eb_monitoring_readings` (1-day
  snapshot); disclose the narrow 2-month `eb_payments` coverage whenever an EB cost trend is
  requested.

---

## 15. Accounting / ledger

### Ledger foundation — `M.TB.001` (trial balance / accounting checks)

- **Business meaning:** Per-account debit/credit totals and the fundamental accounting-integrity
  identity (total debits = total credits).
- **Source columns:** `journal_lines.debit/credit/account_id`; `coa_accounts.code/name/
  account_type/normal_balance/parent_id`.
- **The most thoroughly validated concept in the whole semantic layer:** 8 of 8
  ledger-foundation checks (`LEDGER.01`–`08` in `validation_summary.csv`) matched their exported
  reference views **exactly** — row counts, debit/credit totals, both trial-balance conventions
  (`v_trial_balance`/`F.012` reversal-excluded, `v_trial_balance_detailed`/`F.013`
  reversal-included), and `H.007`'s 10-account reversal-effect set.
- **Reversal treatment:** **Both** conventions exist side by side and are **both exact** —
  `F.012` (24 accounts with activity, reversal-excluded) and `F.013` (57 accounts, all of COA,
  reversal-included). Gross turnover differs by Rs.17,693,638.16 on both debit and credit sides
  across 10 affected accounts (`H.007`); **balances themselves are unaffected** (`C.002`, proven).
- **Reversal mechanism (mechanistic, from full trigger-body reading, `business_logic.md` §1.3):**
  a reversal is a **second, separate** `journal_entries` row with `is_reversal_of` set — the
  original is never edited or deleted. `enforce_journal_balanced` (a hard DB constraint) proves
  every posted entry is debit=credit balanced.
- **Soft-delete treatment:** Soft-delete → `reverse_journal_entry` (adds a reversal, leaves the
  original in place). Hard-delete → a generic cascade trigger **physically deletes** the JE and
  its lines (not a reversal) for 7 of 8 posting source tables; `receipts` has both mechanisms
  wired, and the cascade-delete wins by alphabetical trigger-firing order (`business_logic.md`
  §1.4).
- **JE-survives-source-deletion mechanism (proven):** `financial_audit_log.journal_entry_id →
  journal_entries.id ON DELETE SET NULL` — the **audit log**, not `journal_entries` itself,
  survives a hard delete (its `journal_entry_id` goes NULL, the row and its frozen
  amounts/source reference persist permanently).
- **Conflict IDs:** `C.002`. **DQ IDs:** None specific to this metric (the source-vs-ledger
  drift diagnostics live under Collections/Invoices/Deposits above).
- **Trust classification:** **SAFE.**

---

## 16. Cash

### Cash balance — `M.CASH.001`

`SUM(signed_amount)` on cash/bank accounts (`1110`/`1120`), reversal-excluded, all-time running
total. Same construction pattern as Deposit Held (§5), which IS validated exactly — this metric
was **not independently re-executed** in the validation pass and is flagged honestly as such
("high confidence by analogy, not independently confirmed" — `metric_reconstruction.md`
`M.CASH.001` notes). **Represents the ledger's view of cash, not a bank-reconciled figure** — no
bank-statement evidence was exported. **Trust: SAFE** (by construction/analogy; recommend adding
an explicit validation check before full production reliance).

---

## 17. Operational KPIs / Risk / Data-quality metrics

This area is a cross-cutting umbrella over concepts already detailed above, framed as
risk/monitoring signals rather than descriptive metrics. Each entry below is a **direct
cross-reference**, not a re-derivation:

- **Outstanding dues** (`M.RISK.001`) = the §4 four-way AR conflict, framed as risk. **BLOCK.**
- **Aging** (`M.RISK.002`, `v_tenant_aging`/`F.008`): buckets by `CURRENT_DATE - charge_date`,
  reversal-included (Def B convention). **Not a competing-definition conflict — a reproducibility
  hazard** (`C.019`): the exported bucket assignments are frozen as of the export window
  (2026-08-29 09:02–11:18) and will not match a fresh reconstruction on any other date unless an
  explicit as-of date is fixed. **DISCLOSE**, always with the as-of date stated.
- **Deposit risk / Phantom deposits** — see §6/§5. **DISCLOSE.**
- **Duplicate invoices** (`M.RISK.005`, `C.020`/`DQ.013`) and **duplicate receipts**
  (`M.RISK.006`, `C.018`/`C.020`/`DQ.014`) — invoices have **no** application-level dedup
  mechanism at all (322 groups, 356 excess rows, Rs.4,040,627.00 combined group value); receipts
  have a **partial, non-remediated** one-time detection pass (9 groups, 23 ids, only 11 still
  live and none soft-deleted — 12 were hard-deleted outside the system's own soft-delete
  convention, confirmed by direct cross-check). **DISCLOSE** for both.
- **Overlapping allotments** (`M.RISK.007`, `DQ.003`): 187 (`H.056`'s figure) to 214
  (this project's own independent re-implementation) overlapping bed/allotment pairs — the only
  metric in the whole reconstruction with an unresolved-but-explained (boundary-condition
  sensitivity) count discrepancy against its own reference. **DISCLOSE.**
- **Ledger/source reconciliation** (`M.RISK.008`) = the umbrella over §2/§3/§6's three
  source-vs-ledger drift findings (receipts Rs.5.34M/6.5%, invoices Rs.2.42M/3.3% fully
  row-reconciled, deposit settlements Rs.583K/10.3% with the suspected 2× mechanism). **DISCLOSE.**
- **Data-quality score / trust status** (`M.RISK.009`): a meta-metric — `COUNT(*) GROUP BY
  ai_trust_status` over this very semantic layer's own registry. **SAFE** (self-validating,
  re-derive on every registry update, never hardcode into the AI layer).

---

## Cross-check against the source registries (required verification)

- Every metric ID referenced above (`M.REV.*` through `M.RISK.*`) exists verbatim in
  `metric_registry.csv` and `semantic_metric_registry.csv`, with **identical** `ai_trust_status`
  / `trust_level` values — confirmed programmatically (0 mismatches) when
  `semantic_metric_registry.csv` was built from `metric_registry.csv`.
- Every conflict ID (`C.001`–`C.024` referenced) and DQ ID (`DQ.001`–`DQ.032` referenced) is
  quoted verbatim from `conflicts.md`/`data_quality_report.md`'s own section titles — no
  conflict/DQ ID was invented or renumbered for this document.
- No dimension, relationship, or business rule appears above that is not already established in
  `business_logic.md`, `conflicts.md`, or `data_quality_report.md`. See `business_dimensions.md`
  for the formal dimension catalog.
