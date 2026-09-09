"""
test_owner_home_presentation.py -- the Owner Home in the owner's language.

Read as an owner, the Executive Snapshot was talking to its own developers. A tile said
`ar_balance: ₹83,297.85; deposit_held: ₹4,221,150.00`. A definition was labelled
`V1, bed.status=Live`. An insight said

    "This is a standing, currently-recorded condition (status: MEASURED) affecting Profit / P&L,
     not a one-off reading. It is surfaced without being asked because classifies it CRITICAL
     ( 2 condition 1)."

-- which is worse than the original, because stripping the record identifier out of a sentence
leaves the sentence broken. The engine's prose is written for the audit trail and is correct
there; it has to be composed again for the owner, from the same structured fields.

These tests hold the boundary, not the wording: no record identifiers, no raw dictionary keys,
no specification clauses, no dangling fragments -- and, just as firmly, no disclosure lost. A
conflicted measure still shows every definition, a caveat still travels with its figure, and
the absence of a materiality threshold is still stated.
"""
import os
import re

import pytest

os.environ.setdefault("AI_ANALYTICS_AUTH_DISABLE", "true")
os.environ.pop("AI_ANALYTICS_ENV", None)


@pytest.fixture(scope="module")
def home():
    from fastapi.testclient import TestClient
    from api.service import AnalyticsService, create_app

    client = TestClient(create_app(AnalyticsService()))
    return client.get("/api/owner/home").json()


def owner_prose(home):
    """Every string the Owner Home renders as prose. Audit fields are excluded on purpose:
    `metric_ids`, `dq_ids`, `conflict_ids` and `evidence` are identifier lists for the detail
    view and the evidence chain, and are not rendered on this screen."""
    out = []
    for insight in home["insights"]:
        out += [insight["what_happened"], insight["why_it_matters"],
                insight["recommended_action"], insight["what_would_change_it"],
                insight["confidence"], insight["category_label"]]
        out += [e.get("question", "") for e in insight["ai_entry_points"]]
    out += [d["decision"] for d in home["decision_queue"]]
    out += [a["recommendation"] for a in home["recommended_actions"]]
    out += [a["confidence"] for a in home["recommended_actions"]]
    out += list(home["limitations"])
    for change in home["changes"]:
        out += [str(change.get(k, "")) for k in
                ("what_happened", "why_it_matters", "what_would_change_it")]
    return [s for s in out if s]


# --- 1. no internal vocabulary ------------------------------------------------------------------

