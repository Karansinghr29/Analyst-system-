"""
test_capability_gap_presentation.py -- what an owner sees when a capability is missing.

The analytics were already right: occupancy has no validated forecasting method, so the system
refuses and offers the latest recorded figure as labelled context. What reached the owner was
three pieces of machinery instead.

  * The chat printed "The wording layer did not contribute to this answer. The figures and the
    posture below are unaffected -- they are computed by the analytics engine, not written by
    the model." A capability-gap answer is never sent to the wording layer; the refusal is
    deterministic by design. The notice explained an internal mechanism that had not failed.
  * The Limitations list read `Forecasting` and `forecast unavailable` -- an internal capability
    label and a state tag standing where a sentence belongs.
  * "Why are you saying this?" restated the answer verbatim, historical figure and all, putting
    a recorded number inside an explanation of why no number could be given.

The figure itself is the thing that must not move: 195 is what occupancy IS, and the moment it
appears anywhere that reads as a projection, the refusal has been undone.
"""
import os
import re

import pytest

os.environ.setdefault("AI_ANALYTICS_AUTH_DISABLE", "true")
os.environ.pop("AI_ANALYTICS_ENV", None)

QUESTION = "next month expected occupancy"

# The debug sentence the frontend renders whenever `llm_fallback` is true.
WORDING_LAYER_NOTICE = "wording layer"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.service import AnalyticsService, create_app

    return TestClient(create_app(AnalyticsService()))


@pytest.fixture(scope="module")
def occupancy(client):
    return client.post("/api/ask", json={"question": QUESTION}).json()


# --- 1. no forecast is produced -------------------------------------------------------------------

def test_no_occupancy_forecast_is_invented(occupancy):
    text = occupancy["answer"]
    assert "Projected" not in text
    assert "forecast" in text.lower(), "the refusal itself is missing"
    assert not re.search(r"\b(?:next month|august 2026)\b.*\b195\b", text, re.I | re.S), (
        "the recorded figure was attached to a future period")


def test_the_refusal_names_what_is_missing(occupancy):
    text = occupancy["answer"].lower()
    assert "can't reliably forecast" in text
    assert "isn't currently available" in text


# --- 2. 195 stays historical ------------------------------------------------------------------------

def test_the_recorded_figure_is_labelled_as_history_not_a_projection(occupancy):
    text = occupancy["answer"]
    assert "195" in text, "the historical context was dropped"
    assert "not a forecast" in text.lower()
    before = text[:text.index("195")]
    assert "Latest historical context" in before, (
        "195 appears without the label that makes it historical")


def test_the_limitations_say_what_the_figure_is_not(occupancy):
    joined = " ".join(occupancy["limitations"])
    assert "not a projection" in joined
    assert "Nothing was estimated in its place." in joined


# --- 3. no implementation language ---------------------------------------------------------------------

def test_the_wording_layer_notice_is_gone(occupancy):
    """It is rendered off `llm_fallback`, which was true for an answer the wording layer was
    never asked to touch."""
    assert occupancy["llm_fallback"] is False
    assert WORDING_LAYER_NOTICE not in occupancy["answer"].lower()
    assert WORDING_LAYER_NOTICE not in " ".join(occupancy["limitations"]).lower()
    why = " ".join(occupancy["owner_explanation"]["paragraphs"]).lower()
    assert WORDING_LAYER_NOTICE not in why


def test_the_limitations_are_sentences_not_internal_labels(occupancy):
    limitations = occupancy["limitations"]
    assert limitations, "the limitation disappeared entirely"
    assert "Forecasting" not in limitations, "the bare capability label is still exposed"
    assert "forecast unavailable" not in limitations, "the internal state tag is still exposed"
    for limitation in limitations:
        assert limitation.rstrip().endswith("."), f"not a sentence: {limitation!r}"
        assert len(limitation.split()) >= 5, f"reads as a label: {limitation!r}"


