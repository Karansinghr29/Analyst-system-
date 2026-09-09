"""
test_descriptive.py -- deterministic descriptive analysis.

The tests that matter are the ones about restraint. Descriptive statistics are easy to compute
and easy to mislead with: a mean deposit of Rs.5,518 where three-quarters of allotments recorded
nothing, a correlation of 0.98 that only records that two measures both grew, a "top apartment"
built from a single allotment. Each of those is pinned here.
"""
import pytest

from engine import descriptive as d
from engine.result import NOT_DETERMINABLE_TEXT


# --- 1. cross-sectional summaries -----------------------------------------------------------------

def test_rent_summary_reports_the_full_descriptive_block():
    summary = d.cross_section("monthly_rent")
    assert summary.available is True
    stats = summary.stats
    for field in ("count", "mean", "median", "min", "max", "std_dev", "p25", "p75",
                  "coefficient_of_variation", "missing_count", "missing_pct",
                  "zero_count", "zero_pct", "skewness"):
        assert field in stats, f"{field} missing from the summary"
    assert stats["count"] > 1000
    assert stats["min"] <= stats["median"] <= stats["max"]
    assert stats["p25"] <= stats["median"] <= stats["p75"]
    assert stats["missing_pct"] < 5


def test_a_zero_inflated_column_says_so_rather_than_leading_with_the_mean():
    """Three-quarters of deposits are zero. A bare average would misdescribe the column."""
    summary = d.cross_section("deposit_paid")
    assert summary.available is True
    assert summary.stats["zero_pct"] > 50
    assert summary.stats["median"] == 0
    joined = " ".join(summary.notes).lower()
    assert "zero" in joined and "average does not" in joined


def test_relative_spread_is_withheld_where_it_would_not_mean_anything():
    """CV divides spread by level; on a mostly-zero column that is arithmetic, not information."""
    balance = d.cross_section("balance_due")
    assert balance.stats["zero_pct"] > 80
    # It is still computed where the column is well-behaved.
    assert d.cross_section("monthly_rent").stats["coefficient_of_variation"] is not None


def test_an_almost_entirely_missing_field_is_refused_not_summarised():
    summary = d.cross_section("expected_stay_days")
    assert summary.available is False
    assert not summary.stats
    assert "15 of 1,213" in summary.not_determinable_reason
    assert NOT_DETERMINABLE_TEXT in summary.not_determinable_reason


# --- 2. time-series summaries ------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["revenue", "collections", "expenses"])
def test_series_statistics_are_computed_on_changes_not_levels(name):
    """A spread computed on levels would measure growth. These series grew."""
    summary = d.series_summary(name)
    assert summary.available is True
    stats = summary.stats
    assert stats["observations"] >= d.MIN_SERIES_OBSERVATIONS
    assert "median" in stats and "std_dev" in stats

    # The dispersion belongs to the CHANGES: it must be far smaller than the level range.
    assert stats["std_dev"] < abs(stats["latest_level"]), (
        "the dispersion looks like a level statistic, not a change statistic")
    joined = " ".join(summary.notes).lower()
    assert "month-to-month" in joined
    assert "growth rather than variability" in joined


def test_the_pre_trading_period_is_excluded_and_the_exclusion_is_stated():
    """Before trading began the ledger holds corrections and negative months; describing those
    as monthly variation would report bookkeeping as business behaviour."""
    summary = d.series_summary("revenue")
    assert summary.stats["period_start"] >= d.OPERATING_START
    assert any("trading had begun" in note for note in summary.notes)


def test_growth_and_volatility_are_reported_as_separate_figures():
    stats = d.series_summary("revenue").stats
    assert stats["median_pct_change"] is not None      # growth
    assert stats["std_dev"] is not None                 # volatility
    assert stats["median_pct_change"] != stats["std_dev"]


# --- 3. relationships ----------------------------------------------------------------------------------

@pytest.mark.parametrize("pair", [("revenue", "collections"), ("revenue", "expenses"),
                                  ("collections", "expenses")])
def test_both_correlations_are_always_returned_together(pair):
    summary = d.relationship(*pair)
    assert summary.available is True
    assert summary.stats["correlation_levels"] is not None
    assert summary.stats["correlation_changes"] is not None, (
        "the level correlation was returned without the change correlation")
    assert summary.stats["paired_months"] >= d.MIN_PAIRED_OBSERVATIONS


def test_the_misleading_level_correlation_carries_its_warning():
    """Revenue against collections reads 0.98 on levels and 0.24 on changes. Shown alone the
    level figure would be the most misleading number this system could produce."""
    summary = d.relationship("revenue", "collections")
    levels = summary.stats["correlation_levels"]
    changes = summary.stats["correlation_changes"]
    assert levels > 0.9 and changes < 0.5, "the fixture relationship has changed"
    joined = " ".join(summary.notes).lower()
    assert "correlation is not causation" in joined
    assert "level figure mostly records that shared rise" in joined


