"""
Phase 5: proactive insight generation, trust propagation, recommendation ceilings, conflict
preservation, and ranking determinism.

The rule that constrains everything here (insight_generation_spec.md 1):
    "an insight is not a different KIND of output, it is an answer the system generated without
     being asked, and it must satisfy every requirement a reactive answer does."

So every trust rule the reactive path enforces applies unchanged: no BLOCK headline, no
collapsed SHOW_BOTH, no invented threshold, no recommendation stronger than its evidence.
"""
import pytest

from engine import insight_ranker
from engine.insight_engine import InsightEngine, PROACTIVE_SEVERITIES, RISK_BOUNDARY_METRICS
from engine.insight_models import (
    ALL_TRIGGERS, ALL_CLASSES, UNSPECIFIED_TRIGGERS, NOT_DETERMINABLE_TEXT,
    TRIGGER_ANOMALY, TRIGGER_MATERIAL_DELTA, TRIGGER_DQ_SEVERITY,
    TRIGGER_DEFINITION_CONFLICT, TRIGGER_RISK_BOUNDARY, classify_area,
)
from engine import business_reasoning

_CACHE = {}


@pytest.fixture(scope="module")
def engine(registry):
    return InsightEngine(registry=registry)


@pytest.fixture(scope="module")
def insights(engine):
    if "insights" not in _CACHE:
        _CACHE["insights"] = engine.generate()
    return _CACHE["insights"]


class TestInsightGeneration:
    def test_insights_are_generated(self, insights):
        assert len(insights) > 0

    def test_every_insight_reaches_observation(self, insights):
        """insight_generation_spec.md 3: 'A candidate must reach at minimum the OBSERVATION
        stage -- a bare FACT/CALCULATION is not yet an insight.'"""
        for i in insights:
            assert i.reached_observation, f"{i.insight_id} never reached OBSERVATION"

    def test_every_insight_carries_the_required_fields(self, insights):
        """The Phase 5 brief's own required field list."""
        for i in insights:
            assert i.insight_id
            assert i.trigger in ALL_TRIGGERS
            assert i.insight_class in ALL_CLASSES
            assert i.trigger_metric_ids or i.dq_ids, f"{i.insight_id}: no trigger provenance"
            assert i.trust_level, f"{i.insight_id}: no trust level"
            assert i.confidence, f"{i.insight_id}: no confidence"
            assert i.time_period, f"{i.insight_id}: no time period"
            assert i.business_dimension, f"{i.insight_id}: no business dimension"

    def test_every_insight_cites_evidence(self, insights):
        for i in insights:
            assert i.evidence_sources or i.dq_ids or i.conflict_ids, (
                f"{i.insight_id}: no traceable evidence -- ai_agent_roles.md forbids surfacing "
                f"an insight without a metric_id/evidence chain")

    def test_every_trigger_metric_resolves_to_the_registry(self, insights, registry):
        for i in insights:
            for mid in i.trigger_metric_ids:
                assert mid in registry, f"{i.insight_id} cites unknown metric {mid}"

    def test_insight_ids_are_unique(self, insights):
        ids = [i.insight_id for i in insights]
        assert len(ids) == len(set(ids))

    def test_dq_insights_come_only_from_critical_and_high(self, engine, insights):
        """2 condition 1. A LOW/INFORMATIONAL finding must not be surfaced proactively --
        ai_agent_roles.md: 'Must never ... manufacture urgency for a LOW/INFORMATIONAL-severity
        finding.'"""
        dq_by_id = {r["dq_id"]: r for r in engine.dq_rows}
        for i in insights:
            if i.trigger != TRIGGER_DQ_SEVERITY:
                continue
            for dq in i.dq_ids:
                if dq in dq_by_id:
                    assert dq_by_id[dq]["severity"].upper() in PROACTIVE_SEVERITIES, (
                        f"{i.insight_id} surfaced a {dq_by_id[dq]['severity']} finding")

    def test_all_critical_and_high_findings_are_candidates(self, engine, insights):
        """insight_generation_spec.md 2: 'Each is a standing candidate.' A CRITICAL finding that
        silently failed to become one would be a false negative in the risk scan."""
        surfaced = {dq for i in insights for dq in i.dq_ids}
        expected = {r["dq_id"] for r in engine.dq_rows
                    if r["severity"].upper() in PROACTIVE_SEVERITIES}
        missing = expected - surfaced
        assert not missing, f"CRITICAL/HIGH findings not surfaced: {sorted(missing)}"


