# Analytics Execution Specification

Specifies how a resolved, trust-cleared query is turned into a computed result. **Specification
only — no code.** Corresponds to pipeline stages **[7] Analytics Plan → [8] Execution → [9]
Validation** in `ai_analytics_architecture.md` §3. Every calculation described here must apply
**exactly** the filters/aggregation/reversal/soft-delete/duplicate policy already documented for
the metric in `semantic_metric_registry.csv` — this document specifies the execution
*mechanics* (how filtering, grouping, comparison, trend, anomaly, and driver operations are
structured), not new calculation rules.

**Precondition:** a query only reaches this specification after the Trust & Conflict Gate has
returned a verdict. For `BLOCK` metrics, the Analytics Plan is constrained to the
"explain-the-conflict" plan (§2.6) — the metric's raw value may still be computed **internally**
(so the AI can, e.g., state the size of the disagreement between competing definitions), but
**never** assembled into a "the answer is X" plan.

---

## 1. Execution engine inputs and outputs

- **Input:** a resolved query = `{metric_id(s), dimension filters, date range, snapshot|
  historical mode, trust verdict}` (the output of `question_understanding_spec.md`).
- **Output:** a `Result` object = `{value(s), grain, date basis actually used, filters actually
  applied, reversal/soft-delete policy actually applied, validation status, evidence
  references}` — every field populated, none inferred silently.
- **Data source:** the same immutable evidence layer used throughout this project
  (`file_manifest.csv`-resolved CSVs) — this specification assumes the same evidence-loading
  discipline already implemented in `scripts/validation/common.py` (manifest-driven, no
  filename guessing), extended to serve live queries rather than one-off validation runs.

---

## 2. Analytics Plan types

The Analytics Plan stage selects one (or a documented composition) of the following plan types,
based on the Intent classification from `question_understanding_spec.md` §2.

### 2.1 Single-value lookup
Apply the metric's documented filter + aggregation once, at the resolved grain/date. Used for
**Lookup** and **Filtered lookup** intents. This is the only plan type a `SAFE` metric needs for
a simple question.

### 2.2 Grouped lookup
Same as 2.1, `GROUP BY` an additional resolved dimension (e.g. by month, by category). Must
confirm the grouping dimension is actually part of the metric's documented grain (§4 of
`ai_analytics_architecture.md`'s grain-protection rule) — a metric whose grain does not include
`property_id` cannot be grouped by property without an explicitly-documented join.

### 2.3 Period comparison
Two Single-value or Grouped lookups, each independently time-resolved (per
`question_understanding_spec.md` §5.1 step 5), placed side by side. **Both periods must use the
identical metric definition, filters, and reversal/soft-delete policy** — a comparison across
two periods using different underlying conventions (e.g. comparing a `SAFE` all-time ledger
figure against a `DISCLOSE` application-level figure for a different period) is not a valid
period comparison and must be rejected or explicitly reframed as a definitional disclosure
instead.

### 2.4 Trend series
A Grouped lookup by time (month, typically), across the metric's full documented coverage or a
requested sub-range. Subject to the coverage-boundary and YoY guards in
`question_understanding_spec.md` §5.1/§5.3. For metrics validated at monthly grain in this
project (`M.REV.002`, `M.EXP.001` via `M.PNL.001`, `M.COL.002`), the trend plan reuses the exact
grouping logic already proven in `scripts/validation/validate_revenue.py`/`validate_expenses.py`
— `(property_id, month)`, never month alone, per the proven grain requirement in
`metric_reconstruction.md`'s `REV.02` finding.

### 2.5 Anomaly scan
A Trend series, with each period's value compared against the series' own historical
distribution (mean, recent trend line, or a documented threshold — the specific statistical
method is an implementation-phase decision, not fixed by this specification; see
`ai_evaluation_framework.md` for how such a method would be validated once chosen). **Before
flagging a period as anomalous, the scan must check `data_quality_report.md` for a known
mechanism that would explain the deviation as a data artifact rather than a business event** —
this is the exact check that would have caught the owner-rent single-batch-posting event
(`DQ.020`) as a known artifact rather than a real business anomaly, had this system existed at
the time.

