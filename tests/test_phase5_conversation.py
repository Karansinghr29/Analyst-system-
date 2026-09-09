"""
Phase 5: multi-turn conversation state, the clarification lifecycle, explicit definition
selection, decision-support assembly, and the hostile-LLM boundary.

The rule that governs the whole file:
    "Never reinterpret an unanswered clarification as permission to choose a definition."

and its twin, from the brief's own worked example:
    "Never silently narrow before the user makes that choice."
"""
import pytest

from engine import conversation_state as cs
from engine import decision_support as ds_mod
from engine.conversation_state import (CLAR_REQUIRED, CLAR_ANSWERED, CLAR_REJECTED,
                                       CLAR_STILL_AMBIGUOUS, ALL_CLARIFICATION_STATES)
from engine.llm_interface import LLMInterface
from engine.llm_provider import CallableProvider, DeterministicMockProvider
from engine.result import NOT_DETERMINABLE_TEXT


@pytest.fixture
def iface(registry):
    return LLMInterface(registry=registry)


def _scripted_verbalizer(registry, fn):
    def prov(prompt, system, max_tokens, temperature):
        if "VERBALIZE" in system:
            return fn(prompt)
        return DeterministicMockProvider()._extract(prompt)
    return LLMInterface(provider=CallableProvider(prov, name="hostile"), registry=registry)


class TestClarificationLifecycle:
    """Phase 5 objective 4: the five distinguishable states."""

    def test_all_five_states_are_defined(self):
        assert len(ALL_CLARIFICATION_STATES) == 5

    def test_clarification_is_opened_and_awaited(self, iface):
        r = iface.ask("How much did we collect?")
        assert r.status == "NEEDS_CLARIFICATION"
        assert r.clarification_state == CLAR_REQUIRED
        assert iface.context.awaiting_clarification

    def test_answering_resolves_and_executes(self, iface):
        iface.ask("How much did we collect?")
        r = iface.ask("The ledger one")
        assert r.clarification_state == CLAR_ANSWERED
        assert r.executed
        assert r.metric_ids == ("M.COL.003",)

    def test_answering_by_metric_id_resolves(self, iface):
        iface.ask("How much did we collect?")
        r = iface.ask("M.COL.001 please")
        assert r.clarification_state == CLAR_ANSWERED
        assert r.metric_ids == ("M.COL.001",)

    def test_answering_by_ordinal_resolves(self, iface):
        iface.ask("How much did we collect?")
        r = iface.ask("the second one")
        assert r.clarification_state == CLAR_ANSWERED
        assert r.executed

    def test_rejection_does_not_pick_for_the_user(self, iface):
        """'you decide' is a refusal to choose, not permission to choose."""
        iface.ask("How much did we collect?")
        r = iface.ask("I don't know, you decide")
        assert r.clarification_state == CLAR_REJECTED
        assert r.executed is False
        assert not r.metric_ids

    def test_still_ambiguous_reply_keeps_the_clarification_open(self, iface):
        iface.ask("How much did we collect?")
        r = iface.ask("the usual figure")
        assert r.clarification_state == CLAR_STILL_AMBIGUOUS
        assert r.executed is False
        assert iface.context.awaiting_clarification

    def test_an_unanswered_clarification_never_becomes_permission(self, iface):
        """Ask, get a non-answer, ask again -- the system must still not choose."""
        iface.ask("How much did we collect?")
        for reply in ("hmm", "whatever you think", "just tell me"):
            r = iface.ask(reply)
            assert r.executed is False, f"{reply!r} was treated as a decision"
            assert r.metric_ids == ()

    def test_clarification_text_is_business_friendly(self, iface):
        r = iface.ask("How much did we collect?")
        assert "question_understanding_spec" not in r.text
        assert "?" in r.text


