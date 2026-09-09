# B. business_logic.md

Evidence-backed business definitions reconstructed from view SQL (`M.016`), the 25 exported
function bodies (`FN.000` + 25 individual `FN.<name>` files), trigger wiring (`FN.TRG`),
base-table columns, and diagnostics. Every definition below is quoted or paraphrased directly
from a specific evidence file — nothing is inferred from a routine's name or signature alone.

**How to read this document.** Where the evidence contains two or more definitions of the same
concept, all of them are stated here, side by side, with no preference. The formal conflict
record — numerical differences, likely cause, recommended handling — is in
[`conflicts.md`](conflicts.md) (deliverable C), not here. Manifest keys (`F.xxx`, `T.xxx`,
`H.xxx`, `FN.xxx`, `M.xxx`) refer to `evidence/file_manifest.csv` and are reproducible with
`scripts/evidence_loader.py`.

**A structural limitation applies to almost every section below and is stated once here.** The
25 exported function bodies are the *trigger orchestration layer* — they decide **when** to
post, reverse, or repost a journal entry, and on what row-level condition. The functions that
decide **what accounts and amounts** actually go into a posting — `build_receipt_lines`,
`build_invoice_lines`, `build_expense_lines`, `build_settlement_lines`, `build_adjustment_lines`,
`post_journal_entry`, `reverse_journal_entry`, `coa_id`, `find_journal_entry_for_source`,
`next_receipt_number`, `trg_owner_payment_journal_post`, `trg_eb_payment_journal_post`,
`trg_asset_journal_post`, `trg_asset_payment_journal_post`, `trg_expense_alloc_journal_repost`
— are **not among the 25 exported bodies** (confirmed against `M.019`/`FN.999`: all of these
names appear in the 458 signature-only routines, not in `FN.000`). Wherever the exact account
code / amount composition of a posting cannot be read from an exported body, this document says
so explicitly and states **"Not determinable from exported evidence."** rather than guessing
from the function's name. Where `v_account_balances` or another view lets the composition be
**verified after the fact** (which account, how much, for which source row), that is used and
cited instead.

---

## 1. Accounting / ledger

### 1.1 Ledger tables and sign convention

**Source tables:** `journal_entries` (14 236 rows, `T.journal_entries`), `journal_lines`
(33 894 rows, `T.journal_lines`), `coa_accounts` (57 rows, `T.coa_accounts`).

**Evidence:** `journal_entries` columns — `id, organization_id, entry_date, period,
description, source_table, source_id, is_reversal_of, posted_at, posted_by, metadata`.
`journal_lines` columns — `id, journal_entry_id, organization_id, account_id, debit, credit,
party_kind, party_id, allotment_id, property_id, apartment_id, bed_id, memo, line_no` (plus the
6 columns the export denormalised in from `journal_entries` — see `data_inventory.md` §A.1).
`coa_accounts` — `id, organization_id, code, name, account_type, normal_balance, parent_id,
is_active, requires_party, requires_allotment, party_kind, description`.

**Sign convention (`v_account_balances`, `M.016`):**

```sql
signed_amount =
  CASE a.normal_balance
    WHEN 'DEBIT'  THEN jl.debit  - jl.credit
    WHEN 'CREDIT' THEN jl.credit - jl.debit
  END
```

i.e. every account's balance is expressed in its own natural direction. `coa_accounts.
normal_balance` is `DEBIT` for `ASSET`/`EXPENSE` account types and `CREDIT` for
`LIABILITY`/`INCOME` (`H.016`, `T.coa_accounts`).

**Chart of accounts (57 accounts, `T.coa_accounts` / `H.016`).** Relevant codes used throughout
this document: `1110`/`1120` cash & bank, `1200` Accounts Receivable – Tenants, `2100` Tenant
Deposits Held, `2400` Booking Advances, `2200` Owner Rent Payable, `4100`–`4500` income
sub-accounts, `5000`–`5900` expense sub-accounts (full tree in `data_inventory.md` and quoted
per-account below where relevant).

### 1.2 Journal posting mechanism — INSERT

Every source table with a posting trigger (`invoices`, `receipts`, `expenses`,
`deposit_settlements`, `tenant_adjustments`, plus `owner_payments`, `assets`, `asset_payments`,
`eb_payments`, `expense_bed_allocations` per `FN.TRG`) calls a `build_<x>_lines()` helper to
produce a `jsonb` array of `{account_id, debit|credit, party_kind, party_id, allotment_id,
property_id, apartment_id, bed_id, memo}` objects, then `post_journal_entry(org, date,
description, source_table, source_id, lines, metadata)` writes one `journal_entries` header +
N `journal_lines` rows. Evidence: `FN.trg_invoice_journal_post`, `FN.trg_receipt_journal_post`,
`FN.trg_expense_journal_post`, `FN.trg_adjustment_journal_post`, `FN.trg_settlement_journal_post`
(all five bodies fully exported and quoted per-domain below). **The exact account/amount
composition inside `build_*_lines()` is not exported** — see the structural limitation above.
What *is* exported and verifiable: `enforce_journal_balanced` (`FN.enforce_journal_balanced`)
runs `AFTER INSERT,UPDATE` on `journal_entries` and raises an exception if
`ABS(SUM(debit)-SUM(credit)) > 0.005` for that entry (skipped only while a header-only insert
has not yet written its lines in the same transaction) — **every posted entry is debit=credit
balanced by a hard DB constraint**, not merely by convention.

### 1.3 Reversal logic

**Mechanism.** A reversal is a **second, separate `journal_entries` row** with
`is_reversal_of = <original.id>` and its own `journal_lines` (evidence: `journal_entries` has
an `is_reversal_of` FK to itself, `ON DELETE RESTRICT`, `M.009`). The original row is never
edited or deleted by a reversal. `reverse_journal_entry(p_je_id, p_reason, p_date)` is called by
every trigger's soft-delete and material-edit paths (`FN.trg_receipt_journal_post`,
`FN.trg_invoice_journal_post`, `FN.trg_expense_journal_post`, `FN.trg_adjustment_journal_post`,
`FN.trg_settlement_journal_post`) — **its own body is not exported**, so the exact lines it
writes (presumably debit/credit-swapped mirror lines) are not verifiable from source, but its
effect is directly observable in `journal_entries.is_reversal_of` and in `H.005`.

**Reversal volume (`H.005`, `v_je_reversal_summary`... wait — sourced from `journal_entries`
directly):** 14 236 total entries, **347 reversal entries (2.44%)**, spanning 2019-11-03 to
2026-09-20.

**Two competing "reversal treatment" conventions coexist in the exported views — preserved
here, not resolved (see `conflicts.md` for the numeric consequence):**

1. **Reversals EXCLUDED — both legs dropped.** `v_account_balances` (`M.016`):
   ```sql
   WHERE je.is_reversal_of IS NULL
     AND NOT EXISTS (SELECT 1 FROM journal_entries r WHERE r.is_reversal_of = je.id)
   ```
   This drops the original entry if it has since been reversed, **and** drops the reversal entry
   itself. Every view built on `v_account_balances` inherits this: `v_pnl`, `v_pnl_by_category`,
   `v_revenue_by_period`, `v_expenses_by_period`, `v_trial_balance`, `v_outstanding_receivables`,
   `v_advance_balances`, `v_org_cash_balance`, `v_expense_composition`, `v_bed_expense_breakdown`,
   `v_property_expense_share`.

2. **Reversals INCLUDED — both legs summed, netting to the same result arithmetically.**
   `v_tenant_current_dues`, `v_tenant_aging`, `v_tenant_ledger`, `v_trial_balance_detailed`,
   `v_account_rollup`, `v_invoice_settlement_status` all query `journal_lines`/`journal_entries`
   directly with **no filter on `is_reversal_of`** — the forward entry and its reversal both
   participate in the `SUM(debit)`/`SUM(credit)`, and because a reversal is (presumably) the
   exact debit/credit mirror of the original, the net contribution of a reversed pair is zero
   either way, arithmetically equivalent to definition 1's exclusion — **for a total or a
   balance**. It is **not** equivalent for a *row count* (`v_tenant_current_dues.charge_count`
   counts every `1200`-debit line including ones later reversed) or for anything windowed by
   `posted_at` (a reversal's `posted_at` can fall in a different period than the original).

3. **A third convention, sign-inverted netting**, appears only in `v_je_amount_reconciliation`
   (`H.001`, `v_je_amount_reconciliation`, see below):
   ```sql
   SUM(CASE WHEN je.is_reversal_of IS NULL THEN jl.debit ELSE -jl.debit END)
   ```
   Arithmetically equivalent to (2) for a total, different code path.

**`enforce_period_lock`** (`FN.enforce_period_lock`, `BEFORE INSERT,DELETE,UPDATE` on
`journal_entries`) explicitly **carves out an exception for reversals**: `IF v_status='closed'
AND NEW.is_reversal_of IS NOT NULL THEN RETURN NEW` — reversals may post into a closed period
even when forward entries may not. **In this dataset the check is structurally a no-op**:
`accounting_periods` is empty (0 rows, confirmed `M.006`), so `v_status` is always `NULL` and the
function always takes the `RETURN COALESCE(NEW,OLD)` early-exit — no period has ever actually
been locked or closed in the exported data.

### 1.4 Soft-delete vs hard-delete — two structurally different outcomes

**Soft-delete (`is_deleted = true` via `UPDATE`).** The row-level trigger's `UPDATE` branch
detects `NEW.is_deleted AND NOT OLD.is_deleted` and calls `reverse_journal_entry(...)`. The
original `journal_entries`/`journal_lines` rows **survive**, unchanged; a new reversal entry is
added. Confirmed in `FN.trg_receipt_journal_post`, `FN.trg_invoice_journal_post`,
`FN.trg_adjustment_journal_post`. `expenses` has **no `is_deleted` column at all** (confirmed
against its exported columns) — `FN.trg_expense_journal_post` has no soft-delete branch, only
hard `DELETE`. `deposit_settlements` uses a different soft/live gate: it posts only when
`status IN ('completed','approved') AND NOT is_deleted`; any transition away from that
(`v_should_post` false) triggers a reversal, whether the cause was `is_deleted` or a `status`
change (`FN.trg_settlement_journal_post`).

**Hard-delete (`DELETE`).** A **separate, generic trigger**, `delete_journal_entries_on_source_delete(TG_ARGV[0])`
(`FN.delete_journal_entries_on_source_delete`), is wired `AFTER DELETE` on 7 tables —
`asset_payments`, `assets`, `deposit_settlements`, `eb_payments`, `expenses`, `owner_payments`,
`tenant_adjustments` (`FN.TRG`) — and **physically `DELETE`s** the matching `journal_entries`
and `journal_lines` rows (not a reversal). `invoices` has its own dedicated equivalent,
`delete_invoice_journal_entries_on_invoice_delete` (`FN.delete_invoice_journal_entries_on_invoice_delete`).
`receipts` has **both**: `trg_cascade_je_receipts → delete_journal_entries_on_source_delete`
*and* `trg_receipt_journal_post`'s own `DELETE` branch, which calls `reverse_journal_entry` on
the same rows. Postgres fires same-timing/same-event triggers on one table in **alphabetical
order by trigger name**; `trg_cascade_je_receipts` < `trg_receipt_journal` alphabetically, so the
cascade-delete fires first and removes the `journal_entries` rows before the reversal branch's
own `SELECT` can find them — **on a hard-deleted receipt, the net effect is physical deletion,
not a reversal entry**, even though the trigger body's own logic looks like it should reverse.
This is read directly from `FN.TRG`'s alphabetical listing and the two function bodies; it has
not been verified by executing SQL, since no live database is available.

`tenant_adjustments`' own trigger body documents this explicitly in a comment: *"trg_cascade_je_tenant_adjustments
removes journal rows; do not reverse here"* (`FN.trg_adjustment_journal_post`, `DELETE` branch).

**JE rows surviving source deletion — the actual mechanism (item E in the brief).**
`log_journal_entry_post` (`FN.log_journal_entry_post`, `AFTER INSERT` on `journal_entries`)
writes one immutable row per posted/reversed entry into `financial_audit_log` (23 132 rows,
`T.financial_audit_log`) with `total_debit`/`total_credit`/`source_table`/`source_id` frozen at
post time. The FK is `financial_audit_log.journal_entry_id → journal_entries.id **ON DELETE SET
NULL**` (`M.009`). So when a `journal_entries` row is later hard-deleted by one of the cascade
triggers above, its `financial_audit_log` row **is not deleted — its `journal_entry_id` becomes
NULL**, and the audit row (with the original amounts and source reference) survives permanently.
**This is the exported evidence's answer to "JE entries surviving source deletion": it is the
audit log, not `journal_entries` itself, that outlives a hard delete** — `journal_entries` rows
are in fact designed to be fully removable. Whether any `journal_entries` row currently points
at a source row that no longer exists is a live-data question answered by `H.051`
(`je_missing_deleted_sources`), not by this mechanism section; see `conflicts.md` / `data_quality_report.md`.

### 1.5 Subledger completeness and balance guarantees

`enforce_subledger_completeness` (`FN.enforce_subledger_completeness`, `BEFORE INSERT,UPDATE` on
`journal_lines`) reads `coa_accounts.requires_party` / `requires_allotment` for the line's
account and raises if a party- or allotment-required account is posted without
`party_kind`/`party_id` or `allotment_id`. `guard_deposit_transfer_before_onboarding`
(`FN.guard_deposit_transfer_before_onboarding`, `BEFORE INSERT` on `journal_lines`) specifically
blocks a `manual`-source, description-`ILIKE '%deposit transfer%'`, account-`2100`-credit line
from being dated before the target allotment's `onboarding_date`.

### 1.6 `v_account_balances` — the join every ledger-derived view sits on

```sql
SELECT je.organization_id, je.entry_date, je.period, je.id AS journal_entry_id,
       je.source_table, je.source_id, je.is_reversal_of,
       a.id AS account_id, a.code, a.name, a.account_type, a.normal_balance,
       parent.code AS parent_code, parent.name AS parent_name,
       jl.party_kind, jl.party_id, jl.allotment_id, jl.property_id, jl.apartment_id, jl.bed_id,
       jl.debit, jl.credit, <signed_amount as in §1.1>
