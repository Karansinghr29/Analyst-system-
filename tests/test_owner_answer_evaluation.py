"""
Owner-answer evaluation by QUESTION CLASS (not canned strings).

Acceptance: answer the owner's actual question whenever existing evidence + analytics can.
A valid-looking metric that answers a *different* question must FAIL.
"""
from engine.analyst_intelligence import AnalystIntelligence, INTENT_METRIC, INTENT_WHAT_TO_DO
from engine.llm_interface import LLMInterface
from engine.llm_provider import DeterministicMockProvider
from engine.intent_models import READY, NEEDS_CLARIFICATION, NOT_DETERMINABLE, BLOCKED
from engine import analysis_capability as acap
from engine import concept_map
from engine import time_resolution as timeres
from engine.question_normalize import normalize_owner_question


ALL_TIME_REV = "72,705,593.43"
THIS_MONTH_REV = "3,244,678"
LAST_MONTH_REV = "3,336,114"


def _ai():
    return AnalystIntelligence(provider=DeterministicMockProvider(), verbalize=False)


def _iface():
    return LLMInterface(provider=DeterministicMockProvider(), verbalize=False)


def _no_tech(text):
    t = text or ""
    for leak in ("M.REV", "M.EXP", "M.OCC", "DQ.", "C.0", "FN.",
                 "structured_output", "analytics_execution_spec", ".csv", "engine."):
        assert leak not in t, f"tech leak {leak!r} in {t[:200]!r}"


# --- current-period revenue lookup ------------------------------------------------------------

def test_class_current_period_revenue_lookup():
    """INTENT=lookup PERIOD=this month CAPABILITY=kpi_lookup ANSWER=monthly revenue figure."""
    q = "how much money did we make this month"
    assert concept_map.match(q), "money/make vernacular must resolve to a financial concept"
    assert not timeres.asks_unsupported_forecast(q)[0]
    r = _iface().ask(q)
    assert r.status == READY and r.executed
    assert r.plan.time and r.plan.time.period_label == "this month"
    assert "M.REV.002" in r.metric_ids
    assert THIS_MONTH_REV in (r.text or "")
    assert ALL_TIME_REV not in (r.text or "")
    assert "not determinable from exported evidence" not in (r.text or "").lower()
    _no_tech(r.text)


# --- named-month revenue lookup ---------------------------------------------------------------

def test_class_named_month_revenue_lookup():
    r = _iface().ask("august revenue")
    assert r.status == READY and r.executed
    assert "M.REV.002" in r.metric_ids
    assert THIS_MONTH_REV in (r.text or "")
    assert ALL_TIME_REV not in (r.text or "")


# --- all-time revenue lookup ------------------------------------------------------------------

def test_class_all_time_revenue_lookup():
    r = _iface().ask("show me revenue")
    assert r.status == READY and r.executed
    assert "M.REV.001" in r.metric_ids
    assert ALL_TIME_REV in (r.text or "")
    assert r.plan.time is None or r.plan.time.period_label in ("all-time", "", None) or (
        r.plan.time.period_label == "all-time")


# --- period comparison ------------------------------------------------------------------------

def test_class_period_comparison():
    a = _ai().ask("compare revenue this month with last month")
    text = (a.text or "").lower()
    assert a.owner_intent == INTENT_METRIC
    assert ALL_TIME_REV not in (a.text or "")
    # Must be a comparison (or disclosed fallback to complete months), never SAFE single lookup.
    assert (
        "increased" in text or "decreased" in text or "did not change" in text
        or "incomplete" in text or "latest complete" in text
    )
    assert "agree definition" not in text


# --- trend ------------------------------------------------------------------------------------

def test_class_trend():
    # Collections is definitionally ambiguous — clarification is the correct business answer.
    a = _ai().ask("are collections getting better")
    text = (a.text or "").lower()
    assert "definition" in text or "which" in text or "trend" in text or "increased" in text
    assert ALL_TIME_REV not in (a.text or "")


# --- driver / why -----------------------------------------------------------------------------

