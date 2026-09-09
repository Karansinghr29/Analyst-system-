"""
test_owner_routing_fixes.py -- three UAT findings, pinned so they cannot come back.

Each of these was a case where the system had the right answer and did not deliver it:

  1. Revenue forecasting was implemented, registered as implemented, and tested -- and the owner
     entry point still replied that no forecasting method was available, because the capability
     classifier called it a gap before the pipeline could reach the forecast.
  2. "rent" was a trigger phrase on the revenue concept, so a rent question came back with a
     revenue total. A wrong number is worse than a refusal, and this was a wrong number.
  3. Nineteen allotments record a rent of zero. They are real records and stay counted; what the
     export does not say is what each zero means, and the output said nothing either way.
"""
import re

import pytest

from engine import analysis_capability as acap
from engine import concept_map
from engine import descriptive_routing as droute
from engine.analyst_intelligence import AnalystIntelligence


@pytest.fixture(scope="module")
def analyst():
    return AnalystIntelligence(verbalize=False)


def answer(analyst, question):
    analyst.llm.reset()
    return analyst.ask(question)


# --- A. forecasting through the real owner entry point --------------------------------------------

FORECAST_QUESTIONS = (
    "Forecast next month revenue",
    "What will revenue look like next month?",
    "Will revenue increase next month?",
    "Forecast revenue for the next 3 months",
)


@pytest.mark.parametrize("question", FORECAST_QUESTIONS)
def test_the_owner_entry_point_returns_a_forecast_not_a_capability_gap(analyst, question):
    a = answer(analyst, question)
    assert a.trust_level == "SAFE", f"{question}: {a.trust_level}"
    assert "Projected revenue" in a.text, a.text[:200]
    for gap in ("isn't currently available", "not implemented", "cannot invent"):
        assert gap not in a.text, f"{question} still answers with the capability gap"


@pytest.mark.parametrize("question", FORECAST_QUESTIONS)
def test_the_forecast_carries_its_empirical_interval(analyst, question):
    """A projection without its tested accuracy invites the owner to read it as a measurement."""
    text = answer(analyst, question).text
    assert "usually" in text and "between" in text, "the prediction interval was dropped"
    assert "%" in text, "the backtested error was dropped"


def test_the_occupancy_predictor_rejection_is_still_disclosed(analyst):
    text = answer(analyst, "Forecast revenue for the next 3 months").text.lower()
    assert "occupancy was tested as a predictor and is not used" in text
    for causal in ("occupancy causes", "caused by occupancy", "occupancy drives"):
        assert causal not in text


def test_the_horizon_limit_holds_and_refuses_honestly(analyst):
    """Six months is the range the backtest measured. Beyond it there is no tested accuracy,
    so there is no forecast -- and the answer must not wear a SAFE badge."""
    ok = answer(analyst, "Forecast revenue for the next 6 months")
    assert ok.trust_level == "SAFE"

    too_far = answer(analyst, "Forecast revenue for the next 12 months")
    assert too_far.trust_level == "NOT_DETERMINABLE"
    assert "6 months" in too_far.text
    assert "Projected revenue for" not in too_far.text, "a refused horizon produced a figure"


def test_no_forecast_figure_originates_outside_the_deterministic_engine(analyst):
    """Every figure the owner sees must be one `engine/forecasting.py` produced."""
    from engine import forecasting

    a = answer(analyst, "Forecast next month revenue")
    expected = forecasting.forecast_revenue(1)
    assert expected.available
    rendered = {v.replace(",", "") for v in re.findall(r"₹([\d,]+\.\d{2})", a.text)}
    for value in (expected.points[0].value, expected.points[0].lower, expected.points[0].upper):
        assert f"{value:.2f}" in rendered, f"{value} is not the engine's figure"


def test_unsupported_forecasts_keep_the_capability_gap_they_had(analyst):
    """The fix opens exactly one door. A measure with no validated model, and a
    driver-conditioned scenario, keep the refusal they already gave."""
    occupancy = answer(analyst, "Forecast occupancy next month")
    assert "isn't currently available" in occupancy.text
    assert acap.classify_analysis_capability(
        "Forecast occupancy next month").route == acap.ROUTE_CAPABILITY_GAP

    scenario = answer(analyst, "What if occupancy were 80%?")
    assert acap.classify_analysis_capability(
        "What if occupancy were 80%?").capability_id == "scenario_analysis"
    assert "not implemented" in scenario.text.lower()


def test_the_classifier_agrees_with_what_the_engine_can_serve():
    """Classification and execution must not disagree about what is supported."""
    for question in FORECAST_QUESTIONS:
        assert acap.supported_forecast(question), question
        cap = acap.classify_analysis_capability(question)
        assert cap.capability_id == "revenue_forecast"
        assert cap.route == acap.ROUTE_METRIC
    for question in ("Forecast occupancy next month", "Forecast expenses next month",
                     "What if occupancy were 80%?", "What is our revenue?"):
        assert not acap.supported_forecast(question), question


# --- B. rent does not resolve to revenue -----------------------------------------------------------

@pytest.mark.parametrize("question", [
    "what is typical rent",
    "what is the rent",
    "how variable are rents",
    "what's the distribution of rent",
])
def test_rent_never_resolves_to_the_revenue_concept(question):
    """Rent is the amount recorded against an allotment; revenue is the ledger figure. Matching
    one to the other returned a different quantity as the answer."""
    assert "revenue" not in [c.name for c, _ in concept_map.match(question)], question


def test_rent_resolves_to_the_rent_subject():
    for question in ("what is typical rent", "how variable are rents", "the monthly rent"):
        assert droute.subject_of(question) == "monthly_rent", question


