"""
test_descriptive_nl_routing.py -- do owner questions reach the descriptive engine, and does
everything else keep going where it went before.

Two halves, and the second is the one that matters. Routing a new capability in is easy; the
risk is that its markers -- "average", "compare", "vary", "change" -- are ordinary English that
appears throughout questions this product already answers. So half the tests below assert that
revenue lookups, occupancy, risk scans, period comparisons and forecasting are untouched.
"""
import re

import pytest

from engine import descriptive_routing as droute
from engine import analysis_capability as acap
from engine.analyst_intelligence import AnalystIntelligence
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture(scope="module")
def analyst():
    # Verbalization off: these tests are about routing and the deterministic draft, not wording.
    return AnalystIntelligence(verbalize=False)


def answer(analyst, question):
    analyst.llm.reset()
    return analyst.ask(question)


# --- 1. the questions that must reach the descriptive engine ------------------------------------

@pytest.mark.parametrize("question,kind,target", [
    ("What's typical rent?", "cross_section", "monthly_rent"),
    ("What is the average rent?", "cross_section", "monthly_rent"),
    ("What's the median rent?", "cross_section", "monthly_rent"),
    ("What's the distribution of rent?", "cross_section", "monthly_rent"),
    ("How variable are rents?", "cross_section", "monthly_rent"),
    ("How much do deposits vary?", "cross_section", "deposit_paid"),
    ("How much revenue moves month to month?", "series", "revenue"),
    ("How much does revenue change each month?", "series", "revenue"),
    ("Is revenue steady or volatile?", "series", "revenue"),
    ("How variable is revenue?", "series", "revenue"),
    ("How variable are collections?", "series", "collections"),
    ("Do collections track revenue?", "relationship", "collections"),
    ("Are collections related to revenue?", "relationship", "collections"),
    ("How do apartments compare on rent?", "apartments", "monthly_rent"),
    ("Which apartments have the highest typical rent?", "apartments", "monthly_rent"),
])
def test_the_required_questions_resolve_to_the_right_entry_point(question, kind, target):
    route = droute.classify(question)
    assert route.kind == kind, f"{question!r} routed to {route.kind!r}"
    assert route.target == target


@pytest.mark.parametrize("question", [
    "What's typical rent?", "How much do deposits vary?",
    "How much revenue moves month to month?", "Is revenue steady or volatile?",
    "Do collections track revenue?", "How do apartments compare on rent?",
])
def test_each_reaches_the_owner_as_a_figure_not_a_capability_gap(analyst, question):
    a = answer(analyst, question)
    assert a.trust_level and a.trust_level != "NOT_DETERMINABLE", a.text
    assert "not implemented" not in a.text.lower()
    assert "isn't currently available" not in a.text.lower()
    assert a.text.strip()


def test_paraphrases_route_on_intent_and_concept_rather_than_wording():
    """No canned-question list: unseen phrasings of the same intent land in the same place."""
    for phrasing in ("what does rent usually come to", "give me the usual rental figure",
                     "what is the normal range of rent"):
        assert droute.classify(phrasing).kind == "cross_section"
    for phrasing in ("how much does income fluctuate from month to month",
                     "is turnover volatile"):
        assert droute.classify(phrasing).kind == "series"
    for phrasing in ("do receipts move together with revenue",
                     "what is the relationship between collections and revenue"):
        assert droute.classify(phrasing).kind == "relationship"


# --- 2. content the routing must not lose --------------------------------------------------------

def test_typical_rent_leads_with_the_median_and_the_count(analyst):
    text = answer(analyst, "What's typical rent?").text
    assert "14,500" in text
    assert "1,186" in text


def test_the_deposit_answer_states_the_zero_share(analyst):
    """Three-quarters of deposits are zero. An answer that led with the mean would mislead."""
    text = answer(analyst, "How much do deposits vary?").text.lower()
    assert "75.9% of values are zero" in text
    assert "the average does not" in text


