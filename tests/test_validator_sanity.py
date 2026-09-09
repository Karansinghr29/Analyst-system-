"""
The Validator role (ai_agent_roles.md 2) and the Validation stage
(analytics_execution_spec.md 8 / ai_analytics_architecture.md 9).

8's non-negotiable rule: "A result that fails an internal sanity check must never be silently
emitted ... a violation here would indicate an execution-engine bug, not a business fact, and
must halt rather than answer."
"""
import math

import pytest

from engine.validator import (Validator, SanityCheckFailure, check_finite,
                              check_non_negative_count, check_ledger_balanced,
                              check_grain_consistency, _ledger_totals)


class TestSanityChecksHalt:
    def test_nan_value_halts_rather_than_answers(self, registry):
        v = Validator()
        with pytest.raises(SanityCheckFailure) as e:
            v.validate(registry.get("M.REV.001"), float("nan"), "INR")
        assert "finite_numeric" in str(e.value)

    def test_infinity_halts(self, registry):
        v = Validator()
        with pytest.raises(SanityCheckFailure):
            v.validate(registry.get("M.REV.001"), float("inf"), "INR")

    def test_negative_count_halts(self, registry):
        v = Validator()
        with pytest.raises(SanityCheckFailure) as e:
            v.validate(registry.get("M.TEN.001"), -3, "count of tenants")
        assert "non_negative_count" in str(e.value)

    def test_nan_nested_in_a_grouped_result_also_halts(self, registry):
        v = Validator()
        with pytest.raises(SanityCheckFailure):
            v.validate(registry.get("M.REV.002"), {"2024-01": 5.0, "2024-02": float("nan")}, "INR")

    def test_halt_can_be_disabled_only_explicitly(self, registry):
        """The engine never does this; the flag exists so a diagnostic caller can INSPECT a
        failing result rather than being unable to see it at all."""
        v = Validator()
        verdict = v.validate(registry.get("M.REV.001"), float("nan"), "INR",
                             halt_on_sanity_failure=False)
        assert verdict.sanity_passed is False


class TestSanityCheckSemantics:
    def test_negative_money_is_allowed(self):
        """A credit balance or a net loss is a legitimate negative. Only declared COUNTS are
        constrained -- over-applying the check would reject real business facts."""
        c = check_non_negative_count(-5000.0, "INR")
        assert c.applicable is False and c.passed is True

    def test_negative_count_is_rejected(self):
        c = check_non_negative_count(-1, "count of beds")
        assert c.applicable is True and c.passed is False

    def test_ledger_debit_equals_credit_across_the_whole_export(self):
        """business_dimensions.md 21 / enforce_journal_balanced. This identity holding is what
        licenses every ledger-derived metric in the registry."""
        debit, credit = _ledger_totals()
        assert abs(debit - credit) < 0.01
        assert debit > 0

    def test_ledger_check_is_skipped_for_non_ledger_metrics(self, registry):
        c = check_ledger_balanced(registry.get("M.TEN.001").source_objects)
        assert c.applicable is False

    def test_ledger_check_applies_to_ledger_metrics(self, registry):
        c = check_ledger_balanced(registry.get("M.REV.001").source_objects)
        assert c.applicable is True and c.passed is True

    def test_grain_consistency_bounds_groups_by_source_population(self, registry):
        c = check_grain_consistency({"2024-01": 1.0, "2024-02": 2.0}, registry.get("M.REV.002"))
        assert c.passed is True

    def test_grain_consistency_states_when_it_cannot_bound(self, registry):
        """8's check must not invent an upper bound it cannot derive -- it says so instead."""
        c = check_grain_consistency({"a": 1}, registry.get("M.RISK.009"))
        assert c.applicable is False
        assert "not cheaply determinable" in c.detail or "not grouped" in c.detail

    def test_scalar_result_is_not_grain_checked(self, registry):
        c = check_grain_consistency(1234.5, registry.get("M.REV.001"))
        assert c.applicable is False


class TestValidatorReferenceComparison:
    def test_match_carries_the_actual_numbers_not_just_a_verdict(self, registry):
        """ai_analytics_architecture.md 9: 'compare reconstructed vs. reference, compute
        absolute/percentage difference' -- Phase 1 carried only the status string."""
        v = Validator()
        verdict = v.validate(registry.get("M.REV.001"), 72705593.43, "INR")
        assert verdict.status == "MATCH"
        assert verdict.reference_value == "72705593.43"
        assert verdict.absolute_difference == "0.00"
        assert verdict.reference_source
        assert "REV.01" in verdict.check_ids

    def test_differs_carries_its_documented_mechanism(self, registry):
        """8: a DIFFERS result 'must carry the same documented explanation, not present as if
        freshly validated.'"""
        v = Validator()
        verdict = v.validate(registry.get("M.RISK.007"), 214, "count of overlapping pairs")
        assert verdict.status == "DIFFERS"
        assert verdict.explanation.strip() != ""
        assert "DQ.003" in verdict.check_ids

    def test_no_reference_returns_unverified_never_match(self, registry):
        v = Validator()
        verdict = v.validate(registry.get("M.CASH.001"), 68690988.62, "INR")
        assert verdict.status == "UNVERIFIED"
        assert verdict.independently_validated is False
        assert "explicitly unverified" in verdict.explanation

    def test_every_metric_gets_a_verdict_from_the_documented_vocabulary(self, executor, registry):
        for mid in registry.all_ids():
            ans = executor.execute(mid)
            for r in ans.results:
                assert r.validation_status in ("MATCH", "DIFFERS", "PARTIAL", "UNVERIFIED",
                                               "NOT_DETERMINABLE"), f"{mid}: {r.validation_status}"

    def test_the_four_known_differs_cases_are_still_visible(self, executor, registry):
        """metric_reconstruction.md's 4 documented DIFFERS checks must remain surfaced, not
        quietly promoted to MATCH by the Phase 2 rewiring."""
        differing = {mid for mid in registry.all_ids()
                     for r in executor.execute(mid).results
                     if r.validation_status == "DIFFERS"}
        assert {"M.REV.002", "M.RISK.007"} <= differing

    def test_sanity_checks_are_attached_to_every_result(self, executor, registry):
        for mid in registry.all_ids():
            for r in executor.execute(mid).results:
                assert r.sanity_checks, f"{mid}: no sanity checks recorded"
                assert all(c.passed for c in r.sanity_checks if c.applicable)
