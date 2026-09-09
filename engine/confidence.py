"""
confidence.py -- Phase 2. answer_contract.md 3's confidence model, encoded exactly.

The governing constraint from 3: "Confidence is **not a single blended score** -- per
ai_trust_policy.md 2, it varies by trust level and must never be flattened into one number that
hides a SHOW_BOTH/BLOCK situation."

The table is reproduced verbatim below and is the ONLY source of a confidence label. Nothing
here computes a score, a percentage, or a blend.

  | Trust level                          | Confidence label                                    |
  |--------------------------------------|-----------------------------------------------------|
  | SAFE, validation_status = MATCH      | HIGH                                                |
  | SAFE, no independent re-validation   | HIGH (by construction, not independently re-validated) |
  | DISCLOSE                             | MEDIUM, with the specific DQ/conflict ID(s) named   |
  | SHOW_BOTH                            | SPLIT -- each definition reports its own separately |
  | BLOCK                                | BLOCKED                                             |
  | NOT_DETERMINABLE                     | UNVERIFIED                                          |

**One documented gap.** The table has no row for `SAFE` + `validation_status = DIFFERS`, which
one metric in the registry actually is (`M.REV.002`, whose REV.02 check DIFFERS on row count
while every overlapping value matches exactly). Rather than silently promoting it to HIGH or
silently demoting it to MEDIUM, this module emits the distinct label
`HIGH (documented DIFFERS: <mechanism>)` and records the gap in UNCOVERED_COMBINATIONS so the
Phase 2 report can surface it as a specification clarification rather than an implementation
decision made quietly. analytics_execution_spec.md 8 requires only that such a result "carry the
same documented explanation, not present as if freshly validated" -- which this label does.
"""
from dataclasses import dataclass

HIGH = "HIGH"
HIGH_BY_CONSTRUCTION = "HIGH (by construction, not independently re-validated)"
MEDIUM = "MEDIUM"
SPLIT = "SPLIT"
BLOCKED = "BLOCKED"
UNVERIFIED = "UNVERIFIED"

# Hypothesis/recommendation-stage vocabulary (answer_contract.md 3, second half) -- reused from
# data_quality_report.md's root_cause_confidence column. Never a numeric percentage: "no
# statistical calibration of these labels exists in the evidence." Phase 3 consumes these; they
# are defined here so the vocabulary lives in one place.
PROVEN = "PROVEN"
SUSPECTED = "SUSPECTED"

UNCOVERED_COMBINATIONS = (
    ("SAFE", "DIFFERS",
     "answer_contract.md 3's table has no row for a SAFE metric whose validation check is "
     "DIFFERS. Implemented as 'HIGH (documented DIFFERS: ...)' -- HIGH because the trust level "
     "is SAFE and every overlapping VALUE matched exactly, qualified because "
     "analytics_execution_spec.md 8 forbids presenting it as freshly validated. Affects "
     "M.REV.002 (REV.02). Flagged for specification clarification, not resolved unilaterally."),
)


@dataclass(frozen=True)
class Confidence:
    label: str
    basis: str
    per_definition: tuple = ()   # populated only for SPLIT

    def __str__(self):
        return self.label


def assess(trust_level, validation_verdict, spec=None, per_definition=()):
    """Return the Confidence for one answer. `validation_verdict` is a
    validator.ValidationVerdict (or None when nothing was computed)."""

    if trust_level == "BLOCK":
        return Confidence(
            BLOCKED,
            "answer_contract.md 3: no numeric confidence is ever emitted alongside a refused "
            "answer -- assigning a score would itself imply a settled number exists.")

    if trust_level == "NOT_DETERMINABLE":
        return Confidence(
            UNVERIFIED,
            "No reference exists to confirm a reconstruction of this metric.")

    if trust_level == "SHOW_BOTH":
        return Confidence(
            SPLIT,
            "answer_contract.md 3: each competing definition reports its own confidence "
            "separately. Never one number for the family.",
            per_definition=tuple(per_definition))

    if trust_level == "DISCLOSE":
        ids = []
        if spec is not None:
            ids = list(spec.conflict_ids) + list(spec.dq_ids)
        named = ", ".join(ids) if ids else "no specific id recorded on this metric"
        return Confidence(
            MEDIUM,
            f"Usable, but a known limitation attaches ({named}).")

    # SAFE
    status = validation_verdict.status if validation_verdict is not None else "UNVERIFIED"
    if status == "MATCH":
        refs = ", ".join(validation_verdict.check_ids)
        return Confidence(
            HIGH,
            f"Reconstructed and independently confirmed against an exported reference "
            f"({refs}, validation_summary.csv).")
    if status == "DIFFERS":
        return Confidence(
            f"{HIGH} (documented DIFFERS: {validation_verdict.explanation[:160]})",
            "answer_contract.md 3 has no row for SAFE+DIFFERS; see "
            "confidence.UNCOVERED_COMBINATIONS. The documented mechanism is carried forward "
            "verbatim rather than the result being presented as freshly validated "
            "(analytics_execution_spec.md 8).")
    if status == "PARTIAL":
        return Confidence(
            f"{HIGH} (partially re-validated)",
            f"Some mapped checks confirmed this metric and some did not run: "
            f"{validation_verdict.explanation[:160]}")
    return Confidence(
        HIGH_BY_CONSTRUCTION,
        "Logic is fully specified from source and structurally sound, but no live re-check "
        "occurred in this project's validation pass (answer_contract.md 3).")
