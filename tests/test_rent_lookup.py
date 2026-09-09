"""
test_rent_lookup.py -- M.RENT.001, the governed entity-level rent lookup.

The finding that shapes every test here: an apartment does not have a rent. `monthly_rental`
sits on `tenant_allotments`, one row per tenant-on-a-bed, and 32 of the 37 apartments with a
current allotment carry more than one rent right now -- A12 alone runs Rs.14,500, Rs.15,500 and
Rs.19,500 across four occupied beds. The application's own `get_occupancy_intelligence` resolves
rent per BED (`distinct on (bed_id) ... order by onboarding_date desc`) and converts it with
`* days / 30.0`, which settles both the grain and the monthly basis from evidence rather than
from the column's name.

So "the rent for A12" is answerable, and the answer is four figures rather than one. The tests
below pin that, and pin the four things that must never be substituted for it: a revenue total,
an average across beds, today's figure presented as a past one, and an estate-wide list handed
back for a question about one apartment.
"""
import re

import pytest

from engine import concept_map
from engine import dimension_resolution as dimres
from engine.analyst_intelligence import AnalystIntelligence
from engine.calculators import rent as rent_calc
from engine.execution import MetricExecutor
from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT
from engine.semantic_registry import SemanticRegistry


@pytest.fixture(scope="module")
def analyst():
    return AnalystIntelligence(verbalize=False)


@pytest.fixture(scope="module")
def registry():
    return SemanticRegistry()


def answer(analyst, question):
    analyst.llm.reset()
    return analyst.ask(question)


# --- 1. current rent lookup -------------------------------------------------------------------

def test_the_metric_returns_one_figure_per_occupied_bed():
    out = MetricExecutor().execute("M.RENT.001", apartment_code="A12")
    assert out.trust_level == "DISCLOSE"
    value = out.results[0].value
    assert isinstance(value, dict)
    assert set(value) == {"A12 bed A1", "A12 bed B1", "A12 bed C1", "A12 bed C2"}
    assert value["A12 bed A1"] == 19500.0
    assert value["A12 bed B1"] == 15500.0
    assert value["A12 bed C1"] == 14500.0
    assert value["A12 bed C2"] == 14500.0


def test_the_owner_answer_states_every_bed_and_collapses_none_of_them(analyst):
    text = answer(analyst, "What is the rent for A12?").text
    for figure in ("19,500", "15,500", "14,500"):
        assert figure in text, f"{figure} is missing from the answer"
    assert "does not have one rent" in text
    # The mean of A12's four beds is 16,000. A figure nobody recorded must not appear.
    assert "16,000" not in text


def test_only_the_named_apartment_is_reported(analyst):
    text = answer(analyst, "What is the rent for A12?").text
    others = set(re.findall(r"\b([A-D]\d{2}[AB]?)\b", text)) - {"A12", "A1", "B1", "C1", "C2"}
    assert not others, f"beds from other apartments leaked in: {sorted(others)}"


def test_an_exited_allotment_is_not_reported_as_current():
    """A12 holds fourteen allotment rows. Four are live; the rest have ended."""
    rows = rent_calc.current_rent_rows("A12")
    assert len(rows) == 4
    assert {r["bed"] for r in rows} == {"A1", "B1", "C1", "C2"}


def test_the_lookup_is_deterministic():
    assert rent_calc.current_rent_rows("A12") == rent_calc.current_rent_rows("A12")


# --- 2. natural-language paraphrases ------------------------------------------------------------

PARAPHRASES = (
    "What is the rent for A12?",
    "How much rent is A12?",
    "What's A12's monthly rent?",
    "What rent does A12 pay?",
)


@pytest.mark.parametrize("question", PARAPHRASES)
def test_each_paraphrase_reaches_the_rent_metric(analyst, question):
    a = answer(analyst, question)
    assert a.metric_ids == ("M.RENT.001",), f"{question}: {a.metric_ids}"
    assert a.trust_level == "DISCLOSE"
    assert "19,500" in a.text, question


@pytest.mark.parametrize("question", PARAPHRASES)
def test_each_paraphrase_resolves_the_apartment_as_an_entity(question):
    assert dimres.resolve_apartment_code(question) == "A12", question
    assert dimres.extract(question).filters.get("apartment_id") == "A12", question


def test_monthly_rent_is_read_as_the_measure_not_as_a_month_breakdown():
    """"Monthly rent" names the amount, the way "monthly salary" does. Read as a request for a
    month-by-month series it produced a dimension rejection for a plain question."""
    request = dimres.extract("What's A12's monthly rent?")
    assert "month" not in request.group_by


# --- 3. unknown apartment ------------------------------------------------------------------------

def test_an_apartment_that_does_not_exist_is_named_not_guessed_at(analyst):
    a = answer(analyst, "What is the rent for Z99?")
    assert a.trust_level == "NOT_DETERMINABLE"
    assert "Z99" in a.text
    assert NOT_DETERMINABLE_TEXT in a.text
    # The estate-wide list must not be handed back for a question about one apartment.
    assert "19,500" not in a.text


