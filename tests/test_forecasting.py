"""
test_forecasting.py -- deterministic revenue forecasting.

The tests that matter here are the refusals and the disclosures. A forecasting module is easy to
make produce a number for any question; what makes this one honest is that it declines what the
evidence does not support -- a horizon beyond its measured accuracy and an occupancy scenario --
says why each time, and reports its benchmark comparison even where a simpler method wins.
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


def test_ridge_is_production_and_its_benchmarks_are_reported_honestly():
    """Multivariate Ridge -- StandardScaler -> Ridge(alpha=5.0) -- is the mandated production model,
    with a fixed penalty and no selection by horizon. It is not required to beat every benchmark
    at every horizon; it is required to publish the comparison truthfully, so the measured result
    -- naive last value more accurate at one, three and six months -- stays visible and
    checkable."""
    assert fc.RIDGE_ALPHA == 5.0
    table = fc.build_feature_table()
    months = fc.validation_months(table)
    assert len(months) == 12 and months == table.rows[-12:], "test period is not the last 12 months"
    assert fc.MIN_TRAIN_ROWS == 6
    assert table.rows.index(months[0]) >= fc.MIN_TRAIN_ROWS
    measured = {}
    for horizon in (1, 3, 6):
        forecast = fc.forecast_revenue(horizon)
        assert forecast.available is True
        assert forecast.method == fc.METHOD_NAME
        assert forecast.features == fc.RIDGE_FEATURES
        assert forecast.model_comparison["production_model"] == "multivariate_ridge"
        assert forecast.backtest["ridge_alpha"] == 5.0, f"h={horizon}: penalty is not fixed at 5.0"
        assert forecast.model_comparison["ridge_alpha"] == 5.0

        chosen = forecast.backtest["mape_pct"]
        naive = forecast.backtest["compared_against"]["naive_last_value_mape_pct"]
        assert chosen is not None and naive is not None, f"h={horizon}: a benchmark is missing"
        # The published figures are the walk-forward figures, not a rounded-in-our-favour copy.
        mape, _residuals, folds, naive_mape = fc._ridge_backtest(table, horizon)
        assert (chosen, naive, forecast.backtest["folds"]) == (mape, naive_mape, folds)
        measured[horizon] = (chosen, naive)

    for horizon in (1, 3, 6):
        assert measured[horizon][0] > measured[horizon][1], (
            f"h={horizon}: Ridge vs naive changed {measured[horizon]}")
    # The one-month backtest is the walk-forward comparison's own figure on the same 12 months.
    one_month = fc.forecast_revenue(1)
    assert one_month.backtest["folds"] == 12
    assert one_month.backtest["mape_pct"] == one_month.model_comparison["models"]["multivariate_ridge"]["MAPE_pct"]

    # Every model in the one-month comparison carries all four metrics, and any model that beat
    # Ridge is named to the owner rather than hidden.
    comparison = fc.forecast_revenue(1).model_comparison
    models = comparison["models"]
    for name, metrics in models.items():
        for key in ("MAE", "RMSE", "MAPE_pct", "R2"):
            assert metrics[key] is not None, f"{name} is missing {key}"
    ridge = models["multivariate_ridge"]["MAPE_pct"]
    beaten_by = [n for n, m in models.items() if n != "multivariate_ridge" and m["MAPE_pct"] < ridge]
    limitations = " ".join(fc.forecast_revenue(1).limitations)
    if beaten_by:
        assert comparison["most_accurate_by_mape"] != "multivariate_ridge"
        assert "simpler methods were more accurate" in limitations
        for name in beaten_by:
            assert fc.OWNER_MODEL_NAMES[name] in limitations, f"{name} beat Ridge but is not named"


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


def test_occupancy_is_a_used_driver_with_the_production_contract_definition():
    """occupancy_pct_lag1 is a production predictor: last month's bed occupancy, occupied physical
    beds over 192 beds before 2026-08 and 203 from it, with its checks disclosed to the owner."""
    assert "occupancy_pct_lag1" in fc.DRIVER_FEATURES
    assert "occupancy_pct_lag1" in fc.RIDGE_FEATURES
    assert fc.RIDGE_FEATURES.index("occupancy_pct_lag1") == fc.RIDGE_FEATURES.index("tenants_lag1") + 1
    assert "occupancy_pct_lag1" not in fc.NOT_DETERMINABLE_FEATURES
    assert fc.forecast_revenue(1).features == fc.RIDGE_FEATURES

    assert (fc.OCCUPANCY_BEDS_BEFORE, fc.OCCUPANCY_BEDS_FROM, fc.OCCUPANCY_CAPACITY_CHANGE) == (
        192, 203, "2026-08")
    source, columns, aggregation, lag = fc.FEATURE_SOURCES["occupancy_pct_lag1"]
    for table in ("tenant_allotments", "beds", "apartments"):
        assert table in source
    for column in ("onboarding_date", "actual_exit_date", "bed_code", "apartment_code"):
        assert column in columns
    assert "apartment_code|bed_code" in aggregation
    assert "192" in aggregation and "203" in aggregation
    assert lag == "T-1"

    drivers = {d["driver"]: d for d in fc.evaluate_drivers()}
    occupancy = drivers["occupancy rate"]
    assert occupancy["verdict"] == "USED"
    check = fc.occupancy_validation()
    assert check["months"] == len(fc.monthly_revenue_series())
    assert check["above_100"] == 0
    # Both contract denominators reconcile with the physical beds in the bed records.
    assert check["physical_beds"] == fc.OCCUPANCY_BEDS_FROM
    assert check["physical_beds_before_added"] == fc.OCCUPANCY_BEDS_BEFORE
    assert "192 beds" in occupancy["evidence"] and "203 beds" in occupancy["evidence"]
    assert f"{check['above_100']} are above 100%" in occupancy["evidence"]
    assert drivers["payments, electricity and expenses"]["verdict"] == "EXCLUDED"

    # The feature for month T is the occupancy of month T-1, never T itself.
    table = fc.build_feature_table()
    pct, _detail = fc.monthly_occupancy(table.periods)
    for target in table.rows:
        previous = fc._add_months(target, -1)
        assert table.features[target]["occupancy_pct_lag1"] == pytest.approx(pct[previous])
        assert table.drivers[previous]["occupancy_pct"] == pytest.approx(pct[previous])


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