_INTERNAL = (
    (r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", "metric id"),
    (r"\bDQ\.\d{3}\b", "data-quality id"),
    (r"\bC\.\d{3}\b", "conflict id"),
    (r"\bINS\.[A-Z0-9._]+\b", "insight id"),
    (r"\bFN\.\d{3}\b", "function id"),
    (r"\bv_[a-z0-9_]+\b", "database view"),
    (r"\b[\w.-]+\.(?:md|csv|py|json)\b", "specification filename"),
    (r"\bcondition \d\b", "internal condition number"),
    (r"status:\s*[A-Z]", "internal status"),
    (r"\b(?:SELECT|FROM|GROUP BY|JOIN)\b", "SQL"),
    (r"\bNOT COMPUTED IN PHASE\b", "phase note"),
    (r"\bbed\.status\b|\bget_universal_metrics\b", "implementation label"),
)


@pytest.mark.parametrize("pattern,what", _INTERNAL)
def test_no_internal_vocabulary_reaches_the_owner(home, pattern, what):
    for text in owner_prose(home):
        assert not re.search(pattern, text), f"{what} leaked: {text[:150]!r}"


def test_no_raw_dictionary_fields_are_exposed(home):
    """`ar_balance: ...; deposit_held: ...` is a serialised dict, not a sentence."""
    for text in owner_prose(home):
        assert not re.search(r"\b[a-z]+_[a-z_]+\s*:", text), f"raw field: {text[:150]!r}"


def test_no_internal_confidence_grade_is_shown_untranslated(home):
    """PROVEN / SUSPECTED / SPLIT are the engine's grades. They mean nothing to an owner
    unless the sentence says what they mean."""
    for text in owner_prose(home):
        assert not re.search(r"\b(?:PROVEN|SUSPECTED|SPLIT|MEASURED)\b", text), (
            f"untranslated grade: {text[:120]!r}")


def test_no_sentence_dangles_where_an_identifier_was_removed(home):
    """The failure mode that made stripping worse than leaking."""
    for text in owner_prose(home):
        for fragment in ("behind before", "behind is currently", "reviewing with",
                         "because classifies", "which treats as", "figure:,"):
            assert fragment not in text, f"broken sentence: {text[:150]!r}"
        assert not re.search(r":\s*[,.;]", text), f"orphaned punctuation: {text[:150]!r}"


# --- 2. a risk insight reads as a business condition -----------------------------------------------

def test_a_risk_insight_says_what_is_happening_and_what_to_do(home):
    risk = next(i for i in home["insights"] if i["insight_id"].startswith("INS.RISK"))
    assert re.search(r"\b(currently|records)\b", risk["what_happened"], re.I)
    assert risk["recommended_action"], "no action stated"
    assert "worklist" in risk["recommended_action"].lower()
    assert risk["why_it_matters"], "no reason stated"


def test_a_data_quality_insight_is_not_described_as_a_definition_conflict(home):
    """They are different findings. Branching on the trust posture rather than on the kind of
    record described a recording problem as "more than one definition of profit"."""
    dq = next(i for i in home["insights"] if i["insight_id"].startswith("INS.DQ"))
    assert "recording problem" in dq["what_happened"].lower()
    assert "more than one definition" not in dq["what_happened"].lower()


def test_the_insight_entry_point_asks_a_question_an_owner_would_type(home):
    for insight in home["insights"]:
        for entry in insight["ai_entry_points"]:
            assert "INS." not in entry.get("question", ""), entry


# --- 3. disclosures are preserved, not tidied away ---------------------------------------------------

def test_a_definition_conflict_keeps_its_business_meaning(home):
    conflict = next(i for i in home["insights"]
                    if i["insight_id"].startswith("INS.CONFLICT"))
    what = conflict["what_happened"].lower()
    assert "more than one definition" in what
    assert "do not agree" in what
    assert "decide which definition" in conflict["recommended_action"].lower()
    assert "authoritative" in conflict["recommended_action"].lower()
    assert "business decision" in conflict["what_would_change_it"].lower()


def test_every_competing_definition_is_still_shown(home):
    """Cleaning the language must not reduce a conflicted measure to one figure."""
    conflicted = [t for t in home["business_health"] + home["operations"]
                  if t.get("definitions")]
    assert conflicted, "no conflicted measure in the payload"
    for tile in conflicted:
        assert len(tile["definitions"]) >= 2, tile["title"]


def test_the_missing_materiality_threshold_is_still_stated(home):
    blob = " ".join(owner_prose(home)).lower()
    assert "threshold" in blob
    assert "no business threshold is defined" in blob or "no threshold exists" in blob


def test_the_system_flag_is_not_presented_as_a_business_priority(home):
    """`Critical` is the system's own rule firing on the evidence. No validated priority score
    exists, so the ordering must not be offered as a judgement about business impact."""
    blob = " ".join(owner_prose(home)).lower()
    assert "not ranked by business impact" in blob
    assert "no validated priority score" in blob


# --- 4. trust states are untouched ---------------------------------------------------------------------

def test_the_trust_postures_are_unchanged(home):
    levels = {t["trust"]["trust_level"] for t in home["business_health"] + home["operations"]}
    assert {"SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK"} <= levels


@pytest.mark.parametrize("title,level", [
    ("revenue", "SAFE"),
    ("collections", "DISCLOSE"),
    ("profit", "BLOCK"),
    ("tenant dues", "SHOW_BOTH"),
])
def test_named_measures_keep_their_posture(home, title, level):
    tile = next(t for t in home["business_health"] if title in t["title"].lower())
    assert tile["trust"]["trust_level"] == level, tile["title"]


def test_the_figures_themselves_are_untouched(home):
    blob = str(home)
    for figure in ("72,705,593.43", "20,784,831.96", "4,221,150.00"):
        assert figure in blob, f"{figure} disappeared from the payload"


# --- 5. the sanitizer's own repairs ----------------------------------------------------------------------

@pytest.mark.parametrize("raw,forbidden", [
    ("3 KPI(s) carry competing definitions and are shown per definition rather than as one "
     "figure: M.AR.001A, M.PROFIT.001.", ":,"),
    ("Recommend reviewing DQ.013 with its documented evidence.", "DQ."),
    ("It is surfaced because DQ.016 classifies it CRITICAL "
     "(insight_generation_spec.md 2 condition 1).", "condition 1"),
])
def test_the_sanitizer_leaves_no_orphaned_punctuation(raw, forbidden):
    from engine import owner_presentation as op

    cleaned = op.sanitize_owner_text(raw)
    assert forbidden not in cleaned, cleaned
    assert not cleaned.rstrip().endswith(":"), cleaned


def test_a_legitimate_colon_survives():
    """The repairs target punctuation left behind by a removal, not ordinary prose."""
    from engine import owner_presentation as op

    for text in ("Note: this figure is usable.",
                 "The definitions disagree: one includes reversals and one does not."):
        assert ":" in op.sanitize_owner_text(text), text


# --- 6. the second pass: readable to a non-technical owner -------------------------------------
#
# The first pass removed the internal vocabulary. What was left still read like a system talking
# about itself: an occupancy tile headlined by its bed count, a reconciliation figure whose parts
# were a flattened dictionary, movements labelled INCREASE between 2026-06-01 and 2026-07-01, and
# a classification caveat repeated on all sixteen cards until it stopped being read.


def test_the_snapshot_date_is_a_date_not_a_system_boundary(home):
    """"export snapshot 2026-08-29" names the engine's own cut-off. An owner reads a date."""
    assert home["as_of"] == "29 August 2026"
    assert "snapshot" not in home["as_of"].lower()


def test_a_movement_reads_in_words_and_months(home):
    """INCREASE / 2026-07-01 is how a movement is recorded, not how it is read."""
    for change in home["changes"]:
        assert change["direction"] in ("rose", "fell", "unchanged", "not yet complete",
                                       "not comparable"), change["direction"]
        for field in ("current_period", "previous_period"):
            assert not re.match(r"^\d{4}-\d{2}", change[field] or ""), change[field]


def test_a_fall_is_not_stated_as_a_double_negative(home):
    """"fell -221,734.74 (-5.88%)" reads as a rise. The direction word carries the sign."""
    for change in home["changes"]:
        if change["direction"] == "fell":
            assert not change["display_change"].lstrip().startswith("-"), change
            assert "(-" not in change["display_change"], change


def test_the_change_insight_states_months_not_period_keys(home):
    change = next(i for i in home["insights"] if i["insight_id"].startswith("INS.CHANGE"))
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", change["what_happened"]), change


def test_the_classification_caveat_is_stated_once_not_on_every_card(home):
    """True of every item on the page, so it belongs beneath the section. Repeated sixteen
    times it is wallpaper."""
    per_card = sum(1 for i in home["insights"]
                   if "not ranked by business impact" in i["what_would_change_it"])
    assert per_card == 0, f"{per_card} cards still repeat the caveat"
    assert any("not ranked by business impact" in l for l in home["limitations"]), (
        "the caveat was dropped rather than moved")


def test_a_recording_problem_does_not_ask_the_owner_to_pick_a_definition(home):
    """A data-quality finding carries conflict records too, but the choice it implies is not
    the owner's to make."""
    dq = next(i for i in home["insights"] if i["insight_id"].startswith("INS.DQ"))
    assert "choosing between the definitions" not in dq["what_would_change_it"].lower()


def test_the_recommendations_agree_with_themselves_grammatically(home):
    """"before tenant dues and 2 other measures is used" is the shape a template leaves."""
    for row in home["decision_queue"]:
        assert " measures is used" not in row["decision"], row["decision"]
        assert " 1 other measures" not in row["decision"], row["decision"]


def test_a_measure_is_not_listed_twice_under_two_names(home):
    """"tenant dues and tenant dues by tenant" says one thing twice; the broader name covers
    the narrower."""
    for row in home["decision_queue"]:
        assert "tenant dues and tenant dues" not in row["decision"], row["decision"]


def test_the_coverage_note_names_months_not_period_keys(home):
    """"Period(s) 2026-08-01, 2026-09-01 excluded as incomplete at the export snapshot
    (2026-08-29)" is the audit sentence. The owner needs which months are missing and why."""
    notes = [c["coverage_note"] for c in home["changes"] if c.get("coverage_note")]
    assert notes, "no coverage note in the payload"
    for note in notes:
        assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", note), note
        assert "Period(s)" not in note, note
        assert "part-month" in note or "left out" in note, note


def test_the_excluded_month_is_not_confused_with_the_snapshot_month(home):
    """August is both an excluded month and the month the snapshot falls in. Reading the dates
    by position promoted September into the snapshot's place and dropped it from the list."""
    revenue = next(c for c in home["changes"] if "Revenue" in c["title"])
    note = revenue["coverage_note"]
    assert "August 2026" in note and "September 2026" in note, note


def test_the_limitations_are_stated_without_jargon(home):
    joined = " ".join(home["limitations"]).lower()
    for word in ("materiality", "kpi(s)", "insight triggers", "specification"):
        assert word not in joined, f"{word!r} still in the limitations"
    assert "threshold" in joined, "the substance was removed with the jargon"
    assert "more than one definition" in joined


def test_no_analyst_jargon_survives_in_the_rendered_prose(home):
    """"Materiality", "KPI(s)" and "insight trigger" are the vocabulary of the specification
    that mandates the behaviour, not of the owner reading its result. The behaviour itself is
    unchanged and still stated -- these tests elsewhere assert the threshold is still declared
    missing."""
    for text in owner_prose(home):
        for word in ("materiality", "kpi(s)", "insight trigger"):
            assert word not in text.lower(), f"{word!r} in owner prose: {text[:120]!r}"
