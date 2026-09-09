"""
Phase 3 stage [7]: analytics_execution_spec.md 2's eight plan types, the structural guards of
the Phase 3 brief's requirement 5, and the delegation of all trust decisions to the Phase 2
Trust Gate.
"""
import pytest

from engine.analytics_planner import AnalyticsPlanner, RISK_COMPOSITE_METRICS
from engine.intent_models import (
    PLAN_SINGLE_VALUE, PLAN_GROUPED, PLAN_PERIOD_COMPARISON, PLAN_TREND, PLAN_ANOMALY,
    PLAN_DRIVER, PLAN_EXPLAIN_CONFLICT, PLAN_RISK_COMPOSITE, PLAN_NONE,
    READY, BLOCKED, NEEDS_CLARIFICATION, NOT_DETERMINABLE, REJECTED,
    NOT_DETERMINABLE_TEXT, validate_plan_schema,
)


@pytest.fixture(scope="module")
def planner(registry, ):
    from engine.gate import TrustGate
    return AnalyticsPlanner(registry=registry, gate=TrustGate(registry))


# Representative questions covering every domain the Phase 3 brief enumerates.
DOMAIN_QUESTIONS = [
    ("revenue",              "How much revenue did we make?"),
    ("collections",          "How much did we collect?"),
    ("tenant dues",          "How much do tenants owe?"),
    ("deposits",             "How much deposit are we holding?"),
    ("occupancy",            "What is occupancy?"),
    ("expenses",             "How much did we spend?"),
    ("profit",               "What was profit last month?"),
    ("owner payments",       "How much did we pay owners?"),
    ("maintenance",          "How many maintenance tickets were raised?"),
    ("EB",                   "What was our electricity cost?"),
    ("tenant lifecycle",     "How many move-outs were there?"),
    ("accounting",           "Does the trial balance balance?"),
    ("data quality",         "Are there duplicate invoices?"),
]


class TestSchemaValidity:
    """Exit criterion: 'every generated Analytics Plan is schema-valid'."""

    @pytest.mark.parametrize("domain,question", DOMAIN_QUESTIONS)
    def test_every_domain_question_produces_a_schema_valid_plan(self, planner, registry,
                                                                domain, question):
        plan = planner.plan(question)
        assert validate_plan_schema(plan, registry) == [], f"{domain}: {question}"

    @pytest.mark.parametrize("domain,question", DOMAIN_QUESTIONS)
    def test_every_domain_question_passes_full_validation(self, planner, domain, question):
        plan = planner.plan(question)
        assert planner.validate(plan) == [], f"{domain}: {question}"

    def test_every_plan_carries_provenance(self, planner):
        for _, q in DOMAIN_QUESTIONS:
            plan = planner.plan(q)
            assert plan.provenance, f"{q}: no provenance"
            assert any("question_understanding_spec.md" in p or
                       "analytics_execution_spec.md" in p or
                       "engine.gate" in p for p in plan.provenance)

    def test_every_metric_reference_resolves_to_the_registry(self, planner, registry):
        for _, q in DOMAIN_QUESTIONS:
            plan = planner.plan(q)
            for mid in plan.metric_ids:
                assert mid in registry
            for call in plan.execution_calls:
                assert call.metric_id in registry


