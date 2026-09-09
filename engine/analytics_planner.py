"""
analytics_planner.py -- Phase 3, pipeline stage [7]. analytics_execution_spec.md 2.

Turns an UnderstoodQuestion into a machine-readable AnalyticsPlan that Phase 2's MetricExecutor
can consume directly. Selects one of the 8 documented plan types, validates the plan, and
attaches the Trust Gate's verdict.

**Trust is delegated, never recomputed.** Every trust field on the plan is copied verbatim from
`engine.gate.TrustGate.authorize()`. This module contains no trust logic of its own -- per
ai_agent_roles.md 3, "The Trust Gatekeeper's verdict is binding on every downstream role. No
later role may reinterpret or soften a BLOCK verdict."

analytics_execution_spec.md's own precondition, which fixes the BLOCK behaviour here:
    "For BLOCK metrics, the Analytics Plan is constrained to the 'explain-the-conflict' plan
     (2.6) -- the metric's raw value may still be computed **internally** (so the AI can, e.g.,
     state the size of the disagreement between competing definitions), but **never** assembled
     into a 'the answer is X' plan."
So a BLOCK plan is still executable; what it may never do is carry a headline.
"""
from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine import concept_map
from engine import dimension_resolution as dimres
from engine import time_resolution as timeres
from engine.question_understanding import QuestionUnderstander, UnderstoodQuestion
from engine.intent_models import (
    AnalyticsPlan, ExecutionCall, ClarificationRequest,
    LOOKUP, FILTERED_LOOKUP, TREND, COMPARISON, ANOMALY, DRIVER, RISK_SCAN, RECOMMENDATION, META,
    PLAN_SINGLE_VALUE, PLAN_GROUPED, PLAN_PERIOD_COMPARISON, PLAN_TREND, PLAN_ANOMALY,
    PLAN_DRIVER, PLAN_EXPLAIN_CONFLICT, PLAN_RISK_COMPOSITE, PLAN_NONE,
    READY, BLOCKED, NEEDS_CLARIFICATION, NOT_DETERMINABLE, REJECTED,
    NOT_DETERMINABLE_TEXT, INTENT_REASONING_CEILING, validate_plan_schema,
)

# question_understanding_spec.md 6.1 "Where are we losing money?" / "Who are our risky tenants?"
# -- risk-scan composites draw on several metrics, each retaining its OWN trust label, never
# blended into one score (analytics_execution_spec.md 2.8: "no composite risk-scoring metric
# exists in the registry -- inventing one at execution time would violate the 'no unsupported
# metric' hallucination-prevention rule").
RISK_COMPOSITE_METRICS = ("M.RISK.002", "M.RISK.003", "M.RISK.004", "M.RISK.005",
                          "M.RISK.006", "M.RISK.007", "M.RISK.008")


def _conflict_first_reason(level, u, period_reason):
    """Lead with the conflict, keep the period limitation as the secondary fact.

    Both are true and the owner needs both, but only one of them is actionable: a period gap
    is a property of this export, while conflicting definitions are a business decision only
    the owner can settle. Neither is dropped, and no figure is offered for either.
    """
    subject = ""
    if u.metric is not None:
        subject = (getattr(u.metric, "concept", "") or "").replace("_", " ")
        subject = subject.replace("explicit:", "").strip()
    subject = subject or "this measure"

    if level == "BLOCK":
        lead = (f"The available definitions of {subject} disagree, so no single figure for it "
                f"can be reported for the period you asked about. Choosing one definition is a "
                f"business decision, and this system will not make it without evidence.")
    else:
        lead = (f"More than one evidence-backed definition of {subject} exists and they give "
                f"different answers, so no single figure can be reported for the period you "
                f"asked about. None of them is selected here.")

    period = (period_reason or "").strip()
    if period:
        return f"{lead} Separately: {period}"
    return f"{lead} {NOT_DETERMINABLE_TEXT}"


# Postures that survive a terminal refusal. A conflict between definitions is a finding in its
# own right; it does not stop being one because the period asked for is also unavailable.
_CONFLICT_POSTURES = ("BLOCK", "SHOW_BOTH")


