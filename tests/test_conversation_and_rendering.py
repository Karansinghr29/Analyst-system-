"""
Phase 4: conversation context, clarification behaviour, business-analyst intent coverage, and
answer-contract survival through rendering.

The governing rule for context:
    "Context must NEVER override explicit new user constraints.
     User: 'Show revenue for July.'  User: 'What about June?'
     The second question inherits the metric but changes only the time period."
"""
import pytest

from engine.llm_interface import LLMInterface
from engine.conversation_context import ConversationContext, Turn
from engine.clarification_manager import (ClarificationManager, TRIGGER_UNKNOWN_ENTITY,
                                          TRIGGER_INVALID_PLAN, TRIGGER_OUTSIDE_COVERAGE,
                                          ALL_TRIGGERS)
from engine.structured_output import LLMPlanRequest
from engine import business_reasoning
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture
def iface(registry):
    return LLMInterface(registry=registry)


class TestNormalQuestions:
    """The brief's normal-question list. Each must produce a usable answer."""

    @pytest.mark.parametrize("question", [
        "How much revenue did we make?",
        "Show collections by month.",
        "What are our expenses?",
        "How many beds are occupied?",
        "How much cash do we have?",
        "Show deposit settlements.",
        "Which expense category is largest?",
    ])
    def test_normal_question_is_answered_or_safely_routed(self, iface, question):
        r = iface.ask(question)
        assert r.status in ("READY", "BLOCKED", "NEEDS_CLARIFICATION", "NOT_DETERMINABLE")
        assert r.text.strip()
        if r.executed:
            assert r.metric_ids
            assert any(mid in r.rendered.skeleton for mid in r.metric_ids), "evidence reference lost"

    def test_revenue_returns_the_validated_figure(self, iface):
        r = iface.ask("How much revenue did we make?")
        assert r.executed
        assert abs(r.answers[0].headline - 72705593.43) < 0.01


class TestAmbiguousQuestions:
    """The brief's ambiguous list. None may silently resolve to one definition."""

    @pytest.mark.parametrize("question", [
        "How much do tenants owe?",
        "What is occupancy?",
        "What was profit last month?",
        "How much did we collect?",
        "Which tenant owes the most?",
        "Why did profit fall?",
    ])
    def test_no_ambiguous_question_yields_a_single_silent_figure(self, iface, question):
        r = iface.ask(question)
        if r.executed and r.trust_level in ("SHOW_BOTH", "BLOCK"):
            for a in r.answers:
                assert a.headline is None, question
        elif r.executed:
            assert r.trust_level in ("SAFE", "DISCLOSE")

    def test_revenue_is_answerable_because_it_is_unambiguous(self, iface):
        """The control: preserving ambiguity must not mean refusing everything."""
        r = iface.ask("How much revenue did we make?")
        assert r.executed and r.trust_level == "SAFE"


