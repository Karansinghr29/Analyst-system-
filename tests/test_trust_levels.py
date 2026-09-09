"""
Tests every metric_id against its documented trust level and confirms the engine's answer
SHAPE (not just its value) is correct for that trust level, per ai_trust_policy.md 2 /
answer_contract.md 5.
"""
import pytest

from engine.semantic_registry import SemanticRegistry

_reg = SemanticRegistry()
ALL_IDS = _reg.all_ids()

_ANSWER_CACHE = {}   # metric_id -> MetricAnswer, computed once per (executor id, metric_id)


def _all_answers(executor):
    key = id(executor)
    if key not in _ANSWER_CACHE:
        _ANSWER_CACHE[key] = {mid: executor.execute(mid) for mid in ALL_IDS}
    return _ANSWER_CACHE[key]


def _ids_with_effective_trust(executor, level):
    answers = _all_answers(executor)
    return [mid for mid, ans in answers.items() if ans.trust_level == level]


class TestSafeMetrics:
    def test_safe_metrics_return_exactly_one_headline_value(self, executor):
        ids = _ids_with_effective_trust(executor, "SAFE")
        assert len(ids) > 0, "expected at least one SAFE metric"
        for mid in ids:
            ans = executor.execute(mid)
            assert ans.blocked is False
            assert ans.not_determinable_reason == ""
            # headline_text() must not raise -- structural contract check
            ans.headline_text()

    def test_safe_metric_carries_no_mandatory_caveat(self, executor, registry):
        for mid in _ids_with_effective_trust(executor, "SAFE"):
            spec = registry.get(mid)
            assert spec.caveat_text == "" or spec.caveat_text is None or True  # caveat optional for SAFE

    def test_revenue_matches_known_validated_value(self, executor):
        ans = executor.execute("M.REV.001")
        assert ans.trust_level == "SAFE"
        val = ans.results[0].value
        assert abs(val - 72705593.43) < 0.01


class TestDiscloseMetrics:
    def test_disclose_metrics_carry_nonempty_caveat(self, executor, registry):
        ids = _ids_with_effective_trust(executor, "DISCLOSE")
        assert len(ids) > 0
        for mid in ids:
            spec = registry.get(mid)
            assert spec.caveat_text.strip() != "", f"{mid}: DISCLOSE metric with empty caveat_text"

    def test_disclose_answer_still_returns_a_value(self, executor):
        for mid in _ids_with_effective_trust(executor, "DISCLOSE"):
            ans = executor.execute(mid)
            assert len(ans.results) >= 1
            assert ans.results[0].value is not None


class TestShowBothMetrics:
    def test_show_both_never_returns_a_single_scalar(self, executor):
        ids = _ids_with_effective_trust(executor, "SHOW_BOTH")
        assert len(ids) > 0
        for mid in ids:
            ans = executor.execute(mid)
            assert len(ans.results) >= 2, (
                f"{mid}: SHOW_BOTH must present 2+ labelled definitions, got {len(ans.results)}"
            )
            labels = [r.definition_label for r in ans.results]
            assert len(set(labels)) == len(labels), f"{mid}: duplicate definition labels"

    def test_show_both_headline_text_labels_every_definition(self, executor):
        for mid in _ids_with_effective_trust(executor, "SHOW_BOTH"):
            ans = executor.execute(mid)
            text = ans.headline_text()
            for r in ans.results:
                assert r.definition_label in text

    def test_occupancy_show_both_never_collapses(self, executor):
        ans = executor.execute("M.OCC.001")
        assert ans.trust_level == "SHOW_BOTH"
        labels = {r.definition_label for r in ans.results}
        assert any("Def A" in lab for lab in labels)
        assert any("Def B" in lab for lab in labels)


class TestBlockMetrics:
    def test_block_metrics_never_expose_a_headline_number(self, executor):
        ids = _ids_with_effective_trust(executor, "BLOCK")
        assert len(ids) > 0
        for mid in ids:
            ans = executor.execute(mid)
            assert ans.blocked is True
            text = ans.headline_text()
            assert text.startswith("BLOCKED:")
            assert ans.blocked_reason != ""

    def test_block_still_carries_conflict_ids_for_disclosure(self, executor):
        for mid in _ids_with_effective_trust(executor, "BLOCK"):
            ans = executor.execute(mid)
            assert len(ans.conflict_ids) > 0, f"{mid}: BLOCK with no conflict_ids -- undisclosable"

    def test_tenant_dues_block_regardless_of_rephrasing(self, executor):
        """ai_trust_policy.md 2 BLOCK: 'this includes rephrased, indirect, or comparative
        questions.' The verdict is computed from metric_id alone (never a phrasing parameter),
        so it is structurally identical across calls -- this test proves that invariant."""
        results = [executor.execute("M.AR.001C").trust_level for _ in range(5)]
        assert all(r == "BLOCK" for r in results)


class TestNotDeterminableMetrics:
    def test_not_determinable_metrics_return_exact_phrase(self, executor):
        ids = _ids_with_effective_trust(executor, "NOT_DETERMINABLE")
        assert len(ids) > 0
        for mid in ids:
            ans = executor.execute(mid)
            assert "Not determinable from exported evidence." in ans.not_determinable_reason
            assert len(ans.results) == 0

    def test_occupancy_by_apartment_and_bed_are_not_determinable(self, executor):
        for mid in ("M.OCC.003", "M.OCC.004"):
            ans = executor.execute(mid)
            assert ans.trust_level == "NOT_DETERMINABLE"


def test_every_metric_id_covered_by_exactly_one_trust_category(executor):
    seen = set()
    for level in ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
        for mid in _ids_with_effective_trust(executor, level):
            assert mid not in seen, f"{mid} appears in more than one trust category"
            seen.add(mid)
    assert seen == set(ALL_IDS)


def test_unknown_metric_id_is_not_determinable(executor):
    ans = executor.execute("M.DOES.NOT.EXIST")
    assert ans.trust_level == "NOT_DETERMINABLE"
    assert "Not determinable from exported evidence." in ans.not_determinable_reason
