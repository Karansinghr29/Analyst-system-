# Business Insight Framework

Specification for the future AI Business Analyst's insight-generation logic. **This document
defines what kinds of insights the semantic layer should eventually enable and how reasoning
must be structured and labelled — it does not implement any of it.** No LLM prompts, agents, or
insight-generation code exist yet. Every insight category below is scoped to what the semantic
layer (`semantic_layer.md`, `semantic_metric_registry.csv`) can actually support today, given
the historical coverage and trust levels already established — this document does not propose
an insight category the evidence cannot back.

---

## Part A — Insight categories

Each category lists the semantic metrics it draws on, and their trust levels, so the future
insight engine knows upfront which analyses can be stated as fact and which must be qualified.

### A.1 Financial analysis

| Insight type | Metrics used | Trust posture |
|---|---|---|
| Revenue trends | `M.REV.001`/`002`, `M.PNL.001` | SAFE — direct trend analysis supported, 53-57 months of coverage |
| Collections trends | `M.COL.001`/`002`/`003` | DISCLOSE — application-level and ledger-derived trends must be labelled separately, never merged into one line |
| Receivables analysis | `M.AR.001A-D`, `M.AR.002`/`003` | BLOCK/SHOW_BOTH — a "receivables trend" insight can only be built per-definition, never as one blended series |
| Cash analysis | `M.CASH.001` | SAFE (by construction, not independently re-validated — flag accordingly) |
| Deposits analysis | `M.DEP.001`/`002`/`003`, `M.RISK.003`/`004` | SAFE for the held balance; DISCLOSE for settlements/refunds; DISCLOSE for phantom-deposit risk |
| Expense analysis | `M.EXP.001`/`002` | SAFE for the total; DISCLOSE for category breakdown (electricity-bucket gap) |
| P&L analysis | `M.PNL.001` | SAFE (ledger-only definition) |
| Owner payments analysis | `M.OWN.001`/`002` | SAFE for the source total; SHOW_BOTH for the owner-rent-in-profit question |
| Profitability analysis | `M.PROFIT.001` | BLOCK — no profitability trend or comparison may be stated as one number; must be run per-definition or refused |
| Margin analysis | Not a registry metric | **Not determinable from exported evidence** — no margin-specific metric was reconstructed; a margin insight would need to be built from `M.REV.001`/`M.EXP.001`/`M.PROFIT.001` directly and inherits `M.PROFIT.001`'s BLOCK status if profit is the denominator |

### A.2 Operational analysis

| Insight type | Metrics used | Trust posture |
|---|---|---|
| Occupancy | `M.OCC.001`/`002`/`005` | SHOW_BOTH — every occupancy insight must name its definition |
| Vacancy | Derived from `M.OCC.001`'s `vacant` bucket | SHOW_BOTH, **with an added caveat**: `v_occupancy`'s own `vacant` column is proven to undercount by exactly the 7 On-Notice-only beds (`C.009`) — a vacancy insight sourced from that specific column must disclose the defect, not merely the definitional ambiguity |
| On-Notice tenants | `M.TEN.002` | SAFE (the raw count); feeding it into an occupancy-% insight inherits SHOW_BOTH |
| Tenant lifecycle | `M.LIFE.001`-`004` | SAFE |
| Move-ins / move-outs | `M.LIFE.002`/`003` | SAFE, 67/47-month coverage — genuine trend analysis supported |
| Bed utilization | `M.OCC.004` | NOT_DETERMINABLE — fully specified, unvalidated; any utilization insight at bed grain must say so |
| Property performance | `M.OCC.002`, `M.AR.003` | **Not meaningfully supportable today** — 1 property in the dataset; a "property performance comparison" insight cannot be generated (there is nothing to compare) |
| Maintenance workload | `M.MAINT.001` | SAFE, 20-month coverage — trend supported, **no YoY** |
| Maintenance costs | `M.MAINT.002` | SAFE (both linkage paths proven to agree) |
| EB/electricity | `M.EB.001`/`002` | DISCLOSE — 2–5 month coverage, **no trend/YoY insight should be generated**; billing-period format issue must be disclosed before any invoice/expense cross-reference |

### A.3 Risk analysis

