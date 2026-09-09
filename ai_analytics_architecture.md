# AI Analytics Architecture

System architecture for the future AI Business Analyst. **Specification only — no code, no
LLM API calls, no chat UI, no backend, no live database connection, no RAG, no vector database,
no agents-in-code.** Every component below consumes the semantic layer already built
(`semantic_layer.md`, `semantic_metric_registry.csv`, `business_dimensions.md`,
`metric_dependency_graph.md`, `ai_trust_policy.md`, `business_insight_framework.md`) as its
**sole specification source** — this document does not introduce a new business fact, metric,
or dimension; it defines how those already-established facts get turned into an answer.

---

## 1. Design goal

A system that behaves as a combined **Data Analyst + Data Scientist + BI Analyst + Business
Analyst + Financial Analyst + Operations Analyst** — able to answer natural-language business
questions with metric lookups, filters, grouping, period comparisons, trends, anomaly detection,
driver analysis, root-cause investigation, and recommendations — while **never** violating the
trust rules already established: `SAFE` / `DISCLOSE` / `SHOW_BOTH` / `BLOCK` /
`NOT_DETERMINABLE`. The trust rules are not a feature of this architecture — they are its
**hard constraint**. Every component described below exists in service of never letting a
`BLOCK` metric reach the user as a single number, never letting a `SHOW_BOTH` metric collapse to
one figure, and never letting `created_at` silently substitute for a business date.

---

## 2. Layered architecture

```
+--------------------------------------------------------------------------------+
| Layer 7:  AI Business Analyst (composed persona)                                |
|           - Data Analyst / Data Scientist / BI / Business / Financial / Ops    |
|           - question_understanding_spec.md + business_reasoning_spec.md        |
+--------------------------------------------------------------------------------+
| Layer 6:  Answer Assembly & Contract                                            |
|           - answer_contract.md: structure every answer must satisfy            |
+--------------------------------------------------------------------------------+
| Layer 5:  Business Reasoning Engine                                             |
|           - FACT -> CALCULATION -> OBSERVATION -> INFERENCE -> HYPOTHESIS       |
|             -> RECOMMENDATION  (business_reasoning_spec.md)                    |
|           - Insight generation (insight_generation_spec.md)                    |
+--------------------------------------------------------------------------------+
| Layer 4:  Analytics Execution Engine                                            |
|           - filter / group / compare-period / trend / anomaly / driver         |
|             (analytics_execution_spec.md)                                      |
+--------------------------------------------------------------------------------+
| Layer 3:  Trust & Conflict Gate                                                 |
|           - reads trust_level, conflict_ids, dq_ids from the semantic registry |
|           - enforces SAFE/DISCLOSE/SHOW_BOTH/BLOCK/NOT_DETERMINABLE            |
|             (ai_trust_policy.md -- ALREADY SPECIFIED, this layer ENFORCES it)  |
+--------------------------------------------------------------------------------+
| Layer 2:  Question Understanding                                                |
|           - Intent -> Metric Resolution -> Dimension Resolution -> Time         |
|             Resolution (question_understanding_spec.md)                        |
+--------------------------------------------------------------------------------+
| Layer 1:  Semantic Layer (ALREADY BUILT, immutable input to this architecture)  |
|           semantic_layer.md | semantic_metric_registry.csv | business_dimensions.md |
|           metric_dependency_graph.md | ai_trust_policy.md                      |
+--------------------------------------------------------------------------------+
| Layer 0:  Evidence Layer (ALREADY BUILT, immutable)                             |
|           253 exported CSVs | file_manifest.csv | metric_reconstruction.md      |
|           validation_summary.csv | data_quality_registry.csv | conflicts.md     |
+--------------------------------------------------------------------------------+
```

**Layers 0–1 are complete and out of scope for further design in this phase** — they are
consumed, not redesigned. Layers 2–7 are what this set of 9 documents specifies.

