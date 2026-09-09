"""
Phase 6: the executive/management briefing.

insight_generation_spec.md 1 governs it: a briefing line is an answer the owner did not ask for,
"and it must satisfy every requirement a reactive answer does." So the three trust rules apply
unchanged, and the Phase 6 brief restates them for this surface:

    SHOW_BOTH        -> show both definitions
    BLOCK            -> no single headline number
    NOT_DETERMINABLE -> exactly "Not determinable from exported evidence."
"""
import pytest

from engine.executive_summary import (ExecutiveSummaryBuilder, render, ALL_SECTIONS,
                                      BUSINESS_HEALTH_KPIS, OPERATIONS_KPIS, RISK_KPIS,
                                      SECTION_BUSINESS_HEALTH, SECTION_RISKS,
                                      SECTION_ATTENTION, SECTION_WHAT_CHANGED)
from engine.result import NOT_DETERMINABLE_TEXT

_CACHE = {}


@pytest.fixture(scope="module")
def summary(registry):
    if "s" not in _CACHE:
        _CACHE["s"] = ExecutiveSummaryBuilder(registry=registry).build()
    return _CACHE["s"]


@pytest.fixture(scope="module")
def text(summary):
    if "t" not in _CACHE:
        _CACHE["t"] = render(summary)
    return _CACHE["t"]


class TestBriefingCoverage:
    def test_every_documented_section_is_present(self, summary):
        assert set(summary.populated_sections()) == set(ALL_SECTIONS)

    def test_business_health_covers_the_documented_kpis(self, summary):
        ids = [l.metric_id for l in summary.business_health]
        assert ids == list(BUSINESS_HEALTH_KPIS)

    def test_operations_covers_the_documented_kpis(self, summary):
        ids = [l.metric_id for l in summary.operations]
        assert ids == list(OPERATIONS_KPIS)

    def test_the_briefing_names_its_as_of_date(self, summary):
        assert "2026-08-29" in summary.generated_as_of

    def test_every_kpi_line_resolves_to_the_registry(self, summary, registry):
        for line in summary.business_health + summary.operations:
            assert line.metric_id in registry


class TestTrustRulesInTheBriefing:
    def test_no_conflicted_kpi_shows_a_single_figure(self, summary):
        for line in summary.business_health + summary.operations:
            if line.trust_level in ("SHOW_BOTH", "BLOCK"):
                assert line.presentable is False, f"{line.metric_id} showed a headline"
                assert line.value is None
                assert len(line.definitions) >= 2, (
                    f"{line.metric_id}: a conflict cannot be read from "
                    f"{len(line.definitions)} definition(s)")

    def test_profit_is_never_a_headline(self, summary, text):
        line = next(l for l in summary.business_health if l.metric_id == "M.PROFIT.001")
        assert line.trust_level == "BLOCK"
        assert line.presentable is False
        assert "no single figure" in line.render()

    def test_receivables_shows_all_four_definitions(self, summary):
        line = next(l for l in summary.business_health if l.metric_id == "M.AR.001A")
        assert len(line.definitions) == 4

    def test_occupancy_shows_every_definition(self, summary):
        line = next(l for l in summary.operations if l.metric_id == "M.OCC.001")
        assert len(line.definitions) >= 4
        assert line.presentable is False

    def test_disclose_kpis_carry_their_caveat(self, summary):
        for line in summary.business_health + summary.operations:
            if line.trust_level == "DISCLOSE" and line.presentable:
                assert line.caveat.strip(), f"{line.metric_id}: DISCLOSE with no caveat"

    def test_not_determinable_lines_use_the_exact_phrase(self, summary):
        for line in summary.business_health + summary.operations:
            if line.trust_level == "NOT_DETERMINABLE":
                assert NOT_DETERMINABLE_TEXT in line.render()

    def test_an_unshowable_kpi_is_still_listed(self, summary):
        """Omitting it would let the briefing read as 'nothing to report here'."""
        unshowable = [l for l in summary.business_health + summary.operations
                      if not l.presentable]
        assert unshowable
        for l in unshowable:
            assert l.reason.strip(), f"{l.metric_id}: withheld with no reason"

    def test_the_rendered_briefing_never_states_a_profit_figure_as_the_answer(self, text):
        block = text.split("BUSINESS HEALTH", 1)[1].split("OPERATIONS", 1)[0]
        profit_line = [l for l in block.splitlines() if "profit" in l.lower()]
        assert profit_line
        assert "no single figure" in profit_line[0]


class TestBriefingContent:
    def test_risks_are_ranked_findings(self, summary):
        assert summary.risks
        for r in summary.risks:
            assert r["insight_id"] and r["trust"] and r["observation"]

    def test_attention_required_names_owner_decisions(self, summary):
        assert summary.attention_required
        for a in summary.attention_required:
            assert a["trust"] in ("BLOCK", "SHOW_BOTH")
            assert "recommend" in a["decision"].lower()

    def test_what_changed_declares_materiality_undefined(self, summary, text):
        for c in summary.what_changed:
            assert NOT_DETERMINABLE_TEXT in c["materiality"]
        assert "materiality: undefined" in text

    def test_why_section_carries_labelled_stages(self, summary):
        for w in summary.why:
            for stage, _ in w["statements"]:
                assert stage in ("FACT", "CALCULATION", "OBSERVATION", "INFERENCE",
                                 "HYPOTHESIS", "RECOMMENDATION")

    def test_what_to_do_items_are_in_recommendation_register(self, summary):
        for a in summary.what_to_do:
            assert "recommend" in a["recommendation"].lower()

    def test_limitations_declare_the_undefined_materiality(self, summary):
        joined = " ".join(summary.limitations)
        assert "Materiality is undefined" in joined
        assert "anomaly" in joined.lower()

    def test_limitations_name_the_conflicted_kpis(self, summary):
        joined = " ".join(summary.limitations)
        assert "competing definitions" in joined

    def test_the_briefing_is_deterministic(self, registry):
        a = ExecutiveSummaryBuilder(registry=registry).build()
        b = ExecutiveSummaryBuilder(registry=registry).build()
        assert [l.metric_id for l in a.business_health] == \
               [l.metric_id for l in b.business_health]
        assert [r["insight_id"] for r in a.risks] == [r["insight_id"] for r in b.risks]

    def test_render_contains_every_section_heading(self, text):
        for section in ALL_SECTIONS:
            assert section in text
