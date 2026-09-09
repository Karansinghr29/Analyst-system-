"""
test_forecast_named_months.py -- a named future month must be forecast as that month.

The defect: `parse_horizon` recognised "next 3 months" and nothing else, so every explicitly
named month fell to its default of 1 and was answered with the FIRST forecast month. Asking for
October 2026, November 2026 or January 2027 all returned August 2026's projection, with nothing
in the answer to say a different month had been substituted. That is the silent substitution the
rest of this system exists to prevent, and it was happening in the one place where the owner
cannot check the answer against a record.

Two questions decide every case here, in order:

  1. Which calendar month was named?
  2. How many months ahead of the last complete operating month is it?

A month already recorded is a historical question, whatever verb asked for it. A month within
the supported horizon is forecast as itself. A month beyond it gets the refusal the horizon
limit already carries.
"""
import re

import pytest

from engine import forecasting as fc
from engine.analyst_intelligence import AnalystIntelligence
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture(scope="module")
def analyst():
    return AnalystIntelligence(verbalize=False)


def answer(analyst, question):
    analyst.llm.reset()
    return analyst.ask(question)


# The last complete operating month in this export is 2026-07, so the supported window runs
# 2026-08 (h=1) .. 2027-01 (h=6). These are derived, not hardcoded, so the fixture moving does
# not silently turn the tests into assertions about nothing.
def _supported_months():
    base = fc.monthly_revenue_series()[-1][0]
    year, month = int(base[:4]), int(base[5:7])
    out = []
    for step in range(1, fc.MAX_HORIZON + 1):
        m = month + step
        out.append(f"{year + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}")
    return out


SUPPORTED = _supported_months()
MONTH_NAMES = {"2026-08": "August 2026", "2026-09": "September 2026", "2026-10": "October 2026",
               "2026-11": "November 2026", "2026-12": "December 2026",
               "2027-01": "January 2027"}


# --- 1. month resolution -------------------------------------------------------------------------

@pytest.mark.parametrize("question,period", [
    ("Forecast revenue for September 2026", "2026-09"),
    ("Forecast revenue for October 2026", "2026-10"),
    ("Forecast revenue for November 2026", "2026-11"),
    ("Forecast revenue for December 2026", "2026-12"),
    ("Forecast revenue for January 2027", "2027-01"),
    ("Forecast revenue for February 2027", "2027-02"),
    ("What will revenue be in October 2026?", "2026-10"),
    ("Predict revenue for November 2026", "2026-11"),
])
def test_the_named_month_is_resolved_before_anything_else(question, period):
    assert fc.parse_target_month(question) == period


@pytest.mark.parametrize("period,expected", list(zip(SUPPORTED, range(1, fc.MAX_HORIZON + 1))))
def test_the_horizon_is_counted_from_the_last_complete_operating_month(period, expected):
    assert fc.horizon_for_period(period) == expected


def test_a_recorded_month_is_not_in_the_future():
    recorded = fc.monthly_revenue_series()[-1][0]
    assert fc.horizon_for_period(recorded) == 0
    assert fc.horizon_for_period("2026-06") < 0


def test_a_relative_question_names_no_month():
    for question in ("next month revenue", "Forecast revenue for the next 3 months",
                     "What will revenue be next month?"):
        assert fc.parse_target_month(question) == "", question


# --- 2. every supported month is forecast as itself ------------------------------------------------

@pytest.mark.parametrize("period", SUPPORTED[1:])   # 2026-09 .. 2027-01
def test_each_supported_month_returns_its_own_projection(analyst, period):
    """September through January, not just October. Each must answer for the month asked."""
    label = MONTH_NAMES[period]
    a = answer(analyst, f"Forecast revenue for {label}")
    assert a.trust_level == "SAFE", f"{label}: {a.trust_level}"
    assert f"Projected revenue for {label}" in a.text, a.text[:160]


@pytest.mark.parametrize("period", SUPPORTED[1:])
def test_no_other_month_is_substituted(analyst, period):
    """The failure mode was August's figure under every other month's question."""
    label = MONTH_NAMES[period]
    a = answer(analyst, f"Forecast revenue for {label}")
    others = {name for key, name in MONTH_NAMES.items() if key != period}
    for other in others:
        assert other not in a.text, f"{label} was answered with {other}"


