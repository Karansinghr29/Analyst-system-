"""
Phase 6: the "What changed?" engine.

The rule that shapes every test here (Phase 6 brief 4):
    "But do NOT invent materiality thresholds. If materiality threshold is not defined, state
     that it is unavailable rather than inventing one."

So the engine reports direction and size, and refuses to say whether a change matters.
"""
import pytest

from engine.change_detection import (ChangeDetector, ladder_for, INCREASE, DECREASE, NO_CHANGE,
                                     UNAVAILABLE, MATERIALITY_UNDEFINED,
                                     COMPARABLE_MONTHLY_METRICS, EXPORT_SNAPSHOT_DATE,
                                     _complete_months)
from engine.result import NOT_DETERMINABLE_TEXT

_CACHE = {}


@pytest.fixture(scope="module")
def detector(registry):
    return ChangeDetector(registry=registry)


@pytest.fixture(scope="module")
def changes(detector):
    if "c" not in _CACHE:
        _CACHE["c"] = detector.detect_all()
    return _CACHE["c"]


class TestMaterialityIsNeverInvented:
    def test_every_change_declares_materiality_undefined(self, changes):
        for c in changes:
            assert c.materiality == MATERIALITY_UNDEFINED
            assert NOT_DETERMINABLE_TEXT in c.materiality

    def test_materiality_cites_the_specification_that_declines_to_fix_it(self):
        assert "insight_generation_spec.md" in MATERIALITY_UNDEFINED

    def test_there_is_no_immaterial_classification(self):
        """Calling a change immaterial requires the threshold that does not exist, so the
        vocabulary deliberately has no such value."""
        from engine import change_detection as cd
        vocab = {cd.INCREASE, cd.DECREASE, cd.NO_CHANGE, cd.UNAVAILABLE}
        assert not any("MATERIAL" in v or "MINOR" in v or "SIGNIFICANT" in v for v in vocab)

    def test_no_change_means_exact_equality_only(self, detector, registry):
        """NO_CHANGE is arithmetic, never a judgement that a small change did not matter."""
        c = detector.detect("M.REV.002")
        if c.classification == NO_CHANGE:
            assert c.absolute_change == 0


class TestIncompletePeriodsAreExcluded:
    """The export snapshot is mid-month, so the final period is only partially captured.
    Comparing a partial month against a complete one manufactures a dramatic false signal."""

    def test_partial_months_are_dropped(self):
        keep, dropped = _complete_months(["2026-06-01", "2026-07-01", "2026-08-01",
                                          "2026-09-01"])
        assert "2026-09-01" in dropped
        assert "2026-08-01" in dropped, (
            f"2026-08 ends after the snapshot {EXPORT_SNAPSHOT_DATE} and is incomplete")
        assert keep == ["2026-06-01", "2026-07-01"]

    def test_complete_months_survive(self):
        keep, dropped = _complete_months(["2025-01-01", "2025-02-01"])
        assert dropped == []
        assert len(keep) == 2

    def test_revenue_comparison_uses_complete_periods(self, detector):
        c = detector.detect("M.REV.002")
        assert c.current_period <= "2026-07-01", (
            "a partial period was compared; this previously produced a spurious -99.86% "
            "'revenue collapse' that is an artifact of the export cut-off, not a business event")

    def test_the_exclusion_is_disclosed(self, changes):
        excluded = [c for c in changes if "excluded as incomplete" in c.coverage_note]
        assert excluded, "periods were dropped without saying so"


class TestChangeClassification:
    def test_every_comparable_metric_is_classified(self, changes):
        assert len(changes) == len(COMPARABLE_MONTHLY_METRICS)
        for c in changes:
            assert c.classification in (INCREASE, DECREASE, NO_CHANGE, UNAVAILABLE)

    def test_unavailable_changes_state_their_reason(self, changes):
        for c in changes:
            if c.classification == UNAVAILABLE:
                assert c.unavailable_reason.strip(), f"{c.metric_id}: unavailable with no reason"

    def test_unavailable_metrics_are_reported_not_dropped(self, changes):
        """Dropping them would let a briefing read as 'nothing changed here'."""
        ids = {c.metric_id for c in changes}
        assert set(COMPARABLE_MONTHLY_METRICS) <= ids

    def test_a_detected_change_carries_both_periods_and_the_delta(self, changes):
        for c in changes:
            if c.detected:
                assert c.current_period and c.previous_period
                assert c.absolute_change is not None

    def test_conflicted_metrics_are_never_compared(self, detector):
        """Comparing periods on a SHOW_BOTH/BLOCK metric would require choosing one definition
        -- the silent resolution the trust policy forbids."""
        for mid in ("M.PROFIT.001", "M.OCC.001", "M.AR.001A"):
            c = detector.detect(mid)
            assert c.classification == UNAVAILABLE, mid
            assert "Conflicting definitions exist." in c.unavailable_reason

    def test_composite_monthly_values_are_not_reduced_to_one_component(self, detector):
        """M.PNL.001's monthly value is a dict; picking one component as 'the' change would be
        a definition decision this layer may not make."""
        c = detector.detect("M.PNL.001")
        assert c.classification == UNAVAILABLE
        assert "composite" in c.unavailable_reason

    def test_unknown_metric_is_unavailable_not_an_error(self, detector):
        c = detector.detect("M.NOPE.001")
        assert c.classification == UNAVAILABLE
        assert NOT_DETERMINABLE_TEXT in c.unavailable_reason

    def test_detection_is_deterministic(self, detector):
        a = detector.detect_all()
        b = detector.detect_all()
        assert [(c.metric_id, c.classification, c.absolute_change) for c in a] == \
               [(c.metric_id, c.classification, c.absolute_change) for c in b]


class TestChangeLadder:
    """business_reasoning_spec.md's chain, and where it must stop."""

    def test_a_detected_change_produces_fact_calculation_observation(self, detector):
        c = detector.detect("M.REV.002")
        if not c.detected:
            pytest.skip("no comparable change")
        l = ladder_for(c)
        assert l["FACT"] and l["CALCULATION"] and l["OBSERVATION"]

    def test_the_ladder_stops_before_asserting_a_cause(self, detector):
        """Naming a cause requires driver analysis; asserting one here would be the unsupported
        causal claim the specification forbids."""
        c = detector.detect("M.REV.002")
        l = ladder_for(c)
        assert "HYPOTHESIS" not in l
        assert "RECOMMENDATION" not in l
        for text in (l.get("OBSERVATION", ""), l.get("CALCULATION", "")):
            assert "because" not in text.lower()
            assert "caused by" not in text.lower()

    def test_the_ladder_carries_the_materiality_disclaimer(self, detector):
        c = detector.detect("M.REV.002")
        assert NOT_DETERMINABLE_TEXT in ladder_for(c)["materiality"]

    def test_summary_buckets_every_metric(self, detector, changes):
        s = detector.summary(changes)
        total = sum(len(v) for v in s.values())
        assert total == len(changes)
