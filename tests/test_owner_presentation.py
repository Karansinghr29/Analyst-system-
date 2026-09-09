"""
Owner-facing natural-language presentation.

The deterministic engine, Trust Gate, Answer Contract, and registries are unchanged. This
suite only checks what the owner is shown: concise business English, not engine dumps.
"""
import re

import pytest

from engine.analyst_intelligence import AnalystIntelligence, INTENT_BRIEFING
from engine.llm_interface import LLMInterface
from engine.llm_provider import CallableProvider, DeterministicMockProvider, LLMUnavailable
from engine.result import NOT_DETERMINABLE_TEXT


_METRIC_ID = re.compile(r"\bM\.[A-Z]+\.\d+[A-Za-z]?\b")
_DQ_ID = re.compile(r"\bDQ\.\d+\b")
_CONFLICT_ID = re.compile(r"\bC\.\d+\b")
_INSIGHT_ID = re.compile(r"\bINS\.[A-Z0-9._-]+\b")
_SPEC_FILE = re.compile(r"\b[\w.-]+\.(?:md|csv|py)\b", re.I)
_DICT_DUMP = re.compile(r"\{[^{}]{0,400}\}")
_ENGINE_DUMP = (
    "METRIC PROVENANCE", "CALCULATION:", "VALIDATION:", "MANAGEMENT BRIEFING",
    "insight_generation_spec", "semantic_metric_registry",
)


def _leaks(text):
    """Internal identifiers, spec filenames, and Python dict dumps that must not reach the owner."""
    t = text or ""
    hits = []
    for rx, label in ((_METRIC_ID, "metric_id"), (_DQ_ID, "dq_id"),
                      (_CONFLICT_ID, "conflict_id"), (_INSIGHT_ID, "insight_id"),
                      (_SPEC_FILE, "file/spec name")):
        m = rx.search(t)
        if m:
            hits.append(f"{label}:{m.group(0)}")
    if _DICT_DUMP.search(t) and ("metric_id" in t or "insight_id" in t or "trust_level" in t):
        hits.append("python-dict-dump")
    for token in _ENGINE_DUMP:
        if token in t:
            hits.append(f"engine-dump:{token}")
    return hits


def _assert_owner_clean(text, limitations=()):
    hits = _leaks(text)
    assert not hits, f"owner text leaked {hits}: {text[:500]}"
    for lim in limitations:
        lim_hits = _leaks(lim)
        assert not lim_hits, f"limitation leaked {lim_hits}: {lim}"


@pytest.fixture
def ai(registry):
    return AnalystIntelligence(registry=registry)


@pytest.fixture
def iface(registry):
    return LLMInterface(registry=registry)


class TestOwnerDoesNotSeeEngineDumps:
    def test_briefing_is_owner_english_not_a_raw_dict_or_engine_dump(self, ai):
        a = ai.ask("How is my business doing?")
        ai.reset()
        assert a.owner_intent == INTENT_BRIEFING
        _assert_owner_clean(a.text, a.limitations)
        assert "Executive takeaway" in a.text
        assert "Key numbers" in a.text
        assert "What needs attention" in a.text
        assert "{" not in a.text or "metric_id" not in a.text

    def test_metric_ids_such_as_ar_and_dq_are_not_in_owner_prose(self, ai):
        for q in ("How is my business doing?", "What are my biggest risks?",
                  "What changed?", "What should I focus on?",
                  "How much revenue did we make?", "How much do tenants owe?"):
            a = ai.ask(q)
            ai.reset()
            _assert_owner_clean(a.text, a.limitations)
            assert "M.AR.001A" not in a.text
            assert "DQ.016" not in a.text

    def test_internal_file_and_spec_names_are_not_exposed(self, ai):
        a = ai.ask("What changed?")
        ai.reset()
        _assert_owner_clean(a.text, a.limitations)
        assert "insight_generation_spec.md" not in a.text
        assert ".md" not in a.text
        assert NOT_DETERMINABLE_TEXT in a.text

    def test_revenue_deterministic_value_is_unchanged(self, iface):
        r = iface.ask("How much revenue did we make?")
        assert r.executed
        assert abs(r.answers[0].headline - 72705593.43) < 0.01
        assert r.trust_level == "SAFE"
        assert "72705593.43" in r.text or "72,705,593.43" in r.text
        _assert_owner_clean(r.text)
        assert "M.REV.001" in r.rendered.skeleton
        assert "M.REV.001" not in r.text


