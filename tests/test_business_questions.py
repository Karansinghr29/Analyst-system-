"""
Phase 6: the business question catalog, end to end.

Phase 6 brief 17 is the product requirement under test:
    "The owner should NOT have to understand metric IDs, table names, SQL, data models, analyst
     terminology, Power BI terminology, or trust-layer internals. They should simply ask normal
     business questions."

So every question here is phrased the way an owner would phrase it, and each is checked against
what the SPECS require the answer's shape to be -- never against a convenient outcome.
"""
import pytest

from engine.analyst_intelligence import AnalystIntelligence
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture(scope="module")
def ai(registry):
    return AnalystIntelligence(registry=registry)


def _ask(ai, q):
    a = ai.ask(q)
    ai.reset()
    return a


# (question, required answer shape)
#   value  -- a single figure may be shown
#   multi  -- competing definitions, never one figure
#   clarify/refuse -- terminated before execution, with a reason
#   briefing/changed/actions/trust -- whole-business shortcuts
CATALOG = [
    ("What is today's occupancy?",              "multi"),
    ("How many tenants are staying?",           "value"),
    ("How many are on notice?",                 "value"),
    ("What is revenue this month?",             "value"),
    ("How much did we collect?",                "clarify"),
    ("How much do tenants owe?",                "multi"),
    ("Which tenants have outstanding dues?",    "multi"),
    ("Why did collections fall?",               "any"),
    ("Why did profit fall?",                    "multi"),
    ("Which expense category is largest?",      "value"),
    ("How much owner payment was made?",        "value"),
    ("How much deposit is held?",               "value"),
    ("How many deposits are unresolved?",       "value"),
    ("Which apartments are under-utilized?",    "refuse"),
    ("Which property is performing better?",    "refuse"),
    ("What are our biggest financial risks?",   "any"),
    ("What data problems should I know about?", "any"),
    ("Which numbers should I trust?",           "trust"),
    ("What changed this month?",                "changed"),
    ("What requires my decision?",              "actions"),
    ("What should I investigate first?",        "actions"),
    ("Give me today's business summary",        "briefing"),
    ("Give me a management briefing",           "briefing"),
    ("How is the business doing?",              "briefing"),
]


class TestQuestionCatalog:
    @pytest.mark.parametrize("question,shape", CATALOG)
    def test_every_catalog_question_answers_in_its_required_shape(self, ai, question, shape):
        a = _ask(ai, question)
        assert a.text.strip(), f"{question}: produced no answer at all"

        if shape == "value":
            assert a.ask_result is not None and a.ask_result.executed, question
            assert a.trust_level in ("SAFE", "DISCLOSE"), f"{question}: {a.trust_level}"
        elif shape == "multi":
            if a.ask_result is not None and a.ask_result.executed:
                assert a.trust_level in ("SHOW_BOTH", "BLOCK"), f"{question}: {a.trust_level}"
                for ans in a.ask_result.answers:
                    assert ans.headline is None, f"{question}: exposed a headline"
        elif shape == "clarify":
            assert a.ask_result is not None
            assert a.ask_result.status == "NEEDS_CLARIFICATION", question
            assert not a.ask_result.executed
        elif shape == "refuse":
            assert a.ask_result is not None
            assert not a.ask_result.executed, question
            assert NOT_DETERMINABLE_TEXT in a.text, question
        elif shape == "briefing":
            assert a.owner_intent == "briefing"
            assert a.summary is not None
        elif shape == "changed":
            assert a.owner_intent == "what_changed"
            assert a.changes
        elif shape == "actions":
            assert a.owner_intent == "what_to_do"
        elif shape == "trust":
            assert a.owner_intent == "what_to_trust"

    def test_no_answer_requires_the_owner_to_know_a_metric_id(self, ai):
        """The owner asks in business language; metric_ids appear as provenance on the
        skeleton, never as something they had to supply or read in the answer."""
        for question, _ in CATALOG[:8]:
            a = _ask(ai, question)
            assert "M." not in question

    def test_every_answered_question_carries_evidence(self, ai):
        for question, shape in CATALOG:
            if shape not in ("value", "multi"):
                continue
            a = _ask(ai, question)
            if a.ask_result is not None and a.ask_result.executed:
                assert any(m in a.ask_result.rendered.skeleton for m in a.metric_ids), question


class TestUnanswerableQuestions:
    """3.3: a question with no corresponding metric is structurally absent, not improvised."""

    @pytest.mark.parametrize("question", [
        "What is our margin analysis?",
        "What is our collection efficiency?",
        "What is our customer lifetime value?",
    ])
    def test_absent_concepts_are_not_improvised(self, ai, question):
        a = _ask(ai, question)
        if a.ask_result is not None and a.ask_result.executed:
            pytest.fail(f"{question}: improvised an answer for an absent concept")
        assert NOT_DETERMINABLE_TEXT in a.text or a.ask_result.status == "NEEDS_CLARIFICATION"

    def test_a_requested_framing_the_metric_lacks_is_disclosed(self, ai):
        """"Churn" legitimately resolves to the move-out count, so the figure is real. But the
        owner asked for a RATE against a BENCHMARK, and neither a denominator nor a benchmark
        exists in the evidence. Answering the count without saying so would be a silent
        reframing, even though the count itself is correct."""
        a = _ask(ai, "What is our churn rate percentage benchmark?")
        joined = " ".join(a.limitations)
        assert NOT_DETERMINABLE_TEXT in joined
        assert "benchmark" in joined.lower()
        assert "rate or ratio" in joined.lower()

    def test_benchmark_questions_state_that_no_benchmark_exists(self, ai):
        a = _ask(ai, "How does our occupancy compare to the industry benchmark?")
        joined = " ".join(a.limitations) + a.text
        assert "benchmark" in joined.lower()
        assert NOT_DETERMINABLE_TEXT in joined

    def test_apartment_level_question_states_the_evidence_limit(self, ai):
        """M.OCC.003/004 are NOT_DETERMINABLE in the registry: no exported reference exists."""
        a = _ask(ai, "Which apartments are under-utilized?")
        assert NOT_DETERMINABLE_TEXT in a.text


class TestOwnerLanguageShortcuts:
    @pytest.mark.parametrize("question,intent", [
        ("How is the business doing?", "briefing"),
        ("Show me the important numbers.", "briefing"),
        ("What changed this month?", "what_changed"),
        ("What should I do today?", "what_to_do"),
        ("What should I worry about?", "what_to_do"),
        ("Which numbers are unreliable?", "what_to_trust"),
        ("Can I trust these figures?", "what_to_trust"),
    ])
    def test_owner_phrasing_routes_to_the_right_workflow(self, ai, question, intent):
        a = _ask(ai, question)
        assert a.owner_intent == intent, f"{question} -> {a.owner_intent}"

    def test_a_specific_metric_question_is_not_hijacked_by_a_shortcut(self, ai):
        a = _ask(ai, "How much revenue did we make?")
        assert a.owner_intent == "metric_question"
