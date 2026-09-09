"""
test_semantic_intent_matrix.py -- one business question, many ways of asking it.

The acceptance question is not "does this sentence work?" but "can an owner say the same thing
however they naturally would, and get the same reading?" So the tests below are built as
PARAPHRASE GROUPS: every member of a group must resolve to the same analytical intent, because
every member means the same thing. A group passing for one phrasing and failing for another is
exactly the defect this file exists to catch.

Two rules the matrix enforces about the mechanism, not just the outcome:

  * Nothing here may be satisfied by a handler for an individual sentence. Each group mixes
    English, Tanglish and clipped phrasing, so the only way to pass a group is to understand the
    words rather than to recognise the sentence.
  * A generic lookup opening -- "how much", "what is", "evlo" -- must never outrank a stronger
    analytical meaning present in the same utterance. "revenue evlo?" is a lookup; "revenue
    usually evlo?" is not.

Where a capability genuinely does not exist, the group asserts the honest limitation rather than
an answer. That is the correct outcome, and pinning it is what stops a future change from
inventing the missing method instead.
"""
import pytest

from engine import analysis_capability as acap
from engine import concept_map
from engine import time_resolution as timeres
from engine.analyst_intelligence import AnalystIntelligence
from engine.intent_models import (LOOKUP, TREND, COMPARISON, DRIVER, ANOMALY, RISK_SCAN)
from engine.question_normalize import normalize_owner_question
from engine.question_understanding import classify_intents
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture(scope="module")
def analyst():
    return AnalystIntelligence(verbalize=False)


def ask(analyst, question):
    analyst.llm.reset()
    return analyst.ask(question)


def normalized(question):
    return normalize_owner_question(question)[0]


def intents_of(question):
    return classify_intents(normalized(question))


def capability_of(question):
    return acap.classify_analysis_capability(normalized(question))


# --- the matrix -----------------------------------------------------------------------------------
#
# (group name, required intent, phrasings). The intent is the MEANING every phrasing shares.

TREND_GROUP = (
    "revenue trend?",
    "how is revenue doing?",
    "revenue epdi poguthu?",
    "revenue eppadi poitu irukku?",
    "revenue improve aagudha?",
    "is revenue getting better?",
    "is revenue improving?",
)

COMPARISON_GROUP = (
    "revenue increase aacha?",
    "did revenue go up?",
    "revenue change enna?",
    "how did revenue change?",
    "revenue koranjutha?",
    "did revenue increase?",
    "how much did revenue move?",
)

DRIVER_GROUP = (
    "why revenue fell?",
    "revenue yen koranjuthu?",
    "why did revenue drop?",
    "revenue yen kammi aachu?",
    "what caused revenue to fall?",
)

LOOKUP_GROUP = (
    "what is our revenue?",
    "how much revenue?",
    "revenue evlo?",
    "revenue amount sollu",
    "show me revenue",
)

ANOMALY_GROUP = (
    "revenue unusual ah irukka?",
    "is revenue unusual?",
    "any odd revenue?",
    "does revenue look off?",
)

FORECAST_GROUP = (
    "next month revenue expected?",
    "revenue next month epdi irukkum?",
    "what revenue do you expect next month?",
    "next month revenue varuma?",
    "forecast next month revenue",
)

RISK_GROUP = (
    "what are my biggest risks?",
    "risk enna?",
    "anything risky?",
    "what should i worry about?",
)


@pytest.mark.parametrize("question", TREND_GROUP)
def test_every_way_of_asking_about_direction_is_a_trend(question):
    """A verb of motion carries this intent far more often than the word "trend" does."""
    assert TREND in intents_of(question), f"{question!r} -> {intents_of(question)}"


@pytest.mark.parametrize("question", COMPARISON_GROUP)
def test_every_way_of_asking_whether_it_moved_is_a_comparison(question):
    assert COMPARISON in intents_of(question), f"{question!r} -> {intents_of(question)}"


@pytest.mark.parametrize("question", DRIVER_GROUP)
def test_every_way_of_asking_why_is_a_driver_question(question):
    assert DRIVER in intents_of(question), f"{question!r} -> {intents_of(question)}"
    assert capability_of(question).capability_id == "driver_analysis", question


@pytest.mark.parametrize("question", LOOKUP_GROUP)
def test_a_bare_amount_question_stays_a_lookup(question):
    assert intents_of(question) == (LOOKUP,), f"{question!r} -> {intents_of(question)}"
    assert capability_of(question).capability_id == "kpi_lookup", question


