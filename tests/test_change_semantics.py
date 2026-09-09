"""
test_change_semantics.py -- "how did X change?" must be read as a change question.

Two defects met here, both product-wide and both found while building the rent lookup.

The first was in the normaliser: its fuzzy repair rewrote "change" to "charged", so
"how did revenue change?" arrived as "how did revenue charged" -- a string carrying no trend,
comparison or driver marker at all. Every change question in the product silently became a
lookup.

The second survived the first being fixed. The intent table catches "increased", "went up",
"compared to" and a dozen other ways of asking how something moved, but not the plainest one,
so a repaired "how did revenue change?" still classified as a lookup and came back with the
all-time revenue total: an answer about a level, given to a question about a movement.

The tests below pin both, and pin the four readings that must NOT be swept up with them --
"what changed?" is the whole-business review, "will revenue increase next month?" is a
forecast, an explicit month-vs-month ask is a comparison, and rent has no history to compare.
"""
import re

import pytest

from engine import analysis_capability as acap
from engine.analyst_intelligence import AnalystIntelligence
from engine.question_normalize import normalize_owner_question
from engine.question_understanding import classify_intents
from engine.intent_models import COMPARISON, DRIVER
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture(scope="module")
def analyst():
    return AnalystIntelligence(verbalize=False)


def answer(analyst, question):
    analyst.llm.reset()
    return analyst.ask(question)


# --- 1. normalisation preserves the words that carry analytical intent ---------------------------

PRESERVED = (
    "change", "changed", "changing", "changes", "history", "historical", "previously",
    "before", "last", "prior", "compared", "comparison", "increased", "decreased",
    "rise", "fell", "growth", "movement",
)


@pytest.mark.parametrize("word", PRESERVED)
def test_the_word_survives_normalisation(word):
    """Each of these turns a question into a different question if it is rewritten. Some are
    protected by the locklist because their rewrite was demonstrated; the rest survive the
    repair on their own. Asserted by behaviour either way, so a future vocabulary change that
    breaks one is caught here rather than in production."""
    for carrier in (word, f"how did revenue {word}", f"the {word} of collections",
                    f"did expenses {word}"):
        cleaned = normalize_owner_question(carrier)[0]
        assert word in cleaned.split(), f"{carrier!r} -> {cleaned!r}"


def test_the_specific_rewrites_that_broke_change_questions_are_gone():
    """The exact corruption: every one of these became "charged", which is a different word
    about a different thing."""
    for question in ("How did revenue change?", "What changed?", "Why did expenses change?",
                     "How did collections change?", "Did rent change?",
                     "Which costs changed?"):
        cleaned = normalize_owner_question(question)[0]
        assert "charged" not in cleaned, f"{question!r} -> {cleaned!r}"
        assert "chang" in cleaned, f"{question!r} -> {cleaned!r}"


def test_the_locklist_was_not_padded_beyond_the_demonstrated_defect():
    """Locking a word suppresses spelling repair for it, so each lock has to earn its place.
    These survive unlocked, and are therefore deliberately absent."""
    from engine.question_normalize import _ENGLISH_LOCKED

    for word in ("growth", "movement", "comparison", "compared", "prior"):
        assert word not in _ENGLISH_LOCKED, (
            f"{word!r} was locked without a demonstrated rewrite")


# --- 2. a change question is classified as one --------------------------------------------------

CHANGE_QUESTIONS = (
    "How did revenue change?",
    "How much did revenue move?",
    "How did collections change?",
    "How did expenses change?",
    "Which costs changed?",
)


@pytest.mark.parametrize("question", CHANGE_QUESTIONS)
def test_asking_how_a_measure_moved_is_a_comparison_not_a_lookup(question):
    assert COMPARISON in classify_intents(question), (
        f"{question!r} -> {classify_intents(question)}")


@pytest.mark.parametrize("question,measure", [
    ("How did revenue change?", "Revenue"),
    ("How much did revenue move?", "Revenue"),
    ("How did expenses change?", "expenses"),
])
def test_the_answer_states_a_movement_not_an_all_time_total(analyst, question, measure):
    """The all-time revenue total is Rs.72,705,593. It answers "what is revenue", and it is
    the wrong answer to "how did revenue change"."""
    a = answer(analyst, question)
    assert a.trust_level == "SAFE", f"{question}: {a.trust_level}"
    text = a.text
    assert "72,705,593" not in text, "the all-time total was returned for a change question"
    assert re.search(r"(increased|decreased|unchanged)", text, re.I), text[:200]
    assert re.search(r"between .+ and ", text, re.I), "the two periods are not stated"