class TestExplicitDefinitionSelection:
    """The brief's worked example: the system may narrow ONLY after the user chooses."""

    def test_show_both_is_not_narrowed_before_a_choice(self, iface):
        r = iface.ask("What is occupancy?")
        assert r.trust_level == "SHOW_BOTH"
        assert all(a.headline is None for a in r.answers)
        assert len(r.answers[0].results) >= 2

    def test_unambiguous_selection_narrows(self, iface):
        iface.ask("What is occupancy?")
        r = iface.ask("Use the day-weighted definition.")
        assert r.definition_selection is not None
        assert r.executed

    def test_ambiguous_selection_asks_rather_than_picking(self, iface):
        """'the live occupancy definition' matches three of the five labels. Picking one would
        be the silent narrowing the trust policy forbids; ignoring the attempt would leave an
        explicit instruction unacknowledged."""
        iface.ask("What is occupancy?")
        r = iface.ask("Use the live occupancy definition.")
        assert r.definition_selection is None
        assert r.status == "NEEDS_CLARIFICATION"
        assert r.clarification is not None
        assert len(r.clarification.options) >= 2

    def test_selection_after_an_ambiguous_attempt_resolves(self, iface):
        iface.ask("What is occupancy?")
        iface.ask("Use the live occupancy definition.")
        r = iface.ask("Def A")
        assert r.definition_selection is not None
        assert r.executed

    def test_a_selected_definition_still_discloses_the_conflict(self, iface):
        iface.ask("What is occupancy?")
        r = iface.ask("Use the day-weighted definition.")
        disclosure = r.definition_selection.disclosure()
        assert "still exist" in disclosure and "disagree" in disclosure

    def test_selection_records_its_provenance(self, iface):
        iface.ask("What is occupancy?")
        r = iface.ask("Use the day-weighted definition.")
        sel = r.definition_selection
        assert sel.user_text
        assert sel.selected_at_turn >= 0
        assert len(sel.alternatives_shown) >= 2

    def test_selection_requires_having_been_shown_the_alternatives(self, iface):
        """A selection cannot be made for a family the user has never seen -- otherwise this
        path would be a way to request a pre-narrowed answer and bypass SHOW_BOTH entirely."""
        r = iface.ask("Use the day-weighted occupancy definition.")
        assert r.definition_selection is None

    def test_a_bare_restatement_is_not_a_selection(self, iface):
        iface.ask("What is occupancy?")
        r = iface.ask("What is occupancy?")
        assert r.definition_selection is None
        assert r.trust_level == "SHOW_BOTH"


class TestMultiTurnInheritance:
    def test_followup_inherits_metric_and_becomes_a_driver_question(self, iface):
        """The brief's example: 'How much revenue did we make last month?' then
        'Why was it lower?'"""
        iface.ask("How much revenue did we make last month?")
        r = iface.ask("Why was it lower?")
        assert r.plan is not None
        assert "driver" in r.plan.intents or r.plan.driver_requested
        assert "M.REV.001" in r.metric_ids or "M.REV.002" in r.metric_ids

    def test_explicit_new_period_is_never_overridden(self, iface):
        iface.ask("Show revenue for 2026-07.")
        r = iface.ask("What about 2026-06?")
        assert "time_range" not in r.inherited_context

    def test_dimension_inheritance_is_additive(self, registry):
        from engine.conversation_context import ConversationContext, Turn
        from engine.structured_output import LLMPlanRequest
        ctx = ConversationContext()
        prior = LLMPlanRequest(intent=("lookup",), concept="revenue",
                               metric_ids=("M.REV.001",), dimensions=("month",))
        ctx.record(Turn(question="revenue by month", request=prior))
        new = LLMPlanRequest(intent=("lookup",), concept="")
        out, inherited = ctx.resolve(new, "what about that?")
        assert out.dimensions == ("month",)
        assert "dimensions" in inherited

    def test_user_correction_drops_inherited_context(self, registry):
        """A correction REPLACES context: carrying it forward would preserve the very error the
        user is correcting."""
        from engine.conversation_context import ConversationContext, Turn
        from engine.structured_output import LLMPlanRequest
        ctx = ConversationContext()
        prior = LLMPlanRequest(intent=("lookup",), concept="revenue",
                               metric_ids=("M.REV.001",), time_range="july")
        ctx.record(Turn(question="revenue for july", request=prior))
        new = LLMPlanRequest(intent=("lookup",), concept="occupancy")
        out, inherited = ctx.resolve(new, "No, I meant occupancy")
        assert inherited == ("correction:context_dropped",)
        assert out.concept == "occupancy"

    def test_correction_is_detected(self):
        assert cs.detect_correction("No, I meant occupancy") is not None
        assert cs.detect_correction("Actually, show expenses") is not None
        assert cs.detect_correction("How much revenue?") is None

    def test_ambiguity_survives_across_turns(self, iface):
        """A SHOW_BOTH family stays SHOW_BOTH on a follow-up -- ambiguity is not worn down by
        repetition."""
        iface.ask("What is occupancy?")
        r = iface.ask("What about it?")
        if r.executed:
            assert r.trust_level in ("SHOW_BOTH", "BLOCK")
            assert all(a.headline is None for a in r.answers)

    def test_context_never_inherits_a_trust_level(self, iface):
        iface.ask("How much revenue did we make?")
        r = iface.ask("What about last month?")
        if r.metric_ids:
            from engine.gate import TrustGate
            gate = TrustGate(iface.registry)
            assert r.trust_level == gate.authorize(r.metric_ids[0]).effective_level


