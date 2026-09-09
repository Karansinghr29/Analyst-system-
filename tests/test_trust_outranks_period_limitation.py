"""
test_trust_outranks_period_limitation.py -- precedence between two true limitations.

"What was profit last month?" used to answer "I don't have a month-scoped series", and stop.
Both facts were true -- profit has no monthly series AND its definitions conflict -- but the
pipeline terminated at stage [4] with the Trust Gate never consulted, so the owner was told the
lesser of the two reasons. The one they could act on was the one withheld: a period gap is a
property of this export, while conflicting definitions are a business decision only they can
settle.

The rule under test:

    TRUST CONFLICT (BLOCK / SHOW_BOTH)  >  period-availability limitation

Neither fact is dropped. No figure is produced for either, so an all-time value can never stand
in for the month that was asked about.
"""
import re

import pytest

from engine.analytics_planner import AnalyticsPlanner
from engine.gate import TrustGate
from engine.llm_interface import LLMInterface
from engine.semantic_registry import SemanticRegistry
from engine.intent_models import NOT_DETERMINABLE, NOT_DETERMINABLE_TEXT


@pytest.fixture(scope="module")
def registry():
    return SemanticRegistry()


@pytest.fixture(scope="module")
def planner(registry):
    return AnalyticsPlanner(registry=registry)


@pytest.fixture(scope="module")
def gate(registry):
    return TrustGate(registry)


@pytest.fixture(scope="module")
def iface():
    return LLMInterface()


def ask(iface, question):
    result = iface.ask(question)
    iface.reset()
    return result


# A period-scoped question per family, spanning every trust posture.
CONFLICTED = [
    "What was profit last month?",
    "profit this month",
    "August profit",
    "occupancy last month",
]

NON_CONFLICTED = [
    "revenue last month",
    "expenses last month",
]

ALL_PERIOD_QUESTIONS = CONFLICTED + NON_CONFLICTED + ["collections last month"]


# == the precedence rule ==========================================================================

@pytest.mark.parametrize("question", CONFLICTED)
def test_the_gate_is_consulted_even_when_a_period_limitation_ends_the_pipeline(
        question, planner):
    """The regression. A terminal plan used to carry no trust level at all, because the gate
    was never asked."""
    plan = planner.plan(question)
    assert plan.trust_level in ("BLOCK", "SHOW_BOTH"), (
        f"{question!r} terminated without a trust verdict (got {plan.trust_level!r})")


@pytest.mark.parametrize("question", CONFLICTED)
def test_the_conflict_is_stated_before_the_period_limitation(question, planner):
    reason = planner.plan(question).not_determinable_reason or ""
    low = reason.lower()
    conflict_at = min((low.find(w) for w in ("disagree", "more than one") if w in low),
                      default=-1)
    period_at = low.find("month-scoped series")
    assert conflict_at >= 0, f"the conflict is not disclosed at all:\n{reason}"
    if period_at >= 0:
        assert conflict_at < period_at, (
            f"the period limitation is stated before the conflict:\n{reason}")


@pytest.mark.parametrize("question", CONFLICTED)
def test_the_period_limitation_is_still_disclosed(question, planner):
    """Leading with the conflict must not drop the other true fact."""
    reason = (planner.plan(question).not_determinable_reason or "").lower()
    assert "month-scoped series" in reason or "not determinable" in reason


def test_the_plan_trust_level_is_the_gate_verdict_verbatim(planner, gate):
    """Precedence changes WHICH limitation leads. It never changes the verdict itself."""
    plan = planner.plan("What was profit last month?")
    assert plan.trust_level == gate.authorize("M.PROFIT.001").effective_level


# == what must never happen =======================================================================

@pytest.mark.parametrize("question", CONFLICTED)
def test_no_figure_is_produced_for_a_conflicted_period_question(question, planner, iface):
    """Not an invented monthly number, and not an all-time number standing in for the month."""
    plan = planner.plan(question)
    assert plan.status == NOT_DETERMINABLE
    assert plan.headline_permitted is False
    assert not plan.execution_calls, "a conflicted period question planned an execution"

    text = ask(iface, question).text or ""
    figures = re.findall(r"\d[\d,]*\.\d{2}", text)
    assert not figures, f"{question!r} produced a figure:\n{text[:400]}"


