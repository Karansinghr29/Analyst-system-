"""
ai_evaluation_framework.md 1.3 -- Conflict/DQ propagation correctness, tested in BOTH
directions as that section requires:

  "For every downgrade documented in metric_dependency_graph.md 6 ... confirm the
   implementation's composite/dependent metrics inherit the correct (worst-of-inputs) trust
   level -- and, equally important, confirm the explicitly-not-asserted non-dependencies in that
   section's closing paragraph are respected ... A false-positive downgrade (over-cautious,
   marking a genuinely SAFE metric as DISCLOSE) is also a defect, not merely a false negative --
   both directions must be tested."
"""
import pytest

from engine import propagation
from engine.propagation import (PROPAGATION_TABLE, EXPLICIT_NON_DEPENDENCIES, NOT_SAFE,
                                audit, contributes, documented_floor)

_SEVERITY = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}


class TestDocumentedDowngrades:
    """Direction 1: every downgrade the graph documents must actually be present."""

    def test_full_table_audit_is_clean(self, registry):
        result = audit(registry)
        assert result.clean, result.summary() + "\n" + "\n".join(
            result.missing_downgrades + result.false_downgrades + result.unknown_metric_ids)

    @pytest.mark.parametrize("metric_id,expected", [
        ("M.AR.001A", "SHOW_BOTH"), ("M.AR.001B", "SHOW_BOTH"),
        ("M.AR.001C", "BLOCK"), ("M.AR.001D", "BLOCK"),
        ("M.OWN.002", "SHOW_BOTH"), ("M.PROFIT.001", "BLOCK"),
        ("M.INV.001", "DISCLOSE"), ("M.EXP.002", "DISCLOSE"),
        ("M.OCC.001", "SHOW_BOTH"), ("M.OCC.002", "SHOW_BOTH"), ("M.OCC.005", "SHOW_BOTH"),
        ("M.EB.001", "DISCLOSE"), ("M.EB.002", "DISCLOSE"),
        ("M.DEP.002", "DISCLOSE"), ("M.DEP.003", "DISCLOSE"),
        ("M.RISK.002", "DISCLOSE"), ("M.RISK.003", "DISCLOSE"),
        ("M.RISK.004", "DISCLOSE"), ("M.RISK.005", "DISCLOSE"), ("M.RISK.007", "DISCLOSE"),
        ("M.COL.003", "DISCLOSE"), ("M.INV.002", "DISCLOSE"),
    ])
    def test_each_documented_downgrade_is_at_least_as_strict(self, registry, metric_id, expected):
        actual = registry.get(metric_id).trust_level
        assert _SEVERITY[actual] >= _SEVERITY[expected], (
            f"{metric_id}: metric_dependency_graph.md 6 documents {expected}, registry has "
            f"{actual} -- weaker than documented.")

    def test_every_table_row_names_only_real_metric_ids(self, registry):
        for rule in PROPAGATION_TABLE:
            for mid in list(rule.downgrades) + list(rule.preserved):
                assert mid in registry, (
                    f"{'/'.join(rule.upstream_ids)} names {mid!r}, which is not in "
                    f"semantic_metric_registry.csv.")

    def test_gate_raises_effective_level_to_the_documented_floor(self, registry):
        """The gate's third trust input. For every metric the graph downgrades, the gate's
        effective level must be at least the documented floor -- never below it."""
        from engine.gate import TrustGate
        gate = TrustGate(registry)
        for rule in PROPAGATION_TABLE:
            for mid, expected in rule.downgrades.items():
                if mid not in registry:
                    continue
                floor = documented_floor(mid)
                eff = gate.authorize(mid).effective_level
                assert _SEVERITY[eff] >= _SEVERITY[floor], (
                    f"{mid}: gate returned {eff}, below the documented floor {floor}.")


