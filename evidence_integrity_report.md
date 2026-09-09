# Evidence / Package Integrity Report — First Pass

**Scope of this document:** package integrity only. No metric reconstruction, no business
analysis, no conflict resolution. Those follow in deliverables B–F.

**Source CSVs were not modified.** Everything below is derived read-only. New files created by
this pass: `evidence/file_manifest.csv`, `data_inventory.md`, `scripts/*`, and this report.

---

## 1. Headline numbers

| Question | Answer | Evidence |
|---|---|---|
| Files discovered | **258** (253 CSV + 5 ZIP) | filesystem |
| CSV files carrying evidence | **253** | filesystem |
| ZIP archives | **5** — 248 members, **100% byte-size-identical to loose CSVs**; contain no unique evidence | `scripts/01_verify_zip_redundancy.py` |
| Public base tables declared | **131** | M.000 `schema_scope` |
| Public base tables with data exported | **101 of 101 non-empty** | manifest, M.006 |
| Public base tables empty (0 rows, correctly not exported) | **30** | M.006 |
| Business views exported | **28 files → 27 distinct views** (F.026 duplicates F.025) | manifest |
| Public views declared | **54** | M.000, M.016 |
| Views with any data export | **35** (27 business + 8 diagnostic) | manifest |
| Views with no data export | **19** (17 `v_export_*` wrappers, 1 empty, 1 ambiguous) | see §6 |
| Function definitions (full bodies) | **25 individual files + 1 bundle of the same 25** | FN.* |
| Total in-scope routines catalogued | **483** = 25 with bodies + 458 signature-only | M.019, FN.999 |
| Triggers catalogued | **55** (exported twice, byte-identical) | FN.TRG = M.021 |
| Diagnostic exports | **67 files → 60 distinct diagnostics** | manifest `H.*` |
| Metadata exports | **29 files** | manifest `M.*` |
| Duplicate exports | **10 byte-identical pairs** + 1 reorder-only pair | §4 |
| Unresolved / unidentifiable files | **0** | manifest |

Every one of the 253 CSVs is identified by content. Nothing is attributed by filename.

---

## 2. Snapshot timestamps and export atomicity

| Marker | Value | File |
|---|---|---|
| Schema scope captured | `2026-08-29 09:00:52.160707+00` | M.000 |
| **Snapshot START** | `2026-08-29 09:02:03.620184+00`, txn `421016:421016:` | M.002 |
| Row counts taken | `2026-08-29 09:02:53.218115+00` | M.006 |
| **Snapshot END** | `2026-08-29 11:18:26.768848+00`, txn `421072:421072:` | M.099 |
| Elapsed | **2 h 16 min 23 s** | derived |
| Transactions committed during window | **56** (421016 → 421072) | derived |
| PostgreSQL version | `PostgreSQL 17.6 on aarch64-unknown-linux-gnu` (both ends, identical) | M.002 / M.099 |

**The export is NOT a single atomic snapshot.** Each CSV is a separate statement against a live
database over a 2h16m window, and 56 transactions committed inside it. Cross-table joins built
from these CSVs can therefore straddle a write. §3 quantifies the actual damage: it is small,
bounded, and fully traced.

---

## 3. Row-count verification — 148 in-scope objects

Method: every exported CSV's data-row count compared against M.006 `exact_rows` for the object
its header signature resolves to.

**Result: 95 of 101 exported tables match M.006 exactly. 6 differ — 5 by exactly +1, and
`bot_conversations` by -8 because only an aggregate was exported (§5.1).**

