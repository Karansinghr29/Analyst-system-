"""
contract.py -- Phase 2. answer_contract.md as an executable checklist.

answer_contract.md 5 states its own purpose for existing in this form:

    "These restate ai_trust_policy.md 2's behavior rules **as structural contract
     requirements**, so a later implementation can validate an answer object against a
     checklist rather than re-deriving the policy from prose each time."

This module IS that checklist. It never fixes an answer -- it reports what is missing. An answer
with violations is, per answer_contract.md 1, "**incomplete**, not merely under-detailed -- the
architecture must not emit it."

Two Phase-2 scope notes, stated rather than silently skipped:
  - "Answer text" (contract 1 row 1) is populated by the Business Reasoning Engine, which is
    Phase 3. Phase 2 answers are internal analytics objects, not prose, so that field is checked
    as NOT-YET-APPLICABLE rather than as a violation.
  - "Epistemic labels" beyond CALCULATION are likewise Phase 3 (the roadmap defers "business
    reasoning beyond CALCULATION"). Phase 2 asserts the ceiling is not exceeded.
"""
from dataclasses import dataclass

from engine.result import MetricAnswer, NOT_DETERMINABLE_TEXT

# business_reasoning_spec.md's ladder, lowest to highest. Phase 2's ceiling is CALCULATION.
EPISTEMIC_LADDER = ("FACT", "CALCULATION", "OBSERVATION", "INFERENCE", "HYPOTHESIS",
                    "RECOMMENDATION")
PHASE_2_CEILING = "CALCULATION"

DEFERRED_TO_PHASE_3 = (
    "Answer text (contract 1) -- produced by the Business Reasoning Engine.",
    "Epistemic labels above CALCULATION (contract 1) -- the FACT->...->RECOMMENDATION ladder.",
)


@dataclass(frozen=True)
class ContractReport:
    metric_id: str
    violations: tuple
    checked: tuple

    @property
    def complete(self):
        return not self.violations

    def summary(self):
        if self.complete:
            return f"{self.metric_id}: answer contract COMPLETE ({len(self.checked)} checks)."
        return (f"{self.metric_id}: answer contract INCOMPLETE -- "
                f"{len(self.violations)} violation(s): " + "; ".join(self.violations))


def _cites_a_number(answer: MetricAnswer):
    """Several contract 1 rows are required only 'for every answer that cites a number'."""
    return any(r.value is not None for r in answer.results)