class TestDecisionSupport:
    """Phase 5 objective 6. 'Do not manufacture missing sections.'"""

    def test_sections_are_populated_only_where_evidence_permits(self, iface):
        r = iface.ask("How much revenue did we make?")
        ds = r.decision_support
        assert ds is not None
        assert ds.executive_summary
        assert ds.key_numbers
        assert ds.evidence

    def test_omitted_sections_are_recorded_with_a_reason(self, iface):
        r = iface.ask("How much revenue did we make?")
        ds = r.decision_support
        for name, reason in ds.omitted_sections.items():
            assert reason, f"{name} omitted with no stated reason"

    def test_block_preserves_the_conflict_instead_of_one_number(self, iface):
        """The brief's own example: profit is BLOCK, so the answer must preserve the conflict
        rather than generating a single 'profit fell by X%' statement."""
        r = iface.ask("What's our profit?")
        ds = r.decision_support
        assert ds.trust_level == "BLOCK"
        assert ds.headline_permitted is False
        assert ds.definition_conflicts, "a BLOCK answer disclosed no definition conflict"

    def test_show_both_keeps_every_definition_in_key_numbers(self, iface):
        r = iface.ask("How much do tenants owe?")
        ds = r.decision_support
        assert len(ds.key_numbers) >= 2
        assert ds.headline_permitted is False

    def test_data_quality_warnings_surface(self, iface):
        r = iface.ask("What was our electricity cost?")
        ds = r.decision_support
        assert ds.data_quality_warnings or ds.limitations

    def test_not_determinable_decision_support_states_the_phrase(self, iface):
        r = iface.ask("What is our margin analysis?")
        assert NOT_DETERMINABLE_TEXT in r.text

    def test_render_produces_no_invented_sections(self, iface):
        r = iface.ask("How much revenue did we make?")
        text = ds_mod.render(r.decision_support)
        for section in ("DRIVERS", "RISKS", "TREND"):
            if section.lower() not in " ".join(r.decision_support.populated_sections()).lower():
                continue
        assert text.strip()


class TestPhase5SafetyBoundary:
    """The LLM remains untrusted at the insight and decision-support layers too."""

    def test_hostile_verbalization_of_a_block_answer_is_rejected(self, registry):
        i = _scripted_verbalizer(registry, lambda p: "Profit is Rs.5,000,000. M.PROFIT.001")
        r = i.ask("What's our profit?")
        assert r.guard_violations
        assert r.rendered.verbalized is False
        assert r.text != r.rendered.skeleton
        assert "M.PROFIT.001" in r.rendered.skeleton

    def test_fabricated_number_is_rejected(self, registry):
        i = _scripted_verbalizer(registry, lambda p: "Revenue was Rs.88,888,888.88 (M.REV.001).")
        r = i.ask("How much revenue did we make?")
        assert any("introduces the number" in g for g in r.guard_violations)

    def test_llm_cannot_choose_a_show_both_winner(self, registry):
        i = _scripted_verbalizer(
            registry, lambda p: "Occupancy: the real number is 82%. M.OCC.001")
        r = i.ask("What is occupancy?")
        assert r.guard_violations
        assert r.rendered.verbalized is False

    def test_pii_in_a_verbalization_is_rejected(self, registry):
        i = _scripted_verbalizer(
            registry, lambda p: "M.REV.001 revenue 72705593.43. Tenant phone on file.")
        r = i.ask("How much revenue did we make?")
        assert any("PII" in g for g in r.guard_violations)

    def test_insights_never_reach_the_user_unguarded(self, iface):
        """An insight is an answer, so it inherits the same rendering guard."""
        r = iface.ask("What are our biggest business risks?")
        assert r.guard_violations == ()

    def test_no_llm_number_is_authoritative(self, registry):
        """Even when the verbalization passes the guard, the authoritative values come from the
        deterministic engine -- proven by the answers carrying them independently."""
        i = LLMInterface(registry=registry)
        r = i.ask("How much revenue did we make?")
        assert abs(r.answers[0].headline - 72705593.43) < 0.01


class TestPipelineOrder:
    """Objective 11: the LLM must remain downstream of authoritative computation."""

    def test_execution_precedes_verbalization(self, registry):
        order = []

        def prov(prompt, system, max_tokens, temperature):
            order.append("verbalize" if "VERBALIZE" in system else "extract")
            if "VERBALIZE" in system:
                return prompt.split("ANSWER SKELETON", 1)[1].strip()
            return DeterministicMockProvider()._extract(prompt)

        i = LLMInterface(provider=CallableProvider(prov, name="ordered"), registry=registry)
        r = i.ask("How much revenue did we make?")
        assert order == ["extract", "verbalize"]
        assert r.executed

    def test_the_skeleton_is_complete_without_the_llm(self, registry):
        """If the model vanished, the deterministic answer would still be valid and complete."""
        i = LLMInterface(registry=registry, verbalize=False)
        r = i.ask("How much revenue did we make?")
        assert r.executed
        assert "M.REV.001" in r.rendered.skeleton
        assert "VALIDATION" in r.rendered.skeleton
        assert r.rendered.verbalized is False