**Directionality rule:** every layer may only read from the layer(s) below it, never bypass a
layer. In particular, Layer 4 (Analytics Execution) may never compute a number that Layer 3
(Trust & Conflict Gate) has not already cleared — trust checking happens **before** execution,
not as a post-hoc filter on the answer, because a `BLOCK` metric must never even be
*computed and then hidden*; it must never be computed for user-facing output at all (it may
still be computed internally for the AI's own reasoning about *why* it's blocked, per
`ai_trust_policy.md` §2 BLOCK behavior — "offer the closest safe alternative").

---

## 3. The question-to-answer pipeline

This is the canonical processing path every question flows through, expanding the 11-stage
pipeline the brief specifies. Each stage is detailed in its own spec document; this section
defines how they connect.

```
User Question
   |
   v
[1] Intent                      -- question_understanding_spec.md §2
   |  (what KIND of question: lookup / trend / comparison / anomaly / driver /
   |   risk-scan / recommendation / follow-up)
   v
[2] Metric Resolution            -- question_understanding_spec.md §3
   |  (map to metric_id(s) in semantic_metric_registry.csv; if no mapping,
   |   -> "Not determinable from exported evidence.")
   v
[3] Dimension Resolution         -- question_understanding_spec.md §4
   |  (map to business_dimensions.md entries: property/tenant/bed/account/etc;
   |   reject unsupported dimension combinations)
   v
[4] Time Resolution              -- question_understanding_spec.md §5
   |  (resolve to the metric's documented date_field; check historical_policy
   |   coverage boundary; distinguish snapshot vs. historical question)
   v
[5] Trust Check                  -- ai_trust_policy.md (ALREADY SPECIFIED) via
   |                                 Layer 3 of this architecture
   |  (read trust_level: SAFE / DISCLOSE / SHOW_BOTH / BLOCK / NOT_DETERMINABLE)
   v
[6] Conflict Check                -- metric_dependency_graph.md §6 propagation table
   |  (if the resolved metric depends on a conflicted/downgraded upstream metric,
   |   inherit the WORST trust level among all dependencies -- per
   |   metric_dependency_graph.md §7's "worst-of-inputs" rule for composites)
   v
[7] Analytics Plan                -- analytics_execution_spec.md §2
   |  (decide WHAT calculation is needed: single lookup, group-by, period
   |   compare, trend series, anomaly scan, driver decomposition -- and which
   |   of those are even PERMITTED given the Trust Check's result)
   v
[8] Execution                     -- analytics_execution_spec.md §3-7
   |  (apply the metric's documented filters/aggregation/reversal/soft-delete
   |   policy EXACTLY as specified in semantic_metric_registry.csv -- no ad-hoc
   |   substitution)
   v
[9] Validation                    -- analytics_execution_spec.md §8
   |  (compare against validation_reference / validation_summary.csv where one
   |   exists; check numeric sanity -- see "numerical validation" in §9 below)
   v
[10] Business Reasoning           -- business_reasoning_spec.md
   |  (FACT -> CALCULATION -> OBSERVATION -> INFERENCE -> HYPOTHESIS ->
   |   RECOMMENDATION -- only entered for trend/anomaly/driver/recommendation
   |   intents; a simple lookup question stops at CALCULATION)
   v
[11] Answer                       -- answer_contract.md
   |  (assemble the final structured answer: text + trust posture + evidence)
   v
Evidence / Confidence
   (attached per answer_contract.md's provenance model -- always present,
    not optional, per ai_trust_policy.md §5)
```

**A question can exit early at several points**, and this is by design, not a failure mode:
- Exit at [2] if no metric mapping exists → `NOT_DETERMINABLE`.
- Exit at [4] if the requested period is outside the metric's `historical_policy` coverage →
  disclose the boundary, do not extrapolate.
- Exit at [5]/[6] with a `BLOCK` verdict → the pipeline still completes stages [7]–[11], but the
  Analytics Plan at [7] is constrained to "explain the conflict," never "compute one number,"
  and the Answer at [11] is the refusal-with-explanation shape defined in
  `ai_trust_policy.md` §2 BLOCK / `answer_contract.md`.

---

