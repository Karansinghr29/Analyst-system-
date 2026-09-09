"""
test_phase17_evidence_recovery.py -- the capabilities the evidence always supported.

The audit that preceded this phase found the gap was never in the export. `journal_lines` is
shipped denormalised with `apartment_id` on the line and the estate calculators grouped it away;
`tenant_allotments` holds 1,213 dated stints and only the current ones were read; `bed_rates`
carries `from_date`/`to_date` and was never loaded at all. M.OCC.005 was registered ACTIVE,
SHOW_BOTH, with "Full history available" written into its own historical policy, and mapped to
NOT_IMPLEMENTED beside two metrics that genuinely have no exported output.

So these tests are not about new analytics. They hold two lines at once: that the recovered
figures are the engine's own rows read one level finer, and that nothing was loosened to get
them -- profit is still blocked, occupancy still shows every definition, no threshold for
"unusual" has appeared, and no unattributed rupee has been quietly given to an apartment.
"""
import re

import pytest

from engine.execution import MetricExecutor
from engine.evidence_loader import load, load_table
from engine.calculators import rent as rent_calc


@pytest.fixture(scope="module")
def executor():
    return MetricExecutor()


def only(answer):
    assert answer.results, f"no result: {answer.not_determinable_reason}"
    return answer.results[0]


# --- 1-2. historical rent, and the rate card kept separate from it -------------------------------

def test_a_past_month_reports_the_rent_recorded_on_the_stay_that_covered_it(executor):
    """M.RENT.001 answers for today. The stay's own dates answer for a past month."""
    answer = executor.execute("M.RENT.002", period="2026-02", apartment_code="A12")
    assert answer.trust_level == "DISCLOSE"
    rents = only(answer).value
    assert rents, "no bed found for a month A12 was occupied in"
    assert all(key.startswith("A12 bed ") for key in rents), rents

    # The stays that produced them really do span that month.
    rows = rent_calc.historical_rent_rows("2026-02", "A12")
    assert {r["bed"] for r in rows} == {k.rsplit(" ", 1)[-1] for k in rents}


def test_a_month_the_apartment_was_empty_is_said_to_be_empty_not_answered_from_today(executor):
    """A12's earliest recorded stay begins in 2025-08. An earlier month has no rent in force,
    and the current figure must not be offered in its place."""
    answer = executor.execute("M.RENT.002", period="2025-06", apartment_code="A12")
    assert answer.trust_level == "NOT_DETERMINABLE"
    assert "no bed occupied" in answer.not_determinable_reason
    assert not answer.results


def test_an_intra_stay_rent_revision_is_still_not_determinable(executor):
    """One stay carries one recorded rent. The table has no revision date and the change log
    holds no rent change, so no second rent may appear inside one stay."""
    answer = executor.execute("M.RENT.002", period="2026-02")
    limitations = only(answer).limitations
    assert "changed part-way through a stay" in limitations
    assert "the records do not show it" in limitations

    audit = load_table("audit_logs")
    assert (audit["table_name"] == "tenant_allotments").sum() == 0
    assert audit["changes"].astype(str).str.contains("monthly_rental").sum() == 0


def test_the_rate_card_is_reported_as_a_listing_not_as_a_charged_rent(executor):
    answer = executor.execute("M.RENT.003", period="2023-05")
    rates = only(answer)
    assert rates.value, "no rate covers that period"
    assert all(re.search(r"bathroom$", k) for k in rates.value), rates.value
    assert "not what any tenant was charged" in rates.limitations

    # Dated, and the dates are the card's own.
    card = load_table("bed_rates")
    assert {"from_date", "to_date", "monthly_rate"} <= set(card.columns)


# --- 3-4. historical occupancy ------------------------------------------------------------------

@pytest.fixture(scope="module")
def occupancy(executor):
    return executor.execute("M.OCC.005")


