"""
Phase 6: decision support.

Phase 6 brief 6 fixes what every recommendation must carry:
    1. Evidence  2. Business impact  3. Risk  4. Confidence  5. Recommended action
    6. What evidence would change the recommendation

and the constraint: "Never produce unsupported recommendations."

business_reasoning_spec.md 2's gating rule is the sharpest of them: a recommendation touching a
BLOCK metric must recommend RESOLVING THE CONFLICT, never an operational action on a disputed
figure.
"""
import pytest

from engine.analyst_intelligence import AnalystIntelligence
from engine.insight_engine import InsightEngine
from engine import business_reasoning
from engine.root_cause import unsupported_causal_claim
from engine.result import NOT_DETERMINABLE_TEXT

_CACHE = {}


@pytest.fixture(scope="module")
def ai(registry):
    return AnalystIntelligence(registry=registry)


@pytest.fixture(scope="module")
def insights(registry):
    if "i" not in _CACHE:
        _CACHE["i"] = InsightEngine(registry=registry).generate()
    return _CACHE["i"]


class TestDecisionQuestions:
    @pytest.mark.parametrize("question", [
        "What should I do?",
        "What needs my attention?",
        "What should I investigate first?",
        "What requires my decision?",
        "What should I worry about?",
    ])
    def test_decision_questions_route_and_answer(self, ai, question):
        a = ai.ask(question)
        ai.reset()
        assert a.owner_intent == "what_to_do"
        assert a.text.strip()
        assert "decision_support_analyst" in a.routing.roles

    def test_attention_items_are_owner_decisions(self, ai):
        a = ai.ask("What requires my decision?")
        ai.reset()
        assert "What needs attention" in a.text
        assert "What to do next" in a.text

    def test_the_biggest_risk_question_returns_ranked_findings(self, ai):
        a = ai.ask("What are our biggest financial risks?")
        ai.reset()
        assert a.text.strip()


class TestRecommendationSupport:
    def test_every_recommendation_is_in_recommendation_register(self, insights):
        for i in insights:
            if i.recommendation.strip():
                assert "recommend" in i.recommendation.lower(), i.insight_id

    def test_no_recommendation_asserts_a_cause(self, insights):
        for i in insights:
            offending = unsupported_causal_claim(i.recommendation)
            assert not offending, f"{i.insight_id}: causal claim {offending!r}"

    def test_no_recommendation_without_an_observation(self, insights):
        """The brief: never jump FACT -> RECOMMENDATION without the intermediate chain."""
        for i in insights:
            if i.recommendation.strip():
                assert i.observation.strip(), f"{i.insight_id}: recommended with no OBSERVATION"

    def test_block_recommendations_address_the_conflict_only(self, insights):
        for i in insights:
            if i.trust_level == "BLOCK" and i.recommendation.strip():
                low = i.recommendation.lower()
                assert any(w in low for w in ("resolv", "decision", "authoritative",
                                              "which definition", "reconcil")), (
                    f"{i.insight_id}: acted on a disputed figure instead of resolving the "
                    f"conflict: {i.recommendation[:140]}")

    def test_every_recommendation_carries_evidence(self, insights):
        for i in insights:
            if i.recommendation.strip():
                assert i.evidence_sources or i.dq_ids or i.conflict_ids, (
                    f"{i.insight_id}: recommendation with no traceable evidence")

    def test_every_recommendation_carries_confidence(self, insights):
        for i in insights:
            if i.recommendation.strip():
                assert i.confidence.strip()
                assert not i.confidence.strip().rstrip("%").replace(".", "").isdigit(), (
                    f"{i.insight_id}: numeric confidence")

    def test_confidence_uses_the_documented_vocabulary(self, insights):
        allowed_fragments = ("PROVEN", "SUSPECTED", "HIGH", "MEDIUM", "SPLIT", "BLOCKED",
                             "UNVERIFIED")
        for i in insights:
            if i.recommendation.strip():
                assert any(f in i.confidence.upper() for f in allowed_fragments), i.confidence

    def test_risk_and_impact_are_carried_where_determinable(self, insights):
        for i in insights:
            if not i.recommendation.strip():
                continue
            has_impact = (i.affected_amount is not None or i.affected_count is not None
                          or i.limitations.strip())
            assert has_impact, (
                f"{i.insight_id}: no business impact stated and no limitation explaining why")

    def test_missing_impact_is_declared_not_omitted(self, insights):
        for i in insights:
            if i.affected_amount is None and i.limitations.strip():
                assert NOT_DETERMINABLE_TEXT in i.limitations or i.affected_count is not None


class TestDecisionSupportObject:
    """The Phase 5 DecisionSupport object, exercised through the Phase 6 surface."""

    def test_block_preserves_the_conflict_rather_than_one_number(self, ai):
        a = ai.ask("What's our profit?")
        ai.reset()
        ds = a.ask_result.decision_support
        assert ds.trust_level == "BLOCK"
        assert ds.headline_permitted is False
        assert ds.definition_conflicts

    def test_sections_are_not_manufactured(self, ai):
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        ds = a.ask_result.decision_support
        for name, reason in ds.omitted_sections.items():
            assert reason.strip(), f"{name} omitted with no reason"

    def test_recommended_actions_never_appear_for_a_bare_lookup(self, ai):
        """business_reasoning_spec.md 3: a Lookup answered with an unsolicited RECOMMENDATION
        violates the specification."""
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        stages = {s.stage for s in a.ask_result.reasoning.statements}
        assert business_reasoning.RECOMMENDATION not in stages


class TestNoUnsupportedRecommendations:
    def test_no_recommendation_is_emitted_for_an_undeterminable_metric(self, ai):
        a = ai.ask("What is our margin analysis?")
        ai.reset()
        assert NOT_DETERMINABLE_TEXT in a.text
        if a.ask_result.reasoning is not None:
            stages = {s.stage for s in a.ask_result.reasoning.statements}
            assert business_reasoning.RECOMMENDATION not in stages

    def test_recommendations_are_deterministic(self, registry):
        a = InsightEngine(registry=registry).generate()
        b = InsightEngine(registry=registry).generate()
        assert [i.recommendation for i in a] == [i.recommendation for i in b]