| Table | M.006 counted | Exported | Δ | Traced cause |
|---|---|---|---|---|
| `profiles` | 222 | 223 | **+1** | new row `0676ded1…`, `created_at 2026-08-29 09:08:22Z` |
| `user_roles` | 209 | 210 | **+1** | role row for the same new user (no `created_at` exported) |
| `maintenance_tickets` | 1610 | 1611 | **+1** | ticket `VIST-26-08-00105`, id `337d65ae…` |
| `ticket_logs` | 8239 | 8240 | **+1** | log row for ticket `337d65ae…` — *same ticket* |
| `ai_logs` | 6765 | 6766 | **+1** | one `diagnosis` call, `gemini-2.5-flash`, `success=false` |
| `bot_conversations` | 9 | 1 | **-8** | **not drift** — row level withheld as PII, 1 aggregate row exported instead (§5.1) |

Excluding `bot_conversations`, each extra row was located and its timestamp confirmed to be **after** `09:02:53Z`. The five
deltas collapse to **three real user events** during the export window: one user signed up
(`profiles` + `user_roles`), one maintenance ticket was raised (`maintenance_tickets` +
`ticket_logs`), and one AI diagnosis ran (`ai_logs`).

**Assessment:** the drift is fully explained, confined to operational tables, and touches **no
financial, ledger, occupancy, or tenancy table**. No metric in scope is affected. Reproducing
`v_maintenance_metrics` must nonetheless use the 1610-row basis that the exported views were
computed on, or accept a one-ticket discrepancy.

Verification script: `scripts/02_verify_row_counts.py`.

---

## 4. Duplicate exports

Ten pairs are **byte-identical**. Each is a harmless re-run; neither copy is preferred, but the
duplicate must not be unioned into an analysis.

| # | Keys | Object | Rows |
|---|---|---|---|
| 1 | `M.021` = `FN.TRG` | trigger wiring | 55 |
| 2 | `H.001` = `H.001b` | `v_je_amount_reconciliation` | 6 |
| 3 | `H.002` = `H.002b` | `v_je_source_counts` | 7 |
| 4 | `H.010` = `F.005` | `v_occupancy` | 1 |
| 5 | `H.015` = `F.022` | `v_active_tenants` | 1 |
| 6 | `H.017` = `H.054` | P&L bucket gap | 57 |
| 7 | `H.020` = `H.020b` | receipt-allocation emptiness | 1 |
| 8 | `H.029` = `F.028` | `v_diag_owner_rent_missing_from_profit` | 46 |
| 9 | **`F.025` = `F.026`** | `maintenance_item_stock_summary` | 93 |
| 10 | `F.027` = `H.047` | `v_exit_reconciliation_worklist` | 45 |

**One further pair differs only by row order:** `H.003` and `H.003b` (`v_je_stub_pollution`,
9 rows). The row *sets* are identical; `manual` and `assets` are transposed. The view has no
deterministic `ORDER BY`. Not a data discrepancy.

**Consequence for the "28 business views" claim:** 28 files were exported under F-keys, but
`F.025`/`F.026` are the same bytes. **27 distinct business views carry data, not 28.**

---

## 5. Base-table coverage — 131 public tables

- **101 tables have rows and all 101 were exported.** Zero unexplained gaps.
- **30 tables hold 0 rows and were not exported.** This is recorded as *empty*, not *missing*.
  The empty set is itself a finding, because it contradicts several plausible metric paths:

  `accounting_periods`, `asset_depreciation`, `asset_maintenance_logs`, `asset_movements`,
  `asset_payments`, `attendance_logs`, `bed_status_history`, `bed_type_config`, `companies`,
  `departments`, `electricity_shares`, `employees`, `leave_requests_sync`, **`ledger_entries`**,
  `lifecycle_config`, `migration_log`, `org_ai_settings`, `payroll`, `purchase_items`,
  `purchase_orders`, **`receipt_allocations`**, `regular_maintenance_rules`,
  `replacement_forecasts`, `tickets`, `upi_tenant_mappings`, `users`, `vendor_remarks`,
  `whatsapp_conversations`, `whatsapp_dedup`, `whatsapp_failures`

  Three of these are load-bearing and are flagged now for deliverables C/D:
  - **`ledger_entries` = 0** while `journal_entries` = 14 236 and `journal_lines` = 33 894.
    A superseded ledger implementation. Any "ledger" reference must be disambiguated.
  - **`receipt_allocations` = 0** against 5 758 live receipts (H.020, exported twice).
    Receipt→invoice settlement is therefore **not** carried by an allocation table; some other
    mechanism does it. Must be established before any collections/AR metric.
  - **`bed_status_history` = 0** — no bed-status audit trail exists, so historical occupancy
    cannot be rebuilt from a status log. It must come from `tenant_allotments` dates.

