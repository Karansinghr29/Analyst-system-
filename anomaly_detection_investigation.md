# Anomaly Detection — Feasibility Investigation

Investigation only. Nothing implemented; no engine, registry, calculator or evidence file changed.

The headline finding is a constraint, not a method: **only three metrics in the registry expose a
month-keyed series at all**, and on the one signal that looked most promising the number of
"anomalies" is decided entirely by the cutoff chosen rather than by anything in the data.

---

## 1. Candidate datasets / metrics

Scanned all 49 registry metrics for a series a baseline could be computed against.

| Family | Series exposed? | Source |
|---|---|---|
| Revenue | **Yes** — monthly | `M.REV.002` |
| Collections | **Yes** — monthly | `M.COL.002` |
| P&L (revenue / expenses / net_profit) | **Yes** — monthly, composite | `M.PNL.001` |
| Expenses (standalone) | No — only as a P&L component | — |
| Receivables / dues | No — snapshot only, and SHOW_BOTH | `M.AR.*` |
| Electricity | No | `T.electricity_readings` |
| Maintenance | No | `T.maintenance_tickets` |
| Occupancy | No — snapshot; historical occupancy is uncomputed | `M.OCC.*` |

**3 of 49 metrics have a time series.** Everything else is a point-in-time figure with nothing
to be unusual *relative to*.

## 2. Available history

| Series | Obs | Span | Gaps | Longest contiguous run | Non-positive |
|---|---|---|---|---|---|
| Revenue (`M.REV.002`) | 51 | 2019-11 … 2026-07 | **30** | 42 mo (2023-02 … 2026-07) | 7 |
| Collections (`M.COL.002`) | 45 | 2022-11 … 2026-07 | **0** | **45 mo** | 0 |
| P&L revenue | 52 | 2019-11 … 2026-07 | 29 | 48 mo | 10 |
| P&L expenses | 52 | 2019-11 … 2026-07 | 29 | 48 mo | 9 |
| P&L net_profit | 52 | 2019-11 … 2026-07 | 29 | 48 mo | 11 |
| Maintenance tickets | **15** | 2025-01 … 2026-03 | 0 | 15 mo | — |
| Electricity readings | **5** | 2026-03 … 2026-07 | — | 5 mo | — |
| EB monitoring | **1** | 2026-08 | — | 1 mo | — |
| Receivables | no series | — | — | — | — |

**Collections is the only clean series in the package** — 45 contiguous months, no gaps, no
non-positive values.

Every financial series carries a strong growth trend (revenue +158,763% end-to-end over its run),
so a **level**-based baseline is meaningless. Any usable signal must be computed on month-over-month
*changes*, not on levels.

**Outliers already present in source data.** The series contain known artefacts, not just business
movements: revenue 2023-08 records ₹20,400 between neighbours of ₹411,010 and ₹430,289. The P&L
components show consecutive z = −23.2 then +23.8 (2026-03/2026-04), the classic signature of a
month missing then restored — a reconstruction artefact, not an event. Of 32 existing data-quality
findings, several (DQ.015, DQ.016, DQ.030) already describe systematic accounting defects that
would surface as "anomalies". **A detector would substantially re-discover known DQ findings and
present them as new business events.**

## 3. Candidate anomaly methods

| Method | Verdict on this evidence |
|---|---|
| Rolling median / MAD on changes | **Most defensible.** Robust to the artefacts above; needs no distributional assumption |
| Rolling mean / SD | Rejected — the artefacts inflate SD and mask the very points they should flag |
| Robust z-score | Same computation as MAD; the score is defensible, the *cutoff* is not (see §6) |
| IQR | Viable but coarser than MAD at n≈40; no advantage here |
| Change-point detection | Rejected — needs a stable regime; these series are one long growth ramp |
| Forecast-residual | Tested directly (see below); signal exists but is cutoff-determined |
| Seasonal decomposition | Rejected — seasonal naive was the worst forecasting method tested (47% MAPE); no separable seasonality |

### Forecast residuals for revenue — tested, as requested

One-step-ahead, strictly out-of-sample, using the existing forecaster:

- 23 residuals, median ₹43,952, MAD ₹58,610
- At \|z\| > 3.5 exactly **one** month flags: 2025-10 (actual ₹2,897,959 vs predicted ₹3,189,671)

The problem is what happens when the cutoff moves:

| cutoff | 2.5 | 3.0 | 3.5 | 4.0 | 5.0 |
|---|---|---|---|---|---|
| flagged | 3 | 2 | **1** | 0 | 0 |

**There is no natural gap in the distribution.** The answer to "how many anomalies were there?"
is entirely a restatement of the cutoff. And the single month that does flag (2025-10) is a real
business movement — revenue easing after a peak — which the model simply under-forecast. Labelling
it an anomaly would tell the owner a genuine trading month was a data problem.

