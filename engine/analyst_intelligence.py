"""
analyst_intelligence.py -- Phase 6. The Virtual Business Analyst: owner question in, structured
analytical answer out, with the analyst lens inferred rather than chosen.

    OWNER QUESTION -> Question Understanding -> Analyst Role Routing -> Metric/Concept
    Resolution -> Dimension Resolution -> Time Resolution -> Analytics Plan -> Trust Gate ->
    Deterministic Calculation -> Validation -> Business Reasoning -> Multi-Lens Analysis ->
    Insight Generation -> Decision Support -> Answer Contract -> LLM Verbalization -> ANSWER

Everything from Question Understanding through Answer Contract is Phase 1-5 and is CALLED, not
reimplemented. This module adds four things and nothing else: lens routing, multi-lens synthesis,
the owner-intent shortcuts (briefing / what-changed / why / what-to-do), and the explainability
chain.

The product requirement that shapes the surface (Phase 6 brief 17):

    "The owner should NOT have to understand metric IDs, table names, SQL, data models, analyst
     terminology, Power BI terminology, or trust-layer internals. They should simply ask normal
     business questions."

So `ask()` takes a sentence. Everything technical is derived, and the technical detail remains
available through `explain()` rather than being pushed at the owner.
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine.llm_interface import LLMInterface
from engine.insight_engine import InsightEngine
from engine.change_detection import ChangeDetector, COMPARABLE_MONTHLY_METRICS
from engine.root_cause import RootCauseAnalyzer
from engine.executive_summary import ExecutiveSummaryBuilder
from engine.bi_contract import BIContractBuilder
from engine import (analyst_roles, explainability, owner_presentation,
                    prompt_contracts, answer_renderer)
from engine.llm_provider import LLMUnavailable
from engine.result import NOT_DETERMINABLE_TEXT

# --- Owner-intent shortcuts -----------------------------------------------------------------------
# Whole-business questions that are not about ONE metric. Routed before metric resolution,
# because asking "how is the business doing?" resolves to no single metric and would otherwise
# terminate as NOT_DETERMINABLE -- which would be true of the metric lookup and false of the
# question.

INTENT_BRIEFING = "briefing"
INTENT_WHAT_CHANGED = "what_changed"
INTENT_WHAT_TO_DO = "what_to_do"
INTENT_WHAT_TO_TRUST = "what_to_trust"
INTENT_METRIC = "metric_question"

_BRIEFING_PHRASES = (
    "how is the business", "how's the business", "business summary", "management briefing",
    "today's business summary", "todays business summary", "give me a briefing",
    "executive summary", "show me the important numbers", "how are we doing",
    "overall picture", "business health",
    # Owner phrasings for the same request. Without these the question resolves to no single
    # metric and is refused -- which is true of the metric lookup and false of the question.
    "management report", "important business insights", "business insights",
    "tell the owner", "brief the owner", "owner report", "board report",
    "show me the insights", "key insights",
    # "How is MY business doing?" is the most natural owner phrasing and is the dashboard's own
    # title, but only "how is THE business" was recognised, so the owner's own words fell
    # through to a metric lookup and were refused.
    "how is my business", "how's my business", "hows my business", "how is business",
    "how is the company", "how's the company", "how is our company", "how's our company",
    "business overview", "company overview", "give me an overview", "give me a business overview",
    "overview of the business", "overview of my business", "overview of our business",
)
_WHAT_CHANGED_PHRASES = (
    "what changed", "what has changed", "what's changed", "whats changed",
    "what changed this month", "what moved", "any changes",
    "compare this month with last", "compare this month to last",
    "this month with last month", "this month vs last month",
    "month on month comparison", "compared with last month",
)
_WHAT_TO_DO_PHRASES = (
    "what should i do", "what should we do", "what needs my attention",
    "what requires my decision", "what should i investigate", "what needs attention",
    "what should management do", "what requires a decision", "what's pending",
    "what should i worry about", "what should i focus on",
    "which area needs attention", "what should i fix", "fix first",
    "where should i start", "what is most urgent", "what's most urgent",
    "priority", "priorities",
    # Risk phrasings route here rather than to a metric lookup. "What are my biggest risks?"
    # is answered by the attention queue -- the BLOCK conflicts and critical data-quality
    # findings the insight layer already validated. It is NOT answered by a risk score: no
    # specification defines one, and the queue's own ranking is the only ordering the evidence
    # supports.
    "biggest risk", "biggest risks", "what are my risks", "what are our risks",
    "what risks", "which risks", "business risks", "main risks", "top risks",
    "look at first", "which area should i look",
    "what should i look at", "what needs action", "needs action",
    "what is important right now", "what's important right now", "whats important right now",
    "what problems should", "problems should i look", "major risk areas",
    "anything risky", "is anything risky",
)
_WHAT_TO_TRUST_PHRASES = (
    "which numbers should i trust", "which numbers can i trust", "which numbers are unreliable",
    "what data problems", "what data should i worry about", "can i trust",
    "how reliable is the data", "which figures are reliable",
)


def classify_owner_intent(question):
    from engine import concept_map

    q = (question or "").lower().strip()
    has_concept = bool(concept_map.match(q))
    for phrases, intent in ((_BRIEFING_PHRASES, INTENT_BRIEFING),
                            (_WHAT_CHANGED_PHRASES, INTENT_WHAT_CHANGED),
                            (_WHAT_TO_DO_PHRASES, INTENT_WHAT_TO_DO),
                            (_WHAT_TO_TRUST_PHRASES, INTENT_WHAT_TO_TRUST)):
        if any(p in q for p in phrases):
            # A named business concept means this is a metric-scoped analysis, not a
            # whole-business workflow — even if workflow-ish words also appear
            # ("compare revenue this month with last month").
            if has_concept and intent in (INTENT_BRIEFING, INTENT_WHAT_CHANGED):
                continue
            return intent
    return INTENT_METRIC


WORKFLOW_INTENTS = (INTENT_BRIEFING, INTENT_WHAT_CHANGED, INTENT_WHAT_TO_DO,
                    INTENT_WHAT_TO_TRUST)


def resolve_owner_intent(question, last_owner_intent=""):
    """Owner-intent classification plus deterministic follow-up inheritance.

    A bare follow-up ("Tell me more.", "Why?") after a whole-business workflow is still that
    workflow. A follow-up that names its own concept is a new metric question and is never
    inherited. The LLM does not make this choice.
    """
    from engine.conversation_context import ConversationContext
    from engine import concept_map

    owner_intent = classify_owner_intent(question)
    if owner_intent != INTENT_METRIC:
        return owner_intent
    if last_owner_intent not in WORKFLOW_INTENTS:
        return INTENT_METRIC
    if not ConversationContext.looks_like_followup(question):
        return INTENT_METRIC
    if concept_map.match(question or ""):
        return INTENT_METRIC
    return last_owner_intent


# --- Multi-lens synthesis --------------------------------------------------------------------------

@dataclass(frozen=True)
class LensView:
    """One analyst lens's contribution. A lens contributes a PERSPECTIVE on already-computed
    metrics; it never contributes a number of its own."""
    role_id: str
    display_name: str
    focus: str
    metric_ids: tuple = ()
    observations: tuple = ()
    caveats: tuple = ()


@dataclass
class AnalystAnswer:
    question: str
    owner_intent: str = INTENT_METRIC
    routing: object = None
    lenses: tuple = ()
    ask_result: object = None            # the Phase 4/5 AskResult, unchanged
    summary: object = None               # ExecutiveSummary, for briefing questions
    # The completed descriptive Summary, when the question was a descriptive one. Carried so the
    # owner explanation can say WHICH statistics were reported without recomputing them -- a
    # second computation could disagree with the answer it is supposed to be explaining.
    descriptive: object = None
    changes: tuple = ()
    root_cause: object = None
    cards: tuple = ()                    # BI MetricCards
    chain: object = None                 # explainability.EvidenceChain
    text: str = ""
    # The deterministic owner draft, kept even when the wording layer rewrote it. `text` is
    # what the owner sees; `owner_draft` is what the engine produced, so the two can be
    # compared in a test and the draft can be served when the guard rejects a verbalization.
    owner_draft: str = ""
    verbalized: bool = False
    guard_violations: tuple = ()
    trust_level: str = ""
    metric_ids: tuple = ()
    limitations: tuple = ()
    not_determinable_reason: str = ""

    @property
    def determinable(self):
        return not self.not_determinable_reason


VERBALIZATION_MAX_TOKENS = 320


class AnalystIntelligence:
    """The single owner-facing entry point."""

    def __init__(self, registry: SemanticRegistry = None, provider=None, verbalize=True):
        self.registry = registry or SemanticRegistry()
        self.gate = TrustGate(self.registry)
        self.executor = MetricExecutor(registry=self.registry, gate=self.gate)
        self.insight_engine = InsightEngine(registry=self.registry, gate=self.gate,
                                            executor=self.executor)
        self.detector = ChangeDetector(self.registry, self.gate, self.executor)
        self.analyzer = RootCauseAnalyzer(self.registry, self.gate, self.executor,
                                          self.detector)
        self.summary_builder = ExecutiveSummaryBuilder(
            self.registry, self.gate, self.executor, self.insight_engine,
            self.detector, self.analyzer)
        self.bi = BIContractBuilder(self.registry, self.gate, self.executor)
        self.llm = LLMInterface(provider=provider, registry=self.registry,
                                executor=self.executor, verbalize=verbalize,
                                insight_engine=self.insight_engine)
        self._summary_cache = None

    # -- the owner-facing surface -------------------------------------------------------------------

    def ask(self, question) -> AnalystAnswer:
        from engine.question_normalize import normalize_owner_question
        from engine import analysis_capability as acap

        cleaned, _ = normalize_owner_question(question or "")
        working = cleaned if cleaned.strip() else (question or "")
        cap = acap.classify_analysis_capability(working)

        owner_intent = resolve_owner_intent(
            working, getattr(self.llm.context, "last_owner_intent", ""))

        # Capability classification upgrades a bare metric fall-through into the matching
        # whole-business workflow or a capability-gap answer. Follow-up inheritance above
        # still wins when resolve_owner_intent kept a prior workflow.
        #
        # CRITICAL: never override a named-concept analysis (comparison/trend/driver/anomaly)
        # with a whole-business workflow — that answers a different question.
        from engine.question_understanding import classify_intents
        from engine import concept_map
        from engine.intent_models import COMPARISON, TREND, DRIVER, ANOMALY

        intents = classify_intents(working)
        has_concept = bool(concept_map.match(working))
        analysis_shaped = any(i in intents for i in (COMPARISON, TREND, DRIVER, ANOMALY))

        if owner_intent == INTENT_METRIC:
            if cap.route == acap.ROUTE_BRIEFING and not has_concept and not analysis_shaped:
                owner_intent = INTENT_BRIEFING
            elif (cap.route == acap.ROUTE_WHAT_CHANGED
                  and not has_concept and not analysis_shaped):
                owner_intent = INTENT_WHAT_CHANGED
            elif (cap.route == acap.ROUTE_WHAT_TO_DO
                  and not analysis_shaped
                  and (not has_concept or cap.capability_id == "attention_required")):
                owner_intent = INTENT_WHAT_TO_DO
            elif cap.route == acap.ROUTE_WHAT_TO_TRUST and not analysis_shaped:
                owner_intent = INTENT_WHAT_TO_TRUST
            elif cap.route == acap.ROUTE_DESCRIPTIVE:
                answer = self._descriptive(working, cap)
                answer = self._verbalize_workflow(answer, working)
                answer.question = question or ""
                self.llm.context.last_owner_intent = INTENT_METRIC
                return answer
            elif cap.route == acap.ROUTE_CAPABILITY_GAP:
                answer = self._capability_gap(working, cap)
                # For forecasting, optionally attach latest historical context when a concept
                # is known — never as the forecast answer itself.
                if cap.capability_id == "forecasting":
                    answer = self._forecast_gap_with_context(working, cap, answer)
                answer.question = question or ""
                self.llm.context.last_owner_intent = INTENT_METRIC
                return answer

        if owner_intent == INTENT_BRIEFING:
            answer = self._briefing(working)
        elif owner_intent == INTENT_WHAT_CHANGED:
            answer = self._what_changed(working)
        elif owner_intent == INTENT_WHAT_TO_DO:
            answer = self._what_to_do(working)
        elif owner_intent == INTENT_WHAT_TO_TRUST:
            answer = self._what_to_trust(working)
        else:
            answer = self._metric_question(working)

        # Whole-business workflows reached the owner as the raw deterministic draft, because
        # only the metric path ran the Phase 4 verbalization. They now take the SAME path:
        # deterministic draft -> Ollama -> guard -> answer, falling back to the draft.
        if owner_intent in WORKFLOW_INTENTS:
            answer = self._verbalize_workflow(answer, working)

        answer.question = question or ""
        self.llm.context.last_owner_intent = owner_intent
        return answer

    def _descriptive(self, question, classification) -> AnalystAnswer:
        """Descriptive analysis, through the same gate-then-execute-then-word order as every
        other answer.

        Nothing is computed here. `engine/descriptive.py` produces the figures, the Trust Gate
        authorizes the metric that governs each described column before any of them is shown,
        and `owner_presentation` does the wording. The gate step is not a formality: the
        outstanding-balance column IS a metric with competing definitions, and describing its
        distribution while that conflict is unresolved would publish through the side door a
        figure the metric path is blocked from stating.
        """
        from engine import descriptive_routing as droute
        from engine.gate import _SEVERITY

        route = droute.classify(question)

        if route.refusal:
            text = owner_presentation.sanitize_owner_text(route.refusal)
            return AnalystAnswer(
                question=question, owner_intent=INTENT_METRIC, text=text, owner_draft=text,
                trust_level="NOT_DETERMINABLE", not_determinable_reason=route.refusal,
                limitations=(classification.limitation,) if classification.limitation else ())

        # A question that named a period is asking about that period. These summaries describe
        # the whole recorded window, so the honest answer is to say so -- never to hand back the
        # all-time figure as though it were the period's.
        period = droute.period_conflict(question)
        if period:
            reason = droute.period_refusal(period)
            text = owner_presentation.sanitize_owner_text(reason)
            return AnalystAnswer(
                question=question, owner_intent=INTENT_METRIC, text=text, owner_draft=text,
                trust_level="NOT_DETERMINABLE", not_determinable_reason=reason)

        metric_ids = droute.governing_metric_ids(route)
        trust_level = "SAFE"
        gate_reason = ""
        for mid in metric_ids:
            decision = self.gate.authorize(mid)
            if _SEVERITY[decision.effective_level] > _SEVERITY[trust_level]:
                trust_level = decision.effective_level
                gate_reason = decision.reason

        # BLOCK and NOT_DETERMINABLE mean no figure may be stated. A description of the column
        # is still a statement of that figure's shape, so it is withheld on the same terms.
        if trust_level in ("BLOCK", "NOT_DETERMINABLE"):
            text = owner_presentation.sanitize_owner_text(
                f"I can't describe {route.subject} as a single picture. The underlying figure "
                f"has competing definitions in your records that produce different numbers, and "
                f"describing one of them would be picking a definition on your behalf. Ask for "
                f"the figure itself and I will show every definition side by side. "
                f"{NOT_DETERMINABLE_TEXT}")
            return AnalystAnswer(
                question=question, owner_intent=INTENT_METRIC, text=text, owner_draft=text,
                trust_level=trust_level, metric_ids=tuple(metric_ids),
                not_determinable_reason=gate_reason or text)

        summary = droute.run(route)
        text = owner_presentation.present_descriptive(summary, route)
        determinable = bool(summary is not None and summary.available)

        limitations = []
        if not determinable:
            trust_level = "NOT_DETERMINABLE"
        elif route.kind in ("cross_section", "apartments") and not metric_ids:
            # No registry metric governs the rent column: it is a recorded field, described as
            # recorded. That is worth saying rather than presenting as a reconciled figure.
            trust_level = "DISCLOSE"
            limitations.append(
                "This describes what is recorded on the allotments themselves. It is not "
                "reconciled against the accounting ledger, so it says what was entered, not "
                "what was billed or received.")

        return AnalystAnswer(
            question=question, owner_intent=INTENT_METRIC, text=text, owner_draft=text,
            trust_level=trust_level, metric_ids=tuple(metric_ids),
            limitations=tuple(limitations),
            # The finished summary travels with the answer so the owner explanation can name
            # which statistics were reported. Nothing is recomputed from it.
            descriptive=summary,
            not_determinable_reason=(
                "" if determinable else getattr(summary, "not_determinable_reason", "")
                or NOT_DETERMINABLE_TEXT))

    def _capability_gap(self, question, classification) -> AnalystAnswer:
        """Recognised analysis type with no implemented method — not an unknown metric."""
        from engine import analysis_capability as acap
        from engine import concept_map

        subject = ""
        hits = concept_map.match(question or "")
        if hits:
            subject = hits[0][0].name.replace("_", " ")
        text = owner_presentation.sanitize_owner_text(
            acap.owner_capability_gap_text(classification, subject=subject))
        # The limitation is a sentence the owner can read, not the capability's internal label.
        # This list is rendered under "Limitations" in the chat panel, where `Forecasting` on
        # its own said nothing and read as a debug tag leaking through.
        measure = subject or "this measure"
        return AnalystAnswer(
            question=question, owner_intent=INTENT_METRIC,
            text=text, owner_draft=text,
            not_determinable_reason=text,
            limitations=(
                f"{classification.label} is not available for {measure}: no validated method "
                f"for it exists in this system, so no projection is offered.",),
        )

    def _forecast_gap_with_context(self, question, classification, gap_answer):
        """Capability-aware forecast refusal, plus optional latest historical context."""
        from engine import concept_map
        from engine.change_detection import COMPARABLE_MONTHLY_METRICS

        hits = concept_map.match(question or "")
        if not hits:
            return gap_answer
        concept = hits[0][0]
        mid = ""
        for cand in tuple(concept.alternatives) + tuple(concept.metric_ids):
            if cand in COMPARABLE_MONTHLY_METRICS or cand in self.registry:
                mid = cand
                if cand in COMPARABLE_MONTHLY_METRICS:
                    break
        if not mid or mid not in self.registry:
            return gap_answer
        try:
            ans = self.executor.execute(mid)
        except Exception:
            return gap_answer
        # Prefer the latest complete month from a series when available.
        raw = ans.headline
        if raw is None and ans.results:
            raw = ans.results[0].value
        context_line = ""
        if isinstance(raw, dict) and raw:
            from engine.change_detection import _complete_months, _numeric
            months, _excl = _complete_months(sorted(raw))
            if months:
                last = months[-1]
                val = _numeric(raw[last])
                if val is not None:
                    context_line = (
                        f"Latest recorded {concept.name.replace('_', ' ')} "
                        f"({last}): {owner_presentation.format_owner_quantity(val)}."
                    )
        elif raw is not None and not isinstance(raw, dict):
            context_line = (
                f"Latest recorded {concept.name.replace('_', ' ')}: "
                f"{owner_presentation.format_owner_quantity(raw)}."
            )
        if not context_line:
            return gap_answer
        text = owner_presentation.sanitize_owner_text(
            f"{gap_answer.text}\n\nLatest historical context (not a forecast):\n"
            f"{context_line}"
        )
        return AnalystAnswer(
            question=question, owner_intent=INTENT_METRIC,
            text=text, owner_draft=text,
            not_determinable_reason=gap_answer.not_determinable_reason,
            metric_ids=(mid,),
            # `forecast unavailable` was an internal state tag standing where a sentence
            # belongs. What the owner needs to know about the figure just shown is what it is
            # and what it is not.
            limitations=tuple(gap_answer.limitations) + (
                f"Recorded {concept.name.replace('_', ' ')} can still be shown, and the figure "
                f"above is the latest of it -- not a projection. Nothing was estimated in its "
                f"place.",),
        )

    def _condensed_brief(self, answer):
        """The small deterministic fact set for this question, or "" if none applies."""
        intent = answer.owner_intent
        if intent == INTENT_BRIEFING and answer.summary is not None:
            return owner_presentation.condense_briefing(answer.summary)
        if intent == INTENT_WHAT_TO_DO and answer.summary is not None:
            return owner_presentation.condense_what_to_do(answer.summary)
        if intent == INTENT_WHAT_CHANGED:
            return owner_presentation.condense_what_changed(answer.changes or ())
        if intent == INTENT_WHAT_TO_TRUST:
            buckets = {}
            for mid in self.registry.all_ids():
                buckets.setdefault(
                    self.gate.authorize(mid).effective_level, []).append(mid)
            return owner_presentation.condense_what_to_trust(buckets)
        return ""

    def _verbalize_workflow(self, answer, question):
        """Re-word a workflow draft through the existing LLM boundary, under guard.

        This is not a second pipeline: it uses the same provider, the same verbalization
        system prompt, and the guard that lives beside the metric guard. The deterministic
        draft is the source of truth, so a model that is unavailable, slow, or wrong costs
        the owner nothing but plainer wording.
        """
        draft = answer.text or ""
        answer.owner_draft = draft

        # The owner sees the concise answer either way. The full draft stays on `owner_draft`
        # for the engine and debug layers.
        brief = self._condensed_brief(answer)
        if brief:
            answer.text = brief

        if not draft.strip() or not getattr(self.llm, "verbalize", False):
            return answer

        # The wording layer is handed a SMALL, question-relevant brief -- not the whole
        # management briefing. A local model restating eight thousand characters times out on
        # CPU, so the owner never saw a verbalized answer at all; and asking a model to
        # summarise invites it to choose what to omit from a conflict disclosure, which is the
        # one decision it must never make. The choice of what to include is made
        # deterministically, above; the model only re-words what it is given.
        brief = brief or draft
        prompt = prompt_contracts.build_verbalization_prompt(brief, "WORKFLOW", question)
        try:
            resp = self.llm.provider.complete(
                prompt, system=prompt_contracts.VERBALIZATION_SYSTEM, temperature=0.0,
                max_tokens=VERBALIZATION_MAX_TOKENS)
        except LLMUnavailable:
            return answer            # the concise draft already stands; never a guess

        # Guarded against the brief the model actually saw: a number it did not receive is
        # a number it invented.
        violations = answer_renderer.guard_workflow(resp.text, brief)
        if violations:
            answer.guard_violations = tuple(violations)
            answer.text = brief      # whole-output rejection, never a partial merge
            return answer

        answer.text = owner_presentation.sanitize_owner_text(resp.text)
        answer.verbalized = True
        return answer

    # -- metric questions ----------------------------------------------------------------------------

    def _metric_question(self, question):
        result = self.llm.ask(question)

        reason_blob = " ".join([
            result.text or "",
            (result.rendered.skeleton if result.rendered else "") or "",
            (result.plan.not_determinable_reason if result.plan else "") or "",
        ]).lower()
        structural = "only 1 distinct value" in reason_blob
        routing = analyst_roles.route(
            intents=(result.plan.intents if result.plan else ()),
            metric_ids=result.metric_ids, registry=self.registry,
            trust_level=result.trust_level, structural_limitation=structural)

        lenses = self._build_lenses(routing, result)

        rc = None
        text = result.text
        trust_level = result.trust_level
        plan = result.plan

        # A question awaiting a clarification has not been answered yet, and none of the
        # presenters below may speak for it. "Why did collections fall?" is a valid change
        # question about a measure with two evidence-backed definitions, so the pipeline
        # correctly stopped to ask which one -- and the comparison presenter then overwrote
        # that question with "I can't produce a period comparison from the available evidence",
        # which is a different claim and a false one. The comparison was never attempted; it
        # was deferred, and the owner was told a limitation instead of being asked.
        awaiting_clarification = (
            (getattr(plan, "status", "") == "NEEDS_CLARIFICATION")
            or result.status == "NEEDS_CLARIFICATION"
            or result.clarification is not None)

        if awaiting_clarification:
            # `result.text` is already the clarification, rendered with every definition. The
            # trust posture stays with the definitions, not with this turn: nothing has been
            # computed, so there is nothing to label SAFE or NOT_DETERMINABLE.
            trust_level = ""

        elif plan is not None and plan.driver_requested and result.metric_ids:
            mid = self._comparable_metric_for_change(result.metric_ids[0], plan)
            # No monthly series belongs to this definition, so there is no period change to
            # explain. `present_driver_answer` states that from the plan rather than analysing
            # a series that describes a different measure.
            rc = self.analyzer.analyze(mid) if mid else None
            text = owner_presentation.present_driver_answer(
                question, plan, result.answers, rc, result.reasoning)
            # Trust applies to the driver answer scope, not a substituted all-time lookup.
            if rc is not None and rc.trust_level:
                trust_level = rc.trust_level
            if rc is not None and (not rc.determinable or (
                    rc.target_change is not None and not rc.target_change.detected)):
                trust_level = "NOT_DETERMINABLE"

        elif "M.RENT.001" in (result.metric_ids or ()) and result.answers:
            # Rent is a set of per-bed figures, not one number, so it needs its own wording for
            # the same reason driver and comparison answers do: the generic metric renderer is
            # built to state a single headline and there is no single headline to state. Gated
            # on there being an executed answer, so a clarification or refusal keeps its own
            # words rather than being restated as "no rent recorded".
            text = owner_presentation.present_rent_answer(plan, result.answers)

        elif plan is not None and (
                getattr(plan, "plan_type", "") == "anomaly_scan"
                or (plan.intents and "anomaly" in plan.intents)):
            text = owner_presentation.present_anomaly_answer(plan, result.answers)
            trust_level = "NOT_DETERMINABLE"

        elif plan is not None and (
                getattr(plan, "plan_type", "") == "period_comparison"
                or (plan.intents and "comparison" in plan.intents)):
            mid = self._comparable_metric_for_change(
                result.metric_ids[0] if result.metric_ids else "", plan)
            if mid:
                cur = prev = None
                if plan.comparison is not None:
                    cur = getattr(plan.comparison.current, "start", None)
                    prev = getattr(plan.comparison.baseline, "start", None)
                elif plan.time is not None and plan.time.start:
                    cur = plan.time.start
                change = self.detector.detect(
                    mid, current_period=cur, previous_period=prev,
                    series_component=self._series_component_for_plan(plan))
                text = owner_presentation.present_comparison_answer(change, plan)
                trust_level = change.trust_level if change.detected else "NOT_DETERMINABLE"
            else:
                text = owner_presentation.present_comparison_answer(None, plan)
                trust_level = "NOT_DETERMINABLE"

        elif plan is not None and (
                getattr(plan, "plan_type", "") == "trend_series"
                or (plan.intents and "trend" in plan.intents)):
            mid = self._comparable_metric_for_change(
                result.metric_ids[0] if result.metric_ids else "", plan)
            if mid:
                change = self.detector.detect(
                    mid, series_component=self._series_component_for_plan(plan))
                text = owner_presentation.present_comparison_answer(change, plan)
                if change.detected:
                    text = ("Trend direction from the latest comparable periods:\n" + text)
                    trust_level = change.trust_level
                else:
                    trust_level = "NOT_DETERMINABLE"
            else:
                text = ("A trend series is not available for this measure from the exported "
                        "evidence.")
                trust_level = "NOT_DETERMINABLE"

        cards = tuple(self.bi.card(m) for m in result.metric_ids)
        chain = explainability.build(result, routing)

        limitations = list(self._framing_mismatch(question, result))
        if rc is not None:
            limitations.extend(rc.limitations)
        if structural:
            limitations.append(
                "The question asks for a comparison the exported data's structure cannot "
                "support; this is a fact about the data, not a calculation failure.")

        return AnalystAnswer(
            question=question, owner_intent=INTENT_METRIC, routing=routing, lenses=lenses,
            ask_result=result, root_cause=rc, cards=cards, chain=chain,
            text=text, trust_level=trust_level,
            metric_ids=result.metric_ids,
            limitations=owner_presentation.owner_limitations(limitations),
            not_determinable_reason=(text if trust_level == "NOT_DETERMINABLE"
                                     and result.status == "NOT_DETERMINABLE" else ""),
        )

    def _comparable_metric_for_change(self, metric_id, plan):
        """The monthly series belonging to THIS measure, or "" when it has none.

        A concept can carry several genuinely different definitions, and only some of them have
        a monthly series. Collections is the case that exposed it: the owner is asked which
        definition they mean, picks the ledger-derived one, and the concept's metric list still
        offered `Collections by month` -- which the registry records as a grouping of the
        APPLICATION-level figure. The comparison then ran on a definition the owner had not
        chosen, under the label of the one they had.

        The registry already states which series belongs to which measure, in each series'
        declared dependencies. That is the authority used here; nothing new is defined.
        """
        from engine.change_detection import COMPARABLE_MONTHLY_METRICS
        from engine import concept_map

        if metric_id in COMPARABLE_MONTHLY_METRICS:
            return metric_id

        concept = ""
        if plan is not None and plan.metric is not None:
            concept = plan.metric.concept
        c = concept_map.concept(concept) if concept else None
        candidates = (tuple(c.metric_ids) + tuple(c.alternatives)) if c is not None else ()
        candidates = [a for a in candidates if a in COMPARABLE_MONTHLY_METRICS]
        if not candidates:
            return metric_id

        # With a resolved measure in hand, the series must be a series OF it.
        if metric_id and metric_id in self.registry:
            for alt in candidates:
                if alt in self.registry and metric_id in tuple(
                        self.registry.get(alt).dependency_metrics or ()):
                    return alt
            return ""      # this definition has no monthly series; refuse rather than swap
        return candidates[0]

    @staticmethod
    def _series_component_for_plan(plan):
        concept = ""
        if plan is not None and plan.metric is not None:
            concept = (plan.metric.concept or "").lower()
        return {
            "expenses": "expenses",
            "revenue": "revenue",
            "profit": "net_profit",
        }.get(concept)

    # Framings an owner may ask for that a metric does not necessarily provide. Matching a
    # concept is not the same as matching the SHAPE requested: "churn" resolves to the move-out
    # count, but "churn RATE" asks for a ratio, and answering a rate question with a count is a
    # silent reframing even though the count itself is correct and correctly labelled.
    _RATIO_WORDS = ("rate", "percentage", "percent", " pct", "ratio", "per bed", "per tenant",
                    "average", "avg ")
    _BENCHMARK_WORDS = ("benchmark", "industry", "target", "compared to peers", "vs peers",
                        "best practice", "norm")

    def _framing_mismatch(self, question, result):
        """Disclose when the owner asked for a framing the resolved metric does not provide."""
        q = (question or "").lower()
        out = []

        if any(w in q for w in self._BENCHMARK_WORDS):
            out.append(
                "A benchmark or target was asked for. The exported evidence contains only this "
                "business's own records -- no industry benchmark, target, or peer comparison "
                f"exists in it. {NOT_DETERMINABLE_TEXT}")

        if any(w in q for w in self._RATIO_WORDS) and result.answers:
            units = {r.unit.lower() for a in result.answers for r in a.results if r.unit}
            expresses_ratio = any(("%" in u or "pct" in u or "percent" in u or "ratio" in u)
                                  for u in units)
            if not expresses_ratio and units:
                out.append(
                    f"A rate or ratio was asked for, but the metric answered here is expressed "
                    f"in {', '.join(sorted(units))}, not as a ratio. The figure shown is the "
                    f"underlying quantity; no rate is derived, because forming one would "
                    f"require choosing a denominator the semantic layer does not document. "
                    f"{NOT_DETERMINABLE_TEXT}")
        return tuple(out)

    def _build_lenses(self, routing, result):
        """Each routed lens states what IT sees in the already-computed answer.

        The synthesis rule from the Phase 6 brief: "combine the lenses without duplicating or
        contradicting metrics." So a metric appears under exactly one lens -- the most direct one
        that claimed it -- and every lens reads the same computed values, which is why they
        cannot contradict each other.
        """
        claimed = set()
        views = []
        for role_id in routing.roles:
            role = analyst_roles.role(role_id)
            if role is None:
                continue
            mine = tuple(m for m in result.metric_ids
                         if m not in claimed
                         and m in self.registry
                         and self.registry.get(m).domain in role.domains)
            claimed.update(mine)

            observations, caveats = [], []
            for m in mine:
                for a in result.answers:
                    if a.metric_id != m:
                        continue
                    if a.headline is not None:
                        observations.append(
                            f"{self.registry.get(m).semantic_name}: {a.headline}")
                    else:
                        observations.append(
                            f"{self.registry.get(m).semantic_name}: no single figure "
                            f"({a.trust_level}); {len(a.results)} competing definitions")
                    if a.caveat:
                        caveats.append(a.caveat)
            views.append(LensView(
                role_id=role_id, display_name=role.display_name,
                focus=role.semantic_scope, metric_ids=mine,
                observations=tuple(observations), caveats=tuple(dict.fromkeys(caveats)),
            ))
        return tuple(views)

    # -- whole-business questions ------------------------------------------------------------------

    def _summary(self):
        if self._summary_cache is None:
            self._summary_cache = self.summary_builder.build()
        return self._summary_cache

    def _briefing(self, question):
        s = self._summary()
        routing = analyst_roles.route(
            intents=(), metric_ids=(), registry=self.registry)
        routing = analyst_roles.RoleRouting(
            roles=(analyst_roles.MANAGEMENT_REPORTING, analyst_roles.BUSINESS_ANALYST,
                   analyst_roles.RISK_DQ_ANALYST),
            reasons={analyst_roles.MANAGEMENT_REPORTING: "a whole-business briefing",
                     analyst_roles.BUSINESS_ANALYST: "cross-domain synthesis",
                     analyst_roles.RISK_DQ_ANALYST: "standing risks and conflicts"},
            primary=analyst_roles.MANAGEMENT_REPORTING)
        return AnalystAnswer(
            question=question, owner_intent=INTENT_BRIEFING, routing=routing,
            summary=s, text=owner_presentation.present_briefing(s),
            metric_ids=tuple(l.metric_id for l in s.business_health + s.operations),
            limitations=owner_presentation.owner_limitations(s.limitations),
        )

    def _what_changed(self, question):
        changes = self.detector.detect_all(COMPARABLE_MONTHLY_METRICS)
        routing = analyst_roles.RoleRouting(
            roles=(analyst_roles.DATA_SCIENTIST, analyst_roles.MANAGEMENT_REPORTING,
                   analyst_roles.BI_ANALYST),
            reasons={analyst_roles.DATA_SCIENTIST: "period change detection",
                     analyst_roles.MANAGEMENT_REPORTING: "reported to management",
                     analyst_roles.BI_ANALYST: "period comparison view"},
            primary=analyst_roles.DATA_SCIENTIST)

        return AnalystAnswer(
            question=question, owner_intent=INTENT_WHAT_CHANGED, routing=routing,
            changes=changes, text=owner_presentation.present_what_changed(changes),
            metric_ids=tuple(c.metric_id for c in changes),
            limitations=owner_presentation.owner_limitations((
                "Materiality is undefined for every change: no threshold exists in the "
                "exported evidence.",)),
        )

    def _what_to_do(self, question):
        s = self._summary()
        routing = analyst_roles.RoleRouting(
            roles=(analyst_roles.DECISION_SUPPORT, analyst_roles.BUSINESS_ANALYST,
                   analyst_roles.RISK_DQ_ANALYST),
            reasons={analyst_roles.DECISION_SUPPORT: "the question asks for an action",
                     analyst_roles.BUSINESS_ANALYST: "business framing",
                     analyst_roles.RISK_DQ_ANALYST: "risks and pending conflicts"},
            primary=analyst_roles.DECISION_SUPPORT)

        return AnalystAnswer(
            question=question, owner_intent=INTENT_WHAT_TO_DO, routing=routing,
            summary=s, text=owner_presentation.present_what_to_do(s),
            limitations=owner_presentation.owner_limitations(s.limitations))

    def _what_to_trust(self, question):
        routing = analyst_roles.RoleRouting(
            roles=(analyst_roles.RISK_DQ_ANALYST, analyst_roles.DATA_ANALYST),
            reasons={analyst_roles.RISK_DQ_ANALYST: "the question is about trust posture",
                     analyst_roles.DATA_ANALYST: "metric-level reliability"},
            primary=analyst_roles.RISK_DQ_ANALYST)

        buckets = {}
        for mid in self.registry.all_ids():
            lv = self.gate.authorize(mid).effective_level
            buckets.setdefault(lv, []).append(mid)

        def _name(mid):
            spec = self.registry.get(mid)
            return spec.display_name or spec.semantic_name

        return AnalystAnswer(
            question=question, owner_intent=INTENT_WHAT_TO_TRUST, routing=routing,
            text=owner_presentation.present_what_to_trust(buckets, _name),
            metric_ids=tuple(self.registry.all_ids()),
            limitations=("Reliability labels are the records' own, unchanged by this wording.",))

    # -- explainability --------------------------------------------------------------------------------

    def explain(self, answer: AnalystAnswer):
        """'Why are you saying this?' -- the evidence chain behind an answer already given."""
        if answer.chain is not None:
            return answer.chain
        if answer.ask_result is not None:
            return explainability.build(answer.ask_result, answer.routing)
        return None

    def reset(self):
        self.llm.reset()