@pytest.mark.parametrize("period", SUPPORTED[1:])
def test_the_figure_is_the_engine_s_own_for_that_horizon(analyst, period):
    """Not merely a different month label on the same number: the value must be the one the
    deterministic model produces at that horizon."""
    horizon = fc.horizon_for_period(period)
    expected = next(p for p in fc.forecast_revenue(horizon).points if p.period == period)
    text = answer(analyst, f"Forecast revenue for {MONTH_NAMES[period]}").text
    assert f"{expected.value:,.2f}" in text, f"{period}: {expected.value} missing"


def test_the_single_month_answer_keeps_its_interval_and_tested_error(analyst):
    a = answer(analyst, "Forecast revenue for October 2026")
    assert "usually" in a.text and "between" in a.text, "the prediction interval was dropped"
    assert "%" in a.text, "the backtested error was dropped"


def test_forecast_month_narrows_without_recomputing():
    """The point returned is the one `forecast_revenue` produced at that horizon, with the
    interval belonging to that horizon rather than to a shorter one."""
    full = fc.forecast_revenue(3)
    single = fc.forecast_month("2026-10")
    assert single.available and len(single.points) == 1
    assert single.points[0] == full.points[2]
    assert single.horizon == 3


# --- 3. beyond the supported horizon ------------------------------------------------------------------

@pytest.mark.parametrize("question", [
    "Forecast revenue for February 2027",
    "Forecast revenue for March 2027",
    "Forecast revenue for June 2027",
    "What will revenue be in December 2027?",
])
def test_a_month_beyond_six_gets_the_existing_honest_limitation(analyst, question):
    a = answer(analyst, question)
    assert a.trust_level == "NOT_DETERMINABLE", f"{question}: {a.trust_level}"
    assert f"{fc.MAX_HORIZON} months" in a.text
    assert "Projected revenue for" not in a.text, "a refused horizon still produced a figure"
    assert "August 2026" not in a.text, "the first forecast month was substituted"


# --- 4. what must not change --------------------------------------------------------------------------

@pytest.mark.parametrize("question", [
    "next month revenue",
    "What will revenue be next month?",
    "Forecast next month revenue",
])
def test_relative_periods_keep_their_existing_semantics(analyst, question):
    a = answer(analyst, question)
    assert a.trust_level == "SAFE"
    assert "Projected revenue for August 2026" in a.text, question


def test_a_multi_month_request_still_lists_every_month(analyst):
    a = answer(analyst, "Forecast revenue for the next 3 months")
    assert a.trust_level == "SAFE"
    for label in ("August 2026", "September 2026", "October 2026"):
        assert label in a.text


@pytest.mark.parametrize("question,label", [
    ("What was revenue in June 2026?", "June 2026"),
    ("Forecast revenue for June 2026", "June 2026"),
])
def test_a_recorded_month_stays_a_historical_question(analyst, question, label):
    """A month the records cover is answered from the records, whatever verb asked for it.
    Projecting it would replace a fact with an estimate."""
    a = answer(analyst, question)
    assert a.trust_level == "SAFE", f"{question}: {a.trust_level}"
    assert "Projected" not in a.text, f"{question} was answered with a projection"
    assert "3,300,730" in a.text


def test_a_future_month_asked_in_the_past_tense_is_not_a_forecast(analyst):
    """"What was revenue in October 2026?" asks what the records hold. They hold nothing for
    October, and that is a coverage answer, not a projection."""
    a = answer(analyst, "What was revenue in October 2026?")
    assert "Projected revenue" not in a.text


def test_unsupported_forecasts_keep_their_capability_gap(analyst):
    for question in ("Forecast occupancy next month", "Forecast expenses next month"):
        a = answer(analyst, question)
        assert "isn't currently available" in a.text, question


def test_the_algorithm_and_its_limits_are_untouched():
    assert (fc.ALPHA, fc.BETA, fc.PHI) == (0.9, 0.4, 0.9)
    assert fc.MAX_HORIZON == 6
    assert fc.MIN_TRAIN_MONTHS == 18 and fc.MIN_OBSERVATIONS == 24
    assert fc.forecast_revenue(1).points[0] == fc.forecast_revenue(1).points[0]