def test_no_causal_language_appears_in_a_relationship_result():
    for pair in (("revenue", "collections"), ("revenue", "expenses")):
        text = " ".join(d.relationship(*pair).notes).lower()
        for phrase in ("causes", "caused by", "drives", "leads to", "because of"):
            assert phrase not in text, f"causal claim in a correlation result: {phrase!r}"


def test_an_unpaired_relationship_is_refused():
    summary = d.relationship("revenue", "occupancy")
    assert summary.available is False
    assert NOT_DETERMINABLE_TEXT in summary.not_determinable_reason


# --- 4. apartment comparison -------------------------------------------------------------------------------

def test_apartments_below_the_minimum_are_shown_but_never_ranked():
    """Three apartments hold a single allotment each, and two of them carry the highest rent in
    the estate. Ranking them would present one observation as a finding; dropping them would
    make the comparison look complete."""
    summary = d.apartment_comparison()
    assert summary.available is True
    stats = summary.stats

    assert stats["apartments_total"] == (stats["apartments_compared"]
                                         + stats["apartments_insufficient"]), (
        "apartments went missing between the two lists")
    assert stats["apartments_insufficient"] > 0, "the fixture has no thin groups left to check"

    for row in stats["insufficient"]:
        assert row["count"] < d.MIN_GROUP_SIZE
    for row in stats["comparable"]:
        assert row["count"] >= d.MIN_GROUP_SIZE
        assert row["p25"] is not None and row["p75"] is not None

    ranked = [r["apartment"] for r in stats["comparable"]]
    thin = {r["apartment"] for r in stats["insufficient"]}
    assert not (set(ranked) & thin), "a thin group appears in the ranking"


def test_the_ranking_is_ordered_and_states_its_own_rule():
    summary = d.apartment_comparison()
    medians = [r["median"] for r in summary.stats["comparable"]]
    assert medians == sorted(medians, reverse=True)
    assert summary.stats["minimum_group_size"] == d.MIN_GROUP_SIZE
    joined = " ".join(summary.notes).lower()
    assert "fewer than 4" in joined and "not ranked" in joined
    assert "does not explain why" in joined, "the comparison implies an explanation it cannot give"


# --- 5. what is deliberately not offered ---------------------------------------------------------------------

@pytest.mark.parametrize("name", ["significance_testing", "confidence_intervals",
                                  "causal_analysis", "occupancy_rate_history",
                                  "property_comparison", "expected_stay_days",
                                  "anomaly_verdict"])
def test_each_excluded_analysis_states_why(name):
    reason = d.unsupported(name)
    assert reason, f"{name} is excluded but gives no reason"
    assert NOT_DETERMINABLE_TEXT in reason


def test_the_module_offers_no_inferential_surface():
    """No p-value, no test statistic, no confidence interval anywhere in the public surface."""
    public = [n for n in dir(d) if not n.startswith("_")]
    for banned in ("p_value", "pvalue", "ttest", "t_test", "chi2", "confidence_interval",
                   "hypothesis", "significance"):
        assert not any(banned in n.lower() for n in public), (
            f"an inferential entry point exists: {banned}")


def test_the_capability_statement_is_honest_about_what_this_is():
    statement = d.CAPABILITY_STATEMENT.lower()
    assert "descriptive" in statement
    assert "not significance testing" in statement
    assert "not causal" in statement or "not causal analysis" in statement


# --- 6. determinism and registry ---------------------------------------------------------------------------------

def test_results_are_deterministic():
    first = d.cross_section("monthly_rent").stats
    second = d.cross_section("monthly_rent").stats
    assert first == second


def test_the_registry_records_descriptive_analysis_and_explains_statistical_summary():
    import csv

    with open("analysis_capability_registry.csv", encoding="utf-8-sig", newline="") as fh:
        rows = {r["capability_id"]: r for r in csv.DictReader(fh)}

    assert rows["descriptive_analysis"]["status"] == "IMPLEMENTED"
    assert rows["descriptive_analysis"]["implemented_in"] == "engine/descriptive.py"
    note = rows["descriptive_analysis"]["limitation"].lower()
    assert "does not test significance" in note and "no causal claim" in note

    # statistical_summary stays NOT_IMPLEMENTED, but is no longer silent about it.
    summary_row = rows["statistical_summary"]
    assert summary_row["status"] == "NOT_IMPLEMENTED"
    assert "descriptive_analysis" in summary_row["limitation"]
    assert "inference" in summary_row["limitation"].lower()
