# Business Reasoning Specification

Defines the epistemic ladder every AI-generated statement must climb, and how far up that ladder
a given question is allowed to go. **Specification only — no reasoning engine code.** This
document is the execution-time counterpart to `business_insight_framework.md`'s Part B/C, which
already defined the FACT→TREND→ANOMALY→DRIVER→IMPACT→EXPLANATION→RECOMMENDATION→OUTCOME→
CONFIDENCE chain and the fact/metric/inference/hypothesis/recommendation categories. **This
document does not redefine those categories — it specifies the shorter, execution-facing chain
the task brief names explicitly** (`FACT → CALCULATION → OBSERVATION → INFERENCE → HYPOTHESIS →
RECOMMENDATION`) and maps it onto the already-established framework, so there is one coherent
reasoning model, not two competing ones.

---

## 1. Reconciling the two chains

`business_insight_framework.md`'s 9-stage chain is the **insight-generation** view (how a
proactive insight is built up, stage by stage, including TREND/ANOMALY/DRIVER/IMPACT as
distinct checkpoints). This document's 6-stage chain is the **epistemic-classification** view
(what *kind* of claim each piece of output is, for the purpose of labelling and trust
enforcement). They map onto each other as follows:

| This document's stage | Corresponds to (business_insight_framework.md) | Epistemic category (business_insight_framework.md Part C) |
|---|---|---|
| **FACT** | The raw FACT stage | Observed fact |
| **CALCULATION** | Still within FACT, but now a derived value (a metric application) | Calculated metric |
| **OBSERVATION** | TREND / ANOMALY stages | A calculated metric restated as a pattern across periods — still evidence-only, no causal claim yet |
| **INFERENCE** | DRIVER / BUSINESS IMPACT stages | Inference — a conclusion combining multiple facts/calculations, still fully evidence-backed |
| **HYPOTHESIS** | POSSIBLE EXPLANATIONS stage | Hypothesis — evidence-consistent, not proven |
| **RECOMMENDATION** | RECOMMENDED ACTION / EXPECTED OUTCOME stages | Recommendation — forward-looking, never provable from history alone |

`CONFIDENCE / EVIDENCE` (the 9th stage) is not a separate rung on this ladder — it is a
**required attribute attached to every stage's output**, per `answer_contract.md`.

---

## 2. Stage definitions and gating rules

### FACT
A value read directly from the evidence with no calculation — e.g. "`journal_entries` has
14,236 rows." **Gating rule:** any question answerable at the FACT stage alone requires no trust
check beyond confirming the underlying table/column exists in `data_inventory.md` — facts about
the evidence package itself (row counts, column existence) are inherently `SAFE`.

### CALCULATION
A value derived by applying one documented `metric_id`'s filters/aggregation to FACTS — this is
the output of the Analytics Execution Engine (`analytics_execution_spec.md`). **Gating rule:**
the CALCULATION stage is where the trust verdict (SAFE/DISCLOSE/SHOW_BOTH/BLOCK/
NOT_DETERMINABLE) is attached and becomes binding for every later stage that uses this value —
a HYPOTHESIS built on a BLOCK-status calculation must itself disclose that its foundation is
disputed, it cannot "launder" a BLOCK number into an apparently-solid downstream claim.

### OBSERVATION
A CALCULATION restated as a pattern: a trend, a period-over-period change, a value outside the
metric's historical range. **Still purely evidence-based — no "why" yet.** **Gating rule:** an
OBSERVATION must be checked against `data_quality_report.md`/`conflicts.md` before being
reported as if it reflects real business behavior — an observation that is actually a data
artifact (the owner-rent single-batch-posting spike, `DQ.020`, is the canonical example in this
project) must be relabelled or annotated at this stage, not left to propagate as if it were a
genuine business signal.