# --- 5. the owner's "Why are you saying this?" -----------------------------------------------------------

def _why(question):
    import os

    os.environ["AI_ANALYTICS_AUTH_DISABLE"] = "true"
    os.environ.pop("AI_ANALYTICS_ENV", None)
    from fastapi.testclient import TestClient
    from api.service import AnalyticsService, create_app

    global _CLIENT
    try:
        client = _CLIENT
    except NameError:
        client = _CLIENT = TestClient(create_app(AnalyticsService()))
    body = client.post("/api/ask", json={"question": question}).json()
    return body.get("owner_explanation") or {}


@pytest.mark.parametrize("question", [
    "Forecast revenue for October 2026",
    "Forecast revenue for the next 3 months",
    "Forecast revenue for February 2027",
    "Forecast occupancy next month",
    "What if occupancy were 80%?",
])
def test_the_owner_explanation_is_never_blank(question):
    """An unsupported forecast is nothing BUT a reason, and its panel came back empty."""
    why = _why(question)
    assert why.get("paragraphs"), f"{question}: blank owner explanation"
    assert why.get("heading")


def test_a_projection_is_explained_as_a_projection():
    """"Taken from your own business records" is false of a month that has not happened."""
    why = _why("Forecast revenue for October 2026")
    text = " ".join(why["paragraphs"]).lower()
    assert "projection for october 2026" in text
    assert "not a recorded figure" in text
    assert "taken from your own business records" not in text
    assert "off by about" in text, "the tested error is not stated"


def test_the_refused_horizon_explains_the_limit():
    why = _why("Forecast revenue for February 2027")
    text = " ".join(why["paragraphs"])
    assert f"{fc.MAX_HORIZON} months" in text
    assert NOT_DETERMINABLE_TEXT in text or "can't" in why["heading"].lower()


@pytest.mark.parametrize("question", [
    "Forecast revenue for October 2026",
    "Forecast revenue for February 2027",
    "Forecast occupancy next month",
])
def test_the_explanation_carries_no_internal_identifier(question):
    text = " ".join(_why(question).get("paragraphs") or [])
    for pattern in (r"\bM\.[A-Z]{2,12}\.\d{3}", r"\bv_[a-z0-9_]+\b",
                    r"\b[\w.-]+\.(?:py|csv|md|json)\b", r"\bhorizon=\d", r"\bmape\b"):
        assert not re.search(pattern, text, re.I), f"{question}: {pattern} leaked"


# --- 6. a future month is a forecast target, never a coverage gap -------------------------------------
#
# The UAT defect. "November revenue" carries no verb, so the future-tense requirement did not
# fire and the question fell through to the historical path, which answered "that period isn't
# fully covered by the exported data". True, useless, and the wrong kind of reason: no amount of
# coverage will ever produce a November figure, because the export stops before it. A named month
# the records cannot reach is a forecast target unless the question is explicitly in the past
# tense.

COVERAGE_SENTENCE = "isn't fully covered by the exported data"

BARE_FUTURE_MONTHS = (
    ("September 2026 revenue", "September 2026"),
    ("October 2026 revenue", "October 2026"),
    ("November revenue", "November 2026"),
    ("November revenue expected", "November 2026"),
    ("December 2026 revenue", "December 2026"),
    ("January 2027 revenue", "January 2027"),
    ("what is November revenue", "November 2026"),
    ("how much revenue in November 2026", "November 2026"),
    ("revenue for November", "November 2026"),
)


@pytest.mark.parametrize("question,label", BARE_FUTURE_MONTHS)
def test_a_future_month_is_forecast_even_without_forecast_wording(analyst, question, label):
    a = answer(analyst, question)
    assert COVERAGE_SENTENCE not in a.text, (
        f"{question!r} was refused for historical coverage, not answered as a forecast")
    assert a.trust_level == "SAFE", f"{question}: {a.trust_level}"
    assert f"Projected revenue for {label}" in a.text, a.text[:160]


