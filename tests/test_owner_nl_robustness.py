"""
Focused smoke: Owner NL robustness — typos, periods, forecast, presentation hygiene.
"""
from engine.llm_interface import LLMInterface
from engine.llm_provider import DeterministicMockProvider
from engine.intent_models import READY, NEEDS_CLARIFICATION, NOT_DETERMINABLE
from engine.question_normalize import normalize_owner_question
from engine.owner_presentation import sanitize_owner_text
from engine import analysis_capability as acap


def _iface():
    return LLMInterface(provider=DeterministicMockProvider(), verbalize=False)


def test_typo_tolerant_current_month_revenue():
    cleaned, _ = normalize_owner_question("thi smonth revenu")
    assert "this month" in cleaned
    assert "revenue" in cleaned
    iface = _iface()
    result = iface.ask("thi smonth revenu")
    assert result.status == READY
    assert result.plan.time.period_label == "this month"
    assert result.plan.time.period_label != "all-time"
    assert "72,705,593.43" not in (result.text or "")  # must not be all-time total
    assert "3,244,678" in (result.text or "")


def test_typo_tolerant_named_month_revenue():
    cleaned, _ = normalize_owner_question("augest month arevenue")
    assert "august" in cleaned
    assert "revenue" in cleaned
    iface = _iface()
    result = iface.ask("augest month revenue")
    assert result.status == READY
    assert result.plan.time.period_label == "2026-08"
    assert result.plan.time.period_label != "all-time"
    assert "M.REV.002" in result.metric_ids
    assert "72,705,593.43" not in (result.text or "")
    assert "3,244,678" in (result.text or "")


def test_explicit_unresolved_period_never_all_time():
    iface = _iface()
    result = iface.ask("weirdperiod month revenue")
    assert result.status == NEEDS_CLARIFICATION
    assert result.executed is False
    text = (result.text or "").lower()
    assert "all-time" not in text or "will not" in text or "period" in text
    assert "72,705,593.43" not in (result.text or "")


def test_next_month_forecast_never_all_time():
    assert acap.classify_analysis_capability("next month revenue").capability_id == "forecasting"
    iface = _iface()
    result = iface.ask("next month revenue")
    assert result.status == NOT_DETERMINABLE
    assert result.executed is False
    text = (result.text or "").lower()
    assert "forecast" in text or "can't forecast" in text or "cannot forecast" in text or "can't reliably" in text
    assert "72,705,593.43" not in (result.text or "")
    assert "tenant or unit" not in text  # must not be misrouted to PII clarification
    assert "not determinable from exported evidence" not in text


def test_normal_owner_answer_hides_technical_internals():
    iface = _iface()
    result = iface.ask("this month revenue")
    assert result.status == READY
    text = result.text or ""
    for leak in ("M.REV", "DQ.", "C.0", "structured_output", "business_reasoning",
                 "analytics_execution_spec", "semantic_metric_registry", ".csv", ".py"):
        assert leak not in text, leak
    # Sanitize also strips planted internals.
    dirty = "Revenue is 100. See M.REV.001 and DQ.015 in structured_output.py / foo.csv."
    clean = sanitize_owner_text(dirty)
    assert "M.REV" not in clean
    assert "DQ." not in clean
    assert "structured_output" not in clean
    assert ".csv" not in clean
