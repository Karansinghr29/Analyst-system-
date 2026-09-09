"""
ai_evaluation_framework.md 1.2 (trust-rule compliance) and the Layer 3 enforcement rules of
ai_analytics_architecture.md 2 / ai_agent_roles.md 3.

The distinction from Phase 1's tests/test_trust_levels.py: those tested that the ANSWER carried
the right trust label. These test that the GATE is structurally binding -- that no code path
can obtain a headline number the gate withheld, that the refusal precedes execution, and that
the metric-mixing guards actually refuse.
"""
import pytest

from engine.gate import (TrustGate, GateViolation, MODE_SINGLE, MODE_FAMILY,
                         MODE_INTERNAL_ONLY, MODE_REFUSE, date_basis_columns)


@pytest.fixture(scope="module")
def gate(registry):
    return TrustGate(registry)


class TestGateAuthorization:
    def test_every_metric_gets_a_decision(self, gate, registry):
        for mid in registry.all_ids():
            d = gate.authorize(mid)
            assert d.execution_mode in (MODE_SINGLE, MODE_FAMILY, MODE_INTERNAL_ONLY, MODE_REFUSE)
            assert d.effective_level in ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK",
                                         "NOT_DETERMINABLE")

    def test_headline_is_permitted_only_for_safe_and_disclose(self, gate, registry):
        for mid in registry.all_ids():
            d = gate.authorize(mid)
            expected = d.effective_level in ("SAFE", "DISCLOSE")
            assert d.headline_permitted is expected, (
                f"{mid}: {d.effective_level} headline_permitted={d.headline_permitted}")

    def test_gate_effective_level_never_below_the_metrics_own_level(self, gate, registry):
        """The gate may only tighten, never loosen. ai_agent_roles.md 3: no later role may
        'reinterpret or soften' the verdict -- and the gate itself may not soften the CSV."""
        sev = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}
        for mid in registry.all_ids():
            d = gate.authorize(mid)
            assert sev[d.effective_level] >= sev[registry.get(mid).trust_level]

    def test_unknown_metric_is_refused_not_improvised(self, gate):
        d = gate.authorize("M.MADE.UP.001")
        assert d.execution_mode == MODE_REFUSE
        assert d.effective_level == "NOT_DETERMINABLE"
        assert not d.headline_permitted

    def test_block_requires_the_full_family(self, gate):
        d = gate.authorize("M.AR.001C")
        assert d.execution_mode == MODE_INTERNAL_ONLY
        assert set(d.required_definitions) == {"M.AR.001A", "M.AR.001B", "M.AR.001C", "M.AR.001D"}

    def test_verdict_identical_across_repeated_calls(self, gate):
        """ai_trust_policy.md 2 BLOCK covers 'rephrased, indirect, or comparative' questions.
        The gate takes no phrasing parameter at all, so the guarantee is by construction; this
        pins that the decision is a pure function of metric_id."""
        first = gate.authorize("M.PROFIT.001")
        for _ in range(5):
            assert gate.authorize("M.PROFIT.001") == first