@pytest.mark.parametrize("question", [
    "February 2027 revenue",
    "February 2027 revenue expected",
    "June 2027 revenue",
])
def test_a_month_past_the_horizon_is_refused_by_the_method_not_by_coverage(analyst, question):
    a = answer(analyst, question)
    assert COVERAGE_SENTENCE not in a.text, (
        f"{question!r} blamed historical coverage for a forecast limit")
    assert a.trust_level == "NOT_DETERMINABLE"
    assert f"{fc.MAX_HORIZON} months" in a.text
    assert "Projected revenue for" not in a.text
    for label in MONTH_NAMES.values():
        assert label not in a.text, f"{question}: {label} was substituted"


def test_the_semantic_order_is_month_then_horizon_then_limit():
    """Resolve the month, count the horizon, then check it against the supported range. The
    coverage of the historical export never enters the decision."""
    for question, period in (("November revenue", "2026-11"),
                             ("February 2027 revenue", "2027-02")):
        resolved = fc.parse_target_month(question)
        assert resolved == period
        horizon = fc.horizon_for_period(resolved)
        assert horizon > 0
        assert (horizon <= fc.MAX_HORIZON) == (period in SUPPORTED)


@pytest.mark.parametrize("question", [
    "June 2026 revenue",
    "What was revenue in June 2026?",
])
def test_a_recorded_month_is_still_answered_from_the_records(analyst, question):
    a = answer(analyst, question)
    assert a.trust_level == "SAFE"
    assert "Projected" not in a.text
    assert "3,300,730" in a.text


def test_the_past_tense_still_asks_what_the_records_hold(analyst):
    """"What WAS revenue in October 2026?" asks for a fact. The records hold none, and saying so
    is the honest answer -- a projection would replace the question with a different one."""
    a = answer(analyst, "What was revenue in October 2026?")
    assert "Projected revenue" not in a.text


@pytest.mark.parametrize("question", ["next month revenue", "What will revenue be next month?"])
def test_relative_periods_are_unaffected(analyst, question):
    a = answer(analyst, question)
    assert a.trust_level == "SAFE"
    assert "Projected revenue for August 2026" in a.text


# --- 7. the refusal explains the method's limit, in owner language -----------------------------------

def test_the_refused_forecast_explanation_names_the_method_not_the_records():
    why = _why("February 2027 revenue expected")
    paragraphs = why.get("paragraphs") or []
    assert paragraphs, "blank owner explanation on a refused forecast"
    text = " ".join(paragraphs)
    assert "limit of the forecasting method, not of your records" in text
    assert f"{fc.MAX_HORIZON} months ahead" in text
    assert COVERAGE_SENTENCE not in text


@pytest.mark.parametrize("question", [
    "November revenue expected",
    "February 2027 revenue expected",
    "February 2027 revenue",
    "Forecast occupancy next month",
    "Forecast expenses next month",
    "What if occupancy were 80%?",
])
def test_every_forecast_answer_carries_a_non_empty_explanation(question):
    why = _why(question)
    assert why.get("heading"), f"{question}: no heading"
    assert why.get("paragraphs"), f"{question}: blank owner explanation"


@pytest.mark.parametrize("question", [
    "February 2027 revenue expected", "Forecast occupancy next month",
    "What if occupancy were 80%?", "November revenue expected",
])
def test_the_explanation_exposes_nothing_internal(question):
    text = " ".join(_why(question).get("paragraphs") or [])
    for pattern in (r"\bM\.[A-Z]{2,12}\.\d{3}", r"\bDQ\.\d{3}\b", r"\bC\.\d{3}\b",
                    r"\bv_[a-z0-9_]+\b", r"\b[\w.-]+\.(?:py|csv|md|json)\b",
                    r"\b(?:SELECT|FROM|GROUP BY|JOIN)\b", r"####",
                    r"\bMAX_HORIZON\b", r"\bmape\b", r"\bhorizon=\d"):
        assert not re.search(pattern, text), f"{question}: {pattern} leaked"


def test_the_successful_forecast_explanation_is_unchanged():
    """The refusal paragraph must not attach itself to an answer that produced a figure."""
    why = _why("November revenue expected")
    text = " ".join(why["paragraphs"])
    assert why["heading"] == "Why this projection is offered"
    assert "projection for November 2026" in text
    assert "limit of the forecasting method" not in text