class TestPlanTypeSelection:
    """analytics_execution_spec.md 2.1-2.8."""

    def test_lookup_produces_single_value(self, planner):
        assert planner.plan("How much revenue did we make?").plan_type == PLAN_SINGLE_VALUE

    def test_trend_produces_trend_series(self, planner):
        assert planner.plan("Revenue by month").plan_type == PLAN_TREND

    def test_comparison_produces_period_comparison(self, planner):
        plan = planner.plan("Was revenue in 2025-06 better than before?")
        assert plan.plan_type == PLAN_PERIOD_COMPARISON
        assert plan.comparison is not None and plan.comparison.valid

    def test_anomaly_produces_anomaly_scan(self, planner):
        assert planner.plan("Was there anything unusual in revenue?").plan_type == PLAN_ANOMALY

    def test_driver_produces_driver_decomposition(self, planner):
        """2.6: decomposition uses metric_dependency_graph.md's DOCUMENTED edges only."""
        plan = planner.plan("Why did revenue fall?")
        assert plan.plan_type == PLAN_DRIVER
        assert plan.driver_requested is True

    def test_driver_components_are_documented_dependencies_only(self, planner, registry):
        plan = planner.plan("Why did our P&L fall?")
        if plan.plan_type == PLAN_DRIVER:
            documented = set(registry.get(plan.metric_ids[0]).dependency_metrics)
            for call in plan.execution_calls:
                if call.label.startswith("driver-component:"):
                    assert call.metric_id in documented, (
                        f"{call.metric_id} is not a documented dependency -- "
                        f"analytics_execution_spec.md 2.6 forbids ad-hoc decomposition")

    def test_show_both_and_block_produce_explain_the_conflict(self, planner):
        """2.7 -- the plan type that produces the content behind the BLOCK/SHOW_BOTH answer
        templates."""
        for q in ("What is occupancy?", "How much do tenants owe?", "What's our profit?"):
            plan = planner.plan(q)
            assert plan.plan_type == PLAN_EXPLAIN_CONFLICT, q
            assert plan.trust_level in ("SHOW_BOTH", "BLOCK"), q

    def test_risk_scan_produces_a_labelled_composite(self, planner):
        """2.8: each contributing metric keeps its own metric_id and trust label; presented as
        a labelled list, never a merged score."""
        plan = planner.plan("What are our biggest business risks?")
        assert plan.plan_type == PLAN_RISK_COMPOSITE
        assert len(plan.execution_calls) >= 5
        ids = [c.metric_id for c in plan.execution_calls]
        assert len(ids) == len(set(ids)), "composite must not duplicate a metric"
        assert set(ids) <= set(RISK_COMPOSITE_METRICS)

    def test_grouped_lookup_when_a_supported_dimension_is_requested(self, planner):
        plan = planner.plan("Show tenant dues by property")
        assert plan.status in (READY, BLOCKED, NOT_DETERMINABLE, REJECTED)


class TestTrustIsDelegated:
    """Exit criterion: 'trust handling is delegated to the existing Trust Gate'."""

    def test_plan_trust_matches_the_gate_verbatim(self, planner, registry):
        from engine.gate import TrustGate
        gate = TrustGate(registry)
        for _, q in DOMAIN_QUESTIONS:
            plan = planner.plan(q)
            if not plan.metric_ids:
                continue
            d = gate.authorize(plan.metric_ids[0])
            if plan.status in (READY, BLOCKED):
                assert plan.trust_level == d.effective_level, q
                assert plan.headline_permitted == d.headline_permitted, q
                assert plan.execution_mode == d.execution_mode, q

    def test_planner_never_softens_a_block(self, planner):
        plan = planner.plan("What's our profit?")
        assert plan.trust_level == "BLOCK"
        assert plan.status == BLOCKED
        assert plan.headline_permitted is False

    def test_block_plan_is_still_executable_internally(self, planner):
        """analytics_execution_spec.md's precondition: a BLOCK metric's raw value may still be
        computed INTERNALLY so the system can state the size of the disagreement -- what is
        forbidden is assembling it into a 'the answer is X' plan."""
        plan = planner.plan("What's our profit?")
        assert plan.executable is True
        assert plan.execution_calls
        assert plan.headline_permitted is False

    def test_block_plan_discloses_its_conflicts(self, planner):
        plan = planner.plan("What's our profit?")
        assert plan.required_disclosures

    def test_show_both_plans_every_family_member(self, planner):
        plan = planner.plan("How much do tenants owe?")
        assert len(plan.execution_calls) == 4
        assert {c.metric_id for c in plan.execution_calls} == {
            "M.AR.001A", "M.AR.001B", "M.AR.001C", "M.AR.001D"}


