"""
test_period_comparison_semantics.py -- the shared period/comparison mechanism.

The bug that prompted these: "if increase revenue this month compare last month" was answered
with June→July, while the same answer admitted August was incomplete. The requested periods
survived the whole pipeline correctly and were then discarded in one place -- the change
detector substituted the latest complete pair and reported it under the original question.

So these tests are written against the CLASS, not the phrase. Three properties, each asserted
across several metric families and several phrasings:

  1. The periods the owner asked for reach the comparison, and are never silently swapped.
  2. An incomplete current period is handled explicitly -- named, disclosed, and offered an
     alternative that is labelled as a different question.
  3. A measured change stays a fact. Only its materiality is unknown.
"""
import re

import pytest

from engine import time_resolution as tr
from engine import owner_presentation as op
from engine import explainability as ex
from engine.change_detection import (ChangeDetector, INCREASE, DECREASE, NO_CHANGE,
                                     UNAVAILABLE, PARTIAL_PERIOD, EXPORT_SNAPSHOT_DATE,
                                     COMPARABLE_MONTHLY_METRICS)
from engine.semantic_registry import SemanticRegistry
from engine.llm_interface import LLMInterface


SNAPSHOT_MONTH = "2026-08"          # incomplete: the export stops on the 29th
LAST_COMPLETE = "2026-07"
PRIOR_COMPLETE = "2026-06"


@pytest.fixture(scope="module")
def registry():
    return SemanticRegistry()


@pytest.fixture(scope="module")
def detector(registry):
    return ChangeDetector(registry=registry)


@pytest.fixture(scope="module")
def iface():
    return LLMInterface()


def ask(iface, question):
    result = iface.ask(question)
    iface.reset()
    return result


# == 1. the requested periods survive =============================================================

# Every phrasing of "the month we are in, against the one before it".
CURRENT_VS_PREVIOUS = [
    "if increase revenue this month compare last month",
    "revenue this month vs last month",
    "did revenue increase this month",
    "current month revenue compared to previous month",
    "this month occupancy compared to last month",
    "this month collections vs last month",
]


@pytest.mark.parametrize("question", CURRENT_VS_PREVIOUS)
def test_current_vs_previous_resolves_to_the_snapshot_month_and_the_one_before(
        question, registry):
    """"This month" is the month the snapshot sits in -- never quietly the last complete one."""
    comparison = tr.resolve_comparison(registry.get("M.REV.002"), question)
    assert comparison.current.start.startswith(SNAPSHOT_MONTH), question
    assert comparison.baseline.start.startswith(LAST_COMPLETE), question


@pytest.mark.parametrize("question,current,baseline", [
    ("August revenue vs July revenue", "2026-08", "2026-07"),
    ("August expenses vs July", "2026-08", "2026-07"),
    ("compare July collections with June", "2026-07", "2026-06"),
    ("September vs March 2025", "2025-09", "2025-03"),
])
def test_an_explicit_month_pair_is_read_in_the_order_it_was_said(
        question, current, baseline, registry):
    """The first month named is the one being asked about; the second is the baseline.

    This used to depend on the order of the month-name table rather than the order of the
    owner's words, so "August vs July" answered July vs June.
    """
    comparison = tr.resolve_comparison(registry.get("M.REV.002"), question)
    assert comparison.current.start.startswith(current), question
    assert comparison.baseline.start.startswith(baseline), question


def test_named_months_are_returned_in_question_order():
    assert tr.named_months("August revenue vs July revenue") == ((2026, 8), (2026, 7))
    assert tr.named_months("July revenue vs August revenue") == ((2026, 7), (2026, 8))
    assert tr.named_months("no month here") == ()
    # The same month twice is one month, not a pair.
    assert len(tr.named_months("sept vs sep")) == 1


def test_a_single_named_month_still_shifts_back_one(registry):
    """Only an explicit PAIR overrides the shift. One month keeps the old behaviour."""
    comparison = tr.resolve_comparison(registry.get("M.REV.002"), "revenue in July")
    assert comparison.current.start.startswith("2026-07")
    assert comparison.baseline.start.startswith("2026-06")


