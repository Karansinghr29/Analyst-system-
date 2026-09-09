# Statistical Analysis — Feasibility Investigation

Investigation only. No implementation; no metric, calculator, Trust Gate, forecasting or evidence
file touched.

**The finding that governs everything below:** the monthly series are almost perfectly
autocorrelated. Revenue levels carry lag-1 ρ = 0.990, collections ρ = 0.975. Once that is
accounted for, 41 monthly observations of revenue carry an **effective sample size of 0.2** — not
41. Every statistic computed on *levels* is therefore descriptive only, and no test assuming
independent observations is admissible on them.

The same series expressed as **month-over-month changes** behaves quite differently (ρ = 0.114 for
revenue, −0.203 for collections), and there inference becomes defensible. That distinction —
levels describe, changes infer — decides each recommendation.

---

## 1. Descriptive statistics

| | |
|---|---|
| **Source** | `M.REV.002`, `M.COL.002`, `M.PNL.001` (monthly); `tenant_allotments` (cross-section) |
| **Observations** | revenue 41, collections 45, expenses 52 monthly; rent **1,186** rows |
| **Granularity** | monthly / per-allotment |
| **Missingness** | revenue 30 gaps pre-2023; collections **0 gaps**; rent 2% missing |
| **Method** | mean, median, min/max, sd, percentiles, CV |
| **Assumptions** | none beyond the sample being what it claims |
| **Defensible?** | **Yes for cross-sections. Qualified for series.** |
| **Useful to owner?** | Yes — "typical rent is ₹14,500, most between ₹13,500 and ₹15,500" is directly actionable |
| **Verdict** | **IMPLEMENTED** (cross-section) / **LIMITED** (series) |

Series descriptives need a caveat the owner must see: revenue mean ₹1,685,924 against a latest
month of ₹3,336,114. The mean describes a business that has more than doubled during the window —
it is a fact about the history, not a "typical month". CV 0.62 is measuring growth, not volatility.

Cross-sections are where the sample sizes actually are, and `monthly_rental` is well-behaved:
n=1,186, median ₹14,500, CV 0.23, skew −0.22.

## 2. Distribution analysis

| | |
|---|---|
| **Source** | `tenant_allotments` columns; monthly change distributions |
| **Observations** | rent 1,186; deposit 1,213; balance_due 1,213; changes 40–51 |
| **Missingness** | `expected_stay_days` **99% missing (n=15)** — unusable |
| **Method** | skewness, percentiles, zero-share; outliers as observations only |
| **Assumptions** | that a shape statistic is meaningful at the given n |
| **Defensible?** | **Yes at n>1,000. No for monthly changes at n≈40** |
| **Useful?** | Yes, with the zero-share stated |
| **Verdict** | **LIMITED** |

The zero-inflation must be disclosed or the numbers mislead badly:

- `deposit_paid`: **921 of 1,213 are zero**. Mean ₹5,518, median **₹0**, skew +1.46.
- `balance_due`: **1,116 of 1,213 are zero**. Mean ₹832, median **₹0**, skew +5.95.

Reporting a mean deposit of ₹5,518 without saying three-quarters are zero would be actively
misleading. These need median-and-share-of-zero, never a bare mean.

## 3. Relationship analysis

| Pair | Paired months | Pearson (levels) | Spearman | **Pearson (changes)** |
|---|---|---|---|---|
| revenue ↔ collections | 41 | 0.983 (r²=0.967) | 0.973 | **0.240** |
| revenue ↔ expenses | 41 | 0.787 | 0.870 | **0.217** |
| collections ↔ expenses | 45 | 0.805 | 0.889 | **0.206** |
| revenue ↔ occupied beds | 41 | 0.839 | 0.838 | **0.271** |

| | |
|---|---|
| **Method** | Pearson, Spearman, and change-on-change |
| **Assumptions** | Pearson: linearity + **independence**. Independence fails on levels (ρ≈0.99) |
| **Defensible?** | **Levels: no. Changes: yes** (effective n ≈ 32 for revenue, ≈ 44 for collections) |
| **Useful?** | Yes — provided the level figure is not shown alone |
| **Verdict** | **LIMITED** — change-on-change only |

Revenue ↔ collections at r² = 0.967 on levels reads as a near-perfect relationship. It is almost
entirely "both grew". On changes it falls to 0.240. **Publishing the level correlation without the
change correlation would be the single most misleading number this system could produce**, because
it looks like the strongest finding in the dataset.

## 4. Trend analysis

| | |
|---|---|
| **Source** | the three monthly series |
| **Observations** | 41 / 45 / 52 |
| **Method** | slope, rate of change, rolling median/MAD, volatility of changes |
| **Assumptions** | that the window is one regime |
| **Defensible?** | **Yes** — descriptive, no inference required |
| **Useful?** | Yes — "typical month-over-month change is +5.3%" is meaningful |
| **Verdict** | **IMPLEMENTED** |

Revenue median MoM change +5.3%, collections +5.4%, expenses +0.0%. Note the sd of MoM % change is
inflated by the pre-operating months (313pp for revenue, driven by a +2009% month); computed on the
operating era only it is usable. Rolling statistics are the safest family here — they need no
distributional assumption and no threshold.

