"""
decision_support.py -- Phase 5 objective 6. Assembles the structured decision-support object
from an executed plan, its answers, its reasoning, and any relevant insights.

    "Do not manufacture missing sections. For example, if profit is BLOCK because three
     incompatible definitions exist, the answer must explicitly preserve the conflict instead of
     generating a single 'profit fell by X%' statement."

Every section is populated only from content that already exists downstream of the deterministic
engine. A section with no evidence stays empty and is listed in `omitted_sections` with the
reason -- an empty section that is *explained* is information; an empty section that is silently
dropped looks like nothing was wrong.

`key_numbers` is the section where the BLOCK rule bites hardest. For a BLOCK metric it carries
every competing definition, each separately labelled, and the object's `headline_permitted`
stays False -- so a consumer that asks for "the number" gets None rather than a choice this
layer was never entitled to make.
"""
from engine.insight_models import DecisionSupport, NOT_DETERMINABLE_TEXT
from engine import business_reasoning
from engine import owner_semantics as osem


def build(plan, answers, reasoning=None, insights=(), question=""):
    ds = DecisionSupport(
        question=question or plan.question,
        trust_level=plan.trust_level,
        headline_permitted=plan.headline_permitted,
    )

    if plan.status == "NOT_DETERMINABLE":
        ds.executive_summary = NOT_DETERMINABLE_TEXT
        ds.limitations = (plan.not_determinable_reason,)
        ds.omitted_sections = {
            s: "no value was computed; the question is not answerable from the exported evidence"
            for s in ("key_numbers", "trend_comparison", "drivers", "recommended_actions")}
        return ds

    if plan.status in ("NEEDS_CLARIFICATION", "REJECTED"):
        ds.executive_summary = ("The question could not be turned into an analysis without "
                                "further input.")
        ds.limitations = tuple(plan.rejection_reasons) or (
            "A clarification is required before this can be answered.",)
        ds.omitted_sections = {s: "the analysis did not run"
                               for s in ("key_numbers", "drivers", "recommended_actions")}
        return ds

    # --- key_numbers ------------------------------------------------------------------------
    key_numbers, evidence, limitations = [], [], []
    caveats, conflicts, dq = [], [], []

    for ans in answers:
        for r in ans.results:
            if r.value is None:
                continue
            key_numbers.append({
                "label": r.definition_label,
                "value": r.value,
                "unit": r.unit,
                "metric_id": r.metric_id,
                "trust_level": ans.trust_level,
                "validation_status": r.validation_status,
                "confidence": r.confidence,
                "as_of": r.as_of,
            })
            evidence.extend(str(e) for e in r.evidence_sources)
            if r.limitations:
                limitations.append(f"{r.metric_id}: {r.limitations}")
        if ans.caveat:
            caveats.append(f"{ans.metric_id}: {ans.caveat}")
        conflicts.extend(ans.conflict_ids)
        dq.extend(ans.dq_ids)

    ds.key_numbers = tuple(key_numbers)

    # --- executive_summary ---------------------------------------------------------------------
    # For a conflicted metric the summary states the CONFLICT, never a synthesised figure.
    if plan.trust_level == "BLOCK":
        ds.executive_summary = (
            f"No single figure for this question can be stated: {len(key_numbers)} competing "
            f"definitions exist and they disagree. The conflict is "
            f"{', '.join(sorted(set(conflicts))) or 'documented in conflicts.md'}. Each "
            f"definition's value is listed separately below; selecting between them is an owner "
            f"decision, not an analytical one.")
    elif plan.trust_level == "SHOW_BOTH":
        ds.executive_summary = (
            f"{len(key_numbers)} competing definitions of this measure exist and are presented "
            f"separately. They are not interchangeable and must not be averaged or merged.")
    elif key_numbers:
        first = key_numbers[0]
        ds.executive_summary = (
            f"{first['label']}: {first['value']} {first['unit']}".strip()
            + f" ({first['metric_id']}, {plan.trust_level}, validation {first['validation_status']})")
    else:
        ds.omitted_sections["executive_summary"] = "no value was computed"

    # --- trend / comparison ----------------------------------------------------------------------
    if plan.comparison is not None and plan.comparison.valid:
        ds.trend_comparison = (
            f"current period {plan.comparison.current.period_label}; "
            f"baseline {plan.comparison.baseline.period_label}",)
    elif plan.comparison is not None:
        ds.omitted_sections["trend_comparison"] = plan.comparison.reason
    else:
        ds.omitted_sections["trend_comparison"] = (
            "the question did not request a comparison, and none was manufactured")

    # --- drivers ------------------------------------------------------------------------------
    if reasoning is not None:
        drivers = tuple(s.text for s in reasoning.statements
                        if s.stage in (business_reasoning.INFERENCE,
                                       business_reasoning.HYPOTHESIS))
        ds.drivers = drivers
        if not drivers:
            ds.omitted_sections["drivers"] = (
                "no driver analysis was requested, and the reasoning ceiling for this intent "
                f"({reasoning.intent_ceiling}) does not permit one unsolicited "
                "(business_reasoning_spec.md 3)")
    else:
        ds.omitted_sections["drivers"] = "no reasoning was produced for this question"

    # --- risks / DQ / conflicts ------------------------------------------------------------------
    ds.data_quality_warnings = tuple(sorted(set(dq)))
    if not ds.data_quality_warnings:
        ds.omitted_sections["data_quality_warnings"] = (
            "no data-quality finding attaches to the metrics used")

    ds.definition_conflicts = tuple(sorted(set(conflicts)))
    if not ds.definition_conflicts:
        ds.omitted_sections["definition_conflicts"] = (
            "no competing definition attaches to the metrics used")

    relevant = tuple(i for i in insights
                     if set(i.trigger_metric_ids) & set(plan.metric_ids))
    ds.risks = tuple(
        f"[{i.insight_id}] {i.observation}" for i in relevant)
    if not ds.risks:
        ds.omitted_sections["risks"] = (
            "no proactive insight currently attaches to the metrics used")

    # --- recommended_actions -----------------------------------------------------------------------
    # Only present when the question asked for one, or when a conflict blocks a decision. A
    # recommendation is never volunteered for a plain lookup (business_reasoning_spec.md 3).
    recs = []
    if reasoning is not None:
        recs = [s.text for s in reasoning.statements
                if s.stage == business_reasoning.RECOMMENDATION]
    if not recs and plan.trust_level == "BLOCK":
        # The SAME sentence the Data Quality page and Owner Home say about a definition conflict,
        # from engine/owner_semantics.py. Written here separately, it named the conflict register
        # mid-sentence and phrased the ask differently from every other surface -- so an owner who
        # read the finding on one page and the answer on another was told two things.
        recs = [osem.DQ_KINDS[osem.KIND_DEFINITION_CONFLICT]["owner_action"]]
    ds.recommended_actions = tuple(recs)
    if not recs:
        ds.omitted_sections["recommended_actions"] = (
            "the question did not request a recommendation; none is volunteered "
            "(business_reasoning_spec.md 3)")

    # --- evidence / confidence / limitations ---------------------------------------------------------
    ds.evidence = tuple(dict.fromkeys(evidence))
    ds.limitations = tuple(limitations) + tuple(caveats)
    if plan.time_note:
        ds.limitations = ds.limitations + (plan.time_note,)
    ds.confidence = answers[0].confidence if answers else ""

    if not ds.evidence:
        ds.omitted_sections["evidence"] = "no evidence sources were recorded"
    if not ds.limitations:
        ds.omitted_sections["limitations"] = "no limitation attaches to the metrics used"

    return ds