@pytest.mark.parametrize("question", CONFLICTED)
def test_no_single_definition_is_silently_chosen(question, iface):
    text = (ask(iface, question).text or "").lower()
    for winner in ("the real ", "the correct figure", "we should use", "best estimate",
                   "the actual profit is"):
        assert winner not in text, f"{question!r} picked a winner ({winner!r})"


@pytest.mark.parametrize("question", CONFLICTED)
def test_no_generic_wording_error_is_returned(question, iface):
    """The owner must not be told their phrasing was wrong for a limit of the evidence."""
    text = (ask(iface, question).text or "").lower()
    assert "couldn't turn that into a well-formed" not in text
    assert "could you rephrase" not in text


@pytest.mark.parametrize("question", CONFLICTED)
def test_the_requested_period_is_preserved_in_the_plan(question, planner):
    """The plan still knows which period was asked about, even though it cannot answer it."""
    plan = planner.plan(question)
    assert plan.time is not None, f"{question!r} discarded the requested period"
    assert (plan.time.period_label or "") != "all-time", (
        f"{question!r} fell back to all-time")


# == the other postures are unchanged =============================================================

@pytest.mark.parametrize("question", NON_CONFLICTED)
def test_a_safe_metric_still_answers_its_requested_period(question, planner, iface):
    """The fix must not turn working answers into refusals."""
    plan = planner.plan(question)
    assert plan.trust_level in ("SAFE", "DISCLOSE"), question
    text = ask(iface, question).text or ""
    assert re.search(r"\d[\d,]*\.\d{2}", text), f"{question!r} lost its figure:\n{text[:200]}"


def test_a_safe_metric_with_an_unavailable_period_still_says_so_honestly(planner):
    """A SAFE metric that genuinely has no series for the period keeps the period limitation as
    its leading reason -- there is no conflict to outrank it."""
    plan = planner.plan("maintenance last month")
    if plan.status != NOT_DETERMINABLE:
        pytest.skip("maintenance resolved to an answerable plan")
    reason = (plan.not_determinable_reason or "").lower()
    assert "disagree" not in reason, "a conflict was claimed where the gate found none"


def test_show_both_definitions_are_not_collapsed(iface):
    """SHOW_BOTH stays SHOW_BOTH: no single figure, and no winner."""
    result = ask(iface, "occupancy last month")
    assert result.trust_level == "SHOW_BOTH"
    text = (result.text or "").lower()
    assert "none of them is selected" in text or "not selected" in text


def test_block_stays_block_through_the_owner_answer(iface):
    result = ask(iface, "What was profit last month?")
    assert result.trust_level == "BLOCK"
    assert NOT_DETERMINABLE_TEXT in (result.text or "") or "disagree" in (result.text or "").lower()


# == owner presentation stays clean ===============================================================

INTERNAL = [
    re.compile(r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b"),
    re.compile(r"\bDQ\.\d{3}\b"),
    re.compile(r"\bC\.\d{3}\b"),
    re.compile(r"\b[\w.-]+\.(?:md|csv|py|json)\b", re.I),
    re.compile(r"\b(?:engine|api|frontend|tests)/", re.I),
    re.compile(r"\b(?:v_[a-z0-9_]+|get_[a-z0-9_]+)\b", re.I),
    re.compile(r"\bGROUP\s+BY\b", re.I),
]


@pytest.mark.parametrize("question", ALL_PERIOD_QUESTIONS)
def test_no_internal_identifier_reaches_the_owner(question, iface):
    text = ask(iface, question).text or ""
    for pattern in INTERNAL:
        assert not pattern.search(text), (
            f"{question!r} leaked {pattern.pattern}:\n{text[:300]}")