23 residuals is also far too few to estimate a tail.

## 4. Backtesting / validation approach

Anomaly detection cannot be validated the way forecasting was, and this is the crux: **there are
no labels.** No exported record marks any month as anomalous, so precision and recall cannot be
computed. What *can* be validated:

1. **Stability** — does the flagged set survive a modest change of cutoff? (Tested: it does not.)
2. **Artefact overlap** — how many flags coincide with known DQ findings rather than business events?
3. **Rolling-origin honesty** — the baseline for month *t* uses only months before *t*.
4. **Persistence** — does a month still flag as more history arrives, or is the flag an artefact of a short window?

Given no labels, (1) and (2) are the meaningful tests, and (1) already fails at the cutoff step.

## 5. Recommended method per family

| Family | Recommendation |
|---|---|
| **Collections** | Rolling median/MAD **on month-over-month changes** — best candidate: 45 contiguous months, no gaps, no non-positive values |
| **Revenue** | Same method, restricted to the operating era (2023-03 onward). Do **not** use forecast residuals: only 23 available and cutoff-determined |
| **Expenses** | Same method, but expect noise — the change MAD is ₹13,350 against a median of ₹0, so 11 of 47 months exceed z = 3.5. That is not 11 anomalies; it is a series where most months barely move and any movement scores high |
| **P&L / net_profit** | **Not recommended.** The composite is BLOCK-adjacent and carries reconstruction artefacts (z = ±23 in consecutive months) |
| **Receivables/dues** | Not possible — no series, and SHOW_BOTH means no single figure to baseline |
| **Electricity** | Not possible — 5 months |
| **Maintenance** | Not possible yet — 15 months, and natural volume swings of 33→107 |

## 6. Is a defensible threshold available?

**No — and this is the finding that shapes the whole recommendation.**

A threshold would have to come from one of: the exported evidence (it contains none), a
specification (`analytics_execution_spec.md 2.5` explicitly defers the statistical method to
implementation), or a statistical convention. The convention route is where this usually gets
smuggled in: "z > 3 is standard" is a convention about normally-distributed data, and these
series are trended, artefact-laden and n≈40.

The empirical test above settles it: moving the cutoff from 3.0 to 3.5 halves the answer.

**But a threshold is only needed to make the VERDICT, not the MEASUREMENT.** This is exactly the
split the system already applies to change detection, which reports direction and size and refuses
materiality. The same split works here:

- **Computable and defensible** — "this month's change was ₹X, which is N times the typical
  monthly change over the last 12 months (median ₹Y)". A fact, no cutoff.
- **Not defensible** — "this month is an anomaly". A verdict requiring a cutoff nobody has set.

## 7. Implementable now

1. **Deviation reporting for collections and revenue** — for a given month, the change, the rolling
   median change, the MAD, and the robust score, stated as measurements. Deterministic; no cutoff.
2. **A "largest movements" ranking** — order months by robust score and show the top N without
   calling any of them anomalous. Ranking needs no threshold.
3. **Artefact cross-reference** — where a large deviation coincides with an existing DQ finding,
   say so, so the owner sees "this is a known data issue" rather than a business event.

## 8. Blocked

| Capability | Blocked by |
|---|---|
| Anomaly *verdict* ("this is an anomaly") | **Business decision** — no defensible cutoff exists |
| Expense anomalies | **Evidence** — median change ₹0 makes the score unstable |
| P&L / profit anomalies | **Evidence** — reconstruction artefacts dominate |
| Receivables anomalies | **Evidence** — no series; SHOW_BOTH |
| Electricity anomalies | **Evidence** — 5 months |
| Maintenance anomalies | **Evidence** — 15 months, high natural variance |
| Forecast-residual anomalies | **Method** — 23 residuals, cutoff-determined, flags real trading months |
| Occupancy anomalies | **Evidence** — no historical series (as established in the forecasting work) |

## 9. Recommended implementation scope

**Build a deviation reporter, not an anomaly detector.** Concretely:

- `engine/deviation.py`, deterministic, no LLM, mirroring `forecasting.py` in structure
- Covers **collections and revenue only**; every other family returns a capability limitation
  naming its specific reason
- Rolling 12-month median/MAD on month-over-month changes, computed strictly from prior months
- Returns: the change, the rolling baseline, the robust score, and any overlapping DQ finding
- **Emits no anomaly verdict.** The owner-facing wording is "this was the largest movement in
  N months" or "this is about X times a typical month's change", never "this is an anomaly"
- Registry: add `deviation_report` as IMPLEMENTED and keep `anomaly_surface` PARTIAL with the
  cutoff reason made explicit

The honest one-line summary: **the data supports telling an owner how unusual a month was; it does
not support telling them whether that matters.** Same shape as the materiality refusal already in
the product.

---

*Investigation only — no implementation performed.*