def test_the_relationship_answer_shows_both_correlations_and_the_caveat(analyst):
    """The level figure alone is the most misleading number this system could publish."""
    text = answer(analyst, "Do collections track revenue?").text.lower()
    assert "0.24" in text and "0.98" in text
    assert "correlation is not causation" in text
    for causal in ("causes", "caused by", "drives", "because of"):
        assert causal not in text


def test_revenue_movement_separates_volatility_from_growth(analyst):
    text = answer(analyst, "How much does revenue change each month?").text.lower()
    assert "month-to-month" in text
    assert "growth" in text
    assert "2023-03" in text, "the operating-era exclusion was dropped"


def test_thin_apartments_are_visible_as_insufficient_data_not_ranked(analyst):
    text = answer(analyst, "How do apartments compare on rent?").text
    assert "Insufficient data" in text
    for code in ("A33", "A34", "D15"):
        assert code in text, f"{code} disappeared from the comparison"
    ranked = text.split("Insufficient data")[0]
    for code in ("A33", "A34", "D15"):
        assert code not in ranked, f"{code} was ranked on a single allotment"
    assert "fewer than 4" in text


# --- 3. what must be refused rather than answered narrowly ---------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("Is the revenue increase statistically significant?", "significance"),
    ("Give me a confidence interval for revenue", "confidence interval"),
    ("Does higher occupancy cause higher revenue?", "causal"),
])
def test_inference_questions_are_refused_with_their_own_reason(analyst, question, expected):
    a = answer(analyst, question)
    assert a.trust_level == "NOT_DETERMINABLE"
    assert NOT_DETERMINABLE_TEXT in a.text
    assert expected in a.text.lower()


def test_an_anomaly_verdict_is_never_produced(analyst):
    """No figure gets labelled an anomaly, by either route.

    Asked inside a descriptive question the descriptive refusal answers it. Asked plainly it
    stays with the anomaly path that already handled it, which refuses on its own wording -- the
    routing added here must not take that question over.
    """
    descriptive_shaped = answer(analyst, "Is the variation in revenue anomalous?")
    assert descriptive_shaped.trust_level == "NOT_DETERMINABLE"
    assert NOT_DETERMINABLE_TEXT in descriptive_shaped.text
    assert "threshold" in descriptive_shaped.text.lower()

    plain = answer(analyst, "Is this month's revenue an anomaly?")
    assert plain.trust_level == "NOT_DETERMINABLE"
    assert "threshold" in plain.text.lower()
    assert "cannot mark" in plain.text.lower() or "not substituting" in plain.text.lower(), (
        "the anomaly path stopped refusing and may now be issuing a verdict")


def test_a_requested_period_is_never_answered_with_the_all_time_figure(analyst):
    """The summaries describe the whole window. Narrowing silently would answer a different
    question than the one asked."""
    for question, label in (("What was typical rent in July 2025?", "2025-07"),
                            ("How variable was revenue last month?", "last month")):
        a = answer(analyst, question)
        assert a.trust_level == "NOT_DETERMINABLE", question
        assert label in a.text
        assert "14,500" not in a.text, "the all-time figure was substituted for the period"


def test_the_trust_gate_still_governs_a_described_column(analyst):
    """The outstanding-balance column is a metric with competing definitions, and it is BLOCK.
    A distribution of it is still a statement about that figure, so the block carries over."""
    a = answer(analyst, "How much do balances due vary?")
    assert a.trust_level == "BLOCK"
    assert "competing definitions" in a.text
    # BLOCK means no headline: the descriptive figures must not appear.
    assert "1,213" not in a.text


# --- 4. no regression in what already worked -------------------------------------------------------

@pytest.mark.parametrize("question,forbidden_kind", [
    ("What is our revenue?", None),
    ("What are total expenses?", None),
    ("How much have we collected?", None),
    ("What is current occupancy?", None),
    ("What are my biggest risks?", None),
    ("Did revenue increase this month compared to last month?", None),
    ("Why did revenue drop?", None),
    ("What changed recently?", None),
    ("Forecast revenue for the next 3 months", None),
    ("What will revenue be next month?", None),
    ("What is the average number of tenants?", None),
    ("Compare this month with last month", None),
])
def test_existing_questions_do_not_enter_the_descriptive_router(question, forbidden_kind):
    """A bare lookup, a period comparison, a risk scan and a forecast all carry words the
    descriptive markers use. None of them is a descriptive question."""
    route = droute.classify(question)
    assert route.kind is None, f"{question!r} was hijacked as {route!r}"
    assert not route.refusal, f"{question!r} was refused by the descriptive layer"


