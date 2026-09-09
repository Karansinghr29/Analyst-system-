"""
Focused smoke: owner chat understands arbitrary phrasing generically — no question hardcoding.
"""
from engine.llm_interface import LLMInterface
from engine.llm_provider import DeterministicMockProvider
from engine.intent_models import READY, NEEDS_CLARIFICATION, NOT_DETERMINABLE
from engine.question_normalize import normalize_owner_question


def _iface():
    return LLMInterface(provider=DeterministicMockProvider(), verbalize=False)


def test_arbitrary_revenue_paraphrase_routes_to_revenue():
    iface = _iface()
    result = iface.ask("how much revenue are we making")
    assert result.status == READY
    assert "M.REV.001" in result.metric_ids
    assert "Not determinable from exported evidence." not in (result.text or "")
    assert "72,705,593.43" in (result.text or "")


def test_unsupported_forecast_does_not_execute_all_time():
    iface = _iface()
    result = iface.ask("what is next month revenue")
    assert result.status == NOT_DETERMINABLE
    assert result.executed is False
    text = result.text or ""
    assert "forecast" in text.lower() or "can't forecast" in text.lower() or "can't reliably" in text.lower()
    assert "72,705,593.43" not in text
    assert "tenant or unit" not in text.lower()
    assert "not determinable from exported evidence" not in text.lower()


def test_appended_role_words_do_not_change_routing():
    bare = normalize_owner_question("what is next month revenue")
    with_role = normalize_owner_question("what is next month revenue data analyst")
    assert bare[0].lower() == with_role[0].lower()
    assert "data analyst" in with_role[1]

    iface = _iface()
    a = iface.ask("what is next month revenue")
    iface.reset()
    b = iface.ask("what is next month revenue data analyst")
    assert a.status == b.status == NOT_DETERMINABLE
    assert a.executed is False and b.executed is False


def test_followup_why_inherits_prior_concept():
    iface = _iface()
    first = iface.ask("show me revenue")
    assert first.status == READY
    assert "M.REV.001" in first.metric_ids

    why = iface.ask("Why?")
    assert why.status in (READY, "BLOCKED")
    assert any(m.startswith("M.REV.") for m in why.metric_ids)
    assert why.inherited_context
    assert "concept" in why.inherited_context or "intent:driver" in why.inherited_context