def validate(answer: MetricAnswer, spec=None) -> ContractReport:
    v, checked = [], []

    def check(name, ok, msg):
        checked.append(name)
        if not ok:
            v.append(msg)

    # --- contract 1: required fields ---------------------------------------------------------
    check("trust_posture", bool(answer.trust_level),
          "Trust posture missing (required for every answer).")
    check("confidence", bool(answer.confidence),
          "Confidence missing (required for every answer, contract 3).")
    check("metric_provenance", bool(answer.metric_id),
          "Metric provenance (metric_id) missing.")

    if _cites_a_number(answer):
        for r in answer.results:
            if r.value is None:
                continue
            tag = f"{answer.metric_id}/{r.definition_label}"
            check("calculation_provenance", bool(r.calculation_provenance),
                  f"{tag}: calculation provenance missing (contract 1).")
            check("evidence_citations", bool(r.citations) or bool(r.evidence_sources),
                  f"{tag}: evidence citations missing -- an uncited number is a defect "
                  f"regardless of whether it is correct "
                  f"(ai_evaluation_framework.md 1.4).")
            check("validation_status", r.validation_status in
                  ("MATCH", "DIFFERS", "PARTIAL", "UNVERIFIED", "NOT_DETERMINABLE"),
                  f"{tag}: validation_status {r.validation_status!r} is not a contract value.")
            check("as_of", bool(r.as_of),
                  f"{tag}: as-of date basis missing (contract 1 -- required for every answer "
                  f"that cites a number).")
            check("result_confidence", bool(r.confidence),
                  f"{tag}: per-definition confidence missing.")

    # contract 1: conflict/DQ disclosure required for ANY non-SAFE metric.
    if answer.trust_level != "SAFE":
        has_disclosure = bool(answer.conflict_ids or answer.dq_ids or answer.caveat
                              or answer.not_determinable_reason or answer.blocked_reason)
        check("conflict_dq_disclosure", has_disclosure,
              f"Non-SAFE metric ({answer.trust_level}) with no conflict_ids, dq_ids, caveat, or "
              f"reason -- nothing discloses WHY it is not SAFE.")

    check("follow_up_affordance", isinstance(answer.follow_up, tuple),
          "Follow-up affordance field absent (may be empty, but must exist).")

    # --- contract 5: answer-shape rules by trust level ----------------------------------------
    tl = answer.trust_level

    if tl == "SAFE":
        check("safe_shape", len(answer.results) >= 1,
              "SAFE: value field must be populated with a number/series.")
        check("safe_headline", answer.headline_permitted,
              "SAFE: a headline value must be permitted.")

    elif tl == "DISCLOSE":
        check("disclose_shape", len(answer.results) >= 1,
              "DISCLOSE: value must be populated.")
        check("disclose_caveat", bool(answer.caveat and answer.caveat.strip()),
              "DISCLOSE: caveat_text is REQUIRED and non-empty, sourced verbatim from "
              "semantic_metric_registry.csv.caveat_text (contract 5).")
        if spec is not None and answer.caveat:
            check("disclose_caveat_verbatim", answer.caveat.strip() == spec.caveat_text.strip(),
                  "DISCLOSE: caveat text was altered rather than carried verbatim "
                  "(ai_evaluation_framework.md 1.2: the caveat's content must not be dropped "
                  "or diluted).")

    elif tl == "SHOW_BOTH":
        check("show_both_shape", len(answer.results) >= 2,
              f"SHOW_BOTH: value must be structurally a list of labelled values, never a "
              f"single scalar -- got {len(answer.results)} (contract 5).")
        check("show_both_no_headline", not answer.headline_permitted and answer.headline is None,
              "SHOW_BOTH: no single headline figure may be readable off the answer.")
        labels = [r.definition_label for r in answer.results]
        check("show_both_labelled", len(set(labels)) == len(labels) and all(labels),
              f"SHOW_BOTH: every competing definition must carry a distinct label; got {labels}.")
        check("show_both_split_confidence", answer.confidence == "SPLIT",
              f"SHOW_BOTH: confidence must be SPLIT, never one blended number for the family "
              f"(contract 3); got {answer.confidence!r}.")

    elif tl == "BLOCK":
        check("block_no_headline", answer.headline is None and not answer.headline_permitted,
              "BLOCK: the headline figure must be absent or explicitly null (contract 5).")
        check("block_flagged", answer.blocked is True,
              "BLOCK: answer must be flagged blocked=True.")
        check("block_reason", bool(answer.blocked_reason),
              "BLOCK: a refusal must carry its explanation.")
        check("block_conflicts", bool(answer.conflict_ids),
              "BLOCK: conflict_ids must be disclosed -- a refusal with no named conflict is "
              "undisclosable (contract 4's worked BLOCK example names them explicitly).")
        check("block_confidence", answer.confidence == "BLOCKED",
              f"BLOCK: confidence must be BLOCKED -- 'assigning a score would itself imply a "
              f"settled number exists' (contract 3); got {answer.confidence!r}.")
        for r in answer.results:
            check("block_labelled_components", bool(r.definition_label),
                  "BLOCK: component definition values must each be separately labelled.")

    elif tl == "NOT_DETERMINABLE":
        check("nd_no_value", len(answer.results) == 0,
              f"NOT_DETERMINABLE: value field must be absent; got {len(answer.results)} "
              f"result(s) (contract 5).")
        check("nd_exact_phrase", NOT_DETERMINABLE_TEXT in answer.not_determinable_reason,
              f"NOT_DETERMINABLE: the exact phrase {NOT_DETERMINABLE_TEXT!r} must appear.")
        check("nd_specific", len(answer.not_determinable_reason) > len(NOT_DETERMINABLE_TEXT) + 20,
              "NOT_DETERMINABLE: explanation must state specifically what evidence is missing "
              "or unresolved, not a generic 'no data' (contract 5).")
        check("nd_confidence", answer.confidence == "UNVERIFIED",
              f"NOT_DETERMINABLE: confidence must be UNVERIFIED; got {answer.confidence!r}.")

    else:
        v.append(f"Unknown trust_level {tl!r}.")

    # --- Phase 2 epistemic ceiling ------------------------------------------------------------
    check("epistemic_ceiling",
          answer.epistemic_label in EPISTEMIC_LADDER and
          EPISTEMIC_LADDER.index(answer.epistemic_label) <= EPISTEMIC_LADDER.index(PHASE_2_CEILING),
          f"Epistemic label {answer.epistemic_label!r} exceeds Phase 2's ceiling "
          f"({PHASE_2_CEILING}); the ladder above it is Phase 3 (implementation_roadmap.md).")

    return ContractReport(metric_id=answer.metric_id, violations=tuple(v), checked=tuple(checked))