class TestExplicitNonDependencies:
    """Direction 2: an over-cautious downgrade is equally a defect."""

    def test_dq003_does_not_downgrade_staying_and_on_notice_counts(self, registry):
        """H.013 proves 0 overlap specifically for the Staying and On-Notice statuses, so
        DQ.003's overlapping-allotment finding must NOT reach M.TEN.001/M.TEN.002."""
        for mid in ("M.TEN.001", "M.TEN.002"):
            assert registry.get(mid).trust_level == "SAFE", (
                f"{mid}: false-positive downgrade -- DQ.003 is an explicit non-dependency.")
            assert not contributes("DQ.003", mid)

    def test_c023_does_not_downgrade_maintenance_cost(self, registry):
        """C.023 was checked and DISPROVEN for this dataset (both maintenance-cost paths agree
        exactly). M.MAINT.002 carries C.023 in its conflict_ids and must still be SAFE -- the
        canonical proof that carrying a conflict id is not itself a downgrade."""
        for mid in ("M.MAINT.001", "M.MAINT.002"):
            assert registry.get(mid).trust_level == "SAFE"
            assert not contributes("C.023", mid)
        assert "C.023" in registry.get("M.MAINT.002").conflict_ids

    def test_dq028_does_not_reach_the_ledger_derived_metrics(self, registry):
        """EB's billing_month format cannot affect entry_date-based ledger reconstruction."""
        for mid in ("M.PROFIT.001", "M.EXP.001", "M.EXP.002"):
            assert not contributes("DQ.028", mid), (
                f"{mid}: DQ.028 is an explicit non-dependency but an edge was asserted.")
        assert registry.get("M.EXP.001").trust_level == "SAFE"

    def test_carrying_a_conflict_id_does_not_imply_a_downgrade(self, registry):
        """The single most important false-positive guard. Four metrics carry a conflict_id or
        dq_id and are nonetheless correctly SAFE. An implementation that downgraded on the mere
        presence of an id would fail ai_evaluation_framework.md 1.3."""
        safe_but_flagged = {
            "M.LIFE.004": "C.001",    # single-convention use, disclosed
            "M.MAINT.002": "C.023",   # checked and disproven for this dataset
            "M.TEN.001": "DQ.003",    # H.013 proves 0 overlap for this status
            "M.TB.001": "C.002",      # the two reversal conventions are proven identical
        }
        for mid, flag in safe_but_flagged.items():
            spec = registry.get(mid)
            assert spec.trust_level == "SAFE", f"{mid} should be SAFE despite carrying {flag}"
            assert flag in (tuple(spec.conflict_ids) + tuple(spec.dq_ids))

    def test_not_determinable_is_not_treated_as_a_downgrade(self, registry):
        """M.OCC.003/M.OCC.004 are NOT_DETERMINABLE because no exported reference exists to
        validate them (status ACTIVE_UNVERIFIED) -- a validation-coverage statement, not a
        conflict-driven downgrade. The audit must not report them as false positives."""
        for mid in ("M.OCC.003", "M.OCC.004"):
            assert registry.get(mid).trust_level == "NOT_DETERMINABLE"
        assert audit(registry).clean


class TestDeclaredDivergences:
    """Where two completed specification documents imply different trust levels for the same
    metric, the engine takes the STRICTER posture and declares the divergence -- it never
    silently resolves one, in either direction."""

    def test_ar002_divergence_is_declared(self):
        d = propagation.declared_divergence("M.AR.002")
        assert d is not None
        assert d.registry_level == "SHOW_BOTH"
        assert d.implied_level == "BLOCK"
        assert d.applied_level == "BLOCK"
        assert "ai_trust_policy.md" in d.evidence

    def test_the_stricter_posture_is_what_actually_applies(self, registry, executor):
        """metric_dependency_graph.md 7's worst-of-inputs rule and ai_trust_policy.md 3's named
        'How much does this tenant owe?' scenario both require BLOCK for per-tenant dues."""
        ans = executor.execute("M.AR.002")
        assert ans.trust_level == "BLOCK"
        assert ans.headline is None
        assert registry.get("M.AR.002").trust_level == "SHOW_BOTH"   # registry left untouched

    def test_no_divergence_ever_loosens_a_posture(self, registry):
        sev = _SEVERITY
        for d in propagation.DECLARED_TRUST_DIVERGENCES:
            assert sev[d.applied_level] >= sev[d.registry_level], (
                f"{d.metric_id}: a divergence may only tighten, never loosen.")
            assert sev[d.applied_level] >= sev[d.implied_level]

    def test_every_divergence_cites_its_evidence(self):
        for d in propagation.DECLARED_TRUST_DIVERGENCES:
            assert len(d.evidence) > 80
            assert ".md" in d.evidence


class TestPropagationJustification:
    def test_every_non_safe_metric_can_explain_itself(self, registry):
        """Auditability: a non-SAFE metric must either be named in the 6 table or carry its own
        conflict/dq ids -- a trust level with no traceable cause is unauditable."""
        for mid in registry.all_ids():
            spec = registry.get(mid)
            if spec.trust_level == "SAFE":
                continue
            has_cause = (documented_floor(mid) is not None
                         or spec.conflict_ids or spec.dq_ids
                         or spec.trust_level == "NOT_DETERMINABLE")
            assert has_cause, f"{mid}: {spec.trust_level} with no traceable cause."

    def test_justification_text_names_the_upstream_finding(self, registry):
        text = propagation.justification("M.PROFIT.001")
        assert "DQ.016" in text and "BLOCK" in text

    def test_justification_is_explicit_when_no_row_applies(self):
        text = propagation.justification("M.LIFE.004")
        assert "No metric_dependency_graph.md 6 propagation row downgrades" in text
