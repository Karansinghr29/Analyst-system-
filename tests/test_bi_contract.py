"""
Phase 6: the BI-consumable semantic contract.

A BI tool's native idiom is one number per tile, and that idiom is exactly what a SHOW_BOTH or
BLOCK metric must not be rendered into. So the contract makes the refusal machine-readable:
`headline_permitted=false` plus a `render_directive`. A dashboard that ignores it and renders
`definitions[0]` has violated the contract, and `validate_card` catches that in CI rather than
leaving an owner to read a wrong number off a tile.
"""
import pytest

from engine.bi_contract import (BIContractBuilder, validate_card, validate_dashboard,
                                REQUIRED_CARD_FIELDS, RENDER_SINGLE_VALUE,
                                RENDER_MULTI_DEFINITION, RENDER_BLOCKED,
                                RENDER_NOT_DETERMINABLE)
from engine.result import NOT_DETERMINABLE_TEXT

_CACHE = {}


@pytest.fixture(scope="module")
def bi(registry):
    return BIContractBuilder(registry=registry)


@pytest.fixture(scope="module")
def all_cards(bi, registry):
    if "cards" not in _CACHE:
        _CACHE["cards"] = tuple(bi.card(m) for m in registry.all_ids())
    return _CACHE["cards"]


class TestCardCompleteness:
    def test_every_metric_produces_a_valid_card(self, all_cards):
        problems = validate_dashboard(all_cards)
        assert problems == {}, problems

    def test_every_required_field_is_exposed(self, all_cards):
        for c in all_cards:
            d = c.as_dict()
            for f in REQUIRED_CARD_FIELDS:
                assert f in d, f"{c.metric_id}: missing {f}"

    def test_every_card_carries_its_definition_and_trace(self, all_cards):
        for c in all_cards:
            assert c.definition.strip(), f"{c.metric_id}: no definition"
            assert c.calculation_trace.strip(), f"{c.metric_id}: no calculation trace"

    def test_every_card_carries_a_trust_level(self, all_cards):
        for c in all_cards:
            assert c.trust_level in ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK",
                                     "NOT_DETERMINABLE")

    def test_cards_expose_dq_and_conflict_indicators(self, all_cards):
        """A dashboard must be able to render a data-quality indicator without a second query."""
        conflicted = [c for c in all_cards if c.trust_level in ("SHOW_BOTH", "BLOCK")]
        assert conflicted
        for c in conflicted:
            assert c.conflicts or c.dq_issues


class TestRenderDirectives:
    def test_safe_cards_permit_a_single_value(self, bi):
        c = bi.card("M.REV.001")
        assert c.headline_permitted is True
        assert c.render_directive == RENDER_SINGLE_VALUE
        assert c.value is not None

    def test_show_both_cards_forbid_a_headline(self, bi):
        c = bi.card("M.OCC.001")
        assert c.headline_permitted is False
        assert c.value is None
        assert c.render_directive == RENDER_MULTI_DEFINITION
        assert len(c.definitions) >= 2

    def test_block_cards_forbid_a_headline_and_name_the_conflict(self, bi):
        c = bi.card("M.PROFIT.001")
        assert c.headline_permitted is False
        assert c.value is None
        assert c.render_directive == RENDER_BLOCKED
        assert c.conflicts

    def test_not_determinable_cards_use_the_exact_phrase(self, bi):
        c = bi.card("M.OCC.003")
        assert c.render_directive == RENDER_NOT_DETERMINABLE
        assert NOT_DETERMINABLE_TEXT in c.not_determinable_reason
        assert c.value is None

    def test_unknown_metric_yields_a_not_determinable_card(self, bi):
        c = bi.card("M.NOPE.001")
        assert c.headline_permitted is False
        assert NOT_DETERMINABLE_TEXT in c.not_determinable_reason

    def test_disclose_cards_carry_their_caveat(self, all_cards):
        for c in all_cards:
            if c.trust_level == "DISCLOSE":
                assert c.caveat.strip(), f"{c.metric_id}: DISCLOSE card with no caveat"


class TestContractCatchesDashboardViolations:
    """The validator must actually fail on a bad card, or it proves nothing."""

    def test_a_show_both_card_rendering_a_headline_is_caught(self, bi):
        c = bi.card("M.OCC.001")
        c.headline_permitted = True
        c.value = c.definitions[0][1]
        problems = validate_card(c)
        assert any("permits a headline" in p for p in problems)
        assert any("carries a single value" in p for p in problems)

    def test_a_block_card_without_conflicts_is_caught(self, bi):
        c = bi.card("M.PROFIT.001")
        c.conflicts = ()
        assert any("names no conflict" in p for p in validate_card(c))

    def test_a_collapsed_definition_set_is_caught(self, bi):
        c = bi.card("M.AR.001A")
        c.definitions = c.definitions[:1]
        assert any("definition(s)" in p for p in validate_card(c))

    def test_a_disclose_card_stripped_of_its_caveat_is_caught(self, bi):
        c = bi.card("M.EB.001")
        c.caveat = ""
        assert any("no caveat" in p for p in validate_card(c))

    def test_a_value_without_evidence_is_caught(self, bi):
        c = bi.card("M.REV.001")
        c.evidence = ()
        assert any("no evidence" in p for p in validate_card(c))


class TestDashboardAssembly:
    def test_a_dashboard_of_mixed_trust_validates(self, bi):
        cards = bi.dashboard(("M.REV.001", "M.OCC.001", "M.PROFIT.001", "M.EB.001",
                              "M.OCC.003"))
        assert validate_dashboard(cards) == {}

    def test_cards_are_serializable(self, bi):
        import json
        c = bi.card("M.OCC.001")
        payload = json.dumps(c.as_dict(), default=str)
        assert "headline_permitted" in payload
        assert "render_directive" in payload

    def test_the_contract_is_deterministic(self, bi):
        a, b = bi.card("M.REV.001"), bi.card("M.REV.001")
        assert a.as_dict()["value"] == b.as_dict()["value"]
        assert a.render_directive == b.render_directive