def test_occupancy_history_is_reconstructed_across_the_recorded_span(occupancy):
    assert occupancy.results, occupancy.not_determinable_reason
    for result in occupancy.results:
        months = sorted(result.value)
        assert months[0] == "2019-11", months[0]
        assert months[-1] == "2026-08", months[-1]
        assert len(months) == 82, len(months)
        assert all(result.value[m] > 0 for m in months), "a month came back empty"


def test_the_reconstruction_matches_the_exported_timeline_definition(occupancy):
    """H.012e states the timeline reading reaches 194 of 203 beds. The reconstruction reports
    the same reach -- derived here, and cross-checked against the export rather than assumed."""
    exported = load("H.012e").iloc[0]
    stated = re.search(r"reaches (\d+) of (\d+) beds", occupancy.results[0].limitations)
    assert stated, occupancy.results[0].limitations
    assert int(stated.group(1)) == int(exported["numerator"])
    assert int(stated.group(2)) == int(exported["denominator"])


def test_both_readings_of_occupied_in_a_month_are_returned_and_neither_is_chosen(occupancy):
    assert occupancy.trust_level == "SHOW_BOTH"
    assert len(occupancy.results) == 2
    labels = [r.definition_label for r in occupancy.results]
    assert any("any point" in l for l in labels), labels
    assert any("last covered day" in l for l in labels), labels
    # They genuinely differ, which is why neither may stand alone.
    any_point = next(r for r in occupancy.results if "any point" in r.definition_label).value
    at_edge = next(r for r in occupancy.results if "last covered" in r.definition_label).value
    assert any(any_point[m] != at_edge[m] for m in any_point)


def test_a_stay_starting_after_the_snapshot_is_not_counted_as_occupancy(occupancy):
    limitations = occupancy.results[0].limitations
    assert "the series stops there" in limitations
    assert "no month is interpolated" in limitations


# --- 5-7. the apartment dimension ---------------------------------------------------------------

@pytest.mark.parametrize("metric_id,account_type", [("M.REV.003", "INCOME"),
                                                    ("M.EXP.003", "EXPENSE")])
def test_apartment_figures_are_the_estate_figures_read_one_level_finer(executor, metric_id,
                                                                      account_type):
    """The apartment total plus the unattributed part must equal the estate total exactly. If it
    does not, the split is not a split of this measure."""
    from engine.calculators import ledger as L
    from engine.calculators.apartment import UNATTRIBUTED

    estate = round(float(L.ledger_excl_reversals().pipe(
        lambda m: m[m["account_type"] == account_type])["signed_amount"].sum()), 2)
    value = only(executor.execute(metric_id)).value
    assert round(sum(value.values()), 2) == estate


def test_the_unattributed_part_is_named_and_never_divided(executor):
    from engine.calculators.apartment import UNATTRIBUTED

    result = only(executor.execute("M.REV.003"))
    assert UNATTRIBUTED in result.value
    assert result.value[UNATTRIBUTED] > 0, "this export has unattributed revenue to disclose"
    assert "NOT spread across the apartments" in result.limitations
    assert "no rule for dividing it" in result.limitations


def test_the_bed_allocation_subset_is_corroboration_not_the_expense_population(executor):
    """`expense_bed_allocations` and the bed-expense view cover a fraction of the expense base.
    Naming them is right; counting them as the whole would understate every apartment."""
    result = only(executor.execute("M.EXP.003"))
    assert "is a subset of the expenses above" in result.limitations
    assert "not added to them" in result.limitations
    allocated = float(load_table("expense_bed_allocations")["allocated_amount"].sum())
    assert allocated < sum(v for v in result.value.values()) / 2


# --- 8-10. what must not have moved -------------------------------------------------------------

def test_profit_is_still_blocked_and_has_no_apartment_headline(executor):
    profit = executor.execute("M.PROFIT.001")
    assert profit.trust_level == "BLOCK"
    assert not profit.headline_permitted
    assert len(profit.results) == 3

    from engine.calculators import REGISTRY
    assert not any("profit" in str(k).lower() and k.startswith("M.")
                   and k not in ("M.PROFIT.001", "M.PNL.001") for k in REGISTRY), \
        "a second profit metric appeared"


