# Business Dimensions Specification

Dimensions the future AI Business Analytics system may slice, filter, or group metrics by.
**Every dimension below is supported by exported evidence** — column existence, cardinality, and
key structure were confirmed in `data_inventory.md`/`business_logic.md`/`metric_reconstruction.md`
during earlier deliverables; none is proposed speculatively here. Where a dimension's practical
usefulness is limited by the data (e.g. single-organization, single-property), that limit is
stated explicitly rather than glossed over.

**Rule enforced throughout:** `created_at` is used as a dimension's business date **only** where
this has been independently proven (`maintenance_tickets`, which has no separate business-open
date). Everywhere else, `created_at` is a bulk-load/system timestamp — confirmed by the
2026-03-28 backfill pattern shared by `invoices`, `receipts`, `tenant_allotments`,
`tenant_adjustments` (`business_logic.md` §9.1a) — and is never substituted for the true business
event date.

---

## 1. Time

- **Definition:** The calendar dimension underlying every trend, period comparison, and
  historical reconstruction.
- **Source:** No dedicated date table — time is derived per-domain from each table's own business
  date column (see the domain-specific dimensions below and `metric_reconstruction.md` §4's
  historical coverage table).
- **Key:** Calendar date, or truncated to month (`date_trunc('month', ...)`) for most reporting
  grains.
- **Hierarchy:** day → month → fiscal year (India FY, April–March, per `get_universal_metrics`'s
  `current_fy`/`last_fy` period presets — `business_logic.md` on `get_universal_metrics`).