def test_why_did_it_change_still_reaches_driver_analysis(analyst):
    assert DRIVER in classify_intents("Why did revenue change?")
    assert acap.classify_analysis_capability(
        "Why did revenue change?").capability_id == "driver_analysis"
    a = answer(analyst, "Why did revenue change?")
    assert a.trust_level == "SAFE"


@pytest.mark.parametrize("question", [
    "Did revenue increase?",
    "Did collections increase?",
    "Why did expenses fall?",
])
def test_the_directional_questions_that_already_worked_still_do(question):
    assert COMPARISON in classify_intents(question), question


def test_collections_change_reaches_the_comparison_path(analyst):
    """Collections carries competing definitions, so the comparison itself is refused. What
    matters here is that it is refused AS a comparison, not answered as a lookup."""
    assert acap.classify_analysis_capability(
        "How did collections change?").capability_id == "period_comparison"
    a = answer(analyst, "How did collections change?")
    # A pending clarification is not a refusal, and carries no trust posture of its own:
    # nothing has been computed yet, so there is nothing to label. The question is put back to
    # the owner with both definitions rather than answered against one of them.
    assert a.ask_result.status == "NEEDS_CLARIFICATION"
    assert a.trust_level == ""
    assert "definition of collections" in a.text.lower()


# --- 3. what must NOT be swept up ------------------------------------------------------------------

def test_what_changed_stays_the_whole_business_review(analyst):
    """It names no measure. Reading it as a period comparison would ask the owner which measure
    they meant when they deliberately named none."""
    assert COMPARISON not in classify_intents("What changed?")
    assert acap.classify_analysis_capability(
        "What changed?").route == acap.ROUTE_WHAT_CHANGED
    a = answer(analyst, "What changed?")
    assert a.owner_intent != "metric_question" or a.text
    assert "Executive takeaway" in a.text or "changed" in a.text.lower()


@pytest.mark.parametrize("question", [
    "What changed?", "What has changed?", "What moved?", "Any changes?",
])
def test_every_whole_business_phrasing_keeps_its_workflow(question):
    assert COMPARISON not in classify_intents(question), question


def test_a_forecast_is_not_a_historical_change(analyst):
    """"Will revenue increase next month?" looks forward. It must reach the forecast, not a
    comparison of two months already recorded."""
    cap = acap.classify_analysis_capability("Will revenue increase next month?")
    assert cap.capability_id == "revenue_forecast"
    a = answer(analyst, "Will revenue increase next month?")
    assert a.trust_level == "SAFE"
    assert "Projected revenue" in a.text


def test_an_explicit_period_comparison_stays_a_period_comparison(analyst):
    question = "Compare August revenue with July revenue"
    assert acap.classify_analysis_capability(question).capability_id == "period_comparison"
    a = answer(analyst, question)
    assert "August" in a.text and "July" in a.text


@pytest.mark.parametrize("question,expected_trust", [
    ("What is our revenue?", "SAFE"),
    ("What are total expenses?", "SAFE"),
    ("What is current occupancy?", "SHOW_BOTH"),
])
def test_plain_lookups_are_untouched(analyst, question, expected_trust):
    assert COMPARISON not in classify_intents(question), question
    a = answer(analyst, question)
    assert a.trust_level == expected_trust, f"{question}: {a.trust_level}"


@pytest.mark.parametrize("question", [
    "What's typical rent?", "How much do deposits vary?",
    "How much revenue moves month to month?",
])
def test_descriptive_analysis_still_wins_its_own_questions(analyst, question):
    assert acap.classify_analysis_capability(question).route == acap.ROUTE_DESCRIPTIVE, question
    a = answer(analyst, question)
    assert a.trust_level in ("SAFE", "DISCLOSE"), f"{question}: {a.trust_level}"


def test_the_risk_scan_is_untouched():
    assert acap.classify_analysis_capability(
        "What are my biggest risks?").route == acap.ROUTE_WHAT_TO_DO