def test_class_driver_why():
    a = _ai().ask("why is revenue down")
    text = (a.text or "").lower()
    assert a.owner_intent == INTENT_METRIC
    assert ALL_TIME_REV not in (a.text or "")
    # Either establishes change + drivers, or honestly rejects an unevidenced decrease.
    assert (
        "do not show" in text or "can't confirm" in text or "not evidenced" in text
        or "decreased" in text or "fell" in text or "driver" in text or "cause" in text
    )


# --- future forecast --------------------------------------------------------------------------

def test_class_future_forecast():
    q = "what will revenue look like next month"
    assert acap.classify_analysis_capability(q).capability_id == "forecasting"
    a = _ai().ask(q)
    text = (a.text or "").lower()
    assert "forecast" in text
    assert ALL_TIME_REV not in (a.text or "")
    assert "nothing in the available records corresponds" not in text
    # Optional historical context is allowed; it must be labelled as not a forecast.
    if "3," in (a.text or "") or "3336" in (a.text or "").replace(",", ""):
        assert "not a forecast" in text or "historical" in text


# --- occupancy SHOW_BOTH ----------------------------------------------------------------------

def test_class_occupancy_show_both():
    assert not timeres.has_explicit_period_intent("how full are we")
    r = _iface().ask("how full are we")
    assert r.status in (READY, BLOCKED) or r.trust_level in ("SHOW_BOTH", "BLOCK")
    text = (r.text or "").lower()
    assert "period" not in text or "definition" in text  # must not false-ask for a period
    assert "which time period" not in text
    assert "def " in text or "definition" in text or "occupancy" in text
    assert "not determinable from exported evidence" not in text
    _no_tech(r.text)


# --- tenant dues SHOW_BOTH --------------------------------------------------------------------

def test_class_tenant_dues_show_both():
    r = _iface().ask("how much do tenants owe")
    assert r.status in (READY, BLOCKED)
    assert r.trust_level in ("SHOW_BOTH", "BLOCK", "DISCLOSE") or r.status == BLOCKED
    assert r.executed
    assert r.metric_ids
    text = (r.text or "").lower()
    assert "tenant or unit" not in text
    assert "not determinable from exported evidence" not in text
    _no_tech(r.text)


# --- decision support -------------------------------------------------------------------------

def test_class_decision_support():
    a = _ai().ask("what should I do")
    assert a.owner_intent == INTENT_WHAT_TO_DO
    text = (a.text or "").lower()
    assert "attention" in text or "decision" in text or "recommend" in text
    assert "no semantic metric" not in text


# --- risk -------------------------------------------------------------------------------------

def test_class_risk():
    a = _ai().ask("what are my biggest risks")
    assert a.owner_intent in (INTENT_WHAT_TO_DO, INTENT_METRIC)
    assert (a.text or "").strip()
    assert "nothing in the available records corresponds" not in (a.text or "").lower()


# --- typo + period ----------------------------------------------------------------------------

def test_class_typo_plus_period():
    nq, _ = normalize_owner_question("thi smonth revenu")
    assert "this month" in nq and "revenue" in nq
    r = _iface().ask("thi smonth revenu")
    assert r.status == READY
    assert "M.REV.002" in r.metric_ids
    assert ALL_TIME_REV not in (r.text or "")


# --- follow-up --------------------------------------------------------------------------------

def test_class_followup():
    iface = _iface()
    first = iface.ask("show me revenue")
    assert first.status == READY
    why = iface.ask("Why?")
    assert why.metric_ids
    assert "M.REV" in str(why.metric_ids)


# --- genuinely unsupported capability ---------------------------------------------------------

def test_class_unsupported_capability():
    a = _ai().ask("what happens if occupancy increases")
    text = (a.text or "").lower()
    assert "scenario" in text or "what-if" in text
    # Must not pretend occupancy SHOW_BOTH answered the scenario.
    assert "agree definition" not in text or "scenario" in text
    assert ALL_TIME_REV not in (a.text or "")


# --- session: forecast must not trap the next question ----------------------------------------

def test_forecast_does_not_trap_next_question():
    iface = _iface()
    f = iface.ask("what will revenue look like next month")
    assert f.executed is False
    assert "forecast" in (f.text or "").lower()
    nxt = iface.ask("how full are we")
    text = (nxt.text or "").lower()
    assert "latest recorded revenue" not in text
    assert "which time period" not in text
    assert "def " in text or "definition" in text or "occupancy" in text or "full" in text