| Insight type | Metrics used | Trust posture |
|---|---|---|
| Overdue receivables | `M.RISK.001`/`002` | BLOCK for the underlying total; the aging bucket itself is DISCLOSE with a mandatory as-of date |
| Invoice balance drift | `M.INV.001` (internal consistency) | DISCLOSE — 42.7% of live invoices affected (`DQ.001`, CRITICAL) — this should be a **proactively surfaced** risk insight, not only answered on request |
| Duplicate invoices | `M.RISK.005` | DISCLOSE — 6.8% of live invoices, no dedup mechanism exists; proactively surfaceable |
| Duplicate receipts | `M.RISK.006` | DISCLOSE — smaller scale (11 live), but demonstrates detected issues are not auto-remediated |
| Overlapping allotments | `M.RISK.007` | DISCLOSE — 187–214 pairs depending on reconstruction method |
| Accounting reconciliation issues | `M.RISK.008` | DISCLOSE — receipts/invoices/deposit-settlements source-vs-ledger gaps |
| Stale/frozen datasets | `tenant_transactions` (`M.AR.001D`), `eb_monitoring_readings` | BLOCK / DISCLOSE respectively — a "data freshness" insight should flag both proactively |
| Missing organization IDs | `whatsapp_events`, `ticket_logs`, `payroll_sync`, `email_templates` | Not a registry metric — a data-integrity insight only, drawn directly from `DQ.025`; would silently under-count an org-scoped `ticket_logs` rollup by 0.79% if not disclosed |
| EB period inconsistencies | `M.EB.001`/`002` | DISCLOSE (`DQ.028`) |
| Ledger/source mismatches | `M.RISK.008` | DISCLOSE |
| Data-quality risks (general) | `M.RISK.009` | SAFE (the meta-metric itself); the underlying issues it counts range across all trust levels |

**Proactive vs. reactive insights.** Some risk items above are marked "proactively surfaceable" —
these are exactly the CRITICAL/HIGH findings from `data_quality_report.md` (`DQ.001`, `DQ.002`,
`DQ.016`, `DQ.019` at CRITICAL; several HIGH items) that represent real, unresolved exposure
(e.g. the Rs.722,700.00 phantom-deposit figure) rather than mere reporting curiosities. The
insight engine should surface these without being asked, subject to the reasoning-chain
discipline in Part B — a proactive surfacing is still a FACT/TREND/ANOMALY statement with
evidence, never a bare alarm.

---

## Part B — The reasoning chain

Every insight the future AI Business Analyst produces must be traceable through these stages,
in order. A stage may be skipped only if it genuinely does not apply (e.g. a pure FACT question
has no DRIVER stage) — it may never be skipped because the evidence for it is inconvenient.

```
FACT
  -> TREND
  -> ANOMALY
  -> DRIVER
  -> BUSINESS IMPACT
  -> POSSIBLE EXPLANATIONS
  -> RECOMMENDED ACTION
  -> EXPECTED OUTCOME
  -> CONFIDENCE / EVIDENCE
```

### FACT
A single, directly-observed value from a `SAFE` or (labelled) `DISCLOSE`/`SHOW_BOTH` metric, at
a stated date/period. Example: *"Ledger-derived revenue for 2026-06 was Rs.X (F.001, MATCH)."*
**A FACT is never itself a conclusion** — it is the raw material every later stage builds on.

### TREND
A FACT observed across multiple periods, using the metric's own documented date field and
respecting its historical-coverage boundary (`ai_trust_policy.md` §1 step 7). A trend statement
must name the window and the metric definition used. **No trend may be constructed for a metric
whose coverage is below ~6 months of relevant history** (EB, maintenance) beyond what that
window actually shows — no extrapolation.

### ANOMALY
A statistically or materially notable deviation from the trend — a single month spiking, a
sudden drop, a value outside the historical range. An anomaly is still a **calculated
observation**, not yet an explanation. It must be checked against `data_quality_report.md`
**before** being reported as a business anomaly: several apparent "anomalies" in this package
turned out to be data-quality artifacts, not business events (e.g. the owner_payments
single-batch posting on 2026-08-13, `DQ.020`, would look like a revenue/expense spike in a naive
month-over-month trend if the poster didn't know it was a migration event, not new business
activity).

### DRIVER
The specific metric component(s) responsible for an anomaly, isolated via the dependency graph
(`metric_dependency_graph.md`). Example: *"The apparent expense spike in 2026-08 is driven
entirely by the owner_rent bucket, which itself reflects a one-time posting batch, not 46 months
of incremental owner-rent activity landing in one month."* A DRIVER claim must cite the specific
upstream table/column/mechanism, not a vague "expenses went up."

### BUSINESS IMPACT
What the driver means in business terms — translating a ledger mechanism into a statement a
non-technical manager would recognize. Example: *"This does not represent a real change in
owner-rent expense; the business's actual owner-rent obligation has been roughly Rs.19M across
the full history, now fully reflected in the ledger in one entry rather than spread across 46
months."*

