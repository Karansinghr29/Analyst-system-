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
| [DQ.011](#dq011) | HIGH | Deposit-phantom exposure: deposit held with no live tenant relationship and... | 32 allotments | ₹722,700.00 | Deposit-held total, refund liability estimation | MEASURED |
| [DQ.013](#dq013) | HIGH | Duplicate invoices: same allotment + billing_month + invoice_type appearing... | 322 duplicate groups, 356 exces... | ₹4,040,627.00 combined va... | Total invoiced revenue, invoice-count-based metrics, AR i... | MEASURED |
| [DQ.015](#dq015) | HIGH | P&L named category buckets exclude account 5150 (Electricity Payments) enti... | 57 of 57 months affected (100% ... | ₹1,030,618.00 (57-month t... | v_pnl_by_category's 9 named category columns, any expense... | MEASURED |
| [DQ.028](#dq028) | HIGH | EB billing_month text format ('Mon-YY') is incompatible with every other bi... | 1411 of 1411 electricity_readin... | N/A (formatting defect, n... | Any join or comparison between EB billing_month and invoi... | MEASURED |
| [DQ.030](#dq030) | HIGH | get_universal_metrics_series.collections filters on the wrong account code ... | N/A (code-level defect, not a r... | N/A | get_universal_metrics_series.collections (a monthly colle... | MEASURED |
| [DQ.033](#dq033) | HIGH | Payroll materially absent from the ledger: 2 of 3 team payments never posted; the... | 2 of 3 team_payments unposted; 71... | ₹45,420.00 proven absent... | M.EXP.001, M.EXP.002, M.PNL.001 (M.PROFIT.001 already BLOCK) | MEASURED |
| [DQ.034](#dq034) | HIGH | Two maintenance-cost definitions disagree by 23.51x; the ticket-linked subset is shown as 100% of... | 450 of 465 maintenance expenses ha... | ₹648,240.00 difference... | M.MAINT.002, M.EXP.002 (M.MAINT.001/M.EXP.001/M.PNL.001 unaffected) | CONFLICTING DEFINITIONS EXIST |
| [DQ.035](#dq035) | HIGH | Five populations each answer "deposit exposure"; two overlap by ₹386,500.00 becaus... | 32 flagged allotments across 25 t... | ₹722,700.00, of which ₹386,500.00... | M.RISK.004, M.RISK.003, M.DEP.001 | CONFLICTING DEFINITIONS EXIST |
| [DQ.036](#dq036) | HIGH | v_tenant_aging is net ledger movement by posting age, not overdue aging; its bucke... | 644 rows (F.008); 3 future-dated... | bucket sum ₹78,329.85 vs total ₹83,297.85, gap ₹4,968.00... | M.RISK.002 | CONFLICTING DEFINITIONS EXIST |
| [DQ.037](#dq037) | HIGH | Every tenant-dues definition mixes current and ended tenancies; the sign of the ans... | 626 allotments with AR activity, ... | ₹83,297.85 = current −₹26,494.15 + ended +₹109,792.00... | M.AR.001A, M.AR.001B, M.AR.001C, M.AR.001D | CONFLICTING DEFINITIONS EXIST |
| [DQ.003](#dq003) | MEDIUM | Overlapping tenant_allotments on the same bed (concurrent occupancy conflicts) | 187 bed x allotment-pair rows | Not determinable from exp... | Occupancy (all definitions that count allotments per bed)... | MEASURED |
| [DQ.006](#dq006) | MEDIUM | Receipt source vs ledger amount: ₹16,282.45 residual; H.001's ₹5,340,795.62 is a formula artifact | 4 receipts (of the 11 traced in H.048); 3 li... | ₹16,282.45 residual (0.02%)... | M.COL.003 vs M.COL.001 reconciliation; individual-rece... | MEASURED |
| [DQ.007](#dq007) | MEDIUM | Invoice source amount vs ledger amount diagnostic diff, fully row-reconciled | 120 invoices (H.049) | ₹2,423,270.00 (H.001 aggr... | Individual-invoice ledger tracing | MEASURED |
| [DQ.010](#dq010) | MEDIUM | 200 journal entries reference a currently soft-deleted receipt | 200 of 6085 receipt-sourced jou... | Not determinable from exp... | Receipt-sourced ledger completeness checks | MEASURED |
| [DQ.012](#dq012) | MEDIUM | Deposit settlement anomalies: premature settlements, duplicate open settlem... | 22 rows across 3 anomaly types | Not determinable from exp... | Deposit settlement validity, deposit-held balance by tenant | MEASURED |
| [DQ.014](#dq014) | MEDIUM | Duplicate receipts detected but not remediated; some duplicates hard-delete... | 9 detection groups, 23 receipt ... | Sum of duplicate_count=2 ... | Total collections if duplicates remain live and unremediated | MEASURED |
| [DQ.017](#dq017) | MEDIUM | Owner-rent date-basis mismatch causes 7 of 54 months to show a nonzero ledg... | 7 of 54 months | Net ₹0.00 across all 54 m... | Month-by-month owner-rent P&L trend (not the annual/lifet... | MEASURED |
| [DQ.018](#dq018) | MEDIUM | v_tenant_aging buckets are CURRENT_DATE-dependent and not reproducible from... | 644 rows (F.008, all rows affec... | ₹4,968.00 bucket gap; buckets... | AR aging bucket distribution (0-30/31-60/61-90/90+) | MEASURED |
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
**Affected amount:** ₹722,700.00 (sum of `deposit_paid` over the 32 flagged allotments, computed directly from `tenant_allotments`; `v_diag_deposit_phantom` itself exports no summed amount)
**Percentage:** Not meaningfully expressible as a % without a comparable denominator

**Evidence file(s):** H.045 (v_diag_deposit_phantom)

**Root cause / mechanism:** tenant_allotments rows with deposit_paid > 0, staying_status IN ('Exited','Cancelled'), and NO deposit_settlements row at all -- the allotment has ended and no settlement was recorded against it. This does NOT mean the deposit was never processed for every row: deposits transfer between a tenant's allotments through manual journal entries, and at least 13 of the 32 flagged amounts are still represented in the ledger through another allotment of the same tenant ([DQ.035](#dq035)). 15 have no account 2100 balance for the tenant at all and 4 are partly represented. What happened to each is Not determinable from exported evidence.

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

<a id="dq033"></a>
### DQ.033 — Payroll is materially absent from the ledger: 2 of 3 team payments never posted, and the 1 posted salary payment is classified outside the salaries bucket

**Severity:** HIGH
**Business area:** Payroll / ledger completeness

**Affected rows:** 2 of 3 `team_payments` rows unposted (1 posted); 71 `team_salary_bills` rows, 0 posted; 18 `payroll_sync` rows, 0 posted; 0 journal lines on account `5700 Salaries & Benefits` and 0 on `5310 Housekeeping - Salaries`
**Affected amount:** **₹45,420.00 proven absent from the ledger** — a ₹18,000.00 team payment and a ₹27,420.00 team payment, both `payment_date` 2026-04-27, both `payment_month` 2026-03. Neither has an `expenses` row, neither has a journal entry, neither has a ledger posting. A further ₹2,420.00 **is** in the ledger, but on `5900 Other Expenses`.
**Percentage:** 0.219% of M.EXP.001 (₹45,420.00 of ₹20,784,831.96)

**Evidence file(s):** T.team_payments, T.team_salary_bills, T.payroll_sync, T.expenses, T.expense_categories, T.journal_lines, T.journal_entries, T.coa_accounts, FN.TRG (55 triggers, none on the three payroll tables), FN.trg_expense_journal_post, M.009 (declared FK `expenses_team_payment_id_fkey`), M.006

**What is proven.** Proven from exported evidence:

1. **₹45,420.00 is absent from the ledger.** The ₹18,000.00 and ₹27,420.00 payments (both `payment_date` 2026-04-27) have no row in `expenses` referencing them, no `journal_entries` row, and no `journal_lines` row carrying their ids in `source_id` or `memo`.
2. **₹2,420.00 is present but classified as `5900 Other Expenses`.** It reaches the ledger through the declared foreign key `expenses.team_payment_id -> team_payments.id` and a `journal_entries` row with `source_table='expenses'` and `source_id` equal to that expense row — a declared relationship and a journal source, not an amount or date resemblance. Because it posted to 5900, it falls in the `other_expenses` bucket and **not** in the `salaries` bucket, which reports ₹0.00.
3. **No posting mechanism exists for payroll.** `FN.TRG` lists 55 triggers; none is on `team_payments`, `team_salary_bills` or `payroll_sync`. The journal-posting triggers cover assets, asset_payments, deposit_settlements, eb_payments, expenses, invoices, owner_payments, receipts and tenant_adjustments only.
4. **Both salary accounts are empty.** `5700 Salaries & Benefits` and `5310 Housekeeping - Salaries` carry zero journal lines and ₹0.00 under either reversal convention.

**Observation, not a cause.** The active `Salaries` expense category has a **NULL** `gl_account_id`, while a separate active category `Staff Salaries` maps to `5700 Salaries & Benefits` and has zero expense rows. This is recorded as an observation only. It is **not** claimed to have caused the 5900 classification.

**Root cause / mechanism:** Not determinable from exported evidence. `build_expense_lines()`, the function that selects the account for an expense posting, is not among the 28 exported function definitions, so the account-selection rule cannot be read. Why the two payments were never entered as expenses is likewise not recorded — operator omission, deliberate exclusion and a failed backfill are all consistent with the export, and nothing distinguishes them.

**Root cause confidence:** PROVEN for the ₹45,420.00 absence, the ₹2,420.00 posting to 5900, the empty 5700/5310 accounts and the absence of any payroll posting trigger — each re-derived directly from the exported CSVs. Not determinable from exported evidence for why the payments were never entered and why the posted one was classified to 5900.

**Status:** MEASURED

**Metrics affected:** M.EXP.001, M.EXP.002, M.PNL.001. M.PROFIT.001 is already `BLOCK` and is not changed by this finding.

**What SAFE and MATCH mean here.** M.EXP.001 and M.PNL.001 remain `SAFE` with a `MATCH` validation label, and that is correct: each reproduces `v_pnl` (`F.001`) exactly. That label means **the metric accurately represents what the ledger holds. It is not evidence that payroll is complete.** The ₹45,420.00 never reached the ledger, so no ledger-versus-ledger check can detect it. M.EXP.002 reports `salaries: ₹0.00`, which is wrong as a business statement in two separate ways — ₹2,420.00 of salary sits in `other_expenses`, and ₹45,420.00 is not in the ledger at all.

**Business impact:** M.EXP.001 is understated by the proven ₹45,420.00 (0.219%). The unresolved basis question is materially larger than that: depending on which basis the business adopts, the amount that belongs in Expenses ranges from ₹47,840.00 to ₹1,063,458.44.

**Records requiring operational reconciliation:** the two unposted `team_payments` rows — ₹18,000.00 (`payment_month` 2026-03, team member `caa1b17f…`) and ₹27,420.00 (`payment_month` 2026-03, team member `274203e6…`), both `payment_date` 2026-04-27, both `bank transfer`.

**Payroll basis is unresolved.** Three defensible readings of "payroll expense" exist in the evidence, and **these must not be added together** — their periods overlap and no foreign key links the three tables, so the overlap is unquantified:

| Basis | Source | Amount |
|---|---|---|
| Cash paid | `team_payments` | ₹47,840.00 |
| Earned / accrued | `team_salary_bills.net_payable` | ₹1,063,458.44 (draft ₹961,288.47; approved ₹33,653.85; paid ₹68,516.12) |
| Computed payroll | `payroll_sync.payable_salary` | ₹220,451.61 (one period, 2026-05-29 to 2026-06-28) |

Whether a `team_salary_bills` row and a `team_payments` row describe the same obligation is **Not determinable from exported evidence** — `M.009` shows each table's only foreign keys are `organization_id` and `team_member_id`, and `payroll_sync` declares none at all. **Conflicting definitions exist. Business decision required.**

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Carry this finding on M.EXP.001, M.EXP.002 and M.PNL.001 as a disclosure. Do not create a calculated payroll-expense metric, and do not select cash-paid, accrued or computed payroll as the official basis — the exported evidence does not establish which the business intends.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — When asked about expenses, profit or a monthly P&L, give the figure and state that ₹45,420.00 of salary paid is proven absent from the ledger and that the payroll basis is undecided. When asked specifically about salary or staff cost, state that the `salaries` bucket reports ₹0.00, that ₹2,420.00 of salary is recorded under `other_expenses`, and that no single payroll total can be stated until the business names the basis.

---

<a id="dq034"></a>
### DQ.034 — Two maintenance-cost definitions disagree by 23.51x, and the ticket-linked subset is presented as 100% of maintenance

**Severity:** HIGH
**Business area:** Maintenance

**Affected rows:** 450 of 465 maintenance-category expenses have no ticket link (15 are linked); 451 of 466 `ticket_resolutions` have no expense row; 689 ledger lines across 6 maintenance accounts
**Affected amount:** **₹648,240.00** — the difference between ₹677,036.00 (maintenance-category ledger spend) and ₹28,796.00 (ticket-linked maintenance)
**Percentage:** the ticket-linked figure is 4.25% of maintenance-category ledger spend; ledger/category is **23.51x** ticket-linked

**Evidence file(s):** T.expenses, T.expense_categories, T.maintenance_tickets, T.ticket_resolutions, T.issue_types, T.journal_lines, T.journal_entries, T.coa_accounts, F.015 (`v_maintenance_metrics`), F.016 (`v_maintenance_by_issue_type`), M.016 (both view definitions), H.058 (`maintenance_cost_linkage`), H.018, H.019

**What is proven.** Proven from exported evidence:

1. **Ticket-linked maintenance = ₹28,796.00**, from **15** `expenses` rows carrying `ticket_resolution_id IS NOT NULL`. Both exported views agree: `F.015.cost` and `F.016.total_cost` each sum to ₹28,796.00, and `H.058.expense_amount_linked` records the same figure.
2. **Maintenance-category ledger spend = ₹677,036.00**, from **465** maintenance-category expenses, posted across accounts **5210** Plumbing ₹1,290.00, **5220** Electrical ₹12,010.00, **5230** Carpentry ₹559.00, **5240** Appliances ₹45,835.00, **5260** HVAC ₹579,741.00 and **5290** Other ₹37,601.00 — 689 journal lines, every one `source_table='expenses'`.
3. **Exact difference = ₹648,240.00.** The 15 ticket-linked expense ids are a subset of the 465 by id-set membership, so the difference is exactly the **450** maintenance expenses that have no ticket link.
4. **The difference splits in two.** **₹203,440.00** (130 expenses) is dated before the first maintenance ticket exists — maintenance `expense_date` runs from 2023-03-11 while `maintenance_tickets.created_at` begins 2025-01-29, so that spend structurally cannot carry a ticket link. **₹444,800.00** (320 expenses) is dated on or after the first ticket and still has no ticket link.
5. **Ticket resolutions: 466 total, only 15 with a linked expense.** `ticket_resolutions.total_cost` sums to **₹31,596.00**; ₹28,796.00 of that sits on the 15 resolutions that have an expense (matching the expense amounts exactly), leaving **₹2,800.00** of declared resolution cost on the other 451 resolutions with **no corresponding expense row and no ledger posting**.
6. **`v_maintenance_by_issue_type` presents the ticket-linked subset as 100% of maintenance.** Its SQL filters `WHERE e.ticket_resolution_id IS NOT NULL` and then computes `pct_of_maintenance` as a window over that already-filtered set, so the exported rows sum to 100% per month with ₹28,796.00 as the denominator. All 465 maintenance expenses carry an `issue_type_id`, so that single predicate produces the entire ₹648,240.00 gap.

**Root cause / mechanism:** Not determinable from exported evidence — for each of:

- why 450 maintenance expenses have no ticket link (no field records whether a ticket was expected);
- whether the `ticket_resolution_id IS NOT NULL` predicate in `v_maintenance_by_issue_type` was intentional scoping or an oversight (no comment, spec or changelog is exported);
- whether the 451 unexpensed resolutions correspond to the 450 unlinked expenses (nothing links them; the near-equal counts are a coincidence of arithmetic, not a relationship);
- whether the 76 repeated maintenance expense rows (56 groups sharing `amount`, `expense_date` and `description`) are duplicates or genuine same-day repeat purchases;
- why account 5260 HVAC holds ₹579,741.00, 85.6% of all maintenance, across 596 lines.

**Root cause confidence:** PROVEN for every figure recorded here — each re-derived directly from the exported CSVs, with the view behaviour read from its own SQL in `M.016`. Not determinable from exported evidence for the five questions above.

**Status:** CONFLICTING DEFINITIONS EXIST

**Metrics affected:** M.MAINT.002 and M.EXP.002 only.

| Metric | Trust | Reports | Basis |
|---|---|---|---|
| M.MAINT.002 | SAFE | ₹28,796.00 as "Maintenance cost" | ticket-linked |
| M.EXP.002 | DISCLOSE | ₹677,036.00 in its `maintenance` bucket | ledger/category |

**M.MAINT.001, M.EXP.001 and M.PNL.001 are NOT affected** and this finding is deliberately not attached to them: the investigation found **no calculation omission** in any of the three. M.MAINT.001 counts tickets, not cost. The full ₹677,036.00 is already inside M.EXP.001's ₹20,784,831.96 and inside M.PNL.001's monthly series — unlike DQ.033, no maintenance amount is missing from the ledger.

**What SAFE and MATCH mean here.** M.MAINT.002 keeps `SAFE` and its `MATCH` validation label, and both are correct: the calculator reproduces `F.015` and `F.016` exactly. That label means **the metric reproduces its exported view correctly. It does not establish that ₹28,796.00 is the complete maintenance spend.** The existing `C.023`/`DQ.027` caveat on this metric concerns Path A versus Path B — two figures that are identical — and says nothing about the ₹648,240.00.

**Business impact:** A measure labelled "Maintenance cost" reports 4.25% of what the business spent on maintenance, while "Expenses by category" reports the other figure for the same period. Read side by side without this finding, the two look like a reconciliation error rather than two definitions.

**Three competing bases — these must NOT be added together.** They overlap: the ticket-linked rows are contained in the ledger/category set, and the resolution-declared figure covers the same 15 rows.

| Basis | Source | Amount |
|---|---|---|
| Ticket-linked resolved work | `expenses.ticket_resolution_id IS NOT NULL` (F.015 / F.016) | ₹28,796.00 |
| All maintenance-category ledger spend | `expenses` category `maintenance` -> accounts 5210-5290 | ₹677,036.00 |
| Resolution-declared cost | `ticket_resolutions.total_cost` | ₹31,596.00 (₹2,800.00 of it never expensed) |

**Conflicting definitions exist. Business decision required.**

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** No — the open question is a business definition, not a data repair

**Blocks an AI/business metric:** No, with both figures shown

**Owner decision required:** Management must decide whether "maintenance cost" means (1) ticket-linked work, (2) all maintenance-category spend, or (3) resolution-declared cost. Separately, and as a process question rather than a definition: whether maintenance expenses should require a ticket link going forward.

**Recommended handling in the semantic layer:** Carry this finding on M.MAINT.002 and M.EXP.002. Present both figures with the basis named beside each; never merge them, never add them, and do not select one as official — the exported evidence does not establish which the business intends.

**Recommended AI disclosure/response behavior:** `SHOW_BOTH` — When asked what maintenance cost, give ₹28,796.00 and ₹677,036.00 side by side, say which basis each is, and state that the official definition is undecided. Never present ₹28,796.00 alone as total maintenance spend, and never add the bases together.

---

<a id="dq035"></a>
### DQ.035 — Five populations each answer "deposit exposure", and two of them overlap by ₹386,500.00

**Severity:** HIGH
**Business area:** Deposits / tenant exits

**Affected rows:** 32 flagged allotments (29 with an exit record, 3 `Cancelled` without) across 25 distinct tenants; 26 exit records with `refund_status='none'`; 200 live settlements with no live exit row; 36 live exits with no settlement row
**Affected amount:** M.RISK.004 **₹722,700.00**, of which **₹386,500.00** is also represented in M.DEP.001 for the same tenant and **₹336,200.00** has no corresponding account 2100 balance at all
**Percentage:** the overlap is 53.5% of M.RISK.004's figure and 9.2% of M.DEP.001's ₹4,221,150.00

**Evidence file(s):** T.tenant_allotments, T.tenant_exits, T.deposit_settlements, T.receipts, T.tenant_transactions, T.journal_lines, T.journal_entries, T.coa_accounts, F.010 (`v_advance_balances`), H.045 (`v_diag_deposit_phantom`), H.046 (`v_deposit_ledger_anomalies`), FN.validate_deposit_settlement

**M.RISK.004's current definition, and that it is correct.** Proven from exported evidence:

```
tenant_allotments
  WHERE deposit_paid > 0
    AND staying_status IN ('Exited','Cancelled')
    AND no live deposit_settlements row exists for the allotment
```

This returns **32 allotments** and **₹722,700.00**, and the row set matches `H.045` exactly. **The metric is mathematically correct under its current definition.** Its `PARTIAL` validation label reflects only that `H.045` exports no summed amount, so the count was independently confirmed and the amount is a first computation.

**`tenant_exits` does NOT feed M.RISK.004.** The calculator reads `tenant_allotments` and `deposit_settlements` only, and no deposit metric in the registry reads the 147-row exit register at all — despite its carrying `advance_held`, `refund_due`, `refund_status` and `refund_date`. Proven from exported evidence.

**Five competing populations and bases. These must NOT be added together** — they are different populations over different keys, and two of them overlap:

| # | Basis | Population | Amount |
|---|---|---|---|
| 1 | Application ended-allotment exposure (M.RISK.004) | 32 allotments | **₹722,700.00** |
| 2 | Ledger liability on those same allotments | same 32 | **₹6,000.00** |
| 3 | Ledger liability for the same tenants, all allotments | 25 tenants | **₹396,250.00** |
| 4 | Exit-register refund obligation | 143 live exits | **₹1,527,276.59** incl. the soft-deleted exit; **₹1,465,724.59** live completed refunds; **₹61,552.00** pending |
| 5 | Settlement workflow | 307 live settlements | **₹5,023,390.33** completed refunds; **₹62,569.00** pending across 5 |

**The overlap, and why it exists.** Proven from exported evidence: every journal line on account **2100 Tenant Deposits Held** carries an `allotment_id`, so matching the 32 flagged allotment_ids returns ₹6,000.00 while matching the same 25 tenants across all their allotments returns ₹396,250.00. Deposits move between a tenant's allotments through manual journal entries whose memos read **"Deposit transfer out"** and **"Deposit transfer in"**, paired with "Security Deposit Received"; `tenant_transactions` records the same concept independently as `DEPOSIT_TRANSFER` rows. Classifying the 32 by what the ledger holds for the same tenant:

| Ledger position for that tenant | Allotments | Flagged amount |
|---|---|---|
| Still holds at least the flagged amount, on another allotment | 13 | ₹303,750.00 |
| Holds part of it | 4 | ₹93,900.00 |
| Holds nothing for the tenant | 15 | ₹325,050.00 |

**M.RISK.004 and M.DEP.001 must NOT be treated as additive.** ₹386,500.00 is common to both — inside M.DEP.001's ₹4,221,150.00 under a different allotment of the same tenant, and inside M.RISK.004's ₹722,700.00 under the flagged one. Only ₹336,200.00 of the flagged amount appears in no 2100 balance.

**M.DEP.001 stays SAFE, and its calculation stays correct.** It reproduces `F.010` (`v_advance_balances.deposit_held`) exactly under its own ledger definition, and its `MATCH` label is accurate. The issue is not its arithmetic: it is that its figure **overlaps** M.RISK.004's and could be misunderstood as a separate, additional amount.

**Exit and settlement register inconsistencies.** Proven from exported evidence:

- **29 of the 32** flagged allotments have an exit record; **3 are `Cancelled` and have none**.
- Those 3 carry **₹65,250.00** of `deposit_paid` between them, but only a **₹1,000.00** booking receipt each and **zero** lines on account 2100. Whether those deposits were actually received is **Not determinable from exported evidence**.
- **26 exit records carry `refund_status='none'`**, with **₹595,350.00** of `advance_held` and **₹0.00** `refund_due`. (The other 3 are `completed`, with ₹19,003.00 due.)
- **200 live deposit settlements have no live `tenant_exits` row**; all 200 have a valid allotment, and all 200 allotments are `Exited`.
- **36 live tenant exits have no settlement row.**
- The cause of these register differences is **Not determinable from exported evidence**.

**Root cause / mechanism:** the transfer mechanism above is proven. What is **Not determinable from exported evidence**: why 26 exits carry no refund amount against ₹595,350.00 of advance held; whether the 3 `Cancelled` deposits were ever received; why 200 settlements have no exit row and 36 exits have no settlement; and which of the five bases the business intends.

**Root cause confidence:** PROVEN for every figure and relationship recorded here — the 32-row population and ₹722,700.00, the ₹6,000.00 and ₹396,250.00 ledger attributions, the ₹386,500.00 overlap and ₹336,200.00 residual, the 13/4/15 split, the transfer mechanism read from the journal memos and corroborated by `tenant_transactions`, and the exit and settlement counts — each re-derived directly from the exported CSVs. Not determinable from exported evidence for the four questions above.

**Status:** CONFLICTING DEFINITIONS EXIST

**Metrics affected:** M.RISK.004, M.RISK.003 and M.DEP.001 only.

| Metric | Trust | Value | Why it is here |
|---|---|---|---|
| M.RISK.004 | DISCLOSE | 32 allotments / ₹722,700.00 | the figure whose basis is disputed |
| M.RISK.003 | DISCLOSE | carries M.RISK.004 as a component | inherits it |
| M.DEP.001 | SAFE | ₹4,221,150.00 | overlaps M.RISK.004 by ₹386,500.00; calculation unchanged and correct |

**Business impact:** Read side by side without this finding, "Deposits held ₹4,221,150.00" and "Deposit exposure at risk ₹722,700.00" look like two separate amounts. ₹386,500.00 is the same money counted in both, and ₹303,750.00 of the flagged amount sits under allotments whose tenants are currently `Staying`.

**Conflicting definitions exist. Business decision required.**

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes for the record-level questions (the 3 `Cancelled` deposits, the 26 zero-refund exits); the definition question is a business decision, not a data repair

**Blocks an AI/business metric:** No, with both figures shown and the overlap stated

**Owner decision required:** Management must decide **which population and basis define "deposit exposure at risk"** — any of the five in the table above. Two further decisions are recorded separately, because they are process questions rather than definitions: **whether transferred deposits should be cleared from the old allotment** (it is what makes the application and ledger figures diverge), and **which register is authoritative for exits and settlements**, given 200 settlements have no exit row and 36 exits have no settlement.

**Recommended handling in the semantic layer:** Carry this finding on M.RISK.004, M.RISK.003 and M.DEP.001. Never present M.RISK.004 and M.DEP.001 as additive; state the ₹386,500.00 overlap whenever both appear. Do not select a basis — the exported evidence does not establish which the business intends.

**Recommended AI disclosure/response behavior:** `SHOW_BOTH` — When asked about deposit exposure or deposits at risk, name the basis of any figure given, state that ₹386,500.00 of the ₹722,700.00 is also inside the ₹4,221,150.00 held, and say the official basis is undecided. Never add the five bases together, and never present ₹722,700.00 as money confirmed lost.

---

<a id="dq036"></a>
### DQ.036 — v_tenant_aging is net ledger movement by posting age, not overdue aging, and its buckets lose ₹4,968.00

**Severity:** HIGH
**Business area:** AR aging

**Affected rows:** 644 rows (F.008, every row structurally); 3 future-dated invoice lines excluded from all buckets; **0 rows** in `receipt_allocations` against **5,758** live receipts
**Affected amount:** bucket sum **₹78,329.85** against F.008's own total of **₹83,297.85** — a proven gap of **₹4,968.00**
**Percentage:** the 31–60 bucket alone is ₹4,488,604.27 against a portfolio net of ₹83,297.85 — 53.9× the net balance, because the buckets hold movement, not balances

**Evidence file(s):** F.008 (`v_tenant_aging`), M.016 (`v_tenant_aging` SQL), H.020 (`receipt_allocations_empty`), T.journal_lines, T.journal_entries, T.coa_accounts, T.receipts

**What is proven.** Proven from exported evidence:

1. **`v_tenant_aging` is net ledger movement grouped by posting age, not conventional overdue/open-invoice aging.** Its CTE is named `ar_charges` but carries **no `debit > 0` filter**: it selects `debit - credit` over every account 1200 line with `party_kind = 'tenant'`.
2. **It includes AR debit *and* credit movement**, not only unpaid invoice charges — payments, credit notes, reversals and deposit-settlement lines all land in the buckets.
3. **Payments and credits therefore create negative buckets.** The exported figures:

| Bucket | Exported value |
|---|---|
| 0–30 | **−₹57,463.94** |
| 31–60 | **₹4,488,604.27** |
| 61–90 | **−₹154,043.45** |
| 90+ | **−₹4,198,767.03** |
| **bucket sum** | **₹78,329.85** |
| **F.008 `total`** | **₹83,297.85** |
| **gap** | **₹4,968.00** |

4. **Each line is bucketed by its own `journal_entries.entry_date`**, never by the settlement date of the invoice it relates to, so a payment ages from its own posting date rather than from the charge it settles. All four exported buckets were reproduced to **₹0.00 absolute error** from `journal_lines` at `CURRENT_DATE = 2026-08-29`.
5. **The ₹4,968.00 gap is a bucket-completeness defect.** Every bucket requires `CURRENT_DATE - charge_date >= 0`, so lines dated after the query date fall into **no bucket** while still counting in the view's `total`. Exactly three invoice-sourced debits qualify:

| entry_date | amount |
|---|---|
| 2026-08-31 | ₹468.00 |
| 2026-09-06 | ₹2,250.00 |
| 2026-09-20 | ₹2,250.00 |
| **total** | **₹4,968.00** |

   and ₹78,329.85 + ₹4,968.00 = ₹83,297.85 exactly.
6. **`receipt_allocations` holds 0 rows against 5,758 live receipts** (`H.020`), so no payment can be tied to the invoice it settles.

**Conventional overdue/open-invoice aging: Not determinable from exported evidence.** With no receipt-to-invoice allocation anywhere in the package, exact receipt-to-invoice settlement aging cannot be derived at all — only modelled, as `F.009` does with a FIFO waterfall.

**Root cause / mechanism:** the two mechanisms above are read directly from the view's own SQL. Which meaning of "aging" the business intends is not established anywhere in the export.

**Root cause confidence:** PROVEN for the semantics and for every figure — the SQL read in full from `M.016`, all four buckets reproduced to ₹0.00 error, the ₹4,968.00 traced to three named lines, and the empty allocation table confirmed in `H.020`. Not determinable from exported evidence for conventional overdue aging and for which meaning the business intends.

**Status:** CONFLICTING DEFINITIONS EXIST

**Metrics affected:** **M.RISK.002** only. No tenant-dues metric is affected — M.AR.001A through M.AR.001D read account 1200 directly and do not consume F.008.

**Business impact:** A figure labelled "aging" answers a different question from the one an owner asks of it. A negative bucket does not mean money is owed back in that age band; it means credits posted in that band exceeded charges. And the four buckets do not add to the view's own total.

**Conflicting definitions exist. Business decision required.**

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** No for the exported-evidence conclusion; a live database would be needed only to build overdue aging, which this export cannot support

**Blocks an AI/business metric:** No, with both meanings stated

**Owner decision required:** Management must decide whether "aging" means net ledger movement by posting age — what the view computes today — or conventional overdue open-invoice aging, which would require receipt-to-invoice allocation the system does not currently record.

**Recommended handling in the semantic layer:** Carry this finding on M.RISK.002. State which meaning any bucket figure carries, and never present a negative bucket as an amount owed. Do not select a meaning — the exported evidence does not establish which the business intends.

**Recommended AI disclosure/response behavior:** `SHOW_BOTH` — When asked about aging or overdue amounts, say that the available buckets are net ledger movement by posting age, give them with their signs, and state that conventional overdue aging is not determinable from the exported evidence because no receipt-to-invoice allocation exists. Never add the buckets and present the result as the outstanding balance: they are short of the view's own total by ₹4,968.00.

---

<a id="dq037"></a>
### DQ.037 — Every tenant-dues definition mixes current and ended tenancies, and the sign of the answer depends on which is meant

**Severity:** HIGH
**Business area:** AR / tenant dues

**Affected rows:** 626 allotments carry ledger AR activity, of which **92** have a nonzero balance — 47 ended (27 debtors, 20 in credit) and 45 current (23 debtors, 22 in credit). Def C covers all 1,213 allotments; Def D covers 1,047.
**Affected amount:** the ledger headline **₹83,297.85** is **current −₹26,494.15 plus ended +₹109,792.00**
**Percentage:** ended tenancies are 131.8% of the ledger headline; current tenants are −31.8% of it

**Evidence file(s):** T.tenant_allotments, T.tenant_transactions, T.journal_lines, T.journal_entries, T.coa_accounts, F.006 (`v_outstanding_receivables`), F.007 (`v_tenant_current_dues`), M.016 (both view definitions), H.052

**What is proven.** Proven from exported evidence:

1. **No tenant-dues definition applies any tenancy-state filter.** `v_outstanding_receivables` filters only `account_code='1200' AND party_kind='tenant'`. `v_tenant_current_dues` filters only `party_kind='tenant' AND code IN ('1200','2100','2400')` — **despite its name it carries no `staying_status` filter** and is not restricted to current tenants. The engine adds none either: `staying_status` appears nowhere in `engine/calculators/receivables.py`, only in the occupancy and deposit calculators.
2. **Def A and Def B include Exited and Cancelled allotments**, and those dominate the total.
3. **The population split, by definition:**

| Definition | Current (Staying + On-Notice + Booked) | Ended (Exited + Cancelled) | Total |
|---|---|---|---|
| A — ledger, reversals excluded | **−₹26,494.15** | **+₹109,792.00** | ₹83,297.85 |
| B — ledger, reversals included | **−₹26,494.15** | **+₹109,792.00** | ₹83,297.85 |
| C — `tenant_allotments.balance_due` | ₹202,383.06 | ₹806,742.72 | ₹1,009,125.78 |
| D — `tenant_transactions` (frozen legacy) | −₹18,479.46 | ₹9,986,502.78 | ₹9,968,023.32 |

4. **The sign flips on the ledger definitions.** Current tenants owe ₹96,460.00 across 23 allotments but hold −₹122,954.15 in credit across 22, netting **−₹26,494.15**. Ended tenancies owe ₹211,263.00 across 27 and hold −₹101,471.00 in credit across 20, netting **+₹109,792.00**. An owner asking what current tenants owe would be handed a positive receivable for a population that is collectively in credit.
5. **Def A's and Def B's splits are identical.** They differ only in line counts — 454 Exited allotments carry reversal-only rows under the reversal-included convention against 436 under the excluded one — while every amount matches.
6. **Def C and Def D are dominated by ended tenancies even more heavily**: 79.9% and 100.2% of their respective totals.

**This is not a calculation bug.** Each definition is arithmetically correct over the population it selects, and every published total reconciles exactly to its exported view (A → F.006, B → F.007, C → the stored column, D → the legacy table). No code defect was found in `engine/calculators/receivables.py`.

**It is a semantic-definition conflict.** No exported view, function or document states which tenancy states "tenant dues" is meant to cover. Whether current-only, ended-only or combined is intended is **Not determinable from exported evidence.**

**Root cause confidence:** PROVEN for every figure and for the absence of any tenancy-state filter — the two view definitions read in full from `M.016`, the calculator read directly, and each population split re-derived from the exported CSVs by joining to `tenant_allotments.staying_status`. Not determinable from exported evidence for which population the business intends.

**Status:** CONFLICTING DEFINITIONS EXIST

**Metrics affected:** M.AR.001A, M.AR.001B, M.AR.001C, M.AR.001D — every tenant-dues definition. Transitively M.AR.002, M.AR.003 and M.RISK.001, which present the four-way view.

**Does it block a metric?** No, and no trust level changes. M.AR.001A and M.AR.001B are already `SHOW_BOTH`; M.AR.001C and M.AR.001D are already `BLOCK`. This finding adds a second axis — population scope — to the definition conflict `DQ.002` already records on the same metrics, and the existing postures already prevent a single silent answer.

**Business impact:** "Tenant dues ₹83,297.85" reads as money current residents owe. It is not: the current population is net in credit, and the figure is ended-tenancy money, most of it concentrated in a few allotments (the five largest ended debtors run from ₹52,493.00 down to ₹14,267.00). Collectability differs sharply between the two populations, and the headline does not distinguish them.

**Conflicting definitions exist. Business decision required.**

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** No — the figures are all computable offline; the open question is a business definition, not a data repair

**Blocks an AI/business metric:** No, with the population named alongside any figure

**Owner decision required:** Management must decide **which tenancy population "tenant dues" covers** — current tenants only (−₹26,494.15 on the ledger definitions), ended tenancies only (+₹109,792.00), or both combined (₹83,297.85). The same choice applies to Def C and Def D if either is ever adopted. This is separate from, and additional to, `DQ.002`'s question of which of the four definitions is official.

**Recommended handling in the semantic layer:** Carry this finding on all four tenant-dues metrics. Name the population alongside any dues figure, and never present the combined headline as what current tenants owe. Do not select a population — the exported evidence does not establish which the business intends.

**Recommended AI disclosure/response behavior:** `SHOW_BOTH` — When asked what tenants owe, give the figure with its population named, and state that current tenants are collectively ₹26,494.15 in credit while ended tenancies account for ₹109,792.00. Never answer a question about current tenants with the combined total.

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

**Affected rows:** 4 receipts carry the residual after reversal netting (of the 11 traced in H.048); 3 live receipts have no ledger posting at all (H.033)
**Affected amount:** ₹16,282.45 residual (M.COL.001 ₹81,855,686.97 vs M.COL.003 ₹81,839,404.52): +₹16,627.45, -₹400.00, +₹53.00, +₹2.00. The ₹5,340,795.62 reported by H.001 is not a residual — it is ₹5,357,078.07 of reversed forward postings that H.001's formula never subtracts, less the ₹16,282.45.
**Percentage:** 0.02% of total receipt value (₹16,282.45 of ₹81.86M)

**Evidence file(s):** H.001 (v_je_amount_reconciliation), H.048, H.033 (source_vs_ledger_diff_summary), T.journal_lines, T.coa_accounts, T.receipts

**Root cause / mechanism:** H.001's je_net_amount is `SUM(CASE WHEN is_reversal_of IS NULL THEN debit ELSE -debit END)`. Reversal lines carry credit and not debit, so the `-debit` branch always evaluates to zero and no reversal is ever subtracted: 112 reversal credits totalling ₹5,357,078.07 exactly offset the 112 forward debits they reverse, and ₹5,357,078.07 − ₹16,282.45 = ₹5,340,795.62 exactly. The remaining ₹16,282.45 is 4 receipts: `8a8f7848…` (VISTA/26-27/04/R00250, ₹16,627.45, zero journal entries), `3789971b…` (−₹400.00), `118da474…` (+₹53.00), `ec8a0992…` (+₹2.00). Aggregate P&L/revenue views (v_pnl, v_revenue_by_period) are unaffected: they use the reversal-excluded v_account_balances convention, which nets forward and reversal pairs correctly.

**Root cause confidence:** PROVEN for the ₹5,340,795.62 artifact (H.001's formula recomputed directly from journal_lines; the decomposition is exact). NOT DETERMINABLE for why the 4 residual receipts differ — build_receipt_lines is not among the 28 exported function definitions and receipts carries no updated_at column, so a post-posting edit can be neither confirmed nor ruled out.

**Status:** MEASURED

**Metrics affected:** M.COL.003 vs M.COL.001 reconciliation (₹16,282.45); individual-receipt ledger tracing; the H.001/H.048 diagnostic's own reliability

**Business impact:** Does not threaten top-line revenue/collections KPIs — the two collections definitions are ₹16,282.45 apart, 0.02%. It does affect individual-receipt ledger tracing, and it removes the H.001 receipts figure as a usable reconciliation reference.

**Offline-fixable from exported evidence:** No  |  **Live-DB investigation/fix required:** Yes

**Blocks an AI/business metric:** No, with disclosure

**Recommended handling in the semantic layer:** Keep M.COL.001 and M.COL.003 as separate disclosed definitions; neither is canonical on the exported evidence. Route the 4 named receipts to operations as records to check. Do not quote ₹5,340,795.62 as a receipts drift.

**Recommended AI disclosure/response behavior:** `DISCLOSE` — For org-level collections questions: give the figure asked for, name which of the two definitions it is, and disclose the ₹16,282.45 residual. For a specific receipt's ledger history: disclose that edited receipts can show inflated totals in the H.001/H.048 diagnostics.

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
**Affected amount:** **₹4,968.00** — F.008's bucket totals are **short** of F.008's own `total` column (₹78,329.85 against ₹83,297.85), because three future-dated invoice lines are counted in `total` but excluded from every age bucket by the `CURRENT_DATE - charge_date >= 0` condition ([DQ.036](#dq036)). The day-bucket assignment also shifts with the query date.
**Percentage:** 100% of aging rows are snapshot-dependent by construction

**Evidence file(s):** M.016 (v_tenant_aging SQL), M.002/M.099 (snapshot timestamps)

**Root cause / mechanism:** v_tenant_aging's bucket filters use CURRENT_DATE - charge_date, evaluated at query time. The exported CSV (F.008) reflects buckets computed at whatever moment inside the 09:02-11:18 export window the query ran, not a fixed historical fact.

**Root cause confidence:** PROVEN (direct SQL reading). The `CURRENT_DATE` dependence is expected application behaviour; the bucket incompleteness recorded above is a defect — the four buckets are not exhaustive of the view's own `total` ([DQ.036](#dq036)).

**Status:** MEASURED

**Metrics affected:** AR aging bucket distribution (0-30/31-60/61-90/90+)

**Business impact:** Two distinct problems. The bucket assignment shifts with the query date, so an aging figure is not reproducible from a frozen export without fixing an as-of date. Separately, and not merely a reproducibility hazard, the buckets are **incomplete**: they omit ₹4,968.00 that the view's own `total` includes, so the four buckets do not add up to it ([DQ.036](#dq036)). The underlying AR total itself is stable at ₹83,297.85.

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
| DQ.034 | C.023 (maintenance cost linkage) — related but distinct: C.023 contrasts the two ticket-linked paths with each other, DQ.034 contrasts ticket-linked cost against maintenance-category ledger spend |
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
| Total DQ issues | **37** |
| CRITICAL | **4** — DQ.001, DQ.002, DQ.016, DQ.019 |
| HIGH | **13** — DQ.004, DQ.005, DQ.008, DQ.011, DQ.013, DQ.015, DQ.028, DQ.030, DQ.033, DQ.034, DQ.035, DQ.036, DQ.037 |
| MEDIUM | **12** — DQ.003, DQ.006, DQ.007, DQ.010, DQ.012, DQ.014, DQ.017, DQ.018, DQ.020, DQ.025, DQ.026, DQ.027 |
| LOW | **6** — DQ.021, DQ.022, DQ.023, DQ.024, DQ.031, DQ.032 |
| INFORMATIONAL | **2** — DQ.009, DQ.029 |
| UNVERIFIED (status) | **2** — DQ.026, DQ.032 |
| BLOCK metrics | **7** — DQ.001, DQ.002, DQ.005, DQ.016, DQ.019, DQ.028, DQ.030 |
| DISCLOSE metrics | **16** — DQ.003, DQ.006, DQ.007, DQ.008, DQ.011, DQ.012, DQ.013, DQ.014, DQ.015, DQ.017, DQ.018, DQ.020, DQ.021, DQ.024, DQ.025, DQ.033 |
| SHOW_BOTH metrics | **6** — DQ.004, DQ.027, DQ.034, DQ.035, DQ.036, DQ.037 |
| SAFE metrics | **6** — DQ.009, DQ.010, DQ.022, DQ.023, DQ.029, DQ.031 |
| UNVERIFIED (ai_handling) | **2** — DQ.026, DQ.032 |

7 + 16 + 6 + 6 + 2 = **37**, matching the total exactly. These figures are read directly from
`data_quality_registry.csv`, which is the source of truth for all counts in this section.

---

## Next recommended deliverable

**`metric_reconstruction.md` (E) + offline validation scripts (F).** Every metric it defines
must cite, per the brief's own requirement, which of this report's DQ entries and which of
`conflicts.md`'s C entries it inherits — this report's `ai_handling` column
(`SAFE`/`DISCLOSE`/`SHOW_BOTH`/`BLOCK`/`UNVERIFIED`) is the direct input to metric_reconstruction's
"known limitations" field for each metric, and `data_quality_registry.csv` is the machine-readable
join key for building that mapping without re-deriving it by hand.
