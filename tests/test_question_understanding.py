"""
Phase 3 stages [1]-[4]: question_understanding_spec.md.

The central rule under test is 3.2: "Family resolution is mandatory, not optional ... A naive
metric-resolution step that matches 'tenant dues' to M.AR.001A alone (because it's first
alphabetically, or because it's SHOW_BOTH rather than BLOCK and therefore 'easier') is a
specification violation."
"""
import pytest

from engine import concept_map
from engine import dimension_resolution as dimres
from engine import time_resolution as timeres
from engine.question_understanding import QuestionUnderstander, classify_intents
from engine.intent_models import (LOOKUP, FILTERED_LOOKUP, TREND, COMPARISON, ANOMALY, DRIVER,
                                  RISK_SCAN, RECOMMENDATION, META, NOT_DETERMINABLE_TEXT)


@pytest.fixture(scope="module")
def understander(registry):
    return QuestionUnderstander(registry)


class TestConceptMapIntegrity:
    """Exit criteria: 'every metric reference resolves to the semantic registry' and 'no
    business definition is duplicated or invented'."""

    def test_every_concept_metric_resolves_to_the_registry(self, registry):
        assert concept_map.verify_against_registry(registry) == []

    def test_every_dimension_phrase_resolves_to_business_dimensions(self):
        assert dimres.verify_dimension_vocabulary() == []

    def test_concept_map_defines_no_business_content(self, registry):
        """A concept carries an INDEX into the registry, never a definition. Its metrics'
        meanings must still come from the registry at runtime."""
        for c in concept_map.all_concepts():
            for mid in c.metric_ids:
                spec = registry.get(mid)
                assert spec.definition, f"{mid} has no registry definition to defer to"
                assert spec.trust_level, f"{mid} has no registry trust level"

    def test_the_five_spec_families_are_all_present(self):
        """question_understanding_spec.md 3.2's own table."""
        for name in ("tenant_dues", "occupancy", "profit", "owner_rent", "collections"):
            assert concept_map.concept(name) is not None, f"missing 3.2 concept {name}"


class TestIntentClassification:
    @pytest.mark.parametrize("question,expected", [
        ("How much revenue did we make?", LOOKUP),
        ("Why did profit fall?", DRIVER),
        ("What should management do next?", RECOMMENDATION),
        ("Did anything look off this month?", ANOMALY),
        ("What are our biggest business risks?", RISK_SCAN),
        ("Revenue by month", TREND),
        ("Is this month better than last?", COMPARISON),
        ("Why can't you tell me tenant dues?", META),
    ])
    def test_intent_is_classified(self, question, expected):
        assert expected in classify_intents(question)

    def test_a_question_may_carry_more_than_one_intent(self):
        """2: 'A single question may carry more than one intent ... the system must decompose
        it into its constituent intents, not blend them.'"""
        intents = classify_intents("Why did profit fall, and what should we do?")
        assert DRIVER in intents and RECOMMENDATION in intents

    def test_intents_are_never_empty(self):
        assert classify_intents("revenue") == (LOOKUP,)
        assert classify_intents("") == (LOOKUP,)


class TestFamilyResolutionIsMandatory:
    """3.2 -- the single most important rule in the spec."""

    def test_tenant_dues_never_resolves_to_one_member(self, understander):
        u = understander.understand("How much do tenants owe?")
        assert u.metric.is_family
        assert set(u.metric.metric_ids) == {"M.AR.001A", "M.AR.001B", "M.AR.001C", "M.AR.001D"}

    def test_naming_one_member_still_expands_to_the_family(self, understander):
        """Asking for M.AR.001A by id must not narrow the answer -- 3.2's rule is about what
        gets answered, not about how the request was phrased."""
        u = understander.understand("tenant dues", metric_id="M.AR.001A")
        assert set(u.metric.metric_ids) == {"M.AR.001A", "M.AR.001B", "M.AR.001C", "M.AR.001D"}

    def test_occupancy_resolves_to_the_multi_definition_metric(self, understander):
        u = understander.understand("What is occupancy?")
        assert u.metric.metric_ids == ("M.OCC.001",)
        assert u.metric.is_family, "M.OCC.001 carries 5 definitions internally"

    def test_profit_resolves_to_the_three_definition_metric(self, understander):
        u = understander.understand("What's our profit?")
        assert u.metric.metric_ids == ("M.PROFIT.001",)
        assert u.metric.is_family

    def test_owner_rent_resolves_to_the_three_definition_metric(self, understander):
        u = understander.understand("How much owner rent did we pay?")
        assert u.metric.metric_ids == ("M.OWN.002",)
        assert u.metric.is_family

    def test_every_family_carries_its_spec_justification(self, understander):
        for q in ("tenant dues", "occupancy", "profit", "owner rent"):
            u = understander.understand(q)
            assert u.metric.family_rule, f"{q}: family resolved with no stated rule"