### 5.1 Base-table exports that are not plain `SELECT *`

| Table | Departure from the raw table | Impact |
|---|---|---|
| `journal_lines` | **Denormalised.** Carries 6 extra columns not on the table — `entry_date`, `period`, `posted_at`, `source_table`, `source_id`, `is_reversal_of` — joined in from `journal_entries`. Row count 33 894 matches M.006 exactly. | Convenient, but these fields must be re-validated against `journal_entries` rather than trusted, since the join happened at export time. |
| `tenants` | 27 PII columns excluded; `phone_hash` substituted. 1027 rows, exact match. | Names/contacts unavailable by design. Joins by `id` unaffected. |
| `enquiries` | `name`, `phone`, `raw_payload` excluded; `phone_hash` substituted. | Fine for counts. |
| `ai_logs` | `prompt_excerpt`, `response_excerpt` excluded. | Fine. |
| `maintenance_tickets` | `photo_urls`, `tenant_name`, `tenant_phone` excluded. | Fine. |
| `ticket_logs` | `notes` excluded. | Free-text unavailable. |
| `profiles` | `avatar_url`, `email`, `full_name`, `phone` excluded. | Fine. |
| **`bot_conversations`** | **Row level NOT exported.** Only a 1-row aggregate (`conversation_count`, `first_updated`, `last_updated`). Table holds 9 rows. | Correct PII handling (`transcript`, `phone`). Conversation-level analysis is **not determinable from exported evidence**. |

All exclusions are consistent with M.027 `sensitive_columns`, which classifies 160 columns:
57 `FINANCIAL_OR_GOVT_ID` → hash, 26 `IDENTITY_DOCUMENT` → exclude, 26 `CONTACT_PHONE` → hash,
19 `CONTACT_EMAIL` → hash, 7 `SECRET_OR_BIOMETRIC` → exclude, 25 `PERSONAL_KEPT` → keep flagged.
**No excluded PII will be reconstructed.**

---

## 6. View coverage — 54 public views

**27 distinct business views exported (F.001–F.028, F.026 duplicate):**

`v_pnl`, `v_pnl_by_category`, `v_revenue_by_period`, `v_expenses_by_period`, `v_occupancy`,
`v_outstanding_receivables`, `v_tenant_current_dues`, `v_tenant_aging`,
`v_invoice_settlement_status`, `v_advance_balances`, `v_org_cash_balance`, `v_trial_balance`,
`v_trial_balance_detailed`, `v_account_rollup`, `v_maintenance_metrics`,
`v_maintenance_by_issue_type`, `v_tenant_lifecycle_events`, `v_tenant_ledger`,
`v_expense_composition`, `v_bed_expense_breakdown`, `v_account_balances`, `v_active_tenants`,
`v_property_expense_share`, `v_asset_payment_status`, `maintenance_item_stock_summary`,
`v_exit_reconciliation_worklist`, `v_diag_owner_rent_missing_from_profit`

**8 diagnostic views exported under H-keys:** `v_je_amount_reconciliation`, `v_je_source_counts`,
`v_je_stub_pollution`, `v_je_intentional_skips`, `v_diag_invoice_drift`,
`v_diag_allotment_balance_drift`, `v_diag_deposit_phantom`, `v_deposit_ledger_anomalies`.

**19 views without data — every absence accounted for:**