def render(ds: DecisionSupport):
    """Plain-text rendering of the decision-support object. Sections that were omitted are
    printed WITH their reason, so a reader can tell 'nothing to report' from 'not computed'."""
    lines = [f"QUESTION: {ds.question}", f"TRUST: {ds.trust_level}"]

    if ds.executive_summary:
        lines.append(f"EXECUTIVE SUMMARY: {ds.executive_summary}")
    for kn in ds.key_numbers:
        lines.append(f"KEY NUMBER [{kn['metric_id']} / {kn['label']}]: {kn['value']} "
                     f"{kn['unit']}".rstrip()
                     + f" (trust {kn['trust_level']}, validation {kn['validation_status']}, "
                       f"confidence {kn['confidence']})")
    for t in ds.trend_comparison:
        lines.append(f"TREND/COMPARISON: {t}")
    for d in ds.drivers:
        lines.append(f"DRIVER: {d}")
    for r in ds.risks:
        lines.append(f"RISK: {r}")
    for w in ds.data_quality_warnings:
        lines.append(f"DATA-QUALITY WARNING: {w}")
    for c in ds.definition_conflicts:
        lines.append(f"DEFINITION CONFLICT: {c}")
    for a in ds.recommended_actions:
        lines.append(f"RECOMMENDED ACTION: {a}")
    if ds.evidence:
        lines.append(f"EVIDENCE: {', '.join(ds.evidence[:10])}")
    if ds.confidence:
        lines.append(f"CONFIDENCE: {ds.confidence}")
    for l in ds.limitations:
        lines.append(f"LIMITATION: {l}")
    for section, reason in sorted(ds.omitted_sections.items()):
        lines.append(f"OMITTED [{section}]: {reason}")
    return "\n".join(lines)