class TestAmbiguityIsPreserved:
    """question_understanding_spec.md 6. The resolver must never settle a definitional
    ambiguity it is not entitled to settle."""

    def test_collections_requires_clarification_not_a_silent_pick(self, understander):
        """3.2: M.COL.001 (application) and M.COL.003 (ledger) are 'related but genuinely
        distinct, NOT one family; resolver must disclose both exist.'"""
        u = understander.understand("How much did we collect?")
        assert u.clarification is not None
        assert u.clarification.kind == "definitional"
        assert u.metric is None, "a clarification must not also carry a resolved metric"
        opts = " ".join(u.clarification.options)
        assert "M.COL.001" in opts and "M.COL.003" in opts

    def test_named_tenant_requires_referential_clarification(self, understander):
        """4.3: 27 PII columns are excluded from the export, so a tenant referred to by name
        cannot be uniquely identified. Guessing would attribute information to the wrong tenant."""
        u = understander.understand("How much does this tenant owe?")
        assert "tenant_id" in u.dimension_request.unresolved_entities

    def test_unrelated_concepts_in_one_question_trigger_clarification(self, understander):
        u = understander.understand("What is our occupancy and electricity cost?")
        assert u.clarification is not None
        assert u.clarification.kind == "definitional"


class TestNotDeterminable:
    def test_absent_concept_is_not_improvised(self, understander):
        """3.3: 'margin analysis' has no corresponding metric. 3.1 step 5: do not guess a
        nearby one."""
        u = understander.understand("What is our margin analysis?")
        assert NOT_DETERMINABLE_TEXT in u.not_determinable_reason
        assert u.metric is None

    def test_degenerate_comparison_gets_the_specific_answer(self, understander):
        """6.1: 'Which property is best?' must terminate with the specific 'only 1 property
        exists' statement, 'not a generic NOT_DETERMINABLE'."""
        u = understander.understand("Which property is best?")
        assert "only 1 distinct value" in u.not_determinable_reason.lower()
        assert "property_id" in u.not_determinable_reason
        assert "no semantic metric corresponds" not in u.not_determinable_reason.lower()

    def test_unknown_metric_id_is_rejected(self, understander):
        u = understander.understand("anything", metric_id="M.NOPE.999")
        assert NOT_DETERMINABLE_TEXT in u.not_determinable_reason


class TestTimeResolution:
    """question_understanding_spec.md 5."""

    def test_date_field_is_the_documented_one_never_created_at(self, understander, registry):
        """5.1 step 2. For every metric except the documented M.MAINT exception, the resolved
        date field must be the registry's own, never substituted."""
        for mid in registry.all_ids():
            spec = registry.get(mid)
            rt = timeres.resolve(spec, "how much last month?")
            assert rt.date_field == spec.date_field

    def test_maintenance_created_at_is_the_documented_exception(self, registry):
        """business_dimensions.md 17: maintenance_tickets has no other business-open-date
        column, so created_at IS the business date -- honoured because the REGISTRY says so."""
        spec = registry.get("M.MAINT.001")
        assert "created_at" in spec.date_field.lower()
        assert "created_at" in timeres.resolve(spec, "tickets last month").date_field.lower()

    def test_period_parsing_is_deterministic_and_clock_independent(self, registry):
        """answer_contract.md 6: the same question must resolve identically every time. All
        reference dates are fixed to the export snapshot, never the machine clock."""
        spec = registry.get("M.REV.001")
        a = timeres.resolve(spec, "revenue last month")
        b = timeres.resolve(spec, "revenue last month")
        assert (a.start, a.end, a.period_label) == (b.start, b.end, b.period_label)
        assert a.start.startswith("2026-07")

    def test_snapshot_only_metric_refuses_a_historical_question(self, registry):
        """5.1 step 4: M.AR.001C is the application's currently stored balance -- there is no
        historical series of past balances."""
        rt = timeres.resolve(registry.get("M.AR.001C"), "what did tenants owe last year?")
        assert rt.within_coverage is False
        assert "no historical form" in rt.coverage_note

    def test_aging_is_current_date_dependent(self, registry):
        """C.019/DQ.018: aging buckets were computed once at query time, not preserved."""
        rt = timeres.resolve(registry.get("M.RISK.002"), "what was our aging on 2024-01-15?")
        assert rt.within_coverage is False
        assert "CURRENT_DATE-dependent" in rt.coverage_note

    def test_maintenance_yoy_is_refused(self, registry):
        """5.3: no YoY for maintenance (20 months), regardless of phrasing."""
        rt = timeres.resolve(registry.get("M.MAINT.001"), "maintenance year on year")
        assert rt.yoy_permitted is False
        assert rt.yoy_note

    def test_eb_trend_is_refused_for_narrow_coverage(self, registry):
        rt = timeres.resolve(registry.get("M.EB.001"), "electricity trend by month")
        assert rt.yoy_permitted is False

    def test_revenue_yoy_is_permitted(self, registry):
        """The guard must not be a blanket refusal -- revenue has 54 months of coverage."""
        rt = timeres.resolve(registry.get("M.REV.001"), "revenue year on year")
        assert rt.yoy_permitted is True

    def test_out_of_coverage_period_states_the_boundary(self, registry):
        rt = timeres.resolve(registry.get("M.REV.001"), "revenue in 2015")
        assert rt.within_coverage is False
        assert rt.coverage_start and rt.coverage_start in rt.coverage_note

    def test_comparison_rejects_a_snapshot_only_metric(self, registry):
        cmp = timeres.resolve_comparison(registry.get("M.AR.001C"), "dues this month vs last")
        assert cmp.valid is False
        assert "snapshot-only" in cmp.reason

    def test_comparison_resolves_both_periods_independently(self, registry):
        cmp = timeres.resolve_comparison(registry.get("M.REV.001"), "revenue last month vs before")
        assert cmp.current.period_label != cmp.baseline.period_label
        assert cmp.valid is True
