"""
execution.py -- the MetricExecutor: orchestrates Trust Gate -> Calculator -> Validator ->
Answer assembly for one resolved metric_id. Corresponds to pipeline stages [5]-[9]+[11] of
ai_analytics_architecture.md 3 (Trust Check -> Conflict Check -> Analytics Plan -> Execution ->
Validation -> Answer), MINUS stages [1]-[4] (Question Understanding -- Phase 4) and [10]
(Business Reasoning -- Phase 3).

PHASE 2 CHANGE -- the gate now runs FIRST and is binding.
------------------------------------------------------
Phase 1 computed a metric and then labelled the answer. Phase 2 obeys
ai_analytics_architecture.md 2's directionality rule literally: `TrustGate.authorize()` is
called before any calculator is looked up, and its `GateDecision` determines whether a
calculator may run at all, in what mode, and whether ANY headline may be read off the result.
A NOT_DETERMINABLE verdict now short-circuits before execution rather than after it, and BLOCK
results are marked `headline_permitted=False` so `MetricAnswer.headline` returns None by
construction rather than by convention.

Phase 2 also assembles the full Answer Contract (answer_contract.md): evidence citation chain,
calculation provenance, confidence, as-of basis, follow-up affordances -- and validates the
finished object against contract.py's checklist before returning it.
"""
import inspect

from engine.semantic_registry import SemanticRegistry, MetricSpec
from engine.gate import TrustGate, MODE_SINGLE, MODE_FAMILY, MODE_INTERNAL_ONLY, MODE_REFUSE
from engine.calculators import REGISTRY, NOT_IMPLEMENTED
from engine.calculators.base import CalcOutput, NotDeterminableError
from engine.validation import ValidationIndex
from engine.validator import Validator, SanityCheckFailure
from engine.result import MetricResult, MetricAnswer, NOT_DETERMINABLE_TEXT
from engine import citation as citation_mod
from engine import confidence as confidence_mod
from engine import contract as contract_mod

# The export snapshot date, fixed for reproducibility. conflicts.md C.019 / DQ.018: any
# CURRENT_DATE-dependent metric must be reconstructed against an explicit as-of date rather
# than the machine's real clock, or the same question yields different answers on different days.
EXPORT_SNAPSHOT_DATE = "2026-08-29"