## 4. Component responsibilities

| Component | Reads from | Produces | Never does |
|---|---|---|---|
| **Question Understanding** | `semantic_metric_registry.csv`, `business_dimensions.md` | Intent, candidate `metric_id`(s), dimension filters, date range | Compute any number; guess a metric when ambiguous (routes to clarification instead, per `question_understanding_spec.md`) |
| **Trust & Conflict Gate** | `semantic_metric_registry.csv.trust_level`, `metric_dependency_graph.md` §6 | A trust verdict (SAFE/DISCLOSE/SHOW_BOTH/BLOCK/NOT_DETERMINABLE) for the resolved metric(s) | Downgrade a metric's trust level based on the question's phrasing (trust is a property of the metric, not the question) |
| **Analytics Execution Engine** | Evidence layer (CSVs) via the same evidence-loading discipline as `scripts/validation/common.py`, filtered/aggregated per the metric's registry row | A raw numeric/tabular result | Apply a filter, aggregation, reversal, or soft-delete rule not already documented in the metric's registry row |
| **Validation** | `validation_summary.csv`, the metric's own `validation_reference` | A validation status for THIS specific query (not just the one validation run captured historically) | Silently accept a result that fails a documented sanity check (see §9) |
| **Business Reasoning Engine** | Execution output, `metric_dependency_graph.md`, `data_quality_report.md` | FACT/CALCULATION/OBSERVATION/INFERENCE/HYPOTHESIS/RECOMMENDATION-labelled statements | Present a HYPOTHESIS or RECOMMENDATION using FACT-level language |
| **Insight Generation** | Same as Business Reasoning, plus proactive triggers | Ranked, evidence-backed insight candidates | Surface an insight without a traceable metric/evidence chain |
| **Answer Assembly** | All of the above | The final structured answer per `answer_contract.md` | Emit an answer missing its trust/evidence/provenance fields |

---

## 5. Cross-cutting concerns (specified here, detailed in their own sections below)

- **Evidence citation model, confidence model, metric/calculation provenance** — `answer_contract.md`.
- **DQ propagation** — already fully specified in `metric_dependency_graph.md` §6; this
  architecture's Trust & Conflict Gate is the enforcement point, not a re-specification.
- **Temporal reasoning, business-date handling, historical vs. snapshot reasoning** —
  `question_understanding_spec.md` §5, enforcing `business_dimensions.md` §1's rules.
- **Organization/property/tenant grain protection** — §6 below.
- **Prevention of metric mixing** — §7 below.
- **Hallucination prevention, numerical validation, answer consistency** — §8–9 below.

---

## 6. Grain protection

Every metric in `semantic_metric_registry.csv` documents its grain (`org=...; property=...;
tenant/allotment=...`). The architecture must enforce that:

1. **A result computed at one grain is never presented as if computed at a finer grain.** E.g.
   `M.AR.001A`'s grain is `(tenant_id, allotment_id)` — an answer to "what does tenant X owe"
   must query at that grain, never approximate from an organization-level AR total divided by
   tenant count.
2. **A degenerate dimension is disclosed, not silently used as if meaningful.** Property is a
   degenerate dimension in this dataset (1 property) — a "which property performs best"
   question must be caught by grain protection and answered per `ai_trust_policy.md`'s named
   example, not silently computed against a single-row grouping and presented as a ranking.
3. **Grain mismatches across a composite question are rejected, not auto-joined.** If a question
   implicitly requires joining two metrics at incompatible grains (e.g. combining `M.OCC.001`,
   bed-grain, with `M.PROFIT.001`, org-grain, into a single "profit per occupied bed" figure —
   not a metric in the registry), the Analytics Plan stage must recognize this as **not a
   registry metric** and either decompose it into its documented components (with each one's own
   trust label) or return `NOT_DETERMINABLE`, never silently synthesize a new ratio.

---

## 7. Prevention of metric mixing

"Metric mixing" = combining two metrics that measure superficially similar things but are
**not** the same semantic concept, without disclosing that they differ. The architecture
prevents this via three mechanisms, all already specified upstream and enforced here:

