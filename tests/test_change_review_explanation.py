"""
test_change_review_explanation.py -- "Why are you saying this?" on a whole-business change review.

The answer was right and stayed right. What sat under it was not an explanation.

A change review is answered per measure -- revenue compared, collections compared, P&L not
comparable -- so the answer carries no single trust level of its own. Every posture the owner
projection dispatches on expects one, so the review fell through to the last branch, headed
"Why I can't answer this", and was explained by restating the entire answer back at the owner:
headings, bullet markers, currency figures and all. An answer repeated under a heading saying it
could not be given is worse than a blank panel, because it reads as a second, differently-derived
set of numbers.

What the owner is actually asking has three parts, and the workflow has already decided all
three: which measures the records could be compared on, which could not, and why nothing is
called significant. The projection now reads those off the change objects instead of inventing
an account of them -- and repeats none of the figures, which live in the answer above.
"""
import os
import re

import pytest

os.environ.setdefault("AI_ANALYTICS_AUTH_DISABLE", "true")
os.environ.pop("AI_ANALYTICS_ENV", None)

QUESTION = "What changed this month?"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.service import AnalyticsService, create_app

    return TestClient(create_app(AnalyticsService()))


@pytest.fixture(scope="module")
def review(client):
    return client.post("/api/ask", json={"question": QUESTION}).json()


@pytest.fixture(scope="module")
def why(review):
    return review.get("owner_explanation") or {}


# --- 1. the answer itself is untouched -----------------------------------------------------------

def test_the_answer_still_reports_every_movement(review):
    """This fix is presentation-only. The movements, their figures and their periods are the
    deterministic engine's and must be exactly as they were."""
    text = review["answer"]
    assert "Executive takeaway" in text
    assert "What changed" in text
    assert "Revenue by month increased by ₹35,384.03 (1.07%)" in text
    assert "Collections by month decreased by ₹221,734.74 (5.88%)" in text
    assert "P&L by month: a period comparison is not available." in text
    assert "2026-06-01" in text and "2026-07-01" in text


def test_the_answer_still_carries_the_materiality_caveat(review):
    text = review["answer"]
    assert "Important caveat" in text
    assert "business judgement" in text
    assert "no significance" in text


def test_no_significance_verdict_was_introduced(review):
    """No threshold exists in the records, and none may be implied anywhere in the response."""
    blob = (review["answer"] + " "
            + " ".join(review.get("limitations") or []) + " "
            + " ".join((review.get("owner_explanation") or {}).get("paragraphs") or []))
    for verdict in ("statistically significant", "significant increase", "significant decrease",
                    "materially significant", "not significant", "insignificant"):
        assert verdict not in blob.lower(), f"a significance verdict appeared: {verdict!r}"


# --- 2. the Why panel is populated and is an explanation ------------------------------------------

def test_the_why_panel_is_not_blank(why):
    assert why.get("heading"), "no heading"
    assert why.get("paragraphs"), "blank owner explanation"
    assert len(why["paragraphs"]) >= 3, why["paragraphs"]


def test_the_heading_says_the_answer_was_given_not_refused(why):
    """It was headed "Why I can't answer this" above an answer that answered."""
    assert why["heading"] == "Why this answer is shown"
    assert "can't" not in why["heading"].lower()


def test_the_why_panel_does_not_restate_the_answer(why, review):
    """The failure mode: the whole answer, pasted in as its own explanation."""
    for paragraph in why["paragraphs"]:
        assert paragraph not in review["answer"], "the answer was restated as its own reason"
        assert "Executive takeaway" not in paragraph
        assert "What changed" not in paragraph
        assert "•" not in paragraph, "answer bullets leaked into the explanation"
        assert "\n" not in paragraph, "a multi-line block was passed off as a paragraph"


# --- 3. it says the three things the owner is asking ------------------------------------------------

def test_it_names_the_measures_the_records_could_compare(why):
    joined = " ".join(why["paragraphs"]).lower()
    assert "month-to-month movements for" in joined
    assert "revenue" in joined and "collections" in joined
    assert "shown directly" in joined


def test_the_unavailable_pnl_comparison_is_represented(why):
    joined = " ".join(why["paragraphs"])
    assert "P&L" in joined, "the unavailable comparison is not mentioned"
    lowered = joined.lower()
    assert "not available from the exported evidence" in lowered
    assert "no p&l change is estimated" in lowered


def test_the_materiality_limitation_is_represented(why):
    joined = " ".join(why["paragraphs"]).lower()
    assert "significance threshold" in joined
    assert "business decision" in joined or "business judgement" in joined


