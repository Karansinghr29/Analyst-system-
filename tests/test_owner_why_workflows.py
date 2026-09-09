"""
test_owner_why_workflows.py -- every owner-facing "Why are you saying this?" panel.

The systematic fault: `owner_projection` dispatched on a single trust level, and a whole-business
workflow has none -- a briefing, a change review, the attention queue and the trust review each
span many measures carrying their own postures. All of them fell through to the last branch,
headed "Why I can't answer this", whose fallback is the answer's own text. So an answer that had
just answered was headed as unanswerable and explained by pasting itself back: headings, bullets
and every figure, presented as the reason for themselves.

Descriptive answers failed differently. They carry a real posture, so they landed in the trusted
branch and were explained with its generic sentence -- "this measure has one agreed definition,
taken from your own business records" -- which is true of a ledger total and says nothing about a
distribution of recorded rents.

Each workflow is now explained by its own shape, read off the structure it produced. The
invariant these tests exist for: a Why panel is never blank, never headed as a refusal above an
answer, and never the answer a second time.
"""
import os
import re

import pytest

os.environ.setdefault("AI_ANALYTICS_AUTH_DISABLE", "true")
os.environ.pop("AI_ANALYTICS_ENV", None)

SHOWN = "Why this answer is shown"
TRUSTED = "Why this answer is trusted"
PROJECTION = "Why this projection is offered"
REFUSED = "Why I can't answer this"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.service import AnalyticsService, create_app

    return TestClient(create_app(AnalyticsService()))


@pytest.fixture(scope="module")
def ask(client):
    cache = {}

    def _ask(question):
        if question not in cache:
            cache[question] = client.post("/api/ask", json={"question": question}).json()
        return cache[question]

    return _ask


def why_of(payload):
    return payload.get("owner_explanation") or {}


def why_text(payload):
    return " ".join(why_of(payload).get("paragraphs") or [])


# Every question this file covers, and the heading each must carry.
CASES = (
    ("What revenue do you expect next month?", PROJECTION),
    ("Forecast revenue for the next 3 months", PROJECTION),
    ("next month occupancy", REFUSED),
    ("next month expected occupancy", REFUSED),
    ("What is our typical rent?", SHOWN),
    ("How is my business doing?", SHOWN),
    ("What changed this month?", SHOWN),
    ("What are my biggest risks?", SHOWN),
    ("Which numbers can I trust?", SHOWN),
    ("What is our revenue?", TRUSTED),
    ("What is current occupancy?", "Why multiple figures are shown"),
    ("What was profit last month?", "Why this answer is blocked"),
)


# --- 1. the invariants that hold for every panel ---------------------------------------------------

@pytest.mark.parametrize("question,heading", CASES)
def test_the_panel_is_never_blank(ask, question, heading):
    why = why_of(ask(question))
    assert why.get("heading"), f"{question}: no heading"
    assert why.get("paragraphs"), f"{question}: blank owner explanation"


@pytest.mark.parametrize("question,heading", CASES)
def test_the_heading_matches_what_the_answer_actually_did(ask, question, heading):
    """A produced answer is never headed as a refusal."""
    assert why_of(ask(question))["heading"] == heading, question


@pytest.mark.parametrize("question,heading", CASES)
def test_the_panel_is_not_the_answer_repeated(ask, question, heading):
    payload = ask(question)
    body = payload["answer"]
    for paragraph in why_of(payload)["paragraphs"]:
        assert paragraph not in body, f"{question}: the answer was restated as its own reason"
        assert "\n" not in paragraph, f"{question}: a multi-line block passed off as a paragraph"
        assert "•" not in paragraph, f"{question}: answer bullets leaked in"
        assert "Executive takeaway" not in paragraph, f"{question}: the takeaway leaked in"
        assert "Key numbers" not in paragraph, f"{question}: an answer heading leaked in"


@pytest.mark.parametrize("question,heading", CASES)
def test_no_currency_figure_is_repeated_to_justify_itself(ask, question, heading):
    """The amounts live in the answer. A figure inside "why" reads as a second one, derived
    some other way. (The forecast's tested error is not an amount and is asserted separately --
    it is the reason for the stated uncertainty, which the panel must give.)"""
    text = why_text(ask(question))
    assert "₹" not in text, f"{question}: a currency figure appeared in the explanation"