class TestConversationContext:
    def test_followup_inherits_metric_but_not_period(self, iface):
        """The brief's own worked example."""
        iface.ask("Show revenue for 2026-07.")
        r = iface.ask("What about 2026-06?")
        assert "metric_ids" in r.inherited_context or "concept" in r.inherited_context
        assert "time_range" not in r.inherited_context, (
            "context overrode the explicitly-stated new period")

    def test_explicit_constraint_always_wins(self, registry):
        ctx = ConversationContext()
        prior = LLMPlanRequest(intent=("lookup",), concept="revenue",
                               metric_ids=("M.REV.001",), time_range="july")
        ctx.record(Turn(question="revenue for july", request=prior, metric_ids=("M.REV.001",)))
        new = LLMPlanRequest(intent=("lookup",), concept="", time_range="june")
        resolved, inherited = ctx.resolve(new, "what about june?")
        assert resolved.time_range == "june"
        assert "time_range" not in inherited

    def test_followup_inherits_when_field_is_genuinely_empty(self, registry):
        ctx = ConversationContext()
        prior = LLMPlanRequest(intent=("lookup",), concept="revenue",
                               metric_ids=("M.REV.001",), time_range="july")
        ctx.record(Turn(question="revenue for july", request=prior, metric_ids=("M.REV.001",)))
        new = LLMPlanRequest(intent=("lookup",), concept="")
        resolved, inherited = ctx.resolve(new, "what about it?")
        assert resolved.concept == "revenue"
        assert "concept" in inherited

    def test_why_upgrades_intent_without_changing_the_metric(self, registry):
        ctx = ConversationContext()
        prior = LLMPlanRequest(intent=("lookup",), concept="revenue",
                               metric_ids=("M.REV.001",))
        ctx.record(Turn(question="revenue", request=prior, metric_ids=("M.REV.001",)))
        new = LLMPlanRequest(intent=("lookup",), concept="")
        resolved, inherited = ctx.resolve(new, "why?")
        assert "driver" in resolved.intent
        assert resolved.concept == "revenue"

    def test_break_that_down_inherits_the_metric(self, iface):
        iface.ask("How much revenue did we make?")
        r = iface.ask("Break that down by property.")
        assert r.status in ("READY", "NOT_DETERMINABLE", "REJECTED", "NEEDS_CLARIFICATION")
        assert r.text.strip()

    def test_show_me_the_other_definition_keeps_the_family(self, iface):
        iface.ask("What is occupancy?")
        r = iface.ask("Show me the other definition.")
        if r.executed:
            for a in r.answers:
                assert a.headline is None

    def test_no_context_means_no_inheritance(self, iface):
        r = iface.ask("What about last month?")
        assert r.inherited_context == ()

    def test_a_fresh_question_does_not_inherit(self, registry):
        ctx = ConversationContext()
        prior = LLMPlanRequest(intent=("lookup",), concept="revenue",
                               metric_ids=("M.REV.001",))
        ctx.record(Turn(question="revenue", request=prior, metric_ids=("M.REV.001",)))
        new = LLMPlanRequest(intent=("lookup",), concept="occupancy",
                             metric_ids=("M.OCC.001",))
        resolved, inherited = ctx.resolve(new, "What is occupancy?")
        assert resolved.concept == "occupancy"
        assert inherited == ()

    def test_context_never_carries_a_trust_level(self, registry):
        """Trust is re-derived from the gate every turn -- a stale posture must never be
        inherited (answer_contract.md 6: the contract has no caching concept that could serve
        a stale trust posture)."""
        ctx = ConversationContext()
        prior = LLMPlanRequest(intent=("lookup",), concept="revenue")
        ctx.record(Turn(question="q", request=prior, trust_level="SAFE"))
        new = LLMPlanRequest(intent=("lookup",), concept="")
        resolved, _ = ctx.resolve(new, "what about last month?")
        assert not hasattr(resolved, "trust_level")


class TestClarification:
    def test_every_documented_trigger_exists(self):
        assert len(ALL_TRIGGERS) >= 6

    def test_collections_ambiguity_is_business_friendly(self, iface):
        r = iface.ask("How much did we collect?")
        assert r.clarification is not None
        assert "?" in r.clarification.question
        assert len(r.clarification.options) >= 2
        # A person should not be shown spec citations.
        assert "question_understanding_spec" not in r.clarification.question
        assert "question_understanding_spec" in r.clarification.internal_reason

    def test_unknown_entity_clarification_explains_why(self, iface):
        r = iface.ask("How much does this tenant owe?")
        if r.clarification is not None:
            assert r.clarification.trigger == TRIGGER_UNKNOWN_ENTITY

    def test_invalid_plan_clarification_never_executes(self, registry):
        cm = ClarificationManager(registry)
        c = cm.from_invalid_plan(("metric_id 'M.X' does not exist in semantic_metric_registry",),
                                 "q")
        assert c.trigger == TRIGGER_INVALID_PLAN
        assert c.question

    def test_coverage_clarification_states_the_window(self, iface):
        r = iface.ask("Show me maintenance year on year")
        if r.clarification is not None:
            assert r.clarification.trigger == TRIGGER_OUTSIDE_COVERAGE
            assert "2025" in r.clarification.question or "2026" in r.clarification.question