@pytest.mark.parametrize("metric_id", COMPARABLE_MONTHLY_METRICS)
def test_an_explicit_complete_pair_is_compared_as_asked(metric_id, detector):
    """Across every comparable family: ask for two complete months, get those two months."""
    component = {"M.PNL.001": "revenue"}.get(metric_id)
    change = detector.detect(metric_id,
                             current_period=f"{LAST_COMPLETE}-01",
                             previous_period=f"{PRIOR_COMPLETE}-01",
                             series_component=component)
    if change.classification == UNAVAILABLE:
        pytest.skip(f"{metric_id} is not comparable: {change.unavailable_reason[:80]}")
    assert change.current_period.startswith(LAST_COMPLETE)
    assert change.previous_period.startswith(PRIOR_COMPLETE)
    assert change.requested_comparison_met is True


# == 2. an incomplete current period is explicit ==================================================

@pytest.mark.parametrize("metric_id", COMPARABLE_MONTHLY_METRICS)
def test_an_incomplete_current_period_is_never_swapped_for_complete_months(
        metric_id, detector):
    """The core regression. Asking about the snapshot month must NOT return other months."""
    component = {"M.PNL.001": "revenue"}.get(metric_id)
    change = detector.detect(metric_id,
                             current_period=f"{SNAPSHOT_MONTH}-01",
                             previous_period=f"{LAST_COMPLETE}-01",
                             series_component=component)
    if change.classification == UNAVAILABLE:
        pytest.skip(f"{metric_id} is not comparable: {change.unavailable_reason[:80]}")

    assert change.classification == PARTIAL_PERIOD, metric_id
    assert change.detected is False, "a part-month against a whole one is not a measured change"
    assert change.requested_comparison_met is False
    assert change.requested_current.startswith(SNAPSHOT_MONTH)
    assert change.requested_previous.startswith(LAST_COMPLETE)
    # The substituted answer must not appear as the result.
    assert change.absolute_change is None
    assert change.percentage_change is None


def test_the_incomplete_period_is_named_and_disclosed(detector):
    change = detector.detect("M.REV.002", current_period=f"{SNAPSHOT_MONTH}-01",
                             previous_period=f"{LAST_COMPLETE}-01")
    assert SNAPSHOT_MONTH in change.partial_coverage_note
    assert EXPORT_SNAPSHOT_DATE in change.partial_coverage_note
    assert change.current_is_partial is True


def test_the_to_date_figure_is_offered_when_one_exists(detector):
    """The partial month has a real total. Withholding it would be unhelpful; presenting it as
    a monthly figure would be wrong. It is given, labelled as part-month."""
    change = detector.detect("M.REV.002", current_period=f"{SNAPSHOT_MONTH}-01",
                             previous_period=f"{LAST_COMPLETE}-01")
    assert change.partial_current_value is not None
    text = op.present_comparison_answer(change)
    assert "part-month" in text.lower()


def test_the_complete_month_comparison_is_offered_as_a_labelled_alternative(detector):
    change = detector.detect("M.REV.002", current_period=f"{SNAPSHOT_MONTH}-01",
                             previous_period=f"{LAST_COMPLETE}-01")
    alt = change.alternative
    assert alt is not None and alt.detected
    assert alt.current_period.startswith(LAST_COMPLETE)
    assert alt.previous_period.startswith(PRIOR_COMPLETE)

    text = op.present_comparison_answer(change)
    assert "a different question" in text.lower(), (
        "the alternative must be labelled as a different question, not served as the answer")


@pytest.mark.parametrize("question", CURRENT_VS_PREVIOUS)
def test_end_to_end_the_owner_is_never_headlined_a_pair_they_did_not_ask_for(question, iface):
    """The whole pipeline. Whatever the outcome, the FIRST line must not report a comparison
    between months the owner did not name."""
    text = ask(iface, question).text or ""
    assert text.strip(), question
    first_line = text.splitlines()[0].lower()
    # The old failure: a June-to-July headline under a question about this month.
    assert not ("june" in first_line and "july" in first_line), (
        f"{question!r} headlined a substituted pair:\n{first_line}")