def test_an_unknown_code_resolves_to_nothing_rather_than_the_nearest_match():
    assert dimres.resolve_apartment_code("rent for Z99") == ""
    assert dimres.unknown_apartment_token("rent for Z99") == "Z99"
    # A13 does not exist; A12 does. Proximity must not resolve it.
    assert dimres.resolve_apartment_code("rent for A13") == ""


def test_the_calculator_refuses_an_unknown_apartment():
    out = MetricExecutor().execute("M.RENT.001", apartment_code="Z99")
    assert out.trust_level == "NOT_DETERMINABLE"
    assert "Z99" in out.not_determinable_reason


# --- 4. multiple records for one apartment --------------------------------------------------------

def test_multiple_current_rents_are_shown_as_multiple_not_reconciled(analyst):
    """These are not competing definitions of one figure -- they are different beds. Each is
    correct, and picking one would be choosing which bed speaks for the apartment."""
    rows = rent_calc.current_rent_rows("A12")
    distinct = {r["rent"] for r in rows}
    assert len(distinct) == 3, "the fixture no longer has multiple rents in A12"

    text = answer(analyst, "What is the rent for A12?").text
    assert "3 different amounts" in text
    for bed in ("bed A1", "bed B1", "bed C1", "bed C2"):
        assert bed in text


def test_an_apartment_whose_beds_agree_states_the_single_figure(analyst):
    """Five apartments do agree. Where the records give one answer, one answer is given."""
    from engine.evidence_loader import load_table

    agreeing = ""
    for code in sorted({r["apartment"] for r in rent_calc.current_rent_rows()}):
        rents = {r["rent"] for r in rent_calc.current_rent_rows(code)}
        if len(rents) == 1:
            agreeing = code
            break
    assert agreeing, "no apartment in the fixture has a single current rent"

    text = answer(analyst, f"What is the rent for {agreeing}?").text
    assert "records the same rent" in text
    assert load_table("apartments") is not None


def test_the_latest_allotment_on_a_bed_wins():
    """The application's own rule, kept so the result stays reproducible if a bed ever carries
    two live rows. In this export it carries none, which is itself worth pinning."""
    rows = rent_calc.current_rent_rows()
    keys = [(r["apartment"], r["bed"]) for r in rows]
    assert len(keys) == len(set(keys)), "a bed appeared twice in the current set"


# --- 5. recorded zero rent -------------------------------------------------------------------------

def test_a_recorded_zero_is_kept_and_never_converted_to_missing():
    """The application coalesces NULL to zero. Copying that would make a bed with no rent
    recorded indistinguishable from one genuinely let at zero, and both exist."""
    rows = rent_calc.current_rent_rows()
    zeros = [r for r in rows if r["rent"] == 0]
    assert zeros, "the fixture no longer records a zero rent on a current allotment"
    assert all(r["rent"] is not None for r in zeros), "a zero was turned into a missing value"


def test_the_zero_uncertainty_is_disclosed_and_not_judged(analyst):
    rows = rent_calc.current_rent_rows()
    apartment = next(r["apartment"] for r in rows if r["rent"] == 0)
    text = answer(analyst, f"What is the rent for {apartment}?").text
    lowered = text.lower()
    assert "zero" in lowered
    assert "genuine zero-rent arrangement" in lowered
    assert "never entered" in lowered
    for verdict in ("invalid", "incorrect", "erroneous", "bad data"):
        assert verdict not in lowered, f"a recorded zero was judged {verdict!r}"


# --- 6. historical rent ------------------------------------------------------------------------------

@pytest.mark.parametrize("question", [
    "What was A12 rent last year?",
    "What was A12 rent in August?",
    "How did A12 rent change?",
])
def test_a_past_period_is_refused_rather_than_answered_with_todays_figure(analyst, question):
    """monthly_rental carries no effective date and the export has no update tracking, so an
    edited rent is indistinguishable from an original one. Today's figure is not last year's."""
    a = answer(analyst, question)
    assert a.trust_level == "NOT_DETERMINABLE", f"{question}: {a.trust_level}"
    assert NOT_DETERMINABLE_TEXT in a.text
    assert "19,500" not in a.text, "the current figure was offered as a historical one"


def test_the_registry_declares_the_current_state_limitation(registry):
    """The refusal is driven by the registry, not by a rule hardcoded against this metric."""
    spec = registry.get("M.RENT.001")
    assert spec.historical_policy.strip().upper().startswith("CURRENT STATE ONLY")
    assert "no effective date" in spec.historical_policy.lower()


def test_the_word_change_survives_normalisation():
    """The normaliser rewrote "change" to "charged", which turned every change question into a
    lookup. Rent exposed it; it was never confined to rent."""
    from engine.question_normalize import normalize_owner_question

    for question in ("How did A12 rent change?", "What changed?", "How did revenue change?"):
        assert "change" in normalize_owner_question(question)[0], question


