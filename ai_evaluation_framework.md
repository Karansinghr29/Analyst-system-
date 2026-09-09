# AI Evaluation Framework

Specifies how the future AI Business Analyst — once implemented — must be evaluated before and
after each release. **Specification only — no test code, no CI pipeline, no benchmark dataset
construction.** This document defines *what* must be tested and against *what standard*, drawing
the standard directly from evidence already established in this project (`validation_summary.csv`,
`ai_trust_policy.md`, `answer_contract.md`) rather than inventing a new evaluation rubric.

---

## 1. Evaluation categories

### 1.1 Numeric accuracy

For every `SAFE`/`DISCLOSE` metric with a `validation_reference` in
`semantic_metric_registry.csv`, the implementation's live-query result must match the value
already established in `validation_summary.csv` (or, if evidence is refreshed, the newly
re-derived reference) within the same tolerance already used throughout this project's
validation scripts (0.5% for `MATCH`, with explained mechanism for the 4 known `DIFFERS` cases).
**A regression here — the implementation producing a different number than the already-validated
reconstruction — is a release blocker**, not a warning, because it indicates the execution
engine has silently deviated from a documented filter/aggregation/grain rule.

**Test surface:** all 43 metrics that carry at least one script-executed check in
`validation_summary.csv` (per `metric_reconstruction.md`'s final report) — this is the pre-built
regression suite; the implementation phase's job is to reproduce these 80 checks live, not
invent new ones for this category.

### 1.2 Trust-rule compliance

For every metric, the implementation's live answer must carry the **exact** `trust_level` from
`semantic_metric_registry.csv` — not a looser or stricter posture. Specific checks:

- Every `BLOCK` metric: confirm no answer variant (direct, rephrased, comparative — per
  `ai_trust_policy.md` §2 BLOCK) ever returns a single headline number.
- Every `SHOW_BOTH` metric: confirm the answer structurally contains **all** competing
  definitions, not a subset.
- Every `DISCLOSE` metric: confirm the `caveat_text` is present verbatim (or an equivalent
  faithful paraphrase — an implementation-phase decision on exact wording, but the *content* of
  the caveat must not be dropped or diluted).
- Every `NOT_DETERMINABLE` metric: confirm the answer does not present a value with the same
  confidence framing as a validated one.

**Test surface:** all 49 metrics — this is a completeness requirement, not a sample.

### 1.3 Conflict/DQ propagation correctness

For every downgrade documented in `metric_dependency_graph.md` §6 (the DQ-metric → trust-level
propagation table), confirm the implementation's composite/dependent metrics inherit the correct
(worst-of-inputs) trust level — and, equally important, confirm the **explicitly-not-asserted**
non-dependencies in that section's closing paragraph are respected (e.g. `M.TEN.001`/`002`
remaining `SAFE` despite `DQ.003`'s overlap finding, because `H.013` proves 0 overlap for those
specific statuses). A false-positive downgrade (over-cautious, marking a genuinely SAFE metric as
DISCLOSE) is also a defect, not merely a false negative — both directions must be tested.

### 1.4 Hallucination / evidence-grounding tests

- **No-metric test:** questions with no corresponding semantic metric (e.g. "what's our margin
  analysis") must return `NOT_DETERMINABLE`, never an improvised calculation.
- **No-dimension test:** questions requiring a dimension the data doesn't support (multi-property
  comparison) must be caught at Dimension Resolution, not silently answered against a
  single-row grouping.
- **Citation-completeness test:** every numeric claim in every answer, sampled across the
  evaluation suite, must carry a `metric_id` + evidence citation per `answer_contract.md` §2 —
  an answer with an uncited number is a defect regardless of whether the number happens to be
  correct.
- **created_at-substitution test:** for every metric except `M.MAINT.001`/`002`, confirm the
  implementation never resolves a "when" question to `created_at` when a documented business
  date field exists (`question_understanding_spec.md` §5.1 step 2).

### 1.5 Consistency tests

- **Determinism:** the same resolved query, run twice against unchanged evidence, must produce
  an identical `SAFE`-metric value and an identical `SHOW_BOTH`-metric definition set
  (`answer_contract.md` §6).
- **Grain protection:** confirm no answer presents a result computed at a coarser grain as if it
  were the finer grain the question asked about (`ai_analytics_architecture.md` §6).
- **Metric-mixing prevention:** confirm no answer combines two metric_ids across an
  undocumented dependency edge (`ai_analytics_architecture.md` §7); this can be tested by
  attempting known-invalid combinations (e.g. Def-A-ledger revenue minus Def-B-application
  expenses) and confirming the system refuses or flags rather than silently computing a
  plausible-looking but ungrounded number.