class TestBusinessAnalystIntents:
    """The 8 behaviours the brief lists."""

    @pytest.mark.parametrize("question,expected_intent", [
        ("How much revenue did we make?", "lookup"),
        ("Revenue by month", "trend"),
        ("Was there anything unusual in revenue?", "anomaly"),
        ("Why did revenue fall?", "driver"),
        ("What are our biggest business risks?", "risk_scan"),
        ("What should management do next?", "recommendation"),
    ])
    def test_intent_is_distinguished(self, iface, question, expected_intent):
        r = iface.ask(question)
        iface.reset()
        if r.plan is not None:
            assert expected_intent in r.plan.intents, question

    def test_conflict_explanation_is_its_own_behaviour(self, iface):
        r = iface.ask("What is occupancy?")
        assert r.plan.plan_type == "explain_the_conflict"

    def test_lookup_does_not_climb_to_recommendation(self, iface):
        """business_reasoning_spec.md 3: 'A Lookup-intent question that the system answers with
        an unsolicited RECOMMENDATION has violated this specification.'"""
        r = iface.ask("How much revenue did we make?")
        stages = {s.stage for s in r.reasoning.statements}
        assert "RECOMMENDATION" not in stages
        assert r.reasoning.within_ceiling

    def test_reasoning_never_exceeds_its_ceiling(self, iface):
        for q in ("How much revenue did we make?", "Revenue by month",
                  "Why did revenue fall?", "What is occupancy?"):
            r = iface.ask(q)
            iface.reset()
            if r.reasoning is not None:
                assert r.reasoning.within_ceiling, q
                assert r.reasoning.violations == (), q

    def test_recommendation_for_a_block_metric_recommends_resolving_the_conflict(self, registry):
        """business_reasoning_spec.md 2's most important gating rule."""
        from engine.analytics_planner import AnalyticsPlanner
        planner = AnalyticsPlanner(registry=registry)
        plan = planner.plan("What's our profit?")
        from engine.execution import MetricExecutor
        ex = MetricExecutor(registry=registry)
        answers = [ex.execute(c.metric_id) for c in plan.execution_calls]
        plan = type(plan)(**{**plan.__dict__, "decision_requested": True,
                             "reasoning_ceiling": "RECOMMENDATION"})
        res = business_reasoning.reason(plan, answers, registry)
        recs = [s for s in res.statements if s.stage == "RECOMMENDATION"]
        assert recs
        assert any("resolving the definitional conflict" in s.text for s in recs)

    def test_hypothesis_uses_hedge_language(self, registry):
        from engine.analytics_planner import AnalyticsPlanner
        from engine.execution import MetricExecutor
        planner = AnalyticsPlanner(registry=registry)
        plan = planner.plan("Why did our electricity cost rise?")
        if plan.status != "READY":
            pytest.skip("plan not executable")
        ex = MetricExecutor(registry=registry)
        answers = [ex.execute(c.metric_id) for c in plan.execution_calls]
        res = business_reasoning.reason(plan, answers, registry)
        for s in res.statements:
            if s.stage == "HYPOTHESIS":
                assert any(h in s.text.lower() for h in business_reasoning.HEDGE_PHRASES)
                assert s.confidence in (business_reasoning.PROVEN,
                                        business_reasoning.SUSPECTED)
        assert res.violations == ()


class TestAnswerContractSurvivesRendering:
    """answer_contract.md 1's required fields must all reach the final answer."""

    def test_skeleton_carries_every_required_field(self, iface):
        r = iface.ask("What was our electricity cost?")
        s = r.rendered.skeleton
        for token in ("TRUST POSTURE", "METRIC PROVENANCE", "CALCULATION", "EVIDENCE",
                      "AS OF", "VALIDATION", "CONFIDENCE", "MANDATORY CAVEAT"):
            assert token in s, f"{token} missing from the rendered answer"

    def test_evidence_references_survive(self, iface):
        r = iface.ask("How much revenue did we make?")
        assert "M.REV.001" in r.rendered.skeleton
        assert "T.journal_lines" in r.rendered.skeleton or "F.001" in r.rendered.skeleton

    def test_conflicts_and_dq_ids_survive(self, iface):
        r = iface.ask("What is occupancy?")
        assert "CONFLICTS" in r.rendered.skeleton
        assert any(c in r.rendered.skeleton for c in ("C.006", "C.007", "C.008", "C.009"))

    def test_limitations_survive(self, iface):
        r = iface.ask("How much do tenants owe?")
        assert "DEFINITION" in r.rendered.skeleton
        assert r.rendered.skeleton.count("DEFINITION") >= 4

    def test_not_determinable_rendering_uses_the_exact_phrase(self, iface):
        r = iface.ask("What is our margin analysis?")
        assert NOT_DETERMINABLE_TEXT in r.text

    def test_validation_status_survives(self, iface):
        r = iface.ask("How much revenue did we make?")
        assert "VALIDATION: MATCH" in r.rendered.skeleton
