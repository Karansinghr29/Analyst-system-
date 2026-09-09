"""
test_collections_clarification_routing.py -- a valid question about an ambiguous measure.

"Why did collections fall?" is a perfectly good driver question. Collections is the problem:
the records hold two evidence-backed definitions of it, so the pipeline correctly stopped to
ask which one was meant -- and the comparison presenter then overwrote that question with "I
can't produce a period comparison from the available evidence."

That is a different claim, and a false one. No comparison was attempted; one was deferred. The
owner was told about a limitation that does not exist, while the Why panel underneath still
carried the real reason, so the two halves of the same answer contradicted each other.

The rule these tests hold: while a clarification is open, nothing has been computed, so nothing
downstream may speak for the answer -- no comparison figure, no refusal, no trust posture. Once
the owner picks, the question they originally asked runs against the definition they chose,
with that definition's own Trust Gate posture intact.
"""
import os
import re

import pytest

os.environ.setdefault("AI_ANALYTICS_AUTH_DISABLE", "true")
os.environ.pop("AI_ANALYTICS_ENV", None)

QUESTION = "Why did collections fall?"

APPLICATION_LEVEL = "1"
LEDGER_DERIVED = "2"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.service import AnalyticsService, create_app

    return TestClient(create_app(AnalyticsService()))


def ask(client, question, conversation_id=None):
    return client.post(
        "/api/ask", json={"question": question, "conversation_id": conversation_id}).json()


def conversation(client, opening=QUESTION):
    """A fresh conversation with the clarification open, and its id."""
    payload = ask(client, opening)
    return payload, payload["conversation_id"]


def why_of(payload):
    return payload.get("owner_explanation") or {}


def why_text(payload):
    return " ".join(why_of(payload).get("paragraphs") or [])


# --- 1. the question is answered with a question ------------------------------------------------

@pytest.fixture(scope="module")
def opening(client):
    return conversation(client)[0]


def test_a_clarification_is_required_not_a_refusal(opening):
    assert opening["status"] == "NEEDS_CLARIFICATION"


def test_it_is_not_reported_as_an_unavailable_comparison(opening):
    """The exact wording the comparison presenter used to overwrite the clarification with."""
    text = opening["answer"]
    assert "can't produce a period comparison" not in text
    assert "not available from the available evidence" not in text
    assert "unavailable" not in text.lower()


def test_no_trust_posture_is_claimed_while_nothing_has_been_computed(opening):
    """A pending clarification is not a NOT_DETERMINABLE answer. Nothing ran, so there is
    nothing to label -- and labelling it made the UI show a refusal badge over a question."""
    assert opening["trust_level"] == ""
    assert opening["metric_ids"] == []


def test_both_definitions_are_shown(opening):
    text = opening["answer"]
    assert "definition of collections" in text.lower()
    assert "application-level" in text.lower()
    assert "ledger-derived" in text.lower()
    assert "receipts" in text.lower()
    assert "cash/bank accounts" in text.lower()


def test_neither_definition_is_chosen_and_no_figure_is_produced(opening):
    """Choosing silently is the failure this whole exchange exists to prevent."""
    text = opening["answer"]
    assert "₹" not in text, "a collections figure appeared before the definition was resolved"
    assert not re.search(r"\d[\d,]*\.\d{2}", text), "a computed amount leaked into the question"
    for figure in ("3,769,572", "3,547,837", "81,839,404"):
        assert figure not in text, f"{figure} was produced before the definition was chosen"


def test_the_why_panel_explains_the_clarification(opening):
    why = why_of(opening)
    assert why["heading"] == "Why I need one answer from you"
    assert "can't answer" not in why["heading"].lower(), "a refusal heading over a question"
    text = why_text(opening)
    assert "two valid definitions of collections" in text
    assert "won't choose between them on your behalf" in text


# --- 2. choosing the application-level definition ------------------------------------------------

