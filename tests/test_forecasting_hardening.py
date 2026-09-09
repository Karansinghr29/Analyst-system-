"""
test_forecasting_hardening.py -- production-hardening checks for the forecasting module.

These are the properties that make the forecast safe to put in front of an owner, as opposed to
merely producing a number: no future data reaches the fit, the training window cannot absorb a
part-month, the interval is labelled for what it actually is, and the capability registry tells
the truth about what was implemented and what was refused.
"""
import inspect
import re

import pytest

from engine import forecasting as fc
from engine import owner_presentation as op
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture(scope="module")
def series():
    return fc.monthly_revenue_series()


# --- leakage ------------------------------------------------------------------------------------

def test_the_fit_cannot_see_data_beyond_its_cut(series):
    """Corrupting a future observation must not move a fit that ended before it."""
    values = [v for _, v in series]
    assert len(values) > 32

    before = fc._holt(values[:25], 1)[0]
    tampered = list(values)
    tampered[30] *= 10                      # a future month, far beyond the cut
    after = fc._holt(tampered[:25], 1)[0]
    assert before == after, "a future value influenced the fitted model"


def test_the_backtest_trains_strictly_before_the_period_it_scores():
    source = inspect.getsource(fc._backtest)
    assert "values[:cut]" in source, "training slice is not strictly-before"
    assert "values[cut:cut + horizon]" in source, "the scored window is not strictly-after"


def test_the_tuned_parameters_still_beat_naive_on_an_untuned_tail(series):
    """The parameters were chosen on a sweep over these folds, so the reported error carries
    selection optimism. On a tail held back from that sweep the method must still win -- if it
    only wins where it was tuned, the simpler method should be used instead."""
    values = [v for _, v in series]
    holdout = 8
    train, held = values[:-holdout], values[-holdout:]

    chosen, naive = [], []
    for i, actual in enumerate(held):
        if not actual:
            continue
        history = train + held[:i]
        chosen.append(abs(fc._holt(history, 1)[0] - actual) / abs(actual) * 100)
        naive.append(abs(history[-1] - actual) / abs(actual) * 100)

    assert sum(chosen) / len(chosen) < sum(naive) / len(naive), (
        "the chosen method does not beat naive outside the window it was tuned on")


# --- the training window --------------------------------------------------------------------------

def test_incomplete_and_stub_months_can_never_enter_training(series):
    """2026-08 is a part-month and 2026-09 is a stub. Both must be excluded BY RULE."""
    periods = [p for p, _ in series]
    assert "2026-08" not in periods
    assert "2026-09" not in periods

    source = inspect.getsource(fc.monthly_revenue_series)
    assert "_month_end" in source and "EXPORT_SNAPSHOT_DATE" in source, (
        "exclusion is not derived from the snapshot date; a future export would reintroduce "
        "the part-month")
    # The rule itself, exercised directly.
    assert fc._month_end(2026, 8) > fc.EXPORT_SNAPSHOT_DATE
    assert fc._month_end(2026, 7) <= fc.EXPORT_SNAPSHOT_DATE


def test_direction_is_measured_against_the_last_actual_usable_month(series):
    values = [v for _, v in series]
    forecast = fc.forecast_revenue(1)
    assert forecast.last_actual == values[-1]
    expected = ("increase" if forecast.points[-1].value > values[-1]
                else "decrease" if forecast.points[-1].value < values[-1] else "flat")
    assert forecast.direction == expected


# --- horizons ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("horizon", [1, 2, 3, 4, 5, 6])
def test_supported_horizons_produce_a_forecast(horizon):
    forecast = fc.forecast_revenue(horizon)
    assert forecast.available is True
    assert len(forecast.points) == horizon


@pytest.mark.parametrize("horizon", [7, 12, 24])
def test_horizons_beyond_measured_accuracy_are_refused(horizon):
    forecast = fc.forecast_revenue(horizon)
    assert forecast.available is False
    assert not forecast.points
    assert NOT_DETERMINABLE_TEXT in forecast.not_determinable_reason


