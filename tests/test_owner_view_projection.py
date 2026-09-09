"""
test_owner_view_projection.js.test.py -- the browser-side half of the Owner Home projection.

`owner_view.js` decides what a tile actually reads as: which part of a composite becomes the
headline, how a nested figure is grouped, and how a definition written in implementation
vocabulary is named. Those decisions are not visible from the API payload, so the Python tests
beside this file cannot see them -- and every one of them was wrong in a way an owner would
notice:

  * the occupancy tile headlined `195`, its bed count, because the denominator came before the
    rate in the engine's ordering and the first eligible part was promoted;
  * the reconciliation figure arrives as groups flattened into one string, and the splitter was
    single-level, so `legacy_amount:` reached the screen;
  * `V1, bed.status=Live` and `NOT COMPUTED IN PHASE 1` stood as definition labels.

These assertions are structural rather than cosmetic: they check the RULES the projection
applies, using the real strings the engine emits. They are skipped where no JavaScript runtime
is available, so a machine without Node does not report a failure it cannot diagnose.
"""
import json
import os
import shutil
import subprocess
import textwrap

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="no JavaScript runtime available")

import pathlib

MODULE_URL = (pathlib.Path(__file__).resolve().parent.parent
              / "frontend" / "owner_view.js").as_uri()

# The strings the engine actually produces, taken from the Owner Home payload.
OCCUPANCY = "occupied: 168; total: 195; occupancy_pct: 86.15"
DUES = "ar_balance: ₹83,297.85; deposit_held: ₹4,221,150.00; booking_advance: ₹0.00"
RECONCILIATION = ("deposit_settlements: legacy_amount: ₹5,085,959.33; "
                  "je_net_amount: ₹5,669,454.67; diff: ₹583,495.34; verdict: INVESTIGATE; "
                  "expenses: legacy_amount: ₹716,402.00; verdict: PERFECT")
COLLECTIONS = "total: ₹81,855,686.97; deposit_collections: ₹116,000.00"


def run_projection(script):
    """Evaluate a snippet against the real module and return its JSON result."""
    source = textwrap.dedent(f"""
        import {{ splitComposite, ownerDefinitionLabel }} from '{MODULE_URL}';
        {script}
    """)
    proc = subprocess.run(
        [NODE, "--input-type=module", "-e", source],
        capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


# --- the headline of a composite -----------------------------------------------------------------

def test_a_rate_is_the_headline_not_the_denominator():
    """The occupancy tile read 195 -- the number of beds -- above a label saying "Occupancy"."""
    out = run_projection(
        f"console.log(JSON.stringify(splitComposite({json.dumps(OCCUPANCY)})));")
    assert out["main"] == "86.15%", out
    labels = {p["label"] for p in out["secondary"]}
    assert "Occupied beds" in labels and "Total" in labels, out


def test_a_stated_total_is_still_the_headline_when_there_is_no_rate():
    out = run_projection(
        f"console.log(JSON.stringify(splitComposite({json.dumps(COLLECTIONS)})));")
    assert out["main"] == "₹81,855,686.97"
    assert [p["label"] for p in out["secondary"]] == ["Deposits"]


def test_a_composite_with_no_total_shows_named_parts_and_no_headline():
    """Promoting one part would assert a relationship the payload does not state; keeping the
    raw string put "ar_balance: ..." on the tile."""
    out = run_projection(f"console.log(JSON.stringify(splitComposite({json.dumps(DUES)})));")
    assert out["main"] == ""
    assert [p["label"] for p in out["secondary"]] == [
        "Outstanding", "Held as deposits", "Booking advances"]
    assert all("_" not in p["label"] for p in out["secondary"]), out


# --- nesting and verdicts --------------------------------------------------------------------------

def test_a_nested_composite_is_grouped_rather_than_flattened():
    out = run_projection(
        f"console.log(JSON.stringify(splitComposite({json.dumps(RECONCILIATION)})));")
    labels = [p["label"] for p in out["secondary"]]
    assert "Deposit settlements — Source system" in labels, labels
    assert "Expenses — Source system" in labels, labels
    assert all("_" not in l for l in labels), labels


def test_a_verdict_token_reads_as_an_outcome():
    out = run_projection(
        f"console.log(JSON.stringify(splitComposite({json.dumps(RECONCILIATION)})));")
    values = [p["value"] for p in out["secondary"]]
    assert "Needs investigation" in values and "Matches" in values, values
    assert "INVESTIGATE" not in values and "PERFECT" not in values, values


# --- definition labels ------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Def D (get_universal_metrics v1, bed.status=Live)", "Active-bed definition"),
    ("Def E (historical, day-weighted) -- NOT COMPUTED IN PHASE 1",
     "Not currently available from the exported evidence"),
    ("Def A (v_occupancy, Staying only, Live+Live)", "Residents only, active beds"),
    ("Def C (Staying+On-Notice, ALL beds)", "Residents and those on notice, all beds"),
])
def test_an_implementation_label_is_restated_in_business_terms(raw, expected):
    out = run_projection(
        f"console.log(JSON.stringify(ownerDefinitionLabel({json.dumps(raw)})));")
    assert out == expected


def test_a_label_that_already_reads_plainly_is_left_alone():
    """The projection renames implementation vocabulary; it does not rewrite English."""
    out = run_projection(
        "console.log(JSON.stringify(ownerDefinitionLabel("
        "'Tenant dues -- Def A: v_outstanding_receivables (reversals excluded)')));")
    assert out == "Reversals excluded"


def test_no_definition_is_dropped_by_being_renamed():
    """Every competing definition must survive the projection, including the one that has no
    figure -- an owner who cannot see it cannot know it exists."""
    labels = run_projection(
        "const raw = ['Def A (v_occupancy, Staying only, Live+Live)',"
        " 'Def B (Staying+On-Notice, Live+Live)',"
        " 'Def C (Staying+On-Notice, ALL beds)',"
        " 'Def D (get_universal_metrics v1, bed.status=Live)',"
        " 'Def E (historical, day-weighted) -- NOT COMPUTED IN PHASE 1'];"
        "console.log(JSON.stringify(raw.map(ownerDefinitionLabel)));")
    assert len(labels) == 5
    assert all(l for l in labels), labels
    assert len(set(labels)) == 5, f"two definitions collapsed into one label: {labels}"