def _terminal_trust(status, decision):
    level = decision.effective_level if decision else ""
    if status == NOT_DETERMINABLE and level not in _CONFLICT_POSTURES:
        return "NOT_DETERMINABLE"
    return level


class AnalyticsPlanner:
    def __init__(self, registry: SemanticRegistry = None, gate: TrustGate = None,
                 understander: QuestionUnderstander = None):
        self.registry = registry or SemanticRegistry()
        self.gate = gate or TrustGate(self.registry)
        self.understander = understander or QuestionUnderstander(self.registry)

    # -- public entry points ---------------------------------------------------------------------

    def plan(self, question, concept_name=None, metric_id=None) -> AnalyticsPlan:
        understood = self.understander.understand(question, concept_name=concept_name,
                                                  metric_id=metric_id)
        return self.plan_from(understood)

    def plan_from(self, u: UnderstoodQuestion) -> AnalyticsPlan:
        prov = list(u.provenance)

        # Stages [1]-[4] may terminate the pipeline before planning begins. Both outcomes are
        # correct behaviour, not failures (question_understanding_spec.md 1).
        if u.clarification is not None:
            prov.append("[7] no plan built: resolution requires clarification first "
                        "(question_understanding_spec.md 6 -- the pipeline does not execute "
                        "speculatively against multiple candidate resolutions)")
            return self._terminal(u, NEEDS_CLARIFICATION, prov, clarification=u.clarification)

        if u.not_determinable_reason:
            # A stage [1]-[4] limitation ends the pipeline here. Until now that happened with
            # the Trust Gate never consulted, so a metric whose definitions CONFLICT was
            # reported purely as a period problem: "What was profit last month?" answered "no
            # monthly series" and never disclosed that profit is BLOCK. The owner was told the
            # lesser of two reasons, and the one they could act on was the one withheld.
            #
            # Precedence: a trust conflict outranks a period-availability limitation. The gate
            # is not weakened -- it is consulted where it previously was not, and its verdict is
            # taken verbatim. No execution is planned and no figure is produced, so an all-time
            # value can never stand in for the month that was asked about.
            decision = None
            if u.metric is not None and u.metric.metric_ids:
                head = u.metric.metric_ids[0]
                if head in self.registry:
                    decision = self.gate.authorize(head)

            reason = u.not_determinable_reason
            if decision is not None and decision.effective_level in ("BLOCK", "SHOW_BOTH"):
                prov.append(f"[7] trust conflict outranks the period limitation: gate says "
                            f"{decision.effective_level}; conflict disclosed first")
                reason = _conflict_first_reason(decision.effective_level, u, reason)
            else:
                prov.append("[7] no plan built: no metric resolved")

            return self._terminal(u, NOT_DETERMINABLE, prov,
                                  not_determinable_reason=reason,
                                  decision=decision)

        spec = self.registry.get(u.metric.metric_ids[0])

        # --- [3] grain validation, delegated to the Phase 1 resolver ---------------------------
        resolved_dims, dim_problems, degenerate_reason = dimres.resolve_for_question(
            spec, u.dimension_request)

        if degenerate_reason:
            # 4.2: not a generic NOT_DETERMINABLE -- the specific "only 1 property exists"
            # statement, caught at dimension resolution before Execution.
            prov.append("[3] degenerate-dimension guard fired "
                        "(question_understanding_spec.md 4.2)")
            return self._terminal(
                u, NOT_DETERMINABLE, prov,
                not_determinable_reason=f"{degenerate_reason} {NOT_DETERMINABLE_TEXT}")

        if dim_problems:
            prov.append(f"[3] dimension rejected: {dim_problems}")
            return self._terminal(u, REJECTED, prov, rejection_reasons=dim_problems)

        # An apartment that does not exist is a fact, not an ambiguity. Apartment codes ARE in
        # the export, so there is nothing for the owner to disambiguate: they named one
        # precisely and it is not there. Asking them to be more specific would be asking them
        # to fix a problem they do not have.
        if "apartment_id" in u.dimension_request.unresolved_entities:
            missing = dimres.unknown_apartment_token(u.question)
            if missing:
                prov.append(f"[3] named apartment {missing!r} is not in the exported records")
                return self._terminal(
                    u, NOT_DETERMINABLE, prov,
                    not_determinable_reason=(
                        f"There is no apartment {missing} in your records, so there is nothing "
                        f"to report for it. {NOT_DETERMINABLE_TEXT}"))

        if u.dimension_request.unresolved_entities:
            # 4.3: 27 PII columns are excluded from the export, so a named tenant generally
            # cannot be identified. Never a best-guess match.
            prov.append("[3] referential ambiguity: entity not resolvable from non-PII fields "
                        "(question_understanding_spec.md 4.3)")
            return self._terminal(u, NEEDS_CLARIFICATION, prov, clarification=ClarificationRequest(
                kind="referential",
                question=("Which specific entity do you mean? Please give an identifier "
                          "present in the exported data."),
                options=tuple(f"needs an explicit {e}"
                              for e in u.dimension_request.unresolved_entities),
                reason=("data_inventory.md: 27 PII columns are excluded from the export, so an "
                        "entity referred to by name cannot be uniquely identified from the "
                        "exported evidence. Guessing would risk attributing information to the "
                        "wrong tenant -- a real-world consequence, not merely an analytical "
                        "inconvenience (question_understanding_spec.md 4.3)."),
            ))

        # --- [4] time guards --------------------------------------------------------------------
        # A family whose members carry different time semantics is narrowed to the members that
        # can actually answer the requested period -- and the exclusion is DISCLOSED, never
        # silent (question_understanding_spec.md 5.1 step 4).
        excluded_by_time = ()
        if u.time_by_metric:
            answerable = tuple(m for m in u.metric.metric_ids
                               if u.time_by_metric[m].within_coverage)
            excluded_by_time = tuple(m for m in u.metric.metric_ids
                                     if not u.time_by_metric[m].within_coverage)
            if excluded_by_time and answerable:
                prov.append(f"[4] {list(excluded_by_time)} cannot answer the requested period "
                            f"and are excluded WITH disclosure: {u.time_note[:200]}")

        if u.time is not None and not u.time.within_coverage and not (
                u.time_by_metric and any(t.within_coverage for t in u.time_by_metric.values())):
            prov.append("[4] coverage boundary enforced (question_understanding_spec.md "
                        "5.1 step 3 / step 4)")
            return self._terminal(
                u, NOT_DETERMINABLE, prov,
                not_determinable_reason=f"{u.time.coverage_note} {NOT_DETERMINABLE_TEXT}")

        if u.time is not None and not u.time.yoy_permitted:
            prov.append("[4] YoY/trend guard fired (question_understanding_spec.md 5.3)")
            return self._terminal(
                u, NOT_DETERMINABLE, prov,
                not_determinable_reason=(
                    f"{u.time.yoy_note} Documented coverage is "
                    f"{u.time.coverage_start} to {u.time.coverage_end}. "
                    f"{NOT_DETERMINABLE_TEXT}"))

        # --- [5]/[6] Trust Check + Conflict Check -- DELEGATED to the Phase 2 gate -------------
        decision = self.gate.authorize(u.metric.metric_ids[0])
        prov.append(f"[5][6] trust delegated to engine.gate.TrustGate: "
                    f"{decision.effective_level} (mode={decision.execution_mode}, "
                    f"headline_permitted={decision.headline_permitted}). "
                    f"{decision.propagation_justification[:160]}")

        # A family must be planned as a whole. The gate already knows the family; use ITS list
        # rather than the concept map's, so the two can never drift.
        metric_ids = tuple(decision.required_definitions) or u.metric.metric_ids

        # --- structural guards (Phase 3 requirement 5) ------------------------------------------
        rejections = self._structural_guards(u, metric_ids, decision)
        if rejections:
            prov.append(f"[7] plan rejected by structural guards: {len(rejections)} reason(s)")
            return self._terminal(u, REJECTED, prov, rejection_reasons=tuple(rejections),
                                  decision=decision, metric_ids=metric_ids)

        # --- current-state metrics may not be read back to a past period ---------------------
        # A metric whose registry historical_policy declares CURRENT STATE ONLY holds a value
        # with no effective date. Answering "what was it last year?" with it would present
        # today's figure as a historical one, and nothing in the evidence would contradict the
        # claim. Read from the registry, so the rule belongs to whichever metrics declare it.
        if (u.time is not None and getattr(u.time, "period_label", "") not in ("", "all-time")
                and metric_ids):
            policy = (self.registry.get(metric_ids[0]).historical_policy or "").strip()
            if policy.upper().startswith("CURRENT STATE ONLY"):
                subject = (self.registry.get(metric_ids[0]).semantic_name or "this measure")
                label = u.time.period_label
                prov.append(f"[7] period refused: {metric_ids[0]} is declared current-state "
                            f"only; no effective date exists to read it back to {label}")
                return self._terminal(
                    u, NOT_DETERMINABLE, prov,
                    not_determinable_reason=(
                        f"{subject} is recorded as it stands now, with no date attached to say "
                        f"when it took effect and no record of what it was changed from. I can "
                        f"tell you the position today, but not the position in {label}. "
                        f"{NOT_DETERMINABLE_TEXT}"),
                    decision=decision, metric_ids=metric_ids)

        # --- period-aware metric enforcement (defense in depth) -----------------------------
        # Understanding should already have redirected to a monthly series. If an all-time
        # total still arrives here with a single-month period, refuse silent substitution.
        if (u.time is not None and timeres.is_single_month_period(u.time)
                and metric_ids):
            mid0 = metric_ids[0]
            sname = (self.registry.get(mid0).semantic_name or "").lower()
            is_series = any(t in sname for t in ("month", "monthly", "p&l", "pnl", "by day"))
            if not is_series:
                monthly = ""
                cname = u.metric.concept if u.metric else ""
                if cname and cname.startswith("explicit:"):
                    cname = ""
                for alt in concept_map.period_series_candidates(
                        concept_name=cname or None, metric_ids=metric_ids):
                    if alt == mid0 or alt not in self.registry:
                        continue
                    aname = (self.registry.get(alt).semantic_name or "").lower()
                    if any(t in aname for t in ("month", "monthly", "p&l", "pnl", "by day")):
                        monthly = alt
                        break
                if monthly:
                    metric_ids = (monthly,)
                    decision = self.gate.authorize(monthly)
                    prov.append(f"[7] planner redirected all-time {mid0} -> period series "
                                f"{monthly} (period must be enforced at execution)")
                else:
                    label = getattr(u.time, "period_label", None) or "that period"
                    subject = (u.metric.concept if u.metric else "measure").replace("_", " ")
                    subject = subject.replace("explicit:", "")
                    prov.append("[7] period-scoped plan blocked: no monthly series for "
                                f"{mid0}; refusing silent all-time substitute")
                    return self._terminal(
                        u, NOT_DETERMINABLE, prov,
                        not_determinable_reason=(
                            f"I can show the recorded all-time {subject} figure, but I don't "
                            f"have a month-scoped series that answers {label} for this measure. "
                            f"{NOT_DETERMINABLE_TEXT}"),
                        decision=decision, metric_ids=metric_ids)

        # --- [7] plan-type selection (analytics_execution_spec.md 2.1-2.8) ---------------------
        plan_type, status, calls, extra_prov = self._select_plan(u, metric_ids, decision,
                                                                resolved_dims)
        prov.extend(extra_prov)

        # A resolved entity filter must travel with the call, not merely be recorded on the
        # plan. `dimension_resolver` has already confirmed the metric's own grain carries the
        # dimension, and `MetricExecutor._invoke` refuses a calculator that cannot honour it,
        # so a filter can neither be applied to a metric that does not support it nor quietly
        # dropped on the way to one that does.
        if resolved_dims and calls:
            entity_kwargs = {}
            code = (resolved_dims.filters or {}).get("apartment_id")
            if code:
                entity_kwargs["apartment_code"] = code
            if entity_kwargs:
                calls = tuple(ExecutionCall(metric_id=c.metric_id, label=c.label,
                                            kwargs={**c.kwargs, **entity_kwargs})
                              for c in calls)
                prov.append(f"[7] entity filter carried into execution: {entity_kwargs}")

        ceiling = max((INTENT_REASONING_CEILING[i] for i in u.intents),
                      key=lambda s: _LADDER.index(s))

        return AnalyticsPlan(
            question=u.question, status=status, intents=u.intents, plan_type=plan_type,
            reasoning_ceiling=ceiling,
            metric=u.metric, metric_ids=metric_ids, time=u.time,
            time_note=u.time_note, excluded_by_time=excluded_by_time,
            comparison=u.comparison,
            forecast_note=getattr(u, "forecast_note", "") or "",
            filters=dict(resolved_dims.filters) if resolved_dims else {},
            group_by=tuple(resolved_dims.group_by) if resolved_dims else (),
            degenerate_dimensions_used=(tuple(resolved_dims.degenerate_used)
                                        if resolved_dims else ()),
            trust_level=decision.effective_level,
            execution_mode=decision.execution_mode,
            headline_permitted=decision.headline_permitted,
            required_disclosures=decision.required_disclosures,
            trust_reason=decision.reason,
            breakdown_requested=u.breakdown_requested,
            driver_requested=u.driver_requested,
            decision_requested=u.decision_requested,
            execution_calls=calls,
            provenance=tuple(prov),
        )

    # -- structural guards ------------------------------------------------------------------------

    def _structural_guards(self, u, metric_ids, decision):
        """Phase 3 requirement 5: prevent invalid metric/dimension combinations, cross-grain
        joins, unsupported historical comparisons, mixing incompatible metric families, using a
        diagnostic/DQ metric as a financial headline, and bypassing BLOCK/SHOW_BOTH through
        arithmetic composition."""
        reasons = []

        # Mixing incompatible families / bypassing BLOCK by composition. Delegated to the Phase 2
        # gate's own combination guard -- the same code path that stops revenue-minus-expenses
        # being presented as SAFE profit.
        #
        # The guard governs ARITHMETIC composition (add/subtract/ratio into one figure). It does
        # NOT govern a risk composite, which analytics_execution_spec.md 2.8 prescribes as the
        # SAFE alternative: "run each contributing metric's own plan independently, tag each
        # result with its own metric_id/trust level, and present them as a labelled list, never
        # a merged score." Applying the arithmetic guard there would reject the very shape the
        # spec requires. The no-merge property is asserted separately below.
        is_labelled_list = RISK_SCAN in u.intents
        if (len(metric_ids) > 1 and not is_labelled_list
                and decision.execution_mode not in ("family", "internal_only")):
            ok, level, why = self.gate.authorize_combination(list(metric_ids))
            if not ok:
                reasons.extend(why)

        if is_labelled_list and len(metric_ids) > 1:
            # The composite is only permitted because every member keeps its own identity. If a
            # future change ever collapsed them to one call, that would be the merged score
            # 2.8 forbids -- assert the invariant rather than trusting it.
            if len(set(metric_ids)) != len(metric_ids):
                reasons.append("risk composite contains duplicate metric_ids")

        # A diagnostic/DQ metric may not be presented as a financial headline.
        if LOOKUP in u.intents or FILTERED_LOOKUP in u.intents:
            for mid in metric_ids:
                if concept_map.is_diagnostic(mid, self.registry) and RISK_SCAN not in u.intents:
                    if u.metric.concept not in ("aging", "deposit_risk", "duplicates",
                                                "duplicate_receipts", "overlapping_allotments",
                                                "reconciliation", "data_quality"):
                        reasons.append(
                            f"{mid} is a {concept_map.DIAGNOSTIC_DOMAIN} metric and may not be "
                            f"presented as a financial headline for a lookup question; it is "
                            f"a diagnostic finding, not a business figure.")

        # An unsupported historical comparison.
        if u.comparison is not None and not u.comparison.valid:
            reasons.append(
                f"Comparison rejected: {u.comparison.reason}")

        return reasons

    # -- plan-type selection ----------------------------------------------------------------------

    def _select_plan(self, u, metric_ids, decision, resolved_dims):
        prov = []
        intents = u.intents

        # BLOCK and SHOW_BOTH both take the explain-the-conflict plan (2.7). This precedes every
        # other plan-type choice: the precondition in analytics_execution_spec.md's header
        # constrains a BLOCK metric to this plan regardless of the question's intent.
        if decision.effective_level in ("BLOCK", "SHOW_BOTH"):
            planned = metric_ids
            if u.time_by_metric:
                answerable = tuple(m for m in metric_ids
                                   if u.time_by_metric.get(m) is None
                                   or u.time_by_metric[m].within_coverage)
                if answerable and len(answerable) < len(metric_ids):
                    prov.append(
                        f"[7] family narrowed to {list(answerable)} for this period; the "
                        f"excluded definitions are disclosed, not dropped silently: "
                        f"{u.time_note[:200]}")
                    planned = answerable
            calls = tuple(ExecutionCall(metric_id=m, label=f"definition:{m}")
                          for m in planned)
            prov.append(f"[7] plan={PLAN_EXPLAIN_CONFLICT} -- analytics_execution_spec.md 2.7: "
                        f"compute each competing definition independently and the pairwise "
                        f"differences; never a single value. "
                        f"{len(calls)} definition(s) planned.")
            status = BLOCKED if decision.effective_level == "BLOCK" else READY
            return PLAN_EXPLAIN_CONFLICT, status, calls, prov

        if decision.effective_level == "NOT_DETERMINABLE":
            prov.append(f"[7] no plan: gate posture is NOT_DETERMINABLE -- {decision.reason}")
            return PLAN_NONE, NOT_DETERMINABLE, (), prov

        base_call = ExecutionCall(metric_id=metric_ids[0], label=metric_ids[0])

        if RISK_SCAN in intents:
            present = tuple(m for m in RISK_COMPOSITE_METRICS if m in self.registry)
            calls = tuple(ExecutionCall(metric_id=m, label=f"risk:{m}") for m in present)
            prov.append(f"[7] plan={PLAN_RISK_COMPOSITE} -- analytics_execution_spec.md 2.8: "
                        f"each contributing metric runs its own plan and keeps its own "
                        f"metric_id/trust label; presented as a labelled list, never a merged "
                        f"score ({len(calls)} metrics).")
            return PLAN_RISK_COMPOSITE, READY, calls, prov

        if DRIVER in intents:
            # 2.6: decompose the change using metric_dependency_graph.md's DOCUMENTED edges,
            # never an ad-hoc decomposition.
            deps = tuple(d for d in self.registry.get(metric_ids[0]).dependency_metrics
                         if d in self.registry and d != "ALL")
            calls = (base_call,) + tuple(
                ExecutionCall(metric_id=d, label=f"driver-component:{d}") for d in deps)
            prov.append(f"[7] plan={PLAN_DRIVER} -- analytics_execution_spec.md 2.6: "
                        f"decomposition uses the {len(deps)} documented dependency edge(s) of "
                        f"{metric_ids[0]}, never an ad-hoc decomposition.")
            return PLAN_DRIVER, READY, calls, prov

        if ANOMALY in intents:
            prov.append(f"[7] plan={PLAN_ANOMALY} -- analytics_execution_spec.md 2.5: a trend "
                        f"series; before any period is flagged anomalous the scan must check "
                        f"data_quality_report.md for a known mechanism that would explain the "
                        f"deviation as a data artifact rather than a business event.")
            return PLAN_ANOMALY, READY, (base_call,), prov

        if COMPARISON in intents and u.comparison is not None and u.comparison.valid:
            prov.append(f"[7] plan={PLAN_PERIOD_COMPARISON} -- analytics_execution_spec.md 2.3: "
                        f"both periods use the identical definition, filters, and "
                        f"reversal/soft-delete policy.")
            return PLAN_PERIOD_COMPARISON, READY, (base_call,), prov

        if TREND in intents:
            prov.append(f"[7] plan={PLAN_TREND} -- analytics_execution_spec.md 2.4, subject to "
                        f"the coverage-boundary and YoY guards already applied at stage [4].")
            return PLAN_TREND, READY, (base_call,), prov

        if resolved_dims is not None and resolved_dims.group_by:
            prov.append(f"[7] plan={PLAN_GROUPED} -- analytics_execution_spec.md 2.2, "
                        f"group_by={list(resolved_dims.group_by)} confirmed against "
                        f"{metric_ids[0]}'s documented grain.")
            return PLAN_GROUPED, READY, (base_call,), prov

        if META in intents:
            prov.append("[7] plan=explain-the-conflict for a meta/definitional question -- "
                        "question_understanding_spec.md 2: answered from conflicts.md / "
                        "ai_trust_policy.md content, bypassing Execution.")
            calls = tuple(ExecutionCall(metric_id=m, label=f"definition:{m}")
                          for m in metric_ids)
            return PLAN_EXPLAIN_CONFLICT, READY, calls, prov

        prov.append(f"[7] plan={PLAN_SINGLE_VALUE} -- analytics_execution_spec.md 2.1.")
        return PLAN_SINGLE_VALUE, READY, (base_call,), prov

    # -- helpers -----------------------------------------------------------------------------------

    def _terminal(self, u, status, prov, clarification=None, not_determinable_reason="",
                  rejection_reasons=(), decision=None, metric_ids=()):
        ceiling = max((INTENT_REASONING_CEILING[i] for i in u.intents),
                      key=lambda s: _LADDER.index(s))
        return AnalyticsPlan(
            question=u.question, status=status, intents=u.intents, plan_type=PLAN_NONE,
            reasoning_ceiling=ceiling, metric=u.metric,
            metric_ids=tuple(metric_ids) or (u.metric.metric_ids if u.metric else ()),
            time=u.time, comparison=u.comparison,
            clarification=clarification, not_determinable_reason=not_determinable_reason,
            rejection_reasons=tuple(rejection_reasons),
            # A refusal is not a trusted figure: carrying the metric's own gate level onto a
            # NOT_DETERMINABLE plan badged "I cannot answer this" as DISCLOSE, which reads as
            # though a usable number were being qualified rather than withheld.
            #
            # BLOCK and SHOW_BOTH are the exception, and the exception matters more than the
            # rule. Those postures say the definitions themselves disagree, which outranks
            # "and also the period is unavailable" -- the conflict is what the owner has to act
            # on, and relabelling it NOT_DETERMINABLE would let a period limitation hide it.
            trust_level=_terminal_trust(status, decision),
            execution_mode=decision.execution_mode if decision else "",
            headline_permitted=False,
            required_disclosures=decision.required_disclosures if decision else (),
            breakdown_requested=u.breakdown_requested,
            driver_requested=u.driver_requested,
            decision_requested=u.decision_requested,
            forecast_note=getattr(u, "forecast_note", "") or "",
            provenance=tuple(prov),
        )

    # -- validation --------------------------------------------------------------------------------

    def validate(self, plan: AnalyticsPlan):
        """Full plan validation, covering Phase 3 requirement 4's checklist. Returns problems."""
        problems = list(validate_plan_schema(plan, self.registry))

        for mid in plan.metric_ids:
            if mid not in self.registry:
                problems.append(f"metric {mid!r} not in the semantic registry")
                continue
            spec = self.registry.get(mid)

            for dim in list(plan.filters) + list(plan.group_by):
                if dim not in dimres.KNOWN_DIMENSIONS:
                    problems.append(f"dimension {dim!r} is not catalogued in "
                                    f"business_dimensions.md")

            if plan.time is not None and plan.time.date_field != spec.date_field:
                # Only the primary metric's date_field is carried on the plan; a family member
                # with a different documented field is legitimate and is re-resolved per call.
                if mid == plan.metric_ids[0]:
                    problems.append(
                        f"{mid}: plan uses date_field {plan.time.date_field!r} but the registry "
                        f"documents {spec.date_field!r}")

            # The Trust Gate must be able to evaluate every planned metric.
            d = self.gate.authorize(mid)
            if d.verdict is None and mid in self.registry:
                problems.append(f"{mid}: trust gate could not produce a verdict")

        if plan.executable and plan.trust_level in ("SHOW_BOTH", "BLOCK"):
            if plan.plan_type != PLAN_EXPLAIN_CONFLICT:
                problems.append(
                    f"{plan.trust_level} plan must use the explain-the-conflict plan type")
            if len(plan.execution_calls) < 2 and len(plan.metric_ids) > 1:
                problems.append(
                    f"{plan.trust_level} plan narrows a {len(plan.metric_ids)}-member family to "
                    f"{len(plan.execution_calls)} execution call(s)")

        if plan.comparison is not None and not plan.comparison.valid and plan.status == READY:
            problems.append("plan is READY but carries an invalid comparison")

        return problems


_LADDER = ("FACT", "CALCULATION", "OBSERVATION", "INFERENCE", "HYPOTHESIS", "RECOMMENDATION")
