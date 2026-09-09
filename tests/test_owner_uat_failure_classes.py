"""
Focused tests for UAT failure CLASSES (shared semantic mechanisms), not canned sentences.

Each section documents:
  Reported example → Root cause → Shared mechanism → Broader class covered.
"""
from engine.question_normalize import normalize_owner_question
from engine import concept_map, analysis_capability as acap
from engine.question_understanding import classify_intents
from engine.intent_models import COMPARISON, RISK_SCAN
from engine.analyst_intelligence import AnalystIntelligence, INTENT_WHAT_TO_DO
from engine.llm_interface import LLMInterface
from engine.llm_provider import DeterministicMockProvider
from engine.intent_models import READY

ALL_TIME_REV = "72,705,593.43"


def _ai():
    return AnalystIntelligence(provider=DeterministicMockProvider(), verbalize=False)


def _iface():
    return LLMInterface(provider=DeterministicMockProvider(), verbalize=False)


# ---------------------------------------------------------------------------
# CLASS A — TIME QUALIFIER PRESERVATION
# Reported: thid month revenue → must not become all-time
# Root cause: period tokens must survive normalize + planning + monthly metric selection
# Shared mechanism: question_normalize time repair + understanding monthly redirect
# Broader class: this/last/named month across revenue AND other month-capable concepts
# ---------------------------------------------------------------------------

def test_class_time_qualifier_variants_preserve_period_for_revenue():
    variants = [
        "this month revenue",
        "current month revenue",
        "thid month revenue",
        "thi month revenue",
        "revenue this month",
        "how much revenue this month",
        "this month's revenue",
        "this month revenue evlo",
        "intha month revenue",
        "last month revenue",
        "august revenue",
        "August 2026 revenue",
    ]
    for q in variants:
        nq, _ = normalize_owner_question(q)
        assert "revenue" in nq, q
        assert (
            "this month" in nq or "current month" in nq or "last month" in nq
            or "august" in nq or "2026" in nq
        ), (q, nq)
        r = _iface().ask(q)
        assert ALL_TIME_REV not in (r.text or ""), (q, r.text)
        assert r.status == READY and r.executed, q
        assert "M.REV.002" in r.metric_ids, q


def test_class_time_qualifier_not_revenue_specific_expenses_and_collections():
    for q in ("this month expenses", "thid month expenses", "intha month expenses"):
        r = _iface().ask(q)
        assert "20,784,831" not in (r.text or ""), q
        text = (r.text or "").lower()
        assert "expense" in text or "month-scoped" in text

    nq, _ = normalize_owner_question("intha month collection")
    assert "this month" in nq
    assert "collection" in nq
    a = _ai().ask("this month collection")
    assert "definition" in (a.text or "").lower() or "collections" in (a.text or "").lower()
    assert ALL_TIME_REV not in (a.text or "")


def test_normalize_does_not_corrupt_change_english():
    nq, _ = normalize_owner_question("rent went up")
    assert "went" in nq
    assert "rent rent" not in nq
    assert "there" in normalize_owner_question("are there unusual expenses")[0]


# ---------------------------------------------------------------------------
# CLASS B — COLLECTION CONCEPT / INTENT RESOLUTION
# Reported: this month collection not understood
# Root cause: singular/vernacular forms + period deixis must still resolve collections
# Shared mechanism: concept_map phrases + plural stem + deixis normalize
# Broader class: collection vernacular, while keeping definitional clarification
# ---------------------------------------------------------------------------

def test_class_collections_vernacular_resolves_and_clarifies_definition():
    variants = [
        "collection",
        "collections",
        "collected amount",
        "money collected",
        "this month collection",
        "collection this month",
        "intha month collection evlo",
        "how much did we collect",
        "rent collected",
    ]
    for q in variants:
        nq, _ = normalize_owner_question(q)
        hits = concept_map.match(nq)
        assert any(c.name == "collections" for c, _ in hits), (q, nq, hits)
        a = _ai().ask(q)
        text = (a.text or "").lower()
        assert "nothing in the available records corresponds" not in text, q
        assert "definition" in text or "collections" in text or "collect" in text, (q, text[:160])


# ---------------------------------------------------------------------------
# CLASS C — RENT + CHANGE / COMPARISON INTENT
# Reported: rent romba increase aacha
# Root cause: rent not mapped; change verbs not comparison; normalize ate "went"
# Shared mechanism: revenue synonyms + comparison markers + particle normalize
# Broader class: rent/revenue directional change questions
# ---------------------------------------------------------------------------

def test_class_rent_change_is_comparison_not_blank_lookup():
    variants = [
        "did rent increase",
        "rent increased?",
        "rent romba increase aacha",
        "rent went up",
        "rent increase this month",
        "rent increased from last month",
        "rental income increased?",
        "is rent going up",
        "rent koranjucha",
    ]
    for q in variants:
        nq, _ = normalize_owner_question(q)
        hits = concept_map.match(nq)
        assert any(c.name in ("revenue", "owner_rent") for c, _ in hits), (q, nq, hits)
        intents = classify_intents(nq)
        assert COMPARISON in intents or "decreased" in nq, (q, nq, intents)
        a = _ai().ask(q)
        text = (a.text or "").lower()
        assert "which measure should i look up" not in text, (q, text[:160])
        assert ALL_TIME_REV not in (a.text or "")


# ---------------------------------------------------------------------------
# CLASS D — RISK / ATTENTION SEMANTIC ROUTING
# Reported: anything i should worry about / what needs attention
# Root cause: (1) worry/problem vernacular missing from attention markers;
#             (2) plural stem "needs"→"need" (via concept vocab "need") broke markers
# Shared mechanism: ENGLISH_LOCKED need/needs + attention markers (stem-tolerant)
# Broader class: open-ended worry / problem / attention / focus-first questions
# ---------------------------------------------------------------------------

def test_class_risk_attention_routing():
    variants = [
        "anything i should worry about",
        "anything to worry about",
        "any problems",
        "any issues",
        "what needs attention",
        "what should I focus on",
        "biggest risks",
        "where is the problem",
        "entha area problem",
        "edhavadhu problem iruka",
        "anything concerning",
        "what should I look at first",
    ]
    for q in variants:
        nq, _ = normalize_owner_question(q)
        cap = acap.classify_analysis_capability(nq)
        intents = classify_intents(nq)
        assert (
            cap.route == acap.ROUTE_WHAT_TO_DO
            or RISK_SCAN in intents
            or cap.capability_id == "attention_required"
        ), (q, nq, cap, intents)
        a = _ai().ask(q)
        assert a.owner_intent == INTENT_WHAT_TO_DO, (q, a.owner_intent, (a.text or "")[:120])
        text = (a.text or "").lower()
        assert "which measure should i look up" not in text, q
        assert (
            "attention" in text or "risk" in text or "decision" in text
            or "executive" in text or "worry" in text
        ), (q, text[:160])
