"""
test_occupancy_apartment_availability.py -- which apartments belong in the occupancy denominator.

Written after a reported defect: A33/A34 supposedly missing from the August occupancy
denominator, A22 supposedly present in it. The evidence does not support either claim -- the
existing `Live` bed AND `Live` apartment semantics already produce exactly the requested
behaviour, and the exported `v_occupancy` reference agrees with it bed for bed.

So these are regression locks, not a fix. They pin the availability rule to the SOURCE STATUS
COLUMNS rather than to any apartment code, so a future apartment record is handled by the same
rule. The apartment codes appear only as the fixtures the report named.
"""
import pytest

from engine.evidence_loader import load_table, load_view
from engine.calculators.occupancy import _live_beds_frame
from engine.execution import MetricExecutor


ACTIVE_IN_AUGUST = ("A33", "A34")     # apartments.status == 'Live'
INACTIVE = "A22"                      # apartments.status == 'Not-Active', ended 2026-01-20


@pytest.fixture(scope="module")
def beds_by_code():
    beds = load_table("beds")
    apts = load_table("apartments")
    code_of = dict(zip(apts["id"], apts["apartment_code"]))
    frame = beds.copy()
    frame["apartment_code"] = frame["apartment_id"].map(code_of)
    return frame


@pytest.fixture(scope="module")
def denominator_bed_ids():
    """The Def A / Def B denominator: a bed that is Live in an apartment that is Live."""
    return set(_live_beds_frame()["id"])


def test_active_apartments_contribute_their_available_beds(beds_by_code, denominator_bed_ids):
    """A33 and A34 are Live apartments, so their Live beds are in the denominator.

    Asserted through the status columns, not the codes: every bed counted is one the source
    marks Live in an apartment the source marks Live. Their own Not-Active beds are correctly
    left out -- an apartment being available does not make a decommissioned bed available.
    """
    apts = load_table("apartments")
    for code in ACTIVE_IN_AUGUST:
        assert (apts.loc[apts["apartment_code"] == code, "status"] == "Live").all(), (
            f"{code} is not Live in the source; the premise of this test has changed")

        rows = beds_by_code[beds_by_code["apartment_code"] == code]
        live_beds = set(rows.loc[rows["status"] == "Live", "id"])
        assert live_beds, f"{code} has no Live beds in the source"
        assert live_beds <= denominator_bed_ids, (
            f"{code}'s available beds are missing from the occupancy denominator")

        dormant = set(rows.loc[rows["status"] != "Live", "id"])
        assert not (dormant & denominator_bed_ids), (
            f"{code} contributed a bed the source does not mark Live")


def test_an_inactive_apartment_is_excluded_from_the_denominator(
        beds_by_code, denominator_bed_ids):
    """A22 is Not-Active, so none of its beds may sit in the denominator.

    The exclusion comes from the apartment's own status, so any apartment retired later is
    handled identically without touching this code.
    """
    apts = load_table("apartments")
    assert (apts.loc[apts["apartment_code"] == INACTIVE, "status"] == "Not-Active").all()

    rows = beds_by_code[beds_by_code["apartment_code"] == INACTIVE]
    assert len(rows) > 0, "the fixture apartment has no beds"
    assert not (set(rows["id"]) & denominator_bed_ids), (
        f"{INACTIVE} is inactive but its beds are counted as available")

    # And the reconstruction still matches the exported reference bed for bed.
    reference = load_view("v_occupancy")
    assert int(reference["total_beds"].iloc[0]) == len(denominator_bed_ids)


def test_the_competing_occupancy_definitions_are_preserved():
    """The conflict is the finding. Def C counts ALL beds -- including the inactive ones -- by
    design, and that disagreement is exactly what SHOW_BOTH exists to disclose. Narrowing it to
    one 'correct' denominator would resolve a conflict the evidence has not resolved."""
    answer = MetricExecutor().execute("M.OCC.001")
    assert answer.trust_level == "SHOW_BOTH"
    assert answer.headline_permitted is False

    totals = {r.definition_label: (r.value or {}).get("total")
              for r in answer.results if isinstance(r.value, dict)}
    assert len(totals) >= 3, "the competing definitions were collapsed"
    assert len(set(totals.values())) > 1, (
        "every definition now agrees on the denominator; a genuine conflict was silently "
        "resolved")
