# Question Understanding Specification

Specifies how a natural-language business question is resolved to a semantic-layer query.
**Specification only — no NLP model, no prompt, no code.** Every resolution target referenced
below (`metric_id`, dimension, date field) is one already catalogued in
`semantic_metric_registry.csv` / `business_dimensions.md` — this document defines the resolution
*procedure*, not new business content.

Corresponds to pipeline stages **[1] Intent → [2] Metric Resolution → [3] Dimension Resolution →
[4] Time Resolution** in `ai_analytics_architecture.md` §3.

---

## 1. Overview

```
User Question
   -> [1] Intent classification
   -> [2] Metric resolution (metric_id or metric family)
   -> [3] Dimension resolution (business_dimensions.md entries + filter values)
   -> [4] Time resolution (date_field + range + snapshot-vs-historical)
   -> handed to Trust & Conflict Gate (ai_analytics_architecture.md Layer 3)
```

Each stage can terminate the pipeline early with a clarification request or a
`NOT_DETERMINABLE` result — this is correct behavior, not a fallback for failure.

---

## 2. Intent classification

The system must classify every question into one of the following intent categories before
attempting metric resolution — the intent determines which parts of the semantic layer are
relevant and which pipeline stages (business reasoning, insight generation) will be invoked
later.

| Intent | Description | Example | Downstream handling |
|---|---|---|---|
| **Lookup** | A single current or point-in-time value. | "What's our revenue?" | Stops at CALCULATION in `business_reasoning_spec.md`. |
| **Filtered lookup** | A lookup narrowed by a dimension. | "What's occupancy at [property]?" | Same as Lookup, plus Dimension Resolution filtering. |
| **Trend** | A value over multiple periods. | "How has revenue trended this year?" | Requires OBSERVATION stage (business_reasoning_spec.md). |
| **Comparison** | Two periods, entities, or definitions compared. | "Is this month better than last?" | Requires OBSERVATION; may require SHOW_BOTH handling if the metric itself has competing definitions. |
| **Anomaly detection** | Asking whether something looks unusual. | "Did anything look off this month?" | Requires OBSERVATION → INFERENCE (business_reasoning_spec.md §Anomaly). |
| **Driver / root-cause** | Asking *why* a metric moved. | "Why did profit fall?" | Requires full chain through HYPOTHESIS (business_reasoning_spec.md). |
| **Risk scan** | Asking about exposure/risk broadly. | "Who are our risky tenants?" | Draws on `data_quality_report.md`/`business_insight_framework.md` §A.3 directly, not a single metric. |
| **Recommendation** | Asking what to do. | "What should management do?" | Must reach RECOMMENDATION stage, never answered from CALCULATION alone. |
| **Follow-up** | References prior conversational context. | "And what about last quarter?" | Re-enters the pipeline with the prior question's resolved metric/dimension carried forward, time re-resolved. |
| **Meta / definitional** | Asking about the data or the system itself, not a business value. | "Why can't you tell me tenant dues?" | Answered directly from `conflicts.md`/`ai_trust_policy.md` content, bypasses Execution entirely. |

