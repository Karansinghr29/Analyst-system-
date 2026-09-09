"""
Phase 6: the "Why?" engine.

The boundary under test is epistemic, not computational (Phase 6 brief 5):
    "Do not hallucinate causes. Separate: proven fact / calculated relationship / observed
     pattern / inference / hypothesis. If causal evidence does not exist, explicitly say
     correlation/pattern only."

The exported evidence contains no experiment and no control, so nothing here may assert that one
metric CAUSED another to move.
"""
import pytest

from engine.root_cause import (RootCauseAnalyzer, unsupported_causal_claim, CAUSAL_DISCLAIMER,
                               PATTERN_ONLY, EDGE_ONLY, NO_EDGE)
from engine import business_reasoning
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture(scope="module")
def analyzer(registry):
    return RootCauseAnalyzer(registry=registry)


WHY_QUESTIONS = ["M.REV.002", "M.PNL.001", "M.COL.002", "M.PROFIT.001", "M.AR.001A",
                 "M.OCC.001", "M.EXP.001", "M.DEP.002"]


class TestNoHallucinatedCauses:
    @pytest.mark.parametrize("metric_id", WHY_QUESTIONS)
    def test_no_statement_asserts_a_cause(self, analyzer, metric_id):
        a = analyzer.analyze(metric_id)
        for s in a.statements:
            offending = unsupported_causal_claim(s.text)
            assert not offending, f"{metric_id}/{s.stage}: asserted a cause ({offending!r})"

    def test_every_driver_carries_the_causal_disclaimer(self, analyzer):
        a = analyzer.analyze("M.PNL.001")
        for d in a.drivers:
            if d.status == PATTERN_ONLY:
                assert CAUSAL_DISCLAIMER in d.note

    def test_the_disclaimer_says_correlation_not_cause(self):
        assert "not a demonstrated cause" in CAUSAL_DISCLAIMER
        assert "no experiment or control" in CAUSAL_DISCLAIMER

    def test_hypotheses_use_hedge_language(self, analyzer):
        for mid in WHY_QUESTIONS:
            a = analyzer.analyze(mid)
            for s in a.statements:
                if s.stage == business_reasoning.HYPOTHESIS:
                    assert any(h in s.text.lower()
                               for h in business_reasoning.HEDGE_PHRASES), f"{mid}: {s.text[:80]}"
                    assert s.confidence == business_reasoning.SUSPECTED


class TestDocumentedEdgesOnly:
    """analytics_execution_spec.md 2.6: decomposition uses metric_dependency_graph.md's
    documented edges, "never into an undocumented ad-hoc decomposition"."""

    @pytest.mark.parametrize("metric_id", WHY_QUESTIONS)
    def test_every_driver_is_a_documented_dependency(self, analyzer, registry, metric_id):
        a = analyzer.analyze(metric_id)
        documented = set(registry.get(metric_id).dependency_metrics)
        for d in a.drivers:
            assert d.metric_id in documented, (
                f"{metric_id}: {d.metric_id} is not a documented dependency")

    def test_every_driver_cites_where_the_edge_is_documented(self, analyzer):
        a = analyzer.analyze("M.PROFIT.001")
        for d in a.drivers:
            assert "metric_dependency_graph.md" in d.edge_source

    def test_a_metric_with_no_edges_says_so(self, analyzer):
        a = analyzer.analyze("M.REV.001")
        assert not a.drivers
        assert any("documents no dependency edge" in l for l in a.limitations)
        assert any(NOT_DETERMINABLE_TEXT in l for l in a.limitations)

    def test_an_edge_without_a_comparison_is_reported_not_dropped(self, analyzer):
        a = analyzer.analyze("M.PROFIT.001")
        edge_only = [d for d in a.drivers if d.status == EDGE_ONLY]
        for d in edge_only:
            assert d.note.strip()


class TestConflictedTargets:
    """2.6: a conflicted target decomposes PER DEFINITION and is never merged."""

    def test_block_target_decomposes_per_definition(self, analyzer):
        a = analyzer.analyze("M.PROFIT.001")
        assert a.trust_level == "BLOCK"
        assert a.per_definition, "a BLOCK target produced no per-definition decomposition"

    def test_conflicted_target_states_the_no_merge_rule(self, analyzer):
        for mid in ("M.PROFIT.001", "M.AR.001A", "M.OCC.001"):
            a = analyzer.analyze(mid)
            joined = " ".join(a.limitations)
            assert "per definition" in joined.lower()
            assert "Conflicting definitions exist." in joined

    def test_ar_family_decomposes_across_all_four(self, analyzer):
        a = analyzer.analyze("M.AR.001A")
        assert len(a.per_definition) == 4


class TestEpistemicLadder:
    def test_statements_are_ordered_up_the_ladder(self, analyzer):
        a = analyzer.analyze("M.PNL.001")
        rungs = [business_reasoning.LADDER.index(s.stage) for s in a.statements]
        assert rungs == sorted(rungs), "the ladder was climbed out of order"

    def test_no_recommendation_is_emitted_unasked(self, analyzer):
        """business_reasoning_spec.md 3: a driver question's ceiling is HYPOTHESIS."""
        for mid in WHY_QUESTIONS:
            a = analyzer.analyze(mid)
            stages = {s.stage for s in a.statements}
            assert business_reasoning.RECOMMENDATION not in stages, mid

    def test_inference_is_labelled_proven_only_when_the_edge_is_documented(self, analyzer):
        a = analyzer.analyze("M.PNL.001")
        for s in a.statements:
            if s.stage == business_reasoning.INFERENCE:
                assert s.confidence == business_reasoning.PROVEN
                assert "documented" in s.text.lower()

    def test_worst_of_inputs_holds_for_inference(self, analyzer, registry):
        from engine.gate import TrustGate
        gate = TrustGate(registry)
        sev = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}
        a = analyzer.analyze("M.PNL.001")
        for s in a.statements:
            if s.stage == business_reasoning.INFERENCE and s.metric_ids:
                worst = max((gate.authorize(m).effective_level for m in s.metric_ids
                             if m in registry), key=lambda lv: sev[lv], default="SAFE")
                assert sev[s.trust_level] >= sev[worst]


class TestUnknownAndUndeterminable:
    def test_unknown_metric_is_not_determinable(self, analyzer):
        a = analyzer.analyze("M.NOPE.001")
        assert not a.determinable
        assert NOT_DETERMINABLE_TEXT in a.not_determinable_reason

    def test_analysis_is_deterministic(self, analyzer):
        a = analyzer.analyze("M.PNL.001")
        b = analyzer.analyze("M.PNL.001")
        assert [(s.stage, s.text) for s in a.statements] == \
               [(s.stage, s.text) for s in b.statements]

    def test_guard_detects_a_causal_claim(self):
        assert unsupported_causal_claim("Revenue fell because of the owner rent posting")
        assert unsupported_causal_claim("This is caused by duplicate invoices")
        assert not unsupported_causal_claim(
            "The movement is consistent with the change and would explain part of it")