def test_current_occupancy_still_shows_every_competing_definition(executor):
    current = executor.execute("M.OCC.001")
    assert current.trust_level == "SHOW_BOTH"
    assert len(current.results) >= 4
    assert not current.headline_permitted


def test_no_anomaly_verdict_was_introduced():
    """Historical data now exists. A definition of what counts as anomalous still does not, and
    the recovery must not have invented one."""
    from engine.calculators import REGISTRY
    import engine.calculators.occupancy as occ
    import engine.calculators.apartment as apt

    for module in (occ, apt, rent_calc):
        source = open(module.__file__, encoding="utf-8").read()
        for word in ("z_score", "zscore", "iqr", "stddev", "std_dev", "anomaly_threshold"):
            assert word not in source.lower(), f"{module.__name__} introduced {word}"


# --- 11-14. owner-facing behaviour ---------------------------------------------------------------

INTERNAL = (
    r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", r"\b[FTH]\.\d{3}[a-z]?\b", r"\bFN\.[a-z_]+\b",
    r"\bv_[a-z0-9_]+\b", r"\bjournal_lines\b", r"\bapartment_id\b", r"\bsigned_amount\b",
    r"\bbed_rates\b", r"\bexpense_bed_allocations\b", r"\btenant_allotments\b",
    r"\b(?:SAFE|DISCLOSE|SHOW_BOTH|BLOCK)\b",
)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.service import AnalyticsService, create_app
    return TestClient(create_app(AnalyticsService()))


@pytest.mark.parametrize("title", ["Revenue by apartment", "Expenses by apartment",
                                   "Historical occupancy", "Published rate by bed type"])
def test_the_new_tiles_reach_the_owner_without_internal_vocabulary(client, title):
    for section in ("financial", "operations"):
        payload = client.get(f"/api/analytics/{section}").json()
        tile = next((t for t in payload["tiles"] if t["title"].startswith(title)), None)
        if tile is None:
            continue
        # The boundary is the owner projection, which is what every surface renders and what
        # the export writes. The raw payload keeps the engine's own audit wording on purpose --
        # that is where the evidence chain reads it.
        from engine import owner_presentation as op

        prose = " ".join(op.sanitize_owner_text(str(x)) for x in
                         (tile.get("caveat", ""), tile.get("unavailable_reason", ""),
                          (tile.get("trust") or {}).get("owner_explanation", "")))
        for pattern in INTERNAL:
            assert not re.search(pattern, prose), f"{title}: {pattern} leaked -- {prose[:160]}"
        return
    pytest.fail(f"{title} is on no section")


def test_an_unknown_apartment_stays_an_honest_limitation(executor):
    answer = executor.execute("M.RENT.002", period="2026-02", apartment_code="ZZ99")
    assert answer.trust_level == "NOT_DETERMINABLE"
    assert "There is no apartment 'ZZ99' in the exported records." in answer.not_determinable_reason
    assert not answer.results


def test_the_question_layer_reaches_the_recovered_apartment_revenue():
    from engine.analyst_intelligence import AnalystIntelligence

    analyst = AnalystIntelligence(verbalize=False)
    analyst.llm.reset()
    answer = analyst.ask("Which apartment generated the most revenue?")
    assert answer.trust_level == "DISCLOSE", answer.trust_level
    assert "Not determinable" not in answer.text


def test_the_question_layer_still_refuses_to_pick_one_occupancy_definition():
    """Routing now finds historical occupancy. It must still decline to compare periods on a
    measure whose definitions disagree, rather than choosing one to make the answer come out."""
    from engine.analyst_intelligence import AnalystIntelligence

    analyst = AnalystIntelligence(verbalize=False)
    analyst.llm.reset()
    answer = analyst.ask("How did occupancy change over the last 6 months?")
    assert answer.trust_level == "NOT_DETERMINABLE"
    assert "definition" in answer.text.lower()