### INFERENCE
A conclusion drawn by combining multiple CALCULATIONs/OBSERVATIONs, where the combination itself
is fully evidence-backed (documented in `metric_dependency_graph.md`) — no unverified leap.
Example: *"The 4-way AR conflict means no single tenant-dues figure exists in this package"* is
an INFERENCE — it follows necessarily from the four independently-computed CALCULATIONs, no
guesswork involved. **Gating rule:** an INFERENCE may combine values with **different trust
levels**, but the INFERENCE's own trust level is the **worst** of its inputs
(`metric_dependency_graph.md` §7's "worst-of-inputs" rule) — an inference partly built on a
BLOCK metric is itself not presentable as a clean, trustworthy conclusion.

### HYPOTHESIS
A proposed mechanism or cause that is *consistent* with the evidence but **not proven** by an
exported query/function definition. Example: *"The deposit-settlement 2x pattern is consistent
with a non-reversal-aware SUM in the diagnostic's own unexported query"* — this is the exact
epistemic status `data_quality_report.md`'s `root_cause_confidence = SUSPECTED` column already
encodes. **Gating rule:** a HYPOTHESIS must be phrased with explicit hedge language ("consistent
with," "suggests," "would explain if confirmed") — never with FACT/CALCULATION-register language
("is caused by," "the reason is"). A HYPOTHESIS must state what evidence, if it existed, would
confirm or refute it (mirroring the "EXPECTED OUTCOME" discipline already used throughout
`conflicts.md`).

### RECOMMENDATION
A suggested action — inherently forward-looking, never provable from historical evidence alone.
**Gating rule (the most important one in this document):** a RECOMMENDATION must **never** be
phrased using FACT or CALCULATION register. It must always be attached to: (a) the FACT/
CALCULATION/INFERENCE that motivates it, (b) any HYPOTHESIS it depends on, clearly labelled as
such, and (c) an explicit statement that it is a recommendation, not a certainty. A
recommendation is never emitted for a `BLOCK` metric's underlying number as if that number were
settled — a recommendation touching a BLOCK metric must itself recommend *resolving the
conflict* (e.g. "an owner decision is needed on which AR definition to treat as authoritative")
before any operational recommendation built on a specific dollar figure can be made.

---

## 3. How far a question is allowed to climb the ladder

Not every question should reach RECOMMENDATION — climbing further than the question warrants is
itself a form of overreach the architecture must prevent.

| Intent (from `question_understanding_spec.md` §2) | Ladder ceiling |
|---|---|
| Lookup / Filtered lookup | CALCULATION |
| Trend | OBSERVATION |
| Comparison | OBSERVATION (INFERENCE only if the comparison itself implies a "why," which should be treated as a separate driver sub-question) |
| Anomaly detection | OBSERVATION, checked against DQ before being reported (§2, OBSERVATION gating rule) |
| Driver / root-cause | INFERENCE, with HYPOTHESIS where evidence runs out |
| Risk scan | INFERENCE (each contributing finding is a CALCULATION/OBSERVATION; the scan's synthesis into "these are the risks" is an INFERENCE, never a single risk-score CALCULATION, since no such metric exists) |
| Recommendation | Full ladder, through RECOMMENDATION |
| Meta / definitional | Not on this ladder at all — answered directly from `conflicts.md`/`ai_trust_policy.md` content |

A Lookup-intent question ("what's our revenue?") that the system answers with an unsolicited
RECOMMENDATION has violated this specification just as surely as a Recommendation-intent
question answered with only a bare number.

---

## 4. Worked example: "Why did profit fall?"

Traced through all six stages, showing how trust/conflict status propagates:

1. **FACT:** `v_pnl.net_profit` for month N is Rs.X; for month N−1 it was Rs.Y (both read
   directly, `M.PROFIT.001` Def A specifically — resolved per `question_understanding_spec.md`
   §6.1's worked example).
2. **CALCULATION:** Delta = X − Y, computed per `analytics_execution_spec.md` §5. Trust level:
   `M.PROFIT.001` is `BLOCK` for a bare "what is profit" answer, but this driver question has
   already committed to **one named definition** (Def A) at Question Understanding — the
   CALCULATION is valid **within that scope**, and the answer must state "using the ledger
   definition of profit (one of three that exist in this system, see below)" rather than
   presenting the delta as if profit were unambiguous.
3. **OBSERVATION:** The delta is large relative to the trend line for the preceding 12 months —
   flagged as notable. Checked against `data_quality_report.md`: is there a known mechanism?
4. **INFERENCE:** `metric_dependency_graph.md` §1 shows `M.OWN.002`'s owner-rent bucket feeds
   directly into Def A's expense total. If the owner-rent bucket moved materially in month N,
   that is a documented dependency edge, not a guess — this step is an INFERENCE, not a
   HYPOTHESIS, because the edge itself is proven (`business_logic.md`, both trigger bodies
   read in full).
5. **HYPOTHESIS (only if needed):** If the owner-rent bucket's movement does not fully explain
   the delta, remaining unexplained variance may be attributed to other candidate drivers
   (expense category shifts, revenue account shifts) — each stated as a hypothesis with its own
   supporting/refuting evidence, not asserted as the cause.
6. **RECOMMENDATION (only if the question asked for one, or a follow-up requests it):** e.g.
   *"Recommend confirming whether the month-N owner-rent posting reflects a one-time batch
   (as occurred historically on 2026-08-13, `DQ.020`) before treating this as an ongoing
   trend."*

Every stage above is traceable to a specific `metric_id`/`conflict_id`/`dq_id` — this is the
concrete demonstration of `ai_analytics_architecture.md` §8's hallucination-prevention structure
applied to a real driver question.

---

## 5. Cross-reference

This document, together with `business_insight_framework.md`, forms the complete reasoning
specification — neither supersedes the other. `insight_generation_spec.md` builds on both for
*proactive* (unsolicited) insight generation specifically.