class MetricExecutor:
    def __init__(self, registry: SemanticRegistry = None, validation_index: ValidationIndex = None,
                 gate: TrustGate = None, validator: Validator = None):
        self.registry = registry or SemanticRegistry()
        self.validation = validation_index or ValidationIndex()
        self.gate = gate or TrustGate(self.registry)
        self.validator = validator or Validator(self.validation)

    # -- public entry point ---------------------------------------------------------------------

    def execute(self, metric_id, **calc_kwargs) -> MetricAnswer:
        # [5]+[6] Trust Check and Conflict Check -- BEFORE anything is computed.
        decision = self.gate.authorize(metric_id)

        if decision.verdict is None:
            return self._finish(self._unknown_metric_answer(metric_id, decision), None)

        spec = self.registry.get(metric_id)

        # ai_analytics_architecture.md 2: a metric the gate refuses is never computed for
        # user-facing output. This is the Phase 2 structural change -- the refusal precedes
        # execution rather than filtering it afterwards.
        if decision.execution_mode == MODE_REFUSE:
            return self._finish(self._not_determinable_answer(
                spec, decision,
                reason=(f"This metric's trust level is NOT_DETERMINABLE: {decision.reason} "
                        f"{NOT_DETERMINABLE_TEXT}")), spec)

        calc_fn = REGISTRY.get(metric_id)
        if calc_fn is None or calc_fn == NOT_IMPLEMENTED:
            return self._finish(self._not_determinable_answer(
                spec, decision,
                reason=(f"This metric is fully specified in the semantic layer (documented "
                        f"trust level if computable: {spec.trust_level}) but its calculation is "
                        f"not implemented in the execution engine (out of scope -- see "
                        f"metric_reconstruction.md and the Phase 1 implementation report). "
                        f"{NOT_DETERMINABLE_TEXT}")), spec)

        try:
            calc_out = self._invoke(calc_fn, spec, calc_kwargs)
        except NotDeterminableError as e:
            return self._finish(self._not_determinable_answer(
                spec, decision, reason=f"{e} {NOT_DETERMINABLE_TEXT}"), spec)

        # [8] Execution -> [9] Validation, in the mode the gate authorized.
        if calc_out.subs is not None:
            results = tuple(self._to_result(spec, label, sub)
                            for label, sub in calc_out.subs.items())
        elif (decision.execution_mode in (MODE_FAMILY, MODE_INTERNAL_ONLY)
              and len(decision.required_definitions) > 1):
            results = self._execute_family_siblings(spec, calc_out, calc_kwargs)
        else:
            results = (self._to_result(spec, spec.display_name, calc_out),)

        if decision.execution_mode in (MODE_FAMILY, MODE_INTERNAL_ONLY):
            # Binding: a family may never be narrowed to a subset before reaching the caller.
            decision.assert_definitions_complete([r.definition_label for r in results])

        blocked = decision.effective_level == "BLOCK"
        numeric_difference = (self._pairwise_diffs(results)
                              if decision.execution_mode in (MODE_FAMILY, MODE_INTERNAL_ONLY)
                              else None)

        answer = MetricAnswer(
            metric_id=metric_id, metric_name=spec.semantic_name,
            trust_level=decision.effective_level, ai_handling=spec.ai_handling,
            caveat=spec.caveat_text, conflict_ids=spec.conflict_ids, dq_ids=spec.dq_ids,
            results=results, blocked=blocked,
            blocked_reason=decision.reason if blocked else "",
            dependency_metrics=spec.dependency_metrics,
            numeric_difference=numeric_difference,
            headline_permitted=decision.headline_permitted,
            propagation_justification=decision.propagation_justification,
            trust_sources={"own": decision.own_level,
                           "dependency": decision.dependency_level,
                           "documented_floor": decision.documented_floor},
            as_of=self._as_of(spec),
            follow_up=self._follow_up(spec, decision),
        )
        return self._finish(answer, spec)

    # -- answer shapes ---------------------------------------------------------------------------

    def _unknown_metric_answer(self, metric_id, decision):
        return MetricAnswer(
            metric_id=metric_id, metric_name=metric_id, trust_level="NOT_DETERMINABLE",
            ai_handling="NOT_DETERMINABLE", caveat="", conflict_ids=(), dq_ids=(),
            not_determinable_reason=(
                f"{metric_id!r} is not a semantic metric -- no such metric_id exists in "
                f"semantic_metric_registry.csv, and the system never improvises a metric to "
                f"fill the gap (ai_analytics_architecture.md 8). {NOT_DETERMINABLE_TEXT}"),
            headline_permitted=False,
            propagation_justification=decision.propagation_justification,
        )

    def _not_determinable_answer(self, spec, decision, reason):
        return MetricAnswer(
            metric_id=spec.metric_id, metric_name=spec.semantic_name,
            trust_level="NOT_DETERMINABLE", ai_handling=spec.ai_handling,
            caveat=spec.caveat_text, conflict_ids=spec.conflict_ids, dq_ids=spec.dq_ids,
            not_determinable_reason=reason,
            dependency_metrics=spec.dependency_metrics,
            headline_permitted=False,
            propagation_justification=decision.propagation_justification,
            trust_sources={"own": decision.own_level,
                           "dependency": decision.dependency_level,
                           "documented_floor": decision.documented_floor},
            as_of=self._as_of(spec),
            follow_up=self._follow_up(spec, decision),
        )

    def _finish(self, answer: MetricAnswer, spec):
        """Attach the contract's confidence field, then validate the finished object against
        answer_contract.md's own checklist. Violations are ATTACHED, never silently repaired --
        a repaired answer would hide the defect from the evaluation framework."""
        per_def = tuple((r.definition_label, r.confidence) for r in answer.results)
        primary_verdict = None
        for r in answer.results:
            if r.validation_detail and "verdict" in r.validation_detail:
                primary_verdict = r.validation_detail["verdict"]
                break

        conf = confidence_mod.assess(answer.trust_level, primary_verdict, spec, per_def)
        answer.confidence = conf.label
        answer.confidence_basis = conf.basis

        report = contract_mod.validate(answer, spec)
        answer.contract_violations = report.violations
        return answer

    # -- execution helpers ----------------------------------------------------------------------

    def _execute_family_siblings(self, spec, own_calc_out, calc_kwargs):
        """ai_analytics_architecture.md 7 mechanism 1: a question resolving to a FAMILY must
        never be silently narrowed to one member. M.AR.001A queried alone still returns B/C/D."""
        results = []
        for sib_id in self.registry.family_members(spec.metric_id):
            if sib_id == spec.metric_id:
                results.append(self._to_result(spec, spec.display_name, own_calc_out))
                continue
            sib_spec = self.registry.get(sib_id)
            sib_fn = REGISTRY.get(sib_id)
            if sib_fn is None or sib_fn == NOT_IMPLEMENTED:
                continue
            try:
                sib_out = self._invoke(sib_fn, sib_spec, calc_kwargs)
            except NotDeterminableError:
                continue
            results.append(self._to_result(sib_spec, sib_spec.display_name, sib_out))
        return tuple(results)

    def _invoke(self, calc_fn, spec, calc_kwargs):
        """Call a calculator, auto-supplying kwargs it declares (e.g. `registry`) that the
        caller did not explicitly pass.

        A kwarg the calculator does NOT declare is refused rather than dropped. The planner only
        sends one when the question asked for that narrowing, so silently ignoring it would
        compute the estate-wide figure and present it as the answer to a question about one
        apartment -- a wider number wearing the narrower question's label.
        """
        sig = inspect.signature(calc_fn)
        kwargs = {}
        for name, value in calc_kwargs.items():
            if name in sig.parameters:
                kwargs[name] = value
            elif value not in (None, "", (), {}):
                raise NotDeterminableError(
                    f"This measure cannot be narrowed to the requested "
                    f"{name.replace('_', ' ')}: its calculation does not support that filter, "
                    f"and the unfiltered figure would answer a wider question than the one "
                    f"asked.")
        if "registry" in sig.parameters and "registry" not in kwargs:
            kwargs["registry"] = self.registry
        return calc_fn(spec, **kwargs) if kwargs else calc_fn(spec)

    def _to_result(self, spec: MetricSpec, label: str, calc_out: CalcOutput) -> MetricResult:
        # [9] Validation -- the Validator role. Sanity failures HALT (analytics_execution_spec 8);
        # they are re-raised as SanityCheckFailure rather than degraded into a returned answer.
        verdict = self.validator.validate(spec, calc_out.value, calc_out.unit,
                                          definition_label=label)

        chain = citation_mod.chain_for(spec)
        conf = confidence_mod.assess(spec.trust_level, verdict, spec)

        return MetricResult(
            metric_id=spec.metric_id, metric_name=spec.semantic_name, definition_label=label,
            value=calc_out.value, unit=calc_out.unit,
            period="all-time (no period filter applied at this layer)",
            grain=spec.grain, dimensions=spec.dimensions, date_field=spec.date_field,
            filters_applied=spec.filters, reversal_policy_applied=spec.reversal_policy,
            soft_delete_policy_applied=spec.soft_delete_policy,
            evidence_sources=calc_out.evidence_sources or chain.resolved_keys,
            calculation_provenance=calc_out.provenance or spec.definition,
            validation_status=verdict.status, validation_reference=spec.validation_reference,
            validation_detail={
                "detail": verdict.explanation,
                "reconstructed": verdict.reconstructed_value,
                "reference": verdict.reference_value,
                "absolute_difference": verdict.absolute_difference,
                "percentage_difference": verdict.percentage_difference,
                "reference_source": verdict.reference_source,
                "check_ids": verdict.check_ids,
                "verdict": verdict,
            },
            limitations=calc_out.limitations,
            confidence=conf.label, confidence_basis=conf.basis,
            citations=chain.citations, as_of=self._as_of(spec),
            sanity_checks=verdict.sanity_checks,
        )

    # -- Answer Contract field derivation --------------------------------------------------------

    def _as_of(self, spec):
        """answer_contract.md 1: 'The business date basis actually used, and -- for
        snapshot-dependent metrics -- the reconstruction/query date.'"""
        basis = (spec.date_field or "").strip() or "Not applicable (no date basis)"
        policy = (spec.historical_policy or "").lower()
        snapshot_dependent = ("current_date" in policy or "snapshot" in policy
                              or "current_date" in (spec.date_field or "").lower())
        if snapshot_dependent:
            return (f"{basis}; reconstructed as of the export snapshot date "
                    f"{EXPORT_SNAPSHOT_DATE} (fixed rather than the machine clock -- "
                    f"conflicts.md C.019 / DQ.018 reproducibility hazard).")
        return f"{basis}; coverage: {spec.historical_policy}"

    def _follow_up(self, spec, decision):
        """answer_contract.md 1: 'What clarification or drill-down the system can offer next.'
        Derived deterministically from the semantic layer -- never invented."""
        out = []
        siblings = [m for m in self.registry.family_members(spec.metric_id)
                    if m != spec.metric_id]
        if siblings:
            out.append(f"Compare the competing definitions individually: {', '.join(siblings)}.")
        for dep in spec.dependency_metrics:
            if dep in self.registry and dep != "ALL":
                out.append(f"Decompose into its documented component {dep} "
                           f"({self.registry.get(dep).semantic_name}).")
        if decision.effective_level == "BLOCK":
            out.append("Offer the closest safe alternative metric with its caveat stated, "
                       "rather than a single figure (ai_trust_policy.md 2 BLOCK behaviour).")
        if decision.required_disclosures:
            out.append(f"Explain the underlying findings: "
                       f"{', '.join(decision.required_disclosures)}.")
        return tuple(out)

    @staticmethod
    def _pairwise_diffs(results):
        diffs = {}
        numeric = [(r.definition_label, r.value) for r in results
                   if isinstance(r.value, (int, float)) and not isinstance(r.value, bool)]
        for i in range(len(numeric)):
            for j in range(i + 1, len(numeric)):
                la, va = numeric[i]
                lb, vb = numeric[j]
                diffs[f"{la} vs {lb}"] = {
                    "absolute_difference": round(abs(va - vb), 2),
                    "percentage_difference": round(abs(va - vb) / abs(vb) * 100, 2) if vb else None,
                }
        return diffs or None
