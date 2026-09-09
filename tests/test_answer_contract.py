"""
answer_contract.md as an enforced checklist, plus ai_evaluation_framework.md 1.4's
citation-completeness requirement and 1.5's determinism requirement.

answer_contract.md 1: "An answer missing any required field below is **incomplete**, not merely
under-detailed -- the architecture must not emit it."
"""
import pytest

from engine import contract as contract_mod
from engine import confidence as confidence_mod
from engine.citation import chain_for
from engine.result import NOT_DETERMINABLE_TEXT

_ANSWERS = {}


def _answers(executor, registry):
    key = id(executor)
    if key not in _ANSWERS:
        _ANSWERS[key] = {mid: executor.execute(mid) for mid in registry.all_ids()}
    return _ANSWERS[key]


class TestContractCompleteness:
    def test_every_metric_produces_a_complete_answer_contract(self, executor, registry):
        failures = []
        for mid, ans in _answers(executor, registry).items():
            report = contract_mod.validate(ans, registry.get(mid))
            if not report.complete:
                failures.append(report.summary())
        assert not failures, "\n".join(failures)

    def test_answers_carry_no_attached_violations(self, executor, registry):
        """The executor attaches violations rather than repairing them, so a non-empty list
        here means an answer was emitted incomplete."""
        for mid, ans in _answers(executor, registry).items():
            assert ans.contract_violations == (), f"{mid}: {ans.contract_violations}"

    def test_required_fields_present_on_every_answer(self, executor, registry):
        for mid, ans in _answers(executor, registry).items():
            assert ans.trust_level, f"{mid}: no trust posture"
            assert ans.confidence, f"{mid}: no confidence"
            assert ans.metric_id, f"{mid}: no metric provenance"
            assert isinstance(ans.follow_up, tuple), f"{mid}: no follow-up affordance field"

    def test_every_numeric_answer_states_its_as_of_basis(self, executor, registry):
        for mid, ans in _answers(executor, registry).items():
            for r in ans.results:
                if r.value is not None:
                    assert r.as_of, f"{mid}/{r.definition_label}: no as-of date basis"


class TestContractShapeRules:
    """answer_contract.md 5."""

    def test_show_both_is_structurally_a_list(self, executor, registry):
        for mid, ans in _answers(executor, registry).items():
            if ans.trust_level == "SHOW_BOTH":
                assert len(ans.results) >= 2, f"{mid}: SHOW_BOTH flattened to {len(ans.results)}"
                assert ans.confidence == "SPLIT"

    def test_block_headline_is_null_but_components_are_labelled(self, executor, registry):
        for mid, ans in _answers(executor, registry).items():
            if ans.trust_level == "BLOCK":
                assert ans.headline is None
                assert ans.confidence == "BLOCKED"
                assert ans.conflict_ids
                for r in ans.results:
                    assert r.definition_label

    def test_disclose_caveat_is_carried_verbatim(self, executor, registry):
        """ai_evaluation_framework.md 1.2: the caveat's content 'must not be dropped or
        diluted.'"""
        n = 0
        for mid, ans in _answers(executor, registry).items():
            if ans.trust_level == "DISCLOSE":
                n += 1
                assert ans.caveat.strip() == registry.get(mid).caveat_text.strip()
                assert ans.caveat.strip() != ""
        assert n > 0

    def test_not_determinable_uses_the_exact_phrase_and_is_specific(self, executor, registry):
        for mid, ans in _answers(executor, registry).items():
            if ans.trust_level == "NOT_DETERMINABLE":
                assert NOT_DETERMINABLE_TEXT in ans.not_determinable_reason
                assert len(ans.results) == 0
                assert ans.confidence == "UNVERIFIED"
                # 5: "not a generic 'no data'"
                assert len(ans.not_determinable_reason) > len(NOT_DETERMINABLE_TEXT) + 20

    def test_contract_validator_actually_catches_a_broken_answer(self, executor):
        """A checklist that never fails proves nothing. Flatten a SHOW_BOTH answer and confirm
        the validator rejects it."""
        ans = executor.execute("M.OCC.001")
        ans.results = ans.results[:1]
        report = contract_mod.validate(ans)
        assert not report.complete
        assert any("SHOW_BOTH" in v for v in report.violations)