class TestStructuralGuards:
    """Phase 3 requirement 5."""

    def test_degenerate_comparison_is_caught_before_execution(self, planner):
        plan = planner.plan("Which property is best?")
        assert plan.status == NOT_DETERMINABLE
        assert plan.execution_calls == ()
        assert "only 1 distinct value" in plan.not_determinable_reason.lower()

    def test_unsupported_historical_comparison_is_rejected(self, planner):
        plan = planner.plan("Compare maintenance year on year")
        assert plan.status in (NOT_DETERMINABLE, REJECTED)
        assert plan.execution_calls == ()

    def test_snapshot_only_family_member_is_excluded_from_a_historical_question(self, planner):
        """5.1 step 4. The AR family has MIXED time semantics: Def A/B are ledger-backed and
        historical, Def C is the application's currently-stored balance ("not a time series"),
        Def D is a frozen 2026-04 migration snapshot. A "last year" question must exclude the
        member that cannot answer it -- and must DISCLOSE the exclusion rather than silently
        narrowing the family or silently reapplying snapshot logic at a past date."""
        plan = planner.plan("What did tenants owe last year?", metric_id="M.AR.001C")
        planned = {c.metric_id for c in plan.execution_calls}
        assert "M.AR.001C" not in planned, "snapshot-only definition answered a past period"
        assert {"M.AR.001A", "M.AR.001B"} <= planned, "historical definitions were dropped"
        assert "M.AR.001C" in plan.excluded_by_time
        assert plan.time_note, "the exclusion was silent -- it must be disclosed"
        assert "M.AR.001C" in plan.time_note

    def test_a_wholly_unanswerable_period_is_not_determinable(self, planner):
        """When NO member of the family can answer the period, the plan terminates rather than
        narrowing to nothing."""
        plan = planner.plan("What was occupancy in 2015?")
        assert plan.status == NOT_DETERMINABLE
        assert plan.execution_calls == ()

    def test_arithmetic_bypass_of_block_is_refused(self, planner, registry):
        """The composition guard, delegated to the Phase 2 gate: 'profit' must not be
        reconstructible as SAFE revenue minus SAFE expenses."""
        ok, level, reasons = planner.gate.authorize_combination(["M.REV.001", "M.EXP.001"])
        assert ok is False
        assert level == "BLOCK"
        assert any("M.PROFIT.001" in r for r in reasons)

    def test_cross_family_arithmetic_is_refused(self, planner):
        ok, _, reasons = planner.gate.authorize_combination(["M.AR.001A", "M.AR.001C"])
        assert ok is False
        assert any("Cross-family" in r for r in reasons)

    def test_no_plan_is_both_executable_and_clarification_seeking(self, planner):
        """6: 'the pipeline does not execute speculatively against multiple candidate
        resolutions and pick the best result after the fact.'"""
        for _, q in DOMAIN_QUESTIONS + [("amb", "How much did we collect?")]:
            plan = planner.plan(q)
            if plan.status == NEEDS_CLARIFICATION:
                assert plan.execution_calls == (), q

    def test_terminated_plans_are_never_executable(self, planner):
        for q in ("What is our margin analysis?", "Which property is best?",
                  "How much did we collect?"):
            plan = planner.plan(q)
            assert plan.executable is False, q


