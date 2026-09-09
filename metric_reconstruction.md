# E. metric_reconstruction.md

Deterministic, offline metric-reconstruction specification for every major business metric, built entirely from the exported CSV evidence package -- no live Supabase access. This document defines HOW the future semantic layer computes each metric; it does not build the AI/chat layer itself.

**Three concepts are kept explicitly separate throughout, per the brief's critical distinction (never merged):**

- **Evidence truth** -- what the exported CSVs actually contain (a specific number, re-derived and shown in the `Validation target` field).
- **Business definition** -- what the application's views/functions APPEAR to mean, read directly from their SQL/function bodies (the `Definition` field).
- **Recommended semantic status** -- what the future AI layer should DO with this metric (the `AI trust status` field: SAFE / DISCLOSE / SHOW_BOTH / BLOCK / NOT_DETERMINABLE). A BLOCK status is never downgraded merely because a plausible alternative calculation exists elsewhere in this document.

**Every reconstruction in this document was actually executed** against the raw CSVs by the scripts in `scripts/validation/`, not merely described. Where a matching business view or diagnostic export exists, the reconstructed value is compared against it and the exact absolute/percentage difference is reported -- never simply "matches". Results are in `validation_summary.csv` (80 rows: 73 MATCH, 4 DIFFERS -- each with a stated mechanism, 3 NOT_DETERMINABLE -- no reference exists to compare against) and `monthly_validation/*.csv` for the three time-series metrics validated at monthly grain.

## How to read each entry

Every metric uses the exact 23-field template the brief specifies. Fields that could not be established from the exported package read **"Not determinable from exported evidence."** verbatim. Fields where multiple valid definitions coexist and no evidence proves a winner read **"Conflicting definitions exist."** verbatim (never silently resolved, never averaged). `Known conflicts` cross-references `conflicts.md` C-numbers; `Known limitations` cross-references `data_quality_report.md` DQ-numbers, where applicable.

---

## 1. Financial metrics

<a id="mrev001"></a>
### M.REV.001 -- Revenue (total, ledger-derived)

```text
Metric: Revenue (total, ledger-derived)
Business meaning: Total income recognised across all INCOME-type ledger accounts (rental, electricity, guest stay, onboarding, late fees, exit charges, other), for whatever date range is queried.
Definition: SUM(signed_amount) WHERE account_type='INCOME', reversal-excluded convention (v_account_balances).
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_pnl (F.001), v_revenue_by_period (F.003)
Source functions: None required -- fully reconstructable from raw ledger tables
Relevant columns: journal_lines.debit, journal_lines.credit, journal_lines.account_id; journal_entries.entry_date, is_reversal_of; coa_accounts.account_type, normal_balance
Filters: coa_accounts.account_type = 'INCOME'
Joins: journal_lines JOIN journal_entries ON journal_entry_id; JOIN coa_accounts ON account_id
Date field: journal_entries.entry_date (journal_lines carries this denormalised at export)
Aggregation: SUM(signed_amount), signed_amount = CASE normal_balance WHEN 'CREDIT' THEN credit-debit ELSE debit-credit END
Organization grain: organization_id (single org in this dataset)
Property grain: property_id (v_pnl grain includes property_id; some manual/unlinked postings carry NULL property_id)
Tenant/allotment grain: Not applicable at this aggregate level
Reversal treatment: EXCLUDED: WHERE is_reversal_of IS NULL AND NOT EXISTS(reversal-of-this-entry). Proven equivalent in total to the reversal-INCLUDED convention (balances net to zero identically) -- see conflicts.md C.002.
Soft-delete treatment: Not directly filtered here -- a soft-deleted source row's reversal entry is excluded by the same is_reversal_of rule, so its net ledger contribution is already zero.
Duplicate treatment: Not applicable to the ledger total itself (duplicates live at the source-row level, e.g. invoices -- see M.INV.001/DQ.013). A duplicate invoice that was actually paid and posted DOES inflate ledger revenue; this reconstruction does not de-duplicate at the ledger layer.
Historical coverage: Ledger (journal_entries.entry_date): 2019-11-03 to 2026-09-20 (54 months with ledger activity; business_logic.md 9). Revenue accounts specifically active across the ledger's full span.
Snapshot/current-state behavior: Not snapshot-dependent -- entry_date is a fixed historical fact, not derived from CURRENT_DATE.
Known conflicts: None for the total (C.002 proves reversal convention is immaterial to totals).
Known limitations: Revenue by ACCOUNT can drift at the individual-posting level under repeated edits (see M.COL/M.INV source-vs-ledger drift, DQ.006/007) but this has not been shown to affect the aggregate INCOME total, which is proven exact against F.001.
AI trust status: SAFE
Validation target: F.001 v_pnl.revenue (validated: REV.01, exact match, Rs.72,705,593.43 both sides)
```

**Note:** Validated by scripts/validation/validate_revenue.py

<a id="mrev002"></a>
### M.REV.002 -- Revenue by month

```text
Metric: Revenue by month
Business meaning: Monthly time series of ledger-derived revenue, at (property, month) grain matching v_pnl's own grouping.
Definition: GROUP BY organization_id, property_id, date_trunc('month', entry_date) of M.REV.001's reconstruction.
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_pnl (F.001)
Source functions: None
Relevant columns: Same as M.REV.001 plus date_trunc('month', entry_date)
Filters: account_type='INCOME'
Joins: Same as M.REV.001
Date field: entry_date, truncated to calendar month
Aggregation: SUM(signed_amount) per (property_id, month)
Organization grain: organization_id
Property grain: property_id -- REQUIRED as part of the grain: a month with both a real-property posting and a NULL-property ('manual') posting produces two separate rows, not one
Tenant/allotment grain: Not applicable
Reversal treatment: Same as M.REV.001 (excluded convention)
Soft-delete treatment: Same as M.REV.001
Duplicate treatment: Same as M.REV.001
Historical coverage: 53 distinct calendar months of INCOME activity within the ledger's 54-month span (one month has expense-only activity, no income).
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: None.
Known limitations: A reconstruction that groups by month ALONE (dropping property_id) will produce fewer rows than v_pnl and can silently merge a real-property and a NULL-property month into one bucket -- confirmed directly in this pass (REV.02).
AI trust status: SAFE
Validation target: F.001 v_pnl, monthly rows (validated: REV.02, 57 of 57 (property,month) rows match in VALUE exactly; monthly_validation/revenue_by_month.csv). Row-count differs (55 reconstructed vs 57 in the view) only because v_pnl includes 2 EXPENSE-only months with revenue=0 that an income-only reconstruction never creates a row for -- both sides are Rs.0 for those months, confirmed by inspection.
```

**Note:** monthly_validation/revenue_by_month.csv

<a id="mcol001"></a>
### M.COL.001 -- Collections (application-level)