- **17 `v_export_*` wrappers** (`apartments`, `assets`, `audit_logs`, `beds`,
  `deposit_settlements`, `electricity_readings`, `expenses`, `invoices`, `journal_entries`,
  `journal_lines`, `maintenance_tickets`, `properties`, `receipt_allocations`, `receipts`,
  `tenant_adjustments`, `tenant_allotments`, `tenants`). These are PII-safe read wrappers; the
  underlying base tables were exported directly with the same exclusions applied. **Redundant,
  not missing.** Verified: for `beds`, `deposit_settlements`, `electricity_readings`, `invoices`,
  `journal_entries`, `tenant_adjustments` the exported row counts equal the base-table M.006
  counts exactly, so the base table — not the wrapper — is what was read.
- **`v_diag_orphan_receipts` — the view is EMPTY.** H.032 `diagnostic_view_rowcounts` records
  0 rows. Absence is explained. *(This is a substantive finding: there are no orphan receipts.)*
- **`maintenance_item_low_stock` — AMBIGUOUS.** Its column list is byte-identical to
  `maintenance_item_stock_summary`, so header matching cannot separate them. The 93-row export
  equals the full `maintenance_items` row count (93), which points to `stock_summary`. Whether
  `maintenance_item_low_stock` was ever exported is **not determinable from exported evidence.**

### 6.1 Views exported as truncated samples — do not treat as complete

| Key | View | Exported | True size | Note |
|---|---|---|---|---|
| `H.036` | `v_tenant_lifecycle_events` | **500** | 2204 (`F.017`) | `LIMIT 500` sample |
| `H.038` | journal-line trace | 200 | 33 894 lines | row trace |
| `H.039` | `tenant_transactions` trace | 200 | 16 451 | row trace |
| `H.040` | invoice-drift trace | 200 | 2227 drifting (`H.043`) | row trace |
| `H.041` | receipts trace | 200 | 5858 | row trace |
| `H.028` | tenant balance 4-way | 200 | 1213 (`H.052` is the full set) | superseded by H.052 |

Aggregating any of these as if complete will produce wrong numbers. `F.017` and `H.052` are the
full-population versions and should be preferred.

---

## 7. Function and trigger evidence — complete

| Set | Count | File |
|---|---|---|
| In-scope routines total | **483** (478 public + 5 market) | M.019 |
| Routines with **no** body exported | **458** | FN.999 `functions__remaining_inventory` |
| Routines with body exported | **25** | FN.000 `functions__business_logic` + 25 single files |
| Arithmetic | 458 + 25 = **483 ✔ exact** | — |

Set difference `M.019 − FN.999` yields **exactly** the 25 business-logic routines. **No function
definition is missing from the declared business-logic set.**

The 25 bodies exist in two forms: `FN.000` carries the bare `prosrc` with a `source_length`
column; the 25 individual files carry the full `CREATE FUNCTION` text (consistently ~130–200
chars longer). Both agree.

The 25: `get_universal_metrics`, `get_universal_metrics_v2`, `get_universal_metrics_series`,
`get_occupancy_intelligence`, `get_bed_occupancy_timeline`, `trg_invoice_journal_post`,
`trg_receipt_journal_post`, `trg_expense_journal_post`, `trg_settlement_journal_post`,
`trg_adjustment_journal_post`, `enforce_journal_balanced`, `enforce_period_lock`,
`enforce_subledger_completeness`, `delete_journal_entries_on_source_delete`,
`delete_invoice_journal_entries_on_invoice_delete`, `sync_tenant_staying_status`,
`sync_tenant_staying_status_on_delete`, `validate_deposit_settlement`,
`guard_deposit_transfer_before_onboarding`, `normalize_owner_payment_journal_dates`,
`expense_sync_resolution`, `ensure_booking_receipt_number`, `log_journal_entry_post`,
`_export_profile_name`, `refresh_org_metrics`.