_INTERNAL = (
    (r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", "metric id"),
    (r"\bDQ\.\d{3}\b", "data-quality id"),
    (r"\bC\.\d{3}\b", "conflict id"),
    (r"\bv_[a-z0-9_]+\b", "database view"),
    (r"\b[\w.-]+\.(?:py|csv|md|json)\b", "file name"),
    (r"\b(?:SELECT|FROM|GROUP BY|JOIN|table|column|schema)\b", "database terminology"),
    (r"\b(?:wording layer|language layer|provider|adapter|ollama|llm|model output)\b",
     "model or provider internal"),
    (r"\b(?:capability_id|owner_summary|not_determinable_reason|ask_result|AnalystAnswer)\b",
     "engine internal"),
    (r"\bengine[/\\]", "implementation path"),
)


@pytest.mark.parametrize("field", ["answer", "limitations", "why"])
def test_nothing_internal_reaches_the_owner(occupancy, field):
    if field == "answer":
        text = occupancy["answer"]
    elif field == "limitations":
        text = " ".join(occupancy["limitations"])
    else:
        text = " ".join(occupancy["owner_explanation"]["paragraphs"])
    for pattern, what in _INTERNAL:
        assert not re.search(pattern, text, re.I), f"{what} leaked into {field}: {text[:160]}"


# --- 4. the Why panel says the four things the owner needs -----------------------------------------------

def test_the_why_panel_is_populated_and_owner_readable(occupancy):
    why = occupancy["owner_explanation"]
    assert why.get("heading")
    paragraphs = why.get("paragraphs") or []
    # Two, not three: the refusal sentence that opens the ANSWER is no longer repeated here.
    # The panel carries the reasons, not the answer.
    assert len(paragraphs) >= 2, paragraphs
    joined = " ".join(paragraphs).lower()

    assert "no validated method" in joined, "does not say the method is unvalidated"
    assert "recorded occupancy can still be shown" in joined, (
        "does not say history can still be shown")
    assert "not a projection" in joined, "does not say the figure is history only"
    assert "nothing was estimated" in joined, "does not say nothing was substituted"


def test_the_why_panel_does_not_restate_the_recorded_figure(occupancy):
    """A number inside "why I can't give you a number" reads as the number."""
    joined = " ".join(occupancy["owner_explanation"]["paragraphs"])
    assert "195" not in joined


def test_the_owner_panel_is_prose_not_the_raw_evidence_chain(occupancy):
    """The chain is a list of {link, content, source} records for auditors. Whatever it holds,
    the owner panel is sentences -- never those records rendered directly.

    (For a capability gap the chain is empty: it is built from the Phase 4 result, and a gap
    produces none. That is existing behaviour and not what this panel depends on.)
    """
    paragraphs = occupancy["owner_explanation"]["paragraphs"]
    assert all(isinstance(p, str) for p in paragraphs)
    for record in occupancy.get("evidence_chain") or []:
        assert record.get("content") not in paragraphs, (
            "an audit-chain record was rendered to the owner verbatim")


# --- 5. nothing that already worked changed ----------------------------------------------------------------

def test_revenue_forecasting_is_untouched(client):
    r = client.post("/api/ask",
                    json={"question": "Forecast revenue for the next 3 months"}).json()
    assert r["trust_level"] == "SAFE"
    assert r["llm_fallback"] is False
    assert "Projected revenue for the next 3 months" in r["answer"]
    for label in ("August 2026", "September 2026", "October 2026"):
        assert label in r["answer"]
    why = r["owner_explanation"]
    assert why["heading"] == "Why this projection is offered"
    assert "not a recorded figure" in " ".join(why["paragraphs"])


def test_a_refused_horizon_is_still_refused_by_the_method(client):
    r = client.post("/api/ask", json={"question": "February 2027 revenue expected"}).json()
    assert r["trust_level"] == "NOT_DETERMINABLE"
    assert "6 months" in r["answer"]
    assert "Projected revenue for" not in r["answer"]


def test_other_capability_gaps_get_the_same_treatment(client):
    for question in ("Forecast expenses next month", "What if occupancy were 80%?"):
        r = client.post("/api/ask", json={"question": question}).json()
        assert r["llm_fallback"] is False, question
        assert r["owner_explanation"].get("paragraphs"), question
        for limitation in r["limitations"]:
            assert limitation.rstrip().endswith("."), f"{question}: {limitation!r}"


def test_a_plain_lookup_is_unaffected(client):
    r = client.post("/api/ask", json={"question": "What is our revenue?"}).json()
    assert r["trust_level"] == "SAFE"
    assert r["llm_fallback"] is False
    assert "72,705,593" in r["answer"]