FROM journal_lines jl
  JOIN journal_entries je ON je.id = jl.journal_entry_id
  JOIN coa_accounts a     ON a.id = jl.account_id
  LEFT JOIN coa_accounts parent ON parent.id = a.parent_id
WHERE je.is_reversal_of IS NULL
  AND NOT EXISTS (SELECT 1 FROM journal_entries r WHERE r.is_reversal_of = je.id)
```
(`M.016`, exported as `F.021`, 32 040 rows.) **Date field:** `entry_date` (the ledger-effective
date, set by the trigger, normally `COALESCE(source_date, current_date)` — see §5 for the
owner-payment-specific override). **Grain:** one row per `journal_lines` row (i.e. per debit or
credit leg), carrying `organization_id`/`property_id`/`apartment_id`/`bed_id` where the posting
line supplied them. **Reversal treatment:** excluded (§1.3, definition 1). **Soft-delete
treatment:** inherited — a soft-deleted source's reversal entry is *also* excluded by this same
`is_reversal_of` filter, so once a source is soft-deleted, neither its original nor its reversal
appears here; the net contribution is correctly zero.

### 1.7 Trial balance — two exported variants (see `conflicts.md`)

- **`v_trial_balance`** (`F.012`, 24 rows) and **`v_trial_balance_detailed`** (`F.013`, 57
  rows) — the first is `v_account_balances` (reversals excluded) grouped by account; the second
  is a `WITH RECURSIVE` account-tree walk summing **raw `journal_lines`** (reversals included,
  §1.3 definition 2) per account, `LEFT JOIN`ed so zero-activity accounts still appear (which is
  why it has 57 rows — one per `coa_accounts` row — versus `v_trial_balance`'s 24, which only
  lists accounts with `v_account_balances` activity).
- **`v_account_rollup`** (`F.014`, 57 rows) — a `WITH RECURSIVE` descendant walk that sums every
  **raw** `journal_lines` row under an account and all its children, again reversals-included.
- `H.007` (`trial_balance_reversal_effect`) is the row-level comparison of the excl-vs-incl
  convention across all 57 accounts; raw values are preserved there, not re-derived here.

---

## 2. Revenue

**No single `revenue` table exists.** Three distinct, evidence-backed revenue definitions:

### 2.1 Ledger-derived revenue — `v_pnl`, `v_pnl_by_category`, `v_revenue_by_period`

```sql
-- v_pnl (F.001, 57 rows)
SELECT organization_id, property_id,
       date_trunc('month', entry_date)::date AS month,
       SUM(signed_amount) FILTER (WHERE account_type='INCOME')  AS revenue,
       SUM(signed_amount) FILTER (WHERE account_type='EXPENSE') AS expenses,
       revenue - expenses AS net_profit
FROM v_account_balances
WHERE account_type IN ('INCOME','EXPENSE')
GROUP BY organization_id, property_id, month
```
**Source tables (via `v_account_balances`):** `journal_lines` × `journal_entries` ×
`coa_accounts`. **Date field:** `journal_entries.entry_date`, truncated to month. **Filter:**
`account_type='INCOME'`. **Reversal treatment:** excluded (§1.3-1). **Soft-delete treatment:**
excluded transitively — a soft-deleted invoice/receipt/adjustment has no live, un-reversed
journal line. **Grain:** `organization_id, property_id, month`. **Account universe:** all
`4xxx` INCOME accounts (`4100` rental, `4200` electricity, `4250` guest stay, `4300`
onboarding, `4400` late fees, `4500` exit charges — from `v_pnl_by_category`'s explicit
per-account breakdown, `M.016`). **Evidence:** `M.016`, exported `F.001`/`F.002`/`F.003`.

`v_revenue_by_period` (`F.003`, 224 rows) is the same source at `account_code` grain instead of
aggregated — `GROUP BY organization_id, property_id, month, account_code, account_name`.

### 2.2 Invoice-based revenue — `get_universal_metrics` (v1)

```sql
i_period AS (SELECT * FROM invoices
             WHERE organization_id=p_org AND COALESCE(is_deleted,false)=false
               AND COALESCE((billing_month||'-01')::date, invoice_date, created_at::date)
                   BETWEEN v_start AND v_end)