@pytest.mark.parametrize("question,expected_trust", [
    ("What is our revenue?", "SAFE"),
    ("What are total expenses?", "SAFE"),
    ("What is current occupancy?", "SHOW_BOTH"),
])
def test_existing_metric_answers_are_unchanged(analyst, question, expected_trust):
    a = answer(analyst, question)
    assert a.trust_level == expected_trust, f"{question}: {a.trust_level}"


def test_a_bare_average_of_a_series_stays_a_lookup():
    """"Average revenue" asks about a level. The series summary describes month-to-month
    movement, which is a different question, so central tendency alone must not pull it in."""
    assert droute.classify("What is the average revenue?").kind is None
    assert droute.classify("What is average monthly revenue?").kind is None


def test_forecasting_still_classifies_as_forecasting():
    """Descriptive routing must not take a forecast question.

    Which forecast capability it lands on is settled elsewhere: a revenue forecast is served by
    `revenue_forecast`, anything else by the generic `forecasting` gap. What matters here is
    that neither becomes descriptive analysis.
    """
    for question in ("Forecast revenue for the next 3 months",
                     "What will revenue be next month?",
                     "Predict revenue",
                     "Forecast occupancy next month"):
        cap = acap.classify_analysis_capability(question)
        assert cap.capability_id in ("forecasting", "revenue_forecast"), (
            f"{question}: {cap.capability_id}")
        assert cap.route != acap.ROUTE_DESCRIPTIVE


def test_the_deterministic_forecast_is_still_produced():
    """Descriptive routing sits after the forecast branch and must not shadow it."""
    from engine.llm_interface import LLMInterface

    llm = LLMInterface(verbalize=False)
    result = llm.ask("Forecast revenue for the next 3 months")
    assert result.forecast is not None and result.forecast.available
    assert result.trust_level == "SAFE"


def test_risk_and_occupancy_routing_is_untouched():
    assert acap.classify_analysis_capability(
        "What are my biggest risks?").route == acap.ROUTE_WHAT_TO_DO
    assert acap.classify_analysis_capability(
        "What is current occupancy?").route == acap.ROUTE_METRIC


# --- 5. owner language ------------------------------------------------------------------------------

_INTERNAL = (
    (r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", "metric id"),
    (r"\bDQ\.\d{3}\b", "data-quality id"),
    (r"\bC\.\d{3}\b", "conflict id"),
    (r"\bF\.\d+\b", "finding id"),
    (r"\bv_[a-z0-9_]+\b", "database view"),
    (r"\b[\w.-]+\.(?:py|csv|md|json)\b", "file name"),
    (r"\b(?:tenant_allotments|monthly_rental|deposit_paid|balance_due|journal_lines)\b",
     "table or column name"),
    (r"\b(?:SELECT|FROM|GROUP BY|JOIN)\b", "SQL"),
    (r"\b(?:cross_section|series_summary|apartment_comparison|descriptive_routing)\b",
     "function or module name"),
)


@pytest.mark.parametrize("question", [
    "What's typical rent?", "How much do deposits vary?",
    "How much revenue moves month to month?", "Do collections track revenue?",
    "How do apartments compare on rent?", "Which apartments have the highest typical rent?",
    "Is the revenue increase statistically significant?",
    "What was typical rent in July 2025?", "How much do balances due vary?",
])
def test_no_internal_identifier_reaches_the_owner(analyst, question):
    text = answer(analyst, question).text
    for pattern, what in _INTERNAL:
        assert not re.search(pattern, text), f"{what} leaked into the answer for {question!r}"


def test_the_answers_read_as_business_english(analyst):
    text = answer(analyst, "What's typical rent?").text
    assert "₹" in text, "money is not rendered as money"
    assert "{" not in text and "}" not in text, "a raw structure was dumped into the answer"
