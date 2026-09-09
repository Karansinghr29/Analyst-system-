"""
Focused smoke: Owner AI Analyst routes by analytical capability, not canned questions.
"""
from engine.analyst_intelligence import (
    AnalystIntelligence, INTENT_BRIEFING, INTENT_WHAT_CHANGED, INTENT_WHAT_TO_DO, INTENT_METRIC,
)
from engine.llm_provider import DeterministicMockProvider
from engine import analysis_capability as acap
from engine.intent_models import READY


def _ai():
    return AnalystIntelligence(provider=DeterministicMockProvider(), verbalize=False)


def test_capability_classifier_is_analysis_type_not_question_list():
    cases = [
        ("What will revenue be next month?", "forecasting", acap.ROUTE_CAPABILITY_GAP),
        ("What happens if occupancy increases?", "scenario_analysis", acap.ROUTE_CAPABILITY_GAP),
        ("Why did revenue fall?", "driver_analysis", acap.ROUTE_METRIC),
        ("What changed this month?", "what_changed", acap.ROUTE_WHAT_CHANGED),
        ("Which area needs attention?", "attention_required", acap.ROUTE_WHAT_TO_DO),
        ("How is the business doing?", "executive_summary", acap.ROUTE_BRIEFING),
        ("Are collections getting better?", "trend", acap.ROUTE_METRIC),
        ("Are there unusual expenses?", "anomaly_surface", acap.ROUTE_METRIC),
        ("Should I increase rent?", "scenario_analysis", acap.ROUTE_CAPABILITY_GAP),
    ]
    for question, capability_id, route in cases:
        cap = acap.classify_analysis_capability(question)
        assert cap.capability_id == capability_id, (question, cap)
        assert cap.route == route, (question, cap)


def test_forecast_is_capability_aware_not_unknown_metric():
    ai = _ai()
    answer = ai.ask("What will revenue be next month? data analyst")
    text = (answer.text or "").lower()
    assert "forecast" in text or "can't reliably forecast" in text or "can't forecast" in text
    assert "nothing in the available records corresponds" not in text
    assert "72,705,593.43" not in (answer.text or "")
    assert "tenant or unit" not in text
    # Forecast must not execute an all-time metric lookup as the forecast answer.
    if answer.ask_result is not None:
        assert answer.ask_result.executed is False
    assert "not a forecast" in text or "historical" in text or "currently available" in text


def test_scenario_gap_is_not_unknown_metric():
    ai = _ai()
    answer = ai.ask("What happens if occupancy increases?")
    text = (answer.text or "").lower()
    assert "scenario" in text or "what-if" in text
    assert "not implemented" in text or "not invented" in text
    assert "nothing in the available records corresponds" not in text


def test_workflows_and_metric_paths_still_route():
    ai = _ai()

    briefing = ai.ask("How is my business doing?")
    assert briefing.owner_intent == INTENT_BRIEFING
    assert (briefing.text or "").strip()

    ai.llm.reset()
    changed = ai.ask("What changed this month?")
    assert changed.owner_intent == INTENT_WHAT_CHANGED
    assert (changed.text or "").strip()

    ai.llm.reset()
    attention = ai.ask("What are my biggest risks?")
    assert attention.owner_intent == INTENT_WHAT_TO_DO
    assert (attention.text or "").strip()

    ai.llm.reset()
    revenue = ai.ask("how much revenue are we making")
    assert revenue.owner_intent == INTENT_METRIC
    assert revenue.ask_result is not None
    assert revenue.ask_result.status == READY
    assert "M.REV.001" in revenue.metric_ids


def test_followup_why_inherits_prior_metric_context():
    ai = _ai()
    first = ai.ask("show me revenue")
    assert first.ask_result.status == READY
    why = ai.ask("Why?")
    assert why.ask_result is not None
    assert any(m.startswith("M.REV.") for m in why.metric_ids)