_INTERNAL = (
    (r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", "metric id"),
    (r"\bDQ\.\d{3}\b", "data-quality id"),
    (r"\bC\.\d{3}\b", "conflict id"),
    (r"\bH\.\d{3}\b", "finding id"),
    (r"\bF\.\d{3}\b", "evidence id"),
    (r"\bv_[a-z0-9_]+\b", "database view"),
    (r"\b[\w.-]+\.(?:py|csv|md|json)\b", "file name"),
    (r"\b(?:SELECT|FROM|GROUP BY|JOIN|schema|column)\b", "database terminology"),
    (r"\bengine[/\\]", "implementation path"),
    (r"\b(?:wording layer|language layer|provider|adapter|ollama|llm)\b", "model internal"),
    (r"\b(?:SAFE|DISCLOSE|SHOW_BOTH|BLOCK|NOT_DETERMINABLE|WORKFLOW|READY|"
     r"UNAVAILABLE|PARTIAL_PERIOD)\b", "workflow status token"),
    (r"\b(?:ask_result|owner_projection|evidence_chain|metric_id|trust_level)\b",
     "engine internal"),
)


@pytest.mark.parametrize("question,heading", CASES)
def test_nothing_internal_reaches_the_owner(ask, question, heading):
    text = why_text(ask(question))
    for pattern, what in _INTERNAL:
        assert not re.search(pattern, text), f"{question}: {what} leaked -- {text[:150]}"


@pytest.mark.parametrize("question,heading", CASES)
def test_the_panel_is_prose_not_the_audit_chain(ask, question, heading):
    payload = ask(question)
    paragraphs = why_of(payload)["paragraphs"]
    for record in payload.get("evidence_chain") or []:
        assert record.get("content") not in paragraphs, f"{question}: audit record rendered"


# --- 2. the forecast workflow ------------------------------------------------------------------------

def test_a_successful_forecast_explains_that_it_is_a_projection(ask):
    payload = ask("What revenue do you expect next month?")
    text = why_text(payload)
    assert "not a recorded figure" in text
    assert "revenue history" in text
    assert "months it had not been shown" in text, "the out-of-sample test is not described"
    assert "off by about" in text, "the tested error is not given as the reason for the range"


def test_the_forecast_panel_does_not_repeat_the_projection_or_its_range(ask):
    payload = ask("What revenue do you expect next month?")
    text = why_text(payload)
    for figure in ("3,429,771.16", "3,268,690.53", "3,627,307.21"):
        assert figure not in text, f"{figure} was repeated in the explanation"


def test_the_forecast_panel_states_the_trading_assumption(ask):
    """A projection of a trend assumes the trend's conditions hold; the answer says so and the
    explanation must not drop it."""
    payload = ask("Forecast revenue for the next 3 months")
    assert "broadly as it has" in payload["answer"], "the assumption left the answer"
    assert why_of(payload)["heading"] == PROJECTION


# --- 3. the forecast capability gap ---------------------------------------------------------------------

@pytest.mark.parametrize("question", ["next month occupancy", "next month expected occupancy"])
def test_the_unsupported_forecast_explains_the_missing_method(ask, question):
    text = why_text(ask(question)).lower()
    assert "no validated method" in text
    assert "recorded occupancy can still be shown" in text, (
        "does not say history can still be shown")
    assert "not a projection" in text
    assert "nothing was estimated" in text


@pytest.mark.parametrize("question", ["next month occupancy", "next month expected occupancy"])
def test_the_historical_figure_stays_out_of_the_refusal(ask, question):
    payload = ask(question)
    assert "195" in payload["answer"], "the historical context left the answer"
    assert "195" not in why_text(payload), (
        "a historical figure was put inside the explanation of an unavailable forecast")


# --- 4. descriptive analysis ------------------------------------------------------------------------------

def test_the_descriptive_panel_describes_what_was_described(ask):
    text = why_text(ask("What is our typical rent?"))
    lowered = text.lower()
    assert "allotment" in lowered, "the grain of the description is not stated"
    assert "typical value" in lowered, "the statistics used are not named"
    assert "middle half" in lowered or "full recorded span" in lowered


def test_the_descriptive_panel_states_the_missing_and_zero_handling(ask):
    lowered = why_text(ask("What is our typical rent?")).lower()
    assert "nothing entered" in lowered, "missing-value handling is not stated"
    assert "entered as zero are kept as recorded" in lowered


def test_the_descriptive_panel_keeps_the_reconciliation_caveat(ask):
    """This is the answer's own DISCLOSE limitation, and the generic trusted sentence dropped
    it entirely."""
    payload = ask("What is our typical rent?")
    text = why_text(payload)
    assert "not reconciled against the accounting ledger" in text
    assert any(l in why_of(payload)["paragraphs"] for l in payload["limitations"]), (
        "the deterministic limitation is not what the panel shows")
    assert "one agreed definition" not in text, "the generic trusted sentence is still shown"


def test_the_descriptive_panel_repeats_no_figure(ask):
    text = why_text(ask("What is our typical rent?"))
    assert "14,500" not in text and "1,186" not in text
    assert not re.search(r"\d[\d,]*\.\d{2}", text)


# --- 5. the executive / business-health workflow -------------------------------------------------------------

def test_the_business_health_panel_explains_the_structure(ask):
    text = why_text(ask("How is my business doing?")).lower()
    assert "snapshot" in text and "as exported" in text
    assert "shown directly" in text, "agreed measures are not described"
    assert "rather than collapsed into one figure" in text, "competing definitions not described"
    assert "need your decision" in text, "owner decisions are not described"
    assert "period movements" in text, "supported movements are not described"
    assert "unavailable" in text, "unavailable comparisons are not described"


def test_the_business_health_panel_repeats_none_of_the_amounts(ask):
    payload = ask("How is my business doing?")
    text = why_text(payload)
    assert "₹" not in text
    assert not re.search(r"\d[\d,]*\.\d{2}", text), "an amount was repeated"
    assert "Executive takeaway" not in text
    assert "As at export snapshot" not in text, "the answer's own header was repeated"


def test_the_attention_queue_explains_that_it_is_not_ranked(ask):
    """A different workflow, so a different explanation -- and the one thing it must say is
    that nothing invented an order for the owner's decisions."""
    text = why_text(ask("What are my biggest risks?")).lower()
    assert "listed rather than ranked" in text
    assert "no priority score exists" in text
    assert "snapshot built from the evidence" not in text, "the briefing wording was reused"


def test_the_trust_review_explains_that_postures_are_preserved(ask):
    text = why_text(ask("Which numbers can I trust?")).lower()
    assert "keeps the posture the records assigned" in text
    assert "upgraded or downgraded" in text


# --- 6. the panels that already worked ------------------------------------------------------------------------

def test_the_change_review_panel_is_unchanged(ask):
    text = why_text(ask("What changed this month?")).lower()
    assert "month-to-month movements for" in text
    assert "no p&l change is estimated" in text
    assert "significance threshold" in text


def test_the_plain_metric_panel_is_unchanged(ask):
    text = why_text(ask("What is our revenue?"))
    assert "one agreed definition" in text
    assert "checked against the available source records" in text


def test_the_show_both_panel_is_unchanged(ask):
    payload = ask("What is current occupancy?")
    text = why_text(payload).lower()
    assert "evidence-backed definitions" in text
    assert "business decision" in text
    assert payload["trust_level"] == "SHOW_BOTH"


def test_the_block_panel_is_unchanged(ask):
    payload = ask("What was profit last month?")
    text = why_text(payload).lower()
    assert "do not agree" in text
    assert "decision needed" in text
    assert payload["trust_level"] == "BLOCK"


# --- 7. no answer or posture moved --------------------------------------------------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("What is our revenue?", "SAFE"),
    ("What is current occupancy?", "SHOW_BOTH"),
    ("What was profit last month?", "BLOCK"),
    ("What is our typical rent?", "DISCLOSE"),
    ("What revenue do you expect next month?", "SAFE"),
])
def test_no_trust_posture_changed(ask, question, expected):
    assert ask(question)["trust_level"] == expected, question


def test_the_answers_themselves_are_untouched(ask):
    """This is a presentation change. Every figure the engine produced must still be there."""
    assert "72,705,593" in ask("What is our revenue?")["answer"]
    assert "14,500" in ask("What is our typical rent?")["answer"]
    assert "3,429,771.16" in ask("What revenue do you expect next month?")["answer"]
    assert "35,384.03" in ask("What changed this month?")["answer"]
    assert "195" in ask("next month occupancy")["answer"]


def test_no_estimate_was_introduced_anywhere(ask):
    for question, _heading in CASES:
        payload = ask(question)
        blob = (payload["answer"] + " " + why_text(payload)).lower()
        for invented in ("estimated at", "approximately ₹", "roughly ₹", "we estimate"):
            assert invented not in blob, f"{question}: an estimate appeared -- {invented!r}"