...
'totalRentalRevenue'   , SUM(rent_amount)         FROM i_period
'totalEbCharged'       , SUM(electricity_amount)  FROM i_period
'totalOnboardingCharges', SUM(total_amount) FROM i_period WHERE invoice_type='onboarding'
'totalExitCharges'     , SUM(total_amount) FROM i_period WHERE invoice_type='exit_charge'
'totalOtherCharges'    , SUM(other_charges)       FROM i_period
'totalInvoiced'        , SUM(total_amount)        FROM i_period
```
(`FN.get_universal_metrics`, full body quoted.) **Source table:** `invoices` directly (not the
ledger). **Date field:** `COALESCE(billing_month::date, invoice_date, created_at::date)` — a
3-way fallback, evaluated **per invoice**, not a single column. **Filter:**
`organization_id = p_organization_id AND is_deleted=false`. **Reversal treatment: not
applicable** — this path never touches `journal_entries`; an invoice's ledger reversal has no
effect on this number, only editing/soft-deleting the invoice row itself does. **Soft-delete
treatment:** excluded via `is_deleted=false`. **Grain:** whole-organization totals for one
period window (`current_month` / `last_month` / `current_fy` / `last_fy`, computed from
`CURRENT_DATE` — **snapshot-dependent**, see §1 caveat in the integrity report). **Period
default:** `current_fy` (Indian FY, April–March).

### 2.3 Ledger-derived revenue, period-summed — `get_universal_metrics_v2`

`v2` does **not** re-derive revenue from `invoices`; it sums `v_pnl_by_category.revenue` (and
its per-account-type columns) over the requested `[v_from, v_to]` window
(`FN.get_universal_metrics_v2`, lines computing `v_revenue`/`v_rental_income`/etc. from a `SELECT
... FROM v_pnl_by_category WHERE month BETWEEN ...`). So v2's revenue is definition 2.1
(ledger-derived), re-aggregated over an arbitrary date range rather than v1's four fixed presets,
and accepts explicit `p_from`/`p_to` overrides. Both v1 and v2 evaluate the period boundary using
`current_date` unless `p_from`/`p_to` are supplied.

### 2.4 `get_universal_metrics_series` — monthly ledger revenue, with a suspected bug

```sql
SUM(signed_amount) FILTER (WHERE account_code LIKE '4%') AS revenue
FROM v_account_balances WHERE organization_id = p_organization_id GROUP BY month
```
Equivalent to 2.1's total (all `4xxx` INCOME accounts). **However**, the same query's
`collections` column is `SUM(signed_amount) FILTER (WHERE account_code = '1000' AND
source_table='receipts')`. `coa_accounts` (`T.coa_accounts`/`H.016`) shows **`1000` is the
"Assets" header/rollup account** — the parent of `1100`→`1110`/`1120` — not a leaf posting
account. Real cash/bank postings use `1110`/`1120` directly, confirmed by two other pieces of
evidence in this same codebase: `v_je_amount_reconciliation`'s receipts leg filters
`a.code LIKE '11%'`, and `get_universal_metrics_v2`'s own `v_collections` filters
`ca.code IN ('1110','1120')`. **Reading the function body alone, `get_universal_metrics_series.
collections` is very likely to return zero (or near-zero) for every month**, because no receipt
posting is expected to hit account `1000` directly. This is an observation from the exported
source code, not a result of executing it — no live database is available to confirm the
runtime output. Flagged for `data_quality_report.md`.

---

## 3. Collections

**Definition A — receipts, application-level (`get_universal_metrics` v1).**
```sql
r_period AS (SELECT * FROM receipts WHERE organization_id=p_org AND is_deleted=false
             AND payment_date BETWEEN v_start AND v_end)
'totalCollections'              , SUM(amount_paid) FROM r_period
'depositCollections'            , SUM(amount_paid) FROM r_period WHERE receipt_type='booking'
'totalCollectionsWithoutDeposit', totalCollections - depositCollections
```
**Source:** `receipts` (5858 rows, `T.receipts`). **Date field:** `payment_date`. **Filter:**
`organization_id`, `is_deleted=false`. **Grain:** org-wide, period window. **Reversal/soft-delete:**
n/a to ledger; only the receipt row's own `is_deleted` matters.

**Definition B — ledger-derived cash inflow (`get_universal_metrics_v2`).**
```sql
SUM(jl.debit) FROM journal_lines jl JOIN journal_entries je ... JOIN coa_accounts ca
WHERE je.source_table='receipts' AND ca.code IN ('1110','1120')
  AND je.entry_date BETWEEN v_from AND v_to AND jl.debit > 0
  AND je.is_reversal_of IS NULL
  AND NOT EXISTS (SELECT 1 FROM journal_entries r WHERE r.is_reversal_of = je.id)
```
Deposit collections (booking receipts) computed the same way but on account `2100` credit lines.
**Source:** `journal_lines`/`journal_entries` filtered to `source_table='receipts'` and cash/bank
accounts. **Date field:** `journal_entries.entry_date`. **Reversal treatment:** excluded
(matches §1.3-1 exactly, written out explicitly rather than via `v_account_balances`).
**Grain:** org-wide, arbitrary `[v_from,v_to]` window.

**Definition C — `tenant_transactions` legacy ledger.** `H.026`
(`tenant_transactions_taxonomy`) shows a `PAYMENT`/`CREDIT`/`PAYMENT` bucket sourced from
`reference_table='receipts'`: 7188 rows, `sum_amount` ₹104 745 183, spanning
`0206-03-27`(sic, corrupt year, see integrity report §9) to `2026-05-05`. This is a **separate,
now-frozen system** (`tenant_transactions`, 16 451 rows total, `created_at` all within
2026-04-17→28 — a one-time backfill/migration snapshot, not a live feed; `T.tenant_transactions`).
It is not wired to any trigger in `FN.TRG` and has no relationship declared to `journal_entries`
beyond sharing `reference_table='receipts'` values. **Not determinable from exported evidence**
whether this system is still authoritative for any live metric or is purely historical.

**Journal posting mechanism for receipts** (`FN.trg_receipt_journal_post`, full body quoted in
§1.4): `INSERT`/repost calls `build_receipt_lines(NEW.id)` (**body not exported**) then
`post_journal_entry`. A **second, separate posting** happens when `receipt_type='booking' AND
tenant_allotment_id IS NOT NULL`: a hand-built two-line entry debiting account `1200` (AR –
tenant) and crediting `4300` (onboarding income) for `amount_paid`, labelled "Onboarding Charges
Received" — this specific posting **is** fully readable from the trigger body (unlike the
generic `build_receipt_lines` path). **Receipt numbering:** `ensure_booking_receipt_number`
(`FN.ensure_booking_receipt_number`, `BEFORE INSERT` on `receipts`) auto-assigns a receipt number
only for `receipt_type='booking'` rows with a blank `receipt_number`, calling
`next_receipt_number(org, property_id, payment_date)` (**body not exported** — FY/sequence logic
not verifiable from source; `receipt_number_counters`, 8 rows, `T.receipt_number_counters`,
holds `organization_id, property_id, fy, month, last_seq` and is presumably what that function
increments, but the increment logic itself is not exported).

---

## 4. AR / tenant dues

**Three named views compute a tenant balance; they agree on total AR but differ in
population, reversal handling, and scope.** All are preserved; `conflicts.md` carries the
numeric comparison.

### 4.1 `v_outstanding_receivables` (`F.006`, 626 rows) — reversals EXCLUDED
```sql
SELECT organization_id, party_id AS tenant_id, allotment_id,
       SUM(signed_amount) AS outstanding,
       MAX(entry_date) FILTER (WHERE debit>0)  AS last_charge_date,
       MAX(entry_date) FILTER (WHERE credit>0) AS last_payment_date
FROM v_account_balances
WHERE account_code = '1200' AND party_kind = 'tenant'
GROUP BY organization_id, party_id, allotment_id
```
**Source:** `v_account_balances` (⇒ reversals excluded, soft-deletes excluded). **Filter:**
account `1200` (AR–Tenants) only, `party_kind='tenant'`. **Grain:** `tenant_id, allotment_id`.
Carries only AR — no deposit or advance figures.

### 4.2 `v_tenant_current_dues` (`F.007`, 645 rows) — reversals INCLUDED
```sql
SELECT jl.organization_id, jl.party_id AS tenant_id, jl.allotment_id,
       SUM(CASE WHEN a.code='1200' THEN jl.debit-jl.credit ELSE 0 END) AS ar_balance,
       SUM(CASE WHEN a.code='2100' THEN jl.credit-jl.debit ELSE 0 END) AS deposit_held,
       SUM(CASE WHEN a.code='2400' THEN jl.credit-jl.debit ELSE 0 END) AS booking_advance,
       ar_balance AS net_dues,
       MAX(je.entry_date) FILTER (WHERE a.code='1200' AND jl.credit>0) AS last_payment_date,
       MAX(je.entry_date) FILTER (WHERE a.code='1200' AND jl.debit>0)  AS last_charge_date,
       COUNT(*) FILTER (WHERE a.code='1200' AND jl.debit>0)  AS charge_count,
       COUNT(*) FILTER (WHERE a.code='1200' AND jl.credit>0) AS payment_count
FROM journal_lines jl JOIN journal_entries je ON je.id=jl.journal_entry_id
  JOIN coa_accounts a ON a.id=jl.account_id
WHERE jl.party_kind='tenant' AND a.code IN ('1200','2100','2400')
GROUP BY jl.organization_id, jl.party_id, jl.allotment_id
```
**Source:** raw `journal_lines`/`journal_entries`/`coa_accounts` — **no `is_reversal_of`
filter at all**. **Filter:** `party_kind='tenant'`, accounts `1200`/`2100`/`2400`. **Grain:**
`tenant_id, allotment_id`. Carries AR *and* deposit-held *and* booking-advance in one row, plus
`charge_count`/`payment_count` (which **do** double-count a reversed-and-reposted charge, since
both the original and the correction are counted — unlike the netted dollar totals).

**`H.006` (`ar_definition_conflict`) confirms empirically:** total AR is **identical** between
the two (₹83 297.85), but `v_tenant_current_dues` additionally reports `deposit_held` =
₹4 221 150.00 and `booking_advance` = ₹0.00, which `v_outstanding_receivables` does not carry at
all (structurally, not just as a zero).

### 4.3 `v_tenant_aging` (`F.008`, 644 rows) — CURRENT_DATE-dependent, reversals INCLUDED
```sql
ar_charges AS (SELECT jl.organization_id, jl.party_id AS tenant_id, jl.allotment_id,
                      je.entry_date AS charge_date, jl.debit-jl.credit AS net
               FROM journal_lines jl JOIN journal_entries je ON je.id=jl.journal_entry_id
                 JOIN coa_accounts a ON a.id=jl.account_id
               WHERE a.code='1200' AND jl.party_kind='tenant')
SELECT ..., SUM(net) FILTER (WHERE CURRENT_DATE-charge_date BETWEEN 0 AND 30)  AS bucket_0_30,
            SUM(net) FILTER (WHERE CURRENT_DATE-charge_date BETWEEN 31 AND 60) AS bucket_31_60,
            SUM(net) FILTER (WHERE CURRENT_DATE-charge_date BETWEEN 61 AND 90) AS bucket_61_90,
            SUM(net) FILTER (WHERE CURRENT_DATE-charge_date > 90)             AS bucket_90_plus,
            SUM(net) AS total