- **Valid values:** No fixed enum — bounded per-domain by each table's actual coverage (below).
- **Slowly-changing implications:** Not applicable (time itself does not change).
- **Current vs. historical meaning:** "Current" = as of `CURRENT_DATE`/the query moment — several
  metrics (`v_tenant_aging`, `get_universal_metrics`'s default period presets,
  `get_bed_occupancy_timeline`'s `LEAST(p_to, CURRENT_DATE)` clamp) are `CURRENT_DATE`-dependent
  and **not reproducible from a frozen export without fixing an explicit as-of date** — the
  package's own snapshot timestamp is `2026-08-29 09:02:03–11:18:26 UTC` (`M.002`/`M.099`).
- **Known data-quality issues:** (a) A small number of forward-dated rows exist past the
  snapshot in several tables — `journal_entries.entry_date`, `invoices.invoice_date`,
  `deposit_settlements.settlement_date`, `tenant_allotments.actual_exit_date` all reach
  2026-09-20 (`DQ.024`). (b) One corrupt date: `tenant_transactions.date` minimum is
  `0206-03-27` — a probable year-transposition of 2026 (`DQ.023`). (c) A placeholder/epoch date:
  `apartments.start_date = 1899-12-30` for 2 rows (`DQ.022`, both `Not-Active` apartments,
  minimal live impact). (d) EB tables' `billing_month` uses a different text format from every
  other billing-period column (`DQ.028` — see dimension 18 below).
- **Per-domain coverage (re-derived from `M.025`, not assumed):**

  | Domain | Range | Months | Business date column |
  |---|---|---|---|
  | Tenancy | 2019-11-03 to 2026-08-31 | 67 | `tenant_allotments.onboarding_date` |
  | Ledger | 2019-11-03 to 2026-09-20 | 54 | `journal_entries.entry_date` |
  | Receipts | 2022-11-30 to 2026-08-28 | 46 | `receipts.payment_date` |
  | Owner payments | 2022-11-01 to 2026-08-01 | 46 | `owner_payments.bill_date` |
  | Invoices | 2023-02-05 to 2026-09-20 | 44 | `invoices.invoice_date` |
  | Expenses | 2023-03-11 to 2026-08-24 | 35 | `expenses.expense_date` |
  | Deposits | 2023-04-03 to 2026-09-20 | 35 | `deposit_settlements.settlement_date` |
  | Maintenance | 2025-01-29 to 2026-08-29 | 20 | `maintenance_tickets.created_at` (no separate business-open date exists) |
  | EB (`eb_payments`) | 2026-04-29 to 2026-06-27 | **2** | `eb_payments.bill_date` |
  | `tenant_transactions` | nominal 2019-11 to 2026-05 | -- | `date`, but **frozen** — all 16,451 rows were `created_at` 2026-04-17 to 2026-04-28 (an 11-day migration) |

  **No YoY or month-over-month comparison should be recommended for maintenance (20 months) or
  EB (2–5 months)** — insufficient depth. Ledger, tenancy, receipts, owner payments, invoices,
  expenses, and deposits (35+ months) can support YoY once 2 full years of the relevant window
  exist.
- **Metrics that may safely use this dimension:** Any metric with a `Date field` documented in
  `metric_registry.csv` — i.e. essentially all Financial and Operations metrics — **provided**
  the correct per-domain business-date column is used, never `created_at` as a substitute.

---

## 2. Organization

- **Definition:** The tenant-of-the-SaaS-platform boundary (not to be confused with a residential
  tenant).
- **Source:** `organizations` table; `organization_id` foreign key present on 122 of 131 public
  tables (`M.007`).
- **Key:** `organizations.id` (UUID).
- **Hierarchy:** Top-level — organization → property → apartment → bed.
- **Valid values:** **Exactly 1 organization exists in this exported dataset** — `distinct_orgs =
  1` on every populated table that carries the column (`M.007`). This is effectively a
  single-tenant snapshot, not a genuine multi-org portfolio.
- **Known data-quality issues:** 4 tables carry NULL `organization_id` on a subset of rows —
  `whatsapp_events` (600 of 1943, 30.9%), `ticket_logs` (65 of 8239, 0.79%), `payroll_sync` (6 of
  18, 33.3%), `email_templates` (3 of 4, 75.0%) (`DQ.025`). An org-scoped filter
  (`WHERE organization_id = X`) will silently drop these rows via an equality join.
- **Current vs. historical meaning:** Not applicable (a stable identity dimension).
- **Metrics that may safely use this dimension:** All metrics carrying `organization_id` in
  their grain — in practice this dimension provides no real discriminating power in the current
  snapshot (single org), but the column/architecture is present and should be preserved for a
  genuine multi-org future.

---

## 3. Property

- **Definition:** A physical property (building/complex) the business operates.
- **Source:** `properties` table; `property_id` foreign key on `apartments`, and (for financial
  metrics) `journal_lines.property_id` where a posting carries it.
- **Key:** `properties.id` (UUID).
- **Hierarchy:** organization → **property** → apartment → bed.
- **Valid values:** **Exactly 1 property in this dataset** (`M.006`/`M.000`) — property-level
  breakdowns (`M.OCC.002`, `M.AR.003`, etc.) are **currently degenerate**, identical to the
  organization-level total, and not meaningfully testable as multi-property comparisons from the
  exported evidence.
- **Known data-quality issues:** Some ledger postings (`journal_lines.property_id`) carry NULL
  — `v_pnl`'s own grain includes a NULL-property "manual"/unlinked bucket (3 of 57 monthly rows,
  confirmed during `metric_reconstruction.md`'s revenue validation).
- **Current vs. historical meaning:** A property has a `status` field (`Live`/`Not-Active`, per
  `apartments`' analogous pattern) — not independently profiled at the property level in this
  pass.
- **Metrics that may safely use this dimension:** Any financial or occupancy metric that carries
  `property_id` in its grain (most of §1 in `semantic_layer.md`) — with the caveat above that a
  multi-property breakdown cannot be meaningfully validated until more than 1 property exists in
  the data.

---

## 4. Apartment

- **Definition:** A unit within a property, containing one or more beds.
- **Source:** `apartments` table (43 rows).
- **Key:** `apartments.id` (UUID); `apartment_code` (human-readable, e.g. `D13A`).
- **Hierarchy:** property → **apartment** → bed.
- **Valid values:** `status IN ('Live', 'Not-Active')` (per `H.008`'s bed×apartment status
  matrix). 38 Live, 5 Not-Active per `H.009`.
- **Slowly-changing / history implications:** `apartments.start_date`/`end_date` bound an
  apartment's availability window — used directly by `get_occupancy_intelligence` and
  `get_bed_occupancy_timeline` to clamp occupied-day calculations. **2 apartments carry a
  corrupted `start_date` of `1899-12-30`** (a classic spreadsheet epoch/null-placeholder
  artifact, `DQ.022`) — both are `Not-Active`, so this does not currently distort any live
  occupancy calculation, but would need correcting before either apartment is reactivated.
- **Current vs. historical meaning:** `status` is the current-state field; historical
  availability (for a since-decommissioned apartment) would need `end_date`.
- **Known data-quality issues:** `H.008` shows a `Not-Active` bed can exist inside a `Live`
  apartment (3 such beds) — i.e. bed and apartment status are independently maintained, not
  cascaded.
- **Metrics that may safely use this dimension:** All occupancy metrics (`M.OCC.001`–`005`),
  `M.EB.001`/`002` (electricity is billed per apartment), maintenance metrics (tickets/expenses
  carry `apartment_id`).

---

## 5. Bed

- **Definition:** The physical, billable unit of occupancy within an apartment.
- **Source:** `beds` table (203 rows).
- **Key:** `beds.id` (UUID); `bed_code`.
- **Hierarchy:** apartment → **bed** (the finest physical grain in the portfolio).
- **Valid values:** `status IN ('Live', 'Not-Active')`. 195 beds are Live-in-Live-apartment
  (the "Def A/B" occupancy denominator); 203 total beds (the "Def C/E" denominator). `bed_type`,
  `toilet_type` are further attributes (used by `get_occupancy_intelligence`'s `bed_type_label`
  grouping).
- **Slowly-changing / history implications:** **No `bed_status_history` audit trail exists** —
  that table is declared but holds **0 rows** (`data_quality_report.md` §5 / `DQ.029`). Bed
  status is a current-state-only field; historical bed status cannot be reconstructed from a log
  and must instead be inferred from `tenant_allotments` occupancy patterns where possible.
- **Current vs. historical meaning:** `status` reflects the CURRENT state only. Historical
  occupancy (which beds were occupied when) is reconstructed entirely from `tenant_allotments`
  date ranges (dimension 7 below), never from a bed-status log.
- **Known data-quality issues:** 187 pairs of `tenant_allotments` overlap on the same `bed_id`
  (`H.056`/`DQ.003`) — this project's own independent re-implementation found 214 pairs, a
  bounded, explained (boundary-condition sensitivity) discrepancy, not a data error per se.
- **Metrics that may safely use this dimension:** All occupancy metrics; `M.OCC.004` specifically
  (occupancy by bed) is fully specified but has **no exported reference to validate against**
  (NOT_DETERMINABLE status).

---

## 6. Tenant

- **Definition:** A resident (person) who has or had a lease/allotment.
- **Source:** `tenants` table (1027 rows, 27 PII columns excluded from the export per
  `M.027`/`evidence_integrity_report.md`).
- **Key:** `tenants.id` (UUID). No PII-based key (`phone`, `email`) is available offline.
- **Hierarchy:** tenant → (one or more) `tenant_allotments` (a tenant can hold multiple
  allotments over time, or — per `H.056` — even simultaneously, on the same or different beds).
- **Valid values / current status:** `tenants.staying_status` — a **derived, denormalised**
  field (see dimension 7), lower-cased from `tenant_allotments.staying_status` via a priority
  rule.
- **Slowly-changing implications:** A tenant's status changes whenever any of their allotments
  change, via `sync_tenant_staying_status`/`sync_tenant_staying_status_on_delete` (both trigger
  bodies fully exported). This is a **type-1 SCD pattern (overwrite)** at the `tenants` row —
  no history of past `tenants.staying_status` values is retained on that table; history must be
  reconstructed from `tenant_allotments` directly.
- **Known data-quality issues:** None specific to the tenant identity dimension itself (PII
  exclusion is by design, not a defect).
- **Metrics that may safely use this dimension:** `M.TEN.001`–`003`, `M.LIFE.001`–`004`,
  `M.AR.001A`–`D`/`002` (tenant-grain AR).

---

## 7. Tenant lifecycle / status (`tenant_allotments.staying_status`)

- **Definition:** The authoritative lifecycle state of one lease/allotment.
- **Source:** `tenant_allotments` table (1213 rows) — **this table, not `tenants`, is the
  source of truth**; `tenants.staying_status` is always derived from it (dimension 6).
- **Key:** `tenant_allotments.id` (the allotment), FK to `tenant_id` and `bed_id`.
- **Valid values (enum, `H.014`, exhaustive and confirmed by row count):**

  | Value | Count | Notes |
  |---|---|---|
  | `Exited` | 1003 | onboarding 2019-11-03 to 2026-08-15 |
  | `Staying` | 168 | onboarding 2021-12-05 to 2026-08-31 |
  | `Cancelled` | 31 | |
  | `On-Notice` | 7 | onboarding 2024-06-08 to 2026-07-23 — **the 7 beds central to `C.009`/`DQ.005`** |
  | `Booked` | 4 | onboarding 2026-08-01 to 2026-08-16 — inherently forward-looking |

- **Hierarchy:** Not hierarchical — a flat enum, but consuming metrics group it into logical
  buckets that **differ by metric** (this is itself the source of the occupancy conflict family,
  `semantic_layer.md` §7): "occupied" = `Staying` only in some views, `Staying`+`On-Notice` in
  others.
- **Slowly-changing / history implications:** A tenant's full lifecycle is the union of all their
  `tenant_allotments` rows across time — this table is genuinely history-preserving (unlike
  `tenants.staying_status`), since each move/re-lease creates a new row rather than overwriting.
- **Current vs. historical meaning:** The **current** state of one allotment is its own
  `staying_status` value. **Historical** occupancy (was this bed occupied on date X) requires
  interval logic over `onboarding_date`/`actual_exit_date`, as implemented in
  `get_bed_occupancy_timeline`/`get_occupancy_intelligence` — never inferred from `staying_status`
  alone, which reflects only the present.
- **Known data-quality issues:** 187–214 overlapping-allotment pairs on the same bed (`DQ.003`).
  `bed_status_history` (a table that could have independently corroborated this dimension) is
  empty (`DQ.029`).
- **Metrics that may safely use this dimension:** Every occupancy and tenant-lifecycle metric in
  `semantic_layer.md` §7–9.

---

## 8. Invoice

- **Definition:** A charge issued to a tenant.
- **Source:** `invoices` table (5214 live rows).
- **Key:** `invoices.id`; `invoice_number` (human-readable, not guaranteed unique — see duplicate
  issue below).
- **Hierarchy:** tenant/allotment → invoice → `invoice_line_items` (line-item detail, not
  separately profiled as its own dimension here since no metric in the registry uses it
  directly).
- **Valid values:** `invoice_type` (`regular`, `exit_charge`, `additional_deposit`, and others
  per `H.035`); `status` (`pending`, `paid`, `partial`, and others); `reference_type`
  (`onboarding`, `room_switch`, `exit_charge`, `exit_estimated_eb`, or NULL — a polymorphic
  discriminator, `M.011`).
- **Slowly-changing implications:** An invoice's `total_amount`/`amount_paid`/`balance` are
  application-maintained and **can drift from internal consistency** — 42.7% of live invoices
  show `amount_paid + balance ≠ total_amount` (`DQ.001`, CRITICAL). `amount_paid`/`balance` are
  **not** part of `trg_invoice_journal_post`'s repost trigger condition — confirmed from the
  full trigger body — meaning the ledger and these two columns can silently diverge without a
  repost.
- **Current vs. historical meaning:** `status` is current-state; `invoice_date`/`billing_month`
  are the fixed business dates.
- **Known data-quality issues:** 356 of 5214 (6.8%) are duplicate rows across 322 groups (same
  allotment + billing_month + invoice_type), with **no application-level deduplication
  mechanism** (`DQ.013`). `billing_month` is TEXT `'YYYY-MM'` (100% conformant, confirmed) — the
  **correct** format, unlike EB's tables (dimension 18).
- **Metrics that may safely use this dimension:** `M.INV.001`/`002`, `M.PROFIT.001` (Def B),
  `M.RISK.005`.

---

## 9. Receipt

- **Definition:** A payment received from a tenant.
- **Source:** `receipts` table (5858 live rows).
- **Key:** `receipts.id`; `receipt_number`.
- **Valid values:** `receipt_type` (`payment`, `booking`, `onboarding`, and others);
  `payment_mode`.
- **Slowly-changing implications:** Edited receipts (repeated `amount_paid`/`payment_date`/etc.
  changes) trigger a reverse-and-repost cycle on the ledger side (`trg_receipt_journal_post`,
  body fully exported) — `entry_count > 1` on the ledger is a strong signal of an edited receipt.
- **Current vs. historical meaning:** `payment_date` is the business date; `is_deleted` is the
  current-state soft-delete flag.
- **Known data-quality issues:** 11 of 23 flagged-duplicate receipt ids (per
  `receipts_dedup_audit`, a one-time 2026-04-22 detection pass) are still live and
  undeduplicated; the other 12 were **hard-deleted**, outside the system's own soft-delete
  convention, confirmed by direct cross-check (`DQ.014`). Source-vs-ledger residual of
  Rs.16,282.45 (0.02%) across 4 receipts, one of which has no ledger posting at all; the
  Rs.5,340,795.62 reported by `H.001` is a formula artifact of that view, not a residual
  (`DQ.006`/`C.014`). 200 of 6085 ledger entries reference a
  currently-soft-deleted receipt — confirmed to be **consistent with the documented reversal
  design**, not a defect (`DQ.010`).
- **Metrics that may safely use this dimension:** `M.COL.001`–`003`, `M.RISK.006`.

---

## 10. Payment (owner payment)

*(Distinguished from "Receipt," which is a tenant-side payment — see dimension 16 for the
owner-specific payment dimension.)*

---

## 11. Deposit

- **Definition:** Security deposit held on behalf of a tenant.
- **Source:** Ledger account `2100` "Tenant Deposits Held" (liability); `tenant_allotments.
  deposit_paid` (source-side); `deposit_settlements` (the settlement/refund event).
- **Key:** No dedicated deposit table — the balance is a ledger-account view (`v_advance_balances`
  /`F.010`), or a stored value on `tenant_allotments`.
- **Valid values:** Not enum-based — a monetary balance per tenant/allotment.
- **Slowly-changing implications:** A deposit's held balance changes on receipt, transfer
  (`guard_deposit_transfer_before_onboarding` blocks backdating a transfer before the
  allotment's `onboarding_date` — body fully exported), and settlement.
- **Known data-quality issues:** 32 allotments hold a deposit with no live tenant relationship
  and no settlement record at all (Rs.722,700.00 exposure, `DQ.011`, a figure computed for the
  first time in `metric_reconstruction.md`). See dimension 12 (Deposit settlement) for the
  settlement-side issues.
- **Metrics that may safely use this dimension:** `M.DEP.001`, `M.RISK.003`/`004`.

---

## 12. Deposit settlement

- **Definition:** The event that closes out a tenant's deposit (deductions applied, refund
  issued) at exit.
- **Source:** `deposit_settlements` table (307 live rows).
- **Key:** `deposit_settlements.id`; FK to `allotment_id`/`tenant_id`.
- **Valid values:** `status` — the **ledger-posting gate** is `IN ('completed','approved')`
  (confirmed from `trg_settlement_journal_post`'s full body); other statuses (e.g. `pending`) do
  not post.
- **Slowly-changing implications:** `validate_deposit_settlement` is a **write-time-only**
  constraint (blocks deductions on a non-exited allotment at INSERT/UPDATE) — it does **not**
  re-validate existing rows if the allotment's status changes retroactively, the suspected (not
  proven) mechanism behind 22 flagged anomaly rows across 3 types (`H.046`/`DQ.012`).
- **Known data-quality issues:** Source-vs-ledger drift of Rs.583,495.34 (10.3%), with a strong
  (23 of 43 rows exactly 2.0000×) suspected double-count mechanism in the diagnostic query itself
  (`DQ.008`/`C.016`) — the strongest mechanistic lead of the three source-vs-ledger conflicts in
  the package.
- **Metrics that may safely use this dimension:** `M.DEP.002`/`003`, `M.RISK.003`.

---

## 13. Expense category

- **Definition:** The classification of an expense for P&L reporting.
- **Source:** **Two structurally different, coexisting classification schemes** — see
  `semantic_layer.md` §10 for the full account-5150 conflict.
  1. `v_pnl_by_category`'s 9 hand-written `account_code LIKE` patterns.
  2. `v_expense_composition`'s COA parent-child hierarchy (`coa_accounts.parent_id`).
- **Key:** `coa_accounts.code` (leaf) → `coa_accounts.parent_id` (category, scheme 2 only).
- **Hierarchy:** `5000` (Operating Expenses, root) → `5100`/`5150`/`5200`/`5300`/`5400`/`5500`/
  `5600`/`5700`/`5800`/`5900` (mid-level) → sub-accounts (e.g. `5210`–`5290` under `5200`
  Maintenance & Repairs).
- **Valid values:** 57 total COA accounts (`H.016`); the EXPENSE-type subtree spans `5000`–`5900`.
- **Known data-quality issues, PROVEN:** Account `5150` (Electricity Payments) is excluded from
  all 9 of scheme 1's named buckets (captured only in a 10th, separate `electricity` column) —
  4.96% of total expenses, exact 57-month arithmetic proof (`DQ.015`). Scheme 2 instead groups
  `5150` under the shared "Operating Expenses" parent alongside owner rent (`5100`) — a
  **third**, different category assignment for the same account. **Do not invent a mapping that
  puts electricity under "utilities" or any other named bucket — no evidence supports it.**
- **Metrics that may safely use this dimension:** `M.EXP.002`.

---

## 14. Account / chart of accounts

- **Definition:** The ledger account dimension — the backbone of every financial metric.
- **Source:** `coa_accounts` table (57 rows).
- **Key:** `coa_accounts.id` (UUID); `code` (the human/business key, e.g. `1200`).
- **Hierarchy:** `account_type` (`ASSET`/`LIABILITY`/`INCOME`/`EXPENSE`) → `parent_id`
  (self-referencing) → leaf account.
- **Valid values:** `normal_balance` (`DEBIT` for ASSET/EXPENSE, `CREDIT` for LIABILITY/INCOME);
  `requires_party`/`requires_allotment`/`party_kind` flags (enforced at posting time by
  `enforce_subledger_completeness`, body fully exported).
- **Key accounts referenced throughout the semantic layer:** `1110`/`1120` cash & bank, `1200`
  AR–Tenants, `2100` Tenant Deposits Held, `2400` Booking Advances, `2200` Owner Rent Payable
  (declared but its actual usage was not independently traced in this pass — **Not determinable
  from exported evidence** whether `2200` is actively posted to), `4100`–`4500`/`4900` income
  sub-accounts, `5100`–`5900` expense sub-accounts.
- **Slowly-changing implications:** COA accounts are effectively static reference data in this
  export (no evidence of accounts being added/retired mid-history was examined).
- **Metrics that may safely use this dimension:** Every ledger-derived metric in
  `semantic_layer.md` §1, §10–16.

---

## 15. Owner

- **Definition:** A property owner receiving rent/revenue-share.
- **Source:** `owners` table; `owner_contracts` (35 rows, contract terms: `monthly_rent`,
  `revenue_share_percentage`, `security_deposit`, `lock_in_months`, `escalation_percentage`,
  `escalation_interval_months`).
- **Key:** `owners.id`; `owner_contracts.id` (FK to `owner_id`, `property_id`).
- **Slowly-changing implications:** `owner_contracts` carries escalation terms — **not
  independently traced in this pass** whether `owner_payments.escalated_amount` is verifiably
  computed from these contract terms (the relationship is plausible from column naming but **Not
  determinable from exported evidence** without a dedicated calculation function, which is not
  among the 25 exported bodies).
- **Metrics that may safely use this dimension:** `M.OWN.001`/`002` (at the owner_payments
  grain; not independently validated at the per-owner breakdown grain in this pass).

---

## 16. Owner payment

- **Definition:** A rent/revenue-share payment made (or accrued) to a property owner.
- **Source:** `owner_payments` table (345 rows).
- **Key:** `owner_payments.id`; FK to `owner_id`, `contract_id`, `apartment_id`.
- **Valid values:** `status IN ('paid','pending', ...)`.
- **Slowly-changing implications:** **The only source-vs-ledger reconciliation in the whole
  package with zero drift** — `escalated_amount`/`base_amount` post to the ledger with a
  PROVEN PERFECT match (`H.001`).
- **Current vs. historical meaning:** `bill_date` is the correct business/ledger-posting date
  (`normalize_owner_payment_journal_dates`, body fully exported, forces the JE's `entry_date` to
  `bill_date`). `paid_date`/`due_date` is a **different, third** date basis used only by
  `v_diag_owner_rent_missing_from_profit` — the two bases disagree at the monthly grain on 7 of
  54 months (`DQ.017`), though the all-time total is identical either way.
  **`created_at`/`posted_at` must NEVER be used as the business date** — all 345 rows were
  ledger-posted in a single ~82-minute batch on 2026-08-13, a migration event, not incremental
  live posting (`DQ.020`).
- **Known data-quality issues:** None on the amount itself (proven perfect); the date-basis
  ambiguity above is the only issue.
- **Metrics that may safely use this dimension:** `M.OWN.001`/`002`, `M.PROFIT.001` (as the
  mechanism behind the profit-definition conflict).

---

## 17. Maintenance

- **Definition:** A maintenance ticket and its resolution/cost lifecycle.
- **Source:** `maintenance_tickets` (1611 rows), `ticket_resolutions` (466 rows), `ticket_logs`
  (8239 rows, action audit trail).
- **Key:** `maintenance_tickets.id`; `ticket_resolutions.id` (FK `ticket_id`).
- **Hierarchy:** apartment/bed → ticket → resolution → linked expense(s).
- **Valid values:** `maintenance_tickets.status` (`assigned`, `in_progress`,
  `pending_tenant_approval`, `waiting_for_cost_approval`, `closed`/`resolved`/`completed`/
  `cancelled`/`rejected`, per `get_universal_metrics`'s own status-bucket logic).
- **Slowly-changing implications:** A ticket can have **more than one** resolution — 2 of 466
  resolutions belong to tickets with 2 resolutions each (`H.018`) — this is the **proven**
  mechanism behind `H.019`'s 1613-vs-1611 ticket-count discrepancy (a genuine finding made
  during `metric_reconstruction.md`: 1611 + 2 double-resolved tickets = 1613 exactly).
- **Current vs. historical meaning:** `created_at` **is** the business date here — confirmed as
  the correct choice because `maintenance_tickets` has no other business-open-date column
  (unlike every other domain, where `created_at` is a backfill artifact).
- **Known data-quality issues:** No `is_deleted` column exists on `maintenance_tickets` — no
  soft-delete concept for this domain.
- **Metrics that may safely use this dimension:** `M.MAINT.001`/`002`.

---

## 18. Maintenance category (issue type)

- **Definition:** The classification of a maintenance ticket/expense by issue type.
- **Source:** `issue_types` table (51 rows); linked to both `maintenance_tickets` (via
  `issue_type_id` on the ticket) and `expenses` (via a **separate, independent**
  `issue_type_id` FK on the expense row itself).
- **Key:** `issue_types.id`.
- **Known data-quality issues:** **Two independent linkage paths to cost exist** — cost-by-
  ticket-resolution (`v_maintenance_metrics`) vs. cost-by-expense's-own-issue-type
  (`v_maintenance_by_issue_type`) — structurally capable of disagreeing whenever an expense's own
  `issue_type_id` differs from its linked ticket's issue type, though **proven, for this
  dataset, to produce an identical total** (`C.023`, an update to the original "can disagree"
  framing).
- **Metrics that may safely use this dimension:** `M.MAINT.002`.

---

## 19. Electricity / EB

- **Definition:** Electricity meter reading, billing, and tenant-allocation dimension.
- **Source:** `electricity_readings` (1411 rows), `eb_payments` (70 rows), `eb_rates` (2 rows),
  `eb_monitoring_readings` (35 rows), `eb_tenant_shares` (801 rows).
- **Key:** No single unifying key across these 5 tables — each links back to `apartment_id`/
  `property_id`/`invoice_id` independently.
- **Known data-quality issues, PROVEN:** `billing_month` on `electricity_readings` and
  `eb_tenant_shares` uses `'Mon-YY'` text (0% `'YYYY-MM'` conformance, full-population check);
  every other billing-period column in the schema uses `'YYYY-MM'` (100% conformance,
  `invoices`/`expenses`/`owner_payments`, full-population check) — see dimension 20 below.
  `eb_monitoring_readings` is a single-day snapshot (2026-08-18), not a time series
  (`DQ.021`). `eb_payments` has only 2 months of coverage — the narrowest of any financial
  domain.
- **Metrics that may safely use this dimension:** `M.EB.001`/`002`.

---

## 20. Billing period

- **Definition:** The month a charge/expense/payment belongs to, distinct from the transaction's
  posting date.
- **Source:** `billing_month` (TEXT) columns on `invoices`, `expenses`, `electricity_readings`,
  `eb_tenant_shares`; `payment_month` (TEXT) on `owner_payments`.
- **Valid values, PROVEN by full-population check in this pass:**
  - `invoices.billing_month`, `expenses.billing_month`, `owner_payments.payment_month`: **100%**
    `'YYYY-MM'` format (e.g. `'2026-04'`), 0 exceptions across the full populations.
  - `electricity_readings.billing_month`, `eb_tenant_shares.billing_month`: **0%** `'YYYY-MM'`
    format — **100%** use `'Mon-YY'` instead (e.g. `'Apr-25'`), 0 exceptions.
- **Known data-quality issue (`DQ.028`, HIGH severity — proven, not suspected):** This is a
  genuine schema inconsistency, not a display formatting choice — a direct string join or the
  `(billing_month || '-01')::date` cast pattern used elsewhere in the codebase (e.g. in
  `get_universal_metrics`) **will fail or silently misparse** for the two EB tables. **Any
  semantic-layer join between EB billing_month and invoices/expenses billing_month requires an
  explicit format-conversion step first** (`'Mon-YY'` → `'YYYY-MM'` or vice versa).
- **Metrics that may safely use this dimension:** `M.INV.001`, `M.EXP.001`/`002`, `M.OWN.001`
  (all `'YYYY-MM'`, safe to join directly); `M.EB.001`/`002` (`'Mon-YY'`, requires conversion
  before joining to the others).

---

## 21. Journal entry

- **Definition:** One ledger posting event — the header row for a set of debit/credit lines.
- **Source:** `journal_entries` table (14,236 rows).
- **Key:** `journal_entries.id`.
- **Valid values:** `is_reversal_of` (NULL for a forward entry, or the id of the entry it
  reverses — never both a forward-entry attribute and a reversal-entry attribute
  simultaneously). `source_table`/`source_id` (the polymorphic link back to the originating
  business event — see dimension 22).
- **Hierarchy:** journal entry → (1 or more) `journal_lines` (the actual debit/credit postings).
- **Slowly-changing implications:** A journal entry, once posted, is **never edited** — a
  correction always takes the form of a **new** reversal entry plus a **new** forward entry
  (proven from all 5 posting trigger bodies, `business_logic.md` §1.3–1.4). `enforce_period_lock`
  (body fully exported) would block forward postings into a closed period while still allowing
  reversals — **structurally a no-op in this dataset**, since `accounting_periods` (the table
  that would hold "closed" period records) is empty (`DQ.029`), so every period reads as
  effectively open.
- **Current vs. historical meaning:** `entry_date` is the ledger-effective business date;
  `posted_at` is when the row was physically written (can differ substantially — e.g. the
  owner_payments single-batch posting on 2026-08-13 for entries dated as far back as 2022-11,
  `DQ.020`).
- **Known data-quality issues:** 347 of 14,236 entries (2.44%) are reversals (`H.005`). Two
  reversal-related conventions coexist across consuming views (excluded vs. included, `C.002`,
  proven immaterial to balances) plus a third, sign-inversion-netting convention used only by
  `v_je_amount_reconciliation` (`business_logic.md` §1.3 definition C).
- **Metrics that may safely use this dimension:** Every ledger-derived metric.

---

## 22. Source transaction (polymorphic reference)

- **Definition:** The business-event row a journal entry (or other record) was generated from —
  a polymorphic relationship (discriminator column + reference-id column, no single-table FK is
  possible by construction).
- **Source:** 5 declared polymorphic relationships (`M.011`):

  | Table | Discriminator | Reference column |
  |---|---|---|
  | `journal_entries` | `source_table` | `source_id` |
  | `financial_audit_log` | `source_table` | `source_id` |
  | `invoices` | `reference_type` | `reference_id` |
  | `tenant_adjustments` | `reference_type` | `reference_id` |
  | `tenant_transactions` | `reference_table` | `reference_id` |

- **Valid values (`journal_entries.source_table`):** `invoices`, `receipts`, `expenses`,
  `deposit_settlements`, `owner_payments`, `tenant_adjustments`, `assets`, `asset_payments`,
  `eb_payments`, and `manual` (hand-posted entries with no source row at all).
- **Known data-quality issues, PROVEN vs. UNVERIFIED:** Orphan/completeness checks exist for
  **only 1 of the 5** polymorphic relationships, and even then only partially — `journal_entries.
  source_id` was checked (0 orphans, `H.021`/`H.025`) against `invoices`/`receipts`/`expenses`/
  `deposit_settlements` specifically, **not** against `owner_payments`/`tenant_adjustments`/
  `assets`/`asset_payments`/`eb_payments`. `invoices.reference_id`, `tenant_adjustments.
  reference_id`, `tenant_transactions.reference_id`, and `financial_audit_log.source_id` have
  **no exported orphan check at all** (`DQ.026`). **Do not assume referential completeness for
  any of these beyond what was explicitly checked.**
- **Metrics that may safely use this dimension:** Any ledger-derived metric relying on
  `source_table='X'` filters (the majority of Financial metrics) — safely, for the 4 checked
  source tables; with an explicit "unverified" caveat for the rest.

---

## Dimension coverage summary

21 distinct dimensions specified (item 10, "Payment," is folded into "Receipt" and "Owner
payment" since no separate generic payment table exists — noted explicitly rather than silently
omitted). Every dimension traces to a specific table/column already catalogued in
`data_inventory.md`; no dimension, key, or hierarchy was invented for this document. Three
dimensions (Property, Organization, Owner-at-breakdown-grain) are currently **degenerate** in
this single-org/single-property dataset — the architecture supports them, but they provide no
discriminating power against the current export. `created_at` is used as the business date for
exactly one dimension (Maintenance) — every other use of `created_at` in the exported schema is
a load/backfill artifact, not a business event.