### POSSIBLE EXPLANATIONS
Where the DRIVER stage cannot fully account for an anomaly from evidence alone, this stage lists
**hypotheses**, explicitly labelled as such, ranked by how well the evidence supports each —
mirroring the discipline already used throughout `conflicts.md`/`data_quality_report.md` (e.g.
the deposit-settlement 2× pattern: "consistent with a non-reversal-aware SUM in the diagnostic
query — a strong, but not proven, hypothesis"). **A hypothesis is never promoted to a DRIVER
statement without evidence that confirms it.**

### RECOMMENDED ACTION
A suggested next step, **always phrased as a recommendation, never as a fact or a certainty**.
Example: *"Recommend reconciling the deposit_settlements source-vs-ledger drift with a live-DB
query using a reversal-aware SUM, since the 2.0000x pattern in 23 of 43 rows is the strongest
lead among the three source-vs-ledger conflicts."* A recommendation must name what evidence
would confirm or refute it, per `ai_trust_policy.md`.

### EXPECTED OUTCOME
What should be observed if the recommended action is taken and the hypothesis is correct — a
falsifiable prediction, not a guarantee. Example: *"If the diagnostic query is corrected to net
reversals, the deposit-settlement source-vs-ledger gap should shrink toward Rs.0 for the 23
rows showing the exact 2x pattern; if it does not, the double-count hypothesis is wrong and a
different mechanism is at play."*

### CONFIDENCE / EVIDENCE
Every insight closes with an explicit confidence statement tied to concrete evidence: the
`metric_id`(s), `validation_status`, `conflict_ids`/`dq_ids` involved, and whether the
underlying claim is `PROVEN` (independently re-derived and exact-matched, e.g. the P&L bucket
gap) or `SUSPECTED` (a plausible, evidence-consistent mechanism not confirmed by an exported
query definition, e.g. the deposit-settlement 2× pattern) — using exactly the vocabulary already
established in `data_quality_report.md`'s `root_cause_confidence` column, not a new scale
invented for this document.

---

## Part C — Separating fact, metric, inference, hypothesis, and recommendation

Five distinct epistemic categories, which must never be blurred together in an insight's output:

| Category | Definition | Example from this package |
|---|---|---|
| **Observed fact** | A value read directly from the exported evidence, with no calculation. | "`journal_entries` has 14,236 rows; 347 are reversals (`H.005`)." |
| **Calculated metric** | A value derived by applying a documented aggregation/filter to observed facts, matching a `metric_registry.csv` definition. | "Total ledger revenue is Rs.72,705,593.43 (`M.REV.001`, MATCH vs. `F.001`)." |
| **Inference** | A conclusion drawn by combining multiple calculated metrics or facts, still fully evidence-backed (no unverified leap). | "The 4-way AR conflict means no single tenant-dues figure exists in this package (`C.005`, all four definitions independently computed and compared)." |
| **Hypothesis** | A proposed mechanism or cause that is *consistent* with the evidence but not proven by an exported query/function definition. | "The deposit-settlement 2x pattern is consistent with a non-reversal-aware SUM in the diagnostic's own (unexported) query." |
| **Recommendation** | A suggested action, inherently forward-looking and never provable from historical evidence alone. | "Recommend re-running the deposit-settlement reconciliation with a reversal-aware SUM against a live database." |

**Enforcement rule:** every sentence of an insight output should be classifiable into exactly
one of these five categories, and the category should be recoverable from how the sentence is
phrased (this document does not mandate literal tagging in user-facing text, but the underlying
generation logic must track which category each claim belongs to). A **recommendation must never
be phrased using fact-language** ("profit fell because X" when X is a hypothesis, not a proven
driver) — the correct phrasing is "profit *may have* fallen because of X, which is consistent
with [evidence] but not confirmed."

---

## Part D — What this framework explicitly does not do yet

- It does not generate any actual insight — no code, no prompts, no scheduled job.
- It does not define anomaly-detection thresholds (what counts as "statistically notable") —
  that is a modeling decision for the implementation phase, informed by but not decided in this
  specification.
- It does not define how insights are delivered (dashboard tile, chat response, proactive
  alert) — that is a UI/architecture decision explicitly out of scope here.
- It does not attempt to generate insights for metrics with insufficient historical depth
  (maintenance, EB) beyond what their actual coverage supports — no YoY, no long-run trend,
  regardless of how the future system is asked.
- It does not resolve any of the `SHOW_BOTH`/`BLOCK` conflicts on the business's behalf — every
  future insight touching those metrics inherits the same disclosure obligations defined in
  `ai_trust_policy.md`, permanently, until an explicit owner/product decision changes a metric's
  trust level in the registry.