def test_the_reasons_come_from_the_workflow_not_from_prose_written_here(review, why):
    """The materiality sentence is the workflow's own limitation, carried through rather than
    re-authored -- so a change to the policy changes the panel with it."""
    limitations = review.get("limitations") or []
    assert limitations
    assert any(l in why["paragraphs"] for l in limitations), (
        "the deterministic limitation is not what the panel shows")


def test_the_measure_names_track_the_detected_changes():
    """Built from the change objects, not from a fixed list of measures."""
    from engine.analyst_intelligence import AnalystIntelligence
    from engine import explainability as ex

    ai = AnalystIntelligence(verbalize=False)
    answer = ai.ask(QUESTION)
    assert answer.changes, "the review produced no change objects"
    paragraphs = " ".join(ex._change_analysis_reason(answer)).lower()
    for change in answer.changes:
        word = ex._measure_word(change.metric_name).lower()
        assert word in paragraphs, f"{change.metric_name!r} is missing from the explanation"


# --- 4. no figure is invented inside the explanation --------------------------------------------------

def test_the_why_panel_contains_no_numeric_figure(why):
    """A number in "why" reads as a second figure derived some other way. The movements belong
    in the answer, once."""
    joined = " ".join(why["paragraphs"])
    assert "₹" not in joined, "a currency figure appeared in the explanation"
    assert not re.search(r"\d[\d,]*\.\d{2}", joined), "a money-shaped figure appeared"
    assert not re.search(r"\d+(?:\.\d+)?\s*%", joined), "a percentage appeared"
    assert not re.search(r"\b\d{4}-\d{2}(?:-\d{2})?\b", joined), "a raw period key appeared"


# --- 5. nothing internal reaches the owner --------------------------------------------------------------

_INTERNAL = (
    (r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", "metric id"),
    (r"\bDQ\.\d{3}\b", "data-quality id"),
    (r"\bC\.\d{3}\b", "conflict id"),
    (r"\bH\.\d{3}\b", "finding id"),
    (r"\bF\.\d{3}\b", "evidence id"),
    (r"\bv_[a-z0-9_]+\b", "database view"),
    (r"\b[\w.-]+\.(?:py|csv|md|json)\b", "file name"),
    (r"\b(?:SELECT|FROM|GROUP BY|JOIN|schema|table|column)\b", "database terminology"),
    (r"\bengine[/\\]", "implementation path"),
    (r"\b(?:wording layer|language layer|provider|adapter|ollama|llm)\b", "model internal"),
    (r"\b(?:classification|UNAVAILABLE|PARTIAL_PERIOD|change object|ask_result|"
     r"owner_projection|evidence_chain)\b", "internal workflow terminology"),
)


def test_no_internal_identifier_or_terminology_reaches_the_owner(why):
    text = " ".join(why["paragraphs"])
    for pattern, what in _INTERNAL:
        assert not re.search(pattern, text), f"{what} leaked: {text[:180]}"


def test_the_panel_is_prose_not_the_audit_chain(review, why):
    for record in review.get("evidence_chain") or []:
        assert record.get("content") not in why["paragraphs"], (
            "an audit-chain record was rendered to the owner verbatim")


# --- 6. the other Why surfaces are unchanged ---------------------------------------------------------------

def test_the_occupancy_capability_gap_panel_is_unchanged(client):
    r = client.post("/api/ask", json={"question": "next month expected occupancy"}).json()
    why = r["owner_explanation"]
    assert why["heading"] == "Why I can't answer this"
    joined = " ".join(why["paragraphs"]).lower()
    assert "no validated method" in joined
    assert "not a projection" in joined
    assert "nothing was estimated" in joined
    assert r["llm_fallback"] is False
    assert "195" in r["answer"] and "195" not in joined


def test_the_revenue_forecast_panel_is_unchanged(client):
    r = client.post("/api/ask",
                    json={"question": "Forecast revenue for the next 3 months"}).json()
    why = r["owner_explanation"]
    assert why["heading"] == "Why this projection is offered"
    joined = " ".join(why["paragraphs"])
    assert "not a recorded figure" in joined
    assert "off by about" in joined
    assert r["trust_level"] == "SAFE"


def test_a_plain_metric_answer_still_explains_its_trust(client):
    r = client.post("/api/ask", json={"question": "What is our revenue?"}).json()
    why = r["owner_explanation"]
    assert why["heading"] == "Why this answer is trusted"
    assert "one agreed definition" in " ".join(why["paragraphs"])