class TestUnimplementableTriggers:
    """Two of the four triggers have no threshold anywhere in the evidence or the specs. The
    engine must report that, not invent a cutoff and not report zero findings as if it had
    looked."""

    def test_anomaly_and_material_delta_are_declared_unsupported(self):
        unsupported = InsightEngine.unsupported_triggers()
        assert TRIGGER_ANOMALY in unsupported
        assert TRIGGER_MATERIAL_DELTA in unsupported

    def test_each_unsupported_trigger_uses_the_exact_phrase(self):
        for trigger, reason in UNSPECIFIED_TRIGGERS.items():
            assert NOT_DETERMINABLE_TEXT in reason, trigger

    def test_each_unsupported_trigger_quotes_its_specification(self):
        """The reason must cite the document that declines to fix the threshold, so a reader can
        confirm the gap is the specification's and not this implementation's."""
        assert "analytics_execution_spec.md" in UNSPECIFIED_TRIGGERS[TRIGGER_ANOMALY]
        assert "insight_generation_spec.md" in UNSPECIFIED_TRIGGERS[TRIGGER_MATERIAL_DELTA]

    def test_no_insight_fires_on_an_invented_threshold(self, insights):
        for i in insights:
            assert i.trigger not in (TRIGGER_ANOMALY, TRIGGER_MATERIAL_DELTA), (
                f"{i.insight_id} fired a trigger whose threshold does not exist in evidence")


class TestInsightTrustPropagation:
    def test_no_insight_exposes_a_block_headline(self, insights):
        for i in insights:
            if i.trust_level == "BLOCK":
                assert i.headline_permitted is False, f"{i.insight_id} allowed a BLOCK headline"

    def test_show_both_insights_never_assert_one_figure(self, insights):
        """5: a conflicted metric 'may generate an insight about the CONFLICT itself, never one
        asserting a competing figure as the business's actual position.'"""
        for i in insights:
            if i.trust_level in ("SHOW_BOTH", "BLOCK"):
                assert i.headline_permitted is False
                assert i.conflict_ids or i.dq_ids, (
                    f"{i.insight_id}: conflicted insight with nothing disclosed")

    def test_conflict_insights_preserve_every_definition(self, insights, registry):
        conflict = [i for i in insights if i.trigger == TRIGGER_DEFINITION_CONFLICT]
        assert conflict, "no definition-conflict insight was generated"
        for i in conflict:
            assert i.trust_level in ("SHOW_BOTH", "BLOCK")
            assert "do not agree" in i.observation.lower() or "disagree" in i.observation.lower()

    def test_trust_level_matches_the_gate(self, insights, registry):
        """The insight path must not compute its own trust posture."""
        from engine.gate import TrustGate
        gate = TrustGate(registry)
        sev = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}
        for i in insights:
            if not i.trigger_metric_ids:
                continue
            worst = max((gate.authorize(m).effective_level for m in i.trigger_metric_ids
                         if m in registry), key=lambda lv: sev[lv], default="SAFE")
            assert sev[i.trust_level] >= sev[worst], (
                f"{i.insight_id} claims {i.trust_level}, weaker than its inputs' {worst}")

    def test_disclose_insights_carry_a_caveat(self, insights):
        for i in insights:
            if i.trust_level == "DISCLOSE":
                assert i.caveat.strip(), f"{i.insight_id}: DISCLOSE without a caveat"