**A single question may carry more than one intent** (e.g. "why did profit fall, and what
should we do?" = driver + recommendation) — the system must decompose it into its constituent
intents and answer each per its own rules, not blend them into one undifferentiated response.

---

## 3. Metric resolution

### 3.1 Procedure

1. Extract the business concept(s) named or implied in the question (e.g. "revenue," "how much
   we owe," "occupancy").
2. Match against `semantic_metric_registry.csv.semantic_name` / `.description` /
   `.display_name` — **not** a fuzzy free-text match against the whole registry row; the match
   target is the concept's name and description fields specifically.
3. If the concept maps to **exactly one** `metric_id`, proceed with that.
4. If the concept maps to a **metric family** (`semantic_layer.md`'s multi-definition concepts:
   tenant dues §4, occupancy §7, profit §12, owner rent §11), resolve to the **whole family**,
   never to one member picked implicitly.
5. If the concept maps to **zero** metrics, do not guess a nearby one — return
   `"Not determinable from exported evidence — no semantic metric corresponds to this question."`
6. If the concept maps to **multiple, unrelated** metrics (true ambiguity, not a known family —
   e.g. "collections" could mean `M.COL.001` or `M.COL.003`, two *related but distinct* metrics,
   not members of one documented family), apply the ambiguity-handling rule in §6.

### 3.2 Family resolution is mandatory, not optional

This is the single most important rule in this document, because it is the mechanism that
prevents the exact failure mode `ai_trust_policy.md` §0 rule 3 prohibits ("never downgrade a
BLOCK metric because a plausible alternative exists"). A naive metric-resolution step that
matches "tenant dues" to `M.AR.001A` alone (because it's first alphabetically, or because it's
`SHOW_BOTH` rather than `BLOCK` and therefore "easier") is a **specification violation**. The
resolver must always check `semantic_layer.md`'s concept groupings before finalizing a
resolution — a concept-to-metric-family mapping table, derived directly from `semantic_layer.md`'s
own section structure, is the required lookup artifact:

| Concept | Resolves to family | Not a single metric |
|---|---|---|
| Tenant dues / receivables / outstanding dues | `M.AR.001A`, `M.AR.001B`, `M.AR.001C`, `M.AR.001D` (+ `M.AR.002`/`003`/`M.RISK.001` at other grains) | Never resolve to `M.AR.001A` alone |
| Occupancy | `M.OCC.001` (which itself represents 5+ definitions), `M.OCC.002`, `M.OCC.005` | Never resolve to one bare percentage |
| Profit | `M.PROFIT.001` (3 definitions within one metric_id) | Never resolve to "the ledger figure" silently |
| Owner rent / owner-rent-in-profit | `M.OWN.002` (3 definitions within one metric_id) | Never resolve to one of the three silently |
| Collections | `M.COL.001` (application) and `M.COL.003` (ledger) — related but genuinely distinct, not one family; resolver must disclose both exist | — |

### 3.3 Concept not represented in the registry

Some plausible business questions have **no corresponding metric** at all — e.g. "margin
analysis" (`business_insight_framework.md` §A.1 notes this explicitly), "collection efficiency"
(`metric_dependency_graph.md` §2), or a multi-property performance ranking (only 1 property
exists). The resolver must recognize these as **structurally absent**, not attempt a
best-effort improvisation from adjacent metrics. Output: `NOT_DETERMINABLE`, with the specific
reason (no such metric; or the required dimension is degenerate) stated.

---

## 4. Dimension resolution

### 4.1 Procedure

1. Extract any dimension references in the question (a property name, a tenant name, a bed
   code, a date range phrase, an account/category name).
2. Match against `business_dimensions.md`'s catalogued dimensions and their valid values (where
   an enum exists — e.g. `staying_status IN ('Staying','On-Notice','Booked','Exited',
   'Cancelled')`).
3. Confirm the resolved metric's `grain` (from `semantic_metric_registry.csv`) actually supports
   the requested dimension. A metric whose grain does not include `property_id` cannot be
   filtered by property without an explicit join documented in `semantic_layer.md`/
   `business_logic.md` (e.g. `M.COL.001` requires a join through `tenant_allotments` to reach
   property — this join is documented, so it is permitted; an undocumented join is not).
4. If the requested dimension value doesn't exist in the data (e.g. a property name not in the
   1-row `properties` table), return `NOT_DETERMINABLE` for that specific filter — do not silently
   drop the filter and answer unfiltered.

### 4.2 Degenerate-dimension guard

Per `ai_analytics_architecture.md` §6 (grain protection): `organization` and `property` are
**degenerate** dimensions in this dataset (1 org, 1 property). Any question that depends on
comparing across multiple values of a degenerate dimension (e.g. "which property performs
best") must be caught **here**, at dimension resolution, before reaching Execution — the answer
is not `NOT_DETERMINABLE` in the sense of "we can't compute it," it is the more specific
statement: *"only 1 property exists in the exported data; there is nothing to compare."*

### 4.3 Reference to entity identity

Tenant/bed/apartment identification in a question ("this tenant," "bed D13A-2") must resolve to
a specific row key (`tenant_id`, `bed_id`, etc.) before Execution — never a fuzzy/partial name
match that could silently resolve to the wrong entity. Because 27 PII columns are excluded from
the export (`data_inventory.md`), entity resolution by name may not always be possible from the
exported evidence alone — where a tenant cannot be uniquely identified from available
(non-PII) fields, the answer is `NOT_DETERMINABLE`, not a best-guess match.

---

## 5. Time resolution

### 5.1 Procedure

1. Identify the requested period from the question (explicit dates, a relative phrase like
   "this month"/"last quarter"/"this year," or no period at all → defaults to the metric's
   natural "current" framing).
2. Map to the metric's **documented `date_field`** from `semantic_metric_registry.csv` —
   **never** substitute `created_at` unless the metric's own row says `created_at` is the
   business date (the one confirmed case: `M.MAINT.001`/`002`, per `business_dimensions.md`
   §17).
3. Check the requested period against the metric's `historical_policy` coverage. If the period
   falls partially or fully outside documented coverage, disclose the boundary explicitly — the
   answer states what IS covered, not a silently truncated or extrapolated figure.
4. Determine **snapshot vs. historical** framing (this is a distinct sub-decision from the date
   range itself):
   - Some metrics have **only** a snapshot form (e.g. `M.AR.001C`, the application's currently
     stored `balance_due` — there is no historical time series of past balances).
   - Some metrics have **both** forms with **different underlying definitions**, not merely
     different date filters on the same definition — most importantly occupancy: Defs A–D are
     snapshots (current allotment state), Def E and `get_occupancy_intelligence` are genuinely
     historical (day-weighted over a date range). A question like "what was occupancy in March"
     must route to Def E / `M.OCC.005`, **not** to a naive re-filtering of Def A's snapshot
     logic to a past date (Def A's SQL has no date parameter at all — it cannot answer a
     historical question by construction).
   - `v_tenant_aging` (`M.RISK.002`) is **inherently `CURRENT_DATE`-dependent** — a historical
     aging question ("what was our aging position on X date") is `NOT_DETERMINABLE` from the
     exported evidence unless X equals the export's own snapshot date (2026-08-29), because the
     aging buckets were computed once, at query time, and not preserved as a time series.
5. For period-comparison questions, resolve **both** periods through steps 1–4 independently,
   and reject the comparison if either period fails historical-coverage or snapshot/historical
   compatibility (comparing a snapshot-only metric across two dates is not meaningful and must
   be flagged, not silently computed by reapplying snapshot logic at two arbitrary dates it was
   never designed to support).

### 5.2 Fiscal year awareness

Where a metric's own function body defines a fiscal-year convention (April–March, per
`get_universal_metrics`'s `current_fy`/`last_fy` presets, `business_dimensions.md` §1), a
question using "this year" in a financial context should resolve to that FY convention, not a
calendar year, **when the resolved metric is one whose documented source function uses that
convention**. For ledger-derived metrics without an FY-aware source function (most of them),
calendar-year framing is the correct default — the resolver must not impose FY framing onto a
metric that was never defined with it.

### 5.3 YoY / long-range comparison guard

Per `metric_reconstruction.md` §4 and `business_insight_framework.md` §A.2: **no YoY or
month-over-month trend should be generated for maintenance (20 months) or any EB sub-table
(1–5 months)** regardless of how the question is phrased. This is enforced at Time Resolution,
not left to the reasoning stage to catch — a YoY request against an under-covered metric returns
`NOT_DETERMINABLE` with the actual coverage stated, before any computation is attempted.

---

## 6. Ambiguity handling

Distinguishing **definitional ambiguity** (which of several valid semantic definitions) from
**referential ambiguity** (which specific entity/period the user means) is required — they are
handled differently.

- **Definitional ambiguity** (the question could map to a `SHOW_BOTH`/`BLOCK` family, or to two
  related-but-distinct metrics like Collections app-vs-ledger): per `ai_trust_policy.md` §4,
  present both/all interpretations briefly and ask which is intended, UNLESS the family's
  documented default (`conflicts.md`'s "Recommended handling" per conflict) makes one
  interpretation clearly primary for a lookup-intent question — in which case answer with the
  default and disclose the alternative exists, reserving an explicit clarification question for
  cases where the two interpretations would give **materially different actionable
  conclusions** (e.g. a BLOCK metric always gets the full disclosure, never a silent default).
- **Referential ambiguity** (unclear which tenant/property/period): ask a clarification question
  directly — never guess an entity when getting it wrong would attribute information to the
  wrong tenant (a real-world consequence, not merely an analytical inconvenience).
- **Both stages must complete before Execution begins** — the pipeline does not execute
  speculatively against multiple candidate resolutions and pick the "best" result after the
  fact; that would reintroduce exactly the silent-resolution risk this whole specification
  exists to prevent.

### 6.1 Worked examples (resolution only — trust/answer behavior is `ai_trust_policy.md`'s domain)

- **"What's our profit?"** → Intent: Lookup. Metric resolution: `M.PROFIT.001`, a
  **within-metric** 3-way family (not 3 separate metric_ids, but the registry marks the whole
  thing `BLOCK`). No dimension needed. Time: defaults to all-time or the metric's natural
  framing if unspecified. Hands off to Trust Gate as `BLOCK` — resolution is NOT where the
  refusal happens, only where the family is correctly identified as indivisible.
- **"How much does this tenant owe?"** → Intent: Filtered lookup. Metric resolution:
  `M.AR.001A-D` family. Dimension resolution: resolve "this tenant" to a `tenant_id` (referential
  — may require a clarification if ambiguous within the conversation). Time: current-state
  snapshot (no time series exists for any of the 4 definitions in this sense). Hands off as
  `BLOCK`.
- **"What's occupancy?"** → Intent: Lookup. Metric resolution: `M.OCC.001` family (5+
  definitions within it). Dimension: none requested (organization-wide). Time: snapshot,
  current. Hands off as `SHOW_BOTH`.
- **"Which property is best?"** → Intent: Comparison. Dimension resolution: **fails** at §4.2
  (degenerate dimension guard) — no metric-resolution ambiguity at all, the question is well-formed
  but the dimension it needs cannot support a comparison. Terminates here with the specific
  "only 1 property exists" answer, not a generic `NOT_DETERMINABLE`.
- **"Why did revenue fall?"** → Intent: Driver/root-cause. Metric resolution: `M.REV.001`/`002`
  (`SAFE`). Time: requires resolving BOTH the current period and a comparison baseline period
  (§5.1 step 5). Hands off to Trust Gate as `SAFE` for the metric itself, but the
  driver-analysis reasoning that follows (`business_reasoning_spec.md`) may surface
  lower-trust upstream drivers (e.g. if the fall traces to an owner-rent posting-timing event,
  which touches `M.OWN.002`, `SHOW_BOTH`) — trust propagates into the explanation even when the
  top-level metric itself is `SAFE`.
- **"Who are our risky tenants?"** → Intent: Risk scan. Does not resolve to one metric — draws
  on `M.RISK.002`(aging)/`M.AR.001A-B`(dues, disclosed)/`M.RISK.004`(phantom deposits) as a
  composite. Dimension: tenant-grain, listing multiple entities, not a single lookup.
- **"Where are we losing money?"** → Intent: Risk scan / driver. Resolves to a composite scan
  across `M.EXP.002` (category drift), `M.RISK.005`/`006` (duplicate billing), `M.RISK.008`
  (ledger/source reconciliation gaps) — genuinely multi-metric, each retaining its own trust
  label in the resulting answer, never blended into one "money lost" figure (no such metric
  exists in the registry).
- **"What should management do next?"** → Intent: Recommendation. Requires the FULL reasoning
  chain (`business_reasoning_spec.md`) — Question Understanding's job here is only to establish
  scope (management-wide, not one metric), then hand off; the actual recommendation logic is
  entirely downstream.

---

## 7. Failure modes this specification prevents

- Silently picking one member of a metric family because it's easier to answer.
- Using `created_at` as a business date because the question didn't specify a date field.
- Answering a historical question with a snapshot-only definition (or vice versa).
- Computing a comparison across a degenerate dimension and presenting a spurious "winner."
- Generating a YoY trend for a domain with under 6 months of real coverage.
- Guessing which tenant/property a vague reference means when the wrong guess has real
  consequences.
