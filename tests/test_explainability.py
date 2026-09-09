"""
Phase 6: explainability. "Why are you saying this?"

Phase 6 brief 14 fixes the chain:
    Question -> interpretation -> analyst role -> metric -> calculation -> source evidence
             -> validation -> trust decision -> reasoning -> recommendation

Nothing in the chain is computed. Every link is READ from an object an earlier stage already
produced, which is the point: a link that cannot be filled is a real gap, and the chain says so
rather than narrating over it.
"""
import pytest

from engine import explainability
from engine.explainability import (ALL_LINKS, CONDITIONALLY_EMPTY, LINK_QUESTION,
                                   LINK_METRIC, LINK_CALCULATION, LINK_EVIDENCE,
                                   LINK_VALIDATION, LINK_TRUST, LINK_REASONING,
                                   LINK_ANALYST_ROLE, LINK_RECOMMENDATION)
from engine.analyst_intelligence import AnalystIntelligence


@pytest.fixture(scope="module")
def ai(registry):
    return AnalystIntelligence(registry=registry)


TRACEABLE_QUESTIONS = [
    "How much revenue did we make?",
    "What is occupancy?",
    "What's our profit?",
    "What was our electricity cost?",
    "Why did revenue fall?",
]


class TestChainCompleteness:
    @pytest.mark.parametrize("question", TRACEABLE_QUESTIONS)
    def test_every_answer_has_a_complete_chain(self, ai, question):
        a = ai.ask(question)
        ai.reset()
        chain = ai.explain(a)
        assert chain is not None
        assert explainability.validate(chain) == (), question

    @pytest.mark.parametrize("question", TRACEABLE_QUESTIONS)
    def test_every_documented_link_is_present_in_the_chain(self, ai, question):
        a = ai.ask(question)
        ai.reset()
        chain = ai.explain(a)
        names = [l.name for l in chain.links]
        for link in ALL_LINKS:
            assert link in names, f"{question}: missing {link}"

    def test_the_chain_starts_with_the_owners_own_words(self, ai):
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        chain = ai.explain(a)
        assert chain.get(LINK_QUESTION).content == "How much revenue did we make?"

    def test_every_present_link_cites_its_source(self, ai):
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        chain = ai.explain(a)
        for l in chain.links:
            if l.present and l.name != LINK_QUESTION:
                assert l.source.strip(), f"{l.name}: no source"


class TestChainContent:
    def test_the_metric_link_names_the_metric_id(self, ai):
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        chain = ai.explain(a)
        assert "M.REV.001" in chain.get(LINK_METRIC).content

    def test_the_evidence_link_names_manifest_keys(self, ai):
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        chain = ai.explain(a)
        content = chain.get(LINK_EVIDENCE).content
        assert "T.journal_lines" in content or "F.001" in content

    def test_the_validation_link_names_the_check_result(self, ai):
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        chain = ai.explain(a)
        assert "MATCH" in chain.get(LINK_VALIDATION).content

    def test_the_trust_link_records_the_verdict_and_headline_permission(self, ai):
        a = ai.ask("What's our profit?")
        ai.reset()
        chain = ai.explain(a)
        content = chain.get(LINK_TRUST).content
        assert "BLOCK" in content
        assert "headline_permitted=False" in content

    def test_the_analyst_role_link_explains_why_each_lens_was_chosen(self, ai):
        a = ai.ask("Why did profit fall?")
        ai.reset()
        chain = ai.explain(a)
        content = chain.get(LINK_ANALYST_ROLE).content
        assert "financial_analyst" in content
        assert "domain" in content or "intent" in content

    def test_the_calculation_link_carries_the_provenance(self, ai):
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        chain = ai.explain(a)
        assert chain.get(LINK_CALCULATION).content.strip()
        assert "M.REV.001" in chain.get(LINK_CALCULATION).content

    def test_a_conflicted_answer_records_its_disclosures(self, ai):
        a = ai.ask("What is occupancy?")
        ai.reset()
        chain = ai.explain(a)
        assert "disclosures" in chain.get(LINK_TRUST).content

    def test_a_ceiling_raise_is_recorded_not_silent(self, ai):
        """A SHOW_BOTH lookup reaches INFERENCE by obligation; the raise must be visible."""
        a = ai.ask("What is occupancy?")
        ai.reset()
        chain = ai.explain(a)
        assert "ceiling raised" in chain.get(LINK_REASONING).content


class TestGapsAreDeclaredNotHidden:
    def test_a_lookup_declares_why_it_has_no_recommendation(self, ai):
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        chain = ai.explain(a)
        assert not chain.get(LINK_RECOMMENDATION).present
        assert any(LINK_RECOMMENDATION in g for g in chain.gaps)

    def test_every_empty_link_has_a_documented_empty_case(self, ai):
        for q in TRACEABLE_QUESTIONS + ["What is our margin analysis?",
                                        "Which property is performing better?"]:
            a = ai.ask(q)
            ai.reset()
            chain = ai.explain(a)
            for l in chain.links:
                if not l.present:
                    assert l.name in CONDITIONALLY_EMPTY, f"{q}: {l.name} empty undocumented"

    def test_a_refused_question_still_produces_a_chain(self, ai):
        a = ai.ask("What is our margin analysis?")
        ai.reset()
        chain = ai.explain(a)
        assert chain is not None
        assert explainability.validate(chain) == ()
        assert not chain.get(LINK_METRIC).present

    def test_the_validator_catches_a_broken_chain(self, ai):
        """A validator that never fails proves nothing."""
        a = ai.ask("How much revenue did we make?")
        ai.reset()
        chain = ai.explain(a)
        broken = explainability.EvidenceChain(
            links=tuple(l for l in chain.links if l.name != LINK_TRUST))
        problems = explainability.validate(broken)
        assert any(LINK_TRUST in p for p in problems)

    def test_a_present_link_with_no_content_is_caught(self):
        link = explainability.ChainLink(name=LINK_METRIC, content="   ", source="x",
                                        present=True)
        chain = explainability.EvidenceChain(links=(link,))
        assert any("carries no content" in p for p in explainability.validate(chain))


class TestRendering:
    def test_the_chain_renders_readably(self, ai):
        a = ai.ask("What's our profit?")
        ai.reset()
        text = ai.explain(a).render()
        assert "WHY THIS ANSWER" in text
        for link in (LINK_METRIC, LINK_TRUST, LINK_EVIDENCE):
            assert link.upper() in text

    def test_the_chain_is_deterministic(self, ai):
        a1 = ai.ask("How much revenue did we make?")
        ai.reset()
        c1 = ai.explain(a1).render()
        a2 = ai.ask("How much revenue did we make?")
        ai.reset()
        c2 = ai.explain(a2).render()
        assert c1 == c2