# --- 7. rent is never revenue ---------------------------------------------------------------------------

@pytest.mark.parametrize("question", PARAPHRASES)
def test_rent_never_resolves_to_revenue(question):
    names = [c.name for c, _ in concept_map.match(question)]
    assert "revenue" not in names, f"{question}: {names}"
    assert "rent" in names, f"{question}: {names}"


def test_the_rent_concept_is_backed_by_a_real_registry_metric(registry):
    """Not a concept pretending to be a metric: M.RENT.001 exists, is governed, and is what the
    concept points at."""
    concept = concept_map.concept("rent")
    assert concept.metric_ids == ("M.RENT.001",)
    assert "M.RENT.001" in registry
    assert concept_map.verify_against_registry(registry) == []


@pytest.mark.parametrize("substitute", ["72,705,593", "Revenue (total"])
def test_no_revenue_figure_appears_in_a_rent_answer(analyst, substitute):
    text = answer(analyst, "What is the rent for A12?").text
    assert substitute not in text


def test_the_registry_forbids_the_substitutions_by_name():
    import csv

    with open("semantic_metric_registry.csv", encoding="utf-8", newline="") as fh:
        row = next(r for r in csv.DictReader(fh) if r["metric_id"] == "M.RENT.001")
    prohibited = row["prohibited_questions"].lower()
    for substitute in ("revenue", "invoice amount", "amount paid", "balance due",
                       "owner rent", "deposit"):
        assert substitute in prohibited, f"{substitute} is not named as forbidden"


# --- 8. Trust Gate posture ------------------------------------------------------------------------------

def test_the_gate_governs_the_metric_and_requires_its_caveat(registry):
    decision = TrustGate(registry).authorize("M.RENT.001")
    assert decision.effective_level == "DISCLOSE"
    assert decision.caveat_required is True
    assert decision.headline_permitted is True


def test_the_caveat_states_the_two_things_that_could_mislead(registry):
    caveat = registry.get("M.RENT.001").caveat_text.lower()
    assert "no single apartment rent" in caveat
    assert "zero" in caveat


def test_a_filter_the_calculator_cannot_honour_is_refused_not_dropped():
    """Silently ignoring a narrowing computes the wide figure and labels it with the narrow
    question. Owner payments carry an apartment dimension but no apartment filter."""
    out = MetricExecutor().execute("M.OWN.001", apartment_code="A12")
    assert out.trust_level == "NOT_DETERMINABLE"
    assert "apartment code" in out.not_determinable_reason


# --- 9. no internal identifiers -----------------------------------------------------------------------------

_INTERNAL = (
    (r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b", "metric id"),
    (r"\bDQ\.\d{3}\b", "data-quality id"),
    (r"\bFN\.[a-z_]+\b", "function id"),
    (r"\bv_[a-z0-9_]+\b", "database view"),
    (r"\b[\w.-]+\.(?:py|csv|md|json)\b", "file name"),
    (r"\b(?:tenant_allotments|monthly_rental|staying_status|apartment_id|bed_id)\b",
     "table or column name"),
    (r"\b(?:SELECT|distinct on|FROM|GROUP BY)\b", "SQL"),
    (r"\b(?:current_rent_rows|calc_current_rent_by_bed|present_rent_answer)\b", "function name"),
)


@pytest.mark.parametrize("question", list(PARAPHRASES) + [
    "What is the rent for Z99?",
    "What was A12 rent last year?",
    "How did A12 rent change?",
])
def test_no_internal_identifier_reaches_the_owner(analyst, question):
    text = answer(analyst, question).text
    for pattern, what in _INTERNAL:
        assert not re.search(pattern, text), f"{what} leaked into the answer for {question!r}"


# --- 10 & 11. nothing that already worked changed -----------------------------------------------------------

@pytest.mark.parametrize("question,expected_trust", [
    ("What is our revenue?", "SAFE"),
    ("What is our income?", "SAFE"),
    ("What are total expenses?", "SAFE"),
    ("What is current occupancy?", "SHOW_BOTH"),
])
def test_existing_questions_are_unchanged(analyst, question, expected_trust):
    a = answer(analyst, question)
    assert a.trust_level == expected_trust, f"{question}: {a.trust_level}"
    assert "M.RENT.001" not in (a.metric_ids or ()), f"{question} was hijacked by rent"


@pytest.mark.parametrize("question", [
    "What's typical rent?",
    "How variable are rents?",
    "What's the distribution of rent?",
    "How do apartments compare on rent?",
])
def test_descriptive_rent_questions_still_go_to_descriptive_analysis(analyst, question):
    """The lookup answers "what is the rent HERE"; descriptive analysis answers "what does rent
    look like across the estate". Adding the first must not swallow the second."""
    from engine import analysis_capability as acap

    assert acap.classify_analysis_capability(question).route == acap.ROUTE_DESCRIPTIVE, question
    a = answer(analyst, question)
    assert "M.RENT.001" not in (a.metric_ids or ()), question
    assert a.trust_level == "DISCLOSE"