## 5. Group / property / tenant comparisons

| Grouping | Distinct | Verdict |
|---|---|---|
| **property_id** | **1** | **BLOCKED_BY_EVIDENCE** — no comparison universe |
| **apartment_id** | **38** (33 with ≥10 allotments) | **LIMITED** — real universe, with a caveat |
| **tenant_id** | **989** | **LIMITED** — large, but per-tenant n is small |

The apartment universe is genuine — median 34 allotments per apartment — but carries a trap worth
naming. Ranking apartments by median rent puts **D15, A34 and A33 at the extremes, and each has
n = 1**. A "top 5 apartments by rent" built naively would be a ranking of single observations. Any
grouped comparison needs a minimum group size, and apartments below it must be shown as
"insufficient data" rather than omitted (omitting them makes the ranking look complete).

Property remains what it has always been: one property, nothing to rank.

## 6. Statistical significance

**Verdict: BLOCKED_BY_EVIDENCE on levels; LIMITED on changes.**

This is the section where a plausible-looking number would do the most damage. The measurement:

| Series | n | lag-1 ρ | **effective n** |
|---|---|---|---|
| revenue, levels | 41 | 0.990 | **0.2** |
| collections, levels | 45 | 0.975 | **0.6** |
| revenue, changes | 40 | 0.114 | ~32 |
| collections, changes | 44 | −0.203 | ~44 (capped at n) |

A p-value or confidence interval on a level series with effective n below 1 is not a weak
result — it is not a result. Any test the system ran there would produce a number, and the number
would mean nothing.

On changes, inference is admissible. Even then I would report **an interval, never a verdict**: no
significance threshold exists in the evidence or in any specification, and the product has already
established that it does not invent one. The same discipline the forecaster uses — empirical
intervals from actual error, no assumed distribution — transfers directly.

## 7. Revenue drivers

Confirms and extends the forecasting investigation.

| | |
|---|---|
| **Paired observations** | 41 months |
| **Pearson (levels)** | 0.839 |
| **Pearson (changes)** | **0.271** |
| **Occupancy *rate*** | **not derivable** — beds carry no dates, so historical availability cannot be rebuilt |
| **Verdict** | **LIMITED** — reportable as an association, never as a driver |

Occupied beds and revenue rise together; on changes the association is weak. **No causal claim is
supportable**, and the forecasting backtest already showed occupancy makes revenue prediction ~7×
worse. Any statistical surface must describe this as association and say the predictive test failed.

## 8. Collections / revenue / expense relationships

All three pairs have adequate paired observations (41–45 months) and all three show the same
pattern: strong on levels (0.79–0.98), weak on changes (0.21–0.24). **LIMITED**, change-on-change
only, with both figures shown together so the level number cannot be read alone.

Expenses carry an additional problem: 9 non-positive months and a median MoM change of exactly
₹0, so relative statistics on expenses are unstable.

---

## Reuse of the forecasting backtest infrastructure

**Partly — the discipline, not the functions.**

| Asset | Reusable? |
|---|---|
| `_percentile` | **Yes**, directly — empirical intervals need it |
| `monthly_revenue_series` | **Yes** — the complete-months-only, operating-era rule is exactly right |
| Rolling-origin pattern in `_backtest` | **Yes as a pattern**, no as a function — it is horizon-shaped and forecast-specific |
| `_naive_mape` | No — MAPE is a forecast metric |
| `MIN_TRAIN_MONTHS`, `MIN_OBSERVATIONS` | **Yes as precedent** — the idea of a declared minimum before any output |

The genuinely valuable inheritance is the **rule that a statistic is published only with the
validation that earned it**, and that a horizon/sample below the declared minimum returns a
refusal rather than a number.

---

## Recommendation — the smallest defensible capability

**A descriptive statistics surface. No inference, no significance, no ranking of thin groups.**

Scope, in priority order:

1. **Cross-sectional descriptives** on `monthly_rental`, `deposit_paid`, `balance_due` — n, median,
   percentiles, min/max, **share of zeros**, missingness. This is where the sample sizes are and
   where an owner gets immediate value ("typical rent ₹14,500; three-quarters of allotments show no
   deposit recorded").
2. **Series descriptives on changes, not levels** — median MoM change, its dispersion, and the
   rolling baseline. Level mean/CV shown only with the explicit note that the window spans a
   period of growth.
3. **Paired relationships reported as a pair** — level correlation and change correlation always
   together, with the change figure given the emphasis, plus the paired-observation count.
4. **Refusals with reasons** — property comparison (1 property), significance testing on levels
   (effective n < 1), `expected_stay_days` (99% missing), occupancy rate (not derivable).

Deliberately **excluded** from the first slice: hypothesis tests, p-values, confidence intervals on
levels, apartment/tenant rankings, distribution-shape claims on monthly data.

Why this is the right size: it materially improves the Data Scientist experience — the product
currently declares `statistical_summary` NOT_IMPLEMENTED and offers nothing — while every number in
it is a description of data actually present, requiring no threshold, no assumed distribution, and
no inference the sample cannot bear. It also directly prevents the failure mode this evidence most
invites: publishing r² = 0.967 between revenue and collections as though it were a discovery.

---

*Investigation only — no implementation performed.*