class TestGateIsBinding:
    def test_assert_headline_permitted_raises_for_show_both(self, gate):
        with pytest.raises(GateViolation):
            gate.authorize("M.OCC.001").assert_headline_permitted()

    def test_assert_headline_permitted_raises_for_block(self, gate):
        with pytest.raises(GateViolation):
            gate.authorize("M.PROFIT.001").assert_headline_permitted()

    def test_assert_headline_permitted_passes_for_safe(self, gate):
        assert gate.authorize("M.REV.001").assert_headline_permitted() is None

    def test_narrowing_a_family_raises(self, gate):
        with pytest.raises(GateViolation):
            gate.authorize("M.AR.001A").assert_definitions_complete(["only one"])

    def test_answer_headline_is_none_whenever_gate_withheld_it(self, executor, registry):
        """The structural guarantee, end to end: for every SHOW_BOTH/BLOCK/NOT_DETERMINABLE
        metric, there is no field on the returned answer a caller can read as THE number."""
        for mid in registry.all_ids():
            ans = executor.execute(mid)
            if ans.trust_level in ("SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
                assert ans.headline is None, f"{mid}: leaked a headline value"
                assert ans.headline_permitted is False

    def test_safe_and_disclose_answers_do_expose_a_headline(self, executor, registry):
        for mid in registry.all_ids():
            ans = executor.execute(mid)
            if ans.trust_level in ("SAFE", "DISCLOSE"):
                assert ans.headline is not None, f"{mid}: SAFE/DISCLOSE with no headline"


class TestRefusalPrecedesExecution:
    def test_not_determinable_metric_never_invokes_a_calculator(self, executor, monkeypatch):
        """ai_analytics_architecture.md 2's directionality rule: a BLOCKED/refused metric 'must
        never even be computed and then hidden.' M.OCC.003 is NOT_DETERMINABLE; if any
        calculator ran for it, this sentinel would fire."""
        import engine.execution as ex

        called = []

        class SpyRegistry(dict):
            def get(self, key, default=None):
                called.append(key)
                return dict.get(self, key, default)

        monkeypatch.setattr(ex, "REGISTRY", SpyRegistry(ex.REGISTRY))
        ans = executor.execute("M.OCC.003")
        assert ans.trust_level == "NOT_DETERMINABLE"
        assert called == [], f"calculator lookup happened for a refused metric: {called}"

    def test_a_permitted_metric_does_reach_its_calculator(self, executor, monkeypatch):
        """Control for the test above -- proves the sentinel can actually fire, so its silence
        for M.OCC.003 is evidence of the short-circuit rather than of a broken spy."""
        import engine.execution as ex

        called = []

        class SpyRegistry(dict):
            def get(self, key, default=None):
                called.append(key)
                return dict.get(self, key, default)

        monkeypatch.setattr(ex, "REGISTRY", SpyRegistry(ex.REGISTRY))
        executor.execute("M.REV.001")
        assert called == ["M.REV.001"]


class TestMetricMixingPrevention:
    """ai_analytics_architecture.md 7."""

    def test_same_family_arithmetic_is_refused(self, gate):
        ok, level, reasons = gate.authorize_combination(["M.AR.001A", "M.AR.001C"])
        assert ok is False
        assert any("Cross-family arithmetic refused" in r for r in reasons)

    def test_revenue_minus_expenses_inherits_profits_block(self, gate):
        """The most important mixing guard: 'profit' must not be reconstructible as
        SAFE-revenue minus SAFE-expenses, which would bypass M.PROFIT.001's BLOCK verdict."""
        ok, level, reasons = gate.authorize_combination(["M.REV.001", "M.EXP.001"])
        assert ok is False
        assert level == "BLOCK"
        assert any("M.PROFIT.001" in r for r in reasons)

    def test_documented_safe_composite_is_permitted(self, gate):
        """M.PNL.001 documents M.REV.002 + M.EXP.001 and is itself SAFE, so that specific
        combination must be allowed -- the guard must not be a blanket refusal."""
        ok, level, reasons = gate.authorize_combination(["M.REV.002", "M.EXP.001"])
        assert ok is True, reasons
        assert level == "SAFE"

    def test_undocumented_combination_is_refused(self, gate):
        ok, level, reasons = gate.authorize_combination(["M.OCC.001", "M.PROFIT.001"])
        assert ok is False
        assert any("Undocumented combination" in r for r in reasons)

    def test_block_input_poisons_any_composite(self, gate):
        ok, level, reasons = gate.authorize_combination(["M.REV.001", "M.PROFIT.001"])
        assert ok is False
        assert level == "BLOCK"

    def test_date_basis_extraction_compares_columns_not_prose(self, registry):
        """M.REV.001 and M.EXP.001 describe entry_date with different prose but share the same
        underlying column -- comparing the raw strings would produce a false mixing refusal."""
        a = date_basis_columns(registry.get("M.REV.001").date_field)
        b = date_basis_columns(registry.get("M.EXP.001").date_field)
        assert a == b == {"entry_date"}

    def test_date_basis_is_empty_for_snapshot_metrics(self, registry):
        """'Not applicable (a current-value column, not an event)' names no date column. An
        unknown basis must assert nothing about mixing rather than be treated as different."""
        assert date_basis_columns(registry.get("M.AR.001C").date_field) == set()