```
**Same raw-journal-lines, reversals-included source as 4.2.** Buckets by `CURRENT_DATE -
entry_date` — **this view's output is a snapshot as of the moment it is queried**; the exported
CSV (`F.008`) reflects buckets computed relative to whatever `CURRENT_DATE` was at export time
(inside the 09:02–11:18 window, `M.002`/`M.099`). Reproducing this offline requires fixing an
"as-of" date and is not a fixed historical fact.

### 4.4 `v_invoice_settlement_status` (`F.009`, 5379 rows) — FIFO ledger settlement, a fourth
angle on "how much of this invoice is paid"
```sql
-- windowed cumulative debit/credit per (org, tenant, allotment) over AR account 1200 lines,
-- ordered by entry_date, posted_at, line_no; for each debit ("charge") line:
amount_settled     = GREATEST(0, LEAST(debit, total_credits - prior_debit))
amount_outstanding = debit - amount_settled
settlement_status  = 'paid' | 'partial' | 'unpaid'   (threshold 0.01)
WHERE source_table = 'invoices'
```
This allocates the tenant's *aggregate* AR credits (payments) against charges in **date order**
(a FIFO waterfall), **not** a per-invoice `receipt→invoice` link — there is no
`receipt_allocations` data to join (`receipt_allocations` = 0 rows, confirmed empty,
`data_inventory.md`/integrity report §5). **This is the ledger-derived counterpart to the
application-maintained `invoices.amount_paid`/`invoices.balance`/`invoices.status` columns —
a separate, independently-computed settlement status.** `H.043` (`v_diag_invoice_drift`, 2227
rows) is the direct row-level comparison of `invoices.total_amount - amount_paid - balance`
(app-maintained internal consistency, not compared to the ledger here) — see `conflicts.md`.

### 4.5 `tenant_transactions` — a fifth, frozen definition

`tenant_transactions` (16 451 rows, `T.tenant_transactions`) carries its own
`ledger_type`/`direction`/`category`/`reference_table` taxonomy (`H.026`, quoted in §3) with
`CHARGE`/`DEBIT` and `PAYMENT`/`CREDIT` rows referencing `invoices`, `receipts`,
`tenant_allotments`, `tenant_adjustments`, `deposit_settlements`. `H.028`/`H.052`
(`tenant_balance_4way_sample`/`_full`) compare, per allotment: `allotment_balance_due` (the
application-stored column on `tenant_allotments`), `tenant_transactions_balance` (computed from
this table), `journal_ar_incl_reversals`, `journal_ar_excl_reversals` — **four simultaneously
exported balance definitions for the same allotment** (this is conflict G, formally recorded in
`conflicts.md`). This document records that the four exist and are structurally different
computations; it does not adjudicate which is authoritative.

`v_diag_allotment_balance_drift` (`H.044`, 713 rows) computes its own fifth comparison, again
independently:
```sql
computed_balance = SUM(amount) FILTER (WHERE direction='DEBIT')
                  - SUM(amount) FILTER (WHERE direction='CREDIT')
FROM tenant_transactions WHERE ledger_type IN ('CHARGE','PAYMENT')
-- compared against tenant_allotments.balance_due, floored at 0, flagged if |drift| > 1.00
```

---

## 5. Deposits / settlements

**Source tables:** `deposit_settlements` (307 rows, `T.deposit_settlements`) and, on the ledger
side, `journal_entries`/`journal_lines` with `source_table='deposit_settlements'`.

**Columns (`T.deposit_settlements`):** `id, organization_id, tenant_id, allotment_id,
deposit_amount, pending_rent, pending_eb, pending_late_fees, damages, other_deductions,
total_deductions, refund_amount, settlement_date, status, notes, created_at, is_deleted` (17 of
23 `v_export_deposit_settlements` columns; the export used the base table directly).

### 5.1 Posting gate — only `completed`/`approved` settlements reach the ledger

```sql
v_should_post := status IN ('completed','approved') AND NOT is_deleted
```
(`FN.trg_settlement_journal_post`, full body in §1.) On `INSERT`, posts only if
`v_should_post`. On `UPDATE`: not-posted→posted posts fresh; posted→not-posted (status reverted,
or soft-deleted) reverses; posted→posted-but-amounts-changed (`deposit_amount`, `pending_rent`,
`pending_eb`, `pending_late_fees`, `damages`, `other_deductions`, `refund_amount`) reverses and
reposts. **Date field for the posting:** `COALESCE(settlement_date, current_date)`. **Hard
delete:** `trg_cascade_je_deposit_settlements → delete_journal_entries_on_source_delete`
physically removes the JE (§1.4).

### 5.2 Validation — pre-INSERT/UPDATE constraint on deductions

`validate_deposit_settlement` (`FN.validate_deposit_settlement`, `BEFORE INSERT,UPDATE`):
sums `pending_rent + pending_eb + pending_late_fees + damages + other_deductions`; if that total
is `> 0` and the target allotment (when `allotment_id` is set) has **no `actual_exit_date` AND
`staying_status NOT IN ('Exited','Cancelled')`**, the write is rejected
(`ERRCODE=check_violation`). A deduction-free row (pure transfer/refund, or `allotment_id IS
NULL`, "legacy tenant-only settlement") is always allowed. **This is a write-time (not
retrospective) constraint** — it does not re-validate existing rows if the allotment's status
changes afterward, which is offered as the likely mechanism behind `v_deposit_ledger_anomalies`'
`premature_settlement` anomaly (22 rows total across 3 anomaly types, `H.046`) — stated as a
plausible mechanism from reading the trigger logic, not confirmed by tracing individual rows.

### 5.3 Ledger-amount vs source-amount — three named diagnostics, exact SQL

```sql
-- v_je_amount_reconciliation (H.001):
legacy_amount  = SUM(deposit_settlements.refund_amount) WHERE NOT is_deleted
je_net_amount  = SUM(CASE WHEN je.is_reversal_of IS NULL THEN jl.credit ELSE -jl.credit END)
                 FROM journal_entries je JOIN journal_lines jl ... JOIN coa_accounts a
                 WHERE je.source_table='deposit_settlements' AND a.account_type='ASSET'
                       AND a.code LIKE '11%'
```
`H.001` result: `legacy_amount` ₹5 085 959.33 vs `je_net_amount` ₹5 669 454.67 — **diff
₹583 495.34, verdict `INVESTIGATE`**. Note this diagnostic compares only `refund_amount` (the
cash leg, account `11%`) — it does **not** compare `total_deductions` or `deposit_amount`
against their own ledger legs (accounts `2100` deposit-held, or wherever deductions post — not
exported). `H.050` (`settlement_amount_vs_ledger_rows`, 43 rows) is the row-level trace behind
this aggregate; row-level mechanism is deferred to `conflicts.md`/`data_quality_report.md`.

`v_je_source_counts` (part of `H.002`): `deposit_settlements` — `legacy_live=307`,
`legacy_total=307`, `je_forward=338`, `je_reversal=38`, `je_distinct_sources=300`,
`gap_live_minus_je = 307-300 = 7` — **7 live, non-deleted settlements have no forward journal
entry at all.** Given §5.1's posting gate, the most direct evidence-supported explanation is
that these 7 rows are not in `status IN ('completed','approved')` — **not confirmed by tracing
the 7 rows themselves** in the exported diagnostics; recorded as the mechanism implied by the
trigger logic, not as a proven fact.

### 5.4 Deposit-phantom and anomaly views

`v_diag_deposit_phantom` (`H.045`, 32 rows): allotments with `deposit_paid > 0`,
`staying_status IN ('Exited','Cancelled')`, and **no** `deposit_settlements` row at all —
"Deposit held with no live tenant relationship." `v_deposit_ledger_anomalies` (`H.046`, 22 rows,
full SQL read above) unions three anomaly types: `premature_settlement` (§5.2),
`duplicate_open_settlement` (>1 non-`completed` settlement on one allotment), and
`transfer_double_count` (the same tenant's deposit ledger balance, computed from
`journal_lines` accounts `2100`/`2400` reversals-excluded, appears on more than one allotment
simultaneously).

---

## 6. Occupancy

**No single occupancy definition exists in the codebase.** Five distinct, independently-computed
definitions are exported, all read in full below; `conflicts.md` carries the numeric comparison
table and the mechanism behind the "7 unbucketed On-Notice beds."

### 6.1 `v_occupancy` (`F.005`, 1 row) — definition A (Staying only, live bed+apartment)
```sql
live_beds AS (SELECT b.* FROM beds b JOIN apartments ap ON ap.id=b.apartment_id
              WHERE b.status='Live' AND ap.status='Live'),
state AS (SELECT b.*,
  EXISTS(SELECT 1 FROM tenant_allotments a WHERE a.bed_id=b.id AND a.staying_status='Staying')   AS occupied,
  EXISTS(SELECT 1 FROM tenant_allotments a WHERE a.bed_id=b.id AND a.staying_status='Booked')    AS booked,
  EXISTS(SELECT 1 FROM tenant_allotments a WHERE a.bed_id=b.id AND a.staying_status='On-Notice') AS on_notice
  FROM live_beds b)
SELECT organization_id, property_id,
  COUNT(*)                                              AS total_beds,
  COUNT(*) FILTER (WHERE occupied)                      AS occupied,
  COUNT(*) FILTER (WHERE on_notice AND occupied)         AS on_notice,
  COUNT(*) FILTER (WHERE NOT occupied AND booked)        AS booked,
  COUNT(*) FILTER (WHERE NOT occupied AND NOT booked AND NOT on_notice) AS vacant,
  ROUND(100.0 * occupied / total_beds, 2)                AS occupancy_pct