**Caveat carried forward:** the 458 signature-only routines have *no bodies*. Per the brief, none
is assumed irrelevant. If a metric traces into one of them, the answer becomes *"not determinable
from exported evidence"* rather than a guess.

Trigger wiring (55 triggers, table/timing/events/function) is present twice, byte-identical
(`M.021`, `FN.TRG`). Two further definition sets, `M.020` (36 routines) and `M.022` (40
functions), came with the original metadata package and overlap the above; they have not yet
been diffed against FN.000 — a task for deliverable B.

---

## 8. Diagnostics — 67 files, 60 distinct, all read

All present and identified; keys `H.001`–`H.058` plus `H.012a`–`H.012e`. The five
`H.012a`–`H.012e` files are the un-suffixed exports (`..csv`, `… (2)..csv`, etc.) that carry the
occupancy definition comparison; they are the only files **not** included in any ZIP.

Selected values recorded now for traceability (analysis deferred to C/D):

**Ledger vs source amounts (H.001)** — `expenses`, `owner_payments`, `tenant_adjustments` are
`PERFECT` (diff 0.00). Three are `INVESTIGATE`: `receipts` +5 340 795.62, `invoices`
+2 423 270.00, `deposit_settlements` +583 495.34.

**Occupancy — five competing definitions, all exported (H.012a–e):**

| Def | Basis | Numerator | Denominator |
|---|---|---|---|
| A | `v_occupancy` — Live bed + Live apartment, Staying only | 168 | 195 |
| B | Live bed + Live apartment, Staying **+ On-Notice** | 175 | 195 |
| C | **ALL** beds, Staying + On-Notice | 175 | 203 |
| D | `get_universal_metrics` — `beds.status='Live'`, Staying | 168 | 195 |
| E | `get_bed_occupancy_timeline` — Staying + On-Notice + Exited | 194 | 203 |

**The 7 unbucketed On-Notice-only beds are explicitly identified** in `H.011` — bed ids
`53df99b1…`, `18323ac7…`, `dcfddc61…`, `cead0c81…`, `3d87a782…`, `2225fe89…`, `16d9e7d4…`, each
with `occupied=false, booked=false, on_notice=true`. `H.013` corroborates: 168 Staying,
7 On-Notice, 7 beds held on notice, **0 beds carrying both statuses** — so A and B differ by
exactly these 7 and there is no double-count.

**AR definitions disagree on population but not on total (H.006):** `v_outstanding_receivables`
(reversals *excluded*) = 626 rows, total AR 83 297.85. `v_tenant_current_dues` (reversals
*included*) = 645 rows, total AR 83 297.85 — **identical AR**, plus `deposit_held` 4 221 150.00
and `booking_advance` 0.00 that the first view does not carry. Recorded as a conflict; not
resolved here.

`H.032` confirms every diagnostic view's true size, which is how the `v_diag_orphan_receipts = 0`
absence in §6 was verified rather than assumed.

---

## 9. Historical coverage — claims verified against M.025

Every claim in the brief was checked against the exported temporal profile. **All 10 confirmed;
one needs a caveat.**

| Claim | M.025 evidence | Verdict |
|---|---|---|
| occupancy/tenancy from 2019-11 | `tenant_allotments.onboarding_date` 2019-11-03 → 2026-08-31, 67 months | **confirmed** |
| receipts from 2022-11 | `receipts.payment_date` 2022-11-30 → 2026-08-28, 46 months | **confirmed** |
| owner payments from 2022-11 | `owner_payments.bill_date` 2022-11-01 → 2026-08-01, 46 months | **confirmed** |
| ledger from 2019-11 | `journal_entries.entry_date` 2019-11-03 → 2026-09-20, 54 months | **confirmed** |
| invoices from 2023-02 | `invoices.invoice_date` 2023-02-05 → 2026-09-20, 44 months | **confirmed** |
| expenses from 2023-03 | `expenses.expense_date` 2023-03-11 → 2026-08-24, 35 months | **confirmed** |
| deposits from 2023-04 | `deposit_settlements.settlement_date` 2023-04-03 → 2026-09-20, 35 months | **confirmed** |
| maintenance from 2025-01 | `maintenance_tickets.created_at` 2025-01-29 → 2026-08-29, 20 months | **confirmed** |
| EB ≈ 2 months | `eb_payments` 2026-04-29 → 2026-06-27 = **2 months** ✔ — but see caveat | **confirmed, with caveat** |
| `tenant_transactions` frozen ≈ 2026-05 | `.date` max **2026-05-05**; all rows written 2026-04-17 → 2026-04-28 | **confirmed** |