def test_a_comparison_on_a_measure_with_no_monthly_series_explains_itself(iface):
    """Occupancy has no month-scoped series, so no answer the owner could give would help.

    They used to get "I couldn't turn that into a well-formed analysis request", which blames
    their phrasing for a limit of the evidence. The honest reason must reach them, and it must
    still carry the exact refusal phrase.
    """
    result = ask(iface, "this month occupancy compared to last month")
    text = result.text or ""
    low = text.lower()
    assert "couldn't turn that into a well-formed" not in low, (
        "a structural evidence gap was reported as a malformed question")
    assert "month-scoped series" in low or "monthly" in low
    assert "Not determinable from exported evidence." in text


def test_a_comparison_on_a_conflicted_family_asks_which_definition(iface):
    """Collections has two competing definitions. Choosing one to compare would be exactly the
    silent resolution the trust policy forbids, so the turn is a question, not a figure."""
    text = (ask(iface, "this month collections vs last month").text or "").lower()
    assert "which definition" in text
    assert "%" not in text, "a comparison was computed on a conflicted family"


def test_a_requested_period_absent_from_the_series_is_refused_not_substituted(detector):
    change = detector.detect("M.REV.002", current_period="2015-01-01",
                             previous_period="2014-12-01")
    assert change.detected is False
    assert change.absolute_change is None


# == 3. a measured change is a fact; only materiality is unknown ==================================

def test_a_measured_change_is_stated_as_a_fact(detector):
    change = detector.detect("M.REV.002", current_period=f"{LAST_COMPLETE}-01",
                             previous_period=f"{PRIOR_COMPLETE}-01")
    assert change.classification in (INCREASE, DECREASE, NO_CHANGE)
    text = op.present_comparison_answer(change)

    assert "increased by" in text.lower() or "decreased by" in text.lower() \
        or "did not change" in text.lower()
    # The figure itself must NOT be described as undeterminable.
    head = text.splitlines()[0]
    assert "not determinable" not in head.lower(), (
        f"the measured change was downgraded to undeterminable:\n{head}")


def test_materiality_is_stated_separately_from_the_change(detector):
    change = detector.detect("M.REV.002", current_period=f"{LAST_COMPLETE}-01",
                             previous_period=f"{PRIOR_COMPLETE}-01")
    text = op.present_comparison_answer(change)
    low = text.lower()
    assert "materially significant cannot be determined" in low
    assert "threshold" in low, "the reason materiality is unknown must be given"
    # It is its own sentence, not a qualifier attached to the figure.
    materiality_line = [ln for ln in text.splitlines() if "materially significant" in ln.lower()]
    assert materiality_line, "materiality is not on its own line"
    assert "increased by" not in materiality_line[0].lower()


def test_the_change_and_its_materiality_are_separate_fields(detector):
    """Represented separately on the object, not only in the prose."""
    change = detector.detect("M.REV.002", current_period=f"{LAST_COMPLETE}-01",
                             previous_period=f"{PRIOR_COMPLETE}-01")
    assert change.absolute_change is not None          # observed_change = known
    assert change.percentage_change is not None        # change_percentage = known
    assert "not determinable" in (change.materiality or "").lower()   # materiality = unknown


# == 4. owner explainability exposes no internals =================================================