FROM state GROUP BY organization_id, property_id
```
**Source tables:** `beds`, `apartments`, `tenant_allotments`. **Filter:** `beds.status='Live'
AND apartments.status='Live'`. **Grain:** `organization_id, property_id` — a **current snapshot**,
no date parameter. `occupancy_pct` numerator = `Staying` only. **Exported result:** total=195,
occupied=168 → 86.15% — matches `H.012` definition **A** (168/195).

**The "7 unbucketed On-Notice beds" — mechanism, read directly from this SQL.** The output
column `on_notice` is defined as `COUNT(*) FILTER (WHERE on_notice AND occupied)` — i.e. a bed
must simultaneously have a `Staying` allotment (`occupied=true`) **and** an `On-Notice`
allotment (`on_notice=true`) to be counted. `H.013` (`allotment_status_rollup`) shows
**0 beds carry both statuses at once** (`beds_with_both_statuses = 0`), so this column is
structurally guaranteed to be `0` regardless of how many beds are actually on notice. A bed
whose *only* allotment is `On-Notice` has `occupied=false, on_notice=true, booked=false`: it
fails the `on_notice` column's filter (`occupied` is false), and it **also** fails the `vacant`
filter (`NOT on_notice` is false). **It matches none of the view's four output buckets.**
`H.011` (`unbucketed_on_notice_beds`) names the exact 7 bed ids with `occupied=false,
booked=false, on_notice=true` — bed ids `53df99b1…`, `18323ac7…`, `dcfddc61…`, `cead0c81…`,
`3d87a782…`, `2225fe89…`, `16d9e7d4…`. `H.013` corroborates: 168 Staying allotments, 7 On-Notice
allotments, 7 beds held on notice, 0 overlap. **This bug is local to `v_occupancy`'s SQL** — see
§6.4, `get_universal_metrics`'s own occupancy bucketing does not share this defect.

### 6.2 `v_active_tenants` (`F.022`, 1 row) — tenant-grained, no bed/apartment filter
```sql
SELECT organization_id, property_id,
  COUNT(DISTINCT tenant_id) FILTER (WHERE staying_status IN ('Staying','On-Notice')) AS active_tenants,
  COUNT(DISTINCT tenant_id) FILTER (WHERE staying_status='Booked')                   AS booked_tenants,
  COUNT(DISTINCT tenant_id)                                                          AS total_tenants_ever
FROM tenant_allotments GROUP BY organization_id, property_id
```
**Source:** `tenant_allotments` directly — **no join to `beds`/`apartments` at all**, so bed or
apartment `status` (Live/Not-Active) has no bearing on this count. **Grain:** counts distinct
**tenants**, not beds — a tenant with two simultaneous allotments (see `H.056`
`overlapping_allotments`, 187 pairs) is counted once. **`active_tenants`** = `Staying` +
`On-Notice` combined — this is definition **B**'s numerator basis (Staying+On-Notice), but
applied to tenants, not beds.

### 6.3 `get_bed_occupancy_timeline(p_bed_id, p_from, p_to)` — per-bed day-range timeline,
definition E
```sql
occ AS (SELECT GREATEST(ta.onboarding_date, v_from) seg_from,
               LEAST(COALESCE(ta.actual_exit_date, CURRENT_DATE), v_to) seg_to, ta.tenant_id
        FROM tenant_allotments ta
        WHERE ta.bed_id = p_bed_id
          AND ta.staying_status IN ('Staying','On-Notice','Exited')
          AND ta.onboarding_date IS NOT NULL)
-- + vacant-gap segments computed between/around the occupied segments
```
(`FN.get_bed_occupancy_timeline`, full body quoted above.) **This function itself applies no
bed/apartment `status='Live'` filter** — it is called per specific `bed_id`; whether the caller
restricts to Live beds is a property of the caller, not this function. Includes historically
`Exited` tenancies as "occupied" days, which is why definition E's H.012e figure (194/203) is
larger than the Staying-only definitions and uses the full 203-bed universe as its denominator,
not the 195-bed Live∩Live universe. **Date-bounded:** `v_to = LEAST(p_to, CURRENT_DATE)` — never
counts future days.

### 6.4 `get_universal_metrics` (v1) `propertyStatus` — definition D, with a **different**
on-notice mechanism than `v_occupancy`
```sql
live_beds AS (SELECT id FROM beds WHERE organization_id=p_org AND status='Live'),
-- (no join requiring apartments.status='Live' — see caveat below)
bed_state AS (SELECT b.id,
  EXISTS(... staying_status='Staying')   AS has_staying,
  EXISTS(... staying_status='On-Notice') AS has_notice,
  EXISTS(... staying_status='Booked')    AS has_booked
  FROM live_beds b),
occ AS (SELECT COUNT(*) total,
               COUNT(*) FILTER (WHERE has_staying)                      occupied,
               COUNT(*) FILTER (WHERE NOT has_staying AND has_booked)   booked,
               COUNT(*) FILTER (WHERE NOT has_staying AND has_notice)   notice
        FROM bed_state)
```
`occupancyPct = occupied/total*100` (Staying only — **matches H.012 definition D, 168/195**).
**Unlike `v_occupancy`, the `notice` column here is `NOT has_staying AND has_notice`** — it
correctly isolates the on-notice-only beds (since `H.013` shows 0 overlap, this is equivalent to
just `has_notice`), so `get_universal_metrics`'s `notice` count is **not** subject to the §6.1
bug; `vacant = GREATEST(total-occupied-booked-notice, 0)` is a clean residual that correctly
excludes the 7 beds. **Caveat:** `live_beds` here is filtered only on `beds.status='Live'`, with
no join requiring `apartments.status='Live'` — structurally different from `v_occupancy`'s
double filter. In this dataset it happens to make no numeric difference (`H.008` bed×apartment
matrix shows all 195 Live beds sit in Live apartments already), but the SQL itself does not
enforce it.

### 6.5 `get_universal_metrics_v2` `propertyStatus` — same bed-status logic as v1, **different
`occupancyPct` formula**
```sql
live_beds AS (SELECT b.id FROM beds b JOIN apartments a ON a.id=b.apartment_id
              WHERE b.status='Live' AND a.status='Live'),   -- matches v_occupancy's double filter
bed_status AS (SELECT lb.id,
  (SELECT al.staying_status FROM tenant_allotments al
   WHERE al.bed_id=lb.id AND al.staying_status IN ('Staying','On-Notice','Booked')
   ORDER BY CASE staying_status WHEN 'Staying' THEN 1 WHEN 'On-Notice' THEN 2 WHEN 'Booked' THEN 3 END,
            onboarding_date NULLS LAST LIMIT 1) AS status
  FROM live_beds lb)
SELECT COUNT(*) total, COUNT(*) FILTER(WHERE status='Staying') occupied,
       COUNT(*) FILTER(WHERE status='On-Notice') notice, COUNT(*) FILTER(WHERE status='Booked') booked,
       COUNT(*) FILTER(WHERE status IS NULL) vacant