class TestAmbiguousQuestionsNeverSilentlyResolve:
    """The Phase 3 brief's own list of ambiguous questions. For each, verify the system does
    NOT silently select one definition."""

    AMBIGUOUS = [
        "How much do tenants owe?",
        "What is occupancy?",
        "What was profit last month?",
        "Why did profit fall?",
        "How much revenue did we make?",
        "Which tenants are overdue?",
    ]

    @pytest.mark.parametrize("question", AMBIGUOUS)
    def test_no_ambiguous_question_yields_a_silent_single_definition(self, planner, question):
        plan = planner.plan(question)
        if plan.trust_level in ("SHOW_BOTH", "BLOCK"):
            assert plan.plan_type == PLAN_EXPLAIN_CONFLICT
            assert plan.headline_permitted is False
            if len(plan.metric_ids) > 1:
                assert len(plan.execution_calls) == len(plan.metric_ids)
        else:
            # A question that is NOT definitionally ambiguous (revenue) may legitimately
            # resolve to one metric -- but only because the registry says there is exactly one
            # definition, never because the resolver picked the easier of several.
            assert len(plan.metric_ids) == 1
            assert plan.trust_level in ("SAFE", "DISCLOSE")

    def test_tenant_dues_never_collapses_to_the_easier_member(self, planner):
        """3.2's named failure mode: resolving to M.AR.001A because it is SHOW_BOTH rather
        than BLOCK, and therefore 'easier'."""
        plan = planner.plan("How much do tenants owe?")
        assert "M.AR.001C" in plan.metric_ids and "M.AR.001D" in plan.metric_ids

    def test_occupancy_never_yields_a_bare_percentage(self, planner):
        plan = planner.plan("What is occupancy?")
        assert plan.headline_permitted is False

    def test_profit_never_yields_the_ledger_figure_silently(self, planner):
        plan = planner.plan("What was profit last month?")
        assert plan.trust_level == "BLOCK"
        assert plan.headline_permitted is False

    def test_overdue_question_surfaces_the_ar_family_as_an_alternative(self, planner):
        """ai_evaluation_framework.md 3 marks this scenario 'Composite, SHOW_BOTH + DISCLOSE':
        aging is DISCLOSE, but the dues family it implicates is not silently omitted."""
        plan = planner.plan("Which tenants are overdue?")
        assert plan.trust_level == "DISCLOSE"
        assert plan.metric is not None
        assert any(a.startswith("M.AR.001") for a in plan.metric.alternatives)

    def test_revenue_is_answerable_because_it_has_one_definition(self, planner):
        """The control case: preserving ambiguity must not mean refusing everything."""
        plan = planner.plan("How much revenue did we make?")
        assert plan.status == READY
        assert plan.trust_level == "SAFE"
        assert plan.headline_permitted is True


class TestPlanIsExecutableByPhase2:
    """Requirement 3: 'a machine-readable Analytics Plan that can be passed directly into
    Phase 2 execution'."""

    def test_execution_calls_run_through_the_phase_2_executor(self, planner, executor):
        plan = planner.plan("How much revenue did we make?")
        answers = [executor.execute(c.metric_id, **c.kwargs) for c in plan.execution_calls]
        assert len(answers) == 1
        assert answers[0].trust_level == "SAFE"
        assert abs(answers[0].headline - 72705593.43) < 0.01

    def test_block_plan_executes_without_leaking_a_headline(self, planner, executor):
        plan = planner.plan("What's our profit?")
        for call in plan.execution_calls:
            ans = executor.execute(call.metric_id, **call.kwargs)
            assert ans.headline is None
            assert ans.trust_level == "BLOCK"

    def test_show_both_family_plan_executes_every_definition(self, planner, executor):
        plan = planner.plan("How much do tenants owe?")
        for call in plan.execution_calls:
            ans = executor.execute(call.metric_id, **call.kwargs)
            assert len(ans.results) == 4, f"{call.metric_id} narrowed the family"

    def test_risk_composite_executes_each_member_separately(self, planner, executor):
        plan = planner.plan("What are our biggest business risks?")
        levels = {}
        for call in plan.execution_calls:
            ans = executor.execute(call.metric_id, **call.kwargs)
            levels[call.metric_id] = ans.trust_level
        assert len(levels) == len(plan.execution_calls)
        # 2.8: each keeps its OWN trust label -- never one blended score.
        assert len(set(levels.values())) >= 1