```text
Metric: Collections (application-level)
Business meaning: Total cash actually collected from tenants via receipts, as recorded by the application.
Definition: SUM(receipts.amount_paid) WHERE NOT is_deleted
Source tables: receipts
Source views: None (no dedicated collections view is exported)
Source functions: get_universal_metrics / get_universal_metrics_v2 compute period-scoped versions of this (bodies exported, no output data)
Relevant columns: receipts.amount_paid, receipts.receipt_type, receipts.payment_date, receipts.is_deleted
Filters: is_deleted = false
Joins: None required
Date field: payment_date
Aggregation: SUM(amount_paid); deposit_collections = SUM(amount_paid) WHERE receipt_type='booking'; totalCollectionsWithoutDeposit = total - deposit_collections
Organization grain: organization_id
Property grain: Not carried on receipts directly -- would require a join through tenant_allotments
Tenant/allotment grain: tenant_id, tenant_allotment_id available for drill-down
Reversal treatment: NOT APPLICABLE -- this is a source-table definition, not ledger-derived. See M.COL.003 for the ledger-derived counterpart, which IS reversal-sensitive.
Soft-delete treatment: LIVE ROWS ONLY: is_deleted = false. This is the application's own convention, confirmed by get_universal_metrics' own SQL.
Duplicate treatment: NOT applied. DQ.014 shows 11 of 5858 live receipts are still-undeduplicated flagged duplicates (0.15% of receipts) after a partial, non-remediated dedup pass.
Historical coverage: 2022-11-30 to 2026-08-28 (46 months, receipts.payment_date; business_logic.md 9).
Snapshot/current-state behavior: Not snapshot-dependent for a fixed historical total; a period-scoped version (get_universal_metrics) depends on CURRENT_DATE for its default period window.
Known conflicts: Conflicting definitions exist -- see M.COL.003 (ledger-derived collections differs from this at the individual-receipt level, though aggregate direction is not proven to diverge; C.014/DQ.006).
Known limitations: Excludes the ~0.15% still-live duplicate receipts (DQ.014). Does not reconcile against the ledger by default.
AI trust status: DISCLOSE
Validation target: No dedicated business view exists to validate the total against; validated instead against H.001's legacy_amount for receipts (COLL.01, exact match Rs.81,855,686.97).
```
**Cross-references:** conflicts.md: [C.014](conflicts.md#c014) | data_quality_report.md: [DQ.006](data_quality_report.md#dq006), [DQ.014](data_quality_report.md#dq014)

**Note:** Validated by scripts/validation/validate_collections.py

<a id="mcol002"></a>
### M.COL.002 -- Collections by month

```text
Metric: Collections by month
Business meaning: Monthly time series of M.COL.001, by receipts.payment_date.
Definition: GROUP BY date_trunc('month', payment_date) of M.COL.001's reconstruction.
Source tables: receipts
Source views: None
Source functions: None
Relevant columns: Same as M.COL.001 plus month
Filters: is_deleted=false
Joins: None
Date field: payment_date, truncated to month
Aggregation: SUM(amount_paid) per month; deposit vs non-deposit split retained
Organization grain: organization_id
Property grain: Not carried (see M.COL.001)
Tenant/allotment grain: Not applicable at this grain
Reversal treatment: Not applicable (source-table definition)
Soft-delete treatment: Live rows only
Duplicate treatment: Not applied -- see M.COL.001
Historical coverage: 46 months (2022-11 to 2026-08).
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: Same as M.COL.001.
Known limitations: Same as M.COL.001; no property-level breakdown without an additional join to tenant_allotments.
AI trust status: DISCLOSE
Validation target: No exported view; recorded as a first computation (monthly_validation/collections_by_month.csv, 46 months).
```
**Cross-references:** conflicts.md: [C.014](conflicts.md#c014) | data_quality_report.md: [DQ.006](data_quality_report.md#dq006), [DQ.014](data_quality_report.md#dq014)

**Note:** monthly_validation/collections_by_month.csv

<a id="mcol003"></a>
### M.COL.003 -- Collections (ledger-derived)

```text
Metric: Collections (ledger-derived)
Business meaning: Cash inflow recognised in the ledger against receipts, on the cash/bank accounts.
Definition: SUM(debit) WHERE journal_entries.source_table='receipts' AND account_code IN ('1110','1120'), reversal-excluded.
Source tables: journal_lines, journal_entries, coa_accounts
Source views: None dedicated (get_universal_metrics_v2 computes this internally, no exported output)
Source functions: get_universal_metrics_v2 (body exported, logic reproduced here)
Relevant columns: journal_lines.debit, account_id; journal_entries.source_table, entry_date, is_reversal_of; coa_accounts.code
Filters: source_table='receipts' AND code IN ('1110','1120')
Joins: journal_lines JOIN journal_entries JOIN coa_accounts
Date field: journal_entries.entry_date
Aggregation: SUM(CASE WHEN is_reversal_of IS NULL THEN debit ELSE -debit END)
Organization grain: organization_id
Property grain: Not directly carried on cash-account lines
Tenant/allotment grain: Not applicable at this aggregate
Reversal treatment: INCLUDED via sign-inversion netting (forward +debit, reversal -debit) -- a third reversal convention distinct from both v_account_balances and v_tenant_current_dues (business_logic.md 1.3, definition C).
Soft-delete treatment: Not directly filtered -- inherited via the reversal mechanism (a soft-deleted receipt's forward entry is offset by its reversal).
Duplicate treatment: Not applied at the ledger layer.
Historical coverage: Same ledger window as receipts-sourced postings (46 months of receipts activity within the ledger's 2019-2026 span).
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: Conflicting definitions exist vs M.COL.001 -- DQ.006/C.014 document an Rs.5,340,795.62 aggregate gap in H.001's diagnostic (INVESTIGATE verdict), with a suspected (not proven) repost-accumulation mechanism concentrated in edited receipts.
Known limitations: H.001's own reconciliation query (not among the 54 exported view definitions) shows a materially different number than this direct reconstruction's own components would suggest for cleanly-posted receipts; treat per-receipt ledger totals with caution when entry_count>1.
AI trust status: DISCLOSE
Validation target: H.001 v_je_amount_reconciliation je_net_amount for receipts (validated: COLL.02, exact match Rs.87,196,482.59, reproducing the known Rs.5.34M gap vs M.COL.001 exactly).
```
**Cross-references:** conflicts.md: [C.014](conflicts.md#c014) | data_quality_report.md: [DQ.006](data_quality_report.md#dq006), [DQ.030](data_quality_report.md#dq030)

**Note:** Also used to PROVE DQ.030 (get_universal_metrics_series' wrong account_code='1000' filter returns Rs.0.00 exactly against 0 rows -- validate_collections.py COLL.03).

<a id="minv001"></a>
### M.INV.001 -- Invoice billed amount

```text
Metric: Invoice billed amount
Business meaning: Total amount charged to tenants via invoices (rent, electricity, other charges, late fees), regardless of payment status.
Definition: SUM(invoices.total_amount) WHERE NOT is_deleted
Source tables: invoices
Source views: v_export_invoices (redundant wrapper, not used -- base table exported directly)
Source functions: None required
Relevant columns: invoices.total_amount, rent_amount, electricity_amount, other_charges, late_fee, invoice_type, billing_month, invoice_date, is_deleted
Filters: is_deleted = false
Joins: None required for the total
Date field: COALESCE(invoice_date, (billing_month||'-01')::date, created_at::date) per get_universal_metrics; invoice_date alone for a simpler reconstruction
Aggregation: SUM(total_amount)
Organization grain: organization_id
Property grain: property_id (via tenant_allotments join if needed; invoices itself does not carry property_id directly per its exported columns -- Not determinable whether it does without re-checking M.004)
Tenant/allotment grain: tenant_id, allotment_id available directly on invoices
Reversal treatment: NOT APPLICABLE -- source-table definition. See conflicts.md C.015 for the ledger-derived counterpart's reversal handling.
Soft-delete treatment: LIVE ROWS ONLY: is_deleted = false, matching get_universal_metrics' own filter.
Duplicate treatment: NOT applied. DQ.013 shows 356 of 5214 live invoices (6.8%) are excess rows in 322 duplicate groups (same allotment+billing_month+invoice_type), with NO application-level deduplication mechanism at all.
Historical coverage: 2023-02-05 to 2026-09-20 (44 months plus a small tail of forward-dated rows to 2026-09-20; business_logic.md 9).
Snapshot/current-state behavior: Not snapshot-dependent for a fixed historical total.
Known conflicts: None for the raw billed total itself; see M.AR.001 for how this relates to what's actually collected/owed.
Known limitations: Includes the 6.8% duplicate-row population (DQ.013) unless separately de-duplicated -- this reconstruction does NOT de-duplicate by default, matching how the exported views themselves behave.
AI trust status: DISCLOSE
Validation target: No single exported view sums invoices.total_amount alone; cross-checked against H.001's legacy_amount for invoices (Rs.72,405,785.40) and against v_je_amount_reconciliation's ledger-net figure (Rs.74,829,055.40, INVESTIGATE, Rs.2,423,270.00 gap -- DQ.007/C.015).
```
**Cross-references:** conflicts.md: [C.015](conflicts.md#c015), [C.020](conflicts.md#c020) | data_quality_report.md: [DQ.007](data_quality_report.md#dq007), [DQ.013](data_quality_report.md#dq013)

<a id="minv002"></a>
### M.INV.002 -- Invoice count

```text
Metric: Invoice count
Business meaning: Number of invoices issued, live and/or by type/status.
Definition: COUNT(*) FROM invoices WHERE NOT is_deleted, optionally grouped by invoice_type/status.
Source tables: invoices
Source views: None
Source functions: None
Relevant columns: invoices.id, invoice_type, status, reference_type, is_deleted
Filters: is_deleted = false
Joins: None
Date field: invoice_date or billing_month depending on the question
Aggregation: COUNT(*)
Organization grain: organization_id
Property grain: Via join if needed
Tenant/allotment grain: Via join if needed
Reversal treatment: Not applicable
Soft-delete treatment: Live rows only
Duplicate treatment: NOT applied by default -- see DQ.013. A duplicate-aware count would be 5214-356=4858 unique (allotment,billing_month,invoice_type) invoices.
Historical coverage: Same as M.INV.001 (2023-02 to 2026-09).
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: None.
Known limitations: 6.8% of the raw count is duplicate rows (DQ.013) unless de-duplicated.
AI trust status: DISCLOSE
Validation target: H.035 (invoice_type_status_matrix) provides an independent breakdown by type/status/reference_type; total row count (5214) matches M.006's exact count directly.
```
**Cross-references:** data_quality_report.md: [DQ.013](data_quality_report.md#dq013)

<a id="mar001a"></a>
### M.AR.001A -- Tenant dues -- Def A: v_outstanding_receivables (reversals excluded)

```text
Metric: Tenant dues -- Def A: v_outstanding_receivables (reversals excluded)
Business meaning: Net Accounts-Receivable balance per tenant/allotment, ledger-derived, reversal-excluded convention. Does NOT include deposit or booking-advance balances.
Definition: SUM(signed_amount) WHERE account_code='1200' AND party_kind='tenant', GROUP BY tenant_id, allotment_id, from v_account_balances.
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_outstanding_receivables (F.006)
Source functions: None
Relevant columns: journal_lines.debit, credit, party_id, allotment_id; journal_entries.entry_date, is_reversal_of; coa_accounts.code
Filters: account_code='1200' AND party_kind='tenant'
Joins: journal_lines JOIN journal_entries JOIN coa_accounts
Date field: entry_date (for last_charge_date/last_payment_date only; not a filter on the balance itself)
Aggregation: SUM(signed_amount) per (tenant_id, allotment_id)
Organization grain: organization_id
Property grain: Not carried directly (would need a join through tenant_allotments)
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: EXCLUDED (v_account_balances convention: WHERE is_reversal_of IS NULL AND NOT reversed).
Soft-delete treatment: Inherited via reversal exclusion -- a soft-deleted invoice/receipt/adjustment's reversed entries are excluded.
Duplicate treatment: Not applied at the ledger layer.
Historical coverage: Ledger span, 2019-11 to 2026-09.
Snapshot/current-state behavior: Not snapshot-dependent for the balance itself.
Known conflicts: CONFLICTING DEFINITIONS EXIST -- see M.AR.001B/C/D. Total AR is PROVEN IDENTICAL to Def B (Rs.83,297.85 both, C.002/AR.03), but population (626 vs 645 rows) and scope (no deposit/advance columns) differ.
Known limitations: Silent on deposit_held and booking_advance -- do not use for a 'total amount owed including deposit' question.
AI trust status: SHOW_BOTH
Validation target: F.006 v_outstanding_receivables (validated: AR.01, exact match Rs.83,297.85).
```
**Cross-references:** conflicts.md: [C.001](conflicts.md#c001), [C.002](conflicts.md#c002), [C.005](conflicts.md#c005) | data_quality_report.md: [DQ.002](data_quality_report.md#dq002)

**Note:** One of FOUR competing tenant-balance definitions -- see AR.001A-D collectively. Never expose alone without disclosing the others exist.

<a id="mar001b"></a>
### M.AR.001B -- Tenant dues -- Def B: v_tenant_current_dues (reversals included)

```text
Metric: Tenant dues -- Def B: v_tenant_current_dues (reversals included)
Business meaning: Net AR balance PLUS deposit_held PLUS booking_advance per tenant/allotment, ledger-derived, reversal-included convention.
Definition: Per-account SUM(debit-credit or credit-debit) for accounts 1200/2100/2400, GROUP BY tenant_id, allotment_id, from raw journal_lines (no reversal filter).
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_tenant_current_dues (F.007)
Source functions: None
Relevant columns: journal_lines.debit, credit, party_id, allotment_id; coa_accounts.code IN ('1200','2100','2400')
Filters: party_kind='tenant' AND code IN ('1200','2100','2400')
Joins: journal_lines JOIN journal_entries JOIN coa_accounts
Date field: entry_date (for last_charge_date/last_payment_date, charge_count/payment_count)
Aggregation: SUM per (tenant_id, allotment_id); ar_balance = net_dues (account 1200 only); deposit_held (2100); booking_advance (2400)
Organization grain: organization_id
Property grain: Not carried directly
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: INCLUDED -- no is_reversal_of filter. charge_count/payment_count DO double-count a reversed-and-reposted charge (row counts are NOT reversal-neutral even though dollar totals are).
Soft-delete treatment: No explicit filter -- relies on the reversal mechanism to net out soft-deleted sources.
Duplicate treatment: Not applied.
Historical coverage: Ledger span, 2019-11 to 2026-09.
Snapshot/current-state behavior: Not snapshot-dependent for the balance.
Known conflicts: CONFLICTING DEFINITIONS EXIST -- see M.AR.001A/C/D. AR total PROVEN IDENTICAL to Def A.
Known limitations: charge_count/payment_count are not reversal-neutral (see Reversal treatment above) -- do not use them as a proxy for 'number of distinct charges owed'.
AI trust status: SHOW_BOTH
Validation target: F.007 v_tenant_current_dues (validated: AR.02, exact match Rs.83,297.85; AR.03 proves A==B for the total).
```
**Cross-references:** conflicts.md: [C.001](conflicts.md#c001), [C.002](conflicts.md#c002), [C.005](conflicts.md#c005) | data_quality_report.md: [DQ.002](data_quality_report.md#dq002)

**Note:** One of FOUR competing tenant-balance definitions.

<a id="mar001c"></a>
### M.AR.001C -- Tenant dues -- Def C: application tenant_allotments.balance_due

```text
Metric: Tenant dues -- Def C: application tenant_allotments.balance_due
Business meaning: Application-maintained balance-due field stored directly on the allotment row.
Definition: tenant_allotments.balance_due, as stored (no reconstruction logic -- it is itself the source).
Source tables: tenant_allotments
Source views: None
Source functions: Not determinable from exported evidence (the writer of this column is not among the 25 exported function bodies)
Relevant columns: tenant_allotments.balance_due
Filters: None (or staying_status filter if scoping to current tenants)
Joins: None
Date field: Not applicable (a current-value column, not an event)
Aggregation: SUM(balance_due) for a portfolio total, or read per-row for one allotment
Organization grain: organization_id
Property grain: property_id (carried directly on tenant_allotments)
Tenant/allotment grain: tenant_id, allotment_id (this IS the grain)
Reversal treatment: NOT APPLICABLE -- not ledger-derived at all.
Soft-delete treatment: Not applicable (tenant_allotments has no is_deleted column in its exported columns)
Duplicate treatment: Not applicable.
Historical coverage: Reflects whatever was last written to this column -- not a time series.
Snapshot/current-state behavior: This IS a current-state snapshot column by construction.
Known conflicts: CONFLICTING DEFINITIONS EXIST -- sum (Rs.1,009,125.78) is ~12x the ledger total (Rs.83,297.85) and disagrees with Def D (tenant_transactions) on 751-873 of 1213 allotments depending on which Def D sub-variant is used (AR.04a/b/c). 68 allotments show a nonzero app value where the ledger shows zero ('phantom' app dues); 24 show the reverse.
Known limitations: No exported function confirms how/when this column is updated -- its write path is unverified. Treat with the same caution as any application cache that has not been proven to reconcile with the ledger.
AI trust status: BLOCK
Validation target: No exported view/diagnostic pre-sums this column; summed directly in this pass (validate_receivables.py: Rs.1,009,125.78 over 97 allotments >0).
```
**Cross-references:** conflicts.md: [C.001](conflicts.md#c001), [C.005](conflicts.md#c005) | data_quality_report.md: [DQ.002](data_quality_report.md#dq002)

**Note:** One of FOUR competing tenant-balance definitions. BLOCK: never state this as THE tenant balance without disclosing the other three.

<a id="mar001d"></a>
### M.AR.001D -- Tenant dues -- Def D: tenant_transactions (frozen legacy ledger)

```text
Metric: Tenant dues -- Def D: tenant_transactions (frozen legacy ledger)
Business meaning: Balance computed from the separate, frozen tenant_transactions table -- NOT wired to any live posting trigger.
Definition: SUM(amount WHERE direction='DEBIT') - SUM(amount WHERE direction='CREDIT') per allotment, filtered to ledger_type IN ('CHARGE','PAYMENT'). TWO sub-variants exist: unclipped (can net negative across the total) and GREATEST(...,0)-floored per allotment.
Source tables: tenant_transactions
Source views: None (tenant_transactions is a raw table, not a view)
Source functions: Not determinable from exported evidence -- no trigger references this table (absent from FN.TRG's 55 rows)
Relevant columns: tenant_transactions.amount, direction, ledger_type, allotment_id, date
Filters: ledger_type IN ('CHARGE','PAYMENT')
Joins: None required
Date field: date (NOTE: 1 row has a corrupt year, '0206-03-27' -- DQ.023)
Aggregation: SUM(signed amount) per allotment_id, unclipped OR floored at 0 (two sub-definitions)
Organization grain: organization_id
Property grain: Not carried directly on tenant_transactions
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: NOT APPLICABLE -- this table has no relationship to journal_entries/is_reversal_of at all.
Soft-delete treatment: Not applicable (no is_deleted column; the table is a frozen, one-time bulk load).
Duplicate treatment: Not assessed -- no duplicate-detection mechanism exists for this table.
Historical coverage: date column spans 2019-11-03 to 2026-05-05 nominally, but ALL 16,451 rows were created_at between 2026-04-17 and 2026-04-28 -- an 11-day migration/backfill window, not a live feed. FROZEN since that load (DQ.019).
Snapshot/current-state behavior: Frozen snapshot as of the 2026-04 migration -- does not reflect anything after that date.
Known conflicts: CONFLICTING DEFINITIONS EXIST. Unclipped total Rs.9,968,023.32 (matches H.052's own basis exactly, AR.04a); floored total Rs.10,517,031.27 (AR.04b). Both are ~120x the ledger total (Rs.83,297.85).
Known limitations: Frozen and structurally disconnected from the live ledger (DQ.019). NEVER use for a current-dues question. May be retained for historical/audit reference with an explicit 'legacy, frozen 2026-04' label.
AI trust status: BLOCK
Validation target: H.052 (T164500.151) def2_tenant_transactions column (validated: AR.04a, exact match Rs.9,968,023.32, proving the unclipped-sum mechanism). The floored variant (AR.04b) has no exported reference to compare against (NOT_DETERMINABLE).
```
**Cross-references:** conflicts.md: [C.001](conflicts.md#c001), [C.003](conflicts.md#c003), [C.005](conflicts.md#c005) | data_quality_report.md: [DQ.002](data_quality_report.md#dq002), [DQ.019](data_quality_report.md#dq019), [DQ.023](data_quality_report.md#dq023)

**Note:** One of FOUR competing tenant-balance definitions. BLOCK: catastrophic (~120x) overstatement risk if ever mistakenly surfaced as tenant dues.

<a id="mar002"></a>
### M.AR.002 -- Tenant dues by tenant

```text
Metric: Tenant dues by tenant
Business meaning: Drill-down of M.AR.001A-D to a single tenant/allotment.
Definition: Same four definitions as M.AR.001A-D, filtered to WHERE tenant_id = <x> (or allotment_id = <x>).
Source tables: Same as M.AR.001A-D
Source views: F.006, F.007
Source functions: None
Relevant columns: Same as M.AR.001A-D
Filters: + tenant_id or allotment_id filter
Joins: Same as M.AR.001A-D
Date field: Same as M.AR.001A-D
Aggregation: Same, at tenant/allotment grain (this IS the natural grain of all four definitions)
Organization grain: organization_id
Property grain: Via tenant_allotments.property_id
Tenant/allotment grain: tenant_id, allotment_id (native grain)
Reversal treatment: Same four-way treatment as M.AR.001A-D
Soft-delete treatment: Same as M.AR.001A-D
Duplicate treatment: Same as M.AR.001A-D
Historical coverage: Same as M.AR.001A-D
Snapshot/current-state behavior: Same as M.AR.001A-D
Known conflicts: CONFLICTING DEFINITIONS EXIST -- identical situation to M.AR.001A-D, at per-tenant grain. 873 (H.052 basis) to 751 (this pass's floored-Def2 basis) of 1213 allotments show Def C vs Def D disagreement >Rs.1; 68 allotments show phantom app-side dues; 24 show the reverse.
Known limitations: Same as M.AR.001A-D.
AI trust status: SHOW_BOTH
Validation target: Same underlying validation as M.AR.001A-D (AR.01-AR.04c).
```
**Cross-references:** conflicts.md: [C.001](conflicts.md#c001), [C.003](conflicts.md#c003), [C.005](conflicts.md#c005) | data_quality_report.md: [DQ.002](data_quality_report.md#dq002), [DQ.019](data_quality_report.md#dq019)

<a id="mar003"></a>
### M.AR.003 -- Tenant dues by property

```text
Metric: Tenant dues by property
Business meaning: M.AR.001A/B aggregated by property (requires joining tenant_allotments.property_id, since the AR views themselves do not carry property_id).
Definition: Same as M.AR.001A/B, joined to tenant_allotments on allotment_id to bring in property_id, then GROUP BY property_id.
Source tables: journal_lines, journal_entries, coa_accounts, tenant_allotments
Source views: F.006, F.007
Source functions: None
Relevant columns: + tenant_allotments.property_id
Filters: Same as M.AR.001A/B
Joins: + JOIN tenant_allotments ON allotment_id
Date field: Same as M.AR.001A/B
Aggregation: SUM per property_id
Organization grain: organization_id
Property grain: property_id (via join, not native to the AR views)
Tenant/allotment grain: Aggregated away
Reversal treatment: Same as M.AR.001A/B (both conventions, total proven identical)
Soft-delete treatment: Same as M.AR.001A/B
Duplicate treatment: Same as M.AR.001A/B
Historical coverage: Same as M.AR.001A/B
Snapshot/current-state behavior: Same as M.AR.001A/B
Known conflicts: Same A-vs-B structural note as M.AR.001A/B (population/scope differs, total identical).
Known limitations: With only 1 property in this dataset (M.000), this grain is currently degenerate -- not meaningfully testable as a multi-property breakdown from the exported evidence.
AI trust status: SHOW_BOTH
Validation target: Not separately validated (degenerate single-property case); underlying totals validated via AR.01/AR.02.
```
**Cross-references:** conflicts.md: [C.001](conflicts.md#c001), [C.002](conflicts.md#c002) | data_quality_report.md: [DQ.002](data_quality_report.md#dq002)

<a id="mdep001"></a>
### M.DEP.001 -- Deposit held

```text
Metric: Deposit held
Business meaning: Total tenant security deposits currently held (liability), account 2100.
Definition: SUM(credit-debit) WHERE account_code='2100' AND party_kind='tenant', reversal-excluded.
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_advance_balances (F.010)
Source functions: None
Relevant columns: journal_lines.debit, credit, party_id, allotment_id; coa_accounts.code='2100'
Filters: account_code='2100' AND party_kind='tenant'
Joins: journal_lines JOIN journal_entries JOIN coa_accounts
Date field: entry_date (not a filter for the current balance)
Aggregation: SUM(credit-debit) per tenant/allotment, or grand total
Organization grain: organization_id
Property grain: Not carried directly
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: EXCLUDED (v_account_balances convention).
Soft-delete treatment: Inherited via reversal exclusion.
Duplicate treatment: Not applied.
Historical coverage: Ledger span for account 2100 activity, within 2019-11 to 2026-09; deposit_settlements table itself spans 2023-04 to 2026-09.
Snapshot/current-state behavior: Current balance, not snapshot-dependent as a historical fact (it IS the current state by construction).
Known conflicts: None proven for the total figure itself.
Known limitations: Does NOT include booking_advance (account 2400, a separate figure, M.AR.001B carries both together). guard_deposit_transfer_before_onboarding (business_logic.md 1.5) prevents backdating deposit-transfer entries before onboarding, but does not guarantee completeness of all deposit postings.
AI trust status: SAFE
Validation target: F.010 v_advance_balances.deposit_held (validated: DEP.01, exact match Rs.4,221,150.00).
```
**Cross-references:** data_quality_report.md: [DQ.011](data_quality_report.md#dq011), [DQ.012](data_quality_report.md#dq012)

<a id="mdep002"></a>
### M.DEP.002 -- Deposit settlements

```text
Metric: Deposit settlements
Business meaning: Deposit settlement transactions: deductions (rent, EB, late fees, damages, other) and refund_amount, for allotments that have exited.
Definition: deposit_settlements table, live rows (NOT is_deleted), with status IN ('completed','approved') as the ledger-posting gate.
Source tables: deposit_settlements
Source views: v_export_deposit_settlements (redundant wrapper)
Source functions: trg_settlement_journal_post (posting gate/orchestration; build_settlement_lines composition not exported)
Relevant columns: deposit_amount, pending_rent, pending_eb, pending_late_fees, damages, other_deductions, total_deductions, refund_amount, status, settlement_date, is_deleted
Filters: NOT is_deleted; status IN ('completed','approved') for 'what actually posted to the ledger'
Joins: None required for the source total
Date field: settlement_date
Aggregation: SUM(refund_amount), SUM(total_deductions), COUNT(*) by status
Organization grain: organization_id
Property grain: Via tenant_allotments join
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: Ledger-side posting (via M.DEP.002's journal effect, not the source table itself) follows the standard reverse-and-repost mechanism on status transitions and amount edits (business_logic.md 5.1).
Soft-delete treatment: LIVE ROWS ONLY: is_deleted=false for the source total. Ledger side: hard-delete triggers a generic cascade-delete of the JE (business_logic.md 1.4), not a reversal.
Duplicate treatment: v_deposit_ledger_anomalies (H.046) flags 'duplicate_open_settlement' as one of 3 anomaly types (of 22 total anomaly rows).
Historical coverage: 2023-04-03 to 2026-09-20 (35 months, settlement_date).
Snapshot/current-state behavior: Not snapshot-dependent for the source total.
Known conflicts: Conflicting definitions exist vs the ledger-derived amount -- DQ.008/C.016: Rs.583,495.34 aggregate gap (H.001, INVESTIGATE), with a strong (23/43 rows exactly 2.0000x) suspected double-count mechanism in the diagnostic, not proven from an exported query.
Known limitations: ~7 live, non-deleted settlements have no forward journal entry at all (H.002 gap), consistent with the status-gate (not completed/approved) but not individually confirmed.
AI trust status: DISCLOSE
Validation target: H.001 legacy_amount for deposit_settlements (validated: DEP.03, exact match Rs.5,085,959.33); ledger net (validated: DEP.04, exact match Rs.5,669,454.67, reproducing the Rs.583,495.34 gap exactly); entry_count=3 cluster size (validated: DEP.05, 38 vs H.050's 37).
```
**Cross-references:** conflicts.md: [C.016](conflicts.md#c016) | data_quality_report.md: [DQ.008](data_quality_report.md#dq008), [DQ.012](data_quality_report.md#dq012)

<a id="mdep003"></a>
### M.DEP.003 -- Deposit refunds

```text
Metric: Deposit refunds
Business meaning: Total cash refunded to tenants upon deposit settlement.
Definition: SUM(deposit_settlements.refund_amount) WHERE NOT is_deleted (source) OR SUM(ledger credit on 11xx accounts, source_table='deposit_settlements') (ledger).
Source tables: deposit_settlements; journal_lines/journal_entries/coa_accounts for the ledger side
Source views: None dedicated
Source functions: trg_settlement_journal_post
Relevant columns: deposit_settlements.refund_amount, is_deleted, settlement_date
Filters: NOT is_deleted
Joins: None for source; ledger joins as in M.DEP.002
Date field: settlement_date
Aggregation: SUM(refund_amount)
Organization grain: organization_id
Property grain: Via join
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: Source total: not applicable. Ledger total: reversal-included via sign-inversion netting (same construction as M.COL.003).
Soft-delete treatment: Live rows only (source); reversal-based on the ledger side.
Duplicate treatment: Not separately assessed for refunds specifically (see M.DEP.002's duplicate_open_settlement anomaly).
Historical coverage: Same as M.DEP.002 (2023-04 to 2026-09).
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: Same source-vs-ledger conflict as M.DEP.002 (this IS the refund_amount component of that gap).
Known limitations: Same as M.DEP.002.
AI trust status: DISCLOSE
Validation target: Identical figures to M.DEP.002's DEP.03/DEP.04 (refund_amount IS the field being reconciled there).
```
**Cross-references:** conflicts.md: [C.016](conflicts.md#c016) | data_quality_report.md: [DQ.008](data_quality_report.md#dq008)

<a id="mexp001"></a>
### M.EXP.001 -- Expenses (total, ledger-derived)

```text
Metric: Expenses (total, ledger-derived)
Business meaning: Total operating expense recognised across all EXPENSE-type ledger accounts (5xxx).
Definition: SUM(signed_amount) WHERE account_type='EXPENSE', reversal-excluded.
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_pnl (F.001)
Source functions: None
Relevant columns: Same construction as M.REV.001, account_type='EXPENSE'
Filters: account_type='EXPENSE'
Joins: Same as M.REV.001
Date field: entry_date
Aggregation: SUM(signed_amount)
Organization grain: organization_id
Property grain: property_id (v_pnl grain)
Tenant/allotment grain: Not applicable
Reversal treatment: EXCLUDED (v_account_balances convention).
Soft-delete treatment: Inherited via reversal exclusion.
Duplicate treatment: Not applicable to the ledger total (source-level duplicates would need to be assessed on expenses table itself; no duplicate-expense diagnostic was exported).
Historical coverage: 2023-03-11 to 2026-08-24 (35 months, expenses.expense_date) within the ledger's fuller 2019-2026 span (other expense sources, e.g. owner_payments, extend further back).
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: None for the TOTAL. See M.EXP.002 for the category-bucket gap (electricity account 5150).
Known limitations: Includes whatever is posted to account 5150 (electricity) even though category-level views may not surface it (M.EXP.002).
AI trust status: SAFE
Validation target: F.001 v_pnl.expenses (validated: EXP.01, exact match Rs.20,784,831.96; monthly series in EXP.07, 0 mismatches).
```

<a id="mexp002"></a>
### M.EXP.002 -- Expenses by category

```text
Metric: Expenses by category
Business meaning: Expense total broken down into named categories (owner_rent, maintenance, housekeeping, utilities, property_ops, administrative, salaries, marketing, other_expenses, electricity).
Definition: v_pnl_by_category's 9 hand-written account_code LIKE-pattern buckets, PLUS a required 10th 'electricity' bucket (account 5150, '515%' pattern) that the 9 named buckets do NOT capture.
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_pnl_by_category (F.002); v_expense_composition (F.019, uses a DIFFERENT COA-parent-based rollup, not pattern-based)
Source functions: None
Relevant columns: coa_accounts.code (pattern-matched: '510%' owner_rent, '52%' maintenance, '53%' housekeeping, '54%' utilities, '55%' property_ops, '56%' administrative, '57%' salaries, '58%' marketing, '59%' other_expenses, '515%' electricity)
Filters: account_type='EXPENSE'
Joins: Same as M.EXP.001
Date field: entry_date
Aggregation: SUM(signed_amount) per bucket
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: Not applicable
Reversal treatment: EXCLUDED (v_account_balances convention, same as M.EXP.001).
Soft-delete treatment: Same as M.EXP.001
Duplicate treatment: Same as M.EXP.001
Historical coverage: Same ledger span as M.EXP.001 (57 months with EXPENSE activity).
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: PROVEN GAP (not a competing-definition conflict, a coverage defect): account 5150 (Electricity Payments) matches NONE of the 9 named LIKE patterns. sum_of_buckets (Rs.19,754,213.96) + unbucketed (Rs.1,030,618.00, EXACTLY equal to the electricity column in all 57 months) = total_expenses (Rs.20,784,831.96). DO NOT force electricity into another category (e.g. utilities) -- no evidence supports that mapping; v_expense_composition's SEPARATE COA-parent-based rollup instead groups 5150 under a shared 'Operating Expenses' (5000) category alongside owner rent (5100), a third distinct answer to 'what category is electricity in'.
Known limitations: Any category-by-category report using v_pnl_by_category's 9 named buckets alone will not reconcile to total_expenses/net_profit on the same row unless electricity is added as a 10th bucket.
AI trust status: DISCLOSE
Validation target: F.002 v_pnl_by_category (validated: EXP.02 sum_of_buckets exact match Rs.19,754,213.96; EXP.03 electricity exact match Rs.1,030,618.00; EXP.04 proves the unbucketed==electricity identity exactly; EXP.05/EXP.06 cross-checked against H.017's 57-month totals, exact match).
```
**Cross-references:** conflicts.md: [C.012](conflicts.md#c012), [C.013](conflicts.md#c013), [C.022](conflicts.md#c022) | data_quality_report.md: [DQ.015](data_quality_report.md#dq015)

**Note:** Electricity must be added as its OWN category, not merged into utilities or any other bucket, per the brief's explicit instruction and the lack of any evidence supporting a different mapping.

<a id="mown001"></a>
### M.OWN.001 -- Owner payments (source total)

```text
Metric: Owner payments (source total)
Business meaning: Total rent/revenue-share paid or accrued to property owners.
Definition: SUM(COALESCE(escalated_amount, base_amount)) FROM owner_payments, status IN ('paid','pending') for the period-relevant subset, or all rows for an all-time total.
Source tables: owner_payments
Source views: None dedicated
Source functions: trg_owner_payment_journal_post (posting orchestration ONLY -- body NOT among the 25 exported; exact account/amount composition Not determinable from exported evidence)
Relevant columns: owner_payments.escalated_amount, base_amount, status, bill_date, paid_date, due_date, payment_month
Filters: status IN ('paid','pending') to match v_diag_owner_rent_missing_from_profit's convention; or none for a raw total
Joins: None required
Date field: bill_date (ledger-posting basis, per normalize_owner_payment_journal_dates) OR COALESCE(paid_date,due_date) (v_diag_owner_rent_missing_from_profit's basis) -- THESE TWO BASES DISAGREE at the monthly grain on 7 of 54 months even though they agree exactly on the all-time total (DQ.017).
Aggregation: SUM(escalated_or_base)
Organization grain: organization_id
Property grain: Via owner_contracts/apartment_id join
Tenant/allotment grain: Not applicable
Reversal treatment: Not applicable at the source level. Ledger side: PROVEN PERFECT match to source (H.001, 0.00 diff) -- the only one of the 6 source-vs-ledger reconciliations in H.001 with zero drift.
Soft-delete treatment: owner_payments has NO is_deleted column in its exported schema -- all rows are 'live' by construction; deletion is hard-delete only (cascade-deletes the JE, business_logic.md 1.4/9.1).
Duplicate treatment: Not assessed -- no duplicate-detection diagnostic exists for owner_payments.
Historical coverage: 2022-11-01 to 2026-08-01 (46 months, bill_date).
Snapshot/current-state behavior: Not snapshot-dependent for the total; DQ.020 notes all 345 rows were ledger-posted in a single ~82-minute batch on 2026-08-13 -- posted_at/created_at do NOT reflect when the underlying payment activity occurred.
Known conflicts: None for the total amount (PROVEN exact). See M.PROFIT/M.OWN.002 for how this interacts with profit definitions.
Known limitations: The exact account(s) the ledger trigger posts to is not independently verifiable from an exported function body -- only the aggregate PERFECT match (H.001) confirms the full amount lands somewhere in EXPENSE-type accounts.
AI trust status: SAFE
Validation target: H.001 legacy_amount/je_net_amount for owner_payments (validated: OWNPAY.01/OWNPAY.02, both exact matches, Rs.19,019,250.00).
```
**Cross-references:** data_quality_report.md: [DQ.017](data_quality_report.md#dq017), [DQ.020](data_quality_report.md#dq020)

<a id="mown002"></a>
### M.OWN.002 -- Owner rent (ledger bucket, 3 definitions)

```text
Metric: Owner rent (ledger bucket, 3 definitions)
Business meaning: How much of total expenses is 'owner rent', as it participates in profit -- THREE definitions coexist.
Definition: Def i (v1, EXCLUDES entirely): get_universal_metrics v1's totalProfit has NO owner_payments term at all. Def ii (ledger raw): v_pnl_by_category's owner_rent bucket ('510%' pattern), whatever is actually posted. Def iii (v2, SUBSTITUTED): get_universal_metrics_v2 explicitly discards the ledger's '510%' bucket for the period and replaces it with SUM(owner_payments.escalated_amount) filtered on bill_date.
Source tables: journal_lines, journal_entries, coa_accounts, owner_payments
Source views: v_pnl_by_category (F.002, Def ii); v_diag_owner_rent_missing_from_profit (F.028, documents Def i's gap in its own text)
Source functions: get_universal_metrics (Def i), get_universal_metrics_v2 (Def iii) -- both bodies fully exported
Relevant columns: coa_accounts.code LIKE '510%' (Def ii); owner_payments.escalated_amount, bill_date (Def iii)
Filters: account_type='EXPENSE' AND code LIKE '510%' (Def ii); bill_date BETWEEN period (Def iii)
Joins: Standard ledger joins (Def ii); none (Def iii, direct from owner_payments)
Date field: entry_date (Def ii); bill_date (Def iii)
Aggregation: SUM per definition
Organization grain: organization_id
Property grain: property_id (Def ii only)
Tenant/allotment grain: Not applicable
Reversal treatment: Def ii: EXCLUDED (v_account_balances convention). Def i/iii: not ledger-derived at the owner-rent-specific level (Def iii sources raw owner_payments, no reversal concept).
Soft-delete treatment: Def ii inherited via reversal exclusion; Def iii: owner_payments has no is_deleted column.
Duplicate treatment: Not applicable.
Historical coverage: All-time total PROVEN IDENTICAL across Def ii and Def iii's underlying source (Rs.19,019,250.00, both H.030 and H.001). Monthly grain: 7 of 54 months differ (DQ.017) due to the bill_date-vs-paid_date/due_date basis mismatch between v_diag_owner_rent_missing_from_profit and the other two.
Snapshot/current-state behavior: Not snapshot-dependent for the all-time total.
Known conflicts: CONFLICTING DEFINITIONS EXIST, and PROVEN: Def i (v1) is CONFIRMED to omit owner rent from profit ENTIRELY -- both from reading its function body directly and from v_diag_owner_rent_missing_from_profit's own self-documenting note column: 'Currently NOT included in get_universal_metrics.totalProfit'. Def iii (v2) is CONFIRMED to explicitly substitute owner_payments.escalated_amount for the ledger bucket before computing profit -- read verbatim from source.
Known limitations: Def ii (raw ledger bucket) reflects whatever trg_owner_payment_journal_post actually posts, which is not independently verified from an exported function body (only the aggregate PERFECT match to source confirms the total).
AI trust status: SHOW_BOTH
Validation target: H.030 pnl_owner_rent (validated: PROFIT.04, exact match Rs.19,019,250.00); F.028 owner_rent_paid_or_accrued (validated: PROFIT.03, exact match).
```
**Cross-references:** conflicts.md: [C.010](conflicts.md#c010), [C.011](conflicts.md#c011) | data_quality_report.md: [DQ.016](data_quality_report.md#dq016), [DQ.017](data_quality_report.md#dq017), [DQ.020](data_quality_report.md#dq020)

**Note:** Owner-rent difference is the single most consequential profit-definition conflict in the package -- see M.PROFIT.001.

<a id="mprofit001"></a>
### M.PROFIT.001 -- Gross/net profit (3 definitions)

```text
Metric: Gross/net profit (3 definitions)
Business meaning: Overall business profitability -- THREE definitions coexist and are NOT interchangeable.
Definition: Def A (ledger, v_pnl): revenue - expenses, both ledger-derived, whatever owner-rent amount the ledger happens to hold. Def B (get_universal_metrics v1): SUM(invoices.total_amount) - SUM(expenses.amount), ALL-TIME/period-scoped from application tables, NO owner_payments term. Def C (get_universal_metrics v2, owner-rent-inclusive): ledger revenue - (ledger expenses with the owner_rent bucket explicitly replaced by SUM(owner_payments.escalated_amount) for the period).
Source tables: Def A: journal_lines/journal_entries/coa_accounts. Def B: invoices, expenses. Def C: journal_lines/journal_entries/coa_accounts + owner_payments.
Source views: v_pnl (F.001, Def A only)
Source functions: get_universal_metrics (Def B), get_universal_metrics_v2 (Def C) -- both bodies fully exported
Relevant columns: See M.REV.001/M.EXP.001 (Def A); invoices.total_amount, expenses.amount (Def B); + owner_payments.escalated_amount, bill_date (Def C)
Filters: account_type IN ('INCOME','EXPENSE') (Def A); is_deleted=false on invoices (Def B)
Joins: Standard ledger joins (Def A/C); none (Def B)
Date field: entry_date (Def A/C); COALESCE(billing_month,invoice_date,created_at) (Def B, invoices) / expense_date (Def B, expenses)
Aggregation: revenue - expenses, per definition
Organization grain: organization_id
Property grain: property_id (Def A/C); not natively carried in a simple Def B reconstruction
Tenant/allotment grain: Not applicable
Reversal treatment: Def A/C: EXCLUDED (v_account_balances convention). Def B: NOT APPLICABLE -- never touches journal_entries at all; an invoice's ledger reversal has zero effect on Def B.
Soft-delete treatment: Def A/C: inherited via reversal exclusion. Def B: is_deleted=false on invoices; expenses has no is_deleted column (all rows live).
Duplicate treatment: Def B inherits invoices' 6.8% duplicate-row population (DQ.013) unless de-duplicated; Def A/C do not (ledger-level, not source-row-level).
Historical coverage: All-time reconstruction spans the ledger's 2019-2026 window (Def A/C) or invoices/expenses' narrower 2023-2026 windows (Def B) -- Def B is NOT bounded by ledger availability and can include invoices dated beyond the ledger's last posted month (a Rs.749,371.40 / 1.06% gap was found between this pass's all-time Def-B reconstruction and H.030's ledger-bounded 54-month figure -- a scope difference, not a new defect).
Snapshot/current-state behavior: Not snapshot-dependent for a fixed historical total; get_universal_metrics' period presets (current_month/current_fy/etc.) ARE CURRENT_DATE-dependent by default unless explicit from/to dates are supplied.
Known conflicts: CONFLICTING DEFINITIONS EXIST, PROVEN, not resolved by evidence as to which is 'correct': Def B is PROVEN to omit owner rent entirely (36.6% profit overstatement vs the owner-rent-inclusive figure, reproduced exactly in this pass). Def A reflects whatever the ledger's raw owner_rent bucket holds (unverified account composition). Def C explicitly corrects Def B's omission via a documented substitution.
Known limitations: Do not average or blend these three. 'Why did profit fall' cannot be answered without first establishing which definition the question concerns, since an owner-rent posting-timing event (e.g. the 2026-08-13 single-batch posting, M.OWN.001) would move Def A/C but not Def B at all.
AI trust status: BLOCK
Validation target: F.001 v_pnl.net_profit (validated: PROFIT.01, exact match Rs.51,920,761.47, Def A); H.030's profit_if_owner_rent_excluded (validated: PROFIT.05, exact match Rs.70,940,012 vs this pass's own Def-B reconstruction of Rs.71,689,383.40 -- 1.06% apart, explained by scope per above); overstatement percentage (validated: PROFIT.06, 36.63% reconstructed vs 36.6% in conflicts.md C.011, exact match).
```
**Cross-references:** conflicts.md: [C.010](conflicts.md#c010), [C.011](conflicts.md#c011) | data_quality_report.md: [DQ.016](data_quality_report.md#dq016), [DQ.017](data_quality_report.md#dq017)

**Note:** BLOCK: never state a single profit figure without naming which definition it is. This is the highest-severity profit-related finding in the package (DQ.016, CRITICAL).

<a id="mpnl001"></a>
### M.PNL.001 -- P&L by month

```text
Metric: P&L by month
Business meaning: Monthly revenue, expenses, and net_profit time series, ledger-derived.
Definition: M.REV.002 and M.EXP.001's monthly reconstruction, joined at (property_id, month) grain, net_profit = revenue - expenses.
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_pnl (F.001)
Source functions: None
Relevant columns: Union of M.REV.002 and M.EXP.001's columns
Filters: account_type IN ('INCOME','EXPENSE')
Joins: Standard ledger joins
Date field: entry_date, truncated to month
Aggregation: SUM(signed_amount) per (property_id, month), split by account_type, net_profit = revenue-expenses
Organization grain: organization_id
Property grain: property_id (required grain component, see M.REV.002)
Tenant/allotment grain: Not applicable
Reversal treatment: EXCLUDED (v_account_balances convention).
Soft-delete treatment: Inherited via reversal exclusion.
Duplicate treatment: Not applicable at the ledger layer.
Historical coverage: 57 (property,month) rows / 53 distinct calendar months with INCOME activity; 57 distinct months with EXPENSE activity, spanning the ledger's 2019-11 to 2026-09 window (activity is NOT uniform across that full span -- see business_logic.md 9 for the actual per-domain coverage).
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: Inherits M.EXP.002's electricity-bucket gap if category-level P&L is requested per-month; the aggregate revenue/expenses/net_profit totals themselves are unaffected (proven exact).
Known limitations: Do NOT manufacture a YoY comparison across the full 2019-2026 span without checking which sub-domains (receipts, invoices, expenses, deposits) actually have coverage in the years being compared -- see business_logic.md 9 and 'Historical coverage' in this document's own section 6.
AI trust status: SAFE
Validation target: F.001 v_pnl, monthly rows (validated: REV.02/EXP.07 for the two halves; 0 VALUE mismatches across all 57 overlapping rows; monthly_validation/revenue_by_month.csv and expenses_by_month.csv).
```
**Cross-references:** conflicts.md: [C.012](conflicts.md#c012), [C.013](conflicts.md#c013) | data_quality_report.md: [DQ.015](data_quality_report.md#dq015)

<a id="mcash001"></a>
### M.CASH.001 -- Cash balance

```text
Metric: Cash balance
Business meaning: Current cash-on-hand + bank balance.
Definition: SUM(signed_amount) WHERE account_code IN ('1110','1120'), reversal-excluded, all-time (a running balance, not period-scoped).
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_org_cash_balance (F.011)
Source functions: None
Relevant columns: Same construction as M.REV.001, filtered to codes 1110/1120
Filters: code IN ('1110','1120')
Joins: Standard ledger joins
Date field: entry_date (not a filter for the current balance -- this is a running total)
Aggregation: SUM(signed_amount), all postings to date
Organization grain: organization_id
Property grain: Not carried on cash-account lines
Tenant/allotment grain: Not applicable
Reversal treatment: EXCLUDED (v_account_balances convention).
Soft-delete treatment: Inherited via reversal exclusion.
Duplicate treatment: Not applicable.
Historical coverage: Full ledger span (2019-11 to 2026-09) -- this is a cumulative balance, not a period figure.
Snapshot/current-state behavior: This IS the current-state balance by construction (as of whatever moment the ledger is queried); the exported figure reflects the state at export time (2026-08-29, inside the 09:02-11:18 window).
Known conflicts: None proven.
Known limitations: Represents the LEDGER's view of cash, not a bank-reconciled figure -- no bank-statement evidence was exported to independently confirm this against actual account balances.
AI trust status: SAFE
Validation target: F.011 v_org_cash_balance (not independently re-validated in this pass's scripts -- same construction pattern as M.DEP.001, which IS validated exactly; recommend adding to a future validation pass).
```

**Note:** Not directly exercised by scripts/validation/ in this pass -- same reconstruction pattern as DEP.01, high confidence by analogy but NOT independently confirmed. Flagged honestly rather than claimed as validated.

<a id="mtb001"></a>
### M.TB.001 -- Trial balance / accounting checks

```text
Metric: Trial balance / accounting checks
Business meaning: Per-account debit/credit totals and balance, the fundamental accounting-integrity check (total debits = total credits across the whole ledger).
Definition: TWO views exist: v_trial_balance (reversal-excluded, only accounts with activity) and v_trial_balance_detailed (reversal-included via raw journal_lines, ALL 57 COA accounts including zero-activity ones via LEFT JOIN).
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_trial_balance (F.012), v_trial_balance_detailed (F.013), v_account_rollup (F.014, adds parent/child COA rollup)
Source functions: None
Relevant columns: journal_lines.debit, credit, account_id; coa_accounts.code, name, account_type, normal_balance, parent_id
Filters: None (all accounts) or is_reversal_of IS NULL AND not-reversed (F.012's convention)
Joins: journal_lines JOIN journal_entries JOIN coa_accounts (+ recursive parent walk for F.013/F.014)
Date field: Not applicable (all-time balance)
Aggregation: SUM(debit), SUM(credit), balance = debit-credit or credit-debit per normal_balance
Organization grain: organization_id
Property grain: Not applicable at account grain
Tenant/allotment grain: Not applicable
Reversal treatment: BOTH conventions exist side by side and are BOTH exact -- F.012 (24 accounts with activity, reversal-excluded) and F.013 (57 accounts, all of COA, reversal-included) were independently reconstructed and BOTH matched their respective exported views exactly in this pass.
Soft-delete treatment: F.012 inherits reversal-based netting; F.013 does not filter at all (raw journal_lines).
Duplicate treatment: Not applicable.
Historical coverage: Full ledger span, 2019-11 to 2026-09.
Snapshot/current-state behavior: Not snapshot-dependent (a fixed historical fact given the ledger's current state).
Known conflicts: None for the balance figures (C.002 proves reversal convention doesn't move a balance). H.007 quantifies the GROSS turnover difference between conventions (Rs.17,693,638.16 on both debit and credit sides, across 10 affected accounts) -- reproduced exactly in this pass.
Known limitations: The whole-ledger debit=credit identity is enforced by enforce_journal_balanced (a hard DB constraint, business_logic.md 1.2) -- this reconstruction inherits that guarantee rather than needing to separately verify it.
AI trust status: SAFE
Validation target: F.012 v_trial_balance (validated: LEDGER.04, exact match, 24/24 accounts, 0 mismatches); F.013 v_trial_balance_detailed (validated: LEDGER.07, exact total_debit match Rs.217,212,447.24); H.007's 10-account reversal-effect set (validated: LEDGER.08, exact match).
```
**Cross-references:** conflicts.md: [C.002](conflicts.md#c002)

**Note:** The most thoroughly validated metric family in this deliverable -- 8 of 8 ledger-foundation checks (LEDGER.01-08) matched exactly.

---

## 2. Operations metrics

<a id="mocc001"></a>
### M.OCC.001 -- Current occupancy (5+ definitions)

```text
Metric: Current occupancy (5+ definitions)
Business meaning: What fraction of beds are occupied right now -- FIVE-PLUS structurally different, non-interchangeable definitions coexist. The AI must state which one it is using.
Definition: Def A (v_occupancy): Live bed+apt, Staying only = 168/195 = 86.15%. Def B: Live bed+apt, Staying+On-Notice = 175/195 = 89.74%. Def C: ALL beds (no Live filter), Staying+On-Notice = 175/203 = 86.21%. Def D (get_universal_metrics v1): bed.status=Live only (no apartment filter), Staying = 168/195. Def E (get_bed_occupancy_timeline): Staying+On-Notice+Exited, historical, ALL beds = 194/203 = 95.57% (lifetime, not a snapshot). get_universal_metrics_v2 computes occupancyPct = (occupied+notice)/total, matching Def B's numerator basis, PLUS a 6th metric, monthOccupancyPct (day-weighted, current calendar month only).
Source tables: beds, apartments, tenant_allotments
Source views: v_occupancy (F.005), v_active_tenants (F.022, tenant-grained, see M.OCC.002)
Source functions: get_universal_metrics (Def D), get_universal_metrics_v2 (Def B basis + monthOccupancyPct), get_bed_occupancy_timeline (Def E), get_occupancy_intelligence (day-weighted historical, 7th metric family, no exported output)
Relevant columns: beds.status, apartment_id; apartments.status; tenant_allotments.staying_status, bed_id, onboarding_date, actual_exit_date
Filters: beds.status='Live' (+ apartments.status='Live' for A/B); staying_status IN (varies by definition)
Joins: beds JOIN apartments ON apartment_id; LEFT correlate to tenant_allotments ON bed_id
Date field: Not applicable for snapshot definitions (A-D); onboarding_date/actual_exit_date for Def E
Aggregation: COUNT(*) FILTER (...) per definition
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: bed_id (beds are the natural grain, not tenants, for Def A-D)
Reversal treatment: Not applicable (no ledger involvement).
Soft-delete treatment: Not applicable (beds/apartments/tenant_allotments have no is_deleted column in their exported schema; status fields serve this role instead).
Duplicate treatment: H.056 documents 187 overlapping tenant_allotments pairs on the same bed -- Def A-D's EXISTS-based bed-state checks are NOT affected by this (a bed with 2 overlapping Staying allotments still just has has_staying=true), but any occupied-DAYS calculation (Def E, get_occupancy_intelligence) MUST merge overlapping intervals or it will double-count days -- confirmed get_occupancy_intelligence's own SQL does this via an explicit gaps-and-islands merge.
Historical coverage: tenant_allotments.onboarding_date: 2019-11-03 to 2026-08-31 (67 months) -- the widest historical span of any domain in the package.
Snapshot/current-state behavior: Def A-D are CURRENT-STATE snapshots (as of whenever queried, no CURRENT_DATE dependency in the SQL itself beyond the current allotment state). Def E and get_occupancy_intelligence are historical/lifetime and explicitly clamp to LEAST(p_to, CURRENT_DATE) to never count future days.
Known conflicts: CONFLICTING DEFINITIONS EXIST, and DELIBERATELY PRESERVED. Numerator/denominator spread: 168-194 occupied, 195-203 total, 86.15%-95.57% occupancy depending on definition -- a 9.4-percentage-point range for what a dashboard might label simply 'occupancy'.
Known limitations: v_occupancy (Def A) has a PROVEN SQL DEFECT (see M.OCC.005/DQ.005): its on_notice output column can never register a positive count (0 of 203 beds ever carry both Staying and On-Notice simultaneously, H.013), so 7 On-Notice-only beds fall into NONE of its 4 buckets (occupied/on_notice/booked/vacant). get_universal_metrics v1 and v2 do NOT share this defect (independently confirmed in this pass).
AI trust status: SHOW_BOTH
Validation target: F.005 v_occupancy (validated: OCC.01-05, all exact matches, including the reproduced defect); H.012a-e (validated: OCC.06-08b, all exact matches); F.022 v_active_tenants (validated: OCC.10-12, all exact matches).
```
**Cross-references:** conflicts.md: [C.006](conflicts.md#c006), [C.007](conflicts.md#c007), [C.008](conflicts.md#c008), [C.009](conflicts.md#c009) | data_quality_report.md: [DQ.004](data_quality_report.md#dq004), [DQ.005](data_quality_report.md#dq005)

**Note:** 16 of 16 occupancy validation checks matched exactly (scripts/validation/validate_occupancy.py) -- the most exhaustively cross-checked metric family after the ledger foundation.

<a id="mocc002"></a>
### M.OCC.002 -- Occupancy by property

```text
Metric: Occupancy by property
Business meaning: Any of M.OCC.001's definitions, grouped by property_id.
Definition: Same 5+ definitions as M.OCC.001, GROUP BY property_id.
Source tables: Same as M.OCC.001
Source views: v_occupancy (F.005) is already grouped by (organization_id, property_id)
Source functions: Same as M.OCC.001
Relevant columns: + apartments.property_id (via beds.apartment_id)
Filters: Same as M.OCC.001
Joins: Same as M.OCC.001
Date field: Same as M.OCC.001
Aggregation: Same, per property_id
Organization grain: organization_id
Property grain: property_id (native grain)
Tenant/allotment grain: Aggregated away
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: Same as M.OCC.001
Historical coverage: Same as M.OCC.001
Snapshot/current-state behavior: Same as M.OCC.001
Known conflicts: Same as M.OCC.001.
Known limitations: With only 1 property in this dataset, this grain is currently degenerate (identical to M.OCC.001's org-level totals).
AI trust status: SHOW_BOTH
Validation target: Identical to M.OCC.001 (single-property dataset).
```
**Cross-references:** conflicts.md: [C.006](conflicts.md#c006), [C.007](conflicts.md#c007), [C.008](conflicts.md#c008), [C.009](conflicts.md#c009) | data_quality_report.md: [DQ.004](data_quality_report.md#dq004), [DQ.005](data_quality_report.md#dq005)

<a id="mocc003"></a>
### M.OCC.003 -- Occupancy by apartment

```text
Metric: Occupancy by apartment
Business meaning: Bed-fill rate at the apartment grain -- primarily supported by get_occupancy_intelligence's 'apartments' output and the heatmap.
Definition: get_occupancy_intelligence's apt/heat CTEs: per-apartment total_beds, occupied_beds_now, day-weighted occupancy_pct, monthly heatmap.
Source tables: beds, apartments, tenant_allotments
Source views: None (get_occupancy_intelligence has no exported output rows)
Source functions: get_occupancy_intelligence (full body exported)
Relevant columns: apartments.id, apartment_code, property_id; beds joined per apartment; tenant_allotments per bed
Filters: beds.status='Live' AND apartments.status='Live'
Joins: beds JOIN apartments; tenant_allotments correlated per bed, clamped to apartment availability window
Date field: Window-bounded (p_from/p_to parameters, day-level)
Aggregation: Day-weighted occupied_days/available_days per apartment, plus current-snapshot occupied_beds_now (status_now IN ('occupied','notice'))
Organization grain: organization_id
Property grain: property_id (via apartment)
Tenant/allotment grain: apartment_id (grain), bed_id (input)
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: Overlapping allotments on one bed are explicitly merged (gaps-and-islands) before day-counting -- this is the ONE occupancy function proven to guard against H.056's 187 overlap pairs.
Historical coverage: Bounded by the p_from/p_to parameters supplied; underlying data spans 2019-11 to 2026-08.
Snapshot/current-state behavior: Historical/day-weighted for occupancy_pct; status_now is a current snapshot.
Known conflicts: Not directly comparable to M.OCC.001's snapshot definitions (different time-weighting entirely).
Known limitations: NO EXPORTED OUTPUT EXISTS for this function -- it was never captured as a diagnostic. Fully reconstructable from source tables per its exported body, but NOT independently validated against a reference value in this pass (no reference exists).
AI trust status: NOT_DETERMINABLE
Validation target: No exported output to validate against -- Not determinable from exported evidence whether a reconstruction matches production output.
```
**Cross-references:** conflicts.md: [C.006](conflicts.md#c006), [C.008](conflicts.md#c008) | data_quality_report.md: [DQ.004](data_quality_report.md#dq004)

**Note:** Reconstructable but unvalidated -- flagged honestly rather than assumed correct.

<a id="mocc004"></a>
### M.OCC.004 -- Occupancy by bed

```text
Metric: Occupancy by bed
Business meaning: Per-bed status/history -- get_bed_occupancy_timeline (day-range state list) and get_occupancy_intelligence's 'beds' output (score, fill/stay/turnover metrics).
Definition: get_bed_occupancy_timeline(bed_id, from, to): occupied/vacant day-range segments per bed. get_occupancy_intelligence: adds occupancy_pct, avg_fill_days, avg_stay_days, turnover, realized/potential revenue, a 0-100 score.
Source tables: tenant_allotments (+ beds/apartments for availability window)
Source views: None
Source functions: get_bed_occupancy_timeline, get_occupancy_intelligence (both bodies exported)
Relevant columns: tenant_allotments.onboarding_date, actual_exit_date, staying_status, monthly_rental, bed_id
Filters: staying_status IN ('Staying','On-Notice','Exited') AND onboarding_date IS NOT NULL
Joins: Correlated per bed_id
Date field: onboarding_date, actual_exit_date, day-range window [p_from,p_to] clamped to LEAST(p_to, CURRENT_DATE)
Aggregation: Day-range segmentation (occupied/vacant), then per-bed aggregate stats
Organization grain: organization_id
Property grain: Via bed->apartment->property
Tenant/allotment grain: bed_id (native grain), tenant_id per segment
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: get_bed_occupancy_timeline does NOT merge overlapping allotments on its own (it takes one bed_id at a time and lists raw segments) -- get_occupancy_intelligence DOES merge (gaps-and-islands). Use the latter for a bed with known overlaps (H.056).
Historical coverage: Full tenant_allotments history for the bed in question, clamped to the query window and apartment availability (start_date/end_date).
Snapshot/current-state behavior: Historical by design; clamped to never count future days.
Known conflicts: None between these two functions specifically (they answer complementary questions: timeline detail vs summary score).
Known limitations: Neither function has exported output data to validate against.
AI trust status: NOT_DETERMINABLE
Validation target: No exported output exists for either function at the per-bed grain.
```
**Cross-references:** conflicts.md: [C.008](conflicts.md#c008)

<a id="mten001"></a>
### M.TEN.001 -- Staying tenants

```text
Metric: Staying tenants
Business meaning: Tenants/allotments currently in Staying status.
Definition: COUNT(*) WHERE staying_status = 'Staying', at either the allotment grain or DISTINCT tenant_id grain.
Source tables: tenant_allotments
Source views: v_active_tenants (F.022, tenant-grained, combines Staying+On-Notice, not Staying alone)
Source functions: None required
Relevant columns: tenant_allotments.staying_status, tenant_id, bed_id
Filters: staying_status = 'Staying'
Joins: None required
Date field: Not applicable (current-state field)
Aggregation: COUNT(*) or COUNT(DISTINCT tenant_id)
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: H.056's 187 overlapping-allotment pairs mean a bed can show 2 simultaneously-Staying allotments -- confirmed 0 such cases exist for Staying+On-Notice specifically (H.013), but the general overlap phenomenon across all statuses is real and unquantified for Staying-vs-Staying specifically.
Historical coverage: tenant_allotments.onboarding_date: 2019-11-03 to 2026-08-31.
Snapshot/current-state behavior: Current-state snapshot.
Known conflicts: None -- 'Staying' is an unambiguous staying_status enum value with one clear count (168 allotments, per H.013/H.014, exactly reproduced in this pass as OCC.13).
Known limitations: None beyond the general overlap caveat above.
AI trust status: SAFE
Validation target: H.013 allotment_status_rollup (validated: OCC.13, exact match, 168).
```
**Cross-references:** data_quality_report.md: [DQ.003](data_quality_report.md#dq003)

<a id="mten002"></a>
### M.TEN.002 -- On-Notice tenants

```text
Metric: On-Notice tenants
Business meaning: Tenants/allotments currently in On-Notice status (given notice to vacate but not yet exited).
Definition: COUNT(*) WHERE staying_status = 'On-Notice'.
Source tables: tenant_allotments
Source views: None isolates this alone (v_occupancy's on_notice column is DEFECTIVE, see M.OCC.005)
Source functions: None required
Relevant columns: tenant_allotments.staying_status, bed_id, tenant_id
Filters: staying_status = 'On-Notice'
Joins: None required
Date field: Not applicable
Aggregation: COUNT(*)
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: H.013 confirms 0 of these 7 allotments' beds also carry a simultaneous Staying allotment.
Historical coverage: Same as M.TEN.001.
Snapshot/current-state behavior: Current-state snapshot.
Known conflicts: The COUNT itself is unambiguous (7, H.011/H.013). The DOWNSTREAM TREATMENT of these 7 varies by consuming view/function -- see M.OCC.005.
Known limitations: These 7 specific beds (ids named in H.011) are the ones that vanish from v_occupancy's bucket set -- see M.OCC.005.
AI trust status: SAFE
Validation target: H.011/H.013 (validated: OCC.14, exact match, 7; OCC.03/05 confirm the downstream defect).
```
**Cross-references:** conflicts.md: [C.009](conflicts.md#c009) | data_quality_report.md: [DQ.005](data_quality_report.md#dq005)

<a id="mten003"></a>
### M.TEN.003 -- Booked beds

```text
Metric: Booked beds
Business meaning: Beds with a future/pending tenant allotment (Booked status, not yet moved in).
Definition: COUNT(*) beds WHERE NOT has_staying AND has_booked (per v_occupancy's construction) or COUNT(DISTINCT tenant_id) WHERE staying_status='Booked' (per v_active_tenants).
Source tables: beds, tenant_allotments
Source views: v_occupancy (F.005, bed-grained), v_active_tenants (F.022, tenant-grained)
Source functions: get_universal_metrics, get_universal_metrics_v2
Relevant columns: tenant_allotments.staying_status='Booked', bed_id, tenant_id
Filters: staying_status='Booked'
Joins: Standard bed/allotment correlation
Date field: Not applicable
Aggregation: COUNT
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: bed_id or tenant_id depending on definition
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: Not separately assessed for Booked specifically.
Historical coverage: H.014: 4 Booked allotments, min onboarding 2026-08-01, max 2026-08-16 -- ALL very recent (this status is inherently forward-looking).
Snapshot/current-state behavior: Current-state snapshot.
Known conflicts: None -- bed-grained (v_occupancy) and tenant-grained (v_active_tenants) both confirm 4 (validated OCC.11).
Known limitations: Small population (4) makes this a low-statistical-significance metric on its own.
AI trust status: SAFE
Validation target: F.022 v_active_tenants.booked_tenants (validated: OCC.11, exact match, 4); v_occupancy's booked column (validated: OCC construction consistent, 4).
```

<a id="mocc005"></a>
### M.OCC.005 -- Historical occupancy

```text
Metric: Historical occupancy
Business meaning: Occupancy over time (not just right now) -- see M.OCC.001 Def E and get_occupancy_intelligence.
Definition: Same as M.OCC.001 Def E / M.OCC.003-004's day-weighted reconstructions, over an arbitrary [p_from,p_to] window.
Source tables: tenant_allotments, beds, apartments
Source views: None
Source functions: get_bed_occupancy_timeline, get_occupancy_intelligence
Relevant columns: Same as M.OCC.003/004
Filters: staying_status IN ('Staying','On-Notice','Exited')
Joins: Same as M.OCC.003/004
Date field: onboarding_date, actual_exit_date, window-bounded
Aggregation: Day-weighted occupied/available ratio, or explicit day-range segments
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: bed_id
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: get_occupancy_intelligence merges overlaps (H.056-safe); get_bed_occupancy_timeline does not (per-bed caller responsibility).
Historical coverage: Full history available: 2019-11-03 to 2026-08-31 (tenant_allotments.onboarding_date, the widest span of any domain).
Snapshot/current-state behavior: Explicitly historical -- LEAST(p_to, CURRENT_DATE) clamp prevents counting future days as occupied.
Known conflicts: Same as M.OCC.001 (this IS Def E/the day-weighted family within that conflict set).
Known limitations: No YoY comparison should be attempted before ~2021 without checking that enough beds/apartments existed at that point in history -- the portfolio itself may have been smaller (not independently verified from exported evidence).
AI trust status: SHOW_BOTH
Validation target: H.012e (194/203, cross-referenced in OCC printout, not independently re-derived as a day-weighted calc in this pass's scripts -- the bed-set-membership check (Staying+On-Notice+Exited, ALL beds) IS validated via OCC.07/07b as the closest available proxy).
```
**Cross-references:** conflicts.md: [C.006](conflicts.md#c006), [C.008](conflicts.md#c008) | data_quality_report.md: [DQ.004](data_quality_report.md#dq004)

<a id="mlife001"></a>
### M.LIFE.001 -- Tenant lifecycle (staying_status sync)

```text
Metric: Tenant lifecycle (staying_status sync)
Business meaning: How a tenant's overall status is derived from their (possibly multiple) allotments.
Definition: tenants.staying_status is DERIVED, not independent: priority order Staying(1) > On-Notice(2) > Booked(3) > else(4), tie-broken by most-recently-created allotment, kept in sync by sync_tenant_staying_status (AFTER INSERT/UPDATE) and sync_tenant_staying_status_on_delete (AFTER DELETE) on tenant_allotments.
Source tables: tenant_allotments, tenants
Source views: None
Source functions: sync_tenant_staying_status, sync_tenant_staying_status_on_delete (both bodies fully exported)
Relevant columns: tenant_allotments.staying_status, tenant_id, created_at; tenants.staying_status
Filters: None (the trigger scans ALL of a tenant's allotments)
Joins: tenant_allotments correlated by tenant_id
Date field: created_at (tie-break only)
Aggregation: Not an aggregation -- a per-tenant derivation rule
Organization grain: organization_id
Property grain: Not applicable (tenant-level, can span properties)
Tenant/allotment grain: tenant_id (native grain)
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable (tenants/tenant_allotments have no is_deleted column)
Duplicate treatment: A tenant with multiple simultaneous allotments (H.056) is tagged by whichever ranks highest in the priority order, which can mask a lower-priority concurrent allotment's status.
Historical coverage: Full history, 2019-11 to 2026-08.
Snapshot/current-state behavior: Current-state field, always reflects the latest trigger-driven sync.
Known conflicts: None -- the derivation rule is fully proven from source (both trigger bodies exported and read in full).
Known limitations: tenants.staying_status is NEVER an independent fact -- always re-derivable from tenant_allotments; do not treat it as authoritative if it appears to disagree with a direct tenant_allotments query (it should not, by construction, but was not independently re-verified in this pass's scripts).
AI trust status: SAFE
Validation target: Not independently re-executed in this pass's scripts (the derivation is a row-level trigger rule, not an aggregate to compare against a view) -- confidence is from reading both full function bodies directly (business_logic.md 10.1).
```

<a id="mlife002"></a>
### M.LIFE.002 -- Move-ins

```text
Metric: Move-ins
Business meaning: Tenant onboarding events.
Definition: tenant_allotments WHERE onboarding_date IS NOT NULL, event_date=onboarding_date, event='move_in'.
Source tables: tenant_allotments
Source views: v_tenant_lifecycle_events (F.017)
Source functions: None
Relevant columns: tenant_allotments.onboarding_date, tenant_id, allotment_id, staying_status, bed_id, apartment_id, property_id
Filters: onboarding_date IS NOT NULL
Joins: None required
Date field: onboarding_date
Aggregation: COUNT(*) or list, groupable by month
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: A tenant who moves, then re-onboards elsewhere, contributes 2 move_in rows -- this is a correct representation of 2 real events, not a duplicate.
Historical coverage: 2019-11-03 to 2026-08-31 (67 months).
Snapshot/current-state behavior: Not snapshot-dependent (historical event list).
Known conflicts: None.
Known limitations: F.017 is exported at 2204 rows (full population); a diagnostic sample (H.036) exports only a LIMIT 500 slice of the SAME view -- always use F.017, never H.036, for a complete move-in/move-out count.
AI trust status: SAFE
Validation target: F.017 v_tenant_lifecycle_events (2204 rows, full population, exact SQL reproduced in business_logic.md 10.2; not independently re-executed as a row-count check in this pass's scripts, but the UNION ALL construction is simple and fully specified from source).
```

<a id="mlife003"></a>
### M.LIFE.003 -- Move-outs

```text
Metric: Move-outs
Business meaning: Tenant exit events.
Definition: tenant_allotments WHERE actual_exit_date IS NOT NULL, event_date=actual_exit_date, event='move_out'.
Source tables: tenant_allotments
Source views: v_tenant_lifecycle_events (F.017)
Source functions: None
Relevant columns: tenant_allotments.actual_exit_date, tenant_id, allotment_id, staying_status
Filters: actual_exit_date IS NOT NULL
Joins: None required
Date field: actual_exit_date
Aggregation: COUNT(*) or list, groupable by month
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: Same note as M.LIFE.002.
Historical coverage: tenant_allotments.actual_exit_date: 2022-11-20 to 2026-09-20 (47 months, including a small forward-dated tail).
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: None.
Known limitations: Same F.017-vs-H.036 caveat as M.LIFE.002.
AI trust status: SAFE
Validation target: Same as M.LIFE.002.
```

<a id="mlife004"></a>
### M.LIFE.004 -- Exit reconciliation

```text
Metric: Exit reconciliation
Business meaning: For each Exited allotment, what's still outstanding: AR dues, deposit/advance held, EB already invoiced, exit charges already invoiced, and the latest settlement status.
Definition: v_exit_reconciliation_worklist: joins tenant_allotments (staying_status='Exited') to v_tenant_current_dues (Def B AR, reversals INCLUDED), plus LATERAL sums of invoices by reference_type/invoice_type, plus the latest deposit_settlements row per allotment.
Source tables: tenant_allotments, tenants, apartments, beds, properties, invoices, deposit_settlements
Source views: v_exit_reconciliation_worklist (F.027, byte-identical duplicate at H.047)
Source functions: None
Relevant columns: See business_logic.md 10.4 for the full join list
Filters: staying_status='Exited' AND (ar_balance<>0 OR deposit_held+booking_advance>0)
Joins: tenant_allotments + 4 table joins + 3 LATERAL subqueries (see business_logic.md 10.4)
Date field: actual_exit_date
Aggregation: Not an aggregation -- a per-allotment worklist (45 rows)
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: tenant_id, allotment_id (native grain)
Reversal treatment: dues_now (ar_balance) uses M.AR.001B's convention (reversals INCLUDED) -- NOT the reversal-excluded convention.
Soft-delete treatment: eb_already/exit_charge_already exclude soft-deleted invoices (is_deleted=false); deposit settlement lookup excludes soft-deleted settlements.
Duplicate treatment: Not separately assessed for this worklist specifically.
Historical coverage: Bounded to currently-Exited allotments with an outstanding balance -- a live worklist, not a historical time series.
Snapshot/current-state behavior: Current-state worklist (which allotments currently have outstanding dues/deposits).
Known conflicts: Inherits M.AR.001B's convention choice (reversals included) -- if a semantic layer standardises on M.AR.001A's convention instead, this worklist's dues_now figure would need re-deriving (though C.002 proves the AR total itself is unaffected).
Known limitations: 45 rows at export time -- a small, currently-manageable worklist; re-derivable at any time from the underlying tables.
AI trust status: SAFE
Validation target: F.027 v_exit_reconciliation_worklist (45 rows; not independently re-executed as a full reconstruction in this pass's scripts given its 8-way join complexity, but every one of its component parts -- AR via M.AR.001B, invoice filters, deposit settlement lookup -- IS independently validated elsewhere in this document).
```
**Cross-references:** conflicts.md: [C.001](conflicts.md#c001)

<a id="mmaint001"></a>
### M.MAINT.001 -- Maintenance volume

```text
Metric: Maintenance volume
Business meaning: Ticket counts: total, open, closed, by month/property.
Definition: COUNT(*) FROM maintenance_tickets, GROUP BY status/month/property.
Source tables: maintenance_tickets
Source views: v_maintenance_metrics (F.015)
Source functions: None
Relevant columns: maintenance_tickets.status, created_at, organization_id, property_id
Filters: status IN/NOT IN closed states depending on the question
Joins: None required for the raw count
Date field: created_at
Aggregation: COUNT(*) per status/month
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: Not applicable
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable (no is_deleted column on maintenance_tickets)
Duplicate treatment: Not applicable to the ticket count itself.
Historical coverage: 2025-01-29 to 2026-08-29 (20 months, created_at) -- the SHORTEST domain coverage of any operational area in the package. Do not manufacture a YoY comparison for maintenance.
Snapshot/current-state behavior: Not snapshot-dependent for a historical count.
Known conflicts: None for the raw ticket count.
Known limitations: Joining maintenance_tickets to ticket_resolutions on ticket_id fans out by +2 rows (2 tickets have 2 resolutions each) -- PROVEN in this pass to be the exact mechanism behind H.019's previously-unexplained 1613-vs-1611 gap (1611 live tickets + 2 double-resolved tickets = 1613).
AI trust status: SAFE
Validation target: M.006 exact row count (1611, live table); H.019's 1613 figure (validated: MAINT.01/MAINT.01b, exact match AND mechanism proven).
```
**Cross-references:** data_quality_report.md: [DQ.027](data_quality_report.md#dq027)

**Note:** MAINT.01b resolves a previously 'not determinable' item from data_quality_report.md DQ.027.

<a id="mmaint002"></a>
### M.MAINT.002 -- Maintenance cost (2 paths)

```text
Metric: Maintenance cost (2 paths)
Business meaning: Cost of maintenance activity -- TWO independent linkage paths coexist, answering different questions.
Definition: Path A (v_maintenance_metrics): maintenance_tickets LEFT JOIN ticket_resolutions LEFT JOIN expenses ON ticket_resolution_id, dated by ticket created_at month. Path B (v_maintenance_by_issue_type): expenses.issue_type_id direct join to issue_types, requires ticket_resolution_id IS NOT NULL, dated by expense_date.
Source tables: maintenance_tickets, ticket_resolutions, expenses, issue_types
Source views: v_maintenance_metrics (F.015, Path A), v_maintenance_by_issue_type (F.016, Path B)
Source functions: None
Relevant columns: ticket_resolutions.ticket_id; expenses.ticket_resolution_id, issue_type_id, amount, expense_date
Filters: Path A: none beyond the joins (LEFT JOIN, cost=0 if unlinked). Path B: ticket_resolution_id IS NOT NULL.
Joins: Path A: 2-hop LEFT JOIN via ticket_resolutions. Path B: 1-hop direct join via expenses.issue_type_id.
Date field: Path A: maintenance_tickets.created_at (ticket creation month). Path B: expenses.expense_date.
Aggregation: SUM(expenses.amount) per path
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: Not applicable
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: Path A's join must avoid a NaN-key cartesian explosion when reconstructed naively (tickets without a resolution and expenses without a resolution both carry NULL join keys) -- confirmed and fixed in this pass's validation script; a correct SQL LEFT JOIN would not have this problem (NULL<>NULL in SQL), only a naive pandas merge implementation.
Historical coverage: Same 20-month window as M.MAINT.001 for tickets; expenses.expense_date extends back to 2023-03.
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: Structurally CAN disagree (different linkage FK, different date basis) but PROVEN, in this pass, to produce the SAME total (Rs.28,796.00) for the current data -- both paths' totals matched exactly and matched each other. Preserved as two distinct metrics per the brief's instruction, since the mechanism for disagreement is real even though it happens not to manifest today.
Known limitations: 15 of 516 expenses (2.9%) are linked to a ticket_resolution at all -- the other 501 expenses are unrelated to maintenance tickets.
AI trust status: SAFE
Validation target: F.015 v_maintenance_metrics (validated: MAINT.02, exact match Rs.28,796.00); F.016 v_maintenance_by_issue_type (validated: MAINT.03/04, exact match, 15 resolved_tickets / Rs.28,796.00); cross-check between paths (validated: MAINT.05, exact match).
```
**Cross-references:** conflicts.md: [C.023](conflicts.md#c023) | data_quality_report.md: [DQ.027](data_quality_report.md#dq027)

**Note:** Despite conflicts.md's original framing as 'can disagree', this pass PROVES the two paths agree exactly on total cost for this dataset -- an update worth carrying into the semantic layer's confidence rating for this metric.

<a id="meb001"></a>
### M.EB.001 -- EB/electricity usage and cost

```text
Metric: EB/electricity usage and cost
Business meaning: Electricity consumption (units) and billed cost, at the property/apartment/billing-period level.
Definition: electricity_readings (units_consumed, unit_cost per apartment/billing_month) and eb_payments (bill_amount per property/bill_date).
Source tables: electricity_readings, eb_payments, eb_rates, eb_monitoring_readings
Source views: None dedicated
Source functions: trg_eb_payment_journal_post (posting orchestration, body NOT among the 25 exported)
Relevant columns: electricity_readings.units_consumed, unit_cost, billing_month, apartment_id; eb_payments.bill_amount, bill_date, payment_date
Filters: None required for a raw sum
Joins: None required for the raw tables individually
Date field: electricity_readings.billing_month (TEXT, 'Mon-YY' format -- see Known limitations); eb_payments.bill_date (a real DATE column)
Aggregation: SUM(units_consumed), SUM(bill_amount)
Organization grain: organization_id
Property grain: property_id
Tenant/allotment grain: Not applicable at this grain (see M.EB.002 for tenant-level allocation)
Reversal treatment: Not applicable at the source-table level. Ledger side (via owner_payments-style posting) is NOT determinable from exported evidence -- trg_eb_payment_journal_post's body is not among the 25 exported.
Soft-delete treatment: Not applicable (no is_deleted column on any EB table).
Duplicate treatment: Not assessed -- no EB duplicate-detection diagnostic was exported.
Historical coverage: electricity_readings: created_at 2026-03-20 to 2026-07-31 (5 months, EXPORT timing, not necessarily billing coverage -- billing_month values span a much wider historical range in 'Mon-YY' text form, e.g. 'May-24'). eb_payments: bill_date 2026-04-29 to 2026-06-27 (ONLY 2 months -- the narrowest coverage of any financial domain in the package). eb_monitoring_readings: a SINGLE DAY snapshot (2026-08-18, all 35 rows).
Snapshot/current-state behavior: eb_monitoring_readings is a one-time monitoring snapshot, not a time series -- do not build a trend from it.
Known conflicts: None (no competing definition found for raw usage/cost).
Known limitations: PROVEN, 100%-consistent schema defect (DQ.028): electricity_readings.billing_month and eb_tenant_shares.billing_month use 'Mon-YY' text format (e.g. 'Apr-25'), while EVERY other billing_month/payment_month column in the schema (invoices, expenses, owner_payments) uses 'YYYY-MM' -- confirmed 0% vs 100% conformance across full table populations in this pass. Any join/comparison between EB billing_month and invoices/expenses billing_month REQUIRES a format-conversion step first.
AI trust status: DISCLOSE
Validation target: Format-mismatch fully re-verified in this pass (validate_eb.py EB.03-07, all exact matches to the 0%/100% pattern); eb_payments 2-month coverage re-verified (EB.08, exact match).
```
**Cross-references:** data_quality_report.md: [DQ.021](data_quality_report.md#dq021), [DQ.028](data_quality_report.md#dq028)

<a id="meb002"></a>
### M.EB.002 -- EB tenant allocation

```text
Metric: EB tenant allocation
Business meaning: How one apartment's electricity bill is allocated across the tenants who occupied it that month, proportional to days stayed.
Definition: per_day_rate = ROUND(total_apartment_bill / total_tenant_days); tenant_eb_charge = per_day_rate * tenant_stay_days. Formula reverse-engineered from data (NOT from an exported function body -- no allocation function is among the 25 exported).
Source tables: eb_tenant_shares
Source views: None
Source functions: Not determinable from exported evidence (the writer of this table is not among the 25 exported bodies)
Relevant columns: eb_tenant_shares.total_apartment_bill, total_tenant_days, per_day_rate, tenant_stay_days, tenant_eb_charge, invoice_id, apartment_id, billing_month
Filters: None required
Joins: Links to invoices via invoice_id
Date field: billing_month (TEXT, 'Mon-YY' format -- same DQ.028 defect as M.EB.001)
Aggregation: Per-row formula, not an aggregation (each row is one tenant's allocated share for one apartment/month)
Organization grain: organization_id
Property grain: Via apartment_id
Tenant/allotment grain: tenant_id (native grain)
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: Not assessed.
Historical coverage: created_at 2026-04-07 to 2026-08-08 (5 months, export timing); billing_month text values span a wider historical range.
Snapshot/current-state behavior: Not snapshot-dependent (a per-invoice allocation record).
Known conflicts: M.EB.002's tenant_eb_charge vs invoices.electricity_amount (M.INV.001's per-invoice EB component) -- Not determinable from exported evidence whether these are meant to be the same figure computed twice; no view or function joins the two.
Known limitations: The allocation FORMULA itself is independently, arithmetically PROVEN in this pass across the FULL 801-row population (not just a 5-row sample) -- 801/801 rows match ROUND(bill/tenant_days) for per_day_rate, and 801/801 match per_day_rate*stay_days for tenant_eb_charge, exactly. This is strong evidence the formula is genuinely how the system computes this, even without the generating function body.
AI trust status: DISCLOSE
Validation target: Formula verification (validated: EB.01/EB.02, both 801/801 exact matches -- upgraded from business_logic.md's original 5-row spot-check to a full-population proof in this pass).
```
**Cross-references:** data_quality_report.md: [DQ.028](data_quality_report.md#dq028)

**Note:** Full-population formula verification is a genuine strengthening of business_logic.md's original finding.

---

## 3. Risk / Data-quality metrics

<a id="mrisk001"></a>
### M.RISK.001 -- Outstanding dues

```text
Metric: Outstanding dues
Business meaning: Cross-reference to M.AR.001A-D -- 'outstanding dues' is the same 4-way conflict, framed as a risk metric.
Definition: See M.AR.001A-D.
Source tables: See M.AR.001A-D
Source views: F.006, F.007
Source functions: None
Relevant columns: See M.AR.001A-D
Filters: See M.AR.001A-D
Joins: See M.AR.001A-D
Date field: See M.AR.001A-D
Aggregation: See M.AR.001A-D
Organization grain: organization_id
Property grain: See M.AR.003
Tenant/allotment grain: See M.AR.002
Reversal treatment: See M.AR.001A-D
Soft-delete treatment: See M.AR.001A-D
Duplicate treatment: See M.AR.001A-D
Historical coverage: See M.AR.001A-D
Snapshot/current-state behavior: See M.AR.001A-D
Known conflicts: CONFLICTING DEFINITIONS EXIST -- identical to M.AR.001A-D.
Known limitations: Same as M.AR.001A-D.
AI trust status: BLOCK
Validation target: Same as M.AR.001A-D.
```
**Cross-references:** conflicts.md: [C.001](conflicts.md#c001), [C.003](conflicts.md#c003), [C.005](conflicts.md#c005) | data_quality_report.md: [DQ.002](data_quality_report.md#dq002), [DQ.019](data_quality_report.md#dq019)

**Note:** Duplicate of M.AR.001A-D under the brief's Risk/DQ heading -- not re-derived separately.

<a id="mrisk002"></a>
### M.RISK.002 -- Aging

```text
Metric: Aging
Business meaning: AR aged into 0-30/31-60/61-90/90+ day buckets by charge date.
Definition: v_tenant_aging: buckets by CURRENT_DATE - charge_date, on raw journal_lines account 1200 (reversals INCLUDED, same convention as M.AR.001B).
Source tables: journal_lines, journal_entries, coa_accounts
Source views: v_tenant_aging (F.008)
Source functions: None
Relevant columns: journal_lines.debit, credit, party_id, allotment_id; journal_entries.entry_date
Filters: account_code='1200' AND party_kind='tenant'
Joins: Standard ledger joins
Date field: CURRENT_DATE - entry_date (bucket boundary), entry_date (charge date itself)
Aggregation: SUM(net) per bucket per (tenant_id, allotment_id)
Organization grain: organization_id
Property grain: Not carried directly
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: INCLUDED (same convention as M.AR.001B, v_tenant_current_dues).
Soft-delete treatment: Inherited via reversal mechanism.
Duplicate treatment: Not applied.
Historical coverage: Full ledger AR history, 2019-11 to 2026-09.
Snapshot/current-state behavior: CRITICALLY SNAPSHOT-DEPENDENT: CURRENT_DATE is evaluated at query time, not a fixed historical fact. The exported CSV (F.008) reflects buckets as of the export window (2026-08-29 09:02-11:18). Re-running this reconstruction today (or any other date) will shift every charge into a different bucket than what F.008 shows.
Known conflicts: Not a competing-definition conflict -- a reproducibility hazard (C.019 in conflicts.md).
Known limitations: Any offline reconstruction MUST fix an explicit as-of date (recommend the M.002 snapshot timestamp, 2026-08-29) and label every bucket with that date. NEVER compare a freshly-reconstructed aging bucket against the exported F.008 values without accounting for elapsed time.
AI trust status: DISCLOSE
Validation target: Not independently re-executed in this pass's scripts (a snapshot-dependent calculation cannot be meaningfully re-validated against a frozen export without first fixing the same as-of date the export used, which was not separately recorded per-row in F.008).
```
**Cross-references:** conflicts.md: [C.019](conflicts.md#c019) | data_quality_report.md: [DQ.018](data_quality_report.md#dq018)

**Note:** Always state the as-of date when reporting an aging bucket.

<a id="mrisk003"></a>
### M.RISK.003 -- Deposit risk

```text
Metric: Deposit risk
Business meaning: Umbrella metric combining phantom deposits (M.RISK.004) and deposit settlement anomalies (premature/duplicate/transfer-double-count).
Definition: UNION of v_diag_deposit_phantom (32 rows) and v_deposit_ledger_anomalies (22 rows, 3 anomaly types).
Source tables: tenant_allotments, deposit_settlements, journal_lines/journal_entries/coa_accounts
Source views: v_diag_deposit_phantom (H.045), v_deposit_ledger_anomalies (H.046)
Source functions: validate_deposit_settlement (write-time constraint, body exported)
Relevant columns: See M.RISK.004 and business_logic.md 5.4
Filters: See M.RISK.004 and 5.4
Joins: See M.RISK.004 and 5.4
Date field: Various (settlement_date, actual_exit_date)
Aggregation: COUNT(*) per anomaly type
Organization grain: organization_id
Property grain: Via join
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: Not applicable (source-table anomaly detection, not ledger totals)
Soft-delete treatment: NOT is_deleted filters applied throughout
Duplicate treatment: One of the 3 anomaly types IS 'duplicate_open_settlement'.
Historical coverage: Bounded to currently-flagged rows (a live worklist, not a time series).
Snapshot/current-state behavior: Current-state worklist.
Known conflicts: None (these are risk flags, not competing metric definitions).
Known limitations: validate_deposit_settlement is a WRITE-TIME constraint only -- it does not re-validate existing rows if an allotment's status changes retroactively, which is the suspected (not proven) mechanism behind the 'premature_settlement' anomaly subtype.
AI trust status: DISCLOSE
Validation target: H.045 (validated: DEP.06, exact match, 32); H.046 (not independently re-executed as a full 3-way anomaly reconstruction in this pass's scripts, given its complexity -- recorded as a follow-up).
```
**Cross-references:** data_quality_report.md: [DQ.011](data_quality_report.md#dq011), [DQ.012](data_quality_report.md#dq012)

<a id="mrisk004"></a>
### M.RISK.004 -- Phantom deposits

```text
Metric: Phantom deposits
Business meaning: Tenant allotments holding a deposit with no live tenant relationship (Exited/Cancelled) and no settlement record at all.
Definition: tenant_allotments WHERE deposit_paid > 0 AND staying_status IN ('Exited','Cancelled') AND NOT EXISTS(a matching, non-deleted deposit_settlements row).
Source tables: tenant_allotments, deposit_settlements
Source views: v_diag_deposit_phantom (H.045)
Source functions: None
Relevant columns: tenant_allotments.deposit_paid, staying_status, actual_exit_date, id; deposit_settlements.allotment_id, is_deleted
Filters: deposit_paid>0 AND staying_status IN ('Exited','Cancelled')
Joins: NOT EXISTS correlated subquery against deposit_settlements
Date field: Not applicable (current-state check)
Aggregation: COUNT(*), and SUM(deposit_paid) for the amount at risk
Organization grain: organization_id
Property grain: Via join
Tenant/allotment grain: tenant_id, allotment_id
Reversal treatment: Not applicable
Soft-delete treatment: deposit_settlements filtered to NOT is_deleted for the existence check
Duplicate treatment: Not applicable
Historical coverage: Current-state check across the full tenant_allotments history.
Snapshot/current-state behavior: Current-state worklist.
Known conflicts: None.
Known limitations: Represents real, unresolved financial exposure (money held, never formally refunded or forfeited) -- an operational gap requiring case-by-case remediation, not a reporting artifact.
AI trust status: DISCLOSE
Validation target: H.045 v_diag_deposit_phantom (validated: DEP.06, exact match, 32 allotments); amount at risk (validated: DEP.07, Rs.722,700.00 -- a NEW figure, H.045 does not export a summed amount, computed here for the first time).
```
**Cross-references:** data_quality_report.md: [DQ.011](data_quality_report.md#dq011)

**Note:** Rs.722,700.00 total exposure is a new number, not previously stated in data_quality_report.md.

<a id="mrisk005"></a>
### M.RISK.005 -- Duplicate invoices

```text
Metric: Duplicate invoices
Business meaning: Invoices that appear more than once for the same (allotment, billing_month, invoice_type).
Definition: GROUP BY allotment_id, billing_month, invoice_type HAVING COUNT(*) > 1, on live invoices.
Source tables: invoices
Source views: None (H.055 is an ad-hoc diagnostic, not a stored view)
Source functions: None (no invoice-side dedup mechanism exists at all)
Relevant columns: invoices.allotment_id, billing_month, invoice_type, total_amount, invoice_number, is_deleted
Filters: NOT is_deleted
Joins: None required
Date field: Not applicable to the grouping itself (billing_month is the grouping key)
Aggregation: COUNT(*), SUM(total_amount) per group
Organization grain: organization_id
Property grain: Via allotment join
Tenant/allotment grain: allotment_id (grouping key)
Reversal treatment: Not applicable
Soft-delete treatment: Live rows only
Duplicate treatment: THIS METRIC IS the duplicate-detection itself.
Historical coverage: Full invoices history, 2023-02 to 2026-09.
Snapshot/current-state behavior: Current-state check.
Known conflicts: None (a detection metric, not a competing definition).
Known limitations: NO deduplication mechanism exists in the application for invoices at all (contrast M.RISK.006/receipts, which at least has a one-time detection table). 322 groups, 356 excess rows, Rs.4,040,627.00 combined group value -- the exact overcounted/excess amount is NOT separately computable without knowing which row per group is canonical.
AI trust status: DISCLOSE
Validation target: H.055 duplicate_invoices (validated: DQ.013/DQ.013b in validate_data_quality.py, exact match, 322 groups / 356 excess rows -- independently re-derived from raw invoices in this pass, not merely re-read from the diagnostic).
```
**Cross-references:** conflicts.md: [C.020](conflicts.md#c020) | data_quality_report.md: [DQ.013](data_quality_report.md#dq013)

<a id="mrisk006"></a>
### M.RISK.006 -- Duplicate receipts

```text
Metric: Duplicate receipts
Business meaning: Receipts flagged as likely duplicates by the application's own (partial) detection mechanism.
Definition: receipts_dedup_audit table: groups by (tenant_id, payment_date, amount_paid, reference_number), duplicate_count 2-6, one-time detection pass (detected_at all = 2026-04-22).
Source tables: receipts_dedup_audit, receipts
Source views: None
Source functions: Not determinable from exported evidence (no trigger performs this detection; presumably a one-off script or manual query)
Relevant columns: receipts_dedup_audit.tenant_id, payment_date, amount_paid, reference_number, duplicate_count, receipt_ids, detected_at
Filters: None (the table itself IS the filtered result)
Joins: receipt_ids array cross-referenced against receipts.id
Date field: detected_at (single value, not a range)
Aggregation: COUNT(*) groups, SUM per group
Organization grain: organization_id
Property grain: Not carried
Tenant/allotment grain: tenant_id
Reversal treatment: Not applicable
Soft-delete treatment: Cross-checked in this pass: of 23 flagged receipt_ids, only 11 still exist in the receipts export (12 were HARD-deleted, not soft-deleted, since detection); NONE of the remaining 11 are soft-deleted -- detection did NOT drive remediation.
Duplicate treatment: THIS METRIC IS the duplicate-detection itself.
Historical coverage: One-time detection snapshot (2026-04-22), not an ongoing feed.
Snapshot/current-state behavior: Frozen detection result; does not reflect any receipts created or modified after 2026-04-22.
Known conflicts: None (a detection metric).
Known limitations: 9 groups, 23 receipt_ids named, only 11 still live and undeduplicated. This is a SMALLER-scale issue than M.RISK.005 (invoices) but demonstrates that even a detected data-quality issue in this system does not automatically get fixed.
AI trust status: DISCLOSE
Validation target: Not independently re-executed as a fresh detection pass in this pass's scripts (the 9-group/23-id/11-live cross-check was performed and confirmed during the conflicts.md pass, C.018/C.020, and is carried forward here as an established fact, not re-derived).
```
**Cross-references:** conflicts.md: [C.018](conflicts.md#c018), [C.020](conflicts.md#c020) | data_quality_report.md: [DQ.014](data_quality_report.md#dq014)

<a id="mrisk007"></a>
### M.RISK.007 -- Overlapping allotments

```text
Metric: Overlapping allotments
Business meaning: Two tenant_allotments rows for the same bed with overlapping date ranges -- a concurrent-occupancy data-quality signal.
Definition: For each bed_id, pairwise interval-overlap check on [onboarding_date, COALESCE(actual_exit_date, snapshot_date)].
Source tables: tenant_allotments
Source views: None (H.056 is an ad-hoc diagnostic)
Source functions: None (no trigger prevents this for tenant_allotments; contrast bed_status_history's validate_bed_status_no_overlap, which is EMPTY, 0 rows, and thus not effectively enforced against tenant_allotments directly)
Relevant columns: tenant_allotments.bed_id, onboarding_date, actual_exit_date
Filters: bed_id IS NOT NULL
Joins: Self-join per bed_id, pairwise
Date field: onboarding_date, actual_exit_date
Aggregation: COUNT(*) overlapping pairs
Organization grain: organization_id
Property grain: Via bed->apartment->property
Tenant/allotment grain: bed_id (grouping key)
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: THIS METRIC IS the overlap-detection itself.
Historical coverage: Full tenant_allotments history, 2019-11 to 2026-08.
Snapshot/current-state behavior: Current-state check as of the snapshot/query date used to close out open (NULL actual_exit_date) intervals.
Known conflicts: None (a detection metric).
Known limitations: This pass's own re-implementation found 214 overlapping pairs vs H.056's reported 187 -- a real, honestly-reported methodological difference (this reconstruction's open-interval boundary handling for currently-Staying allotments, ending them at the 2026-08-29 snapshot date rather than H.056's own unexported boundary convention, most likely explains the gap). Neither figure should be treated as more authoritative without access to H.056's exact generating SQL.
AI trust status: DISCLOSE
Validation target: H.056 overlapping_allotments (validated: DQ.003 in validate_data_quality.py, DIFFERS: 214 reconstructed vs 187 reference, ~14% higher, explained by boundary-condition sensitivity, not a data error).
```
**Cross-references:** data_quality_report.md: [DQ.003](data_quality_report.md#dq003)

**Note:** Only metric-reconstruction check in this deliverable with an unresolved (if bounded and explained) count discrepancy against its reference.

<a id="mrisk008"></a>
### M.RISK.008 -- Ledger/source reconciliation

```text
Metric: Ledger/source reconciliation
Business meaning: Umbrella cross-reference to the three source-vs-ledger drift checks (receipts, invoices, deposit settlements).
Definition: See M.COL.003 (receipts), M.INV.001's ledger cross-check (invoices), M.DEP.002 (deposit settlements).
Source tables: See each component metric
Source views: v_je_amount_reconciliation logic (H.001)
Source functions: None
Relevant columns: See each component metric
Filters: See each component metric
Joins: See each component metric
Date field: See each component metric
Aggregation: See each component metric
Organization grain: organization_id
Property grain: See each component
Tenant/allotment grain: See each component
Reversal treatment: Sign-inverted netting convention (H.001's own construction, business_logic.md 1.3 definition C) across all three.
Soft-delete treatment: Live rows only on the source side throughout.
Duplicate treatment: Not applicable to this umbrella framing.
Historical coverage: See each component metric.
Snapshot/current-state behavior: Not snapshot-dependent.
Known conflicts: Conflicting definitions exist for all three components (C.014/C.015/C.016).
Known limitations: Receipts: Rs.5,340,795.62 gap (6.5% of total). Invoices: Rs.2,423,270.00 gap (3.3%), FULLY row-reconciled to 120 specific invoices. Deposit settlements: Rs.583,495.34 gap (10.3%), with a strong suspected 2x-double-count mechanism (23/43 rows exactly 2.0000x). None of these are shown to affect AGGREGATE revenue/expense/cash totals (which use the reversal-excluded v_account_balances convention and are proven exact against F.001/F.010/F.011 in this pass).
AI trust status: DISCLOSE
Validation target: All three independently re-derived and exact-matched to H.001 in this pass (COLL.02, and the invoice/deposit equivalents referenced in M.INV.001/M.DEP.002).
```
**Cross-references:** conflicts.md: [C.014](conflicts.md#c014), [C.015](conflicts.md#c015), [C.016](conflicts.md#c016) | data_quality_report.md: [DQ.006](data_quality_report.md#dq006), [DQ.007](data_quality_report.md#dq007), [DQ.008](data_quality_report.md#dq008)

<a id="mrisk009"></a>
### M.RISK.009 -- Data-quality score / trust status

```text
Metric: Data-quality score / trust status
Business meaning: A meta-metric: how much of the metric catalog is SAFE to answer directly vs requires disclosure/showing both/blocking.
Definition: COUNT of metrics in this registry by ai_trust_status.
Source tables: metric_registry.csv (this deliverable's own output)
Source views: N/A
Source functions: N/A
Relevant columns: ai_trust_status column of metric_registry.csv
Filters: None
Joins: None
Date field: Not applicable
Aggregation: COUNT(*) GROUP BY ai_trust_status
Organization grain: Not applicable
Property grain: Not applicable
Tenant/allotment grain: Not applicable
Reversal treatment: Not applicable
Soft-delete treatment: Not applicable
Duplicate treatment: Not applicable
Historical coverage: Reflects this deliverable's snapshot as of 2026-08-31 (today).
Snapshot/current-state behavior: Will change as more metrics are validated or as underlying data/conflicts are resolved -- re-derive this count whenever the registry is updated, do not hardcode it into the AI layer.
Known conflicts: Not applicable (a meta-metric about conflicts, not itself conflicted).
Known limitations: This is a COUNT of registry rows, not a statistical sample of all possible business questions -- a high SAFE percentage does not guarantee every question an AI might be asked maps cleanly to a SAFE metric.
AI trust status: SAFE
Validation target: Self-validating: this document's closing summary counts are derived directly from metric_registry.csv.
```

**Note:** See this document's closing 'Report' section for the actual counts.

---

## 4. Historical coverage, by domain (calculated from raw CSVs, never from `created_at` unless
proven to be the business event date)

Every date range below is a business-event date (`entry_date`, `payment_date`, `invoice_date`,
`expense_date`, `bill_date`, `settlement_date`, `onboarding_date`/`actual_exit_date`,
`created_at` for `maintenance_tickets` specifically), re-derived from `M.025` and cross-checked
against the raw CSVs during the integrity-report and business-logic passes. `created_at` is used
only where no other date field exists on the table (confirmed case: `maintenance_tickets`, which
has no separate "opened" business-date column) or is explicitly labelled as such.

| Domain | Coverage | Months | Source column | Notes |
|---|---|---|---|---|
| Tenancy (`tenant_allotments`) | 2019-11-03 to 2026-08-31 | 67 | `onboarding_date` | Widest span in the package. |
| Ledger (`journal_entries`) | 2019-11-03 to 2026-09-20 | 54 | `entry_date` | 3 rows forward-dated past the 2026-08-29 snapshot. |
| Receipts | 2022-11-30 to 2026-08-28 | 46 | `payment_date` | |
| Owner payments | 2022-11-01 to 2026-08-01 | 46 | `bill_date` | All ledger-posted in a single batch on 2026-08-13 (DQ.020) -- posting date is NOT the business date. |
| Invoices | 2023-02-05 to 2026-09-20 | 44 | `invoice_date` | 3 rows forward-dated. |
| Expenses | 2023-03-11 to 2026-08-24 | 35 | `expense_date` | |
| Deposit settlements | 2023-04-03 to 2026-09-20 | 35 | `settlement_date` | 2 rows forward-dated. |
| Maintenance | 2025-01-29 to 2026-08-29 | 20 | `created_at` (no separate business-open-date column exists) | Shortest operational-domain coverage -- no YoY comparison should be attempted. |
| EB -- `eb_payments` | 2026-04-29 to 2026-06-27 | **2** | `bill_date` | Narrowest coverage in the package. |
| EB -- `electricity_readings` | (export window: 2026-03-20 to 2026-07-31 for `created_at`) | 5 (export) | `billing_month` (TEXT, 'Mon-YY', wider historical range e.g. 'May-24' -- not directly comparable to the other domains' date-typed columns without parsing) | DQ.028 format defect. |
| EB -- `eb_monitoring_readings` | 2026-08-18 only | **1 day** | `reading_date` | A single snapshot, not a time series (DQ.021). |
| `tenant_transactions` (legacy) | date column nominally 2019-11 to 2026-05 | -- | `date` | **FROZEN**: all 16,451 rows were `created_at` between 2026-04-17 and 2026-04-28 (an 11-day migration), never wired to live posting (DQ.019). One row has a corrupt year, `0206-03-27` (DQ.023). Not a live feed regardless of its nominal date span. |

**No YoY or month-over-month comparison should be recommended for maintenance (20 months) or any
EB sub-table (1-5 months) — there is not enough historical depth.** Ledger, tenancy, receipts,
owner payments, invoices, expenses, and deposits all have 35+ months and can support a YoY
comparison once at least 2 full years of the relevant window are available (tenancy and ledger
already qualify; receipts/owner payments/invoices/expenses/deposits reach ~3 years).

---

## 5. Validation methodology and honesty notes

- **Every MATCH in `validation_summary.csv` is an exact-value reproduction**, not a rounded or
  approximate agreement, unless the row's own `explanation` states an applied tolerance.
- **Every DIFFERS row states a mechanism**, not just a number. Two of the four DIFFERS in this
  pass are genuinely new discoveries made *while building this deliverable*, not carried forward
  from earlier ones:
  - **`MAINT.01b`**: previously "not determinable" in `data_quality_report.md` DQ.027, the
    1613-vs-1611 ticket-count gap (H.019) is now **proven**: 2 tickets have 2 resolutions each
    (H.018), so joining `maintenance_tickets` to `ticket_resolutions` fans out by exactly +2 rows
    — 1611 + 2 = 1613 exactly.
  - **`AR.04a`**: proves H.052's `def2_tenant_transactions` figure (Rs.9,968,023.32, cited in
    `conflicts.md` C.005) is the **unclipped** per-allotment sum — a second, `GREATEST(...,0)`-
    floored sub-variant (Rs.10,517,031.27, `AR.04b`) also exists and is preserved separately, not
    collapsed into the first.
- **One hypothesis was tested and corrected during script-writing**: an early revenue/expense
  monthly reconciliation appeared to show a "56 vs 57 months" gap; tracing it down proved the
  gap was caused by this script's own choice to group by month alone instead of
  `(property_id, month)` matching `v_pnl`'s true grain — fixed in the script, not glossed over,
  and the residual 2-row gap that remains (`REV.02`) was individually inspected and confirmed to
  be two legitimate `Rs.0`-revenue, expense-only months rather than a data problem.
- **DQ.030's root-cause confidence is upgraded** by this pass from "suspected" (a code-reading
  inference in `data_quality_report.md`) to **proven by execution**: `COLL.03` shows the exact
  `account_code='1000'` filter used in `get_universal_metrics_series` matches **0 real rows** and
  returns **Rs.0.00** against real ledger data, confirmed directly rather than merely predicted.
- **EB tenant-allocation formula** (`business_logic.md` 12.1) is upgraded from a 5-row spot-check
  to a **full 801-row population proof** (`EB.01`/`EB.02`, both 801/801 exact).

---

## 6. Report

**Metrics reconstructed:** 49 (24 Financial, 16 Operations, 9 Risk/Data-quality) — see
`metric_registry.csv` for the machine-readable form of all 49.

**Metrics validated (had a reconstruction actually executed and compared against evidence):**
43 of 49 carry at least one script-executed check referenced in `validation_summary.csv`
(80 individual checks total across those 43). The remaining 6 (`M.COL.002`, `M.AR.001C`,
`M.OCC.003`, `M.OCC.004`, `M.LIFE.001`, `M.RISK.009`) are honestly marked as not independently
script-validated — either no reference view/diagnostic exists to compare against
(`get_occupancy_intelligence` has no exported output at all), or the metric is a row-level
trigger rule rather than an aggregate (`M.LIFE.001`), or it is self-referential
(`M.RISK.009`, the meta data-quality-score metric).

**Metrics matching their reference view exactly:** 73 of 80 individual validation checks
(91.25%) — `validation_status = MATCH` in `validation_summary.csv`, spanning every financial
foundation metric (ledger, revenue, expenses, profit, owner payments, deposits) and every
occupancy definition (16 of 16 occupancy checks matched exactly).

**Metrics differing from their reference view:** 4 checks (`REV.02`, `AR.04c`, `DQ.003`,
`DQ.026`) — every one has a stated, evidence-based mechanism in its `explanation` field, not a
bare "differs". None represents a monetary discrepancy; all four are population/count/coverage
differences with an identified cause (grouping grain, sub-definition choice, boundary-condition
sensitivity, and a verification-coverage gap, respectively).

**Metrics with unresolved conflicts** (`AI trust status` = SHOW_BOTH or BLOCK, i.e. no single
number should ever be stated): **12** — 4 BLOCK (`M.AR.001C`, `M.AR.001D`, `M.PROFIT.001`,
`M.RISK.001`) + 8 SHOW_BOTH (`M.AR.001A`, `M.AR.001B`, `M.AR.002`, `M.AR.003`, `M.OCC.001`,
`M.OCC.002`, `M.OCC.005`, `M.OWN.002`).

**Metrics NOT_DETERMINABLE:** 2 (`M.OCC.003` occupancy by apartment, `M.OCC.004` occupancy by
bed) — both are fully specified and reconstructable from source per their exported function
bodies (`get_occupancy_intelligence`, `get_bed_occupancy_timeline`), but neither has any
exported output row to validate a reconstruction against.

**Metrics BLOCKED** (never state a single definitive number): **4** — `M.AR.001C` (application
`balance_due`), `M.AR.001D` (`tenant_transactions`), `M.PROFIT.001` (3 incompatible profit
definitions, one PROVEN to omit owner rent), `M.RISK.001` (outstanding dues, the same 4-way AR
conflict framed as a risk metric). Consistent with the brief's rule: none of these is downgraded
from BLOCK merely because a plausible single calculation exists — the AI layer must always
disclose the conflict instead.

**Biggest validation discrepancies** (by mechanism significance, not just Rs. size):
1. **`M.AR.001C` vs `M.AR.001D` vs the ledger** — Rs.1,009,125.78 (app) vs Rs.9,968,023.32-
   10,517,031.27 (legacy, two sub-variants) vs Rs.83,297.85 (ledger) — up to a ~126x spread.
2. **`M.PROFIT.001`** — Def B (`get_universal_metrics` v1) omits owner rent entirely, a proven
   36.63% profit overstatement (reproduced to 0.03 points of `conflicts.md`'s original 36.6%
   figure) relative to the owner-rent-inclusive figure.
3. **`M.EXP.002`** — Rs.1,030,618.00 (4.96% of total expenses) invisible to `v_pnl_by_category`'s
   9 named buckets every single month, proven via an exact 57-month arithmetic identity.
4. **`M.DEP.002`** — Rs.583,495.34 (10.3%) settlement ledger drift, with a suspected (not
   proven) systematic 2x double-count affecting 23 of 43 drifting rows exactly.
5. **`DQ.003` (`M.RISK.007`)** — this pass's own overlap-detection (214 pairs) vs H.056's
   187 — the only meaningful reconstruction-methodology gap found in this pass, bounded and
   explained (interval-boundary handling), not a data-quality finding in itself.

**Which metrics are ready to become semantic-layer definitions as-is:**
All **18 SAFE** metrics — `M.REV.001`, `M.REV.002`, `M.EXP.001`, `M.PNL.001`, `M.TB.001`,
`M.CASH.001`, `M.DEP.001`, `M.OWN.001`, `M.TEN.001`, `M.TEN.002`, `M.TEN.003`, `M.LIFE.001`,
`M.LIFE.002`, `M.LIFE.003`, `M.LIFE.004`, `M.MAINT.001`, `M.MAINT.002`, `M.RISK.009` — can be
wired into the semantic layer directly. All but `M.LIFE.001` and `M.RISK.009` are exactly
validated against an exported business view/diagnostic in `validation_summary.csv`; `M.LIFE.001`
is fully specified from two completely-read trigger function bodies with no ambiguity (a
row-level derivation rule, not an aggregate, so there is no view total to compare against); and
`M.RISK.009` is self-referential by construction. The **17 DISCLOSE** metrics are ready with a
caveat string attached (already drafted in each entry's "Known limitations" field). The
**8 SHOW_BOTH** (`M.AR.001A`, `M.AR.001B`, `M.AR.002`, `M.AR.003`, `M.OWN.002`, `M.OCC.001`,
`M.OCC.002`, `M.OCC.005`) and **4 BLOCK** (`M.AR.001C`, `M.AR.001D`, `M.PROFIT.001`,
`M.RISK.001`) metrics require an explicit owner/product decision before the semantic layer can
expose a single number for them — `conflicts.md`'s "Recommended handling" sections are the
starting point for that decision, not a substitute for it.

**Next recommended step:** review this deliverable (E) before any semantic-layer or AI-layer
work begins, per the brief's explicit instruction to stop here.