class TestConfidenceModel:
    """answer_contract.md 3."""

    def test_confidence_label_matches_the_documented_table(self, executor, registry):
        expected = {"SHOW_BOTH": "SPLIT", "BLOCK": "BLOCKED", "NOT_DETERMINABLE": "UNVERIFIED"}
        for mid, ans in _answers(executor, registry).items():
            if ans.trust_level in expected:
                assert ans.confidence == expected[ans.trust_level], mid
            elif ans.trust_level == "DISCLOSE":
                assert ans.confidence == "MEDIUM", mid
            else:
                assert ans.confidence.startswith("HIGH"), f"{mid}: {ans.confidence}"

    def test_confidence_is_never_a_blended_number(self, executor, registry):
        """3: confidence 'must never be flattened into one number that hides a SHOW_BOTH/BLOCK
        situation.' No confidence label may be numeric."""
        for mid, ans in _answers(executor, registry).items():
            assert not ans.confidence.strip().rstrip("%").replace(".", "").isdigit(), mid

    def test_unvalidated_safe_metric_is_not_framed_as_validated(self, executor):
        """ai_agent_roles.md Validator: 'must never present an unverified result with the same
        confidence framing as a validated one.' M.CASH.001 has no exported reference."""
        validated = executor.execute("M.REV.001")
        unvalidated = executor.execute("M.CASH.001")
        assert validated.trust_level == unvalidated.trust_level == "SAFE"
        assert validated.confidence == "HIGH"
        assert unvalidated.confidence != "HIGH"
        assert "not independently re-validated" in unvalidated.confidence

    def test_the_safe_plus_differs_gap_is_declared_not_hidden(self, executor):
        """answer_contract.md 3's table has no SAFE+DIFFERS row. M.REV.002 is exactly that
        case. The implementation must surface the gap rather than quietly pick a label."""
        assert any(combo[:2] == ("SAFE", "DIFFERS")
                   for combo in confidence_mod.UNCOVERED_COMBINATIONS)
        ans = executor.execute("M.REV.002")
        assert ans.trust_level == "SAFE"
        assert "DIFFERS" in ans.confidence


class TestEvidenceCitation:
    """answer_contract.md 2 / ai_evaluation_framework.md 1.4 citation-completeness."""

    def test_every_cited_number_carries_a_metric_id_and_evidence(self, executor, registry):
        for mid, ans in _answers(executor, registry).items():
            for r in ans.results:
                if r.value is None:
                    continue
                assert r.metric_id, "a number with no metric_id"
                assert r.citations or r.evidence_sources, (
                    f"{mid}/{r.definition_label}: uncited number -- a defect regardless of "
                    f"whether the number is correct (1.4).")

    def test_citation_chain_resolves_to_manifest_keys(self, registry):
        """2's four-layer chain: metric_id -> source_objects -> file_manifest key ->
        validation_reference. 49 of 50 metrics resolve; M.RISK.009's declared source is this
        project's OWN output (metric_registry.csv), which is correctly not evidence."""
        incomplete = [mid for mid in registry.all_ids()
                      if not chain_for(registry.get(mid)).complete]
        assert incomplete == ["M.RISK.009"], incomplete

    def test_unresolvable_objects_are_reported_not_dropped(self, registry):
        """A dropped citation would make an uncited number look cited."""
        chain = chain_for(registry.get("M.RISK.009"))
        assert chain.unresolved
        assert all(c.note for c in chain.unresolved)

    def test_a_resolved_citation_names_a_real_exported_file(self, registry):
        chain = chain_for(registry.get("M.REV.001"))
        assert "T.journal_lines" in chain.resolved_keys
        assert "F.001" in chain.resolved_keys
        for c in chain.citations:
            if c.resolved:
                assert c.file.endswith(".csv")


class TestDeterminism:
    """ai_evaluation_framework.md 1.5 / answer_contract.md 6."""

    def test_identical_query_produces_an_identical_answer_object(self, executor, registry):
        """Compared over contract_identity(), which excludes the wall-clock `computed_at`
        stamp -- that field differs on every call by construction, so determinism is asserted
        over everything else."""
        for mid in registry.all_ids():
            a, b = executor.execute(mid), executor.execute(mid)
            assert a.contract_identity() == b.contract_identity(), mid

    def test_show_both_returns_the_same_definition_set_each_time(self, executor):
        a = executor.execute("M.OCC.001")
        b = executor.execute("M.OCC.001")
        assert [r.definition_label for r in a.results] == [r.definition_label for r in b.results]

    def test_computed_at_is_the_only_nondeterministic_field(self, executor):
        """States the exception explicitly rather than leaving it implicit -- answer_contract.md
        6 says 'an identical answer object', and this is the one field that cannot satisfy it."""
        a = executor.execute("M.REV.001")
        b = executor.execute("M.REV.001")
        assert a.results[0].computed_at != b.results[0].computed_at
        assert a.results[0].contract_identity() == b.results[0].contract_identity()
