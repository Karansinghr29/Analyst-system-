"""
business_reasoning.py -- Phase 4 supporting module. The minimal deterministic implementation of
business_reasoning_spec.md's epistemic ladder:

    FACT -> CALCULATION -> OBSERVATION -> INFERENCE -> HYPOTHESIS -> RECOMMENDATION

Scope, stated plainly: this is the ladder-LABELLING and gating layer the Phase 4 pipeline needs,
not a full reasoning engine. It produces evidence-backed statements at the rungs the question's
intent permits, each tagged with its epistemic category, its source metric_id(s), and its trust
level. It generates NO free-form advice -- the brief is explicit: "Do not implement free-form
autonomous business advice yet. Recommendations must remain grounded in the existing
business_insight_framework.md."

Three gating rules from the spec are enforced here in code:

  3    -- a question may not climb higher than its intent's ceiling. "A Lookup-intent question
          that the system answers with an unsolicited RECOMMENDATION has violated this
          specification just as surely as a Recommendation-intent question answered with only a
          bare number."
  2    -- INFERENCE inherits the WORST trust level of its inputs; a HYPOTHESIS built on a BLOCK
          calculation "cannot launder a BLOCK number into an apparently-solid downstream claim."
  2    -- an OBSERVATION must be checked against data_quality_report.md before being reported as
          real business behaviour. A known data artifact is relabelled at this stage.
"""
from dataclasses import dataclass, field

FACT = "FACT"
CALCULATION = "CALCULATION"
OBSERVATION = "OBSERVATION"
INFERENCE = "INFERENCE"
HYPOTHESIS = "HYPOTHESIS"
RECOMMENDATION = "RECOMMENDATION"

LADDER = (FACT, CALCULATION, OBSERVATION, INFERENCE, HYPOTHESIS, RECOMMENDATION)

# business_insight_framework.md's root_cause_confidence vocabulary -- never a numeric scale.
PROVEN = "PROVEN"
SUSPECTED = "SUSPECTED"

_SEVERITY = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}

# Hedge language a HYPOTHESIS must use, and fact-register language it must never use
# (business_reasoning_spec.md 2, HYPOTHESIS/RECOMMENDATION gating rules).
HEDGE_PHRASES = ("consistent with", "suggests", "would explain", "may have", "appears to",
                 "is a candidate", "cannot be confirmed")
FACT_REGISTER_PHRASES = ("is caused by", "the reason is", "because of", "this proves",
                         "definitely", "certainly")


@dataclass(frozen=True)
class Statement:
    stage: str               # one of LADDER
    text: str
    metric_ids: tuple = ()
    trust_level: str = ""
    conflict_ids: tuple = ()
    dq_ids: tuple = ()
    confidence: str = ""     # PROVEN / SUSPECTED for HYPOTHESIS; the contract label otherwise
    evidence: tuple = ()

    def rung(self):
        return LADDER.index(self.stage)


@dataclass
class ReasoningResult:
    statements: tuple = ()
    ceiling: str = CALCULATION          # the ceiling actually applied
    intent_ceiling: str = CALCULATION   # the intent's own ceiling, before any mandatory raise
    ceiling_raised_for_disclosure: bool = False
    highest_reached: str = CALCULATION
    violations: tuple = ()
    dq_annotations: tuple = ()

    @property
    def within_ceiling(self):
        return LADDER.index(self.highest_reached) <= LADDER.index(self.ceiling)


def _worst(levels):
    worst = "SAFE"
    for lv in levels:
        if lv and _SEVERITY.get(lv, 0) > _SEVERITY[worst]:
            worst = lv
    return worst