class TestTrustSemanticsSurviveOwnerPresentation:
    def test_block_remains_blocked(self, iface):
        r = iface.ask("What was profit last month?")
        assert r.trust_level == "BLOCK"
        for a in r.answers:
            assert a.headline is None
        low = r.text.lower()
        assert any(w in low for w in ("cannot", "conflict", "no single", "disagree"))
        _assert_owner_clean(r.text)
        assert "M.PROFIT.001" in r.rendered.skeleton
        assert "M.PROFIT.001" not in r.text

    def test_show_both_remains_all_definitions_no_winner(self, iface):
        r = iface.ask("How much do tenants owe?")
        assert r.trust_level == "SHOW_BOTH"
        for a in r.answers:
            assert a.headline is None
        labels = [res.definition_label for a in r.answers for res in a.results]
        assert len(labels) >= 2
        low = r.text.lower()
        shown = sum(1 for lab in labels if lab.lower()[:18] in low)
        assert shown >= min(2, len(labels))
        for phrase in ("the real number is", "the correct figure is", "best estimate"):
            assert phrase not in low
        _assert_owner_clean(r.text)

    def test_not_determinable_remains_unavailable(self, iface):
        r = iface.ask("What is our margin analysis?")
        assert NOT_DETERMINABLE_TEXT in r.text
        _assert_owner_clean(r.text)


class TestOllamaFailureFallsBackToOwnerSkeleton:
    def test_llm_unavailable_uses_deterministic_owner_text_not_the_contract_dump(self, registry):
        def boom(prompt, system, max_tokens, temperature):
            if "VERBALIZE" in (system or ""):
                raise LLMUnavailable("ollama down")
            return DeterministicMockProvider()._extract(prompt)

        i = LLMInterface(provider=CallableProvider(boom, name="down"), registry=registry)
        r = i.ask("How much revenue did we make?")
        assert r.executed
        assert abs(r.answers[0].headline - 72705593.43) < 0.01
        assert "72705593.43" in r.text or "72,705,593.43" in r.text
        assert "METRIC PROVENANCE" not in r.text
        assert "M.REV.001" not in r.text
        _assert_owner_clean(r.text)

    def test_rejected_verbalization_falls_back_to_owner_draft_not_raw_skeleton(self, registry):
        def hostile(prompt, system, max_tokens, temperature):
            if "VERBALIZE" in (system or ""):
                return "Revenue was Rs.99,999,999.99 for M.REV.001."
            return DeterministicMockProvider()._extract(prompt)

        i = LLMInterface(provider=CallableProvider(hostile, name="hostile"), registry=registry)
        r = i.ask("How much revenue did we make?")
        assert r.guard_violations
        assert r.rendered.verbalized is False
        assert "99,999,999.99" not in r.text and "99999999.99" not in r.text
        assert "72705593.43" in r.text or "72,705,593.43" in r.text
        assert r.text != r.rendered.skeleton
        assert "METRIC PROVENANCE" not in r.text
        _assert_owner_clean(r.text)


class TestWhyFollowUpStillWorks:
    def test_why_after_revenue_keeps_the_subject_and_stays_owner_facing(self, ai):
        first = ai.ask("How much revenue did we make?")
        assert first.ask_result and first.ask_result.executed
        why = ai.ask("Why?")
        ai.reset()
        assert why.text.strip()
        _assert_owner_clean(why.text, why.limitations)
        assert "M.REV.001" in why.metric_ids

    def test_why_after_briefing_stays_a_briefing_and_stays_owner_facing(self, ai):
        first = ai.ask("How is my business doing?")
        assert first.owner_intent == INTENT_BRIEFING
        why = ai.ask("Why?")
        ai.reset()
        assert why.text.strip()
        _assert_owner_clean(why.text, why.limitations)
        assert "Executive takeaway" in why.text or why.owner_intent == INTENT_BRIEFING
