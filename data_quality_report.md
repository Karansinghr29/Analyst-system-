# D. data_quality_report.md

Formal data-quality register for the future AI analytics trust layer. Consolidates every diagnostic (`H.001`-`H.058`), the row-level traces (`H.011`-`H.013`, `H.038`-`H.041`), function/trigger evidence, metadata (`M.*`), and the raw CSV package into one register, organized by severity and offline-fixability rather than by semantic pairing (that organization is `conflicts.md`, which this report cross-references rather than repeats).

**No finding here is re-invented.** Every DQ entry traces to a specific evidence file and, where a number is stated, that number was re-derived directly from the raw CSV in this pass (not carried forward from a diagnostic's label alone). Two hypotheses considered during this and the prior `conflicts.md` pass were tested against the data and disproven — both are recorded as ruled-out mechanisms (`DQ.010`, `DQ.014`) rather than silently dropped.

**Status vocabulary used throughout:**
- **MEASURED** — evidence directly quantifies the issue.
- **MEASURED EMPTY** — evidence proves zero rows; recorded as empty, not missing.
- **UNVERIFIED** — no diagnostic covers this case; existence/scale is not established either way from the exported package.
- **CONFLICTING DEFINITIONS EXIST** — two or more valid definitions disagree and no evidence proves a winner (full detail lives in `conflicts.md`).

**AI-handling vocabulary** (what the future AI system must do before answering a question touching this issue):
- **SAFE** — answer normally, no caveat needed.
- **DISCLOSE** — answer, but state the limitation.
- **SHOW_BOTH** — present competing figures/definitions side by side, never pick one silently.
- **BLOCK** — do not state a single definitive number; explain why instead.
- **UNVERIFIED** — state plainly that this has not been verified from the exported evidence.

---

## Summary matrix

| DQ ID | Severity | Issue | Rows | Amount | Metrics affected | Status |
|---|---|---|---:|---:|---|---|
| [DQ.001](#dq001) | CRITICAL | Invoice amount_paid + balance != total_amount (internal invoice-record inco... | 2227 of 5214 live invoices | not separately summed in ... | Invoice balance, AR aging, invoice settlement status, any... | MEASURED |
| [DQ.002](#dq002) | CRITICAL | Four competing tenant/allotment balance definitions disagree by up to ~120x | 873 of 1213 allotments (app-sto... | App-stored balance_due su... | Tenant current dues, AR total, collections-risk ranking, ... | MEASURED |
| [DQ.016](#dq016) | CRITICAL | get_universal_metrics (v1) totalProfit omits owner rent entirely, overstati... | 46 months of owner_payments act... | ₹19,019,250.00 total owne... | get_universal_metrics.totalProfit (v1) specifically; any ... | MEASURED |
| [DQ.019](#dq019) | CRITICAL | tenant_transactions is a frozen, unwired legacy ledger with a balance total... | 16,451 rows total; 699 of 1213 ... | Sum ₹9,968,023.32 vs live... | Any metric that might mistakenly source 'tenant balance' ... | MEASURED |
| [DQ.004](#dq004) | HIGH | Five structurally different, non-interchangeable occupancy definitions coexist | N/A (definitional, not row-level) | N/A | Occupancy % (all forms), 'current occupancy' AI answers, ... | CONFLICTING DEFINITIONS EXIST |
| [DQ.005](#dq005) | HIGH | v_occupancy SQL defect: 7 On-Notice-only beds fall into none of the view's ... | 7 beds (of 195 Live-in-Live-apa... | N/A | v_occupancy.on_notice (structurally always 0), v_occupanc... | MEASURED |
| [DQ.008](#dq008) | HIGH | Deposit settlement source amount vs ledger amount, with a suspected systema... | 43 settlements (H.050) | ₹583,495.34 (H.001 aggreg... | Individual-settlement ledger tracing, deposit-refund reco... | MEASURED |
| [DQ.011](#dq011) | HIGH | Deposit-phantom exposure: deposit held with no live tenant relationship and... | 32 allotments | Not determinable from exp... | Deposit-held total, refund liability estimation | MEASURED |
| [DQ.013](#dq013) | HIGH | Duplicate invoices: same allotment + billing_month + invoice_type appearing... | 322 duplicate groups, 356 exces... | ₹4,040,627.00 combined va... | Total invoiced revenue, invoice-count-based metrics, AR i... | MEASURED |
| [DQ.015](#dq015) | HIGH | P&L named category buckets exclude account 5150 (Electricity Payments) enti... | 57 of 57 months affected (100% ... | ₹1,030,618.00 (57-month t... | v_pnl_by_category's 9 named category columns, any expense... | MEASURED |
| [DQ.028](#dq028) | HIGH | EB billing_month text format ('Mon-YY') is incompatible with every other bi... | 1411 of 1411 electricity_readin... | N/A (formatting defect, n... | Any join or comparison between EB billing_month and invoi... | MEASURED |
| [DQ.030](#dq030) | HIGH | get_universal_metrics_series.collections filters on the wrong account code ... | N/A (code-level defect, not a r... | N/A | get_universal_metrics_series.collections (a monthly colle... | MEASURED |
| [DQ.003](#dq003) | MEDIUM | Overlapping tenant_allotments on the same bed (concurrent occupancy conflicts) | 187 bed x allotment-pair rows | Not determinable from exp... | Occupancy (all definitions that count allotments per bed)... | MEASURED |
| [DQ.006](#dq006) | MEDIUM | Receipt source amount vs ledger amount diagnostic diff | 11 receipts traced (H.048); agg... | Aggregate diff ₹5,340,795... | Individual-receipt ledger tracing; the H.001/H.048 diagno... | MEASURED |
| [DQ.007](#dq007) | MEDIUM | Invoice source amount vs ledger amount diagnostic diff, fully row-reconciled | 120 invoices (H.049) | ₹2,423,270.00 (H.001 aggr... | Individual-invoice ledger tracing | MEASURED |
| [DQ.010](#dq010) | MEDIUM | 200 journal entries reference a currently soft-deleted receipt | 200 of 6085 receipt-sourced jou... | Not determinable from exp... | Receipt-sourced ledger completeness checks | MEASURED |
| [DQ.012](#dq012) | MEDIUM | Deposit settlement anomalies: premature settlements, duplicate open settlem... | 22 rows across 3 anomaly types | Not determinable from exp... | Deposit settlement validity, deposit-held balance by tenant | MEASURED |
| [DQ.014](#dq014) | MEDIUM | Duplicate receipts detected but not remediated; some duplicates hard-delete... | 9 detection groups, 23 receipt ... | Sum of duplicate_count=2 ... | Total collections if duplicates remain live and unremediated | MEASURED |
| [DQ.017](#dq017) | MEDIUM | Owner-rent date-basis mismatch causes 7 of 54 months to show a nonzero ledg... | 7 of 54 months | Net ₹0.00 across all 54 m... | Month-by-month owner-rent P&L trend (not the annual/lifet... | MEASURED |
| [DQ.018](#dq018) | MEDIUM | v_tenant_aging buckets are CURRENT_DATE-dependent and not reproducible from... | 644 rows (F.008, all rows affec... | N/A (bucket totals sum co... | AR aging bucket distribution (0-30/31-60/61-90/90+) | MEASURED |
| [DQ.020](#dq020) | MEDIUM | All 345 owner_payments ledger postings occurred in a single ~82-minute batc... | 345 of 345 owner_payments rows;... | ₹19,019,250.00 (full owne... | Any owner-payment posting-time or cash-flow-timing analys... | MEASURED |
| [DQ.025](#dq025) | MEDIUM | NULL organization_id rows in 4 tables | whatsapp_events 600/1943; ticke... | N/A (operational tables, ... | Any org-scoped rollup of ticket_logs (maintenance activit... | MEASURED |
| [DQ.026](#dq026) | MEDIUM | 4 of 5 declared polymorphic relationships have no exported orphan-check dia... | N/A (verification coverage gap,... | N/A | Confidence in referential integrity for owner_payments/te... | UNVERIFIED |
| [DQ.027](#dq027) | MEDIUM | Maintenance ticket view/actual count mismatch, and two independent cost-lin... | 2-ticket gap (1613 view vs 1611... | Not determinable from exp... | v_maintenance_metrics vs v_maintenance_by_issue_type cost... | MEASURED |
| [DQ.021](#dq021) | LOW | eb_monitoring_readings is a single-day snapshot, not a time series | 35 of 35 rows (100%) | N/A | Any EB danger-monitoring trend or historical alert metric | MEASURED |
| [DQ.022](#dq022) | LOW | Placeholder/epoch date in apartments.start_date | 2 of 43 apartments | N/A | Apartment availability-window calculations (get_occupancy... | MEASURED |
| [DQ.023](#dq023) | LOW | Corrupt year in tenant_transactions.date (0206-03-27 instead of a plausible... | 1 of 16,451 rows | Not determinable from exp... | Any MIN(date) or unbounded date-range calculation over te... | MEASURED |
| [DQ.024](#dq024) | LOW | Post-snapshot-dated (future) rows in financial/tenancy tables | Small counts per column (2-11 r... | Not determinable from exp... | Any time-series metric with an implicit 'up to today' ass... | MEASURED |
| [DQ.031](#dq031) | LOW | Non-atomic export: 5 tables show +1 row vs the row-count snapshot due to li... | 5 tables, 1 row each (profiles,... | N/A | None in financial/ledger/occupancy/tenancy scope | MEASURED |
| [DQ.032](#dq032) | LOW | market schema declared IN_SCOPE but 0 of 17 tables were exported | 421 rows across 7 non-empty mar... | N/A (competitive-pricing ... | None of the 13 required metric areas depend on the market... | UNVERIFIED |
| [DQ.009](#dq009) | INFORMATIONAL | v_je_stub_pollution diagnostic re-run returns rows in different order (H.00... | 9 rows (same set, transposed or... | N/A | None -- row set is identical | MEASURED |
| [DQ.029](#dq029) | INFORMATIONAL | 30 declared public tables are empty (0 rows), including two structurally si... | 30 tables, 0 rows each | N/A | ledger_entries (superseded by journal_entries/journal_lin... | MEASURED EMPTY |

**32 issues total.** Severity: 4 CRITICAL, 8 HIGH, 12 MEDIUM, 6 LOW, 2 INFORMATIONAL. AI handling: 7 BLOCK, 15 DISCLOSE, 2 SHOW_BOTH, 6 SAFE, 2 UNVERIFIED.

**Severity reasoning for every CRITICAL and HIGH finding is given in its own section below** (the brief requires this explicitly, not just a label).

---

## Detailed findings

Ordered by severity (CRITICAL first), matching the summary matrix above.

<a id="dq001"></a>
### DQ.001 — Invoice amount_paid + balance != total_amount (internal invoice-record inconsistency)

**Severity:** CRITICAL  
**Why:** the brief's own test is "expose unresolved money": 42.7% of live invoices have an internally inconsistent paid/balance record. Almost half of the invoice population cannot be trusted at the individual-record level, which is a direct AR/collections exposure, not a cosmetic gap.
**Business area:** Invoices / AR

**Affected rows:** 2227 of 5214 live invoices
**Affected amount:** not separately summed in H.043 (per-row drift only)
**Percentage:** 42.7%

**Evidence file(s):** H.043 (v_diag_invoice_drift)

**Root cause / mechanism:** invoices.amount_paid/balance are application-maintained columns, not recalculated by any exported ledger trigger (trg_invoice_journal_post's repost condition excludes amount_paid/balance from its change-detection list). Likely drifts whenever a receipt/adjustment changes the amount_paid side without a corresponding invoice-row update.

**Root cause confidence:** SUSPECTED (mechanism plausible from trigger logic; not proven by tracing individual rows to their causing receipt/adjustment)

**Status:** MEASURED

**Metrics affected:** Invoice balance, AR aging, invoice settlement status, any 'amount due' figure sourced from invoices table directly

**Business impact:** Cannot trust a single-invoice balance figure almost half the time; blocks confident individual-invoice AR answers.

**Offline-fixable from exported evidence:** Partial  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** Yes

**Recommended handling in the semantic layer:** Never expose invoices.balance as a trusted 'amount due' figure at the individual-invoice grain without cross-checking v_invoice_settlement_status (ledger-derived). Safe to use invoices.total_amount (the charge) alone.

**Recommended AI disclosure/response behavior:** `BLOCK` — If asked 'is invoice X paid', state that the invoice's own paid/balance fields are known to drift from the ledger in ~43% of cases and offer the ledger-derived settlement status instead.

---

<a id="dq002"></a>
### DQ.002 — Four competing tenant/allotment balance definitions disagree by up to ~120x

**Severity:** CRITICAL  
**Why:** four independently-sourced tenant-balance figures disagree by up to ~120x with no evidence proving which is authoritative. Any collections or dues decision built on the wrong one materially misstates money owed.
**Business area:** AR / tenant dues

**Affected rows:** 873 of 1213 allotments (app-stored vs tenant_transactions); 1213 of 1213 compared across all 4 defs
**Affected amount:** App-stored balance_due sum ₹1,009,125.78; tenant_transactions sum ₹9,968,023.32; ledger (both conventions) sum ₹83,297.85
**Percentage:** 72% of allotments disagree app-vs-legacy by >₹1

**Evidence file(s):** H.028, H.052, H.044, H.006

**Root cause / mechanism:** tenant_allotments.balance_due (app column), tenant_transactions (frozen legacy table), and the live ledger (journal_lines, two conventions that agree with each other) were never reconciled against one another; ledger pair is internally consistent (proven, 0 of 1213 allotments differ), the other two are not tied to any live posting trigger.

**Root cause confidence:** PROVEN (ledger-pair identity verified row-by-row); SUSPECTED for why app/legacy diverge from the ledger

**Status:** MEASURED

**Metrics affected:** Tenant current dues, AR total, collections-risk ranking, 'which tenants owe money'

**Business impact:** No reliable single tenant-balance figure exists in the exported evidence; this is the single most consequential unresolved conflict for a collections/dues AI answer.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** Yes

**Recommended handling in the semantic layer:** Never answer 'what does this tenant owe' with a single number. Surface the ledger figure as the accounting-system answer and flag the app-stored figure as a disclosed discrepancy if it differs.

**Recommended AI disclosure/response behavior:** `BLOCK` — Always disclose that up to 4 different balance figures exist for a given tenant/allotment and state which one is being reported.

---

<a id="dq016"></a>
### DQ.016 — get_universal_metrics (v1) totalProfit omits owner rent entirely, overstating reported profit

**Severity:** CRITICAL  
**Why:** a proven 36.6% profit overstatement in a named, callable metrics function is precisely the brief's definition of "can materially misstate financial/business decisions." This is not a rounding issue; it changes whether the business looks profitable.
**Business area:** Profit / P&L, owner payments

**Affected rows:** 46 months of owner_payments activity (v_diag_owner_rent_missing_from_profit); 54 months in H.030's comparison
**Affected amount:** ₹19,019,250.00 total owner rent omitted; profit-if-excluded (₹70,940,012) exceeds ledger-inclusive profit (₹51,920,762) by exactly this amount
**Percentage:** 36.6% profit overstatement (70,940,012 / 51,920,762 = 1.366x) across the full 54-month reconstructable history

**Evidence file(s):** M.016 (v_diag_owner_rent_missing_from_profit, self-documenting note column), FN.get_universal_metrics, FN.get_universal_metrics_v2 (proven fix), H.001, H.030

**Root cause / mechanism:** get_universal_metrics v1's totalProfit formula is SUM(invoices.total_amount) - SUM(expenses.amount), with no owner_payments term anywhere in the expression -- confirmed by reading the full function body. get_universal_metrics_v2 explicitly corrects this by substituting SUM(owner_payments.escalated_amount) for the period into its expense total.

**Root cause confidence:** PROVEN (both function bodies fully exported and compared; the omitted view's own note column states this in plain text)

**Status:** MEASURED

**Metrics affected:** get_universal_metrics.totalProfit (v1) specifically; any dashboard or AI answer sourced from it

**Business impact:** A 36.6% profit overstatement is large enough to materially change a business decision (e.g. reinvestment, hiring, owner distribution) if v1's figure were relied upon -- textbook CRITICAL per the brief's own definition ('can materially misstate financial/business decisions').

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** Yes

**Recommended handling in the semantic layer:** Retire or clearly flag get_universal_metrics v1's totalProfit as legacy/incomplete. Use get_universal_metrics_v2's totalProfit (or v_pnl's ledger-based net_profit) as the canonical profit figure going forward.

**Recommended AI disclosure/response behavior:** `BLOCK` — Never state a profit figure sourced from v1 without disclosing the owner-rent omission; when asked 'why did profit fall/rise', always check whether an owner-rent posting event (timing shift) could explain a v1-only anomaly.

---

<a id="dq019"></a>
### DQ.019 — tenant_transactions is a frozen, unwired legacy ledger with a balance total ~120x the live ledger

**Severity:** CRITICAL  
**Why:** if ever mistakenly treated as a dues source, this table would overstate AR by roughly 120x. The mechanism (frozen, unwired legacy table) is well understood, but the blast radius of misuse is catastrophic, which is what drives the severity, not the certainty of the root cause.
**Business area:** AR / tenant dues, collections

**Affected rows:** 16,451 rows total; 699 of 1213 allotments show tenant_transactions balance > 0
**Affected amount:** Sum ₹9,968,023.32 vs live ledger ₹83,297.85 -- gap ₹9,884,725.47
**Percentage:** ~120x (11,966%) larger than the live ledger figure

**Evidence file(s):** H.026, H.044, H.052, M.025, FN.TRG (absence of any wiring to this table)

**Root cause / mechanism:** tenant_transactions was bulk-loaded once (all 16,451 rows created_at between 2026-04-17 and 2026-04-28, an 11-day migration/backfill window) and is not referenced by any of the 55 wired triggers or 25 exported posting functions -- it has never participated in live posting since its load.

**Root cause confidence:** PROVEN (structural facts: frozen creation window, absent from trigger wiring); SUSPECTED for why its balance total is so much larger (not traced row-by-row)

**Status:** MEASURED

**Metrics affected:** Any metric that might mistakenly source 'tenant balance' or 'collections history' from tenant_transactions

**Business impact:** If ever mistakenly surfaced as 'tenant dues', would overstate AR by roughly 120x -- a catastrophic single-metric error, hence CRITICAL despite the mechanism being structurally well understood (frozen, unwired).

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** N (the structural facts are fully proven offline; understanding why the balance differs would need live investigation)

**Blocks an AI/business metric:** Yes

**Recommended handling in the semantic layer:** Never use tenant_transactions for a current-dues or collections metric. May be retained for historical/audit reference (2019-2026 coverage) with an explicit 'legacy, frozen 2026-04, not reconciled' label.

**Recommended AI disclosure/response behavior:** `BLOCK` — If a user specifically asks about tenant_transactions, disclose it is a frozen legacy system with a balance total two orders of magnitude larger than the live ledger and should not be treated as authoritative.

---

<a id="dq004"></a>
### DQ.004 — Five structurally different, non-interchangeable occupancy definitions coexist

**Severity:** HIGH  
**Why:** occupancy is one of the ten example AI questions in the brief ("what is current occupancy"). A 9.4-percentage-point spread across five legitimate, evidence-proven definitions materially affects that headline KPI.
**Business area:** Occupancy

**Affected rows:** N/A (definitional, not row-level)
**Affected amount:** N/A
**Percentage:** Range 86.15% to 95.57% depending on definition chosen (a 9.4-point spread for the 'same' headline KPI)

**Evidence file(s):** H.012a, H.012b, H.012c, H.012d, H.012e, H.008, H.013

**Root cause / mechanism:** v_occupancy, v_active_tenants, get_universal_metrics v1, get_universal_metrics v2, get_bed_occupancy_timeline, and get_occupancy_intelligence each independently define bed universe (Live-only vs all beds), On-Notice treatment (occupied or not), and time horizon (snapshot vs historical) differently.

**Root cause confidence:** PROVEN (all five function/view bodies read in full and compared directly)

**Status:** CONFLICTING DEFINITIONS EXIST

**Metrics affected:** Occupancy % (all forms), 'current occupancy' AI answers, occupancy trend charts

**Business impact:** A single unqualified 'occupancy %' answer can materially mislead management by up to 9.4 percentage points depending on which internal definition silently backs it.

**Offline-fixable from exported evidence:** N/A  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** Partially — see SHOW_BOTH handling below

**Recommended handling in the semantic layer:** The semantic layer must pick one canonical current-occupancy formula (recommend Staying+On-Notice over Live-in-Live-apartment beds, matching get_universal_metrics_v2) and label every occupancy figure with its definition and time horizon in metadata.

**Recommended AI disclosure/response behavior:** `SHOW_BOTH` — If a user asks 'what is our occupancy' with no further context, state the canonical figure and note that other valid definitions exist which may differ by several points.

---

<a id="dq005"></a>
### DQ.005 — v_occupancy SQL defect: 7 On-Notice-only beds fall into none of the view's 4 output buckets

**Severity:** HIGH  
**Why:** a proven SQL defect (not a data anomaly) in a named business view causes 7 beds to disappear from every vacancy/occupancy bucket. Materially affects the occupancy KPI and is 100% reproducible from source.
**Business area:** Occupancy

**Affected rows:** 7 beds (of 195 Live-in-Live-apartment beds)
**Affected amount:** N/A
**Percentage:** 3.59% of Live beds

**Evidence file(s):** H.011, H.013, M.016 (v_occupancy definition)

**Root cause / mechanism:** v_occupancy's on_notice output column requires a bed to be simultaneously Staying (occupied=true) AND On-Notice (on_notice=true); H.013 proves 0 of 203 beds ever carry both statuses, so the column can never register a positive count and the 7 On-Notice-only beds fail every one of the view's 4 filters (occupied, on_notice, booked, vacant).

**Root cause confidence:** PROVEN (direct SQL analysis cross-checked against H.013's 0-overlap fact)

**Status:** MEASURED

**Metrics affected:** v_occupancy.on_notice (structurally always 0), v_occupancy.vacant (undercounted by 7)

**Business impact:** Any vacancy-risk report built on v_occupancy.vacant understates true vacancy exposure by exactly the number of On-Notice-only beds at query time (7 in this snapshot) -- a proven, reproducible SQL bug, not a data anomaly.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** Yes

**Recommended handling in the semantic layer:** Do not use v_occupancy.on_notice or v_occupancy.vacant downstream. Use get_universal_metrics_v2's bed-bucketing (NOT has_staying AND has_notice) as the corrected replacement.

**Recommended AI disclosure/response behavior:** `BLOCK` — If specifically asked about v_occupancy's vacant/on_notice figures, disclose the known defect rather than presenting the number as reliable.

---

<a id="dq008"></a>
### DQ.008 — Deposit settlement source amount vs ledger amount, with a suspected systematic 2x double-count mechanism

**Severity:** HIGH  
**Why:** ₹583,495.34 (10.3% of settlement ledger value) shows an exact, arithmetically-clean 2x pattern strongly consistent with a real diagnostic-query defect rather than noise — large enough, and clean enough, to materially affect confidence in deposit-refund reconciliation pending live-DB confirmation.
**Business area:** Deposits / ledger

**Affected rows:** 43 settlements (H.050)
**Affected amount:** ₹583,495.34 (H.001 aggregate = H.050 row-sum, exact match)
**Percentage:** 10.3% of total settlement ledger value (₹583K of ₹5.67M)

**Evidence file(s):** H.001, H.050

**Root cause / mechanism:** 23 of 43 drifting rows show ledger_amount at EXACTLY 2.0000x source_amount, all with entry_count=3 (one edit-and-repost cycle: original + reversal + correction). Arithmetically consistent with the diagnostic's ledger_amount summing raw credit postings without a reversal-aware netting step (original_credit + corrected_credit = 2x, if the reversal posts as a debit rather than a negative credit on that leg).

**Root cause confidence:** SUSPECTED (strong arithmetic pattern, 23/43 rows exactly 2.0000x; not proven since H.050's SQL is not exported)

**Status:** MEASURED

**Metrics affected:** Individual-settlement ledger tracing, deposit-refund reconciliation

**Business impact:** The cleanest, most mechanistically-explicable of the three source-vs-ledger diagnostics (DQ.006/007/008) -- the exact 2x ratio is the strongest lead for a genuine diagnostic-query bug rather than a real accounting error.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Treat H.050's ledger_amount column as unreliable for any settlement with entry_count > 1. Re-run with a reversal-aware SUM against a live database as the highest-confidence next investigative step among the source-vs-ledger diagnostics.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — Disclose when asked about a specific settlement's ledger reconciliation; do not disclose for aggregate deposit-held totals (v_org_cash_balance, v_advance_balances use the reversal-excluded convention and are not shown to share this pattern).

---

<a id="dq011"></a>
### DQ.011 — Deposit-phantom exposure: deposit held with no live tenant relationship and no settlement

**Severity:** HIGH  
**Why:** 32 allotments hold tenant deposits with no live tenant and no settlement record at all. This is real, unresolved money exposure (the brief's CRITICAL/HIGH test), not merely an analytical inconvenience — kept at HIGH rather than CRITICAL because the exact rupee amount at risk is not separately summed in the evidence.
**Business area:** Deposits

**Affected rows:** 32 allotments
**Affected amount:** Not determinable from exported evidence (v_diag_deposit_phantom does not export a deposit_paid sum; per-row deposit_paid values are in the underlying rows)
**Percentage:** Not meaningfully expressible as a % without a comparable denominator

**Evidence file(s):** H.045 (v_diag_deposit_phantom)

**Root cause / mechanism:** tenant_allotments rows with deposit_paid > 0, staying_status IN ('Exited','Cancelled'), and NO deposit_settlements row at all -- the tenant has left but the deposit was never processed for refund or forfeiture through the settlement workflow.

**Root cause confidence:** PROVEN (direct query result, unambiguous filter conditions)

**Status:** MEASURED

**Metrics affected:** Deposit-held total, refund liability estimation

**Business impact:** Represents real, unquantified-in-aggregate financial exposure (money held that has not been formally refunded or forfeited) -- a genuine operational gap, not merely a reporting inconsistency.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Surface this list as an operational worklist (similar to v_exit_reconciliation_worklist) -- these are real unresolved deposits requiring settlement action, not a data artifact.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If asked about deposit liability or unresolved deposits, always include this 32-allotment set explicitly.

---

<a id="dq013"></a>
### DQ.013 — Duplicate invoices: same allotment + billing_month + invoice_type appearing more than once

**Severity:** HIGH  
**Why:** 356 excess invoice rows (6.8% of all live invoices) spanning ₹4.04M in combined group value, with zero application-level deduplication mechanism in place. Materially affects invoice-count and potential AR/revenue totals.
**Business area:** Invoices / data quality

**Affected rows:** 322 duplicate groups, 356 excess rows beyond one-per-group (of 5214 live invoices)
**Affected amount:** ₹4,040,627.00 combined value across all rows in the 322 groups (H.055 'total' column, summed); exact overcounted/excess amount is NOT separately computable from the exported diagnostic without knowing which row per group is canonical
**Percentage:** 6.8% of live invoices are excess/duplicate rows by count

**Evidence file(s):** H.055 (duplicate_invoices)

**Root cause / mechanism:** No invoice-side deduplication mechanism exists (no invoices_dedup_audit table, no trigger performs invoice duplicate detection) -- contrast with receipts, which have a maintained (if unenforced) dedup-detection table (DQ.014). 319 of 322 groups are invoice_type='regular'.

**Root cause confidence:** PROVEN (row-level groups directly enumerated); cause of WHY duplicates were created (double-billing run, import artifact, etc.) is not determinable from exported evidence

**Status:** MEASURED

**Metrics affected:** Total invoiced revenue, invoice-count-based metrics, AR if duplicates remain unpaid

**Business impact:** Materially affects invoice-count and potentially revenue totals if duplicates were never paid down (would inflate apparent AR); no application-level fix exists yet, so this recurs with every new invoice run until addressed.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Any revenue/AR metric built from raw invoices should be cross-checked against H.055's group list; a de-duplication pass (keep earliest or lowest invoice_number per group) is recommended before this table is treated as ground truth for total invoiced revenue.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If asked about total invoiced revenue or invoice counts, disclose that ~6.8% of invoice rows are flagged as possible duplicates and have not been remediated.

---

<a id="dq015"></a>
### DQ.015 — P&L named category buckets exclude account 5150 (Electricity Payments) entirely; ~5% of total expenses invisible to category breakdown

**Severity:** HIGH  
**Why:** a proven, 100%-consistent (all 57 months) arithmetic gap removes ~5% of total expenses from every category-level P&L view. Materially affects an important KPI (expense-by-category reporting) even though the total_expenses figure itself is unaffected.
**Business area:** Expenses / P&L

**Affected rows:** 57 of 57 months affected (100% of P&L history)
**Affected amount:** ₹1,030,618.00 (57-month total, proven equal to 'unbucketed' exactly in every month)
**Percentage:** 4.96% of total expenses (₹1,030,618 of ₹20,784,832)

**Evidence file(s):** H.017, H.054 (byte-identical), M.016 (v_pnl_by_category SQL), H.016 (coa_accounts)

**Root cause / mechanism:** Account 5150's code prefix ('515') matches none of the 9 hand-written LIKE patterns (owner_rent '510%', maintenance '52%', ..., other_expenses '59%'); the view computes a separate, 10th 'electricity' column ('515%' pattern) that is not included in what H.017 measures as sum_of_buckets.

**Root cause confidence:** PROVEN (arithmetic identity: unbucketed == electricity_column exactly, all 57 months, re-verified from raw CSV)

**Status:** MEASURED

**Metrics affected:** v_pnl_by_category's 9 named category columns, any expense-by-category chart built from them

**Business impact:** A materially-sized cost center (~5% of all expenses, ~Rs.18K/month average) is silently absent from every category-level P&L report built on the 9 named buckets -- proven, reproducible, and currently uncorrected in the source views.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Add 'electricity' as a 10th first-class category in the semantic layer's expense taxonomy; do not present the 9-bucket breakdown as summing to total_expenses without it.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If asked for an expense breakdown by category, always include electricity as its own line, sourced from v_pnl_by_category's separate electricity column.

---

<a id="dq028"></a>
### DQ.028 — EB billing_month text format ('Mon-YY') is incompatible with every other billing_month/period column in the schema ('YYYY-MM')

**Severity:** HIGH  
**Why:** a proven, 100%-consistent (2212 of 2212 rows) date-format incompatibility blocks any month-keyed reconciliation between the EB subsystem and the rest of billing. Materially affects historical EB reconstruction, one of the 13 required metric areas.
**Business area:** EB / electricity

**Affected rows:** 1411 of 1411 electricity_readings rows; 801 of 801 eb_tenant_shares rows (2212 rows total)
**Affected amount:** N/A (formatting defect, not an amount discrepancy)
**Percentage:** 100% of both EB allocation tables

**Evidence file(s):** M.004 (column data types, all billing_month/payment_month columns are text), direct full-column format verification in this pass: electricity_readings and eb_tenant_shares 100% 'Mon-YY' format (e.g. 'Apr-25', 'Mar-26'); invoices, expenses, owner_payments 100% 'YYYY-MM' format, 0 exceptions in either group

**Root cause / mechanism:** electricity_readings and eb_tenant_shares were built or imported using a different billing_month text convention than the rest of the schema. No exported function or trigger normalizes between the two formats.

**Root cause confidence:** PROVEN (100% format verification across both full table populations, cross-checked against 3 other tables' 100% conformance to the other format)

**Status:** MEASURED

**Metrics affected:** Any join or comparison between EB billing_month and invoices.billing_month/expenses.billing_month/owner_payments.payment_month; any code pattern using (billing_month || '-01')::date, which works for 'YYYY-MM' but would fail or misparse for 'Apr-25'

**Business impact:** Blocks any month-keyed reconciliation between the EB subsystem and the rest of the billing system without a manual format-conversion step -- a proven, 100%-consistent schema inconsistency that compounds the electricity blind spot already identified in DQ.015.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** Yes

**Recommended handling in the semantic layer:** Any semantic-layer join between EB tables and invoices/expenses on billing_month must first normalize 'Mon-YY' to 'YYYY-MM' (or vice versa) -- a direct string join or a naive (billing_month || '-01')::date cast will silently fail or misparse for the EB tables.

**Recommended AI disclosure/response behavior:** `BLOCK` — If asked to reconcile EB charges against invoices by month, disclose that a format conversion is required and has not been implemented in any exported view/function.

---

<a id="dq030"></a>
### DQ.030 — get_universal_metrics_series.collections filters on the wrong account code (a non-leaf header account)

**Severity:** HIGH  
**Why:** a proven wrong-account-code defect in a named, callable metrics function (other columns in the same function are correct, only `collections` is wrong). Materially affects a KPI trend series a dashboard could plausibly surface as-is.
**Business area:** Ledger function correctness

**Affected rows:** N/A (code-level defect, not a row-level issue)
**Affected amount:** N/A
**Percentage:** Likely 100% of months return zero or near-zero for this specific column

**Evidence file(s):** FN.get_universal_metrics_series, H.016/M.004 (coa_accounts, proving account 1000 is the 'Assets' header/rollup account, not a leaf posting account), FN.get_universal_metrics_v2 and H.001 (both correctly use 1110/1120 or LIKE '11%' for the same concept)

**Root cause / mechanism:** The function filters account_code = '1000' AND source_table = 'receipts', but journal_lines are posted against leaf accounts (1110 'Cash on Hand', 1120 'Bank - Operating Account'), never against the header account 1000 directly -- confirmed by two other, correctly-coded functions in the same package using the leaf accounts for the identical concept.

**Root cause confidence:** PROVEN at the code level (account role confirmed from coa_accounts, cross-referenced against 2 other correct implementations); runtime output (whether it truly returns zero) not confirmed since no live database is available to execute it

**Status:** MEASURED

**Metrics affected:** get_universal_metrics_series.collections (a monthly collections trend series)

**Business impact:** A materially wrong KPI series (revenue and expenses in the same function use correct LIKE '4%'/'5%' patterns and are unaffected) -- proven from source code, not merely suspected.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** N (the fix is a one-line code change; confirming the runtime symptom would need live execution)

**Blocks an AI/business metric:** Yes

**Recommended handling in the semantic layer:** Do not surface get_universal_metrics_series.collections until the account-code filter is corrected to IN ('1110','1120') or LIKE '11%', matching the rest of the codebase. Substitute get_universal_metrics_v2's totalCollections logic for any trend-series need in the meantime.

**Recommended AI disclosure/response behavior:** `BLOCK` — If asked for a monthly collections trend, do not use this specific function's output; use the corrected v2 logic and note the substitution if pressed on methodology.

---

<a id="dq003"></a>
### DQ.003 — Overlapping tenant_allotments on the same bed (concurrent occupancy conflicts)

**Severity:** MEDIUM
**Business area:** Tenant lifecycle

**Affected rows:** 187 bed x allotment-pair rows
**Affected amount:** Not determinable from exported evidence
**Percentage:** Not meaningfully expressible as a % of 1213 allotments (pairwise overlap count, not row count)

**Evidence file(s):** H.056 (overlapping_allotments)

**Root cause / mechanism:** Two tenant_allotments rows for the same bed have overlapping date ranges (a1_in/a1_out vs a2_in/a2_out). No exported trigger prevents this at write time for tenant_allotments (unlike bed_status_history, which has validate_bed_status_no_overlap -- but that table is empty, 0 rows, so its constraint is not effectively enforced against tenant_allotments directly).

**Root cause confidence:** PROVEN (row-level overlap pairs directly enumerated in H.056)

**Status:** MEASURED

**Metrics affected:** Occupancy (all definitions that count allotments per bed), tenant lifecycle event timelines, revenue attribution by bed

**Business impact:** Understood, bounded scope; already correctly handled by at least one exported function (get_occupancy_intelligence); other bed-day-based calculations that do not merge overlaps would overstate occupied days.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Any per-bed occupancy or revenue calculation should de-duplicate/merge overlapping allotments (as get_occupancy_intelligence does via its gaps-and-islands merge) rather than summing raw allotment spans, which would double-count occupied days for these 187 pairs.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If asked about a specific bed's history and it falls in this set, disclose that overlapping tenancy records exist and the reported occupancy may reflect a merge.

---

<a id="dq006"></a>
### DQ.006 — Receipt source amount vs ledger amount diagnostic diff

**Severity:** MEDIUM
**Business area:** Receipts / ledger

**Affected rows:** 11 receipts traced (H.048); aggregate diff across all receipts
**Affected amount:** Aggregate diff ₹5,340,795.62 (H.001); traced 11-row sample shows individual diffs from -₹16,627.45 to +₹189,267.00
**Percentage:** 6.5% of total receipt value (₹5.34M of ₹81.86M)

**Evidence file(s):** H.001 (v_je_amount_reconciliation), H.048

**Root cause / mechanism:** Receipts with multiple forward postings (repeated edit-and-repost cycles via trg_receipt_journal_post) show ledger_amount roughly proportional to entry_count, consistent with the diagnostic's own query summing raw postings without netting historical corrections. Aggregate P&L/revenue views (v_pnl, v_revenue_by_period) are NOT shown to share this drift, since they use the reversal-excluded v_account_balances convention which nets forward+reversal pairs to zero correctly.

**Root cause confidence:** SUSPECTED (H.048's own generating SQL is not among the 54 exported view definitions, so the exact mechanism cannot be confirmed from source)

**Status:** MEASURED

**Metrics affected:** Individual-receipt ledger tracing; the H.001/H.048 diagnostic's own reliability

**Business impact:** Does not threaten top-line revenue/collections KPIs; threatens confidence in individual-receipt ledger tracing and the diagnostic tool itself pending live-DB re-verification.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Flag any receipt with entry_count > 1 for review before quoting its individual ledger-derived total. Org-level revenue/collections totals are unaffected and remain SAFE.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — For org-level revenue/collections questions: answer normally. For a specific receipt's ledger history: disclose that edited receipts can show inflated ledger totals in this diagnostic.

---

<a id="dq007"></a>
### DQ.007 — Invoice source amount vs ledger amount diagnostic diff, fully row-reconciled

**Severity:** MEDIUM
**Business area:** Invoices / ledger

**Affected rows:** 120 invoices (H.049)
**Affected amount:** ₹2,423,270.00 (H.001 aggregate = H.049 row-sum, exact match)
**Percentage:** 3.3% of total invoiced value (₹2.42M of ₹72.4M)

**Evidence file(s):** H.001, H.049

**Root cause / mechanism:** Concentrated among recent (2026-05 to 2026-08), pending, repeatedly-edited invoices (entry_count up to 15). Consistent with trg_invoice_journal_post's reverse-and-repost cycle accumulating in a non-netted diagnostic query, same hypothesis as DQ.006.

**Root cause confidence:** SUSPECTED (H.049's generating SQL not exported)

**Status:** MEASURED

**Metrics affected:** Individual-invoice ledger tracing

**Business impact:** Fully accounted row-by-row (proven, not merely aggregate); concentrated in still-open pending invoices, so may resolve naturally as those invoices finalize -- worth live-DB monitoring rather than urgent remediation.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Same handling as DQ.006 -- flag high-entry_count invoices; aggregate revenue views unaffected.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — Disclose only when asked about a specific, recently-edited invoice's ledger history.

---

<a id="dq010"></a>
### DQ.010 — 200 journal entries reference a currently soft-deleted receipt

**Severity:** MEDIUM
**Business area:** Ledger integrity

**Affected rows:** 200 of 6085 receipt-sourced journal entries
**Affected amount:** Not determinable from exported evidence
**Percentage:** 3.29%

**Evidence file(s):** H.051, T.receipts_dedup_audit (cross-checked and ruled out as the cause)

**Root cause / mechanism:** Consistent with the documented soft-delete design (trg_receipt_journal_post reverses rather than deletes on soft-delete, leaving the original forward entry in place alongside a new reversal). The specific hypothesis that receipts_dedup_audit's 9 detected duplicate groups explain this was tested directly in this pass and DISPROVEN: of 23 flagged receipt ids, only 11 remain in the export (12 hard-deleted) and none of the 11 are soft-deleted.

**Root cause confidence:** SUSPECTED for the general mechanism (design-consistent); the specific trigger event for each of the 200 is not determinable from exported evidence

**Status:** MEASURED

**Metrics affected:** Receipt-sourced ledger completeness checks

**Business impact:** No evidence of financial misstatement -- invoices (0) and deposit_settlements (0) show none of this pattern, and the mechanism is consistent with intended design for receipts.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No

**Recommended handling in the semantic layer:** Do not flag as corruption by default -- consistent with correct reversal-not-deletion design. Flag only if a metric needs to distinguish delete-driven reversals from edit-driven reversals, which this diagnostic does not separate.

**Recommended AI disclosure/response behavior:** `SAFE` — No disclosure needed for standard queries; if asked specifically 'do deleted receipts still show in the ledger', explain the reversal-based design.

---

<a id="dq012"></a>
### DQ.012 — Deposit settlement anomalies: premature settlements, duplicate open settlements, transfer double-counts

**Severity:** MEDIUM
**Business area:** Deposits

**Affected rows:** 22 rows across 3 anomaly types
**Affected amount:** Not determinable from exported evidence (aggregate not summed in H.046)
**Percentage:** 7.2% of 307 live settlements (unique allotments may be fewer than 22 due to overlap across anomaly types)

**Evidence file(s):** H.046 (v_deposit_ledger_anomalies), FN.validate_deposit_settlement

**Root cause / mechanism:** validate_deposit_settlement is a write-time (BEFORE INSERT/UPDATE) constraint that blocks deductions on a non-exited allotment at the moment of writing, but does not re-validate existing rows if the allotment's status later changes -- consistent with, but not proven to be, the cause of the 'premature_settlement' anomaly subtype.

**Root cause confidence:** SUSPECTED

**Status:** MEASURED

**Metrics affected:** Deposit settlement validity, deposit-held balance by tenant

**Business impact:** Bounded, identified set requiring case-by-case review; does not invalidate the deposit system as a whole.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Route these 22 rows to a manual-review worklist; do not auto-correct.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If asked about a specific tenant/allotment in this set, disclose the anomaly type and details field verbatim.

---

<a id="dq014"></a>
### DQ.014 — Duplicate receipts detected but not remediated; some duplicates hard-deleted outside the soft-delete convention

**Severity:** MEDIUM
**Business area:** Receipts / data quality

**Affected rows:** 9 detection groups, 23 receipt ids named; only 11 of 23 ids still exist in the export (12 hard-deleted)
**Affected amount:** Sum of duplicate_count=2 groups' amount_paid values, e.g. Rs.1,000-20,000 per group (individual values in T.receipts_dedup_audit); aggregate not computed here
**Percentage:** 0.15% of 5858 live receipts implicated by count

**Evidence file(s):** T.receipts_dedup_audit, T.receipts (cross-checked in this pass)

**Root cause / mechanism:** receipts_dedup_audit is a one-time detection pass (single detected_at timestamp, 2026-04-22) with no automated remediation trigger. Manual/other process subsequently hard-deleted 12 of the 23 flagged receipts (bypassing the system's otherwise-consistent soft-delete convention); the remaining 11 are still live, undeduplicated duplicates.

**Root cause confidence:** PROVEN (directly cross-checked: 11 of 23 ids remain, 0 of those 11 are soft-deleted)

**Status:** MEASURED

**Metrics affected:** Total collections if duplicates remain live and unremediated

**Business impact:** Small in scale (11 live receipts) but demonstrates that detected data-quality issues in this system do not automatically get fixed -- relevant precedent for DQ.013's larger, entirely-undetected invoice duplicates.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Treat the 11 still-live flagged receipt ids as a known duplicate-collections set; recommend soft-deleting the later duplicate in each pair/group per the existing convention rather than hard-deleting.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If asked about collections totals or a specific tenant with a flagged duplicate, disclose the detection but note remediation is incomplete.

---

<a id="dq017"></a>
### DQ.017 — Owner-rent date-basis mismatch causes 7 of 54 months to show a nonzero ledger-vs-payments-schedule difference despite the totals matching exactly

**Severity:** MEDIUM
**Business area:** Owner payments, P&L

**Affected rows:** 7 of 54 months
**Affected amount:** Net ₹0.00 across all 54 months (differences cancel); individual month diffs not separately summed here
**Percentage:** 13% of months affected at the monthly grain

**Evidence file(s):** H.030 (pnl_owner_rent_vs_payments)

**Root cause / mechanism:** Three different date bases compete for 'which month' an owner payment belongs to: the ledger-posting trigger (normalize_owner_payment_journal_dates) uses bill_date; get_universal_metrics_v2's substitution also uses bill_date; but v_diag_owner_rent_missing_from_profit groups by COALESCE(paid_date, due_date) instead -- a third, different basis. H.030 appears to compare the ledger's bill_date-based monthly figure against a payments-schedule figure using a different date column, producing month-level shifts that net to zero overall.

**Root cause confidence:** SUSPECTED (the date-basis mismatch is proven to exist among the three functions; H.030's own exact grouping column is not confirmed since its SQL is not among the 54 exported views)

**Status:** MEASURED

**Metrics affected:** Month-by-month owner-rent P&L trend (not the annual/lifetime total, which is proven exact)

**Business impact:** Does not affect the annual/lifetime owner-rent total (proven exact); can cause a monthly P&L trend line to show a false bump or dip in the 7 affected months.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Pick one date basis (recommend bill_date, matching the ledger trigger) for all owner-rent-by-month reporting; do not mix v_diag_owner_rent_missing_from_profit's paid_date/due_date basis with the ledger's bill_date basis in the same trend line.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If asked about owner rent in a specific month, note that month-level attribution can shift by up to one posting cycle depending on which date field is used; the annual total is reliable regardless.

---

<a id="dq018"></a>
### DQ.018 — v_tenant_aging buckets are CURRENT_DATE-dependent and not reproducible from a frozen export without fixing an as-of date

**Severity:** MEDIUM
**Business area:** AR aging

**Affected rows:** 644 rows (F.008, all rows affected structurally)
**Affected amount:** N/A (bucket totals sum correctly; only the day-bucket assignment shifts)
**Percentage:** 100% of aging rows are snapshot-dependent by construction

**Evidence file(s):** M.016 (v_tenant_aging SQL), M.002/M.099 (snapshot timestamps)

**Root cause / mechanism:** v_tenant_aging's bucket filters use CURRENT_DATE - charge_date, evaluated at query time. The exported CSV (F.008) reflects buckets computed at whatever moment inside the 09:02-11:18 export window the query ran, not a fixed historical fact.

**Root cause confidence:** PROVEN (direct SQL reading -- this is expected application behavior, not a defect)

**Status:** MEASURED

**Metrics affected:** AR aging bucket distribution (0-30/31-60/61-90/90+)

**Business impact:** Reproducibility hazard only; the underlying AR totals are stable, only the day-bucket labels shift over time.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Any offline reconstruction of aging buckets must fix an explicit as-of date (recommend M.002's 2026-08-29 timestamp) and label every bucket with that date; never compare a reconstructed bucket against F.008 without accounting for elapsed time.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — Always state the as-of date when reporting an aging bucket.

---

<a id="dq020"></a>
### DQ.020 — All 345 owner_payments ledger postings occurred in a single ~82-minute batch, not incrementally

**Severity:** MEDIUM
**Business area:** Owner payments

**Affected rows:** 345 of 345 owner_payments rows; 410 forward journal entries
**Affected amount:** ₹19,019,250.00 (full owner-rent ledger total, all posted in one batch)
**Percentage:** 100% of owner_payments postings

**Evidence file(s):** M.025 (owner_payments.created_at, 1 distinct month), H.004 (je_by_source_dates, posted_at range 2026-08-13 09:14:24 to 10:36:58)

**Root cause / mechanism:** A migration/backfill event on 2026-08-13 posted all historical owner-payment ledger entries at once, rather than owner payments being posted incrementally as they occurred over 2022-2026.

**Root cause confidence:** PROVEN (created_at and posted_at ranges directly measured)

**Status:** MEASURED

**Metrics affected:** Any owner-payment posting-time or cash-flow-timing analysis; interacts with DQ.017's date-basis issue

**Business impact:** No misstatement of amounts (proven PERFECT match to source in H.001); relevant context for interpreting any 'when was this posted' question, not a financial-accuracy issue.

**Offline-fixable from exported evidence:** N/A  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Do not interpret owner_payments' posted_at/created_at as reflecting when the underlying payment activity actually happened; always use bill_date (or the specific date field the metric calls for) instead.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If asked about posting-time cash flow patterns, note that owner-payment ledger entries were bulk-migrated on 2026-08-13 and do not reflect real-time posting.

---

<a id="dq025"></a>
### DQ.025 — NULL organization_id rows in 4 tables

**Severity:** MEDIUM
**Business area:** Data quality / organization grain

**Affected rows:** whatsapp_events 600/1943; ticket_logs 65/8239; payroll_sync 6/18; email_templates 3/4
**Affected amount:** N/A (operational tables, not financial)
**Percentage:** whatsapp_events 30.9%; ticket_logs 0.79%; payroll_sync 33.3%; email_templates 75.0%

**Evidence file(s):** M.007 (organization_grain)

**Root cause / mechanism:** Not determinable from exported evidence -- no trigger or default-value mechanism for organization_id backfill was found among the 25 exported function bodies for these specific tables.

**Root cause confidence:** UNVERIFIED

**Status:** MEASURED

**Metrics affected:** Any org-scoped rollup of ticket_logs (maintenance activity counts) or whatsapp_events; email_templates/payroll_sync are configuration-scale tables, low metric impact

**Business impact:** Single-organization dataset in this snapshot (distinct_orgs=1 everywhere data exists) limits practical impact today, but the exclusion pattern would compound in a true multi-org deployment.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Any org-filtered query (e.g. WHERE organization_id = X) will silently drop these NULL-org rows via an inner join/equality filter -- use an explicit NULL-inclusive path or document the exclusion for ticket_logs specifically, since it is the only one of the 4 with real analytical volume (8239 rows).

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If a maintenance-activity metric total looks lower than expected, disclose that 0.79% of ticket_logs rows have no organization_id and may be silently excluded by org-scoped filters.

---

<a id="dq026"></a>
### DQ.026 — 4 of 5 declared polymorphic relationships have no exported orphan-check diagnostic

**Severity:** MEDIUM
**Business area:** Ledger integrity / referential completeness

**Affected rows:** N/A (verification coverage gap, not a measured row count)
**Affected amount:** N/A
**Percentage:** N/A

**Evidence file(s):** M.011 (polymorphic_refs, 5 relationships declared), H.025 (orphan check exists for journal_entries.source_id against invoices/receipts/expenses only, 0 orphans), H.051 (covers deposit_settlements/invoices/receipts missing_source, all 0), M.009 (confirms no FK is declared for any of the 5 polymorphic columns, by design)

**Root cause / mechanism:** Polymorphic references cannot carry a single-table FK, so referential integrity for these columns can only be checked by an explicit, purpose-built query -- and only journal_entries.source_id against 4 of its ~9 possible source_table values (invoices, receipts, expenses, deposit_settlements) was exported. owner_payments, tenant_adjustments, assets, asset_payments, and eb_payments as journal_entries.source_id targets, plus invoices.reference_id, tenant_adjustments.reference_id, tenant_transactions.reference_id, and financial_audit_log.source_id, have no exported orphan check at all.

**Root cause confidence:** PROVEN (coverage gap itself is directly enumerable from the manifest)

**Status:** UNVERIFIED

**Metrics affected:** Confidence in referential integrity for owner_payments/tenant_adjustments/assets/asset_payments/eb_payments-sourced journal entries, invoices.reference_id, tenant_adjustments.reference_id, tenant_transactions.reference_id, financial_audit_log.source_id

**Business impact:** A verification gap, not a proven defect -- but means the CRITICAL/HIGH findings elsewhere in this report about journal_entries.source_id (DQ.006-008) cannot be assumed representative of owner_payments/assets/eb_payments-sourced entries, which were never checked.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No

**Recommended handling in the semantic layer:** Do not assume these polymorphic relationships are orphan-free; the 0-orphan results proven for invoices/receipts/expenses/deposit_settlements must not be generalized to the other 5+ source_table values or the 3 other polymorphic columns.

**Recommended AI disclosure/response behavior:** `UNVERIFIED` — If asked to confirm referential completeness of the ledger overall, state that only a subset of polymorphic relationships were verified and the rest are unverified.

---

<a id="dq027"></a>
### DQ.027 — Maintenance ticket view/actual count mismatch, and two independent cost-linkage paths that can disagree

**Severity:** MEDIUM
**Business area:** Maintenance

**Affected rows:** 2-ticket gap (1613 view vs 1611 actual, H.019); linkage-path disagreement scope not separately quantified
**Affected amount:** Not determinable from exported evidence
**Percentage:** 0.12% (2 of 1611) for the count gap

**Evidence file(s):** H.018, H.019, H.058, M.016 (both view definitions)

**Root cause / mechanism:** H.019's 1613-vs-1611 gap is not traced to a specific view or cause in the exported diagnostics. Separately, v_maintenance_metrics links cost via ticket_resolutions -> expenses.ticket_resolution_id and dates by ticket creation month, while v_maintenance_by_issue_type links via expenses.issue_type_id directly (a separate FK from the ticket's own issue type) and dates by expense_date -- these can disagree whenever an expense's issue_type_id differs from its resolution's ticket's issue type, or when creation and expense months differ.

**Root cause confidence:** SUSPECTED (linkage-path divergence is proven structurally from SQL; the 1613-vs-1611 count gap's specific cause is not determinable from exported evidence)

**Status:** MEASURED

**Metrics affected:** v_maintenance_metrics vs v_maintenance_by_issue_type cost totals; ticket counts

**Business impact:** Does not affect total_expenses (unconditional sum of all 5xxx accounts, DQ.015's scope); limited to maintenance-specific category/count reporting.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** Partially — see SHOW_BOTH handling below

**Recommended handling in the semantic layer:** Treat 'cost by property/month' and 'cost by issue type' as two distinct metrics; never sum or directly compare them as the same population without confirming issue-type consistency between a ticket and its linked expense.

**Recommended AI disclosure/response behavior:** `SHOW_BOTH` — If a maintenance-cost-by-category question is asked, disclose that a separately-computed property-level total exists and may not exactly match the category breakdown's sum.

---

<a id="dq021"></a>
### DQ.021 — eb_monitoring_readings is a single-day snapshot, not a time series

**Severity:** LOW
**Business area:** EB / electricity

**Affected rows:** 35 of 35 rows (100%)
**Affected amount:** N/A
**Percentage:** 100%

**Evidence file(s):** M.025 (eb_monitoring_readings date range = 1 day, 2026-08-18)

**Root cause / mechanism:** All 35 rows share reading_date=2026-08-18 exactly; this table appears to capture one monitoring run, not an ongoing feed.

**Root cause confidence:** PROVEN (direct date-range measurement)

**Status:** MEASURED

**Metrics affected:** Any EB danger-monitoring trend or historical alert metric

**Business impact:** Limits EB risk-monitoring analysis to a single date; no financial impact.

**Offline-fixable from exported evidence:** N/A  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Do not build a trend chart from this table; treat it as a single point-in-time snapshot (6 of 35 apartments flagged is_danger=true on that date).

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If asked about EB danger trends over time, state that only one snapshot date (2026-08-18) is available.

---

<a id="dq022"></a>
### DQ.022 — Placeholder/epoch date in apartments.start_date

**Severity:** LOW
**Business area:** Data quality / apartments

**Affected rows:** 2 of 43 apartments
**Affected amount:** N/A
**Percentage:** 4.65%

**Evidence file(s):** M.025 (rows_before_2019=2, min=1899-12-30), direct row lookup in this pass (apartment codes D13A, D23B, both status=Not-Active)

**Root cause / mechanism:** 1899-12-30 is the classic spreadsheet/Excel 'day zero' epoch date, strongly indicating a null or blank numeric value was misinterpreted as a date during an import (both rows share the identical created_at timestamp 2026-03-16 17:47:27, consistent with a single bulk-import batch).

**Root cause confidence:** SUSPECTED (epoch-date pattern is a well-known import artifact signature; not proven by tracing the specific import job)

**Status:** MEASURED

**Metrics affected:** Apartment availability-window calculations (get_occupancy_intelligence's GREATEST(start_date, p_from) clamp)

**Business impact:** Minimal -- confined to 2 already-inactive apartments; would only matter if either were reactivated without the date being fixed first.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No

**Recommended handling in the semantic layer:** Both affected apartments are status=Not-Active, so this does not currently distort any Live-bed occupancy calculation; still recommend correcting or nulling the placeholder value.

**Recommended AI disclosure/response behavior:** `SAFE` — No disclosure needed for standard queries (Not-Active apartments are excluded from live occupancy anyway).

---

<a id="dq023"></a>
### DQ.023 — Corrupt year in tenant_transactions.date (0206-03-27 instead of a plausible 2026 date)

**Severity:** LOW
**Business area:** Data quality / tenant_transactions

**Affected rows:** 1 of 16,451 rows
**Affected amount:** Not determinable from exported evidence (amount field for this specific row not isolated in this pass)
**Percentage:** 0.006%

**Evidence file(s):** M.025 (tenant_transactions.date, rows_before_2019=1, min=0206-03-27)

**Root cause / mechanism:** A 4-digit year transposition (0206 for what is almost certainly 2026), consistent with a data-entry or import parsing error.

**Root cause confidence:** SUSPECTED (transposition pattern is a reasonable inference, not confirmed against a source record)

**Status:** MEASURED

**Metrics affected:** Any MIN(date) or unbounded date-range calculation over tenant_transactions

**Business impact:** Negligible in isolation; already subsumed by DQ.019's broader recommendation not to rely on this table.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No

**Recommended handling in the semantic layer:** Exclude or clamp this single row before computing any MIN(date)/date-range statistic over tenant_transactions; irrelevant given tenant_transactions is already BLOCKed for dues purposes (DQ.019).

**Recommended AI disclosure/response behavior:** `SAFE` — No disclosure needed given tenant_transactions is not used as a source of truth.

---

<a id="dq024"></a>
### DQ.024 — Post-snapshot-dated (future) rows in financial/tenancy tables

**Severity:** LOW
**Business area:** Data quality / cross-cutting

**Affected rows:** Small counts per column (2-11 rows each) across invoices.invoice_date/due_date, journal_entries.entry_date, deposit_settlements.settlement_date, tenant_allotments.actual_exit_date/estimated_exit_date, tenant_notices.exit_date, maintenance_tickets.sla_deadline, organization_subscriptions.current_period_end, and others (39 columns total show after_today > 0 per M.025)
**Affected amount:** Not determinable from exported evidence
**Percentage:** All well under 1% of their respective tables

**Evidence file(s):** M.025 (temporal_profile, rows_after_today column, full list in evidence_integrity_report.md section 9.1c)

**Root cause / mechanism:** Some are legitimate forward-dated business records (e.g. a lease renewal_date or subscription current_period_end in the future is expected). Others (e.g. journal_entries.entry_date up to 2026-09-20, 3 weeks past the 2026-08-29 snapshot) are less obviously legitimate and not individually traced to a cause.

**Root cause confidence:** SUSPECTED for which rows are legitimate vs anomalous (not individually adjudicated)

**Status:** MEASURED

**Metrics affected:** Any time-series metric with an implicit 'up to today' assumption; period-bucket reports for the current/future period

**Business impact:** Low individually; recorded because unbounded date-range logic elsewhere in this evidence package (e.g. get_bed_occupancy_timeline's LEAST(p_to, CURRENT_DATE) clamp) shows the application itself treats this as a real hazard worth guarding against.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Any 'as of today' filter should clamp to the snapshot date (2026-08-29) or CURRENT_DATE at query time, not assume all dated rows are historical.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — If a time-series answer could be affected by forward-dated rows, note the snapshot boundary.

---

<a id="dq031"></a>
### DQ.031 — Non-atomic export: 5 tables show +1 row vs the row-count snapshot due to live writes during the 2h16m export window

**Severity:** LOW
**Business area:** Package integrity / export process

**Affected rows:** 5 tables, 1 row each (profiles, user_roles, maintenance_tickets, ticket_logs, ai_logs); bot_conversations shows -8 for an unrelated PII-export reason
**Affected amount:** N/A
**Percentage:** <0.02% of any affected table

**Evidence file(s):** M.002, M.006, M.099 (snapshot timestamps), evidence_integrity_report.md section 3 (full trace)

**Root cause / mechanism:** Three real user events occurred during the export window (2026-08-29 09:02-11:18): one user signup, one maintenance ticket raised, one AI diagnosis call -- all confirmed by timestamp to be after the row-count snapshot was taken.

**Root cause confidence:** PROVEN (each extra row individually located and timestamped)

**Status:** MEASURED

**Metrics affected:** None in financial/ledger/occupancy/tenancy scope

**Business impact:** None. Included for completeness per the brief's request to consolidate all H.*/metadata findings.

**Offline-fixable from exported evidence:** N/A  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No

**Recommended handling in the semantic layer:** No action needed -- fully traced and confined to operational tables outside financial/ledger/occupancy/tenancy scope.

**Recommended AI disclosure/response behavior:** `SAFE` — No disclosure needed.

---

<a id="dq032"></a>
### DQ.032 — market schema declared IN_SCOPE but 0 of 17 tables were exported

**Severity:** LOW
**Business area:** Package integrity / scope

**Affected rows:** 421 rows across 7 non-empty market tables (of 17 total) never exported; the other 10 market tables are empty
**Affected amount:** N/A (competitive-pricing data, not financial)
**Percentage:** 100% of market schema data unavailable offline

**Evidence file(s):** M.000 (schema_scope, market marked IN_SCOPE), H.037 (market_schema_rowcounts, 7 of 17 tables with row counts)

**Root cause / mechanism:** Not determinable from exported evidence -- no market-schema CSV was exported despite the schema being marked in-scope in the schema inventory.

**Root cause confidence:** UNVERIFIED

**Status:** UNVERIFIED

**Metrics affected:** None of the 13 required metric areas depend on the market schema

**Business impact:** A stated-scope shortfall against the package's own inventory, but does not block any of the 13 required business metric areas.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No

**Recommended handling in the semantic layer:** Exclude market-schema metrics (competitor pricing, locality intelligence) from the semantic layer entirely until live-database export is available.

**Recommended AI disclosure/response behavior:** `UNVERIFIED` — If asked about competitor pricing or market intelligence, state that this data was not exported and is unavailable offline.

---

<a id="dq009"></a>
### DQ.009 — v_je_stub_pollution diagnostic re-run returns rows in different order (H.003 vs H.003b)

**Severity:** INFORMATIONAL
**Business area:** Ledger / diagnostics

**Affected rows:** 9 rows (same set, transposed order)
**Affected amount:** N/A
**Percentage:** N/A

**Evidence file(s):** H.003, H.003b

**Root cause / mechanism:** The view has no deterministic ORDER BY; Postgres does not guarantee row order without one.

**Root cause confidence:** PROVEN

**Status:** MEASURED

**Metrics affected:** None -- row set is identical

**Business impact:** None. Recorded for completeness since the brief specifically asked about reversal-handling/diagnostic-view evidence.

**Offline-fixable from exported evidence:** Yes  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No

**Recommended handling in the semantic layer:** Add an explicit ORDER BY if row order ever matters for a downstream consumer; otherwise no action needed.

**Recommended AI disclosure/response behavior:** `SAFE` — No disclosure needed -- not a data discrepancy.

---

<a id="dq029"></a>
### DQ.029 — 30 declared public tables are empty (0 rows), including two structurally significant ones (ledger_entries, receipt_allocations)

**Severity:** INFORMATIONAL
**Business area:** Data quality / schema

**Affected rows:** 30 tables, 0 rows each
**Affected amount:** N/A
**Percentage:** 22.9% of 131 public tables

**Evidence file(s):** M.006 (row_counts_exact), evidence_integrity_report.md section 5

**Root cause / mechanism:** Superseded features (ledger_entries appears to be an earlier ledger implementation replaced by journal_entries/journal_lines) or features whose intended write path was never activated in the exported function set (receipt_allocations, bed_status_history).

**Root cause confidence:** SUSPECTED for ledger_entries/receipt_allocations being genuinely superseded vs merely unused; PROVEN that all 30 are empty (exact COUNT(*) from M.006)

**Status:** MEASURED EMPTY

**Metrics affected:** ledger_entries (superseded by journal_entries/journal_lines); receipt_allocations (see conflicts.md C.024, receipt-to-invoice settlement is NOT allocation-based); bed_status_history (no bed-status audit trail exists, historical occupancy must come from tenant_allotments dates)

**Business impact:** None currently -- correctly identified as empty rather than missing; recorded because an empty table can otherwise be mistaken for an export gap.

**Offline-fixable from exported evidence:** N/A  |  **Live-DB investigation/fix required:** No

**Blocks an AI/business metric:** No

**Recommended handling in the semantic layer:** Exclude these 30 tables from the semantic layer's active metric catalog; do not build any metric expecting data from ledger_entries or receipt_allocations specifically (both have proven alternative live mechanisms documented in business_logic.md/conflicts.md).

**Recommended AI disclosure/response behavior:** `SAFE` — No disclosure needed for normal queries; if a user asks about 'the ledger_entries table' or 'receipt allocations' by name, state they are empty and explain the superseding mechanism.

---

## Cross-reference to `conflicts.md`

This report and `conflicts.md` describe the same underlying evidence from two different angles —
`conflicts.md` pairs *competing definitions* against each other; this report ranks *quality
issues* by severity and offline-fixability. Several DQ entries are the row-level/severity view
of a conflict already recorded there; neither document repeats the other's full analysis.

| DQ ID | Related conflict(s) in `conflicts.md` |
|---|---|
| DQ.001 | C.004 (application invoice balance vs ledger-derived settlement) |
| DQ.002, DQ.019 | C.001, C.003, C.005 (AR/tenant-dues definition family) |
| DQ.004, DQ.005 | C.006, C.007, C.008, C.009 (occupancy definition family) |
| DQ.006 | C.014 (receipt source vs ledger amount) |
| DQ.007 | C.015 (invoice source vs ledger amount) |
| DQ.008 | C.016 (deposit settlement source vs ledger amount) |
| DQ.010 | C.018 (soft-deleted source vs surviving journal entries) |
| DQ.013, DQ.014 | C.020 (duplicate invoice/receipt definitions) |
| DQ.015 | C.012 (P&L named buckets vs total expenses) |
| DQ.016, DQ.017, DQ.020 | C.010, C.011 (profit definitions, owner-rent treatment) |
| DQ.018 | C.019 (aging bucket snapshot dependence) |
| DQ.026 | C.017 (live source counts vs JE source counts, partial coverage) |
| DQ.027 | C.023 (maintenance cost linkage) |
| DQ.028 | C.013 (electricity account 5150), extended to a schema-level format defect not previously isolated as its own conflict |
| DQ.030 | C.021 (get_universal_metrics_series collections bug) |

DQ.003, DQ.009, DQ.011, DQ.012, DQ.021-DQ.025, DQ.029, DQ.031, DQ.032 are severity/quality
findings without a matching semantic-conflict entry — they are single-sided data-quality facts,
not two competing definitions, so `conflicts.md` does not carry them.

---

## Top 5 business-impact issues

Ranked by potential magnitude of financial/decision misstatement, not by severity label alone
(all five happen to be the four CRITICAL findings plus the highest-magnitude HIGH finding):

1. **DQ.019** — `tenant_transactions` frozen legacy ledger, ~120x (₹9.97M vs ₹83.3K) larger than
   the live ledger. Catastrophic if ever mistakenly surfaced as tenant dues.
2. **DQ.016** — `get_universal_metrics` v1 profit omits owner rent entirely: proven 36.6%
   profit overstatement (₹70.94M vs ₹51.92M) across the full reconstructable history.
3. **DQ.002** — Four tenant-balance definitions disagree by up to ~120x with no evidence-proven
   winner; blocks any single confident "what does this tenant owe" answer.
4. **DQ.001** — 42.7% of live invoices (2227 of 5214) have an internally inconsistent
   paid/balance record — the single largest-population CRITICAL finding.
5. **DQ.013** — 356 excess/duplicate invoice rows (6.8% of all live invoices) spanning ₹4.04M in
   combined group value, with no deduplication mechanism in the application at all.

---

## Answers to the report's required totals

| Question | Answer |
|---|---|
| Total DQ issues | **32** |
| CRITICAL | **4** — DQ.001, DQ.002, DQ.016, DQ.019 |
| HIGH | **8** — DQ.004, DQ.005, DQ.008, DQ.011, DQ.013, DQ.015, DQ.028, DQ.030 |
| MEDIUM | **12** — DQ.003, DQ.006, DQ.007, DQ.010, DQ.012, DQ.014, DQ.017, DQ.018, DQ.020, DQ.025, DQ.026, DQ.027 |
| LOW | **6** — DQ.021, DQ.022, DQ.023, DQ.024, DQ.031, DQ.032 |
| INFORMATIONAL | **2** — DQ.009, DQ.029 |
| UNVERIFIED (status) | **2** — DQ.026, DQ.032 |
| BLOCK metrics | **7** — DQ.001, DQ.002, DQ.005, DQ.016, DQ.019, DQ.028, DQ.030 |
| DISCLOSE metrics | **15** — DQ.003, DQ.006, DQ.007, DQ.008, DQ.011, DQ.012, DQ.013, DQ.014, DQ.015, DQ.017, DQ.018, DQ.020, DQ.021, DQ.024, DQ.025 |
| SHOW_BOTH metrics | **2** — DQ.004, DQ.027 |
| SAFE metrics | **6** — DQ.009, DQ.010, DQ.022, DQ.023, DQ.029, DQ.031 |
| UNVERIFIED (ai_handling) | **2** — DQ.026, DQ.032 |

7 + 15 + 2 + 6 + 2 = **32**, matching the total exactly. These figures are read directly from
`data_quality_registry.csv`, which is the source of truth for all counts in this section.

---

## Next recommended deliverable

**`metric_reconstruction.md` (E) + offline validation scripts (F).** Every metric it defines
must cite, per the brief's own requirement, which of this report's DQ entries and which of
`conflicts.md`'s C entries it inherits — this report's `ai_handling` column
(`SAFE`/`DISCLOSE`/`SHOW_BOTH`/`BLOCK`/`UNVERIFIED`) is the direct input to metric_reconstruction's
"known limitations" field for each metric, and `data_quality_registry.csv` is the machine-readable
join key for building that mapping without re-deriving it by hand.