# --- 4. rent has no history to compare -----------------------------------------------------------------

RENT_CHANGE_QUESTIONS = ("Did A12 rent change?", "How did rent change?",
                         "How did A12 rent change?")


@pytest.mark.parametrize("question", RENT_CHANGE_QUESTIONS)
def test_a_rent_change_question_is_refused_not_answered_with_todays_rent(analyst, question):
    """The recorded rent carries no effective date and no prior value, so a change over time
    cannot be established. Today's figure is not an answer to how it changed."""
    a = answer(analyst, question)
    assert a.trust_level == "NOT_DETERMINABLE", f"{question}: {a.trust_level}"
    assert NOT_DETERMINABLE_TEXT in a.text
    for figure in ("19,500", "15,500", "14,500"):
        assert figure not in a.text, (
            f"{question}: the current rent was presented as a historical change")


def test_the_rent_refusal_explains_what_the_export_lacks(analyst):
    text = answer(analyst, "Did A12 rent change?").text.lower()
    assert "no date is attached" in text
    assert "no earlier value is kept" in text
    assert "position today" in text


def test_the_rent_refusal_is_driven_by_the_registry(analyst):
    """Not a rule hardcoded against this metric: the registry declares the limitation and the
    pipeline reads it."""
    from engine.semantic_registry import SemanticRegistry

    policy = SemanticRegistry().get("M.RENT.001").historical_policy
    assert policy.strip().upper().startswith("CURRENT STATE ONLY")


def test_a_current_rent_question_still_answers(analyst):
    """The limitation is about history, not about rent. Asking for it now still works."""
    a = answer(analyst, "What is the rent for A12?")
    assert a.trust_level == "DISCLOSE"
    assert "19,500" in a.text


# --- 5. owner language ------------------------------------------------------------------------------------