@pytest.mark.parametrize("question", ANOMALY_GROUP)
def test_every_way_of_asking_whether_it_looks_wrong_is_an_anomaly_question(question):
    assert ANOMALY in intents_of(question), f"{question!r} -> {intents_of(question)}"


@pytest.mark.parametrize("question", FORECAST_GROUP)
def test_every_forward_looking_phrasing_reaches_forecasting(question):
    assert capability_of(question).capability_id == "revenue_forecast", question


@pytest.mark.parametrize("question", RISK_GROUP)
def test_every_way_of_asking_about_risk_is_a_risk_question(question):
    assert RISK_SCAN in intents_of(question), f"{question!r} -> {intents_of(question)}"


# --- the groups must not collapse into one another --------------------------------------------------

def test_the_generic_openings_never_outrank_a_stronger_meaning():
    """"How much" and "evlo" open a lookup and also open half the other intents. The stronger
    reading present in the same sentence wins."""
    assert intents_of("revenue evlo?") == (LOOKUP,)
    assert TREND in intents_of("revenue epdi poguthu?")
    assert COMPARISON in intents_of("how much did revenue move?")
    assert DRIVER in intents_of("revenue yen koranjuthu?")
    assert capability_of("revenue usually evlo?").capability_id != "kpi_lookup"


@pytest.mark.parametrize("group,other", [
    (TREND_GROUP, LOOKUP_GROUP),
    (COMPARISON_GROUP, LOOKUP_GROUP),
    (DRIVER_GROUP, LOOKUP_GROUP),
])
def test_an_analytical_group_is_never_read_as_a_bare_lookup(group, other):
    for question in group:
        assert intents_of(question) != (LOOKUP,), f"{question!r} collapsed to a plain lookup"


def test_english_and_tanglish_of_the_same_question_agree():
    """The pairs below are translations of one another. A difference between them is a
    vocabulary gap, not a difference in what was asked."""
    pairs = [
        ("how is revenue doing?", "revenue epdi poguthu?"),
        ("did revenue go up?", "revenue increase aacha?"),
        ("why did revenue drop?", "revenue yen koranjuthu?"),
        ("what is our revenue?", "revenue evlo?"),
        ("is revenue unusual?", "revenue unusual ah irukka?"),
        ("what revenue do you expect next month?", "next month revenue varuma?"),
    ]
    for english, tanglish in pairs:
        assert capability_of(english).capability_id == capability_of(tanglish).capability_id, (
            f"{english!r} and {tanglish!r} were understood differently")


# --- the subject is understood across wordings ------------------------------------------------------

@pytest.mark.parametrize("question,concept", [
    ("collections evlo?", "collections"),
    ("how much have we collected?", "collections"),
    ("expenses evlo?", "expenses"),
    ("what are total expenses?", "expenses"),
    ("occupancy evlo?", "occupancy"),
    ("what is current occupancy?", "occupancy"),
    ("tenant dues evlo?", "tenant_dues"),
    ("how much do tenants owe?", "tenant_dues"),
    ("profit evlo?", "profit"),
    ("typical rent enna?", "rent"),
    ("what is our typical rent?", "rent"),
])
def test_the_business_subject_survives_the_wording(question, concept):
    names = [c.name for c, _ in concept_map.match(normalized(question))]
    assert concept in names, f"{question!r} -> {names}"


# --- period semantics -------------------------------------------------------------------------------

@pytest.mark.parametrize("phrase", ["last 3 months", "past 3 months", "recent 3 months",
                                    "previous 3 months", "trailing 3 months"])
def test_a_rolling_window_resolves_the_same_way_however_it_is_worded(phrase):
    label, start, end = timeres.parse_period(normalized(phrase))
    assert label == "last 3 months", f"{phrase!r} -> {label}"
    assert (start, end) == ("2026-05-01", "2026-07-31"), f"{phrase!r} -> {start}..{end}"


def test_the_window_ends_at_the_last_complete_month():
    """The snapshot month is partial. Including it would report a part-month as a whole one."""
    _label, _start, end = timeres.parse_period("last 3 months")
    assert end == "2026-07-31"


@pytest.mark.parametrize("phrase,label", [
    ("last quarter", "last quarter"),
    ("this month", "this month"),
    ("last month", "last month"),
    ("august", "2026-08"),
])
def test_the_named_and_relative_periods_are_unchanged(phrase, label):
    assert timeres.parse_period(phrase)[0] == label


def test_a_span_resolves_to_the_whole_span():
    """"From June to August" asks about three months. Answering about June is a substitution."""
    label, start, end = timeres.parse_period("from june to august")
    assert start == "2026-06-01" and end == "2026-08-31", f"{label}: {start}..{end}"


