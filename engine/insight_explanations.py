"""
insight_explanations.py -- Phase 5. Builds each insight's reasoning ladder and its Part A
trust posture, from already-documented content only.

insight_generation_spec.md 3: a candidate is produced "by running the FACT->CALCULATION->
OBSERVATION->(INFERENCE->HYPOTHESIS if warranted) ladder against the triggering metric, exactly
as if a user had asked about it."

Every string this module produces is assembled from fields that already exist in the evidence
layer -- the DQ registry's `issue`/`root_cause`/`affected_amount`, the semantic registry's
`caveat_text`, conflicts.md's ids. Nothing is composed from the model's or the author's own
judgement about what the business should conclude.

Two gating rules are enforced here rather than left to the caller:

  * A HYPOTHESIS is emitted ONLY where data_quality_registry.csv's own `root_cause_confidence`
    column says SUSPECTED. Where it says PROVEN, the mechanism is not a hypothesis at all, and
    labelling it as one would understate evidence just as surely as the reverse overstates it.
  * A RECOMMENDATION touching a BLOCK metric recommends RESOLVING THE CONFLICT, never an
    operational action on a disputed figure (business_reasoning_spec.md 2).
"""
import re

from engine.insight_models import NOT_DETERMINABLE_TEXT

# business_insight_framework.md Part A's trust postures, transcribed. This is a lookup into
# already-written specification content, not a new trust assignment: the authoritative trust
# level still comes from the Trust Gate at runtime. This table only supplies Part A's
# *narrative* qualification for an insight class.
PART_A_POSTURE = {
    "M.REV.001": "SAFE -- direct trend analysis supported, 53-57 months of coverage.",
    "M.REV.002": "SAFE -- direct trend analysis supported.",
    "M.COL.001": "DISCLOSE -- application-level and ledger-derived trends must be labelled "
                 "separately, never merged into one line.",
    "M.COL.003": "DISCLOSE -- ledger-derived; never merged with the application-level series.",
    "M.AR.001A": "BLOCK/SHOW_BOTH -- a receivables trend can only be built per-definition.",
    "M.AR.001D": "BLOCK -- frozen legacy table; never a live dues figure.",
    "M.CASH.001": "SAFE (by construction, not independently re-validated -- flag accordingly).",
    "M.DEP.001": "SAFE for the held balance.",
    "M.RISK.004": "DISCLOSE for phantom-deposit risk.",
    "M.EXP.001": "SAFE for the total.",
    "M.EXP.002": "DISCLOSE for the category breakdown (electricity-bucket gap).",
    "M.PNL.001": "SAFE (ledger-only definition).",
    "M.OWN.002": "SHOW_BOTH for the owner-rent-in-profit question.",
    "M.PROFIT.001": "BLOCK -- no profitability trend or comparison may be stated as one number; "
                    "must be run per-definition or refused.",
    "M.OCC.001": "SHOW_BOTH -- every occupancy insight must name its definition.",
    "M.OCC.004": "NOT_DETERMINABLE -- fully specified, unvalidated; any utilization insight at "
                 "bed grain must say so.",
    "M.MAINT.001": "SAFE, 20-month coverage -- trend supported, no YoY.",
    "M.MAINT.002": "SAFE (both linkage paths proven to agree).",
    "M.EB.001": "DISCLOSE -- 2-5 month coverage, no trend/YoY insight should be generated.",
    "M.EB.002": "DISCLOSE -- same coverage and billing-format caveat.",
    "M.RISK.005": "DISCLOSE -- no dedup mechanism exists; proactively surfaceable.",
    "M.RISK.006": "DISCLOSE -- demonstrates detected issues are not auto-remediated.",
    "M.RISK.007": "DISCLOSE -- 187-214 pairs depending on reconstruction method.",
    "M.RISK.008": "DISCLOSE -- source-vs-ledger gaps.",
    "M.RISK.009": "SAFE (the meta-metric itself); the underlying issues range across all trust "
                  "levels.",
}

# Domains where business_insight_framework.md Part A / question_understanding_spec.md 5.3
# forbid a trend framing outright.
NO_TREND_METRICS = ("M.MAINT.001", "M.MAINT.002", "M.EB.001", "M.EB.002")

_MONEY = re.compile(r"(?:Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)")
_COUNT = re.compile(r"^\s*([\d,]+)\s+of\b", re.I)


def parse_amount(text):
    """Pull a rupee figure out of the DQ registry's prose `affected_amount`. Returns None when
    the column states no amount -- and the registry sometimes says so in exactly these words
    ('Not determinable from exported evidence.'), which must stay None rather than becoming 0."""
    if not text:
        return None
    if NOT_DETERMINABLE_TEXT.lower() in text.lower():
        return None
    if text.strip().upper().startswith("N/A"):
        return None
    m = _MONEY.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_count(text):
    if not text:
        return None
    m = _COUNT.match(text.strip())
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def confidence_from_dq(root_cause_confidence):
    """data_quality_report.md's own vocabulary -- PROVEN / SUSPECTED, never a numeric scale
    (answer_contract.md 3: 'no statistical calibration of these labels exists in the
    evidence'). The column often carries both, qualified per clause; the leading token governs."""
    text = (root_cause_confidence or "").strip()
    if text.upper().startswith("PROVEN"):
        return "PROVEN"
    if text.upper().startswith("SUSPECTED"):
        return "SUSPECTED"
    return "SUSPECTED" if "suspected" in text.lower() else "PROVEN" if text else ""