def test_choosing_application_level_runs_the_change_workflow(client):
    _opening, cid = conversation(client)
    chosen = ask(client, APPLICATION_LEVEL, cid)

    assert chosen["status"] == "READY"
    assert chosen["metric_ids"] == ["M.COL.002"], "the monthly series of the chosen definition"
    # The ORIGINAL intent, not a bare lookup of whatever was selected.
    assert re.search(r"(decreased|increased|unchanged)", chosen["answer"], re.I), (
        "the change question became a plain total")
    assert "2026-06-01" in chosen["answer"] and "2026-07-01" in chosen["answer"]


def test_the_application_level_answer_keeps_its_trust_posture(client):
    _opening, cid = conversation(client)
    chosen = ask(client, APPLICATION_LEVEL, cid)
    assert chosen["trust_level"] == "DISCLOSE"


def test_the_application_level_why_says_the_choice_was_the_owners(client):
    _opening, cid = conversation(client)
    chosen = ask(client, APPLICATION_LEVEL, cid)
    text = why_text(chosen)
    assert "definition of collections you chose" in text
    assert "one agreed definition" not in text, (
        "the panel claimed agreement one turn after asking which definition was meant")
    assert "other definition remains available" in text


# --- 3. choosing the ledger-derived definition -----------------------------------------------------

def test_choosing_ledger_derived_runs_against_that_definition(client):
    """The chosen definition is the one that runs. It has no monthly series, so the change
    question is refused ON IT -- not answered from the other definition's series, which is what
    the concept-level lookup used to do."""
    _opening, cid = conversation(client)
    chosen = ask(client, LEDGER_DERIVED, cid)

    assert chosen["metric_ids"] == ["M.COL.003"], "the ledger-derived definition"
    assert "ledger-derived" in chosen["answer"].lower()
    assert chosen["trust_level"] == "NOT_DETERMINABLE"


def test_the_ledger_derived_refusal_does_not_borrow_the_other_definitions_figures(client):
    _opening, cid = conversation(client)
    chosen = ask(client, LEDGER_DERIVED, cid)
    for figure in ("3,769,572", "3,547,837"):
        assert figure not in chosen["answer"], (
            "the application-level series answered a question about the ledger definition")


def test_the_ledger_derived_why_is_headed_as_a_refusal(client):
    """It refused, so it must not be headed "Why this answer is trusted"."""
    _opening, cid = conversation(client)
    chosen = ask(client, LEDGER_DERIVED, cid)
    assert why_of(chosen)["heading"] == "Why I can't answer this"
    assert why_text(chosen), "blank explanation on a refusal"


def test_the_two_choices_lead_to_different_answers(client):
    """If the choice made no difference, asking it would be theatre."""
    _o1, c1 = conversation(client)
    first = ask(client, APPLICATION_LEVEL, c1)
    _o2, c2 = conversation(client)
    second = ask(client, LEDGER_DERIVED, c2)
    assert first["metric_ids"] != second["metric_ids"]
    assert first["answer"] != second["answer"]


# --- 4. asking "why?" while the clarification is open ------------------------------------------------

def test_a_bare_why_while_pending_re_asks_rather_than_answering(client):
    _opening, cid = conversation(client)
    followup = ask(client, "Why?", cid)
    assert followup["status"] == "NEEDS_CLARIFICATION"
    assert "application-level" in followup["answer"].lower()
    assert "ledger-derived" in followup["answer"].lower()


def test_the_followup_why_panel_explains_the_clarification(client):
    _opening, cid = conversation(client)
    followup = ask(client, "Why?", cid)
    why = why_of(followup)
    assert why["heading"] == "Why I need one answer from you"
    assert "two valid definitions of collections" in why_text(followup)


def test_the_followup_why_panel_does_not_dump_the_answer_text(client):
    """The re-ask was being pasted into the panel -- numbering, options and newlines -- under a
    heading saying the question could not be answered."""
    _opening, cid = conversation(client)
    followup = ask(client, "Why?", cid)
    body = followup["answer"]
    for paragraph in why_of(followup)["paragraphs"]:
        assert paragraph not in body, "the answer was restated as its own explanation"
        assert "\n" not in paragraph
        assert "1." not in paragraph and "2." not in paragraph, "option list leaked in"
    assert "still couldn't tell" not in why_text(followup)