...
'occupancyPct', ROUND(100.0 * (occupied + notice) / NULLIF(total,0), 2)
```
**`occupancyPct` here = (Staying + On-Notice) / total — matches H.012 definition B (175/195),
not v1's definition D.** Two versions of the *same named function family* compute
`propertyStatus.occupancyPct` using two different numerators. This is stated as a direct
reading of both bodies (`FN.get_universal_metrics`, `FN.get_universal_metrics_v2`), not an
inference. **Bed-priority tie-break** (Staying > On-Notice > Booked, then earliest
`onboarding_date`) is identical in form to `sync_tenant_staying_status` (§8), applied here at
the bed level instead of the tenant level.

**`get_universal_metrics_v2` also computes a sixth, genuinely distinct metric**: time-weighted
`monthOccupancyPct` — for the **current calendar month only**, a day-by-day
`generate_series` join counts a live bed as "filled" on a given day if any allotment covers that
day under status-specific date rules (`Staying`: `onboarding_date ≤ d`; `On-Notice`:
`onboarding_date ≤ d ≤ actual_exit_date` or exit null; `Booked`: `COALESCE(booking_date,
onboarding_date) ≤ d`; `Exited`: `onboarding_date ≤ d ≤ actual_exit_date`) —
`filled_bed_days / (total_live_beds × days_in_month)`. Neither a point-in-time snapshot nor a
lifetime-average, but a genuine daily occupancy rate for the current month. **Evidence:**
`FN.get_universal_metrics_v2`, quoted in full above.

### 6.6 `get_occupancy_intelligence(p_org, p_from, p_to)` — a seventh, day-weighted,
window-bounded, per-bed metric with a scoring model
Availability window per bed = `[GREATEST(apartments.start_date, p_from), LEAST(apartments.
end_date, p_to)]`, clamped to Live beds in Live apartments. Occupied stints
(`staying_status IN ('Staying','On-Notice','Exited')`) are clamped to that availability window,
merged via a gaps-and-islands overlap-merge (`occ_ord`/`occ_grp`/`occ_merged`) so overlapping or
adjacent allotments on one bed are not double-counted, then `occupied_days` = summed merged-span
length. `occupancy_pct = LEAST(100, ROUND(100.0*occupied_days/available_days, 2))`. Also
computes `avg_fill`/`median_fill` (gap between one tenant's exit and the next tenant's
onboarding), `avg_stay`, `turnover` (`exited_count/available_days*365`), `realized_revenue` /
`potential_revenue` (from `monthly_rental`), a normalised 0–100 `score`
(40% occupancy + 30% inverse fill-time + 20% stay-length + 10% inverse turnover, each min-max
normalised across the bed population), and separately a `status_now` field
(`occupied`/`notice`/`booked`/`vacant`, current-snapshot, `On-Notice` labelled distinctly from
`occupied` but **counted alongside it** in the `occupied_beds_now` rollups:
`COUNT(*) FILTER (WHERE status_now IN ('occupied','notice'))`). Rolls up to per-apartment,
per-property, per-bed-type, a monthly trend, and an apartment×month heatmap. **This function was
not exported as data** (no matching CSV — it takes org/date parameters not captured by any
diagnostic export); its full body is exported (`FN.get_occupancy_intelligence`) and quoted
above, but **no output rows exist to validate against.**

### 6.7 Occupancy definitions actually exported and directly comparable (`H.012a`–`H.012e`)

| Def | Basis (evidence file) | Numerator | Denominator |
|---|---|---|---|
| A | `v_occupancy`: Live bed+apt, Staying only (`H.012a`) | 168 | 195 |
| B | Live bed+apt, Staying+On-Notice (`H.012b`) | 175 | 195 |
| C | ALL beds (no Live filter), Staying+On-Notice (`H.012c`) | 175 | 203 |
| D | `get_universal_metrics` v1: `beds.status=Live` only, Staying (`H.012d`) | 168 | 195 |
| E | `get_bed_occupancy_timeline`: Staying+On-Notice+Exited (`H.012e`) | 194 | 203 |

Definition B is what `get_universal_metrics_v2.propertyStatus.occupancyPct` and
`v_active_tenants.active_tenants` both compute (§6.2, §6.5); it is **not** what `v_occupancy`
(definition A) or `get_universal_metrics` v1 (definition D) compute — three different named
objects in the same codebase disagree with each other on whether On-Notice counts as occupied.

---

## 7. Expenses

**Source table:** `expenses` (516 rows, `T.expenses`). **Columns:** `id, organization_id,
property_id, apartment_id, bed_id, description, amount, expense_date, billing_month,
data_source, related_asset_id, category_id, subcategory_id, vendor_id, ticket_resolution_id,
issue_type_id, payment_mode, …` (20 columns exported; **no `is_deleted` column** — see §1.4).

### 7.1 Posting (`FN.trg_expense_journal_post`, full body in §1)
`INSERT` always attempts `build_expense_lines(NEW.id)` (**body not exported**) then
`post_journal_entry`. `UPDATE` reverse-and-reposts on change to `amount, category_id,
subcategory_id, issue_type_id, expense_date, property_id, apartment_id, bed_id`. `DELETE` (hard,
the only delete path — no soft-delete column) calls `find_journal_entry_for_source` then
`reverse_journal_entry`, **but** `trg_cascade_je_expenses → delete_journal_entries_on_source_delete`
also fires `AFTER DELETE` and, by alphabetical trigger-name ordering (`trg_cascade_je_expenses`
< `trg_expense_journal`), runs first and physically deletes the JE — same net-physical-delete
outcome as receipts (§1.4), by the same mechanism.

### 7.2 Ledger-derived totals and category buckets — `v_pnl` / `v_pnl_by_category`
`v_pnl.expenses` = `SUM(signed_amount) WHERE account_type='EXPENSE'` — **all** `5xxx` accounts,
unconditionally. `v_pnl_by_category` (`F.002`, full SQL in §"P&L" below) buckets by explicit
`account_code LIKE` patterns into 9 named categories (`owner_rent` `510%`, `maintenance` `52%`,
`housekeeping` `53%`, `utilities` `54%`, `property_ops` `55%`, `administrative` `56%`,
`salaries` `57%`, `marketing` `58%`, `other_expenses` `59%`) **plus one separate `electricity`
column (`515%`)** — see §9 for why account `5150` falls outside all 9 named buckets.

### 7.3 Expense-composition view — a different rollup rule than `v_pnl_by_category`
`v_expense_composition` (`F.019`, 138 rows) categorises using the **actual COA parent**, not a
hardcoded pattern:
```sql
category_code = COALESCE(v_account_balances.parent_code, v_account_balances.account_code)
```
Every `51xx`/`52xx`/…/`59xx` leaf account's `parent_code` is `5000` ("Operating Expenses") for
top-level accounts like `5100`/`5150`, or the relevant mid-level parent (`5200`, `5300`, …) for
sub-accounts. **Account `5150` (Electricity Payments) rolls up to category `5000`/"Operating
Expenses" here — the same category as `5100` (Owner Rent) — unlike `v_pnl_by_category`, which
puts it nowhere.** This is a second, independent expense-categorisation rule that happens to
handle account 5150 differently from the first. `v_bed_expense_breakdown` (`F.020`, 385 rows)
and `v_property_expense_share` (`F.023`, 46 rows) both use raw `account_code`/`account_name`
(no rollup) filtered to `bed_id IS NOT NULL` / `property_id IS NOT NULL` respectively.

### 7.4 Maintenance-linked expenses — two different linkage paths (see §11)
`expenses.ticket_resolution_id` links an expense to a maintenance ticket resolution. `expenses.
issue_type_id` links an expense directly to an issue type — **a separate FK, not derived from
the ticket**. `v_maintenance_metrics` sums cost via `ticket_resolutions ⋈ expenses` (through the
resolution). `v_maintenance_by_issue_type` sums cost via `expenses.issue_type_id` directly and
**requires `ticket_resolution_id IS NOT NULL`** as a separate condition — two joins that need
not agree if an expense's `issue_type_id` differs from its resolution's ticket's issue type.

### 7.5 `expense_bed_allocations` — per-bed expense splitting (448 rows, `T.expense_bed_allocations`)
Columns: `id, expense_id, bed_id, organization_id, allocated_amount, created_at`. Wired to
`trg_expense_alloc_journal_repost` (`AFTER INSERT,DELETE,UPDATE` on `expense_bed_allocations`,
`FN.TRG`) — **body not exported**; the exact journal effect of a per-bed allocation is **not
determinable from exported evidence**.

---

## 8. Profit / P&L

**Three structurally different profit numbers are computed in the exported codebase. None is
labelled "wrong"; all are preserved.**

### 8.1 `v_pnl` / `v_pnl_by_category` — pure ledger profit
`net_profit = SUM(signed_amount WHERE account_type='INCOME') - SUM(signed_amount WHERE
account_type='EXPENSE')`, both terms from `v_account_balances` (reversals excluded). This
includes **whatever is actually posted to expense account `5100`/`5150` etc. in the ledger** —
whether or not owner-payment or electricity postings reach those accounts in practice is not
independently confirmed here (the posting trigger bodies for owner payments and EB are not
exported — see §5150 note in §9 and §12 in this document).

### 8.2 `get_universal_metrics` (v1) — invoice-minus-expense profit, **no owner-payments term**
```sql
'totalProfit', (SELECT SUM(total_amount) FROM i_period) - (SELECT SUM(amount) FROM e_period)
```
`i_period` = `invoices` for the period (§2.2), `e_period` = `expenses` for the period (§7).
**There is no owner_payments term anywhere in this expression.** `v_diag_owner_rent_missing_from_profit`
(`F.028`, 46 rows) states this explicitly in its own `note` column:
```sql
SELECT organization_id, date_trunc('month', COALESCE(paid_date,due_date)) AS month,
       SUM(escalated_amount) AS owner_rent_paid_or_accrued,
       'Currently NOT included in get_universal_metrics.totalProfit' AS note
FROM owner_payments WHERE status IN ('paid','pending') GROUP BY organization_id, month
```
This is the view's own self-documenting text — not an inference by this document.

### 8.3 `get_universal_metrics_v2` — ledger profit, with an explicit owner-rent substitution
```sql
v_owner_rent_pnl := v_owner_rent;   -- = v_pnl_by_category.owner_rent ('510%' bucket), ledger-derived
SELECT SUM(op.escalated_amount) INTO v_owner_rent
  FROM owner_payments op WHERE op.bill_date BETWEEN v_from AND v_to;