**EB caveat.** "About 2 months" is right for `eb_payments` only. The EB domain is four tables
with four different coverages: `eb_payments` 2 months (2026-04→06); `electricity_readings`
1411 rows written across 5 months (2026-03→07); `eb_tenant_shares` 801 rows across 5 months
(2026-04→08); `eb_monitoring_readings` **35 rows all dated a single day, 2026-08-18**. EB
must not be treated as one series.

### 9.1 Coverage findings the brief did not state

**(a) `created_at` is not an event date — there was a bulk backfill around 2026-03-28.**
`invoices`, `receipts`, `tenant_allotments`, `tenant_adjustments` all have `created_at` starting
2026-03-28 while their business dates reach back to 2019–2023. `expenses.created_at` starts
2026-04-11 against `expense_date` from 2023-03. **All historical analysis must use business date
columns.** Using `created_at` collapses six years into five months.

**(b) `owner_payments` was posted to the ledger in a single batch.** All 345 rows carry
`created_at = 2026-08-13`, and H.004 shows every owner-payment journal entry `posted_at` inside
2026-08-13 09:14 → 10:36. Directly relevant to conflict **H (owner rent missing from profit)**.

**(c) Post-snapshot-dated rows exist.** Snapshot is 2026-08-29, yet `invoices.invoice_date`,
`journal_entries.entry_date`, `deposit_settlements.settlement_date` and
`tenant_allotments.actual_exit_date` all reach **2026-09-20**. Small counts (2–3 rows each) but
they will land in a future period bucket. `journal_entries` max entry_date 2026-09-20 vs max
`posted_at` 2026-08-29 confirms these are forward-dated, not clock skew.

**(d) One corrupt date.** `tenant_transactions.date` minimum is **`0206-03-27`** — year 206, a
transposition of 2026. Exactly 1 row (`rows_before_2019 = 1`). Will destroy any unbounded
min-date or time-series axis built on that column.

**(e) `tenants.date_of_birth` has 451 rows before 2019** — expected for DOB, listed only so it
is not mistaken for corruption later.

**(f) YoY feasibility.** Only four domains have ≥ 24 months: tenancy (67), ledger (54), receipts
and owner payments (46), invoices (44), expenses (35), deposits (35). Maintenance has 20 months —
a single partial YoY. **EB (2–5 months) and `tenant_transactions` (frozen 2026-05) cannot support
YoY at all.** No YoY comparison will be manufactured for them.

---

## 10. Organization / property grain

- **122 of 131 tables carry `organization_id`;** 9 do not (M.007).
- **This is effectively a single-tenant database.** All 94 populated tables with the column show
  `distinct_orgs = 1`; the other 28 are the empty tables (`distinct_orgs = 0`). Organization
  is therefore not a real analytical dimension here.
- **4 tables contain NULL-organization rows** — must be handled explicitly, not dropped silently:

  | Table | Total rows | NULL org rows |
  |---|---|---|
  | `whatsapp_events` | 1943 | **600** |
  | `ticket_logs` | 8239 | **65** |
  | `payroll_sync` | 18 | 6 |
  | `email_templates` | 4 | 3 |

  `ticket_logs` matters: 65 of 8239 log rows (0.8 %) would vanish under an inner join on
  organization. `whatsapp_events` loses 31 % — but it is not a financial table.