def test_the_clarification_survives_the_followup(client):
    """Asking "why?" must not consume or discard the pending question."""
    _opening, cid = conversation(client)
    ask(client, "Why?", cid)
    chosen = ask(client, APPLICATION_LEVEL, cid)
    assert chosen["status"] == "READY"
    assert chosen["metric_ids"] == ["M.COL.002"]


# --- 5. nothing internal reaches the owner --------------------------------------------------------------

_INTERNAL = (
    (r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", "metric id"),
    (r"\bDQ\.\d{3}\b", "data-quality id"),
    (r"\bC\.\d{3}\b", "conflict id"),
    (r"\bv_[a-z0-9_]+\b", "database view"),
    (r"\b[\w.-]+\.(?:py|csv|md|json)\b", "file name"),
    (r"\b(?:SELECT|FROM|GROUP BY|JOIN)\b", "SQL"),
    (r"\b(?:NEEDS_CLARIFICATION|CLAR_[A-Z_]+|SHOW_BOTH|NOT_DETERMINABLE|DISCLOSE)\b",
     "workflow status token"),
)


@pytest.mark.parametrize("turn", ["opening", "followup", "choice"])
def test_no_internal_identifier_reaches_the_owner(client, turn):
    _opening, cid = conversation(client)
    payload = {"opening": _opening,
               "followup": None,
               "choice": None}[turn]
    if turn == "followup":
        payload = ask(client, "Why?", cid)
    elif turn == "choice":
        payload = ask(client, APPLICATION_LEVEL, cid)
    text = payload["answer"] + " " + why_text(payload)
    for pattern, what in _INTERNAL:
        assert not re.search(pattern, text), f"{turn}: {what} leaked"


# --- 6. what must remain unchanged -----------------------------------------------------------------------

def test_the_other_collections_change_phrasings_behave_the_same(client):
    """Not a fix for one sentence: every phrasing of the same question asks the same thing."""
    for question in ("How much did collections change?", "How did collections change?",
                     "Did collections increase?", "collections koranjutha?"):
        payload = ask(client, question)
        assert payload["status"] == "NEEDS_CLARIFICATION", question
        assert "definition of collections" in payload["answer"].lower(), question
        assert "can't produce a period comparison" not in payload["answer"], question


def test_a_plain_collections_lookup_still_clarifies_as_it_always_did(client):
    payload = ask(client, "How much have we collected?")
    assert payload["status"] == "NEEDS_CLARIFICATION"
    assert "definition of collections" in payload["answer"].lower()


@pytest.mark.parametrize("question,expected_trust", [
    ("Why did revenue change?", "SAFE"),
    ("How did revenue change?", "SAFE"),
    ("What is our revenue?", "SAFE"),
])
def test_an_unambiguous_measure_is_never_asked_about(client, question, expected_trust):
    """Revenue has one definition, so it answers straight through. The clarification path must
    not have widened into questions that were never ambiguous."""
    payload = ask(client, question)
    assert payload["status"] != "NEEDS_CLARIFICATION", question
    assert payload["trust_level"] == expected_trust, question
    assert "definition of" not in payload["answer"].lower(), question


def test_revenue_forecasting_is_untouched(client):
    payload = ask(client, "Forecast revenue for the next 3 months")
    assert payload["trust_level"] == "SAFE"
    assert "Projected revenue for the next 3 months" in payload["answer"]
    assert why_of(payload)["heading"] == "Why this projection is offered"


def test_the_normal_metric_why_panel_is_untouched(client):
    payload = ask(client, "What is our revenue?")
    why = why_of(payload)
    assert why["heading"] == "Why this answer is trusted"
    assert "one agreed definition" in " ".join(why["paragraphs"])


@pytest.mark.parametrize("question,expected", [
    ("What is current occupancy?", "SHOW_BOTH"),
    ("What was profit last month?", "BLOCK"),
])
def test_the_other_trust_postures_are_untouched(client, question, expected):
    assert ask(client, question)["trust_level"] == expected, question