def reason(plan, answers, registry):
    """Build the ladder for one answered plan.

    `plan`    -- the Phase 3 AnalyticsPlan
    `answers` -- the Phase 2 MetricAnswer objects its execution calls produced
    """
    ceiling = plan.reasoning_ceiling
    statements, violations, dq_notes = [], [], []

    # business_reasoning_spec.md 3's ceiling governs how far a question may climb ELECTIVELY --
    # it exists to stop overreach ("a Lookup-intent question answered with an unsolicited
    # RECOMMENDATION"). It cannot suppress a disclosure that ai_trust_policy.md makes mandatory.
    #
    # For a SHOW_BOTH/BLOCK metric, stating that the competing definitions disagree is exactly
    # the INFERENCE business_reasoning_spec.md 2 gives as its worked example ("The 4-way AR
    # conflict means no single tenant-dues figure exists in this package ... it follows
    # necessarily from the four independently-computed CALCULATIONs"), and ai_trust_policy.md
    # requires it of every answer touching those metrics regardless of intent. A bare Lookup
    # ("What is occupancy?") therefore reaches INFERENCE by obligation, not by overreach.
    #
    # The raise is recorded rather than applied silently, and it is capped at INFERENCE: it
    # never licenses a HYPOTHESIS or RECOMMENDATION the question did not ask for.
    mandatory_disclosure = plan.trust_level in ("SHOW_BOTH", "BLOCK")
    if mandatory_disclosure and LADDER.index(ceiling) < LADDER.index(INFERENCE):
        ceiling = INFERENCE

    # A meta/definitional question is, per business_reasoning_spec.md 3's own table, "Not on this
    # ladder at all -- answered directly from conflicts.md/ai_trust_policy.md content". Mapping
    # it onto the ladder at FACT is therefore a modelling artifact, not a rule of the spec, and
    # it misfires whenever a meta-sounding question resolves to a REAL registry metric: "How
    # reliable is our data?" resolves to M.RISK.009, whose value is an ordinary CALCULATION.
    #
    # So when a meta-classified question actually computed something, treat it as the lookup it
    # turned out to be and allow CALCULATION. The raise stops there: it never licenses the
    # OBSERVATION/INFERENCE rungs a meta question did not ask for.
    if plan.metric_ids and LADDER.index(ceiling) < LADDER.index(CALCULATION):
        ceiling = CALCULATION

    # --- CALCULATION: one per computed definition -------------------------------------------
    for ans in answers:
        for r in ans.results:
            if r.value is None:
                continue
            statements.append(Statement(
                stage=CALCULATION,
                text=f"{r.definition_label}: {r.value} {r.unit}".strip(),
                metric_ids=(ans.metric_id,), trust_level=ans.trust_level,
                conflict_ids=ans.conflict_ids, dq_ids=ans.dq_ids,
                confidence=ans.confidence, evidence=tuple(r.evidence_sources),
            ))
        if not ans.results and ans.not_determinable_reason:
            statements.append(Statement(
                stage=FACT, text=ans.not_determinable_reason,
                metric_ids=(ans.metric_id,), trust_level=ans.trust_level,
                confidence=ans.confidence,
            ))

    # --- OBSERVATION: only for intents whose ceiling permits it ------------------------------
    if LADDER.index(ceiling) >= LADDER.index(OBSERVATION):
        for ans in answers:
            if ans.numeric_difference:
                for pair, diff in ans.numeric_difference.items():
                    statements.append(Statement(
                        stage=OBSERVATION,
                        text=(f"{pair} differ by {diff['absolute_difference']}"
                              + (f" ({diff['percentage_difference']}%)"
                                 if diff.get("percentage_difference") is not None else "")),
                        metric_ids=(ans.metric_id,), trust_level=ans.trust_level,
                        conflict_ids=ans.conflict_ids, dq_ids=ans.dq_ids,
                    ))
            # 2's OBSERVATION gating rule: check the DQ register BEFORE reporting a pattern as
            # real business behaviour. Any dq_id on the metric is a known mechanism that must
            # annotate the observation rather than be discovered later.
            if ans.dq_ids:
                note = (f"{ans.metric_id}: {', '.join(ans.dq_ids)} document known data-quality "
                        f"mechanisms affecting this metric. Any pattern here must be read "
                        f"against them before being treated as a business signal.")
                dq_notes.append(note)

    # --- INFERENCE: the conflict conclusion, which follows necessarily ------------------------
    if LADDER.index(ceiling) >= LADDER.index(INFERENCE) or plan.trust_level in ("SHOW_BOTH",
                                                                               "BLOCK"):
        if plan.trust_level in ("SHOW_BOTH", "BLOCK") and len(statements) >= 2:
            inputs = _worst([s.trust_level for s in statements])
            statements.append(Statement(
                stage=INFERENCE,
                text=(f"{len(plan.metric_ids)} independently-computed definitions of this "
                      f"concept disagree, so no single figure for it exists in this evidence "
                      f"package."),
                metric_ids=tuple(plan.metric_ids), trust_level=inputs,
                conflict_ids=plan.required_disclosures,
                confidence=PROVEN,   # follows necessarily from the computed values themselves
            ))

    # --- HYPOTHESIS / RECOMMENDATION ----------------------------------------------------------
    # Only when the question ASKED for one. Both are grounded strictly in already-documented
    # content (the conflict/DQ registers), never generated freely.
    if plan.driver_requested and LADDER.index(ceiling) >= LADDER.index(HYPOTHESIS):
        for ans in answers:
            for dq in ans.dq_ids:
                statements.append(Statement(
                    stage=HYPOTHESIS,
                    text=(f"A movement in {ans.metric_id} may have been influenced by {dq}, "
                          f"which is consistent with the documented mechanism for that finding; "
                          f"this cannot be confirmed from the exported evidence alone."),
                    metric_ids=(ans.metric_id,), trust_level=ans.trust_level, dq_ids=(dq,),
                    confidence=SUSPECTED,
                ))

    if plan.decision_requested and LADDER.index(ceiling) >= LADDER.index(RECOMMENDATION):
        if plan.trust_level == "BLOCK":
            # 2's most important gating rule: a recommendation touching a BLOCK metric must
            # recommend RESOLVING THE CONFLICT, never an operational action on a disputed figure.
            statements.append(Statement(
                stage=RECOMMENDATION,
                text=(f"Recommend resolving the definitional conflict "
                      f"({', '.join(plan.required_disclosures)}) with an owner decision on which "
                      f"definition is authoritative, before any action is taken on a specific "
                      f"figure. This is a recommendation, not a certainty."),
                metric_ids=tuple(plan.metric_ids), trust_level=plan.trust_level,
                conflict_ids=plan.required_disclosures, confidence=SUSPECTED,
            ))
        else:
            statements.append(Statement(
                stage=RECOMMENDATION,
                text=(f"Recommend reviewing {', '.join(plan.metric_ids)} together with its "
                      f"documented caveats before acting. This is a recommendation, not a "
                      f"certainty, and it follows from the calculations above rather than from "
                      f"any forecast."),
                metric_ids=tuple(plan.metric_ids), trust_level=plan.trust_level,
                confidence=SUSPECTED,
            ))

    highest = CALCULATION
    for s in statements:
        if s.rung() > LADDER.index(highest):
            highest = s.stage

    # --- gating enforcement --------------------------------------------------------------------
    if LADDER.index(highest) > LADDER.index(ceiling):
        violations.append(
            f"reasoning reached {highest} but this intent's ceiling is {ceiling} "
            f"(business_reasoning_spec.md 3)")

    for s in statements:
        if s.stage == HYPOTHESIS:
            if not any(h in s.text.lower() for h in HEDGE_PHRASES):
                violations.append(f"HYPOTHESIS lacks hedge language: {s.text[:80]}")
            if any(f in s.text.lower() for f in FACT_REGISTER_PHRASES):
                violations.append(f"HYPOTHESIS uses fact register: {s.text[:80]}")
        if s.stage == RECOMMENDATION:
            if "recommend" not in s.text.lower():
                violations.append(f"RECOMMENDATION not in recommendation register: {s.text[:80]}")

    # A HYPOTHESIS or INFERENCE may not present a cleaner trust level than its inputs.
    input_worst = _worst([s.trust_level for s in statements if s.stage == CALCULATION])
    for s in statements:
        if s.stage in (INFERENCE, HYPOTHESIS, RECOMMENDATION) and s.trust_level:
            if _SEVERITY.get(s.trust_level, 0) < _SEVERITY.get(input_worst, 0):
                violations.append(
                    f"{s.stage} claims trust {s.trust_level} but its inputs are {input_worst} "
                    f"-- worst-of-inputs violated (metric_dependency_graph.md 7)")

    return ReasoningResult(
        statements=tuple(statements), ceiling=ceiling,
        intent_ceiling=plan.reasoning_ceiling,
        ceiling_raised_for_disclosure=(ceiling != plan.reasoning_ceiling),
        highest_reached=highest,
        violations=tuple(violations), dq_annotations=tuple(dq_notes),
    )