1. **Metric family grouping.** `semantic_metric_registry.csv`'s `dependency_metrics` column and
   `semantic_layer.md`'s concept groupings (e.g. the 4-way AR family, the 5+-way occupancy
   family) mean a question resolving to a *family* must never be silently narrowed to one member
   before the Trust Check — the Trust & Conflict Gate sees the whole family and returns
   SHOW_BOTH/BLOCK for the family, not a spuriously-SAFE single member.
2. **No cross-family arithmetic.** The Analytics Execution Engine may not add, subtract, ratio,
   or otherwise combine two metric_ids from **different, incompatible** definitions of the same
   concept (e.g. summing `M.AR.001A` + `M.AR.001C` would double-count) unless
   `metric_dependency_graph.md` explicitly documents that combination as valid (e.g. `revenue -
   expenses = net_profit` for a **single, named** profit definition is valid **within** that
   definition, but revenue from Def-A-ledger minus expenses from a hypothetical Def-B source
   would not be).
3. **Time-basis mixing is a subtype of metric mixing.** Combining a metric that uses `bill_date`
   with one that uses `COALESCE(paid_date,due_date)` in the same trend line (the exact
   `M.OWN.002`/`DQ.017` scenario) is prohibited by the same mechanism — the date_field is part
   of a metric's identity for mixing-prevention purposes, not an interchangeable parameter.

---

## 8. Hallucination prevention

The architecture's primary hallucination-prevention mechanism is structural, not a
post-hoc check: **every number the system emits must originate from Layer 4 (Analytics
Execution), which only reads from Layer 0/1 evidence** — there is no path in this architecture
for a number to enter an answer without a traceable `metric_id` + evidence citation. Specific
mechanisms:

- **No metric, dimension, or business rule may be introduced outside the semantic layer.** If
  Question Understanding cannot resolve a question to an existing `metric_id`/dimension, the
  answer is `NOT_DETERMINABLE` — the system never invents a plausible-sounding metric to fill
  the gap (this mirrors the discipline already enforced throughout every prior deliverable in
  this project).
- **Every quoted figure carries its `metric_id` and `validation_status`** (answer_contract.md) —
  a reviewer can always trace a number back to its reconstruction.
- **Hypotheses and recommendations are structurally separated from facts** (business_reasoning_
  spec.md) — a hallucinated-sounding causal claim ("profit fell because of X") can only be
  emitted as a labelled HYPOTHESIS with its confidence stated, never as an unqualified FACT.
- **Historical-coverage boundaries are hard-enforced** (§3 stage [4]) — the system cannot
  "helpfully" extrapolate a trend into a period with no data.

---

## 9. Numerical validation & answer consistency

- **Numerical validation:** every Execution-stage result should, where a `validation_reference`
  exists for the metric, be sanity-checked in the same style as `validate_*.py` in
  `scripts/validation/` — not by re-running those exact scripts live, but by applying the same
  discipline (compare reconstructed vs. reference, compute absolute/percentage difference, flag
  `DIFFERS` rather than silently accepting). Where a metric has no live-queryable reference (most
  `NOT_DETERMINABLE` and some `DISCLOSE` metrics), the system states the absence of validation
  explicitly rather than implying a check occurred.
- **Answer consistency:** the same question, asked twice with identical resolved
  intent/metric/dimension/time parameters, must produce an identical trust posture and — for
  `SAFE` metrics — an identical number (the evidence is immutable, so this is a determinism
  requirement on the execution engine, not a probabilistic one). For `SHOW_BOTH` metrics,
  consistency means presenting the *same set* of competing definitions in the same relative
  framing each time, not necessarily the same natural-language phrasing.

---

## 10. What this document does not specify

Model selection, prompt engineering, retrieval mechanics, latency/scaling, deployment
infrastructure, authentication, and UI/UX are all out of scope for this architecture phase —
they belong to a later implementation phase (see `implementation_roadmap.md`), and none of them
may be designed in a way that weakens any rule stated above.