v_expenses := v_expenses - v_owner_rent_pnl + v_owner_rent;
'totalProfit', v_revenue - v_expenses
```
**v2 explicitly discards whatever the ledger's `510%` bucket contains for the period and
replaces it with `SUM(owner_payments.escalated_amount)` filtered on `bill_date`, before
computing `totalProfit`.** This is a direct, application-layer correction for the gap that
`v_diag_owner_rent_missing_from_profit` names — read verbatim from `FN.get_universal_metrics_v2`,
not inferred. `totalProfit = v_revenue - v_expenses` where `v_revenue` is the full
`v_pnl_by_category.revenue` sum (§2.3) and `v_expenses` is the ledger total with the owner-rent
swap applied. **`v2.totalProfit` therefore does include an owner-rent term; `v1.totalProfit`
does not; `v_pnl.net_profit` includes whatever the ledger happens to hold, unverified.**

### 8.4 Date-basis conflict inside the owner-rent figure itself
Three different date columns are used to place an owner payment into "profit" for a given
period, and they disagree with each other:
- **Ledger posting date** (`FN.normalize_owner_payment_journal_dates`, `BEFORE INSERT,UPDATE` on
  `journal_entries`): forces `entry_date := owner_payments.bill_date` for any JE with
  `source_table='owner_payments'`.
- **`get_universal_metrics_v2`'s substitution** (§8.3): filters `owner_payments.bill_date`.
- **`v_diag_owner_rent_missing_from_profit`** (§8.2): groups by `COALESCE(paid_date, due_date)`
  — **not** `bill_date`.

`(a)` and `(b)` agree; `(c)` is a third, different basis. Which one "P&L profit for month X"
should use is not determinable from the evidence beyond stating that all three exist.

### 8.5 P&L bucket gap — item I in the brief, fully traced

`H.017`/`H.054` (byte-identical, `pnl_bucket_gap`, 57 months): for every month,
`total_expenses = sum_of_buckets + unbucketed`, and **`unbucketed` equals `electricity_column`
exactly, in every one of the 57 rows** (verified: `SUM(total_expenses)=20 784 832`,
`SUM(sum_of_buckets)=19 754 214`, `SUM(unbucketed)=SUM(electricity_column)=1 030 618`, across
the full 57-row export — this arithmetic identity was independently re-derived from the raw
`H.017` CSV, not merely read off a label). **Mechanism, read directly from `v_pnl_by_category`'s
SQL (§7.2):** account `5150` "Electricity Payments" (`T.coa_accounts`) is a direct child of
`5000`, so its code (`5150`) matches the pattern `'515%'` — but **none** of the 9 named
category-bucket patterns (`510%, 52%, 53%, 54%, 55%, 56%, 57%, 58%, 59%`) matches `5150`
(`54%` is `Utilities`, which starts `540`–`544`, not `515`). `v_pnl_by_category` computes a
**tenth, separate `electricity` column** using its own `515%` pattern specifically to capture
this account — but that column is not one of the 9 "named buckets" that `sum_of_buckets`
(computed by whatever diagnostic query produced `H.017`, not itself one of the 54 exported view
definitions) evidently sums. **`total_expenses` (all `5xxx`) always includes account `5150`;
`sum_of_buckets` (the 9 named categories) never does.** This is the exact, SQL-verified
mechanism behind item I.

---

## 9. Owner payments

**Source table:** `owner_payments` (345 rows, `T.owner_payments`). **Columns:** `id,
organization_id, owner_id, contract_id, apartment_id, payment_month, due_date, base_amount,
escalated_amount, status, paid_date, payment_mode, notes, created_at, actual_due_date,
reference_number, bill_date, …` (17 columns). Related: `owner_contracts` (35 rows,
`T.owner_contracts`) holds `monthly_rent, revenue_share_percentage, security_deposit,
lock_in_months, escalation_percentage, escalation_interval_months, …` — the contract terms that
presumably drive `escalated_amount`, though the calculation itself is not exported as a
function.

**Posting:** `trg_owner_payment_journal` fires `AFTER INSERT,DELETE,UPDATE` on `owner_payments`,
calling `trg_owner_payment_journal_post` — **this trigger function's body is one of the 458
signature-only routines; it is not exported.** The exact account(s) debited/credited and
whether `base_amount` or `escalated_amount` (or something else) is posted is **not determinable
from exported evidence**. What is independently verifiable:
- `H.001` (`v_je_amount_reconciliation`): `legacy_amount = SUM(COALESCE(escalated_amount,
  base_amount))` for **all** rows (no `is_deleted` filter — `owner_payments` has no such column)
  compared against `je_net_amount = SUM(debit WHERE source_table='owner_payments' AND
  account_type='EXPENSE')` — result: **`PERFECT`, diff = 0.00.** So whatever the unexported
  trigger does, it posts the full `COALESCE(escalated_amount, base_amount)` to some EXPENSE
  account, in total, with no observed drift.
- `H.002` (`v_je_source_counts`): `owner_payments` — `legacy_live=345`, `je_forward=410`,
  `je_reversal=0`, `distinct_sources=345`, `gap_live_minus_je=0`. **All 345 rows have at least
  one forward JE; 410 forward entries for 345 sources means 65 rows were reposted at least once
  (edited and re-posted), yet zero reversal entries exist for this source table** — consistent
  with `owner_payments` never soft-deleting (no `is_deleted` column) and the observed "posted in
  one batch" pattern (§9.2).
- `normalize_owner_payment_journal_dates` (§1, full body quoted) forces the JE's `entry_date`
  and `period` to the owner payment's `bill_date` — the ledger period for an owner-rent posting
  is always `bill_date`, regardless of what date the trigger that built the lines originally
  used.

### 9.1 Cascade delete
`trg_cascade_je_owner_payments → delete_journal_entries_on_source_delete` — hard `DELETE`
physically removes the JE (§1.4 generic mechanism; `owner_payments` has no soft-delete path to
compare against).

### 9.2 A single-batch posting event
All 345 `owner_payments` rows carry `created_at = 2026-08-13` (`M.025` temporal profile: 1
distinct month; confirmed in the integrity report §9.1), and `H.004`
(`je_by_source_dates`) shows every `owner_payments`-sourced JE's `posted_at` falling inside
`2026-08-13 09:14:24` to `2026-08-13 10:36:58`. **All owner-payment ledger postings were
generated in a single ~82-minute batch run**, not incrementally as payments occurred — a
migration/backfill event, not live day-to-day posting. This bears directly on §8.4's date-basis
question: whichever date field is used, none of them is "when the posting actually happened."

### 9.3 Profit inclusion — see §8.2/§8.3
Owner rent is **excluded** from `get_universal_metrics` v1's `totalProfit`, **included** (via an
explicit substitution) in `get_universal_metrics_v2`'s, and **included at whatever the
(unexported) ledger trigger posts** in `v_pnl`/`v_pnl_by_category`'s `net_profit`/`owner_rent`
bucket.

---

## 10. Tenant lifecycle

**Source tables:** `tenants` (1027 rows, `T.tenants`, 27 PII columns excluded), `tenant_allotments`
(1213 rows, `T.tenant_allotments`), `tenant_exits` (147 rows), `tenant_notices` (86 rows),
`room_switches` (34 rows), `tenant_adjustments` (266 rows), `tenant_absence_records` (38 rows).

### 10.1 `staying_status` enum and where it lives
`tenant_allotments.staying_status` is the primary lifecycle field. `H.014`
(`staying_status_profile`) shows 5 values with row counts: `Exited` 1003, `Staying` 168,
`Cancelled` 31, `On-Notice` 7, `Booked` 4 (1213 total). **A second, denormalised copy exists on
`tenants.staying_status`** (lower-cased), kept in sync by two triggers:

```sql
-- sync_tenant_staying_status (AFTER INSERT,UPDATE on tenant_allotments)
SELECT staying_status FROM tenant_allotments WHERE tenant_id = NEW.tenant_id
ORDER BY CASE staying_status WHEN 'Staying' THEN 1 WHEN 'On-Notice' THEN 2 WHEN 'Booked' THEN 3 ELSE 4 END,
         created_at DESC LIMIT 1;
UPDATE tenants SET staying_status = lower(latest_status) WHERE id = NEW.tenant_id;
```
(`FN.sync_tenant_staying_status`, full body above.) A tenant with multiple allotments (current
or historical, across properties or via room switches) is tagged with whichever single allotment
ranks highest by this priority order (`Staying` > `On-Notice` > `Booked` > anything else),
tie-broken by most recently created. `sync_tenant_staying_status_on_delete`
(`AFTER DELETE` on `tenant_allotments`) re-runs the same lookup on `OLD.tenant_id`, defaulting to
`'new'` if no allotment remains. **`tenants.staying_status` is therefore not an independent
fact — it is always derived from `tenant_allotments`**, and lags behind by however long the
trigger takes (immediate, but only on `tenant_allotments` writes).

### 10.2 Move-in / move-out events — `v_tenant_lifecycle_events`
```sql
SELECT ..., onboarding_date AS event_date, 'move_in' AS event, staying_status
FROM tenant_allotments WHERE onboarding_date IS NOT NULL
UNION ALL
SELECT ..., actual_exit_date AS event_date, 'move_out' AS event, staying_status
FROM tenant_allotments WHERE actual_exit_date IS NOT NULL
```
(`F.017`, 2204 rows full population; `H.036` is a `LIMIT 500` sample of the same view — use
`F.017`, not `H.036`, for anything requiring the complete set.) **Grain:** one row per
onboarding and one row per exit, per allotment — a tenant who onboarded and later exited
contributes 2 rows; a `Booked` tenant with no `onboarding_date` yet contributes 0.

### 10.3 Exit workflow tables
`tenant_exits` (147 rows) — `exit_date, has_notice, room_inspection, key_returned,
damage_charges, key_loss_fee, exit_charges, eb_charges, pending_rent, total_deductions,
advance_held, …` — the operational exit-processing record, separate from
`tenant_allotments.actual_exit_date` and separate from `deposit_settlements`. `tenant_notices`
(86 rows) — `notice_date, exit_date, actual_exit_date, status` — the notice-to-vacate record,
validated by `validate_notice_exit_date` (`BEFORE INSERT,UPDATE`, `FN.TRG`; body not among the
25 exported). **These three tables (`tenant_allotments.actual_exit_date`, `tenant_exits`,
`tenant_notices`) are not shown by any exported view or function to be kept in sync with each
other automatically** — no trigger wiring in `FN.TRG` links `tenant_exits`/`tenant_notices` back
onto `tenant_allotments`.

### 10.4 `v_exit_reconciliation_worklist` — the one view that joins all of AR, deposit, and EB
for an exited tenant
```sql
FROM tenant_allotments ta JOIN tenants/apartments/beds/properties
  LEFT JOIN v_tenant_current_dues cd ON cd.allotment_id = ta.id     -- §4.2, reversals INCLUDED
  LEFT JOIN LATERAL (SUM(invoices.total_amount) WHERE reference_type='exit_estimated_eb'
                      AND allotment_id=ta.id AND NOT is_deleted) eb
  LEFT JOIN LATERAL (SUM(invoices.total_amount) WHERE invoice_type='exit_charge'
                      AND allotment_id=ta.id AND NOT is_deleted) ec
  LEFT JOIN LATERAL (deposit_settlements.status ORDER BY created_at DESC LIMIT 1 
                      WHERE allotment_id=ta.id AND NOT is_deleted) ds
WHERE ta.staying_status='Exited'
  AND (cd.ar_balance <> 0 OR (cd.deposit_held + cd.booking_advance) > 0)
```
(`F.027`, 45 rows; byte-identical re-export at `H.047`.) **Its `dues_now` figure is definition
4.2's `ar_balance` (reversals included), not definition 4.1's `outstanding`.** `eb_already` and
`exit_charge_already` are read from `invoices` directly by `reference_type`/`invoice_type`, not
from the ledger.

### 10.5 Overlaps and duplicates in the lifecycle data
`H.056` (`overlapping_allotments`, 187 bed×allotment-pair rows) records beds with two
`tenant_allotments` whose date ranges overlap. `H.055` (`duplicate_invoices`, 322
allotment/billing_month/invoice_type groups) records more than one invoice issued for the same
tenant/month/type. Neither is resolved here; both are recorded for `data_quality_report.md`.

---

## 11. Maintenance

**Source tables:** `maintenance_tickets` (1610 counted / 1611 exported, §3 of the integrity
report), `ticket_resolutions` (466 rows), `ticket_logs` (8239/8240), `expenses` (via linkage,
§7.4), `issue_types` (51 rows), `maintenance_items`/`maintenance_item_stock_entries`/
`maintenance_item_usage` (asset/inventory side).

### 11.1 Ticket cost — two independently-computed linkage paths
**`v_maintenance_metrics`** (`F.015`, 20 rows):
```sql
FROM maintenance_tickets mt
  LEFT JOIN ticket_resolutions tr ON tr.ticket_id = mt.id
  LEFT JOIN expenses e ON e.ticket_resolution_id = tr.id