INTERNAL = [
    re.compile(r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b"),      # metric IDs
    re.compile(r"\bDQ\.\d{3}\b"),
    re.compile(r"\b[\w.-]+\.(?:md|csv|py|json)\b", re.I),   # spec files, registries, modules
    re.compile(r"\b(?:engine|api|frontend|tests)/", re.I),  # source paths
    re.compile(r"\bGROUP\s+BY\b", re.I),
    re.compile(r"\bSELECT\b[\s\S]{0,80}\bFROM\b", re.I),
    re.compile(r"\b(?:v_[a-z0-9_]+|get_[a-z0-9_]+)\b", re.I),
]

OWNER_QUESTIONS = [
    "How much revenue did we make?",
    "revenue this month vs last month",
    "August revenue vs July revenue",
    "What is our occupancy?",
    "What is our profit?",
]


@pytest.mark.parametrize("question", OWNER_QUESTIONS)
def test_the_owner_projection_exposes_no_internal_identifier(question, iface, registry):
    result = ask(iface, question)
    projection = ex.owner_projection(result, registry=registry,
                                     change=getattr(result, "change", None))
    rendered = ex.render_owner_projection(projection)
    for pattern in INTERNAL:
        assert not pattern.search(rendered), (
            f"{question!r} leaked {pattern.pattern} into the owner view:\n{rendered}")


def test_the_owner_projection_answers_the_owner_question(iface, registry):
    result = ask(iface, "revenue this month vs last month")
    projection = ex.owner_projection(result, registry=registry, change=result.change)

    assert projection.get("definition"), "no plain-language definition"
    assert projection.get("evidence"), "no statement of what the figure came from"
    assert "August 2026" in projection.get("period", ""), "the requested period is not named"
    assert projection.get("trust"), "no trust posture"
    assert "incomplete" in projection.get("limitation", "").lower()


def test_the_technical_chain_keeps_its_identifiers(iface):
    """The audit record is unchanged -- only the owner projection drops identifiers.

    Nothing here asserts chain completeness: `build()` is called without role routing, which
    legitimately leaves the lens link empty. What matters is that the technical lineage the
    owner no longer sees is still recorded for audit.
    """
    result = ask(iface, "How much revenue did we make?")
    chain = ex.build(result)
    joined = " ".join(f"{l.content} {l.source}" for l in chain.links)
    assert "M.REV" in joined, "the audit chain no longer names the measure it used"
    assert any(src.endswith(".csv") or src.endswith(".py") or ".md" in src
               for src in (l.source for l in chain.links)), (
        "the audit chain no longer cites where each step came from")


# == 5. the same mechanism, reached through Tamil-English =========================================
#
# These go through the SAME normaliser and the SAME period layer. The point is not that Tamil
# is special-cased but that it is not: once "intha" becomes "this", every guarantee above holds
# unchanged. A separate code path for these would be the failure.

TANGLISH = [
    ("intha month revenue last month compare", "2026-08", "2026-07"),
    ("revenue intha month vs last month", "2026-08", "2026-07"),
    ("intha month revenue koranjucha", "2026-08", "2026-07"),
    ("intha month revenue evlo", "2026-08", "2026-07"),
]


@pytest.mark.parametrize("question,current,baseline", TANGLISH)
def test_tamil_english_reaches_the_same_period_resolution(question, current, baseline, registry):
    from engine.question_normalize import normalize_owner_question
    normalized, _ = normalize_owner_question(question)
    comparison = tr.resolve_comparison(registry.get("M.REV.002"), normalized)
    assert comparison.current.start.startswith(current), question
    assert comparison.baseline.start.startswith(baseline), question


@pytest.mark.parametrize("question,_c,_b", TANGLISH)
def test_tamil_english_is_never_headlined_a_substituted_pair(question, _c, _b, iface):
    text = ask(iface, question).text or ""
    assert text.strip(), question
    first_line = text.splitlines()[0].lower()
    assert not ("june" in first_line and "july" in first_line), (
        f"{question!r} headlined a substituted pair:\n{first_line}")


# == 6. incomplete-period behaviour, stated exactly ===============================================

def test_the_snapshot_month_is_treated_as_incomplete_everywhere():
    """One definition of "complete" governs the whole layer."""
    from engine.change_detection import _complete_months
    kept, dropped = _complete_months(
        ["2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"])
    assert "2026-08-01" in dropped, "the snapshot month was treated as whole"
    assert "2026-09-01" in dropped, "a month beyond the snapshot was treated as whole"
    assert kept == ["2026-06-01", "2026-07-01"]


def test_a_default_comparison_still_uses_the_latest_complete_pair(detector):
    """With NO period requested, the latest two whole months remain the right default. The fix
    removed silent SUBSTITUTION, not the default."""
    change = detector.detect("M.REV.002")
    assert change.detected
    assert change.current_period.startswith(LAST_COMPLETE)
    assert change.previous_period.startswith(PRIOR_COMPLETE)
    assert change.requested_comparison_met is True


def test_a_complete_requested_period_is_not_flagged_partial(detector):
    change = detector.detect("M.REV.002", current_period=f"{LAST_COMPLETE}-01",
                             previous_period=f"{PRIOR_COMPLETE}-01")
    assert change.current_is_partial is False
    assert change.classification != PARTIAL_PERIOD
    assert change.alternative is None
