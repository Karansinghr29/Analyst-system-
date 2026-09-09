"""
test_comparison_reason_preserved.py -- a refusal must say WHY, not just that it refused.

"Which property is performing better?" cannot be answered because the export contains one
property. The planner establishes exactly that, and the comparison presentation then replaced
it with "I can't produce a period comparison from the available evidence." -- true, generic, and
useless. The specific reason is the only part the owner can act on.
"""
import pytest

from engine import owner_presentation as op
from engine.analyst_intelligence import AnalystIntelligence
from engine.analytics_planner import AnalyticsPlanner
from engine.change_detection import ChangeDetector, UNAVAILABLE
from engine.result import NOT_DETERMINABLE_TEXT

GENERIC = "i can't produce a period comparison from the available evidence."


@pytest.fixture(scope="module")
def analyst():
    return AnalyticsPlanner()


@pytest.fixture(scope="module")
def ai():
    return AnalystIntelligence(verbalize=False)


def ask(ai, question):
    answer = ai.ask(question)
    ai.reset()
    return answer


# --- 1. the structural refusal keeps its specific reason --------------------------------------

def test_a_single_property_comparison_states_the_actual_reason(ai, analyst):
    """The planner's reason must survive into the owner's answer."""
    plan = analyst.plan("Which property is performing better?")
    assert "only 1 distinct value" in (plan.not_determinable_reason or "").lower(), (
        "the planner no longer produces the structural reason; this test's premise has changed")

    text = (ask(ai, "Which property is performing better?").text or "").lower()
    assert "only 1 distinct value" in text, "the specific reason was replaced by a generic one"
    assert "property_id" in text or "property" in text
    assert text.strip() != GENERIC


def test_the_specific_reason_survives_when_no_comparison_was_attempted():
    """`change=None` is the path that dropped it: the function returned before reading the plan.

    Exercised directly so the fix cannot regress through a caller that passes no change.
    """
    class _Plan:
        not_determinable_reason = (
            "Only 1 distinct value of 'property_id' exists in the exported data. There is "
            "nothing to compare. " + NOT_DETERMINABLE_TEXT)

    text = op.present_comparison_answer(None, _Plan())
    assert "only 1 distinct value" in text.lower()
    assert text.strip().lower() != GENERIC


def test_the_generic_line_remains_when_there_is_genuinely_no_reason():
    """Without a reason from either source, the generic refusal is the honest answer."""
    text = op.present_comparison_answer(None, None)
    assert text.strip().lower() == GENERIC


# --- 2. a valid comparison is unchanged ---------------------------------------------------------

def test_a_valid_period_comparison_is_unchanged():
    """The fix touches only the not-detected branch. A real comparison must read as before."""
    change = ChangeDetector().detect(
        "M.REV.002", current_period="2026-07-01", previous_period="2026-06-01")
    assert change.detected, "the fixture comparison no longer computes"

    text = op.present_comparison_answer(change, None).lower()
    assert "increased by" in text or "decreased by" in text or "did not change" in text
    assert "july 2026" in text and "june 2026" in text
    assert GENERIC not in text
    assert "materially significant cannot be determined" in text


def test_a_safe_metric_answer_is_unaffected(ai):
    text = (ask(ai, "What was revenue last month?").text or "")
    assert "₹3,336,114.03" in text
    assert GENERIC not in text.lower()


# --- 3. other not-detected limitations still render ----------------------------------------------

def test_a_partial_period_refusal_still_renders_its_own_wording(ai):
    """The PARTIAL_PERIOD branch runs before the not-detected branch and must be untouched."""
    text = (ask(ai, "revenue this month vs last month").text or "").lower()
    assert "can't reliably compare august 2026 with july 2026" in text
    assert "part-month" in text
    assert text.strip() != GENERIC


def test_an_unavailable_comparison_keeps_the_change_objects_reason():
    """When the reason lives on the change rather than the plan, it must still be shown."""
    change = ChangeDetector().detect("M.COL.001")
    assert change.classification == UNAVAILABLE
    assert change.unavailable_reason

    text = op.present_comparison_answer(change, None).lower()
    assert "no month-keyed series" in text or "no period comparison is possible" in text
    assert NOT_DETERMINABLE_TEXT.lower() in text


def test_the_plan_reason_wins_but_the_change_reason_is_not_lost():
    """Both reasons are true. The specific one leads; the other is not discarded."""
    class _Plan:
        not_determinable_reason = "Only 1 distinct value of 'property_id' exists."

    class _Change:
        detected = False
        classification = UNAVAILABLE
        unavailable_reason = "A separate limitation about the series."

    text = op.present_comparison_answer(_Change(), _Plan()).lower()
    assert "only 1 distinct value" in text
    assert "separate limitation" in text
    assert text.index("only 1 distinct value") < text.index("separate limitation")


def test_no_internal_identifier_reaches_the_owner(ai):
    import re
    text = ask(ai, "Which property is performing better?").text or ""
    for pattern in (r"\bM\.[A-Z]+\.\d{3}", r"\b[\w-]+\.(?:md|csv|py)\b", r"\b(?:engine|api)/"):
        assert not re.search(pattern, text), f"{pattern} leaked:\n{text}"
