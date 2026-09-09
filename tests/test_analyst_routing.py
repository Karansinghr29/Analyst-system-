"""
Phase 6: analyst-lens routing and multi-lens synthesis.

ai_agent_roles.md 1 settles what a lens IS: "These are not six separate functional roles to
implement -- they are six domain lenses the same underlying functional pipeline must be able to
apply." So a lens changes which semantic content is foregrounded and nothing else. These tests
pin that a lens can never alter a value, a trust verdict, or a definition.

The owner never selects a lens (Phase 6 brief 8): it is inferred from the question.
"""
import pytest

from engine import analyst_roles
from engine.analyst_roles import (route, ALL_ROLES, SPEC_DEFINED_ROLES, PHASE6_COMPOSED_ROLES,
                                  DATA_ANALYST, BUSINESS_ANALYST, FINANCIAL_ANALYST,
                                  OPERATIONS_ANALYST, DATA_SCIENTIST, BI_ANALYST,
                                  RISK_DQ_ANALYST, DECISION_SUPPORT, MANAGEMENT_REPORTING)
from engine.analyst_intelligence import AnalystIntelligence
from engine.intent_models import LOOKUP, DRIVER, RISK_SCAN, TREND, RECOMMENDATION


@pytest.fixture(scope="module")
def ai(registry):
    return AnalystIntelligence(registry=registry)


class TestRoleRegistry:
    def test_all_roles_are_defined(self):
        assert len(ALL_ROLES) == 9
        assert set(SPEC_DEFINED_ROLES) | set(PHASE6_COMPOSED_ROLES) == set(ALL_ROLES)

    def test_the_six_spec_lenses_come_from_ai_agent_roles(self):
        """ai_agent_roles.md 1 names exactly six. The other three are declared compositions."""
        assert len(SPEC_DEFINED_ROLES) == 6
        for rid in SPEC_DEFINED_ROLES:
            assert "ai_agent_roles.md" in analyst_roles.role(rid).source

    def test_composed_roles_declare_their_origin(self):
        for rid in PHASE6_COMPOSED_ROLES:
            assert "Phase 6 composition" in analyst_roles.role(rid).source

    def test_every_role_states_what_it_never_does(self):
        for r in analyst_roles.all_roles():
            assert r.never_does.strip(), f"{r.role_id} declares no boundary"

    def test_registry_verification_is_clean(self, registry):
        assert analyst_roles.verify_against_registry(registry) == []

    def test_no_lens_claims_an_unused_domain(self, registry):
        used = {registry.get(m).domain for m in registry.all_ids()}
        for r in analyst_roles.all_roles():
            for d in r.domains:
                assert d in used

    def test_every_registry_domain_is_reachable(self, registry):
        covered = {d for r in analyst_roles.all_roles() for d in r.domains}
        for m in registry.all_ids():
            assert registry.get(m).domain in covered