# --- interval labelling -------------------------------------------------------------------------------

def test_the_interval_is_labelled_empirical_not_a_confidence_interval():
    forecast = fc.forecast_revenue(3)
    assert forecast.interval_basis, "the interval carries no statement of what it is"
    basis = forecast.interval_basis.lower()
    assert "empirical" in basis and "backtest" in basis
    assert "not a statistical confidence interval" in basis


def test_the_owner_answer_never_calls_it_a_confidence_interval():
    text = op.present_forecast(fc.forecast_revenue(3))
    assert not re.search(r"confidence interval|95%\s*(?:ci|confidence)|p-value|significance level",
                         text, re.I)


# --- occupancy and causal language ------------------------------------------------------------------

def test_occupancy_is_recorded_as_tested_and_rejected():
    drivers = {d["driver"]: d for d in fc.evaluate_drivers()}
    assert drivers["occupied beds"]["verdict"] == "REJECTED"
    assert drivers["occupancy rate"]["verdict"] == "NOT_DERIVABLE"
    assert not any(d["verdict"] == "USED" for d in fc.evaluate_drivers())


def test_no_causal_claim_appears_in_the_module_or_the_owner_answer():
    corpus = inspect.getsource(fc).lower()
    corpus += " ".join(d["evidence"] for d in fc.evaluate_drivers()).lower()
    corpus += fc.scenario_forecast().not_determinable_reason.lower()
    corpus += op.present_forecast(fc.forecast_revenue(1)).lower()
    for phrase in ("occupancy causes", "causes revenue", "caused by occupancy",
                   "drives revenue", "because occupancy", "due to occupancy"):
        assert phrase not in corpus, f"causal claim: {phrase!r}"


def test_the_occupancy_scenario_stays_refused():
    for rate in (0.75, 0.80, 0.90):
        scenario = fc.scenario_forecast(occupancy_rate=rate)
        assert scenario.available is False
        assert not scenario.points
        assert NOT_DETERMINABLE_TEXT in scenario.not_determinable_reason


# --- determinism -----------------------------------------------------------------------------------------

def test_the_module_is_deterministic_and_calls_no_model():
    runs = [[p.value for p in fc.forecast_revenue(3).points] for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]

    source = inspect.getsource(fc)
    # Documentation may DESCRIBE the boundary; no code may cross it.
    code = "\n".join(line for line in source.splitlines()
                     if not line.strip().startswith(("#", '"""', "*")))
    for forbidden in ("self.provider", "provider.complete", "LLMInterface", "build_provider"):
        assert forbidden not in code, f"the forecasting module reaches for the model: {forbidden}"


# --- capability registry -------------------------------------------------------------------------------------

def test_the_registry_records_forecasting_as_implemented():
    """The registry drives the owner-facing "what can this system do" disclosure. Forecasting
    being absent from it made a working capability invisible."""
    import csv

    with open("analysis_capability_registry.csv", encoding="utf-8-sig", newline="") as fh:
        rows = {r["capability_id"]: r for r in csv.DictReader(fh)}

    assert "revenue_forecast" in rows, "forecasting is missing from the capability registry"
    assert rows["revenue_forecast"]["status"] == "IMPLEMENTED"
    assert rows["revenue_forecast"]["implemented_in"] == "engine/forecasting.py"

    assert "forecast_scenario" in rows, "the refused scenario capability is not disclosed"
    assert rows["forecast_scenario"]["status"] == "NOT_IMPLEMENTED"
    assert NOT_DETERMINABLE_TEXT in rows["forecast_scenario"]["limitation"]
    assert "occupancy" in rows["forecast_scenario"]["limitation"].lower()


def test_the_owner_disclosure_surfaces_both_outcomes():
    from engine.capability_disclosure import CapabilityDisclosure

    section = CapabilityDisclosure().for_section("insights")
    supported = {c["capability_id"] for c in section["supported"]}
    unsupported = {c["capability_id"] for c in section["unsupported"]}
    assert "revenue_forecast" in supported
    assert "forecast_scenario" in unsupported
