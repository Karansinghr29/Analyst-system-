"""
llm_interface.py -- Phase 4. The orchestration layer that sits ABOVE the deterministic system.

    User Question
      -> LLM Question Understanding      (this module, via a provider)
      -> structured contract validation  (structured_output.py -- INVALID NEVER EXECUTES)
      -> conversation context            (conversation_context.py -- never overrides explicit)
      -> deterministic AnalyticsPlan     (Phase 3)
      -> Trust Gate                      (Phase 2, authoritative)
      -> deterministic Analytics Execution (Phase 2)
      -> Validator                       (Phase 2)
      -> Business Reasoning              (business_reasoning.py)
      -> Answer Contract                 (answer_renderer.py skeleton)
      -> LLM verbalization               (guarded; falls back to the owner draft)
      -> Final answer

The LLM touches this pipeline in exactly two places, and both are fenced:

  1. It proposes a CONCEPT and an INTENT. Everything else about the plan -- family expansion,
     dimension validation, time resolution, coverage guards, trust -- is re-derived
     deterministically by Phase 3/2 from the semantic layer. A proposal that names an unknown
     metric, concept, or dimension is rejected before any execution.

    2. It restates a finished owner-facing draft in business English. That restatement is
       checked against the contract skeleton and discarded wholesale if it introduces a number,
       drops a caveat, collapses a SHOW_BOTH family, produces a BLOCK headline, or surfaces PII.

There is no third place. The model cannot query, calculate, or override a trust verdict, because
no code path exists through which it could.
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine.analytics_planner import AnalyticsPlanner
from engine.question_understanding import QuestionUnderstander
from engine import prompt_contracts, structured_output, business_reasoning, answer_renderer
from engine.conversation_context import ConversationContext, Turn
from engine.clarification_manager import ClarificationManager
from engine.llm_provider import LLMProvider, LLMUnavailable, default_provider
from engine.intent_models import READY, BLOCKED, NEEDS_CLARIFICATION, NOT_DETERMINABLE, REJECTED
from engine import conversation_state as cs
from engine.result import NOT_DETERMINABLE_TEXT as _ND
from engine import decision_support as ds_mod


@dataclass
class AskResult:
    """Everything one turn produced. `text` is what a user sees; every other field exists so the
    turn is auditable end to end."""
    question: str
    text: str = ""
    status: str = ""
    trust_level: str = ""
    metric_ids: tuple = ()
    plan: object = None
    answers: tuple = ()
    reasoning: object = None
    rendered: object = None
    clarification: object = None
    llm_request: object = None
    contract_violations: tuple = ()
    guard_violations: tuple = ()
    inherited_context: tuple = ()
    executed: bool = False
    repair_attempted: bool = False
    provider_error: str = ""

    # Phase 5
    clarification_state: str = ""
    definition_selection: object = None
    decision_support: object = None
    # The period comparison this answer was built from, when it was one. Kept so
    # the owner-facing explanation can name the periods the question ASKED for.
    change: object = None
    # A completed deterministic forecast, when the question asked for one.
    forecast: object = None
    insights: tuple = ()

    @property
    def refused(self):
        return not self.executed


def _is_capability_guidance(reason):
    """True when a NOT_DETERMINABLE reason already ANSWERS the owner rather than needing a
    question back.

    Some gaps are answerable by narrowing the period, and for those a clarification is the right
    turn. Others are structural -- the measure has no month-scoped series at all -- and no answer
    the owner could give would change that. The planner already writes the honest explanation for
    those, naming what it can show instead, and replacing it with "I couldn't turn that into a
    well-formed analysis request" threw away the useful half and blamed the owner's phrasing for
    a limit of the evidence.

    Matched on the two things that make it guidance rather than a gap: it says the series does
    not exist, and it says what to ask instead.
    """
    text = (reason or "").lower()
    if not text:
        return False
    structural = ("month-scoped series" in text or "no monthly series" in text
                  or "monthly evidence" in text)
    suggests = "ask for" in text or "for example" in text
    return structural and suggests


class LLMInterface:
    def __init__(self, provider: LLMProvider = None, registry: SemanticRegistry = None,
                 planner: AnalyticsPlanner = None, executor: MetricExecutor = None,
                 verbalize: bool = True, insight_engine=None):
        self.registry = registry or SemanticRegistry()
        self.provider = provider or default_provider()
        self.gate = TrustGate(self.registry)
        self.planner = planner or AnalyticsPlanner(
            registry=self.registry, gate=self.gate,
            understander=QuestionUnderstander(self.registry))
        self.executor = executor or MetricExecutor(registry=self.registry, gate=self.gate)
        self.clarifier = ClarificationManager(self.registry)
        self.context = ConversationContext()
        self.verbalize = verbalize
        self.insight_engine = insight_engine
        self._insight_cache = None

    # -- the single entry point -----------------------------------------------------------------

    def ask(self, question) -> AskResult:
        from engine.question_normalize import normalize_owner_question

        # Role address labels must not change business routing. Normalize once; every downstream
        # stage (extract, plan, follow-up inherit) sees the cleaned question.
        cleaned, _stripped = normalize_owner_question(question or "")
        working = cleaned if cleaned.strip() else (question or "")
        self._last_change = None
        result = AskResult(question=question)

        # ---- stage 0: multi-turn state (Phase 5) --------------------------------------------
        # An open clarification is interpreted BEFORE anything else, so that a reply meant as an
        # answer to our question is not re-read as a brand-new question. A reply that does not
        # decisively choose leaves the clarification open -- it is never taken as permission to
        # pick for the user.
        if self.context.awaiting_clarification:
            pc = self.context.answer_clarification(question)
            result.clarification_state = pc.state
            if pc.state == cs.CLAR_ANSWERED:
                self.context.close_clarification()
                if pc.resolved_metric_id:
                    return self._answer_resolved_clarification(question, pc, result)
                # A clarification between competing DEFINITIONS resolves to a label, not to a
                # metric_id (the definitions live inside one metric). Convert the answer into
                # the same explicit DefinitionSelection an in-line selection would produce, so
                # both routes to a user's choice are recorded identically.
                sel = self._selection_from_clarification(pc, question)
                if sel is not None:
                    return self._answer_with_selected_definition(question, sel, result)
            elif pc.state == cs.CLAR_REJECTED:
                result.status = NEEDS_CLARIFICATION
                result.text = (
                    "I can't choose between these for you: they are genuinely different "
                    "definitions that produce different numbers, and picking one would be a "
                    "business decision rather than an analytical one. Here is what each means, "
                    "if that helps you decide:\n" + "\n".join(f"  - {o}" for o in pc.options))
                self._record(question, None, None, result)
                return result
            elif pc.state == cs.CLAR_STILL_AMBIGUOUS:
                # A brand-new owner question must not be trapped by a prior clarification.
                if self._looks_like_fresh_question(working, pc):
                    self.context.close_clarification()
                    # Fall through into normal understanding/planning for this question.
                else:
                    result.status = NEEDS_CLARIFICATION
                    # The pending clarification travels with the result. Without it the
                    # explanation layer had no structured clarification to read and fell back
                    # to the answer text, so asking "why?" while a clarification was open got
                    # the re-ask pasted into the Why panel -- options, numbering and all --
                    # under a heading saying the question could not be answered.
                    result.clarification = pc
                    result.clarification_state = cs.CLAR_STILL_AMBIGUOUS
                    result.text = self._re_ask(pc)
                    self._record(question, None, None, result)
                    return result

        # An explicit definition selection may narrow a family the user has ALREADY been shown.
        selection, ambiguous_candidates = self._detect_definition_selection(question)
        if selection is not None:
            return self._answer_with_selected_definition(question, selection, result)
        if ambiguous_candidates:
            # The user tried to select, but their words fit more than one definition. Ask which.
            prev = self.context.last
            labels = tuple(prev.definitions_shown[i] for i in ambiguous_candidates
                           if i < len(prev.definitions_shown))
            clar = self.clarifier.from_ambiguous_selection(labels, question)
            result.status = NEEDS_CLARIFICATION
            result.clarification = clar
            result.clarification_state = cs.CLAR_STILL_AMBIGUOUS
            result.text = clar.render()
            self.context.open_clarification(clar, ())
            self._record(question, None, None, result)
            return result

        # ---- stage 1: LLM question understanding -------------------------------------------
        # Deterministic capability short-circuits that must not depend on the model proposal.
        from engine import time_resolution as timeres
        from engine import concept_map
        from engine import owner_presentation
        forecast_asked, _forecast_label = timeres.asks_unsupported_forecast(working)

        # Revenue forecasting IS supported -- deterministically, by engine/forecasting.py, whose
        # method was selected by out-of-sample backtest. It is handled before the generic
        # forecast refusal below, which still stands for every concept that has no validated
        # model. The model computes nothing here: the figures, intervals and error metrics are
        # already final when the wording layer sees them.
        from engine import forecasting
        # A month the records already cover is a historical question even when the owner wrote
        # "forecast". Resolved once, here, because both the forecast branch and the generic
        # forecast refusal below have to agree about it -- otherwise "forecast revenue for June
        # 2026" declines to project (rightly) and is then refused as an unsupported forecast,
        # when the recorded June figure was available the whole time.
        named_month = forecasting.parse_target_month(working)
        names_recorded_month = bool(named_month
                                    and forecasting.horizon_for_period(named_month) <= 0)
        if not names_recorded_month and (forecast_asked or forecasting.asks_forecast(working)):
            matched = concept_map.match(working)
            names = [c.name for c, _ in matched]
            # "revenue at 75% occupancy" matches BOTH concepts. It is a revenue question with an
            # occupancy condition, so revenue anywhere in the match is enough to route it here;
            # the scenario itself is then refused on its own evidence.
            if "revenue" in names:
                # A named month is resolved FIRST and answered as itself. Counting months
                # forward applies only when the question counted: "October 2026" and "the next
                # 3 months" are different requests, and reading the first as the second
                # returned August's projection under October's question.
                #
                # `forecast_month` returns None when the month named is already recorded. That
                # is a historical question wearing forecast words, and the recorded figure is
                # the better answer, so this branch declines it and the ordinary period path
                # below takes over.
                if forecasting.asks_scenario(working):
                    forecast = forecasting.scenario_forecast()
                elif named_month:
                    forecast = forecasting.forecast_month(named_month)
                else:
                    horizon, _phrase = forecasting.parse_horizon(working)
                    forecast = forecasting.forecast_revenue(horizon)

                if forecast is not None:
                    result.status = READY if forecast.available else NOT_DETERMINABLE
                    # The forecast's target is invoiced revenue (SUM of invoice totals by billing
                    # month), so it is attributed to the invoice billed-amount metric and carries
                    # that metric's trust posture -- not ledger revenue's.
                    result.metric_ids = ("M.INV.001",)
                    # The gate authorizes the metric; it does not authorize a projection that
                    # was never produced. A refused horizon carrying a trust badge would present
                    # a refusal as a trustworthy answer.
                    result.trust_level = (
                        self.gate.authorize("M.INV.001").effective_level if forecast.available
                        else NOT_DETERMINABLE)
                    result.text = owner_presentation.present_forecast(forecast, working)
                    result.forecast = forecast
                    self._record(working, None, None, result)
                    return result

        if forecast_asked and not names_recorded_month and concept_map.match(working):
            plan = self.planner.plan(working)
            result.plan = plan
            result.status = plan.status
            result.trust_level = plan.trust_level
            result.metric_ids = plan.metric_ids
            from engine import owner_presentation
            result.text = owner_presentation.present_metric_answer(plan, (), None)
            self._record(working, None, plan, result)
            return result

        outcome, raw, repaired, provider_error = self._extract(working)
        result.repair_attempted = repaired
        result.provider_error = provider_error

        if provider_error:
            # A provider failure degrades to a refusal, never to a guess.
            result.status = NOT_DETERMINABLE
            result.text = (f"The language layer is unavailable ({provider_error}), so this "
                           f"question could not be interpreted. No figure is produced, because "
                           f"the system never guesses at an unread question.")
            return result

        # ---- stage 2: contract validation. INVALID NEVER EXECUTES. -------------------------
        if not outcome.valid:
            # One exception, and it is not a weakening of the rule: a bare follow-up like
            # "Why?" is genuinely uninterpretable standalone, so the model is RIGHT to reject
            # it. Given the previous turn it is perfectly interpretable, and the owner means it
            # as a follow-up rather than a new question. The seed below carries nothing from
            # the model's rejected output -- it is empty, and `resolve()` fills it from the
            # previous turn through the same additive inheritance every follow-up uses. The
            # result is planned and gated from scratch, so nothing is executed that the
            # inherited question would not itself have been allowed to execute.
            seed = self.context.followup_seed(working)
            if seed is None and concept_map.match(working):
                # Model proposal failed, but the deterministic concept map can resolve the
                # question. Prefer answering over a generic "rephrase" clarification.
                plan = self.planner.plan(working)
                result.plan = plan
                result.status = plan.status
                result.trust_level = plan.trust_level
                result.metric_ids = plan.metric_ids
                if plan.status == NOT_DETERMINABLE:
                    from engine import owner_presentation
                    result.text = owner_presentation.present_metric_answer(plan, (), None)
                    self._record(working, None, plan, result)
                    return result
                if plan.status in (NEEDS_CLARIFICATION, REJECTED):
                    clar = self.clarifier.for_plan(plan)
                    result.clarification = clar
                    result.text = clar.render() if clar else plan.not_determinable_reason
                    if clar is not None:
                        self._open_plan_clarification(plan, clar, working)
                        result.clarification_state = cs.CLAR_REQUIRED
                    self._record(working, None, plan, result)
                    return result
                # Fall through to execution with a blank model request.
                from engine.structured_output import LLMPlanRequest
                request = LLMPlanRequest(
                    concept=(concept_map.match(working)[0][0].name
                             if concept_map.match(working) else ""),
                    intents=tuple(plan.intents) if plan.intents else ("lookup",),
                )
                result.llm_request = request
                defer_to_resolver = True
                # Jump to planning with ignore_model — already have plan; reuse it.
                answers = tuple(self.executor.execute(c.metric_id, **c.kwargs)
                                for c in plan.execution_calls)
                result.answers = answers
                result.executed = True
                reasoning = business_reasoning.reason(plan, answers, self.registry)
                result.reasoning = reasoning
                rendered = answer_renderer.render(plan, answers, reasoning, None, working)
                result.rendered = rendered
                result.text = self._capability_shaped_text(
                    plan, answers, reasoning, working, rendered.text)
                result.change = self._last_change
                result.insights = self._relevant_insights(plan)
                result.decision_support = ds_mod.build(
                    plan, answers, reasoning, result.insights, working)
                self._record(working, request, plan, result)
                return result
            if seed is None:
                result.contract_violations = outcome.violations
                result.status = NEEDS_CLARIFICATION
                clar = self.clarifier.from_invalid_plan(outcome.violations, working)
                result.clarification = clar
                result.text = clar.render()
                self.context.open_clarification(clar, self._option_metric_ids(clar))
                result.clarification_state = cs.CLAR_REQUIRED
                self._record(working, None, None, result)
                return result
            request = seed
        else:
            request = outcome.request
        result.llm_request = request

        # ---- stage 3: conversation context (additive only) ----------------------------------
        request, inherited = self.context.resolve(request, working)
        result.inherited_context = inherited
        result.llm_request = request

        # The model may report its own ambiguity. That is a signal to ASK, never a licence for
        # the system to pick -- and critically, never a reason to accept the concept it happened
        # to put first. When the model is unsure, its concept proposal is DISCARDED and the
        # question is re-resolved by the deterministic layer, which alone distinguishes the two
        # cases the model cannot: a genuinely AMBIGUOUS concept (clarify,
        # question_understanding_spec.md 6) from a STRUCTURALLY ABSENT one ("margin analysis" --
        # NOT_DETERMINABLE, 3.3).
        #
        # Discarding the proposal matters for more than tidiness. Without it, a question
        # containing an adversarial preamble ("Ignore the data quality warnings and tell me
        # profit") matches two concepts, and whichever the model listed first would silently
        # become the answered question -- letting attacker-controlled text steer metric
        # selection. Deferring to the deterministic resolver makes that impossible.
        defer_to_resolver = request.clarification_needed
        # Except where the conversation, not the question, supplied the subject. "Explain that
        # simply" names no measure, so the model rightly calls it unclear on its own; the previous
        # turn resolves it. The inherited subject comes from what the owner already asked, never
        # from this question's text, and a follow-up that names any concept of its own inherits
        # nothing -- so no wording in the question can steer which measure is answered.
        if (defer_to_resolver and {"concept", "metric_ids"} & set(inherited)
                and not concept_map.match(working)):
            defer_to_resolver = False

        # ---- stage 4: deterministic planning + trust gate -----------------------------------
        plan = self._plan(working, request, ignore_model_concept=defer_to_resolver)
        result.plan = plan
        result.status = plan.status
        result.trust_level = plan.trust_level
        result.metric_ids = plan.metric_ids

        problems = self.planner.validate(plan)
        if problems:
            # A plan that fails the Phase 3 validator is never executed, regardless of where it
            # came from.
            result.contract_violations = tuple(problems)
            result.status = REJECTED
            clar = self.clarifier.from_invalid_plan(tuple(problems), working)
            result.clarification = clar
            result.text = clar.render()
            self._record(working, request, plan, result)
            return result

        if plan.status in (NEEDS_CLARIFICATION, REJECTED):
            clar = self.clarifier.for_plan(plan)
            result.clarification = clar
            result.text = clar.render() if clar else plan.not_determinable_reason
            if clar is not None:
                self._open_plan_clarification(plan, clar, working)
                result.clarification_state = cs.CLAR_REQUIRED
            self._record(working, request, plan, result)
            return result

        if plan.status == NOT_DETERMINABLE:
            # Forecast / capability-gap notes are answers, not clarifications.
            if getattr(plan, "forecast_note", "") or (
                    plan.not_determinable_reason
                    and "forecast" in (plan.not_determinable_reason or "").lower()) or (
                    _is_capability_guidance(plan.not_determinable_reason)):
                from engine import owner_presentation
                result.text = owner_presentation.present_metric_answer(plan, (), None)
                self._record(working, request, plan, result)
                return result
            clar = self.clarifier.for_plan(plan)
            if clar is not None:
                # A coverage limit is answerable by NARROWING the period, so the turn is a
                # question to the user, not a refusal. Report it as such: leaving the status at
                # NOT_DETERMINABLE while showing clarification text would claim the exact phrase
                # "Not determinable from exported evidence." had been used when it had not.
                result.status = NEEDS_CLARIFICATION
                result.clarification = clar
                result.text = clar.render()
            else:
                from engine import owner_presentation
                result.text = owner_presentation.present_metric_answer(plan, (), None)
            self._record(working, request, plan, result)
            return result

        # ---- stage 5: deterministic execution + validation ----------------------------------
        answers = tuple(self.executor.execute(c.metric_id, **c.kwargs)
                        for c in plan.execution_calls)
        result.answers = answers
        result.executed = True

        # ---- stage 6: business reasoning ----------------------------------------------------
        reasoning = business_reasoning.reason(plan, answers, self.registry)
        result.reasoning = reasoning

        # ---- stage 7: answer contract + guarded verbalization -------------------------------
        verbalized = None
        if self.verbalize:
            verbalized = self._verbalize(plan, answers, reasoning, working)

        rendered = answer_renderer.render(plan, answers, reasoning, verbalized, working)
        result.rendered = rendered
        result.text = rendered.text
        result.guard_violations = rendered.guard_violations

        # Capability-shaped presentation for driver/comparison/trend/anomaly/forecast notes.
        result.text = self._capability_shaped_text(
            plan, answers, reasoning, working, result.text)
        result.change = self._last_change

        # ---- stage 8: decision support (Phase 5) --------------------------------------------
        result.insights = self._relevant_insights(plan)
        result.decision_support = ds_mod.build(plan, answers, reasoning, result.insights,
                                               working)

        self._record(working, request, plan, result)
        return result

    @staticmethod
    def _re_ask(pending):
        """The open question, asked again after a reply that did not answer it.

        A choice between competing definitions keeps its numbered, self-describing options: the
        owner is deciding which evidence-backed figure stands, and each option has to say what it
        is. Any other open question is asked again in one sentence.
        """
        from engine import clarification_manager as cm
        options = tuple(pending.options or ())
        if pending.trigger != cm.TRIGGER_CONFLICTING_DEFINITIONS and cm.is_subject_menu(options):
            return (f"I need one more detail before I answer: which area do you mean -- "
                    f"{cm.inline_choices(options).lower()}?")
        lead = (pending.question or "").strip()
        if pending.trigger == cm.TRIGGER_CONFLICTING_DEFINITIONS:
            lead = ("Before I can explain this, I need you to choose which definition to use. "
                    "They are both backed by the records and give different figures, so I "
                    "won't choose for you:")
        return lead + "\n" + "\n".join(f"  {i + 1}. {o}" for i, o in enumerate(options))

    def _looks_like_fresh_question(self, text, pending):
        """True when the reply is a new owner question, not an attempt to pick a clarification option."""
        import re
        from engine import concept_map
        from engine.conversation_context import ConversationContext
        q = (text or "").strip().lower()
        if not q:
            return False
        # "Explain that simply" while a question is open refers to that question. Treating it as
        # new dropped the pending choice and asked the owner which measure they meant, as if the
        # conversation had not happened.
        if ConversationContext.looks_like_followup(q) and not concept_map.match(q):
            return False
        if re.fullmatch(r"[1-9]|cancel|latest.*|historical.*", q):
            return False
        for opt in getattr(pending, "options", ()) or ():
            ol = (opt or "").strip().lower()
            if q == ol or (len(q) >= 8 and q in ol):
                return False
        if concept_map.match(q):
            return True
        words = q.split()
        return len(words) >= 3 and not q[:1].isdigit()

    _last_change = None

    def _capability_shaped_text(self, plan, answers, reasoning, question, fallback_text):
        """Re-present when the plan asked for analysis that lookup prose does not answer."""
        from engine import owner_presentation
        from engine.intent_models import PLAN_DRIVER, PLAN_PERIOD_COMPARISON, PLAN_TREND, PLAN_ANOMALY
        from engine.change_detection import ChangeDetector, COMPARABLE_MONTHLY_METRICS
        from engine import concept_map

        if plan is None:
            return fallback_text
        if getattr(plan, "forecast_note", ""):
            return owner_presentation.present_metric_answer(plan, answers, reasoning)

        def _monthly_id(metric_id):
            if metric_id in COMPARABLE_MONTHLY_METRICS:
                return metric_id
            if plan.metric is not None:
                c = concept_map.concept(plan.metric.concept)
                if c is not None:
                    for alt in tuple(c.alternatives) + tuple(c.metric_ids):
                        if alt in COMPARABLE_MONTHLY_METRICS:
                            return alt
            return metric_id

        if plan.driver_requested or plan.plan_type == PLAN_DRIVER:
            mid = _monthly_id(plan.metric_ids[0] if plan.metric_ids else "")
            if mid:
                try:
                    from engine.root_cause import RootCauseAnalyzer
                    detector = ChangeDetector(self.registry, self.gate, self.executor)
                    analyzer = RootCauseAnalyzer(
                        self.registry, self.gate, self.executor, detector)
                    rc = analyzer.analyze(mid)
                except Exception:
                    rc = None
                return owner_presentation.present_driver_answer(
                    question, plan, answers, rc, reasoning)

        if plan.plan_type in (PLAN_PERIOD_COMPARISON, PLAN_TREND) or (
                plan.intents and ("comparison" in plan.intents or "trend" in plan.intents)):
            mid = _monthly_id(plan.metric_ids[0] if plan.metric_ids else "")
            if mid:
                detector = ChangeDetector(self.registry, self.gate, self.executor)
                cur = prev = None
                if plan.comparison is not None:
                    cur = getattr(plan.comparison.current, "start", None)
                    prev = getattr(plan.comparison.baseline, "start", None)
                component = None
                if plan.metric is not None:
                    component = {
                        "expenses": "expenses", "revenue": "revenue",
                        "profit": "net_profit",
                    }.get((plan.metric.concept or "").lower())
                change = detector.detect(
                    mid, current_period=cur, previous_period=prev,
                    series_component=component)
                # `_capability_shaped_text` has no handle on the AskResult, so the change is
                # parked here and picked up by `ask()` immediately after this returns. Reset at
                # the top of every ask, so a stale one can never attach to a later answer.
                self._last_change = change
                text = owner_presentation.present_comparison_answer(change, plan)
                if plan.plan_type == PLAN_TREND or (plan.intents and "trend" in plan.intents):
                    if change.detected:
                        text = ("Trend direction from the latest comparable periods:\n" + text)
                return text

        if plan.plan_type == PLAN_ANOMALY or (plan.intents and "anomaly" in plan.intents):
            return owner_presentation.present_anomaly_answer(plan, answers)
        return fallback_text

    def _relevant_insights(self, plan):
        """Insights whose trigger metrics overlap this plan's. Generated lazily and cached:
        the candidate set is a pure function of the immutable evidence, so it never changes
        within a session."""
        if self._insight_cache is None:
            if self.insight_engine is None:
                self._insight_cache = ()
            else:
                self._insight_cache = self.insight_engine.generate()
        return tuple(i for i in self._insight_cache
                     if set(i.trigger_metric_ids) & set(plan.metric_ids))

    # -- Phase 5: multi-turn paths ----------------------------------------------------------------

    def _last_turn_with_definitions(self):
        """The most recent turn that actually showed a competing-definition set. Clarification
        turns record none of their own, so a selection made in reply to a clarification has to
        reach past them to find what the user was shown."""
        for turn in reversed(self.context.turns):
            if turn.definitions_shown and turn.trust_level in ("SHOW_BOTH", "BLOCK"):
                return turn
        return None

    def _selection_from_clarification(self, pc, question):
        """Turn an answered definition-clarification into an explicit DefinitionSelection."""
        prev = self._last_turn_with_definitions()
        if prev is None or not pc.resolution:
            return None
        if pc.resolution not in prev.definitions_shown:
            return None
        idx = prev.definitions_shown.index(pc.resolution)
        concept = prev.request.concept if prev.request is not None else ""
        return cs.DefinitionSelection(
            concept=concept or (prev.metric_ids[0] if prev.metric_ids else "this measure"),
            metric_id=(prev.metric_ids[idx] if idx < len(prev.metric_ids) else ""),
            definition_label=pc.resolution,
            selected_at_turn=len(self.context.turns),
            user_text=question,
            alternatives_shown=tuple(prev.definitions_shown),
        )

    def _detect_definition_selection(self, question):
        """An explicit user choice of one competing definition they were ALREADY shown.

        Three conditions must all hold, and the third is the important one: the user must have
        been shown the alternatives in a previous turn. A selection cannot be made for a family
        the user has never seen, which is what stops this path from becoming a way to request a
        pre-narrowed answer and bypass SHOW_BOTH entirely.
        """
        prev = self.context.last
        if prev is None or not prev.definitions_shown:
            return None, ()
        if prev.trust_level not in ("SHOW_BOTH", "BLOCK"):
            return None, ()

        idx, candidates = cs.detect_selection_attempt(question, prev.definitions_shown)
        if idx is None:
            # An AMBIGUOUS attempt is returned to the caller so it can ask which definition was
            # meant. Treating it as "no selection" would let an explicit instruction fall through
            # to an ordinary answer, unacknowledged -- and treating it as a selection would pick
            # for the user, which is the silent narrowing the trust policy forbids.
            return None, candidates

        concept = ""
        if prev.request is not None and prev.request.concept:
            concept = prev.request.concept

        return cs.DefinitionSelection(
            concept=concept or (prev.metric_ids[0] if prev.metric_ids else "this measure"),
            metric_id=(prev.metric_ids[idx] if idx < len(prev.metric_ids) else ""),
            definition_label=prev.definitions_shown[idx],
            selected_at_turn=len(self.context.turns),
            user_text=question,
            alternatives_shown=tuple(prev.definitions_shown),
        ), ()

    def _answer_with_selected_definition(self, question, selection, result):
        """Present ONE definition, because the user explicitly chose it.

        The narrowing is presentational, and the answer says so. The competing definitions are
        still computed and still disclosed -- selection changes which figure leads, never the
        fact that the conflict exists (insight_generation_spec.md 5 / ai_trust_policy.md).
        """
        self.context.select_definition(selection)
        result.definition_selection = selection

        # Reach past any intervening clarification turns to the turn that actually showed the
        # competing definitions -- that is where the plan and its execution calls live. Using
        # `context.last` here fails whenever the user selected in reply to a clarification,
        # because a clarification turn carries no plan of its own.
        prev = self._last_turn_with_definitions() or self.context.last
        plan = prev.plan if prev is not None else None
        if plan is None or not plan.execution_calls:
            result.status = NOT_DETERMINABLE
            result.text = (f"There is no previous set of definitions to select from. "
                           f"{_ND}")
            return result

        answers = tuple(self.executor.execute(c.metric_id, **c.kwargs)
                        for c in plan.execution_calls)
        result.plan = plan
        result.answers = answers
        result.executed = True
        result.trust_level = plan.trust_level
        result.metric_ids = plan.metric_ids
        result.status = plan.status

        chosen = None
        for a in answers:
            for r in a.results:
                if r.definition_label == selection.definition_label:
                    chosen = (a, r)
        lines = [selection.disclosure()]
        if chosen is not None:
            a, r = chosen
            lines.append(f"SELECTED DEFINITION [{r.metric_id} / {r.definition_label}]: "
                         f"{r.value} {r.unit}".rstrip())
            lines.append(f"  EVIDENCE: {', '.join(str(e) for e in r.evidence_sources[:6])}")
            lines.append(f"  VALIDATION: {r.validation_status}")
            lines.append(f"  CONFIDENCE: {r.confidence}")
        lines.append("ALL COMPETING DEFINITIONS REMAIN:")
        for a in answers:
            for r in a.results:
                lines.append(f"  - {r.definition_label}: {r.value}")
        if plan.required_disclosures:
            lines.append(f"CONFLICTS: {', '.join(plan.required_disclosures)}")

        result.text = "\n".join(lines)
        self._record(question, prev.request if prev else None, plan, result)
        return result

    def _answer_resolved_clarification(self, question, pending, result):
        """The user chose one of the metrics we offered. Re-enter the pipeline with that
        metric_id -- through the normal deterministic path, so the Trust Gate still applies.

        Period/concept come from the ORIGINAL question that triggered clarification, never
        from the selection reply ("1", option text), which would silently drop time scope.
        """
        orig = (getattr(pending, "original_question", "") or "").strip() or question
        plan = self.planner.plan(orig, metric_id=pending.resolved_metric_id)
        result.plan = plan
        result.status = plan.status
        result.trust_level = plan.trust_level
        result.metric_ids = plan.metric_ids
        # What the owner chose, as the structured interpretation of this turn. Without it the
        # next "Explain that" had no subject to refer back to, although the owner had just
        # named one. It carries the chosen measure only -- no figure and no posture -- and a
        # follow-up that inherits it is planned and gated from scratch.
        from engine.structured_output import LLMPlanRequest
        request = (LLMPlanRequest(intent=tuple(plan.intents) or ("lookup",),
                                  metric_ids=(pending.resolved_metric_id,))
                   if pending.resolved_metric_id else None)
        result.llm_request = request

        if plan.status not in (READY, BLOCKED) or not plan.execution_calls:
            from engine import owner_presentation
            result.text = owner_presentation.present_metric_answer(
                plan, (), None) if plan.status == NOT_DETERMINABLE else (
                plan.not_determinable_reason or "That selection could not be executed.")
            self._record(orig, request, plan, result)
            return result

        answers = tuple(self.executor.execute(c.metric_id, **c.kwargs)
                        for c in plan.execution_calls)
        reasoning = business_reasoning.reason(plan, answers, self.registry)
        from engine import owner_presentation
        result.answers = answers
        result.reasoning = reasoning
        result.rendered = answer_renderer.render(plan, answers, reasoning, None, orig)
        result.text = self._capability_shaped_text(
            plan, answers, reasoning, orig, result.rendered.text)
        result.change = self._last_change
        result.executed = True
        result.decision_support = ds_mod.build(plan, answers, reasoning, (), orig)
        self._record(orig, request, plan, result)
        return result

    # -- stages ---------------------------------------------------------------------------------

    def _extract(self, question):
        """LLM question understanding, with at most ONE bounded repair attempt. Returns
        (ValidationOutcome, raw_text, repaired, provider_error)."""
        prompt = prompt_contracts.build_extraction_prompt(
            question, self.registry, context_note=self.context.context_note())
        try:
            resp = self.provider.complete(
                prompt, system=prompt_contracts.EXTRACTION_SYSTEM, temperature=0.0)
        except LLMUnavailable as e:
            return None, "", False, str(e)

        outcome = structured_output.parse_and_validate(resp.text, self.registry)
        if outcome.valid or not outcome.repairable:
            return outcome, resp.text, False, ""

        repair = prompt_contracts.build_repair_prompt(
            question, resp.text, outcome.violations, self.registry)
        try:
            resp2 = self.provider.complete(
                repair, system=prompt_contracts.EXTRACTION_SYSTEM, temperature=0.0)
        except LLMUnavailable as e:
            return outcome, resp.text, True, str(e)

        return (structured_output.parse_and_validate(resp2.text, self.registry),
                resp2.text, True, "")

    def _plan(self, question, request, ignore_model_concept=False):
        """Hand the model's proposal to the DETERMINISTIC Phase 3 layer. The model contributes
        a concept (or a metric_id); Phase 3 re-derives family membership, dimensions, time, and
        coverage from the semantic layer, and Phase 2 supplies the trust verdict.

        With `ignore_model_concept`, nothing from the model is used for resolution at all --
        Phase 3 resolves the question text on its own. This is the path taken whenever the model
        signalled uncertainty."""
        if ignore_model_concept:
            return self.planner.plan(self._question_with_context(question, request))

        concept = request.concept or None
        metric_id = None
        if not concept and request.metric_ids:
            metric_id = request.metric_ids[0]

        effective_question = self._question_with_context(question, request)
        return self.planner.plan(effective_question, concept_name=concept, metric_id=metric_id)

    @staticmethod
    def _question_with_context(question, request):
        """Phase 3 parses time, dimensions and INTENT from question TEXT, so a follow-up whose
        meaning lives in the previous turn must be expanded before Phase 3 sees it. This is
        reference resolution -- supplying what "why?" refers to -- not a change of meaning:
        every added word comes from the already-validated contract object, never from the model.

        Expansion is strictly additive. An explicit value in the question is never replaced, so
        a stated period still wins at parse time.
        """
        q = question
        stripped = (question or "").strip().lower().rstrip("?.! ")
        # How the owner wants it said changes nothing about what "that" refers to: "Explain that
        # simply" is still "Explain that".
        for softener in (" more simply", " in simple terms", " in plain english", " simply",
                         " please", " for me", " again"):
            if stripped.endswith(softener):
                stripped = stripped[:-len(softener)].rstrip(" ,")

        # A "why" follow-up carries its subject only by reference -- "Why was it lower?" names
        # no measure at all. Left unexpanded, Phase 3 resolves no metric and the turn dies as
        # NOT_DETERMINABLE, even though the previous turn established exactly what "it" is.
        # Substituting the inherited concept is reference resolution, not reinterpretation: the
        # concept comes from the already-validated contract object, never from the model.
        #
        # Bare "Explain that." / "Explain." are the same kind of reference: they name no
        # measure. Exact-match only -- "explain collections" must keep its own subject.
        bare_explain = stripped in (
            "explain", "explain that", "explain this", "tell me more",
            "what does that mean", "what caused it", "what caused that",
        )
        if stripped.startswith("why") or stripped in ("how so",) or bare_explain:
            subject = request.concept.replace("_", " ") if request.concept else ""
            # A measure the owner chose from a clarification is carried by id, not concept. The
            # id itself is handed to the planner separately; the text only needs the reference.
            if not subject and request.metric_ids:
                subject = "it"
            if subject and subject not in stripped:
                # Keep the user's own words -- they may carry direction ("lower", "higher") that
                # the reasoning layer uses -- and append the subject the question omitted.
                q = f"{question.rstrip('?. ')} -- why did {subject} change?"

        extra = []
        if request.time_range and request.time_range.lower() not in q.lower():
            extra.append(request.time_range)
        if not extra:
            return q
        return f"{q} ({' '.join(extra)})"

    def _verbalize(self, plan, answers, reasoning, question):
        from engine import owner_presentation
        owner_draft = owner_presentation.present_metric_answer(plan, answers, reasoning)
        prompt = prompt_contracts.build_verbalization_prompt(
            owner_draft, plan.trust_level, question)
        try:
            resp = self.provider.complete(
                prompt, system=prompt_contracts.VERBALIZATION_SYSTEM, temperature=0.0)
        except LLMUnavailable:
            return None          # fall back to the owner draft; never to an unverified answer
        return resp.text

    @staticmethod
    def _option_metric_ids(clarification):
        """Extract the metric_id each clarification option refers to, so a reply naming one
        can be matched back deterministically rather than by fuzzy text similarity."""
        import re
        out = []
        for opt in clarification.options:
            m = re.search(r"\b(M\.[A-Z]+\.\d+[A-Za-z]?)\b", opt)
            out.append(m.group(1) if m else "")
        return tuple(out)

    def _open_plan_clarification(self, plan, clar, working_question):
        """Open clarification while preserving (a) metric_ids from the raw plan options
        before owner-facing rephrasing strips them, and (b) the original owner question
        so period survives the selection turn."""
        raw_ids = ()
        if plan is not None and plan.clarification is not None:
            raw_ids = self._option_metric_ids(plan.clarification)
        ids = raw_ids if any(raw_ids) else self._option_metric_ids(clar)
        self.context.open_clarification(
            clar, ids, original_question=working_question or "")

    def _record(self, question, request, plan, result):
        definitions = ()
        if result.answers:
            definitions = tuple(r.definition_label
                                for a in result.answers for r in a.results)
        self.context.record(Turn(
            question=question, request=request, plan=plan, answer=result.rendered,
            trust_level=result.trust_level,
            metric_ids=tuple(result.metric_ids), definitions_shown=definitions,
        ))

    # -- convenience -------------------------------------------------------------------------------

    def reset(self):
        self.context.clear()