def test_an_explicit_rental_income_question_still_reaches_revenue():
    """"Rental income" and "rental revenue" name the ledger figure, and must keep doing so."""
    for question in ("how much rental income did we get", "what is rental revenue"):
        assert "revenue" in [c.name for c, _ in concept_map.match(question)], question
        assert droute.subject_of(question) == "revenue", question


def test_owner_rent_is_still_its_own_concept():
    """Rent paid to owners is an expense, and was never the same concept as tenant rent."""
    assert [c.name for c, _ in concept_map.match("owner rent paid")] == ["owner_rent"]


def test_a_rent_question_no_longer_answers_with_a_revenue_total(analyst):
    a = answer(analyst, "What's typical rent?")
    assert "14,500" in a.text, "the rent figure is missing"
    assert "72,705,593" not in a.text, "the revenue total was returned for a rent question"


def test_the_concept_map_still_verifies_against_the_registry():
    """Removing phrases must not have left a concept pointing at nothing."""
    from engine.semantic_registry import SemanticRegistry

    assert concept_map.verify_against_registry(SemanticRegistry()) == []


# --- C. apartment questions reach apartment analysis -------------------------------------------------

@pytest.mark.parametrize("question", [
    "How do apartments compare on rent?",
    "Which apartments have the highest typical rent?",
    "compare rent across apartments",
])
def test_apartment_questions_resolve_to_the_apartment_subject(question):
    assert droute.subject_of(question) == "apartment", question
    route = droute.classify(question)
    assert route.kind == "apartments" and route.target == "monthly_rent"


def test_the_apartment_answer_is_an_apartment_comparison(analyst):
    text = answer(analyst, "How do apartments compare on rent?").text
    assert "apartments" in text
    assert re.search(r"\b[A-D]\d{2}\b", text), "no apartment was actually named"


# --- D. existing revenue questions are unchanged -----------------------------------------------------

@pytest.mark.parametrize("question,expected_trust", [
    ("What is our revenue?", "SAFE"),
    ("What is our income?", "SAFE"),
    ("What are total expenses?", "SAFE"),
    ("What is current occupancy?", "SHOW_BOTH"),
])
def test_existing_questions_still_resolve_as_before(analyst, question, expected_trust):
    a = answer(analyst, question)
    assert a.trust_level == expected_trust, f"{question}: {a.trust_level}"


def test_revenue_still_matches_the_revenue_concept():
    for question in ("what is our revenue", "how much did we make", "what is turnover",
                     "revenue by month"):
        names = [c.name for c, _ in concept_map.match(question)]
        assert any(n.startswith("revenue") for n in names), f"{question}: {names}"


# --- E. recorded zeros are disclosed, not reinterpreted -----------------------------------------------

def test_the_zeros_are_still_counted_as_records():
    """No filtering, no reinterpretation: the calculation sees every recorded value."""
    from engine import descriptive as d

    stats = d.cross_section("monthly_rent").stats
    assert stats["zero_count"] == 19
    assert stats["min"] == 0, "a recorded zero was filtered out of the calculation"


def test_the_rent_summary_says_what_a_recorded_zero_does_and_does_not_establish(analyst):
    text = answer(analyst, "What's typical rent?").text
    assert "19 of the 1,186 records hold a recorded value of zero" in text
    lowered = text.lower()
    assert "counted above as recorded" in lowered
    assert "genuine zero arrangement" in lowered
    assert "never entered" in lowered
    # Never called invalid, wrong, or an error -- the export does not establish that.
    for verdict in ("invalid", "incorrect", "erroneous", "bad data", "should be excluded"):
        assert verdict not in lowered, f"a recorded zero was judged {verdict!r}"


def test_the_apartment_comparison_explains_a_range_that_starts_at_zero(analyst):
    text = answer(analyst, "How do apartments compare on rent?").text
    assert "recorded rent of zero" in text
    assert "11 apartments" in text
    lowered = text.lower()
    assert "genuine zero-rent arrangement" in lowered
    assert "never entered" in lowered
    for verdict in ("invalid", "incorrect", "erroneous"):
        assert verdict not in lowered


def test_the_zero_note_does_not_duplicate_the_engine_s_own(analyst):
    """Deposits are three-quarters zeros and the engine already says so. One note, not two."""
    text = answer(analyst, "How much do deposits vary?").text
    assert "the average does not" in text
    assert "hold a recorded value of zero" not in text


# --- F. no internal identifiers ------------------------------------------------------------------------

_INTERNAL = (
    (r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", "metric id"),
    (r"\bDQ\.\d{3}\b", "data-quality id"),
    (r"\bC\.\d{3}\b", "conflict id"),
    (r"\bv_[a-z0-9_]+\b", "database view"),
    (r"\b[\w.-]+\.(?:py|csv|md|json)\b", "file name"),
    (r"\b(?:tenant_allotments|monthly_rental|deposit_paid|balance_due|journal_lines)\b",
     "table or column name"),
    (r"\b(?:SELECT|FROM|GROUP BY|JOIN)\b", "SQL"),
    (r"\b(?:forecast_revenue|supported_forecast|subject_of|cross_section|"
     r"apartment_comparison)\b", "function name"),
)


@pytest.mark.parametrize("question", [
    "Forecast next month revenue",
    "Forecast revenue for the next 3 months",
    "Forecast revenue for the next 12 months",
    "Forecast occupancy next month",
    "What's typical rent?",
    "How do apartments compare on rent?",
    "How much rental income did we get?",
])
def test_no_internal_identifier_reaches_the_owner(analyst, question):
    text = answer(analyst, question).text
    for pattern, what in _INTERNAL:
        assert not re.search(pattern, text), f"{what} leaked into the answer for {question!r}"