_INTERNAL = (
    (r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", "metric id"),
    (r"\bDQ\.\d{3}\b", "data-quality id"),
    (r"\bC\.\d{3}\b", "conflict id"),
    (r"\bv_[a-z0-9_]+\b", "database view"),
    (r"\b[\w.-]+\.(?:py|csv|md|json)\b", "file name"),
    (r"\b(?:tenant_allotments|monthly_rental|journal_lines|staying_status)\b", "column name"),
    (r"\b(?:SELECT|FROM|GROUP BY|JOIN)\b", "SQL"),
    (r"month-keyed|series key|classify_intents|_INTENT_MARKERS", "implementation term"),
)


@pytest.mark.parametrize("question", list(CHANGE_QUESTIONS) + list(RENT_CHANGE_QUESTIONS) + [
    "Why did revenue change?", "Will revenue increase next month?",
    "Compare August revenue with July revenue",
])
def test_no_internal_identifier_or_implementation_term_reaches_the_owner(analyst, question):
    text = answer(analyst, question).text
    for pattern, what in _INTERNAL:
        assert not re.search(pattern, text), f"{what} leaked into the answer for {question!r}"


def test_no_answer_begins_mid_sentence(analyst):
    """Stripping an identifier from the front of an engine reason left the owner reading a
    sentence that started in the middle of a clause."""
    for question in RENT_CHANGE_QUESTIONS:
        for line in answer(analyst, question).text.splitlines():
            line = line.strip()
            if not line or line.startswith("•"):
                continue
            assert line[0].isupper() or line[0].isdigit() or line[0] in "₹", (
                f"{question}: answer line starts mid-sentence: {line[:60]!r}")


# --- 6. the two classifiers must agree -----------------------------------------------------------------

# Question understanding and capability classification read the same question independently.
# Execution follows the intent, so a disagreement produces the right answer today -- and would
# produce the wrong one the moment anything routes on the capability id alone. `kpi_lookup`'s
# markers are the generic openings ("how much", "what is", "show me"), and they were outranking
# an intent that had already been established: "how much did revenue move?" was a COMPARISON to
# understanding and a kpi_lookup to the classifier.

MOVEMENT_QUESTIONS = (
    "How much did revenue move?",
    "How much did revenue change?",
    "How much did collections move?",
    "How much did expenses move?",
    "Did revenue move?",
    "Did revenue change?",
    "How much did revenue increase?",
    "How much did revenue decrease?",
)

LOOKUP_QUESTIONS = (
    "How much is revenue?",
    "What is revenue?",
    "Average revenue",
    "What's the average revenue?",
    "Show me revenue",
    "How much have we collected?",
)


@pytest.mark.parametrize("question", MOVEMENT_QUESTIONS)
def test_a_movement_question_classifies_as_the_comparison_capability(question):
    cap = acap.classify_analysis_capability(question)
    assert cap.capability_id == "period_comparison", f"{question}: {cap.capability_id}"
    assert cap.route == acap.ROUTE_METRIC


@pytest.mark.parametrize("question", MOVEMENT_QUESTIONS + LOOKUP_QUESTIONS + (
    "How did revenue change?", "Why did revenue change?", "What changed?",
    "Will revenue increase next month?", "Compare August revenue with July revenue",
    "What are my biggest risks?", "What is current occupancy?", "What's typical rent?",
    "How much do deposits vary?", "Did A12 rent change?",
))
def test_the_capability_never_contradicts_the_established_intent(question):
    """Agreement, not identity. A more specific capability may refine the intent -- a driver
    question is a comparison plus a why, forecasting looks forward, descriptive analysis
    describes a shape -- but a question understanding read as analysis must never come back
    classified as a plain lookup."""
    intents = classify_intents(question)
    cap = acap.classify_analysis_capability(question)
    if cap.capability_id != "kpi_lookup":
        return
    assert intents == ("lookup",), (
        f"{question!r} was classified as a plain lookup but understood as {intents}")


@pytest.mark.parametrize("question", LOOKUP_QUESTIONS)
def test_a_plain_lookup_is_not_dragged_into_the_comparison_path(question):
    """"How much" and "average" are not movement. Only explicit change semantics move."""
    assert COMPARISON not in classify_intents(question), question
    assert acap.classify_analysis_capability(question).capability_id != "period_comparison", (
        question)


def test_the_movement_question_produces_the_existing_comparison_answer(analyst):
    a = answer(analyst, "How much did revenue move?")
    assert a.trust_level == "SAFE"
    assert "72,705,593" not in a.text, "the all-time total was returned for a movement question"
    assert re.search(r"(increased|decreased|unchanged)", a.text, re.I)
    assert re.search(r"between .+ and ", a.text, re.I)


def test_the_average_question_keeps_the_path_it_had(analyst):
    """Not a comparison, and not descriptive either: central tendency alone on a monthly series
    is a level question, which is why it stays a lookup."""
    cap = acap.classify_analysis_capability("What's the average revenue?")
    assert cap.capability_id == "kpi_lookup"
    assert cap.route == acap.ROUTE_METRIC
    a = answer(analyst, "What's the average revenue?")
    assert a.trust_level == "SAFE"


def test_the_specific_capabilities_still_outrank_the_intent(analyst):
    """The fix lets a generic lookup opening yield to the intent. It must not let the intent
    override a capability that read the question more precisely."""
    assert acap.classify_analysis_capability(
        "Why did revenue change?").capability_id == "driver_analysis"
    assert acap.classify_analysis_capability(
        "Will revenue increase next month?").capability_id == "revenue_forecast"
    assert acap.classify_analysis_capability(
        "What's typical rent?").route == acap.ROUTE_DESCRIPTIVE
    assert acap.classify_analysis_capability(
        "What changed?").route == acap.ROUTE_WHAT_CHANGED
    assert acap.classify_analysis_capability(
        "What are my biggest risks?").route == acap.ROUTE_WHAT_TO_DO


def test_the_collections_definition_protection_survives_the_reclassification(analyst):
    """Collections carries competing definitions. Reaching the comparison path must not become
    a way to get one of them picked silently."""
    a = answer(analyst, "How much did collections move?")
    assert a.ask_result.status == "NEEDS_CLARIFICATION"
    assert a.trust_level == ""
    assert "definition of collections" in a.text.lower()
    assert "19,500" not in a.text
    lookup = answer(analyst, "How much have we collected?")
    assert "definition" in lookup.text.lower()


def test_the_rent_historical_limitation_survives_the_reclassification(analyst):
    a = answer(analyst, "Did A12 rent change?")
    assert a.trust_level == "NOT_DETERMINABLE"
    assert NOT_DETERMINABLE_TEXT in a.text
    for figure in ("19,500", "15,500", "14,500"):
        assert figure not in a.text
