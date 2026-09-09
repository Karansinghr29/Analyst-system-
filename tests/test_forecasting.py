"""
test_forecasting.py -- deterministic revenue forecasting.

The tests that matter here are the refusals. A forecasting module is easy to make produce a
number for any question; what makes this one honest is that it declines three specific things
the evidence does not support -- a horizon beyond its measured accuracy, an occupancy scenario,
and any use of occupancy as a predictor -- and says why each time.
"""
import pytest

from engine import forecasting as fc
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture(scope="module")
def series():
    return fc.monthly_revenue_series()


# --- the training data ------------------------------------------------------------------------

def test_the_series_is_complete_months_of_the_operating_era_only(series):
    """A part-month would read as a collapse in trading; the pre-trading ledger is corrections."""
    assert len(series) >= fc.MIN_OBSERVATIONS
    periods = [p for p, _ in series]
    assert periods == sorted(periods), "the series is not chronological"
    assert periods[0] >= fc.OPERATING_START
    # 2026-08 ends after the snapshot, so it must not be trained on.
    assert "2026-08" not in periods
    assert "2026-09" not in periods
    # Contiguous: a gap would silently distort the trend.
    for earlier, later in zip(periods, periods[1:]):
        assert fc._next_month(earlier) == later, f"gap between {earlier} and {later}"


# --- the forecast -------------------------------------------------------------------------------

def test_a_one_month_forecast_is_produced_with_an_interval_and_a_backtest():
    forecast = fc.forecast_revenue(1)
    assert forecast.available is True
    assert len(forecast.points) == 1

    point = forecast.points[0]
    assert point.period == "2026-08", "the forecast does not start after the last actual month"
    assert point.value > 0
    assert point.lower < point.value < point.upper, "the interval does not bracket the estimate"

    assert forecast.backtest["mape_pct"] is not None
    assert forecast.backtest["folds"] >= 5
    assert forecast.direction in ("increase", "decrease", "flat")


def test_the_chosen_method_beats_the_naive_benchmark_it_reports():
    """The module publishes the benchmark it had to beat, so the claim stays checkable."""
    for horizon in (1, 3):
        forecast = fc.forecast_revenue(horizon)
        chosen = forecast.backtest["mape_pct"]
        naive = forecast.backtest["compared_against"]["naive_last_value_mape_pct"]
        assert chosen < naive, (
            f"h={horizon}: chosen method ({chosen}%) is no better than naive ({naive}%); "
            f"the simpler method should then be used")


def test_intervals_widen_with_the_horizon():
    """Uncertainty grows with distance. An interval that did not would be decorative."""
    near = fc.forecast_revenue(1).points[-1]
    far = fc.forecast_revenue(6).points[-1]
    assert (far.upper - far.lower) > (near.upper - near.lower)


def test_forecast_values_are_deterministic():
    """Same evidence, same answer. A forecast that moved between calls could not be audited."""
    first = fc.forecast_revenue(3)
    second = fc.forecast_revenue(3)
    assert [p.value for p in first.points] == [p.value for p in second.points]


# --- the refusals -------------------------------------------------------------------------------

@pytest.mark.parametrize("horizon", [7, 12, 24])
def test_a_horizon_beyond_the_measured_accuracy_is_refused(horizon):
    forecast = fc.forecast_revenue(horizon)
    assert forecast.available is False
    assert not forecast.points, "a refused horizon still produced figures"
    assert str(fc.MAX_HORIZON) in forecast.not_determinable_reason
    assert NOT_DETERMINABLE_TEXT in forecast.not_determinable_reason


def test_an_occupancy_scenario_is_refused_with_its_reason():
    """"What if occupancy hits 80%?" needs a validated occupancy-to-revenue relationship. The
    relationship was tested and failed, so no figure may be produced."""
    scenario = fc.scenario_forecast(occupancy_rate=0.80)
    assert scenario.available is False
    assert not scenario.points
    reason = scenario.not_determinable_reason.lower()
    assert "occupancy" in reason
    assert "predict" in reason or "accurate" in reason
    assert NOT_DETERMINABLE_TEXT in scenario.not_determinable_reason


def test_occupancy_is_reported_as_evaluated_and_rejected():
    """A driver that was tested and rejected is a finding the owner is entitled to, not an
    absence to stay quiet about."""
    drivers = {d["driver"]: d for d in fc.evaluate_drivers()}
    assert "occupied beds" in drivers
    assert drivers["occupied beds"]["verdict"] == "REJECTED"
    assert "0.80" in drivers["occupied beds"]["evidence"], "the correlation is not disclosed"
    assert "0.44" in drivers["occupied beds"]["evidence"], "the change correlation is not shown"

    assert drivers["occupancy rate"]["verdict"] == "NOT_DERIVABLE"
    assert NOT_DETERMINABLE_TEXT in drivers["occupancy rate"]["evidence"]

    for record in fc.evaluate_drivers():
        assert record["verdict"] != "USED", (
            "a driver is in use; the backtest showed none improved on the univariate model")


def test_no_causal_claim_is_made_anywhere():
    """Occupancy is at most an association here. Nothing may call it a cause."""
    text = " ".join(d["evidence"] for d in fc.evaluate_drivers()).lower()
    text += " " + fc.scenario_forecast().not_determinable_reason.lower()
    for phrase in ("causes", "caused by", "because occupancy", "drives revenue",
                   "leads to higher revenue"):
        assert phrase not in text, f"a causal claim was made: {phrase!r}"


# --- the natural-language surface ----------------------------------------------------------------

@pytest.mark.parametrize("question,months", [
    ("What will revenue be next month?", 1),
    ("Forecast revenue for the next 3 months.", 3),
    ("What is the expected revenue next quarter?", 3),
    ("forecast revenue next 6 months", 6),
])
def test_horizons_are_parsed_deterministically(question, months):
    """The model never chooses the horizon: a misread horizon changes the answer silently."""
    assert fc.parse_horizon(question)[0] == months


@pytest.mark.parametrize("question", [
    "What will revenue look like if occupancy reaches 90%?",
    "How much revenue can we expect at 75% occupancy?",
])
def test_scenario_questions_are_recognised_and_refused(question):
    assert fc.asks_scenario(question) is True
    assert fc.scenario_forecast().available is False


def test_the_owner_answer_carries_no_internal_identifiers():
    """A forecast is still an owner answer and obeys the same presentation rules."""
    import re
    from engine import owner_presentation as op
    text = op.present_forecast(fc.forecast_revenue(3))
    for pattern in (r"\bM\.[A-Z]+\.\d{3}", r"\b[\w-]+\.(?:md|csv|py)\b",
                    r"\b(?:engine|api)/", r"\bHolt\b"):
        assert not re.search(pattern, text), f"{pattern} leaked into the owner answer:\n{text}"
    assert "%" in text, "the tested error is not disclosed to the owner"