GROUP BY mt.organization_id, mt.property_id, date_trunc('month', mt.created_at)
-- cost = COALESCE(SUM(e.amount), 0); month = ticket creation month, not expense/resolution date
```
**`v_maintenance_by_issue_type`** (`F.016`, 9 rows):
```sql
FROM expenses e JOIN issue_types it ON it.id = e.issue_type_id
WHERE e.ticket_resolution_id IS NOT NULL
GROUP BY e.organization_id, e.property_id, date_trunc('month', e.expense_date), it.id
-- resolved_tickets = COUNT(DISTINCT e.ticket_resolution_id); month = expense_date
```
The two views can disagree whenever an expense's `issue_type_id` differs from the issue type of
the ticket its `ticket_resolution_id` points to (two separate FKs on the same `expenses` row —
`issue_type_id` and, transitively via `ticket_resolution_id → ticket_resolutions.ticket_id →
maintenance_tickets`, the ticket's own issue type), and whenever `mt.created_at`'s month differs
from `e.expense_date`'s month (a ticket opened in one month can be resolved and expensed in a
later one). `H.019` (`maintenance_view_vs_actual`): a maintenance-ticket view reported 1613 vs
1611 actual tickets — a small, unexplained discrepancy recorded but not traced further here.
`H.058` (`maintenance_cost_linkage`) is the row-level trace connecting resolutions ↔
issue-type-linked expenses ↔ closure cost; not re-derived here.

### 11.2 Ticket resolution cost fields
`ticket_resolutions` (466 rows) carries `total_parts_cost, total_labour_cost, total_cost,
closure_summary` — an **application-recorded** cost figure, independent of both `expenses.amount`
paths above. `H.018` (`resolutions_per_ticket`): 462 tickets have exactly 1 resolution, 2 tickets
have 2 — multiple resolutions per ticket are possible but rare.

### 11.3 Expense-sync-on-delete/update
`expense_sync_resolution` (`FN.expense_sync_resolution`, `AFTER DELETE,UPDATE` on `expenses`,
full body in §7) keeps `ticket_resolutions` in sync when its **linked** expense changes: deleting
the linked expense zeroes `total_cost/actual_total_cost/total_parts_cost/total_labour_cost` and
clears payment fields on the resolution, logging a `ticket_logs` row; updating
`amount/expense_date/vendor_id/receipt_url` propagates the new values onto the resolution and
logs a second `ticket_logs` row. **This is a one-way sync (expense → resolution); no evidence of
the reverse direction (resolution → expense) exists in the exported bodies.**

### 11.4 Maintenance stock
`maintenance_item_stock_summary` (view, `F.025`/`F.026` duplicate, 93 rows) sums
`maintenance_item_stock_entries.quantity_available` per item, `LEFT JOIN`ed so items with zero
stock entries still appear at `current_stock=0`. `maintenance_item_low_stock` filters that to
`current_stock <= minimum_stock_level` — **not separately confirmed to have been exported**; see
`data_inventory.md` §A.2 ambiguity note.

---

## 12. EB / electricity

**Four tables, four different coverages, no exported ledger-posting body.**

| Table | Rows | Columns | Coverage (`M.025`) |
|---|---|---|---|
| `eb_payments` | 70 | `id, org, property_id, apartment_id, bill_date, bill_amount, payment_date, payment_mode, reference_number, billing_period_start/end, is_locked, locked_by` | `bill_date` 2026-04-29→06-27 (2 months) |
| `electricity_readings` | 1411 | `id, org, property_id, apartment_id, reading_start, reading_end, units_consumed, unit_cost, billing_month, is_locked, locked_by` | `created_at` 2026-03→07 (5 months) |
| `eb_tenant_shares` | 801 | `id, invoice_id, apartment_id, billing_month, total_apartment_bill, total_tenant_days, per_day_rate, tenant_stay_days, tenant_eb_charge, total_units, unit_cost` | `created_at` 2026-04→08 (5 months) |
| `eb_monitoring_readings` | 35 | `id, org, property_id, apartment_id, reading_date, start_reading, start_month, current_reading, units_consumed, eb_amount, is_danger` | all 35 rows dated 2026-08-18 (1 day) |

**Posting:** `trg_eb_payment_journal → trg_eb_payment_journal_post` (`AFTER INSERT,UPDATE` on
`eb_payments`, `FN.TRG`) and its cascade-delete counterpart
(`trg_cascade_je_eb_payments → delete_journal_entries_on_source_delete`) exist per the trigger
wiring, but **`trg_eb_payment_journal_post`'s body is one of the 458 signature-only routines —
not exported.** The account(s) it posts to, and whether it uses `bill_amount` or something else,
are **not determinable from exported evidence.**

### 12.1 Tenant EB allocation — a formula independently verified from the exported data itself
`eb_tenant_shares` allocates one apartment's electricity bill across the tenants who occupied it
that month, proportional to days stayed. Reading the columns and checking arithmetically against
5 sample rows (all 5 confirmed exact):
```
per_day_rate     = ROUND(total_apartment_bill / total_tenant_days)     -- rounded to whole rupee
tenant_eb_charge = per_day_rate * tenant_stay_days
```
e.g. row 1: `total_apartment_bill=11276, total_tenant_days=186 → 11276/186=60.62 → rounds to 61;
tenant_stay_days=31 → 61×31=1891`, matching the exported `per_day_rate=61,
tenant_eb_charge=1891` exactly. **This formula is inferred from the data, not from an exported
function body** — no allocation function is among the 25 exported bodies — and is stated here
only because it was independently checked against multiple rows, not merely read off a column
name.

### 12.2 Invoice-level EB
`invoices.electricity_amount` is a separate, invoice-level EB charge column (used by
`get_universal_metrics`'s `totalEbCharged`, §2.2). Its relationship to `eb_tenant_shares.
tenant_eb_charge` (same figure, computed twice?) is **not determinable from exported evidence**
— no view or function joins the two.

### 12.3 EB account in the ledger
Account `5150` "Electricity Payments" (EXPENSE, parent `5000`) is the presumed EB ledger
account based on its name and the arithmetic identity in §8.5, but **no exported function body
confirms `trg_eb_payment_journal_post` or the invoice/expense posting paths actually use account
`5150`** — this is inferred from the account's name and from the P&L bucket-gap arithmetic
alone, not confirmed by tracing a posted line to its source `eb_payments`/`invoices` row. Stated
here as the most evidence-consistent reading, not as a confirmed fact.

---

## Evidence-file index for this document

| Area | Primary evidence |
|---|---|
| Ledger mechanics | `M.016` (view SQL), `FN.000`/25 individual `FN.*` bodies, `FN.TRG`, `M.009` (FKs), `T.journal_entries`, `T.journal_lines`, `T.coa_accounts`, `T.financial_audit_log`, `H.001`–`H.005` |
| Revenue | `M.016` (`v_pnl`, `v_pnl_by_category`, `v_revenue_by_period`), `FN.get_universal_metrics`, `FN.get_universal_metrics_v2`, `FN.get_universal_metrics_series`, `T.invoices` |
| Collections | `FN.get_universal_metrics`, `FN.get_universal_metrics_v2`, `FN.trg_receipt_journal_post`, `FN.ensure_booking_receipt_number`, `H.026`, `T.receipts`, `T.tenant_transactions` |
| AR / dues | `M.016` (`v_outstanding_receivables`, `v_tenant_current_dues`, `v_tenant_aging`, `v_invoice_settlement_status`), `H.006`, `H.028`, `H.043`, `H.044`, `H.052` |
| Deposits | `M.016` (`v_diag_deposit_phantom`, `v_deposit_ledger_anomalies`), `FN.trg_settlement_journal_post`, `FN.validate_deposit_settlement`, `H.001`, `H.002`, `H.045`, `H.046`, `T.deposit_settlements` |
| Occupancy | `M.016` (`v_occupancy`, `v_active_tenants`), `FN.get_universal_metrics`, `FN.get_universal_metrics_v2`, `FN.get_bed_occupancy_timeline`, `FN.get_occupancy_intelligence`, `H.008`, `H.011`–`H.014`, `H.012a`–`H.012e` |
| Expenses | `M.016` (`v_pnl_by_category`, `v_expense_composition`, `v_bed_expense_breakdown`, `v_property_expense_share`), `FN.trg_expense_journal_post`, `T.expenses`, `T.expense_bed_allocations`, `T.coa_accounts` |
| Profit / P&L | `M.016` (`v_pnl`, `v_pnl_by_category`, `v_diag_owner_rent_missing_from_profit`), `FN.get_universal_metrics`, `FN.get_universal_metrics_v2`, `FN.normalize_owner_payment_journal_dates`, `H.017`/`H.054`, `H.029`/`H.030` |
| Owner payments | `FN.normalize_owner_payment_journal_dates`, `H.001`, `H.002`, `H.004`, `M.025`, `T.owner_payments`, `T.owner_contracts` |
| Tenant lifecycle | `M.016` (`v_tenant_lifecycle_events`, `v_exit_reconciliation_worklist`), `FN.sync_tenant_staying_status`, `FN.sync_tenant_staying_status_on_delete`, `H.014`, `H.055`, `H.056`, `T.tenant_allotments`, `T.tenant_exits`, `T.tenant_notices` |
| Accounting / ledger | see row 1 |
| Maintenance | `M.016` (`v_maintenance_metrics`, `v_maintenance_by_issue_type`), `FN.expense_sync_resolution`, `H.018`, `H.019`, `H.058`, `T.maintenance_tickets`, `T.ticket_resolutions` |
| EB / electricity | `T.eb_payments`, `T.electricity_readings`, `T.eb_tenant_shares`, `T.eb_monitoring_readings`, `M.025`, `FN.TRG` (posting wiring, body not exported) |

Not covered above because the 25 exported bodies do not include them: asset posting
(`trg_asset_journal_post`, `trg_asset_payment_journal_post`), receipt/invoice/expense/
adjustment/settlement line composition (`build_*_lines`), reversal line composition
(`reverse_journal_entry`), receipt numbering sequence logic (`next_receipt_number`), and EB
posting (`trg_eb_payment_journal_post`). For all of these: **Not determinable from exported
evidence.**