- Property grain: M.000 and the exports show **1 property row** (`properties` = 1),
  43 apartments, 203 beds. Property is likewise not a discriminating dimension today.

---

## 11. Is the package incomplete? — findings

**Verdict: the package is substantially complete and internally consistent.** It supports all 13
required metric areas. Six real shortfalls, none blocking:

| # | Gap | Severity | Blocks reconstruction? |
|---|---|---|---|
| 1 | **`market` schema: 17 tables declared IN_SCOPE in M.000, 0 exported.** 7 tables hold 421 rows (`competitor_properties` 257, `competitor_intelligence` 133, `amenities_master` 15, `localities` 6, `org_tracked_localities` 5, `scrape_sources` 4, `competitor_room_types` 1). Only H.037 preserves counts, and only for 7 of the 17. | **Medium** — a stated-scope shortfall | No. No required metric area depends on `market`. |
| 2 | **`bot_conversations` row level withheld** (1 aggregate row for 9 real rows). | Low | No. Deliberate PII handling; respected. |
| 3 | **458 of 483 routines have no body.** | Medium | Only if a metric traces into one. Answer will be *"not determinable"*, never a guess. |
| 4 | **`maintenance_item_low_stock` vs `maintenance_item_stock_summary` indistinguishable** by column signature. | Low | No — attribution reasoned in §6, uncertainty recorded. |
| 5 | **Non-atomic export**, 2h16m, 56 transactions, +1 row on 5 tables. | Low | No — fully traced (§3), no financial table touched. |
| 6 | **Six diagnostics are truncated samples** (`LIMIT 200/500`) that could be mistaken for full populations. | Medium if unnoticed | No — flagged in §6.1; full-population equivalents exist for the two that matter. |

**Not gaps.** These look like absences but are documented facts:
30 empty public tables; 17 redundant `v_export_*` wrappers; `v_diag_orphan_receipts` empty
(H.032); 5 ZIPs containing nothing unique.

**M.001 `object_presence_check`: 58 of 58 expected objects `PRESENT`. Zero absent, zero
wrong-kind.**

---

## 12. Artefacts produced by this pass

| File | Purpose |
|---|---|
| `evidence/file_manifest.csv` | **Canonical map: opaque filename → object.** 253 rows, all identified. Columns: `key`, `logical_name`, `class`, `rows`, `cols`, `bytes`, `file`, `note`. Every later deliverable cites the `key`. |
| `data_inventory.md` | Deliverable **A**. 131 tables + 54 views: type, row count, date coverage, columns, `organization_id`, FKs, sensitivity, analytics suitability. |
| `evidence_integrity_report.md` | This report. |
| `scripts/01_verify_zip_redundancy.py` | Proves the 5 ZIPs add nothing. |
| `scripts/02_verify_row_counts.py` | Re-derives §3 from scratch. |
| `scripts/03_build_manifest.py` | Rebuilds the manifest from content only. |
| `scripts/evidence_loader.py` | Loads any object by manifest key — the interface for deliverables B–F. |

All scripts are read-only. **No source CSV was modified.**

---

## 13. Not yet done — deferred by instruction

Metric reconstruction has **not** begun. Still outstanding: deliverables **B** `business_logic.md`,
**C** `conflicts.md`, **D** `data_quality_report.md`, **E** `metric_reconstruction.md`,
**F** validation scripts.

Conflicts A–I from the brief are all evidenced in the package and located (`H.048`, `H.049`,
`H.050`, `H.002`, `H.051`, `H.043`, `H.052`, `H.029`/`H.030`, `H.017`) but **deliberately not
analysed here**. §8 records raw values only. No conflict has been resolved, and none will be
without evidence that proves one side.