def build_dq_ladder(dq_row, metric_ids, trust_level):
    """The ladder for a DQ-severity-triggered insight. Every rung quotes the registry."""
    issue = (dq_row.get("issue") or "").strip()
    area = (dq_row.get("business_area") or "").strip()
    rows = (dq_row.get("affected_rows") or "").strip()
    amount = (dq_row.get("affected_amount") or "").strip()
    root = (dq_row.get("root_cause") or "").strip()
    conf = confidence_from_dq(dq_row.get("root_cause_confidence"))
    dq_id = dq_row.get("dq_id", "")
    severity = dq_row.get("severity", "")

    fact = f"{dq_id} ({severity}, {area}): {issue}"

    calc_bits = []
    if rows and rows.upper() not in ("N/A", ""):
        calc_bits.append(f"affected rows: {rows}")
    if amount and amount.upper() not in ("N/A", ""):
        calc_bits.append(f"affected amount: {amount}")
    calculation = "; ".join(calc_bits) if calc_bits else (
        f"Scope is recorded qualitatively in data_quality_registry.csv; no numeric extent is "
        f"stated for {dq_id}.")

    # OBSERVATION: the "this is a standing pattern, not a one-off" framing insight_generation_
    # spec.md 3 requires. Grounded in the registry's own status column.
    status = (dq_row.get("status") or "").strip()
    observation = (
        f"This is a standing, currently-recorded condition (status: {status or 'MEASURED'}) "
        f"affecting {area or 'the business'}, not a one-off reading. It is surfaced without "
        f"being asked because data_quality_report.md classifies it {severity} "
        f"(insight_generation_spec.md 2 condition 1).")

    inference = ""
    metrics_affected = (dq_row.get("metrics_affected") or "").strip()
    if metrics_affected:
        inference = (f"Any figure drawn from {metrics_affected} inherits this condition, so the "
                     f"finding constrains those answers rather than standing alone.")

    # HYPOTHESIS only where the registry itself says SUSPECTED.
    hypothesis = ""
    if conf == "SUSPECTED" and root:
        hypothesis = (f"The mechanism is consistent with: {root[:400]} This is evidence-"
                      f"consistent and not confirmed by an exported query definition.")

    return {
        "fact": fact, "calculation": calculation, "observation": observation,
        "inference": inference, "hypothesis": hypothesis,
        "confidence": conf,
    }


def build_conflict_ladder(concept_label, metric_ids, definitions, spread_text, conflict_ids):
    """insight_generation_spec.md 5: 'A BLOCK metric may generate an insight about the CONFLICT
    itself ... but never an insight asserting one of the competing figures as the business's
    actual receivables position.' The ladder below therefore never names a preferred value."""
    fact = (f"{len(definitions)} competing definitions of {concept_label} exist in this system "
            f"({', '.join(metric_ids)}).")
    calculation = "; ".join(f"{label}: {value}" for label, value in definitions)
    observation = (f"The definitions do not agree{(' -- ' + spread_text) if spread_text else ''}. "
                   f"No single figure for {concept_label} exists in this evidence package.")
    inference = (f"Any decision that depends on a single {concept_label} figure is blocked until "
                 f"an owner decision selects an authoritative definition "
                 f"({', '.join(conflict_ids) if conflict_ids else 'see conflicts.md'}).")
    recommendation = (f"Recommend an owner decision on which definition of {concept_label} is "
                      f"authoritative. This is a recommendation, not a certainty, and no "
                      f"operational action should be taken on any one of the competing figures "
                      f"until that decision is made.")
    return {"fact": fact, "calculation": calculation, "observation": observation,
            "inference": inference, "hypothesis": "", "recommendation": recommendation}


def build_risk_boundary_ladder(metric_id, semantic_name, value, unit, caveat, validation_status):
    """insight_generation_spec.md 2 condition 4: 'a newly-computed value crosses a documented
    risk boundary ... These are re-derivable facts, not predictions.' The boundary is the
    diagnostic's own definition -- a non-empty result set IS the boundary crossing, so no
    threshold is invented."""
    fact = f"{metric_id} ({semantic_name}) currently returns a non-empty result set."
    calculation = f"{semantic_name}: {value} {unit}".strip()
    observation = (
        f"The documented risk condition behind {metric_id} is currently true: its diagnostic "
        f"returns rows now, which insight_generation_spec.md 2 condition 4 treats as a "
        f"re-derivable fact rather than a prediction. Validation status: {validation_status}.")
    inference = ""
    if caveat:
        inference = f"The finding carries its documented caveat: {caveat}"
    return {"fact": fact, "calculation": calculation, "observation": observation,
            "inference": inference, "hypothesis": "", "recommendation": ""}


def part_a_posture(metric_ids):
    notes = [PART_A_POSTURE[m] for m in metric_ids if m in PART_A_POSTURE]
    return " ".join(notes)


def trend_permitted(metric_ids):
    """business_insight_framework.md Part A / question_understanding_spec.md 5.3."""
    return not any(m in NO_TREND_METRICS for m in metric_ids)
