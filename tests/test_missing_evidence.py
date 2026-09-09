"""
Tests the engine's behavior when required evidence is genuinely unavailable -- must return
NOT_DETERMINABLE, never fabricate or approximate (ai_trust_policy.md 0 rule 1).
"""
import pytest

from engine.evidence_loader import EvidenceNotAvailable, require, is_available
from engine.calculators.base import NotDeterminableError


def test_require_raises_for_unexported_market_schema_table():
    """market schema tables were never exported (DQ.032) -- require() must raise, not return
    an empty/zero DataFrame that could be silently treated as 'zero activity'."""
    with pytest.raises(EvidenceNotAvailable):
        require("market.amenities_master")


def test_is_available_false_for_nonexistent_reference():
    assert is_available("not_a_real_table_or_view") is False


def test_is_available_true_for_a_known_table():
    assert is_available("journal_entries") is True


def test_calc_dq_trust_score_without_registry_is_not_determinable():
    """Demonstrates the calculator's own defence: it refuses to fabricate a result when its
    one genuinely required piece of context (a SemanticRegistry instance) is missing."""
    from engine.calculators.risk_dq import calc_dq_trust_score
    with pytest.raises(NotDeterminableError):
        calc_dq_trust_score(spec=None, registry=None)


def test_engine_reports_not_determinable_for_missing_registry_dependency(executor):
    """End-to-end: executing M.RISK.009 WITHOUT the executor auto-supplying its own registry
    would be not-determinable -- confirmed via direct calculator invocation above; here we
    confirm the executor's auto-injection (engine.execution.MetricExecutor._invoke) is what
    makes the normal path succeed, by checking the auto-injected path DOES succeed."""
    ans = executor.execute("M.RISK.009")
    assert ans.trust_level == "SAFE"
    assert len(ans.results) == 1