### 1.6 Epistemic-ladder compliance

- Sample answers across each intent category (`question_understanding_spec.md` §2) and confirm
  the answer does not climb higher on the FACT→...→RECOMMENDATION ladder than
  `business_reasoning_spec.md` §3's ceiling table permits for that intent.
- Confirm every RECOMMENDATION-stage statement is phrased in recommendation register, never
  fact register (`business_reasoning_spec.md` §2's RECOMMENDATION gating rule) — a
  linguistic/structural check, not a numeric one.
- Confirm every HYPOTHESIS carries its `PROVEN`/`SUSPECTED` confidence label
  (`answer_contract.md` §3).

### 1.7 Historical-coverage compliance

- For maintenance and EB-domain questions, confirm no YoY/trend answer is generated
  (`question_understanding_spec.md` §5.3).
- For every metric, confirm a question about a period outside `historical_policy` coverage
  returns the coverage boundary, not a silently truncated or extrapolated answer.

---

## 2. Evaluation data sources (already available, not to be re-created)

| Source | Used for |
|---|---|
| `validation_summary.csv` (80 checks) | §1.1 numeric accuracy ground truth |
| `semantic_metric_registry.csv` (49 rows) | §1.2 trust-rule ground truth |
| `metric_dependency_graph.md` §6 | §1.3 propagation ground truth |
| `data_quality_report.md`/`data_quality_registry.csv` (32 findings) | §1.4/§1.7 grounding for what should and shouldn't be flagged |
| `ai_trust_policy.md` §3's 10 named example questions | A starting scenario set for end-to-end pipeline testing (§3 below) |
| `conflicts.md` (24 conflicts) | Ground truth for what a `SHOW_BOTH`/`BLOCK` answer's disclosed content should contain |

**No new evaluation dataset needs to be constructed from scratch** — the entire prior body of
work in this project (deliverables A through the semantic layer) already constitutes the
evaluation ground truth. The implementation phase's job is to build a system that reproduces
these already-established, already-verified answers, not to re-derive correctness from nothing.

---

## 3. Scenario-based end-to-end evaluation

The 10 named example questions in `ai_trust_policy.md` §3 form the minimum required end-to-end
scenario suite — each scenario's expected answer *shape* (not exact wording, but trust posture,
required disclosures, and epistemic ceiling) is already fully specified in that document and
must be used as the pass/fail criterion:

| Scenario | Expected trust posture | Expected disclosures |
|---|---|---|
| "How much revenue did we make?" | SAFE | None required |
| "How much does this tenant owe?" | BLOCK | All 4 AR definitions, ~120x spread named |
| "What's our occupancy?" | SHOW_BOTH | Recommended default + alternatives, 9.4-point spread named |
| "What's our profit?" | BLOCK | 3 definitions, 36.6% owner-rent swing named |
| "Which property is best?" | Dimension-resolution refusal | "only 1 property exists," not a generic NOT_DETERMINABLE |
| "Why did revenue fall?" | SAFE base metric, may surface lower-trust drivers | Driver chain traceable to `metric_dependency_graph.md` |
| "Which tenants are overdue?" | Composite, SHOW_BOTH + DISCLOSE | As-of date stated for aging; AR family disclosed |
| "How much electricity cost did we incur?" | DISCLOSE | 2-month coverage, billing-format caveat if joined |
| "What are our biggest business risks?" | Composite | 4 CRITICAL + relevant HIGH findings named individually, never blended |
| "What should management do next?" | RECOMMENDATION | Full ladder, explicitly labelled as recommendation |

Additional scenarios should be added over time as new question patterns are observed in
production use — this table is a floor, not a ceiling, on scenario coverage.

---

## 4. Regression discipline

Any change to `semantic_metric_registry.csv` (e.g. a trust-level update following an owner
decision that resolves a conflict) must trigger re-evaluation of every scenario touching the
changed metric — the evaluation suite is not a one-time gate, it is a standing regression check
tied to the semantic layer's own versioning. Per `answer_contract.md` §6: a trust-level change
must propagate to every answer immediately, and the evaluation framework's job is to confirm it
actually does.

---

## 5. What this framework does not specify

Statistical significance thresholds for anomaly-detection accuracy, user-satisfaction
measurement, latency/performance SLAs, and the concrete test-automation tooling are all
implementation-phase decisions outside this specification's scope.