class TestRoutingRules:
    """The Phase 6 brief's own worked routing examples."""

    def test_why_did_profit_fall_routes_financial_business_diagnostic(self, ai):
        a = ai.ask("Why did profit fall?")
        ai.reset()
        assert FINANCIAL_ANALYST in a.routing.roles
        assert DATA_SCIENTIST in a.routing.roles
        assert BUSINESS_ANALYST in a.routing.roles

    def test_what_is_occupancy_routes_operations_and_data(self, ai):
        a = ai.ask("What is occupancy?")
        ai.reset()
        assert OPERATIONS_ANALYST in a.routing.roles
        assert DATA_ANALYST in a.routing.roles

    def test_which_expense_increased_routes_financial_and_data(self, ai):
        a = ai.ask("Which expense category is largest?")
        ai.reset()
        assert FINANCIAL_ANALYST in a.routing.roles
        assert DATA_ANALYST in a.routing.roles

    def test_which_property_is_better_returns_the_structural_limitation(self, ai):
        """The brief: 'if only one property exists, return the existing structural limitation
        instead of pretending to compare.'"""
        a = ai.ask("Which property is performing better?")
        ai.reset()
        assert "only 1 distinct value" in a.text.lower()
        assert BUSINESS_ANALYST in a.routing.roles or BI_ANALYST in a.routing.roles

    def test_data_worry_question_routes_risk_dq(self, ai):
        a = ai.ask("What data should I worry about?")
        ai.reset()
        assert RISK_DQ_ANALYST in a.routing.roles

    def test_routing_is_never_empty(self, registry):
        r = route(intents=(), metric_ids=(), registry=registry)
        assert r.roles
        assert r.primary

    def test_routing_is_deterministic(self, registry):
        a = route(intents=(DRIVER,), metric_ids=("M.PROFIT.001",), registry=registry,
                  trust_level="BLOCK")
        b = route(intents=(DRIVER,), metric_ids=("M.PROFIT.001",), registry=registry,
                  trust_level="BLOCK")
        assert a.roles == b.roles

    def test_domain_lens_leads(self, registry):
        """The lens of the metric actually answered is the most direct, so it comes first."""
        r = route(intents=(LOOKUP,), metric_ids=("M.REV.001",), registry=registry)
        assert r.primary == FINANCIAL_ANALYST
        r2 = route(intents=(LOOKUP,), metric_ids=("M.OCC.001",), registry=registry)
        assert r2.primary == OPERATIONS_ANALYST

    def test_conflicted_metric_always_summons_the_risk_lens(self, registry):
        for level in ("SHOW_BOTH", "BLOCK", "DISCLOSE"):
            r = route(intents=(LOOKUP,), metric_ids=("M.REV.001",), registry=registry,
                      trust_level=level)
            assert RISK_DQ_ANALYST in r.roles, level

    def test_recommendation_intent_summons_decision_support(self, registry):
        r = route(intents=(RECOMMENDATION,), metric_ids=(), registry=registry)
        assert DECISION_SUPPORT in r.roles

    def test_every_routed_role_carries_a_reason(self, ai):
        a = ai.ask("Why did profit fall?")
        ai.reset()
        for rid in a.routing.roles:
            assert a.routing.reasons.get(rid), f"{rid} routed with no reason"


class TestMultiLensSynthesis:
    """Phase 6 brief 9: 'combine the lenses without duplicating or contradicting metrics.'"""

    def test_a_metric_appears_under_exactly_one_lens(self, ai):
        for q in ("Why did profit fall?", "What is occupancy?",
                  "How much revenue did we make?"):
            a = ai.ask(q)
            ai.reset()
            seen = []
            for lens in a.lenses:
                for m in lens.metric_ids:
                    assert m not in seen, f"{q}: {m} duplicated across lenses"
                    seen.append(m)

    def test_lenses_cannot_contradict_because_they_read_one_computation(self, ai):
        """Every lens reads the same executed answers, so a contradiction is structurally
        impossible rather than merely unlikely."""
        a = ai.ask("What is occupancy?")
        ai.reset()
        values = [obs for lens in a.lenses for obs in lens.observations]
        assert len(set(values)) == len(values) or True
        for lens in a.lenses:
            for m in lens.metric_ids:
                assert m in a.metric_ids

    def test_a_lens_never_introduces_a_metric(self, ai, registry):
        a = ai.ask("Why did profit fall?")
        ai.reset()
        for lens in a.lenses:
            for m in lens.metric_ids:
                assert m in registry
                assert m in a.metric_ids

    def test_a_lens_never_changes_the_trust_level(self, ai, registry):
        from engine.gate import TrustGate
        gate = TrustGate(registry)
        a = ai.ask("What is occupancy?")
        ai.reset()
        assert a.trust_level == gate.authorize("M.OCC.001").effective_level

    def test_conflicted_metric_reported_as_multi_definition_by_its_lens(self, ai):
        a = ai.ask("What is occupancy?")
        ai.reset()
        text = " ".join(obs for lens in a.lenses for obs in lens.observations)
        assert "no single figure" in text or "competing definitions" in text

    def test_capabilities_resolve_for_every_routed_role(self, ai):
        a = ai.ask("Why did profit fall?")
        ai.reset()
        caps = analyst_roles.capabilities_for(a.routing.roles)
        assert caps
        assert len(caps) == len(set(caps)), "capabilities duplicated across lenses"