### 2.6 Driver decomposition
Given an observed change in a metric between two periods (output of 2.3), decompose the change
into its constituent sub-components using `metric_dependency_graph.md`'s documented dependency
edges — e.g. a P&L change decomposes into the revenue-account and expense-category sub-totals
that moved (per `M.EXP.002`'s category breakdown), never into an undocumented ad-hoc
decomposition. Where the top-level metric is itself in conflict (e.g. `M.PROFIT.001`, `BLOCK`),
driver decomposition may still run **per-definition** (decompose Def A's change, separately
decompose Def C's change) but must never merge the two decompositions into one narrative.

### 2.7 Explain-the-conflict plan (for BLOCK / SHOW_BOTH metrics)
Instead of a single value, compute **each** competing definition's value independently (each
using its own documented filters/aggregation), and compute the pairwise numeric difference(s)
between them, citing the relevant `conflict_ids` and their documented "likely mechanism" from
`conflicts.md`. This is the plan type that produces the content behind `ai_trust_policy.md` §2's
BLOCK/SHOW_BOTH answer templates.

### 2.8 Risk / composite scan
For risk-scan intents that draw on multiple metrics (`question_understanding_spec.md` §6.1's
"who are our risky tenants" / "where are we losing money" examples): run each contributing
metric's own plan independently, tag each result with its own metric_id/trust level, and present
them as a **labelled list**, never a merged score (no composite risk-scoring metric exists in
the registry — inventing one at execution time would violate the "no unsupported metric"
hallucination-prevention rule in `ai_analytics_architecture.md` §8).

---

## 3. Filtering

Filters applied at Execution must be **exactly** the metric's documented `filters` column value
from `semantic_metric_registry.csv`, plus any additional dimension filter resolved in
`question_understanding_spec.md` §4 that is confirmed compatible with the metric's grain. No
filter may be silently dropped (e.g. omitting `is_deleted=false` because the question didn't
mention deletion status) or silently added (e.g. adding a status filter the metric definition
doesn't call for).

**Soft-delete and reversal filters are never optional parameters** — they are fixed properties
of the metric's identity (`soft_delete_policy`, `reversal_policy` columns), not something a
user's question can override. A question phrased as "including deleted receipts" against a
metric whose documented policy is "live rows only" should be answered by disclosing that the
metric's canonical definition excludes deleted rows, and — only if the evidence supports a
well-defined alternative — offering the all-rows figure as an explicitly different, non-canonical
number, never silently swapping the policy of the canonical metric itself.

---

## 4. Grouping

Grouping dimensions are drawn from `business_dimensions.md` and must be validated against the
metric's `grain` and `dimensions` columns before use (§2.2 above). Where a metric's proven-correct
grouping requires a compound key (property + month, not month alone — the `REV.02` finding), the
execution engine must use the compound key by default, never the simpler single-column grouping,
even if the question only mentions one of the two dimensions explicitly.

---

## 5. Period comparison mechanics

1. Resolve both periods independently (never assume symmetry — a "this month vs. last month"
   comparison near a coverage boundary may have one period fully covered and the other partial;
   this must be disclosed, not silently computed on unequal bases).
2. Apply the identical Analytics Plan to both.
3. Compute the delta (absolute and percentage) using the same convention
   `metric_reconstruction.md`/`validation_summary.csv` already established for
   reconstructed-vs-reference comparisons — `abs_diff = |A - B|`, `pct_diff = abs_diff / |B| *
   100` (guarding division by zero as `0.0` if both are zero, `inf`/undefined disclosed
   explicitly otherwise).
4. If either period's value is `NOT_DETERMINABLE` or the metric is `BLOCK`, the comparison
   itself inherits that status — never compute a delta between one real number and a suppressed
   one.

---

## 6. Trend analysis mechanics

- Trend series must be built at the metric's proven-correct grouping grain (§4).
- Missing periods within documented coverage (a month with zero activity, e.g. the 2 EXPENSE-only
  months found during revenue validation) are **real zeros**, not gaps to be interpolated —
  distinguish explicitly from periods **outside** documented coverage, which are not zero, they
  are unknown (`NOT_DETERMINABLE`).
- A trend must state its full date range and the metric's underlying definition (especially for
  `SHOW_BOTH` families like occupancy — a trend line is only meaningful within one named
  definition, never blending Def A's snapshot logic with Def E's historical logic across the
  same chart).

---

## 7. Anomaly & driver mechanics (specification-level detail)

- **Anomaly detection method** is deliberately left as an implementation-phase parameter (mean/
  std-dev, moving average, or a documented business threshold) — this specification's
  requirement is only that: (a) the method be applied consistently for a given metric across
  calls, (b) every flagged anomaly be checked against `data_quality_report.md` before being
  reported as a business signal (§2.5), and (c) the anomaly be reported as an OBSERVATION, not
  yet an explained fact (`business_reasoning_spec.md` owns the epistemic labelling).
- **Driver decomposition** must use only dependency edges already documented in
  `metric_dependency_graph.md` — if a plausible driver relationship is not documented there
  (e.g. "occupancy drives revenue" is intuitively true but not a modeled dependency edge in this
  project's evidence — no metric ties bed-occupancy directly to the revenue reconstruction), the
  decomposition must not invent that edge; it should report the observed correlation, if any, as
  a HYPOTHESIS at most, never as a proven driver.

---

## 8. Validation

Every Execution result must be checked against `validation_summary.csv` where a matching
`validation_reference` exists for the metric:
- If the metric's historical validation status was `MATCH`, and the live query uses the same
  filters/grain/date-range convention, the result carries `HIGH` confidence.
- If historical validation was `DIFFERS` (4 such cases exist: `REV.02`, `AR.04c`, `DQ.003`,
  `DQ.026`), the live result must carry the same documented explanation, not present as if
  freshly validated.
- If no `validation_reference` exists (`NOT_DETERMINABLE` metrics, and several `DISCLOSE`
  metrics honestly flagged as "not independently re-validated" in `metric_reconstruction.md` —
  e.g. `M.CASH.001`), the result is computed but explicitly labelled as **unverified against any
  reference**, never presented with the same confidence language as a `MATCH`-backed result.
- **A result that fails an internal sanity check must never be silently emitted.** Sanity checks
  include: non-negative counts, debit=credit balance identities for ledger sub-totals
  (`enforce_journal_balanced`'s guarantee, `business_dimensions.md` §21 — a violation here would
  indicate an execution-engine bug, not a business fact, and must halt rather than answer), and
  grain-consistency (a grouped result's row count should not exceed the ungrouped population).

---

## 9. What this document does not specify

The concrete query language, indexing strategy, or performance characteristics of the execution
engine are implementation-phase decisions. This document fixes the **rules** execution must
follow (which filters, which grain, which validation), not the technology that will apply them.
