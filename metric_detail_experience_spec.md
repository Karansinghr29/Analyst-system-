# Metric Detail Experience Specification

What opens when the owner clicks any metric. Built by `ViewModelBuilder.metric_detail()`.

---

## 1. Panel contents

Every field comes from the engine. Nothing is composed in the UI.

| Section | Source |
|---|---|
| Metric name | registry `semantic_name` |
| Business definition | registry `definition`, verbatim |
| Value / values | the tile payload — one figure, or the labelled definitions |
| Trust level | gate verdict + owner-facing translation |
| Caveat | registry `caveat_text`, mandatory for DISCLOSE |
| Period | the as-of basis actually used |
| Dimensions | registry `dimensions` |
| Calculation | filters · aggregation · reversal policy · soft-delete policy · date field |
| Evidence | manifest keys → exported CSVs |
| Validation | status + the check that confirmed it |
| Related metrics | documented `dependency_metrics` only |
| Conflicts | `conflict_ids` |
| DQ issues | `dq_ids` |
| Insights | findings whose triggers include this metric |
| Recommended questions | the questions this metric can actually answer |

---

## 2. Worked example — Revenue

```
Revenue (total, ledger-derived)                            M.REV.001
₹72,705,593.43                                             [Verified]

DEFINITION   SUM(signed_amount) WHERE account_type = INCOME,
             reversal-excluded, journal_lines × journal_entries × coa_accounts
PERIOD       entry_date basis; ledger span 2019-11-03 to 2026-09-20
CALCULATION  filters · reversal policy · soft-delete policy, as documented
EVIDENCE     T.journal_lines · T.journal_entries · T.coa_accounts · F.001 (v_pnl)
VALIDATION   MATCH — REV.01 in validation_summary.csv
TRUST        Reliable — one agreed definition, checked against source records

  [Trend]  [Breakdown]  [Why did it change?]  [What should I investigate next?]
```

---

## 3. Worked example — Profit (the refusal)

```
Gross/net profit                                        M.PROFIT.001
No single reliable figure — definitions conflict          [Conflict]

Three evidence-backed definitions exist and they disagree.
Choosing between them is a business decision, not an analytical one.

  Def A (ledger, v_pnl)                          ₹51,920,761.47
  Def B (get_universal_metrics v1)               ₹71,689,383.40
  Def C (v2, owner-rent-inclusive)               ₹51,920,761.47

  Def B omits owner rent, overstating profit by ~36.6% against Def A.

CONFLICTS    C.010 · C.011          DQ ISSUES   DQ.016 · DQ.017
DECISION     Which definition is authoritative — requires an owner decision

  [View all definitions]  [How was this calculated?]  [Can I trust this?]
```

No chart. No default. No "primary" definition.

---

## 4. Affordances offered, and withheld

| Affordance | Offered when |
|---|---|
| Trend | a month-keyed series exists |
| Breakdown | the documented grain supports a non-degenerate dimension |
| Why did it change? | the metric has a historical form |
| View all definitions | trust is SHOW_BOTH or BLOCK |
| How was this calculated? | always |
| Can I trust this? | always |

A snapshot-only measure gets **no "Why?"** — "why did it change" presupposes a change that cannot
be established, and a button that always fails is worse than an absent one.

---

## 5. Related metrics

Only documented `dependency_metrics` edges. No metric is offered as "related" because it sounds
similar or shares a word — relatedness comes from the dependency graph, not from resemblance.