def test_a_window_is_refused_rather_than_answered_with_one_month(analyst):
    """No calculator aggregates a span. The figure for May carrying a "last 3 months" label
    would be the worst of both -- a real number, for a period nobody asked about."""
    a = ask(analyst, "last 3 months revenue")
    assert a.trust_level == "NOT_DETERMINABLE"
    assert NOT_DETERMINABLE_TEXT in a.text
    for month_figure in ("3,153,828", "3,300,730", "3,336,114"):
        assert month_figure not in a.text, "a single month was returned for a window"
    assert "72,705,593" not in a.text, "the all-time total was returned for a window"


def test_a_single_period_still_answers(analyst):
    """The window refusal must not swallow the periods that do work."""
    assert "3,336,114" in ask(analyst, "revenue last month").text
    assert "3,300,730" in ask(analyst, "what was revenue in June 2026?").text


# --- end to end: the paraphrases reach the same answer ------------------------------------------------

@pytest.mark.parametrize("question", TREND_GROUP[:5])
def test_the_trend_group_answers_with_a_direction_not_a_total(analyst, question):
    a = ask(analyst, question)
    assert "72,705,593" not in a.text, f"{question}: the all-time total answered a trend question"
    assert "Trend direction" in a.text or "increased" in a.text or "decreased" in a.text


@pytest.mark.parametrize("question", FORECAST_GROUP)
def test_the_forecast_group_answers_with_a_projection(analyst, question):
    a = ask(analyst, question)
    assert a.trust_level == "SAFE", f"{question}: {a.trust_level}"
    assert "Projected revenue" in a.text, question


@pytest.mark.parametrize("question", LOOKUP_GROUP)
def test_the_lookup_group_answers_with_the_recorded_total(analyst, question):
    a = ask(analyst, question)
    assert a.trust_level == "SAFE", f"{question}: {a.trust_level}"
    assert "72,705,593" in a.text, question


# --- capabilities that genuinely do not exist ----------------------------------------------------------

@pytest.mark.parametrize("question", ["revenue usually evlo?", "typical revenue enna?",
                                      "what is typical revenue?"])
def test_a_statistic_that_is_not_offered_gets_the_honest_limitation(analyst, question):
    """The investigation established that the revenue mean describes a window of growth rather
    than a typical month, so no such statistic exists. The all-time total is not a substitute:
    it is a different quantity wearing the question's label."""
    assert capability_of(question).capability_id == "statistical_summary"
    a = ask(analyst, question)
    assert "72,705,593" not in a.text, "the total was returned as a typical value"
    assert "not implemented" in a.text.lower()


@pytest.mark.parametrize("question", ANOMALY_GROUP)
def test_an_anomaly_question_is_understood_and_then_honestly_refused(analyst, question):
    """Understanding the question and having a method for it are different things. No threshold
    for "unusual" exists in the records, and none is invented."""
    a = ask(analyst, question)
    assert a.trust_level == "NOT_DETERMINABLE", question
    assert "threshold" in a.text.lower()


def test_a_measure_with_competing_definitions_asks_rather_than_choosing(analyst):
    """Understanding "collections koranjutha?" does not license picking one of its two
    evidence-backed definitions."""
    a = ask(analyst, "collections koranjutha?")
    assert a.ask_result.status == "NEEDS_CLARIFICATION"
    assert "definition of collections" in a.text.lower()


# --- the guards that must not be weakened -----------------------------------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("what is our revenue?", "SAFE"),
    ("what is current occupancy?", "SHOW_BOTH"),
    ("what was profit last month?", "BLOCK"),
    ("what is our typical rent?", "DISCLOSE"),
])
def test_no_trust_posture_moved(analyst, question, expected):
    assert ask(analyst, question).trust_level == expected, question


def test_the_whole_business_workflows_still_own_their_questions():
    assert capability_of("what changed?").route == acap.ROUTE_WHAT_CHANGED
    assert capability_of("how is my business doing?").route == acap.ROUTE_BRIEFING
    assert capability_of("what are my biggest risks?").route == acap.ROUTE_WHAT_TO_DO
    assert capability_of("which numbers can i trust?").route == acap.ROUTE_WHAT_TO_TRUST


def test_descriptive_analysis_keeps_the_questions_it_serves():
    for question in ("what is our typical rent?", "typical rent enna?",
                     "how much do deposits vary?", "how variable is revenue?"):
        assert capability_of(question).route == acap.ROUTE_DESCRIPTIVE, question