class TestRecommendationCeilings:
    """business_reasoning_spec.md 2. A recommendation must never be stronger than its evidence."""

    def test_no_insight_jumps_fact_to_recommendation(self, insights):
        """The brief: 'The system must never jump FACT -> RECOMMENDATION without the
        intermediate evidence chain.'"""
        for i in insights:
            if i.recommendation.strip():
                assert i.observation.strip(), (
                    f"{i.insight_id} recommends without an OBSERVATION")

    def test_every_recommendation_is_in_recommendation_register(self, insights):
        for i in insights:
            if i.recommendation.strip():
                assert "recommend" in i.recommendation.lower(), (
                    f"{i.insight_id}: recommendation not phrased as one")

    def test_no_recommendation_uses_fact_register(self, insights):
        for i in insights:
            text = i.recommendation.lower()
            for phrase in business_reasoning.FACT_REGISTER_PHRASES:
                assert phrase not in text, f"{i.insight_id}: fact register in a recommendation"

    def test_hypotheses_use_hedge_language(self, insights):
        for i in insights:
            if i.hypothesis.strip():
                assert any(h in i.hypothesis.lower()
                           for h in business_reasoning.HEDGE_PHRASES), (
                    f"{i.insight_id}: HYPOTHESIS without hedge language")

    def test_block_recommendations_recommend_resolving_the_conflict(self, insights):
        """2's most important gating rule: a recommendation touching a BLOCK metric must
        recommend resolving the conflict, never an action on a disputed figure."""
        for i in insights:
            if i.trust_level == "BLOCK" and i.recommendation.strip():
                low = i.recommendation.lower()
                assert any(w in low for w in ("resolv", "decision", "which definition",
                                              "authoritative", "reconcil")), (
                    f"{i.insight_id}: BLOCK recommendation does not address the conflict: "
                    f"{i.recommendation[:120]}")

    def test_confidence_uses_the_documented_vocabulary(self, insights):
        """answer_contract.md 3 / data_quality_report.md's root_cause_confidence column --
        never a numeric percentage."""
        for i in insights:
            assert not i.confidence.strip().rstrip("%").replace(".", "").isdigit(), (
                f"{i.insight_id}: numeric confidence")


class TestInsightRanking:
    def test_ranking_is_deterministic(self, engine):
        a = engine.generate()
        b = engine.generate()
        assert [i.insight_id for i in a] == [i.insight_id for i in b]

    def test_ranking_has_no_blended_score(self, insights):
        """insight_generation_spec.md 4 forbids one explicitly."""
        for i in insights:
            assert not hasattr(i.ranking, "score")
            assert not hasattr(i.ranking, "importance")

    def test_explain_ranking_returns_dimensions_separately(self, insights):
        e = insight_ranker.explain_ranking(insights[0])
        assert "1_trust_adjusted_severity" in e
        assert "2_recency" in e
        assert "3_materiality" in e
        assert "4_coverage_sufficient" in e
        assert all(not isinstance(v, float) or k != "score" for k, v in e.items())

    def test_critical_outranks_high(self, engine, insights):
        dq_by_id = {r["dq_id"]: r for r in engine.dq_rows}
        seen_high = False
        for i in insights:
            sevs = [dq_by_id[d]["severity"].upper() for d in i.dq_ids if d in dq_by_id]
            if not sevs:
                continue
            if "HIGH" in sevs and "CRITICAL" not in sevs:
                seen_high = True
            elif "CRITICAL" in sevs and seen_high:
                # A CRITICAL may legitimately sort after a HIGH only via the documented
                # already-disclosed demotion, never arbitrarily.
                assert i.trust_level in ("SHOW_BOTH", "BLOCK"), (
                    f"{i.insight_id}: CRITICAL ranked below HIGH without the documented "
                    f"already-disclosed demotion")

    def test_missing_materiality_sorts_last_not_as_zero(self):
        """'absence of a figure is not smallness' -- an insight with no determinable amount must
        not outrank one with a real amount in the same tier."""
        from engine.insight_models import RankingDimensions
        with_amount = RankingDimensions(trust_adjusted_severity=0, recency=0,
                                        materiality_amount=1000.0)
        without = RankingDimensions(trust_adjusted_severity=0, recency=0,
                                    materiality_amount=None)
        assert with_amount.sort_key() < without.sort_key()

    def test_group_by_dimension_preserves_separation(self, insights):
        groups = insight_ranker.group_by_dimension(insights)
        assert groups
        assert sum(len(v) for v in groups.values()) == len(insights)


class TestRiskBoundaryTrigger:
    def test_risk_boundary_metrics_are_the_documented_ones(self):
        for m in RISK_BOUNDARY_METRICS:
            assert m.startswith("M.RISK.")

    def test_boundary_insights_introduce_no_threshold(self, insights):
        """2 condition 4: the diagnostic's own definition IS the boundary, so a non-empty
        result set is the crossing. No cutoff is added."""
        for i in insights:
            if i.trigger == TRIGGER_RISK_BOUNDARY:
                assert i.affected_count is not None or i.affected_amount is not None, (
                    f"{i.insight_id}: boundary insight with nothing quantified")


class TestAreaClassification:
    def test_every_class_is_documented(self, insights):
        for i in insights:
            assert i.insight_class in ALL_CLASSES

    def test_unknown_area_falls_back_rather_than_dropping(self):
        assert classify_area("something entirely unmapped") in ALL_CLASSES
        assert classify_area("") in ALL_CLASSES
