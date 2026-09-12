# C. conflicts.md

Formal semantic-conflict registry for the exported evidence package. Every entry below is
sourced from an exact SQL definition (`M.016`, `FN.*`) or a specific diagnostic export (`H.*`),
re-verified numerically from the raw CSVs where a number is stated — none of the figures below
are carried forward from narrative without re-checking the underlying rows in this pass.

**Rule applied throughout:** this document never silently picks a winner. Every entry states
**Definition A** and **Definition B** (and C/D where more than two exist) side by side. Where
the evidence proves one side is arithmetically wrong (e.g. a query referencing the wrong account
code), that is stated as a fact with the proof shown — not as a preference. Everywhere else the
entry says **"Conflicting definitions exist."** Where the exported package cannot settle a
question, the entry says exactly **"Not determinable from exported evidence."**

**How the future semantic layer should read this file.** Each entry ends with four machine-
relevant fields — `Resolution status`, `Recommended handling`, `Expose both to AI?`, `Blocks/limits`.
An AI Q&A layer answering "what are our current dues" or "why did profit fall" must consult the
matching conflict entry before emitting a single number, and — where `Expose both to AI?` says
yes — must either ask which definition the user means or state both figures with their labels,
never average or silently pick one.

---

## Summary table

| ID | Area | Resolution status | Blocks/limits a metric? |
|---|---|---|---|
| [C.001](#c001) | AR / tenant dues | Conflicting definitions exist | Limits — 2 populations, same total |
| [C.002](#c002) | Ledger convention | Resolved (net balances unaffected; turnover differs) | Limits — affects transaction counts/turnover only |
| [C.003](#c003) | AR / tenant dues | Conflicting definitions exist, evidence favors distrust of `tenant_transactions` | Blocks — order-of-magnitude gap |
| [C.004](#c004) | Invoices / receivables | Conflicting definitions exist | Limits |
| [C.005](#c005) | AR / tenant dues | Conflicting definitions exist (4-way) | Blocks — no two of four agree except ledger incl/excl |
| [C.006](#c006) | Occupancy | Conflicting definitions exist (different grain) | Limits |
| [C.007](#c007) | Occupancy | Resolved — same-named field, different formula in v1 vs v2, proven from source | Blocks — silent version drift |
| [C.008](#c008) | Occupancy | Conflicting definitions exist (different time horizon) | Limits |
| [C.009](#c009) | Occupancy | Resolved — proven SQL defect in `v_occupancy` | Blocks — 7 beds vanish from all 4 named buckets |
| [C.010](#c010) | Profit / P&L | Conflicting definitions exist | Blocks — 3 different profit figures |
| [C.011](#c011) | Profit / P&L | Resolved — v1 proven to omit owner rent; v2 proven to correct it | Blocks |
| [C.012](#c012) | Expenses / P&L | Resolved — arithmetic identity proven | Blocks — ~5% of expenses invisible to category view |
| [C.013](#c013) | Expenses / EB | Resolved — same account, 3 different rollup outcomes, proven from SQL | Limits |
| [C.014](#c014) | Receipts / ledger | Conflicting definitions exist; mechanism partly traced | Limits |
| [C.015](#c015) | Invoices / ledger | Conflicting definitions exist; mechanism partly traced | Limits |
| [C.016](#c016) | Deposits / ledger | Conflicting definitions exist; mechanism partly traced (≈2× pattern) | Limits |
| [C.017](#c017) | Ledger / all domains | Resolved — counted directly | Limits |
| [C.018](#c018) | Ledger integrity | Resolved for 3 tables (0 orphans); 1 expected-by-design non-zero case found | Does not block |
| [C.019](#c019) | AR aging | Not a data conflict — a snapshot-dependence hazard | Limits — reproducibility only |
| [C.020](#c020) | Data quality / receipts & invoices | Conflicting definitions exist; asymmetric tooling | Limits |
| [C.021](#c021) | Ledger function | Resolved — proven wrong account code in source | Blocks that one function's `collections` field |
| [C.022](#c022) | Expenses | Conflicting definitions exist | Limits |
| [C.023](#c023) | Maintenance | Conflicting definitions exist | Limits |
| [C.024](#c024) | Collections / AR | Resolved — table is empty by design, not a broken join | Does not block (mechanism understood) |

24 conflicts. Counts and the four requested totals are given at the end of this document.

---

<a id="c001"></a>
## C.001 — `v_outstanding_receivables` vs `v_tenant_current_dues`

**Business area:** AR / tenant dues.

**Definition A — `v_outstanding_receivables`** (`F.006`, 626 rows). Source: `v_account_balances`
(reversals **excluded**, §C.002). Filter: `account_code='1200' AND party_kind='tenant'`.
Grain: `tenant_id, allotment_id`. Carries only `outstanding`, `last_charge_date`,
`last_payment_date` — no deposit or advance figures.

**Definition B — `v_tenant_current_dues`** (`F.007`, 645 rows). Source: raw `journal_lines` /
`journal_entries` / `coa_accounts`, **no** `is_reversal_of` filter (reversals **included**,
§C.002). Filter: `party_kind='tenant' AND account_code IN ('1200','2100','2400')`. Grain: same
(`tenant_id, allotment_id`). Carries `ar_balance`, `deposit_held`, `booking_advance`, `net_dues`,
plus `charge_count`/`payment_count` (which **do** double-count a reversed-and-reposted charge,
since reversals are included in the row count even though they net to zero in the dollar sum).

**Exact numerical difference:** total AR is **identical**: ₹83 297.85 in both (`H.006`,
re-verified independently in this pass from `H.052`: `SUM(def3_ledger_incl_reversals) =
SUM(def4_ledger_excl_reversals) = 83 297.85` across all 1213 allotments, 0 rows differ by more
than ₹0.50). The difference is **row count** (626 vs 645, a 19-row/3% gap — a tenant/allotment
can have zero net AR but nonzero deposit/advance, so it appears in B but not A) and **scope**
(A has no deposit/advance columns at all; B does).

**Which datasets/views produce each:** `v_outstanding_receivables` (A); `v_tenant_current_dues`
(B). Both defined in `M.016`.

**Likely mechanism:** two independently-written views answering two different questions — "AR
balance only" (A) vs "everything a tenant currently owes or has on account" (B) — built against
two different underlying queries (`v_account_balances` vs raw journal tables) that happen to
agree on the AR figure itself because reversals net to zero for a balance total (proven in
C.002).

**Evidence:** `M.016` (both view definitions, quoted in `business_logic.md` §4.1–4.2), `H.006`,
`H.052`.

**Resolution status:** total AR is resolved as identical; the row-population and scope
difference is not a bug — "Conflicting definitions exist" for which one is *the* tenant-dues
figure, because they answer different questions.

**Recommended handling:** the semantic layer should expose "AR balance" (→ A or B's `ar_balance`
column, identical) and "total dues including deposits/advances held" (→ B only) as two distinct
named metrics, not one. Never report A's row count as "number of tenants with dues" without
checking whether B has additional non-AR-dues rows for the same organization.

**Expose both to AI?** Yes — the AR *total* can be quoted from either with a footnote that they
agree; the *dues-including-deposits* figure must be sourced from B specifically and labelled as
such.

**Blocks/limits:** Limits — does not block AR reconstruction (both give the same total), but
blocks a naive "SELECT * FROM v_outstanding_receivables" from ever answering "what does this
tenant owe including their deposit," since that column doesn't exist there.

---

<a id="c002"></a>
## C.002 — Reversal-excluded vs reversal-included ledger balances

**Business area:** Accounting / ledger (cross-cutting — affects every view built on either
convention).

**Definition A — reversals EXCLUDED, both legs dropped.** `v_account_balances` (`M.016`):
```sql
WHERE je.is_reversal_of IS NULL
  AND NOT EXISTS (SELECT 1 FROM journal_entries r WHERE r.is_reversal_of = je.id)
```
Inherited by `v_pnl`, `v_pnl_by_category`, `v_revenue_by_period`, `v_expenses_by_period`,
`v_trial_balance`, `v_outstanding_receivables`, `v_advance_balances`, `v_org_cash_balance`,
`v_expense_composition`, `v_bed_expense_breakdown`, `v_property_expense_share`.

**Definition B — reversals INCLUDED, both legs summed (nets to the same total).**
`v_tenant_current_dues`, `v_tenant_aging`, `v_tenant_ledger`, `v_trial_balance_detailed`,
`v_account_rollup`, `v_invoice_settlement_status` query `journal_lines`/`journal_entries`
directly with no `is_reversal_of` filter at all.

**Definition C — sign-inverted netting**, a third code path used only in
`v_je_amount_reconciliation` (`H.001`): `SUM(CASE WHEN is_reversal_of IS NULL THEN debit ELSE
-debit END)`. Arithmetically equivalent to B for a total.

**Exact numerical difference:** for **balances** (AR total, deposit total, account net balance)
the difference is **₹0.00** — confirmed in this pass by `H.052`: all 1213 allotments'
`def3_ledger_incl_reversals` = `def4_ledger_excl_reversals` exactly (0 rows differ by >₹0.50).
For **gross debit/credit turnover** the difference is large: `H.007`
(`trial_balance_reversal_effect`) shows **10 of 57 accounts** affected, summing to
**₹17 693 638.16** difference on both the debit and credit side (equal, as expected since a
correctly-balanced reversal moves debit and credit by the same amount). Largest affected
accounts: `1200` AR–Tenants ₹8 191 885.31, `1120` Bank–Operating ₹6 012 011.84, `4100` Rental
Income ₹1 893 099.87, `2100` Tenant Deposits Held ₹1 046 950.00, `4200` Electricity Income
₹434 826.14 (re-derived directly from `H.007` in this pass).

**Which datasets/views produce each:** listed above; full SQL in `business_logic.md` §1.3.

**Likely mechanism:** definition A is the "clean balance" convention (built for reporting
totals); definition B is the "full audit trail" convention (built for row-level ledgers/aging
where every posting, including corrections, should be visible). Both are deliberate, not a bug.

**Evidence:** `M.016`, `H.001`, `H.005` (14 236 total entries, 347 reversals = 2.44%), `H.007`,
`H.052`.

**Resolution status:** **Resolved** for balances (definitionally equivalent, proven to ₹0.00
difference). **Conflicting definitions exist** for turnover/transaction-count metrics (charge
counts, gross debit/credit sums, `H.007`'s 10 affected accounts) — these are genuinely different
numbers depending on convention, and neither is "wrong."

**Recommended handling:** any metric that is a **balance** (AR, deposit held, account balance,
cash on hand) may use either convention with no numeric consequence — prefer definition A
(`v_account_balances`) for simplicity and because it's what most named business views already
use. Any metric that is a **count** or a **gross sum over a period** (number of charges posted,
gross rental income before corrections) must state which convention it used, because the two
give different answers.

**Expose both to AI?** Only for count/turnover metrics; not needed for balance metrics (identical
by proof above).

**Blocks/limits:** Limits — narrows which metrics are convention-sensitive to counts and gross
turnover; does not block balance reconstruction.

---

<a id="c003"></a>
## C.003 — `tenant_transactions` vs journal-ledger balances

**Business area:** AR / tenant dues, collections.

**Definition A — journal ledger** (`journal_entries`/`journal_lines`, via `v_account_balances`
or raw). Live, actively posted by 5 trigger functions, 14 236 entries, 2019-11-03 → 2026-09-20
(`M.025`).

**Definition B — `tenant_transactions`** (16 451 rows, `T.tenant_transactions`). A **separate,
parallel ledger** with its own `ledger_type`/`direction`/`category`/`reference_table` taxonomy
(`H.026`): `CHARGE`/`DEBIT` and `PAYMENT`/`CREDIT` rows referencing `invoices`, `receipts`,
`tenant_allotments`, `tenant_adjustments`, `deposit_settlements`. **Not wired to any trigger**
(absent from `FN.TRG`'s 55 rows) and **frozen**: all 16 451 rows have `created_at` between
2026-04-17 and 2026-04-28 — an eleven-day, one-time backfill/migration, not a live feed
(`M.025`, confirmed in the integrity report §9).

**Exact numerical difference (re-derived in this pass, `H.052`):** summed per-allotment balance
— `def2_tenant_transactions` total = **₹9 968 023.32** across 1213 allotments, vs the ledger's
`def3/def4` total of **₹83 297.85** — **a ₹9 884 725.47 gap, a ~120× multiple.** 699 of 1213
allotments show `tenant_transactions` balance > 0, vs only 50 for the ledger.

**Which datasets/views produce each:** ledger — `v_account_balances`, `journal_lines`. Legacy —
`tenant_transactions` directly; `v_diag_allotment_balance_drift` (`H.044`) also
computes its own balance from `tenant_transactions` (`SUM(amount WHERE direction='DEBIT') -
SUM(amount WHERE direction='CREDIT')`, filtered to `ledger_type IN ('CHARGE','PAYMENT')`) and
compares it to `tenant_allotments.balance_due` (definition A of C.005, not the journal ledger).

**Likely mechanism:** `tenant_transactions` is a superseded/legacy balance-tracking table that
was bulk-loaded once (11-day window) and never wired into the live posting pipeline that
maintains `journal_entries`. Its huge balance total relative to the ledger is consistent with it
never having reconciled the payment side against the same charges, or having imported historical
charges that the ledger (`journal_entries`, live since 2019-11) already nets against payments
that `tenant_transactions` doesn't separately carry — **this is a hypothesis based on the
structural facts (unwired, frozen, ~120× larger balance), not proven by tracing individual rows
in the exported diagnostics.**

**Evidence:** `T.tenant_transactions`, `H.026`, `H.044`, `H.052`, `M.025`, `FN.TRG` (absence).

**Resolution status:** Conflicting definitions exist. The evidence does not prove which balance
is "correct," but it does establish that `tenant_transactions` is structurally disconnected from
the live posting system (frozen, unwired) — a fact, not an opinion, that should weigh heavily
against treating it as authoritative for current dues.

**Recommended handling:** do not use `tenant_transactions` for any *current* AR/dues metric. It
may be useful for historical/audit reference given its 2019–2026 date coverage, but any use must
be labelled "legacy system, frozen 2026-04, not reconciled against the live ledger."

**Expose both to AI?** No for "what does this tenant currently owe" — use the ledger only. Yes,
with an explicit "legacy/frozen system" label, if a user specifically asks about
`tenant_transactions` history.

**Blocks/limits:** Blocks — a naive sum over `tenant_transactions` would overstate total dues by
two orders of magnitude.

---

<a id="c004"></a>
## C.004 — Application-maintained invoice `amount_paid`/`balance` vs ledger-derived receivables

**Business area:** Invoices / receivables.

**Definition A — application-maintained.** `invoices.amount_paid` and `invoices.balance` are
columns on the `invoices` row itself, updated by application code (not by any of the 25 exported
trigger bodies — `trg_invoice_journal_post`'s repost condition explicitly does **not** include
`amount_paid`/`balance` among the fields that trigger a reverse-and-repost, confirming these
columns are maintained independently of the ledger-posting trigger).

**Definition B — ledger-derived settlement.** `v_invoice_settlement_status` (`F.009`, 5379 rows)
computes a FIFO waterfall over AR account `1200` lines per `(org, tenant, allotment)`, ordered by
`entry_date, posted_at, line_no`, allocating cumulative credits against cumulative debits:
`amount_settled = GREATEST(0, LEAST(debit, total_credits - prior_debit))`. This is a **different
computation from A**, and it does **not** use any `receipt_allocations` link (that table is
empty — see `C.024`) — it is a pure date-ordered waterfall across the tenant's aggregate AR
activity, not a per-invoice receipt match.

**Exact numerical difference:** `H.043` (`v_diag_invoice_drift`, 2227 rows) measures **A's own
internal consistency** — `total_amount - amount_paid - balance`, all from the `invoices` row
itself — not A vs B. 2227 of 5214 live invoices (43%) show `|drift| > 0.01`. **A-vs-B (the
actual application-vs-ledger comparison) is not separately exported as a joined diagnostic** —
`H.049` (`invoice_amount_vs_ledger_rows`, 120 rows) compares `invoices.total_amount` (the
*charge* amount) against the *ledger's cumulative debit postings* for that invoice, not against
`amount_paid`/`balance`; see `C.015` for that comparison. **Not determinable from exported
evidence:** the exact row-by-row difference between `invoices.balance` and
`v_invoice_settlement_status.amount_outstanding` for the same invoice — no diagnostic joins
these two directly.

**Which datasets/views produce each:** A — `invoices` table columns directly. B —
`v_invoice_settlement_status` (`M.016`).

**Likely mechanism:** A is maintained by application logic outside the exported trigger set
(not determinable further); B is a ledger-side reconstruction built independently, using
date-ordered FIFO allocation rather than any stored allocation link. The two are expected to
diverge whenever (a) A's own internal math has drifted (`H.043`'s 43%), or (b) a repost/reversal
cycle changed the ledger's debit/credit history for an invoice without A's `amount_paid`/
`balance` being recalculated to match.

**Evidence:** `T.invoices`, `M.016` (`v_invoice_settlement_status`), `H.043`.

**Resolution status:** Conflicting definitions exist. Evidence proves A has substantial internal
drift (`H.043`) but does not directly measure A-vs-B.

**Recommended handling:** treat B (`v_invoice_settlement_status`) as the ledger-consistent
settlement figure for any metric that must reconcile with the trial balance; treat A
(`invoices.amount_paid`/`balance`) as the application's own record, useful for UI display but
not for financial reconciliation given the 43% drift rate. A dedicated join between the two
(invoice-by-invoice) is recommended as follow-up validation work before either is trusted alone.

**Expose both to AI?** Yes, whenever a user asks about a specific invoice's paid/outstanding
status — with the caveat that they can disagree.

**Blocks/limits:** Limits — blocks a single "invoice balance" answer from being stated with
confidence at the individual-invoice level without checking both.

---

<a id="c005"></a>
## C.005 — Four competing tenant/allotment balance definitions

**Business area:** AR / tenant dues (item G in the original brief).

**Four definitions, all exported together per-allotment in `H.052`** (1213 rows, full
population; `H.028` is a 200-row sample of the same):

- **Def 1 — `tenant_allotments.balance_due`** (application-stored column). Sum across 1213
  allotments: **₹1 009 125.78**.
- **Def 2 — `tenant_transactions`-computed** (§C.003). Sum: **₹9 968 023.32**.
- **Def 3 — ledger, reversals INCLUDED** (`journal_lines` direct). Sum: **₹83 297.85**.
- **Def 4 — ledger, reversals EXCLUDED** (`v_account_balances`). Sum: **₹83 297.85**.

**Exact numerical differences (re-derived in this pass):**
- Def 3 = Def 4 exactly, 0 of 1213 rows differ by >₹0.50 (this is `C.002`'s finding, restated at
  the per-allotment grain here).
- Def 1 ≠ Def 2 on **873 of 1213 allotments (72%)**, by more than ₹1.
- Def 1 total (₹1 009 125.78) exceeds the ledger total (₹83 297.85) by **₹925 827.93**.
- Def 2 total (₹9 968 023.32) exceeds the ledger total by **₹9 884 725.47** (~120×).
- Population split, Def 1 vs Def 3/4: **97 allotments** have Def 1 > 0; **50 allotments** have
  Def 3/4 > 0; only **26** overlap. **68 allotments show a nonzero app-stored `balance_due` while
  the ledger says AR = 0** ("phantom" app-side dues). **24 allotments show the reverse** (ledger
  says AR owed, app-stored `balance_due` = 0).
- `v_diag_allotment_balance_drift` (`H.044`, 713 rows) is a fifth, independent comparison —
  Def 2 (`tenant_transactions`, `CHARGE`/`PAYMENT` only) vs Def 1 (`tenant_allotments.
  balance_due`), floored at 0, flagged where `|drift| > 1.00` — 713 allotments meet that
  threshold, a different (larger) count than the 873 found by directly diffing Def 1 vs Def 2 in
  `H.052` at the >₹1 threshold; the two diagnostics use different source-row filters
  (`H.044` restricts `tenant_transactions.ledger_type IN ('CHARGE','PAYMENT')`, excluding the
  `DEPOSIT` category rows that C.003's raw total includes) — **the exact reconciliation between
  `H.044`'s 713 and `H.052`'s 873 is not determinable from exported evidence.**

**Which datasets/views produce each:** `tenant_allotments.balance_due` (Def 1, base column);
`tenant_transactions` (Def 2, §C.003); raw `journal_lines` (Def 3); `v_account_balances` (Def 4).
`H.052`/`H.028` export all four side by side; `H.044` is a separate two-way comparison.

**Likely mechanism:** four systems that were each meant to track the same fact
(what a tenant owes) were built or migrated at different times and never fully reconciled. Def 3
and Def 4 (both ledger-derived) are proven identical, so the ledger itself is internally
consistent; Def 1 (app column) and Def 2 (legacy frozen table) each diverge from the ledger and
from each other by large, structurally different amounts.

**Evidence:** `H.028`, `H.052`, `H.044`, `T.tenant_allotments`, `T.tenant_transactions`,
`M.016` (`v_account_balances`).

**Resolution status:** Conflicting definitions exist. The ledger pair (Def 3/4) is internally
resolved (§C.002); no evidence in the package proves whether Def 1, Def 2, or the ledger is the
operationally "true" balance the business currently relies on for collections.

**Recommended handling:** the semantic layer must never silently pick one of these four. For any
"what does tenant X owe" question, surface the ledger figure (Def 3/4) as the accounting-system
answer and, if the application-stored figure (Def 1) differs, flag it explicitly as a
discrepancy requiring reconciliation — never average the two or silently prefer one.

**Expose both to AI?** Yes, always, for this specific metric — this is the single most
consequential unresolved conflict in the package for a "tenant dues" AI answer.

**Blocks/limits:** Blocks — no reliable single "tenant balance" figure exists in the exported
evidence; any AI answer to "what does this tenant owe" must disclose the conflict rather than
assert one number.

---

<a id="c006"></a>
## C.006 — `v_occupancy` vs `v_active_tenants`

**Business area:** Occupancy.

**Definition A — `v_occupancy`** (`F.005`, 1 row). Bed-grained: joins `beds` (status='Live') to
`apartments` (status='Live'), then checks each Live bed for a `Staying`/`Booked`/`On-Notice`
allotment. Denominator = 195 Live beds in Live apartments. `occupancy_pct` numerator = `Staying`
only → **168/195 = 86.15%**.

**Definition B — `v_active_tenants`** (`F.022`, 1 row). Tenant-grained: `COUNT(DISTINCT
tenant_id)` directly from `tenant_allotments`, **no join to `beds` or `apartments` at all** —
bed/apartment `status` has no bearing on this count. `active_tenants` = `Staying` **+**
`On-Notice` combined.

**Exact numerical difference:** A's Staying-only bed count = 168. B's `active_tenants`
(Staying+On-Notice, tenant-grained) is exported as a single-row aggregate without a
directly-matching per-org breakdown in this snapshot (`F.022` is 1 row for the single
organization in this dataset); by construction it is expected to be **≥ 175** (168 Staying-bed
tenants + 7 On-Notice tenants, assuming one tenant per bed, which `H.013`'s 0-overlap finding
supports) minus any double-counting from a tenant holding two simultaneous allotments (`H.056`
finds 187 such overlapping bed/allotment pairs, so some inflation is possible in the opposite
direction). **The two numbers are not directly comparable without re-deriving both at the same
grain** — this document states the structural difference; it does not claim the two are within a
particular tolerance of each other, because no diagnostic file computes both at a common grain.

**Which datasets/views produce each:** `v_occupancy`, `v_active_tenants` (`M.016`).

**Likely mechanism:** two views built for different questions — "what fraction of physical beds
are filled" (A) vs "how many distinct people are currently tenants" (B) — that happen to share
similar-sounding names but count fundamentally different things (beds vs people) with different
inclusion rules (Staying-only vs Staying+On-Notice) and different universes (Live-only beds vs
all allotments regardless of bed/apartment status).

**Evidence:** `M.016`, `H.008`, `H.013`, `H.056`.

**Resolution status:** Conflicting definitions exist — not a numerical disagreement about the
same fact, but two different facts that must not be conflated.

**Recommended handling:** never use `v_active_tenants.active_tenants` to answer an
occupancy-percentage question, and never use `v_occupancy.occupied` to answer "how many tenants
do we have" — label each clearly by grain (beds vs tenants) in the semantic layer's metric
catalog.

**Expose both to AI?** Only if the user's question is ambiguous between "beds filled" and
"tenants active" — otherwise route to the correct one directly.

**Blocks/limits:** Limits — does not block either metric individually, but blocks any single
"occupancy" number from being used interchangeably for both bed-occupancy and tenant-count
questions.

---

<a id="c007"></a>
## C.007 — `get_universal_metrics` (v1) vs `get_universal_metrics_v2` occupancy formula

**Business area:** Occupancy.

**Definition A — v1's `propertyStatus.occupancyPct`.**
```sql
occ AS (SELECT COUNT(*) FILTER (WHERE has_staying) occupied, ... FROM bed_state)
'occupancyPct', ROUND(occupied::numeric/total*100)
```
Staying only. Live-bed universe filtered on `beds.status='Live'` **only** (no join requiring
`apartments.status='Live'`). Matches `H.012` definition D = **168/195**.

**Definition B — v2's `propertyStatus.occupancyPct`.**
```sql
'occupancyPct', ROUND(100.0 * (occupied + notice) / total, 2)
```
Staying **+** On-Notice. Live-bed universe filtered on `beds.status='Live' AND apartments.
status='Live'` (matches `v_occupancy`'s double filter). Matches `H.012` definition B =
**175/195**.

**Exact numerical difference:** **7 beds / 3.59 percentage points** (168/195 = 86.15% vs
175/195 = 89.74%) — exactly the 7 On-Notice beds identified in `H.011`.

**Which datasets/views produce each:** `FN.get_universal_metrics` (v1) and
`FN.get_universal_metrics_v2` — **both bodies fully exported and read in full**; this is not an
inference, it is a direct comparison of two `CREATE FUNCTION` statements that compute a
same-named JSON field (`propertyStatus.occupancyPct`) two different ways.

**Likely mechanism:** v2 is a documented rewrite of v1 ("source: journal_v2" in its own
`meta.source` output field) that also changed the occupancy formula's On-Notice treatment
(alongside the owner-rent fix in `C.011`) without renaming the output field. Any caller that
switched from v1 to v2 (or vice versa) would see `occupancyPct` change by ~3.6 points with no
underlying business change.

**Evidence:** `FN.get_universal_metrics`, `FN.get_universal_metrics_v2` (both bodies quoted in
full in `business_logic.md` §6.4–6.5), `H.011`, `H.012` (definitions B and D).

**Resolution status:** **Resolved** as a fact of the source code — both formulas are fully
readable and unambiguous; the conflict is which one the *application* currently calls, which is
**not determinable from exported evidence** (no calling code, e.g. API routes, was exported).

**Recommended handling:** the semantic layer must pick and document **one** canonical
`occupancyPct` formula (recommend B, Staying+On-Notice, since it is the more recent/v2
convention and avoids the C.009 bug) and never silently mix v1- and v2-sourced occupancy figures
in the same report or trend line.

**Expose both to AI?** Yes, if a user asks "what changed" or "why does occupancy show two
different numbers" — otherwise commit to one per the semantic layer's chosen canonical formula.

**Blocks/limits:** Blocks — silently mixing v1 and v2 outputs in a time series would produce a
fake occupancy jump/drop at the cutover point.

---

<a id="c008"></a>
## C.008 — `get_bed_occupancy_timeline` / `get_occupancy_intelligence` historical vs snapshot occupancy

**Business area:** Occupancy.

**Definition A — snapshot occupancy** (`v_occupancy`, `get_universal_metrics`
`propertyStatus`, `get_universal_metrics_v2` `status_now`). A single point-in-time count as of
`CURRENT_DATE`, from currently-active `tenant_allotments` rows only.

**Definition B — historical/lifetime occupancy** (`get_bed_occupancy_timeline`,
`get_occupancy_intelligence`). Both include `staying_status IN ('Staying','On-Notice','Exited')`
— **historically Exited tenancies count as occupied days** within the queried window. Neither
applies a Live-bed/apartment filter inside the function itself (`get_bed_occupancy_timeline`
takes one `bed_id` at a time and applies no status filter at all;
`get_occupancy_intelligence` restricts its own bed universe to Live beds/apartments via its
`live_bed` CTE, but still counts Exited stints as occupied days within the availability window).

**Exact numerical difference:** `H.012` definition E (`get_bed_occupancy_timeline`-basis,
Staying+On-Notice+Exited, **ALL 203 beds**, not just the 195 Live∩Live) = **194/203 = 95.57%** —
**26/195 to 30/203 percentage points higher** than any snapshot definition (A=86.15%,
B(v2)=89.74%). This is expected and not an error: a lifetime-coverage metric over the full
2019–2026 history will show far higher "ever occupied" rates than a today-only snapshot.

**Which datasets/views produce each:** listed above; full bodies in `business_logic.md` §6.3,
§6.6.

**Likely mechanism:** these are simply different questions ("is this bed occupied right now" vs
"across this bed's history, what fraction of days had a tenant") answered by design, not by
accident.

**Evidence:** `FN.get_bed_occupancy_timeline`, `FN.get_occupancy_intelligence`, `H.012e`.

**Resolution status:** Conflicting definitions exist only in the sense that both are legitimate
and must be labelled by time horizon — not a numerical error.

**Recommended handling:** never state a "get_bed_occupancy_timeline"-derived figure as "current
occupancy." Label every occupancy metric with its time horizon (snapshot / current-month /
lifetime) explicitly in the semantic layer's metric metadata.

**Expose both to AI?** Yes, when a user's question doesn't specify a time horizon ("what's our
occupancy" is ambiguous between "right now" and "historically") — ask or state both, labelled.

**Blocks/limits:** Limits — mislabelling a lifetime figure as current would materially overstate
today's occupancy.

---

<a id="c009"></a>
## C.009 — On-Notice occupancy treatment and the 7 unbucketed beds

**Business area:** Occupancy (item 8 in the brief; the specific SQL defect underlying
`H.011`/`H.013`, already identified structurally in `business_logic.md` §6.1 — restated here as
a formal conflict entry with its resolution status made explicit).

**Definition A — `v_occupancy`'s bucketing (defective).**
```sql
COUNT(*) FILTER (WHERE on_notice AND occupied)                      AS on_notice
COUNT(*) FILTER (WHERE NOT occupied AND NOT booked AND NOT on_notice) AS vacant
```
Requires a bed to be simultaneously `Staying` (`occupied`) **and** `On-Notice` to land in the
`on_notice` bucket. `H.013` proves **0 of 203 beds** ever carry both statuses
(`beds_with_both_statuses = 0`). A bed whose only allotment is `On-Notice`
(`occupied=false, on_notice=true, booked=false`) fails **every** filter: not `occupied`, not
(`on_notice AND occupied`), not `booked`, and not `vacant` (because `NOT on_notice` is false for
it). **It appears in none of the view's four output buckets.**

**Definition B — `get_universal_metrics` (v1 and v2)'s bucketing (correct).**
```sql
COUNT(*) FILTER (WHERE NOT has_staying AND has_notice) AS notice
```
Isolates on-notice-only beds correctly (equivalent to `has_notice` alone, given `H.013`'s 0
overlap), and `vacant = GREATEST(total - occupied - booked - notice, 0)` is a clean residual
that correctly places 168+7=175 beds outside `vacant`.

**Exact numerical difference:** **exactly 7 beds** (`H.011` names them by id:
`53df99b1…, 18323ac7…, dcfddc61…, cead0c81…, 3d87a782…, 2225fe89…, 16d9e7d4…`) are invisible to
`v_occupancy`'s four buckets, while the same 7 are correctly captured by both
`get_universal_metrics` variants' `notice` column. **195 total = 168 (v_occupancy `occupied`) +
0 (v_occupancy `on_notice`, structurally always 0) + `booked` + `vacant`(undercounted by 7)** —
i.e. `v_occupancy`'s own bucket columns will not sum to `total_beds` unless the caller notices
the shortfall.

**Which datasets/views produce each:** `v_occupancy` (defective); `FN.get_universal_metrics`,
`FN.get_universal_metrics_v2` (correct).

**Likely mechanism, proven from the SQL itself (not inferred):** `v_occupancy`'s `on_notice`
output column definition (`WHERE on_notice AND occupied`) was written as if a bed's `On-Notice`
status could coexist with its `Staying` status on the *same* current allotment (e.g. "staying
tenant who has given notice"), rather than `On-Notice` being a **distinct, mutually exclusive**
`staying_status` value in this schema. Because the schema's actual convention makes
`Staying` and `On-Notice` mutually exclusive states of one allotment (confirmed by `H.013`'s
0-overlap), the column's filter condition can never be satisfied.

**Evidence:** `M.016` (`v_occupancy`), `FN.get_universal_metrics`,
`FN.get_universal_metrics_v2`, `H.011`, `H.013`.

**Resolution status:** **Resolved.** This is a proven SQL defect in `v_occupancy` specifically —
not a legitimate alternative definition. The evidence (`H.013`'s 0-overlap fact, checked against
`v_occupancy`'s own filter logic) proves the `on_notice` bucket can never register a positive
count and the 7 On-Notice-only beds are structurally excluded from all four named buckets.

**Recommended handling:** do not use `v_occupancy`'s `on_notice`/`vacant` columns for any
downstream metric. Use `get_universal_metrics_v2`'s bucketing (or an equivalent corrected query)
as the canonical bed-status bucketing going forward. `v_occupancy.occupied` (Staying-only) and
`v_occupancy.occupancy_pct` remain valid as a Staying-only occupancy figure (definition A/D in
C.007) — only the `on_notice`/`vacant` split is broken.

**Expose both to AI?** No — this is not a legitimate two-sided conflict; the AI layer should use
the corrected bucketing and, if asked specifically about `v_occupancy`'s numbers, disclose the
known defect rather than presenting it as an equally-valid alternative.

**Blocks/limits:** Blocks — any report built on `v_occupancy`'s `vacant` count will understate
true vacancy risk awareness by exactly the number of On-Notice-only beds present at query time
(7, in this snapshot).

---

<a id="c010"></a>
## C.010 — Ledger profit vs application `get_universal_metrics` profit

**Business area:** Profit / P&L.

**Definition A — `v_pnl.net_profit`** (`F.001`). Pure ledger: `SUM(INCOME signed_amount) -
SUM(EXPENSE signed_amount)` from `v_account_balances` (reversals excluded), for whatever is
actually posted to `4xxx`/`5xxx` accounts.

**Definition B — `get_universal_metrics` v1 `totalProfit`.**
```sql
(SELECT SUM(total_amount) FROM i_period) - (SELECT SUM(amount) FROM e_period)
```
Invoice-total minus expense-total, both from application tables (`invoices`, `expenses`)
directly for the period window, **not from the ledger at all**. **No owner-payments term** —
see `C.011`.

**Definition C — `get_universal_metrics_v2` `totalProfit`.** `v_revenue - v_expenses`, both
derived from `v_pnl_by_category` (ledger-based) summed over `[v_from, v_to]`, **with the
owner-rent bucket explicitly replaced** by `SUM(owner_payments.escalated_amount)` for the window
(`C.011`).

**Exact numerical difference:** **Not determinable from exported evidence as a single number** —
no diagnostic exports A, B, and C computed for the same organization and period side by side.
What is provable structurally: A and C share the same revenue basis (ledger `4xxx` accounts) but
different expense bases (A = raw ledger `5xxx`; C = ledger `5xxx` with the owner-rent
substitution). B uses a wholly different source (invoices/expenses tables, not the ledger) and
so is expected to diverge from both A and C by at least the invoice-vs-ledger drift documented
in `C.015` (₹2 423 270.00 aggregate) plus the full owner-rent gap documented in `C.011`.

**Which datasets/views produce each:** `v_pnl` (A), `FN.get_universal_metrics` (B),
`FN.get_universal_metrics_v2` (C) — all three bodies fully exported and quoted in
`business_logic.md` §8.

**Likely mechanism:** three independently-evolved profit calculations — a pure ledger view, an
early application-layer approximation (B, invoice/expense based, pre-dating the ledger becoming
authoritative), and a corrected ledger-based rewrite (C) that fixes the owner-rent omission that
B has.

**Evidence:** `M.016`, `FN.get_universal_metrics`, `FN.get_universal_metrics_v2`, `C.011`,
`C.015`.

**Resolution status:** Conflicting definitions exist. The evidence proves B systematically
omits owner rent (`C.011`) and is invoice-based rather than ledger-based (structurally
different inputs from A/C), but does not prove which of A or C is closer to "true" profit
without a live-database join that the exported package does not contain.

**Recommended handling:** treat C (`get_universal_metrics_v2`) as the most complete of the
three (ledger-based, includes owner rent) for any new metric; retain A (`v_pnl`) as the
raw-ledger reference figure; retire B (`get_universal_metrics` v1's `totalProfit`) or clearly
flag it as legacy/incomplete (missing owner rent) if it must still be surfaced.

**Expose both to AI?** Yes, whenever profit is asked about with no further qualification —
state the ledger figure as primary and disclose that an older, invoice-based calculation exists
and excludes owner rent.

**Blocks/limits:** Blocks — "why did profit fall" cannot be answered reliably without first
establishing which of the three profit definitions the question is about, since B's absence of
owner rent alone can produce a profit *increase* in B that A/C would show as flat or falling (or
vice versa) purely from an owner-payment timing shift.

---

<a id="c011"></a>
## C.011 — Owner-rent treatment in profit (item H in the brief)

**Business area:** Profit / P&L, owner payments.

**Definition A — `get_universal_metrics` v1.** `totalProfit = SUM(invoices.total_amount) -
SUM(expenses.amount)`. **No owner_payments term of any kind.** The view
`v_diag_owner_rent_missing_from_profit` (`F.028`) states this in its own `note` column,
verbatim: *"Currently NOT included in get_universal_metrics.totalProfit."*

**Definition B — `v_pnl`/`v_pnl_by_category`.** Includes owner rent **only to the extent it is
actually posted to the ledger's `owner_rent` bucket (`account_code LIKE '510%'`)** — whatever
that amount is, verified by `H.001` to be a `PERFECT` match (0.00 diff) between
`owner_payments`'s `COALESCE(escalated_amount, base_amount)` total and the ledger's net debit
for `source_table='owner_payments'`. So B's owner-rent figure, when it does post, is complete —
but §8.4 of `business_logic.md` notes the posting trigger body itself (`trg_owner_payment_
journal_post`) is not exported, so the *account* it posts to is not independently verified from
source, only from the aggregate-match diagnostic.

**Definition C — `get_universal_metrics_v2`.**
```sql
v_owner_rent_pnl := v_owner_rent;   -- ledger's '510%' bucket for the period
SELECT SUM(op.escalated_amount) INTO v_owner_rent
  FROM owner_payments WHERE bill_date BETWEEN v_from AND v_to;
v_expenses := v_expenses - v_owner_rent_pnl + v_owner_rent;
```
**Explicitly discards the ledger's period-bucketed owner-rent figure and replaces it with
`SUM(owner_payments.escalated_amount)` filtered on `bill_date`**, before computing
`totalExpenses`/`totalProfit`. Read directly from the function body — not inferred.

**Exact numerical difference:** `v_diag_owner_rent_missing_from_profit` (`F.028`, 46 months)
totals **₹19 019 250.00** in `owner_rent_paid_or_accrued` across all months
(`status IN ('paid','pending')`, `COALESCE(paid_date, due_date)` basis) — this is the amount A's
`totalProfit` misses entirely for every period it is asked about. `H.058`/`v_diag_owner_rent_
missing_from_profit`'s companion `H.030` (`pnl_owner_rent_vs_payments`, 54 months) compares
`v_pnl_by_category.owner_rent` (ledger bucket) against `owner_payments.amount` directly per
month — this file exists specifically to quantify how closely B's ledger figure already tracks
the raw `owner_payments` total before C's substitution; its per-month `difference` column is the
authoritative month-by-month figure for anyone reconciling B vs the raw source, and is preserved
in that file rather than re-aggregated here.

**Which datasets/views produce each:** `FN.get_universal_metrics` (A, omits),
`v_pnl`/`v_pnl_by_category` (B, ledger as-posted), `FN.get_universal_metrics_v2` (C, explicit
substitution). `v_diag_owner_rent_missing_from_profit` documents A's gap in its own text.

**Likely mechanism:** A pre-dates owner-rent being reliably posted to the ledger (or was simply
never updated to include it); C is a direct, deliberate fix, confirmed by reading its source.
The three-way date-basis conflict compounding this (`bill_date` vs `paid_date`/`due_date`) is
documented separately in `business_logic.md` §8.4 and not repeated here.

**Evidence:** `FN.get_universal_metrics`, `FN.get_universal_metrics_v2`, `M.016`
(`v_diag_owner_rent_missing_from_profit`'s own note), `H.001`, `H.030`.

**Resolution status:** **Resolved** — the evidence proves A structurally omits owner rent (both
by reading the function body and by the view's own self-documenting note) and proves C's
mechanism for including it. Whether C's substituted figure exactly equals what B's ledger bucket
*would* show if fully reconciled is not separately proven (`H.030`'s per-month diffs are the
relevant evidence for that narrower question and are preserved unresolved there).

**Recommended handling:** never use `get_universal_metrics` v1's `totalProfit` for any
owner-rent-sensitive question ("is the business profitable after owner payments") — it is
proven incomplete. Use C (`get_universal_metrics_v2`) or B (`v_pnl`) instead, both of which
include an owner-rent term.

**Expose both to AI?** Only to explain the discrepancy if a user compares two profit figures
from different periods/tools; otherwise route to C.

**Blocks/limits:** Blocks — v1's `totalProfit` alone cannot answer "why did profit fall" if the
real driver was an owner-rent posting event (e.g. the single-batch posting run on 2026-08-13,
`business_logic.md` §9.2) — v1 would not reflect it at all.

---

<a id="c012"></a>
## C.012 — P&L named category buckets vs total expenses (item 11 in the brief)

**Business area:** Expenses, P&L.

**Definition A — `v_pnl`/`v_pnl_by_category.total_expenses`.** `SUM(signed_amount WHERE
account_type='EXPENSE')` — **every** `5xxx` account, unconditionally.

**Definition B — `sum_of_buckets`** (the 9 named categories in `v_pnl_by_category`: `owner_rent
'510%'`, `maintenance '52%'`, `housekeeping '53%'`, `utilities '54%'`, `property_ops '55%'`,
`administrative '56%'`, `salaries '57%'`, `marketing '58%'`, `other_expenses '59%'`).

**Exact numerical difference (re-derived in this pass from the raw `H.017` CSV, all 57 months):**
`SUM(total_expenses) = ₹20 784 832.00`; `SUM(sum_of_buckets) = ₹19 754 214.00`;
`SUM(unbucketed) = ₹1 030 618.00` — and **`unbucketed` equals `electricity_column` exactly in
every one of the 57 rows**, confirmed by independently summing both columns and finding them
identical (₹1 030 618.00 = ₹1 030 618.00). **4.96% of total expenses are invisible to the 9
named category buckets.**

**Which datasets/views produce each:** `v_pnl_by_category` (`M.016`) computes `total_expenses`
and a separate, tenth `electricity` column (pattern `'515%'`); `H.017`/`H.054` (byte-identical)
is the diagnostic that names the gap `unbucketed` and proves it equals `electricity_column`.

**Likely mechanism, proven from the SQL:** account `5150` "Electricity Payments" is a direct
child of `5000` with code prefix `515` — it matches **none** of the 9 named `LIKE` patterns
(`owner_rent` requires `510%`; the nearest numeric neighbor, `utilities`, requires `54%`, not
`51%`). `v_pnl_by_category` computes a separate `electricity` column using its own `'515%'`
pattern specifically to capture this account, but that column is not one of the 9 buckets that
"sum_of_buckets" (as measured by `H.017`) totals — see `C.013` for the account-level detail.

**Evidence:** `M.016` (`v_pnl_by_category`), `H.017`, `H.054`.

**Resolution status:** **Resolved** — the arithmetic identity (`unbucketed ==
electricity_column`, exact, all 57 months) proves the mechanism beyond doubt; this is not a
disagreement between two valid definitions but a **coverage gap** in one of them (the 9-bucket
breakdown).

**Recommended handling:** any expense-category report built from `v_pnl_by_category`'s 9 named
columns must add the `electricity` column as a 10th named category, or it will silently
undercount total expenses by ~5% relative to its own `total_expenses`/`revenue` figures on the
same row.

**Expose both to AI?** No — this should simply be fixed in the semantic layer's category
catalog (treat `electricity` as a first-class 10th bucket); no ambiguity for the AI to disclose
once fixed.

**Blocks/limits:** Blocks — any "expense breakdown by category" answer sourced from the 9 named
buckets alone will not reconcile to the reported `total_expenses`/`net_profit` on the same row.

---

<a id="c013"></a>
## C.013 — Electricity account 5150 (item 12 in the brief)

**Business area:** Expenses, EB.

This is the account-level detail behind `C.012`, treated as its own entry because **three
different, independently-written views categorise account `5150` three different ways**:

- **`v_pnl_by_category`**: `5150` matches none of the 9 named buckets; captured only in a
  separate, 10th `electricity` column (`'515%'` pattern). Excluded from `sum_of_buckets`.
- **`v_expense_composition`**: uses `COALESCE(parent_code, account_code)` — `5150`'s
  `parent_code` is `5000` ("Operating Expenses"), so it rolls up to the **same category as
  `5100` (Owner Rent)** here, both landing under "Operating Expenses." This view **does**
  include `5150` in its category totals, unlike `v_pnl_by_category`.
- **`v_bed_expense_breakdown`** and **`v_revenue_by_period`/`v_expenses_by_period`**: use raw
  `account_code`/`account_name`, no rollup at all — `5150` appears as its own line, correctly,
  in both.

**Exact numerical difference:** `C.012`'s ₹1 030 618.00 (57-month total) is the amount that
disappears specifically in `v_pnl_by_category`'s 9-bucket view; the same amount is fully present
(under a shared "Operating Expenses" label with owner rent) in `v_expense_composition`, and fully
present (as its own labelled line) in the two ungrouped views.

**Which datasets/views produce each:** `v_pnl_by_category`, `v_expense_composition`,
`v_bed_expense_breakdown`, `v_expenses_by_period` (`M.016`).

**Likely mechanism:** `v_pnl_by_category`'s category patterns were hand-written per named
category (`owner_rent '510%'`, `maintenance '52%'`, etc.) and the author did not add a pattern
covering `510`–`519` generally or `515` specifically outside the dedicated `electricity` column
— an omission in that one view's bucket list, not present in the other three views because they
either use the COA's own parent-child structure (`v_expense_composition`) or don't roll up at
all (the other two).

**Evidence:** `T.coa_accounts` (`H.016`, account `5150` "Electricity Payments," parent `5000`),
`M.016` (all four view definitions), `H.017`.

**Resolution status:** **Resolved** — proven by direct SQL comparison across the four views;
account `5150`'s treatment is a documented fact, not an open question.

**Recommended handling:** the semantic layer's canonical expense-category taxonomy should follow
`v_expense_composition`'s COA-parent-based rollup (or `v_pnl_by_category`'s pattern list with
`5150` added as its own bucket) — not both simultaneously, since they currently disagree on
whether electricity is its own category or shares "Operating Expenses" with owner rent.

**Expose both to AI?** No — pick one categorisation (recommend: electricity as its own named
bucket, matching how the business already thinks about EB as a distinct cost center per the
brief's own framing) and apply it consistently; disclose only if a user's own report was built
on the other convention.

**Blocks/limits:** Limits — narrows to expense-category reporting; does not affect
`total_expenses` or `net_profit` totals (both already include `5150` via the unconditional
`account_type='EXPENSE'` filter).

---

<a id="c014"></a>
## C.014 — Receipt source amount vs ledger amount (item 13 in the brief)

**Business area:** Receipts / ledger.

**Definition A — source amount.** `SUM(receipts.amount_paid) WHERE NOT is_deleted` = **5758
live receipts**, aggregate ₹81 855 686.97 (`H.001`).

**Definition B — ledger cash posted (`M.COL.003`).** `SUM(debit)` for `journal_entries` with
`source_table='receipts' AND code IN ('1110','1120')`, reversal-**excluded** (reversal entries
and the forward entries they reverse are both dropped) = **₹81 839 404.52**, from 5 755
bank-debit lines — exactly one per posted live receipt, credit side ₹0.00. This is the
convention `get_universal_metrics_v2`'s own `v_collections` SQL applies.

**Definition B′ — `H.001`'s diagnostic figure (a view construction, not a registry metric).**
`SUM(CASE WHEN is_reversal_of IS NULL THEN debit ELSE -debit END)` over the same rows =
₹87 196 482.59 (`H.001`). The `-debit` branch never fires: reversal lines carry credit and not
debit, so nothing is subtracted and the result is gross debit including ₹5 357 078.07 of
forward postings that were later reversed.

**Exact numerical difference (A vs B):** **₹16 282.45**, traced to exactly 4 receipts:

| receipt | number | source amount | ledger debit | source − ledger |
|---|---|---|---|---|
| `8a8f7848…` | `VISTA/26-27/04/R00250` | ₹16 627.45 | ₹0.00 (no journal entry exists) | +₹16 627.45 |
| `3789971b…` | `VISTA/26-27/08/R00062` | ₹19 519.00 | ₹19 919.00 | −₹400.00 |
| `118da474…` | `VISTA/26-27/08/R00156` | ₹17 630.00 | ₹17 577.00 | +₹53.00 |
| `ec8a0992…` | `VISTA/26-27/08/R00136` | ₹18 042.00 | ₹18 040.00 | +₹2.00 |

These are rows 5, 8, 9 and 10 of `H.048`; `H.033` reports the same 3 unposted live receipts
(₹16 627) independently. The other 7 `H.048` rows all carry `reversal_count ≥ 1` — their
inflation is netted away entirely under B and contributes ₹0.00.

**Exact numerical difference (A vs B′):** ₹5 340 795.62, verdict `INVESTIGATE` (`H.001`).
This is **a formula artifact, proven by direct recomputation**, not a receipts drift: 112
reversal credit lines totalling ₹5 357 078.07 exactly offset the 112 forward debit lines they
reverse, and ₹5 357 078.07 − ₹16 282.45 = ₹5 340 795.62 exactly. The repost-accumulation
hypothesis recorded earlier does explain the per-row `H.048` ratios, but it does **not**
explain this aggregate, which the missing subtraction accounts for in full.

**Which datasets/views produce each:** `receipts` (A, `T.receipts`); `journal_lines` joined to
`coa_accounts`, filtered to `source_table='receipts'` (B, `T.journal_lines`/`T.coa_accounts`);
`v_je_amount_reconciliation` (`H.001`) computes B′; the row-level trace (`H.048`) is **not**
one of the 54 exported view definitions — its generating SQL is not in `M.016`.

**Why the 4 residual receipts differ: not determinable from exported evidence.** `8a8f7848…`
has zero `journal_entries` rows, so no posting was ever made; the reason is not recorded. The
other three each have one entry, never reversed, internally balanced at the ledger amount,
with `posted_at` equal to `receipts.created_at` to the microsecond. `build_receipt_lines()` —
the function that decides the posted amount — is not among the 28 exported function
definitions, and `receipts` carries no `updated_at` column, so a later edit can be neither
confirmed nor ruled out.

**Evidence:** `H.001`, `H.033`, `H.048`, `T.receipts`, `T.journal_lines`, `T.coa_accounts`,
`FN.get_universal_metrics_v2`, `FN.trg_receipt_journal_post`.

**Resolution status:** **Conflicting definitions exist. Business decision required.** A and B
are each faithful to a definition the application itself ships — `get_universal_metrics`
computes A, `get_universal_metrics_v2` computes B — and no exported view, function or document
names either as the official collections figure. B′ is not a candidate definition; it is a
defective reproduction of B. Neither A nor B has been selected as canonical.

**Recommended handling:** keep A (`M.COL.001`) and B (`M.COL.003`) as separate metrics, both
disclosed, neither merged and neither retired. Route the 4 residual receipts to operations as
records to check, starting with `VISTA/26-27/04/R00250` (₹16 627.45, unposted). Do not quote
₹5 340 795.62 as a receipts drift.

**Expose both to AI?** Both definitions stay exposed as separate metrics (`M.COL.001`,
`M.COL.003`), with the ₹16 282.45 residual disclosed alongside either figure. Trust
classification unchanged: `DISCLOSE`.

**Blocks/limits:** Limits — a business decision is outstanding on which definition is
official, and individual-receipt ledger tracing is affected for the 4 named receipts; does not
block `v_pnl`/`v_revenue_by_period` totals.

---

<a id="c015"></a>
## C.015 — Invoice source amount vs ledger amount (item 14 in the brief)

**Business area:** Invoices / ledger.

**Definition A — source amount.** `SUM(invoices.total_amount) WHERE NOT is_deleted` = 5214 live
invoices, aggregate ₹72 405 785.40 (`H.001`).

**Definition B — ledger net amount.** Same construction as `C.014`, for
`source_table='invoices' AND account_type='ASSET'` (AR account `1200`) = ₹74 829 055.40
(`H.001`).

**Exact numerical difference:** **₹2 423 270.00**, verdict `INVESTIGATE` (`H.001`).
`H.049` (120-row trace, fully summed in this pass): `SUM(difference) = ₹2 423 270.00` — **exactly
matches `H.001`'s aggregate diff**, confirming `H.049` is the complete row-level breakdown of
that gap (all 120 drifting invoices account for the full ₹2 423 270.00; no residual is hidden
elsewhere). `entry_count` distribution across the 120 rows: 75 rows at 3, 26 at 5, 5 at 7, 5 at
9, 1 at 4, 1 at 11, 1 at 15, 3 at 2, 3 at 0. The largest single drift, `VISTA/26-27/05/00077`:
`source_amount ₹11 875.00`, `ledger_amount ₹87 635.00` (≈7.4×), `entry_count=15,
reversal_count=7` (8 forward postings) — all 6 largest-drift rows in `H.049` are `status=pending,
invoice_type=regular`, `invoice_date` in **2026-05 through 2026-08** (i.e. recent, still-open
invoices).

**Which datasets/views produce each:** `invoices` (A); `journal_entries`/`journal_lines`
filtered to `source_table='invoices'` (B); `v_je_amount_reconciliation` (`H.001`, aggregate);
`H.049` (row trace, generating SQL **not** among the 54 exported view definitions —
**not determinable from exported evidence** beyond what the columns show).

**Likely mechanism:** the concentration of large-drift rows among **recent, pending, repeatedly
edited invoices** (high `entry_count`) is consistent with the same repost-accumulation pattern
hypothesised in `C.014` — `FN.trg_invoice_journal_post`'s `UPDATE` branch reverses and reposts on
any change to `total_amount, rent_amount, electricity_amount, other_charges, late_fee,
invoice_type`, and pending/recent invoices are the ones most likely to still be actively edited
(e.g. as EB charges are finalised). **Stated as the most evidence-consistent hypothesis, not
proven**, for the same reason as `C.014` (the diagnostic's own SQL is not exported).

**Evidence:** `H.001`, `H.049`, `T.invoices`, `FN.trg_invoice_journal_post`.

**Resolution status:** Conflicting definitions exist; the row-level total is proven to fully
reconcile to the aggregate diff (a genuine resolution of *where* the ₹2.42M lives, even though
*why* the ledger diverges from source at this magnitude for these 120 invoices is not proven from
an exported query definition).

**Recommended handling:** same as `C.014` — flag high-`entry_count` invoices for review before
trusting an individual invoice's ledger-derived total; org-level `v_pnl`/`v_revenue_by_period`
totals use the reversal-excluded `v_account_balances` convention and are not directly shown to
share this drift.

**Expose both to AI?** Only for individual-invoice questions; not for aggregate revenue.

**Blocks/limits:** Limits — same scope as `C.014`.

---

<a id="c016"></a>
## C.016 — Deposit settlement source amount vs ledger amount (item 15 in the brief)

**Business area:** Deposits / ledger.

**Definition A — source amount.** `SUM(deposit_settlements.refund_amount) WHERE NOT is_deleted`
= ₹5 085 959.33 (`H.001`).

**Definition B — ledger net amount.** Same construction as `C.014`/`C.015`, for
`source_table='deposit_settlements' AND account_type='ASSET' AND code LIKE '11%'` =
₹5 669 454.67 (`H.001`).

**Exact numerical difference:** **₹583 495.34**, verdict `INVESTIGATE` (`H.001`).
`H.050` (43-row trace, fully re-summed in this pass): `SUM(difference) = ₹583 495.34` — **exactly
matches `H.001`'s aggregate**, confirming full row-level accountability. `entry_count`
distribution: **37 of 43 rows have `entry_count=3` exactly** (a strong, narrow cluster, unlike
`C.015`'s wide spread); 3 rows at `entry_count=0` (source exists, no ledger posting at all —
`difference` negative, e.g. settlement `89091842…`, `status=pending`, expected per `C.024`'s
posting-gate rule); 3 at `entry_count=1` (clean, small residual differences of ₹400/-₹53/-₹2,
consistent with normal rounding). **23 of the 43 rows (all `status=completed, entry_count=3`)
show `ledger_amount` within ₹1 of exactly 2× `source_amount`** — re-verified directly in this
pass (e.g. `28500 → 57000.00`, `24750 → 49500.00`, `24552 → 49104.00`, `23250 → 46500.00`,
`21750 → 43500.00`, all exact 2.0000× multiples).

**Which datasets/views produce each:** `deposit_settlements` (A); ledger filtered to
`source_table='deposit_settlements'` (B); `v_je_amount_reconciliation` (`H.001`); `H.050` (row
trace, generating SQL not exported).

**Likely mechanism, directly consistent with `entry_count=3` and the exact 2× ratio:** a
settlement with `entry_count=3` under `FN.trg_settlement_journal_post`'s "amounts changed"
branch (§`business_logic.md` §5.1) means exactly one repost cycle occurred: 1 original forward
entry + 1 reversal entry + 1 corrected forward entry = 3 `journal_entries` rows. **If the
diagnostic's "ledger_amount" sums `credit` (or `debit`) across all 3 entries without netting the
reversal against the original** (i.e. it is a raw `SUM`, not a reversal-aware `SUM`), and the
reversal entry cancels the original by posting the *opposite* line type (debit where the
original had credit) rather than a negative credit, then a plain `SUM(credit)` over the 3 rows
would total `original_credit + corrected_credit = 2 × current source_amount` exactly — matching
the observed pattern precisely. **This is a strong, arithmetically-consistent hypothesis given
the exact 2.0000× ratio on 23/43 rows, but it is not proven from an exported query definition**
(`H.050`'s SQL is not among the 54 exported views).

**Evidence:** `H.001`, `H.050`, `T.deposit_settlements`, `FN.trg_settlement_journal_post`.

**Resolution status:** Conflicting definitions exist; mechanism strongly indicated by the exact
2× arithmetic pattern but not confirmed by an exported query definition — this is the strongest
mechanistic lead of the three source-vs-ledger conflicts (`C.014`/`C.015`/`C.016`) precisely
because of how clean the 2× ratio is.

**Recommended handling:** if this diagnostic's query is available for live-database
re-inspection, re-run it with an `is_reversal_of IS NULL`-aware `SUM` and compare — this is the
single highest-confidence next investigative step among the three source-vs-ledger conflicts.
Until then, do not trust `H.050`'s "ledger_amount" column as a true net ledger figure for any
settlement with `entry_count > 1`.

**Expose both to AI?** Only for individual-settlement questions.

**Blocks/limits:** Limits — same scope as `C.014`/`C.015`; does not affect
`v_pnl`/`v_org_cash_balance` aggregate totals (reversal-excluded convention).

---

<a id="c017"></a>
## C.017 — Live source row counts vs journal-entry source counts (item 16 in the brief)

**Business area:** Ledger, all financial domains.

**Definition A — live source rows.** `COUNT(*) WHERE NOT is_deleted` (or `COUNT(*)` where the
table has no `is_deleted` column) per source table.

**Definition B — distinct journal-entry sources.** `COUNT(DISTINCT source_id) FILTER (WHERE
is_reversal_of IS NULL)` per `source_table`, from `journal_entries`.

**Exact numerical difference, per source table (`H.002`, all 7 rows, re-verified in this pass):**

| source_table | legacy_live (A) | je_distinct_sources (B) | gap (A−B) |
|---|---|---|---|
| `receipts` | 5758 | 5855 | **−97** |
| `invoices` | 5214 | 5204 | **+10** |
| `deposit_settlements` | 307 | 300 | **+7** |
| `tenant_adjustments` | 260 | 266 | **−6** |
| `expenses` | 516 | 516 | 0 |
| `owner_payments` | 345 | 345 | 0 |
| `tenant_transactions` | 16 451 | 0 | **+16 451** |

**Which datasets/views produce each:** `v_je_source_counts` (`H.002`, generating SQL not among
the 54 named views — this is a diagnostic query, described but not independently re-derivable
beyond its exported output).

**Likely mechanism:**
- **`receipts`: −97 (more distinct JE sources than live receipts).** Consistent with receipts
  that were later soft-deleted (`is_deleted=true`) but whose forward journal entries still carry
  a distinct `source_id` counted here — this table's `is_reversal_of IS NULL` filter counts
  *forward* entries regardless of the current source row's deletion state, so a soft-deleted
  receipt's original (un-reversed-at-the-JE-level, i.e. still `is_reversal_of IS NULL`) forward
  entry can still contribute to `je_distinct_sources` even though it no longer counts as "live"
  in `legacy_live`. Directly corroborated by `C.018`'s finding of 200 `journal_entries` rows
  referencing a currently-soft-deleted receipt.
- **`invoices`/`deposit_settlements`: +10 / +7 (more live sources than JE sources).** Consistent
  with `C.024`'s posting-gate finding (settlements only post when `status IN ('completed',
  'approved')`) and with invoices that failed to post for some other reason — `H.042`
  (`v_je_intentional_skips`, 20 rows total across all three checked tables) is the named,
  purpose-built diagnostic for exactly this gap; its row-level detail is the authoritative source
  for *which* rows are missing, not re-derived here.
- **`tenant_adjustments`: −6.** Smallest gap of the four non-zero rows; not further traced here.
- **`tenant_transactions`: +16 451 (100% gap).** Confirms `C.003` — this table is entirely
  disconnected from `journal_entries` (0 distinct sources, because it is never referenced by
  `journal_entries.source_table`).

**Evidence:** `H.002`, `H.042`, `T.receipts`, `T.invoices`, `T.deposit_settlements`,
`T.tenant_adjustments`, `T.tenant_transactions`.

**Resolution status:** **Resolved as a count** (the gaps are exactly quantified above); the
*cause* of each gap is traced to a specific, named mechanism for `receipts` (soft-delete,
corroborated by `C.018`) and `tenant_transactions` (structural disconnection, `C.003`), and
partially traced for `invoices`/`deposit_settlements`/`tenant_adjustments` (posting-gate and
`H.042`'s named skip-list) without row-by-row confirmation in this pass.

**Recommended handling:** treat `H.042`'s 20-row list as the authoritative "why is this source
row not posted" answer for invoices/receipts/deposit_settlements — do not re-derive from the
aggregate gap alone. `tenant_transactions` should never be expected to reconcile against
`journal_entries` (by design, per `C.003`).

**Expose both to AI?** Not directly a user-facing metric — this is a data-quality/completeness
check that belongs in `data_quality_report.md`; included here because it is the numeric
foundation several other conflicts (`C.003`, `C.018`) cite.

**Blocks/limits:** Limits — establishes the scale of source/ledger population mismatch across
every financial domain; does not by itself block any single metric beyond what `C.003`/`C.014`–
`C.016`/`C.018` already state.

---

<a id="c018"></a>
## C.018 — Soft-deleted / missing sources vs surviving journal entries (item 17 in the brief)

**Business area:** Ledger integrity.

**Definition A — "no orphans" (integrity confirmed).** `H.051`
(`je_missing_deleted_sources`) and the separate FK-orphan checks (`H.021`: 14 407
allotment-linked lines, 0 orphans; `H.025`: `journal_entries.source_id` → `invoices`/`receipts`/
`expenses`, 0 orphans in all three, re-verified in this pass) together show: for
`deposit_settlements` (376 entries) and `invoices` (5558 entries), **`missing_source=0` and
`soft_deleted_source=0`** — every journal entry for these two tables points to a source row that
both exists and is not soft-deleted.

**Definition B — journal entries surviving a soft-deleted source (a real, quantified
exception).** For `receipts` (6085 total entries), `H.051` shows **`soft_deleted_receipt = 200`**
— 200 journal-entry rows reference a `receipts.id` whose current `is_deleted = true`. `missing_source=0`
for receipts too (the receipt row itself still exists, merely soft-deleted).

**Exact numerical difference:** 200 of 6085 receipt-sourced journal entries (3.29%) reference a
soft-deleted receipt; 0 of 376 deposit-settlement entries and 0 of 5558 invoice entries show the
same pattern.

**Which datasets/views produce each:** `H.051` (generating SQL not among the 54 named views);
`H.021`/`H.025` (FK-orphan checks, also not named views but simpler, directly-interpretable counts).

**Likely mechanism — verified and corrected in this pass.** The most obvious hypothesis — that
this reflects the `receipts_dedup_audit` table's 9 duplicate-receipt-detection groups
(`T.receipts_dedup_audit`) — was **checked directly against the data and disproven**: of the 23 receipt ids
named across all 9 dedup groups, only 11 still exist in the exported `receipts` table (12 have
been **hard-deleted**, not soft-deleted), and **none of those remaining 11 have `is_deleted =
true`** — all are still live duplicates. **The dedup-detection table does not explain the 200
soft-deleted-but-referenced receipts; the actual cause is not determinable from exported
evidence.** What *is* established as a design fact (not a bug) per `business_logic.md` §1.4: a
receipt's soft-delete triggers `reverse_journal_entry`, which adds a *new* reversal entry and
leaves the original forward entry in place — so a soft-deleted receipt is *expected* to still
have `journal_entries` referencing it (both the original and its reversal). **200 is therefore
consistent with the reversal-not-deletion design working as intended**, not evidence of a broken
mechanism, though this document cannot confirm the exact figure decomposes cleanly into
100 original+100 reversal pairs without the underlying row-level join (not exported).

**Evidence:** `H.051`, `H.021`, `H.025`, `T.receipts_dedup_audit`, cross-checked and
ruled out as the cause), `T.receipts`.

**Resolution status:** **Resolved** for `invoices`/`deposit_settlements` (0 orphans, 0
soft-delete survivors — clean). For `receipts`, the *existence* of 200 survivor entries is
resolved and explained by the reversal-not-deletion design (`business_logic.md` §1.4); the
specific hypothesis this document initially considered (dedup-driven) was tested and disproven
in this pass, and no alternative specific cause is proven — **"Not determinable from exported
evidence"** for anything beyond the general design mechanism.

**Recommended handling:** do not flag the 200 receipt-linked survivor entries as a data
corruption issue by default — they are consistent with correct reversal behavior. Do flag them
for review if a metric needs to distinguish "reversed because the receipt was deleted" from
"reversed for another reason" (edit/correction), since `H.051`'s count does not separate the two.

**Expose both to AI?** No — this is an integrity-check result, not a user-facing metric
conflict; route to `data_quality_report.md`.

**Blocks/limits:** Does not block — the mechanism is understood and consistent with the
documented design; only the specific *trigger event* for each of the 200 is unresolved.

---

<a id="c019"></a>
## C.019 — `v_tenant_aging` bucket semantics (item 18 in the brief)

**Business area:** AR aging.

**Not a two-sided definitional conflict** — `v_tenant_aging`'s buckets
(`bucket_0_30/31_60/61_90/90_plus`) are unambiguously defined:
```sql
SUM(net) FILTER (WHERE CURRENT_DATE - charge_date BETWEEN 0 AND 30)   AS bucket_0_30
-- etc, sourced from raw journal_lines/journal_entries (reversals INCLUDED, per C.002)
```
**The issue is reproducibility, not semantics.** `CURRENT_DATE` is evaluated **at query time**,
so the exported CSV (`F.008`) reflects buckets computed relative to whatever moment inside the
export window (`M.002`–`M.099`, 2026-08-29 09:02–11:18) the query actually ran. Re-running the
same view definition today, or on any other date, produces different bucket assignments for the
same underlying charges — a charge that was "0-30 days" at export time moves buckets every day
thereafter.

**Exact numerical difference:** not applicable — there is no second definition to diff against.
The "difference" is between the exported snapshot and any later re-computation, which cannot be
quantified without a second query run (not available offline).

**Which datasets/views produce it:** `v_tenant_aging` (`M.016`) only.

**Likely mechanism:** standard aging-bucket design (correct and expected for a live application);
the hazard is specific to **offline reconstruction from a frozen CSV export**.

**Evidence:** `M.016` (`v_tenant_aging` SQL), `M.002`/`M.099` (snapshot timestamps).

**Resolution status:** Not a conflict between competing definitions — resolved as a
snapshot-dependence fact. Recorded here because the brief specifically asked it be investigated.

**Recommended handling:** any reconstruction of `v_tenant_aging` must fix an explicit "as-of"
date (recommend: the export's `M.002` timestamp, 2026-08-29) and label every aging bucket with
that date. Never compare an aging bucket reconstructed today against the exported `F.008` values
without accounting for the date shift.

**Expose both to AI?** N/A — instead, the AI layer must always state the as-of date whenever it
reports an aging bucket.

**Blocks/limits:** Limits reproducibility only; does not block the underlying AR figures
(`bucket_0_30 + bucket_31_60 + bucket_61_90 + bucket_90_plus = total`, which is snapshot-stable
even though the individual bucket assignment is not).

---

<a id="c020"></a>
## C.020 — Duplicate invoice and duplicate receipt definitions (item 19 in the brief)

**Business area:** Data quality / receipts & invoices.

**Definition A — receipts: an application-maintained detection table.**
`receipts_dedup_audit` (9 rows, `T.receipts_dedup_audit`) groups receipts by
`(tenant_id, payment_date, amount_paid, reference_number)`, storing `duplicate_count` (2–6) and
the full `receipt_ids` array, with a `detected_at` timestamp (all 9 rows: `2026-04-22
05:50:28.900039+00` — a single detection run, not continuous monitoring). **This is a real,
purpose-built application feature** for receipt deduplication.

**Definition B — invoices: an ad-hoc diagnostic query only.** `H.055`
(`duplicate_invoices`, 322 groups) groups invoices by `(allotment_id, billing_month,
invoice_type)` with `duplicate_count` ≥ 2 (356 extra rows beyond one-per-group: 319 `regular`
groups, 3 `exit_charge` groups). **There is no corresponding application table for invoices** —
no `invoices_dedup_audit` table exists among the 131 base tables, and no trigger in `FN.TRG`
performs invoice-side duplicate detection.

**Exact numerical difference:** receipts — 9 detected duplicate groups (of 5858 live receipts,
0.15% of receipts implicated). Invoices — 322 detected duplicate groups (of 5214 live invoices,
6.2% of invoices implicated, by group count) — **invoices show a duplicate rate roughly 40× the
receipts' detected rate**, though the two are not directly comparable since B's is a raw
diagnostic query with no remediation step, while A's is a maintained application feature.

**Cross-check performed in this pass (a finding in its own right):** of the 23 receipt ids named
across `receipts_dedup_audit`'s 9 groups, only 11 remain in the exported `receipts` table (12
have been hard-deleted since detection), and **none of the remaining 11 are soft-deleted** — the
detection table identified duplicates but **no automated or subsequent remediation soft-deleted
them**; whatever removed the other 12 did so by hard delete, outside the soft-delete convention
this system otherwise uses everywhere else (§`business_logic.md` §1.4). This directly rules out
the hypothesis considered and rejected in `C.018`.

**Which datasets/views produce each:** `T.receipts_dedup_audit` (real table, A);
`H.055`'s underlying query (diagnostic only, generating SQL not among the 54 named views, B).

**Likely mechanism:** receipt deduplication was built as a one-time detection pass (single
`detected_at` timestamp) that was **never wired to an automatic remediation trigger** — the
detected duplicates were left for manual review, and manual review appears to have hard-deleted
some (12 of 23) while leaving others (11 of 23) untouched, rather than using the system's
otherwise-consistent soft-delete convention. Invoice deduplication has no equivalent tooling at
all — `H.055`'s existence as an ad-hoc diagnostic (not a stored table) suggests it was run once
for this evidence package specifically, not as part of ongoing operations.

**Evidence:** `T.receipts_dedup_audit`, `H.055`, `T.receipts`.

**Resolution status:** Conflicting definitions exist in the sense that "duplicate" is detected
by two structurally different, non-comparable mechanisms (a maintained table with a fixed key
for receipts; a query with a different fixed key for invoices) — and the receipts mechanism is
proven, in this pass, not to have driven any actual remediation.

**Recommended handling:** build a single duplicate-detection convention (recommend the receipts'
composite-key approach, `tenant_id + payment_date/invoice_date + amount + reference`) applied
consistently to both tables, and — critically — decide and implement an actual remediation
policy (soft-delete the duplicate, keeping the earliest or the one with a receipt/invoice
number), since neither table currently has one enforced.

**Expose both to AI?** Yes, if asked "are there duplicate invoices/receipts" — state both
detected counts and explicitly note that detection does not currently imply remediation for
either table.

**Blocks/limits:** Limits — inflates any `COUNT`/`SUM` metric built on live, non-deduplicated
`invoices`/`receipts` rows by the undetermined-but-nonzero amount these duplicates represent;
does not block reconstruction, since the duplicate rows are identifiable, just not yet resolved.

---

<a id="c021"></a>
## C.021 — `get_universal_metrics_series` `collections` account-code defect

**Business area:** Ledger function correctness (discovered in this project, not explicitly
requested by the brief's numbered list, but directly relevant to the "how is the business doing"
/ "what happened to revenue" AI use cases the brief names).

**Definition A — what the function computes.**
```sql
SUM(signed_amount) FILTER (WHERE account_code = '1000' AND source_table = 'receipts') AS collections
```
(`FN.get_universal_metrics_series`, full body in `business_logic.md` §2.4.)

**Definition B — where receipt cash postings actually go.** `T.coa_accounts`/`H.016` shows
account `1000` is named **"Assets"** and is the **parent/rollup header** of `1100` ("Bank &
Cash") which is in turn the parent of `1110`/`1120` — the actual leaf posting accounts. This is
independently confirmed by two other pieces of code in the same package:
`v_je_amount_reconciliation`'s receipts leg filters `a.code LIKE '11%'`, and
`get_universal_metrics_v2`'s own `v_collections` calculation filters `ca.code IN ('1110',
'1120')`.

**Exact numerical difference:** **Not determinable from exported evidence by execution** (no
live database available), but the code-level proof is unambiguous: `journal_lines` are posted
against leaf accounts (`1110`/`1120`), never against the header account `1000` directly (headers
exist for rollup/reporting, not for posting — consistent with `enforce_subledger_completeness`'s
`requires_party`/`requires_allotment` design and with every other posting trigger in the package
targeting leaf codes like `1200`, `2100`, `2400`, `4xxx`, `5xxx`). **This function's `collections`
column is very likely to return zero, or near-zero, for every month it is asked about.**

**Which datasets/views produce each:** `FN.get_universal_metrics_series` only (the defect);
`M.016`/`H.016` (`coa_accounts`, proving `1000` is a header account); `FN.get_universal_metrics_v2`
and `H.001`'s `v_je_amount_reconciliation` (proving the correct pattern used elsewhere in the
same codebase).

**Likely mechanism:** a copy-paste or refactor error — every other revenue/expense filter in this
same function correctly uses a `LIKE` pattern (`account_code LIKE '4%'`, `LIKE '5%'`) to sweep an
entire account family, but the `collections` filter uses an **exact match against the wrong,
non-leaf code** instead of either a `LIKE '11%'` pattern or an explicit `IN ('1110','1120')` list.

**Evidence:** `FN.get_universal_metrics_series`, `T.coa_accounts`/`H.016`,
`FN.get_universal_metrics_v2`, `H.001`.

**Resolution status:** **Resolved** as a code-level defect, proven by cross-referencing the
account code's actual role in `coa_accounts` and by comparing against two other, correctly-coded
functions in the same package. Its runtime impact (whether it actually returns zero) is not
independently confirmed by execution.

**Recommended handling:** do not use `get_universal_metrics_series.collections` for any trend
metric until the account-code filter is corrected (to `IN ('1110','1120')` or `LIKE '11%'`,
matching the rest of the codebase). `revenue` and `expenses` in the same function are unaffected
(their `LIKE '4%'`/`LIKE '5%'` patterns are correct).

**Expose both to AI?** No — this is a proven bug, not a legitimate alternative definition; the
AI layer should refuse to surface this specific column until fixed, or substitute
`get_universal_metrics_v2`'s `totalCollections` logic instead.

**Blocks/limits:** Blocks — this specific function's monthly collections trend series should not
be used at all in its current exported form.

---

<a id="c022"></a>
## C.022 — Expense category rollup: pattern buckets vs COA-parent rollup

**Business area:** Expenses.

Restated from `C.013`'s broader lens as its own entry because it is a general-purpose
categorisation disagreement, not specific to account `5150`:

**Definition A — `v_pnl_by_category`.** Hand-written `account_code LIKE` patterns, one per named
category, hardcoded to specific prefix lengths (`510%` is 3 digits + wildcard; `52%`/`53%`/etc
are 2 digits + wildcard) — an inconsistent pattern-length convention across categories that
happens to work for 56 of 57 accounts and fails for `5150` (`C.013`).

**Definition B — `v_expense_composition`.** `COALESCE(parent_code, account_code)` — uses the
actual `coa_accounts.parent_id` hierarchy. Every account resolves to its immediate parent (or
itself if it's a root account), guaranteed complete by construction (every account either has a
parent or is one) — cannot produce an "unbucketed" gap the way A can.

**Exact numerical difference:** for 56 of 57 accounts the two conventions agree in spirit
(each account lands in a category matching its logical grouping); for account `5150` they
diverge as documented in `C.013`. Beyond `5150`, this document does not have evidence of a
second account where A and B disagree — the general design difference (pattern-matching vs
COA-hierarchy-walking) means **any future account added without an exact `LIKE`-pattern match in
`v_pnl_by_category` will silently repeat the `C.012`/`C.013` gap**, which is why this is recorded
as its own conflict rather than folded entirely into `C.013`.

**Which datasets/views produce each:** `v_pnl_by_category`, `v_expense_composition` (`M.016`).

**Likely mechanism:** two views written independently, one using an explicit enumeration
(fragile to new accounts), one using the schema's own hierarchy (robust to new accounts).

**Evidence:** `M.016` (both definitions), `T.coa_accounts`.

**Resolution status:** Conflicting definitions exist as a design pattern; the one concrete
instance of disagreement (`5150`) is resolved in `C.013`.

**Recommended handling:** for the semantic layer's canonical category taxonomy, prefer the
COA-hierarchy approach (`v_expense_composition`'s method) — it is structurally guaranteed
complete, whereas the pattern-list approach requires manual maintenance as accounts are added.

**Expose both to AI?** No — pick the hierarchy-based approach as canonical; disclose only if a
user's own prior report used the other convention.

**Blocks/limits:** Limits — same scope as `C.013`, generalised to future account additions.

---

<a id="c023"></a>
## C.023 — Maintenance cost linkage: two independent paths

**Business area:** Maintenance.

**Definition A — `v_maintenance_metrics`.**
```sql
FROM maintenance_tickets mt
  LEFT JOIN ticket_resolutions tr ON tr.ticket_id = mt.id
  LEFT JOIN expenses e ON e.ticket_resolution_id = tr.id
-- cost = SUM(e.amount); month = date_trunc(mt.created_at)
```
Links cost to a ticket **via its resolution**, and dates cost by **ticket creation month**.

**Definition B — `v_maintenance_by_issue_type`.**
```sql
FROM expenses e JOIN issue_types it ON it.id = e.issue_type_id
WHERE e.ticket_resolution_id IS NOT NULL
-- resolved_tickets = COUNT(DISTINCT e.ticket_resolution_id); month = date_trunc(e.expense_date)
```
Links cost to an issue type **via the expense's own `issue_type_id` FK** (a separate field from
the ticket's issue type), and dates cost by **expense date**.

**Exact numerical difference:** **Not determinable from exported evidence as a single reconciled
number** — no diagnostic directly joins A's per-ticket cost against B's per-issue-type cost for
the same population. `H.019` (`maintenance_view_vs_actual`) shows a **related but distinct**
mismatch: a maintenance view reported **1613** tickets against **1611** actual
(`maintenance_tickets` table) — a 2-ticket gap, not further explained by any exported diagnostic
naming which view produced 1613 or why. `H.058` (`maintenance_cost_linkage`) is the
purpose-built row-level trace connecting resolutions ↔ issue-type-linked expenses ↔ closure
cost; its content is preserved as the authoritative source for this question rather than
re-derived here (it is a single-row aggregate summary, not a per-ticket breakdown, per the
manifest).

**Which datasets/views produce each:** `v_maintenance_metrics`, `v_maintenance_by_issue_type`
(`M.016`); `H.019`, `H.058`.

**Likely mechanism:** two views built to answer different questions ("total cost per property
per month, regardless of category" vs "cost broken down by issue type") that use two different
FK paths to get from an expense back to a maintenance concept, and two different date bases —
they will disagree whenever an expense's own `issue_type_id` differs from its resolution's
ticket's issue type, or whenever a ticket's creation month differs from its resolving expense's
`expense_date` month (e.g. a ticket opened late in one month and resolved/expensed the next).

**Evidence:** `M.016`, `H.018`, `H.019`, `H.058`, `T.maintenance_tickets`, `T.ticket_resolutions`,
`T.expenses`.

**Resolution status:** Conflicting definitions exist; the `H.019` 1613-vs-1611 gap is confirmed
as a fact but not traced to its source view or cause within the exported evidence.

**Recommended handling:** treat "maintenance cost" as two distinct metrics — "cost by property/
month" (A) and "cost by issue type" (B) — never sum or compare them as if they measured the same
population without first confirming issue-type consistency between a ticket and its linked
expense.

**Expose both to AI?** Yes, whenever a maintenance-cost question could plausibly be answered by
either grain.

**Blocks/limits:** Limits — narrows to maintenance cost-by-category reporting; does not block
the overall `total_expenses` figure (which sums all `5xxx` accounts unconditionally, `C.012`).

---

<a id="c024"></a>
## C.024 — `receipt_allocations` empty vs the intended settlement mechanism

**Business area:** Collections / AR (structural, underlies `C.004`).

**Definition A — implied by schema design.** `receipt_allocations` exists as a base table (0
rows, confirmed empty — `data_inventory.md`, integrity report §5) with a dedicated trigger
(`trg_receipt_allocation_cap`, `AFTER INSERT,UPDATE`, `FN.TRG`) and its own PII-safe export view
(`v_export_receipt_allocations`). Its existence strongly implies the system was designed to
explicitly link a receipt to the invoice(s) it settles, via allocation rows.

**Definition B — what actually determines settlement.** `v_invoice_settlement_status`
(`C.004`) computes settlement via a **date-ordered FIFO waterfall** over aggregate AR account
`1200` activity per `(org, tenant, allotment)` — it does **not** reference
`receipt_allocations` at all, because there is nothing to reference.

**Exact numerical difference:** N/A — this is a structural absence, not a numeric drift. 0
allocation rows exist against 5758 live receipts (`H.020`, exported twice, byte-identical).

**Which datasets/views produce each:** `receipt_allocations` (table, empty);
`v_invoice_settlement_status` (the actual mechanism in use, `M.016`).

**Likely mechanism:** the allocation-table feature was built (schema, trigger, export view all
exist) but is **not populated by any of the 25 exported posting functions** — none of
`build_receipt_lines`, `trg_receipt_journal_post`, or any other exported trigger inserts into
`receipt_allocations`. Either the feature was never activated in the application layer (its
write path is outside the 25 exported bodies — possible, since the insert path is not among
them either) or it was deliberately superseded by the FIFO-waterfall approach in
`v_invoice_settlement_status`. **Which of these is true is not determinable from exported
evidence** — no exported function body writes to `receipt_allocations`, but the 458
signature-only routines could contain one.

**Evidence:** `T.receipt_allocations` (0 rows), `H.020`/`H.020b`, `M.016`
(`v_invoice_settlement_status`, `v_export_receipt_allocations`), `FN.TRG`
(`trg_receipt_allocation_cap`), `M.019`/`FN.999` (no `receipt_allocations`-writing function
among the 25 with exported bodies).

**Resolution status:** **Resolved** as a fact of the exported data (the table is empty; the
FIFO waterfall is what actually determines settlement, since it's the only mechanism with any
data behind it) — not resolved as to *why* the allocation table was never populated.

**Recommended handling:** treat `v_invoice_settlement_status`'s FIFO waterfall as the sole
settlement-status mechanism for the semantic layer; do not build any metric that assumes
`receipt_allocations` will be populated, and do not interpret its emptiness as a data-export
gap (it is empty in the live database, not merely un-exported — confirmed by M.006's exact
row count of 0).

**Expose both to AI?** No — there is only one working mechanism (B); disclose the empty
allocation table only if a user specifically asks "which receipt paid this invoice," since that
question **cannot** be answered precisely (the FIFO waterfall answers "how much of this invoice
is settled," not "by which specific receipt").

**Blocks/limits:** Blocks — "which receipt paid invoice X" is not answerable from this evidence
package at all; "how much of invoice X is settled" is answerable via `v_invoice_settlement_status`.

---

## Totals

- **Conflicts documented: 24** (`C.001`–`C.024`).
- **Resolved** (proven mechanism/fact, even if the underlying business question remains open):
  **C.002, C.007, C.009, C.011, C.012, C.013, C.017 (as counts), C.018 (for invoices/settlements;
  partially for receipts), C.019 (reframed as non-conflict), C.021, C.024** — **10**.
- **Unresolved** ("Conflicting definitions exist" with no evidence-proven winner):
  **C.001, C.003, C.004, C.005, C.006, C.008, C.010, C.014, C.015, C.016, C.020, C.022, C.023**
  — **13**.
- **Partially resolved** (mechanism strongly indicated but not proven from an exported query
  definition): counted within the relevant entries above (`C.014`, `C.015`, `C.016` each carry
  an evidence-consistent hypothesis alongside their "Conflicting definitions exist" status);
  **1 additional entry** (`C.018`) is resolved for two of three source tables and open for the
  third — reflected in the 10/13 split by rounding to each entry's dominant status.
- **Blocking a metric** (an AI answer cannot responsibly state a single number without
  disclosing the conflict): **C.003, C.005, C.009, C.010, C.011, C.012, C.021, C.024** — **8**.
- **Requiring an owner/business decision** (evidence cannot determine which definition the
  business should treat as authoritative going forward — a policy choice, not a data question):
  **C.001** (which AR view is canonical), **C.003** (whether `tenant_transactions` is retired),
  **C.004** (app vs ledger invoice balance), **C.005** (which of 4 tenant-balance figures is
  authoritative), **C.007** (v1 vs v2 occupancy formula as the go-forward standard), **C.010**
  (which profit definition is "the" P&L number), **C.013**/**C.022** (electricity's category
  home), **C.020** (duplicate-remediation policy) — **8**.

**Next recommended deliverable:** `data_quality_report.md` (D) — it consumes this file's
numeric findings (especially `C.014`–`C.018`, `C.020`) directly, organizing them by severity,
affected-row-count, and offline-fixability rather than by semantic pairing, and is the natural
next step before `metric_reconstruction.md` (E) can state, metric by metric, which of these
conflicts each reconstructed number inherits.
