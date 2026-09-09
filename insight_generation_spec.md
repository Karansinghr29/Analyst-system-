# Insight Generation Specification

Specifies the mechanics of **proactive** (unsolicited) insight surfacing — as distinct from the
reactive question-answering pipeline already specified in `ai_analytics_architecture.md`/
`business_reasoning_spec.md`. **Specification only — no scheduler, no alerting code, no
scoring-model implementation.** Builds directly on `business_insight_framework.md` (which already
defines the insight categories and the FACT→...→CONFIDENCE reasoning chain) — this document adds
the *generation mechanics*: what triggers a candidate insight, how candidates are ranked, and
how they are delivered to the Answer Contract.

---

## 1. Insight generation is the Insight Generator role from `ai_agent_roles.md`

Reactive flow: `User Question → ... → Answer`. Proactive flow: `Trigger → Candidate Generation →
Ranking → Answer Contract Assembly → Delivery`. Both flows terminate in the same
`answer_contract.md`-compliant structure — an insight is not a different *kind* of output, it is
an answer the system generated without being asked, and it must satisfy every requirement a
reactive answer does (trust posture, evidence citations, epistemic labels, confidence).

---

## 2. Triggers

An insight candidate is generated when one of the following conditions is met — **no other
trigger source is in scope**, since inventing a trigger not grounded in the semantic layer would
itself be a hallucination-prevention violation:

1. **A CRITICAL or HIGH-severity DQ finding exists** (`data_quality_report.md`'s severity
   column) whose scope is currently live (not merely historical/frozen and already fully
   disclosed). Per `data_quality_report.md`'s own final tally: 4 CRITICAL, 8 HIGH. Each is a
   standing candidate for proactive surfacing, re-evaluated on whatever cadence the
   implementation phase chooses (this specification does not fix a schedule).
2. **A trend metric's latest period falls outside its own historical distribution**
   (`analytics_execution_spec.md` §2.5's anomaly scan), **after** the DQ-artifact check has
   ruled out a known data-quality mechanism as the sole explanation.
3. **A period-comparison metric's delta exceeds a materiality threshold** — this specification
   does not fix the threshold value (an implementation-phase/business decision — see
   `ai_evaluation_framework.md` for how such a threshold would be validated), but requires that
   whatever threshold is chosen be applied consistently per metric, not tuned per-instance to
   manufacture insight volume.
4. **A newly-computed value crosses a documented risk boundary** — e.g. a new allotment entering
   the phantom-deposit set (`M.RISK.004`), a new duplicate-invoice group forming (`M.RISK.005`).
   These are **re-derivable facts**, not predictions — the trigger fires because the underlying
   diagnostic query, re-run, now returns a different row set than before.

**Explicitly not a trigger:** an LLM's own "sense" that something seems interesting, absent one
of the four grounded conditions above. This restates `ai_analytics_architecture.md` §8's
hallucination-prevention rule at the insight-generation boundary specifically.

---

## 3. Candidate generation

For each fired trigger, generate one candidate insight using the same Analytics Execution
(`analytics_execution_spec.md`) and Business Reasoning (`business_reasoning_spec.md`) machinery
already specified for reactive answers — a proactive insight is produced by running the FACT→
CALCULATION→OBSERVATION→(INFERENCE→HYPOTHESIS if warranted) ladder against the triggering
metric, exactly as if a user had asked about it.

**A candidate must reach at minimum the OBSERVATION stage** — a bare FACT/CALCULATION is not yet
an "insight" in the sense the business would find useful (it's just a number); an insight needs
at least the "this is a pattern/notable value" framing OBSERVATION provides.

---

## 4. Ranking / prioritization

Candidates are ranked, not delivered in arbitrary or generation order, using a strict priority
ordering — not a blended numeric score (a blended score would itself be an invented metric, the
same failure mode `analytics_execution_spec.md` §2.8 already prohibits for risk-scan
composites):

1. **Trust-adjusted severity first.** A CRITICAL DQ finding on a `SAFE`-adjacent, currently-live
   exposure (e.g. the Rs.722,700.00 phantom-deposit figure, `DQ.011`) ranks above an anomaly on
   an already-`SHOW_BOTH`/`BLOCK` metric (whose ambiguity is already fully disclosed and
   therefore less "newly actionable").
2. **Recency of the underlying evidence** — a trigger condition newly true (a new duplicate
   group, a new anomalous period) ranks above a long-standing, previously-surfaced condition,
   to avoid repeatedly re-alerting on the same static fact.
3. **Materiality (Rs. amount or % scale)** as a tiebreaker within the same severity tier —
   drawing directly on the `affected_amount`/`pct` framing already established in
   `data_quality_report.md`'s summary matrix, not a newly-invented scale.
4. **Coverage sufficiency** — an insight about a domain with under 6 months of coverage
   (maintenance, EB) is never ranked as a "trend" insight (per §5's guard), only ever as a
   snapshot/fact-level candidate.

---

## 5. Guards inherited from the rest of the specification (not re-derived, only cross-referenced)

- **No YoY/trend insight for maintenance or EB** — `question_understanding_spec.md` §5.3.
- **No insight built on a degenerate dimension comparison** (property performance) —
  `question_understanding_spec.md` §4.2.
- **A BLOCK metric may generate an insight about the CONFLICT itself** ("the AR definitions
  disagree by up to 120x, an owner decision is needed") but never an insight asserting one of
  the competing figures as the business's actual receivables position.
- **A HYPOTHESIS-stage insight must be labelled as such** and must never be delivered with the
  same visual/textual weight as a PROVEN, FACT-grounded insight (`answer_contract.md` §3's
  confidence model).

---

## 6. Delivery

Every ranked candidate that clears the pipeline is assembled into an `answer_contract.md`-
compliant object and handed to whatever delivery mechanism the implementation phase builds
(dashboard tile, digest, chat-initiated proactive message) — **this specification does not
design that delivery mechanism**, only guarantees that whatever receives an insight receives one
with full provenance, trust posture, and epistemic labelling already attached, exactly as a
reactive answer would have.

**Deduplication:** an insight already delivered and not yet acted upon (a concept the
implementation phase defines — e.g. "acted upon" might mean a user viewed/dismissed it) should
not be re-delivered on every trigger re-evaluation cycle merely because the underlying condition
is still true — this specification requires state be tracked somewhere (to avoid alert fatigue)
without prescribing the storage mechanism.

---

## 7. Example: proactive surfacing of the phantom-deposit finding

1. **Trigger:** `M.RISK.004`'s underlying query (`v_diag_deposit_phantom` reconstruction,
   §2 condition 4) — a live-evaluable condition, not a one-time historical finding.
2. **Candidate generation:** FACT (32 allotments, per-row detail available) → CALCULATION
   (Rs.722,700.00 total exposure, `metric_reconstruction.md`'s `DEP.07`) → OBSERVATION (this
   represents held tenant money with no processing path forward — an operational gap, not a
   one-off).
3. **Ranking:** HIGH severity (`DQ.011`), currently live, Rs.722,700.00 materiality — ranks
   above most routine trend observations.
4. **Delivery object:** Answer text stating the finding; trust posture `DISCLOSE`; metric
   provenance `M.RISK.004`; evidence citations `H.045`; epistemic labels FACT/CALCULATION/
   OBSERVATION; confidence `HIGH` (the count is proven exact, `DEP.06` in
   `validation_summary.csv`); follow-up affordance: offer the per-allotment worklist for
   remediation action.

This is intentionally the same finding already identified in `data_quality_report.md`/
`business_insight_framework.md` — this document does not add a new fact, it specifies *how the
already-known fact would be surfaced without being asked*.
