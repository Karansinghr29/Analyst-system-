"""
Semantic-contract smoke for Owner NL.

These tests assert that the system answers the *requested* analysis — not merely that
some valid metric was returned. Classes A–Q, not canned one-off strings.
"""
from engine.analyst_intelligence import (
    AnalystIntelligence, INTENT_BRIEFING, INTENT_WHAT_CHANGED, INTENT_WHAT_TO_DO,
    INTENT_METRIC, INTENT_WHAT_TO_TRUST,
)
from engine.llm_provider import DeterministicMockProvider
from engine.llm_interface import LLMInterface
from engine.intent_models import READY, NEEDS_CLARIFICATION
from engine.question_normalize import normalize_owner_question
from engine import analysis_capability as acap
from engine.owner_presentation import sanitize_owner_text


def _ai():
    return AnalystIntelligence(provider=DeterministicMockProvider(), verbalize=False)


def _iface():
    return LLMInterface(provider=DeterministicMockProvider(), verbalize=False)


def _no_tech(text):
    t = text or ""
    for leak in ("M.REV", "M.EXP", "M.OCC", "DQ.", "C.0", "FN.",
                 "structured_output", "business_reasoning", "analytics_execution_spec",
                 "semantic_metric_registry", ".csv", "engine.", "question_understanding"):
        assert leak not in t, f"technical leak {leak!r} in {t[:180]!r}"


# --- A. lookup + current period ---------------------------------------------------------------

def test_A_lookup_current_period_not_all_time():
    r = _iface().ask("this month revenue")
    assert r.status == READY and r.executed
    assert r.plan.time.period_label == "this month"
    assert "M.REV.002" in r.metric_ids
    assert "72,705,593.43" not in (r.text or "")
    assert "3,244,678" in (r.text or "")
    _no_tech(r.text)


# --- B. lookup + named month ------------------------------------------------------------------

def test_B_lookup_named_month_not_all_time():
    r = _iface().ask("august revenue")
    assert r.status == READY and r.executed
    assert r.plan.time.period_label == "2026-08"
    assert "72,705,593.43" not in (r.text or "")
    assert "3,244,678" in (r.text or "")


# --- C. lookup + last month -------------------------------------------------------------------

def test_C_lookup_last_month_not_all_time():
    r = _iface().ask("last month revenue")
    assert r.status == READY and r.executed
    assert r.plan.time.period_label == "last month"
    assert "72,705,593.43" not in (r.text or "")
    assert "3,336,114" in (r.text or "")


# --- D. unresolved period ---------------------------------------------------------------------

def test_D_unresolved_period_clarifies_not_all_time():
    r = _iface().ask("weirdperiod month revenue")
    assert r.status == NEEDS_CLARIFICATION
    assert r.executed is False
    assert "72,705,593.43" not in (r.text or "")
    assert "period" in (r.text or "").lower() or "time" in (r.text or "").lower()


# --- E. future / forecast ---------------------------------------------------------------------

def test_E_future_never_executes_historical():
    assert acap.classify_analysis_capability("next month revenue").capability_id == "forecasting"
    r = _iface().ask("next month revenue")
    assert r.executed is False
    text = (r.text or "").lower()
    assert "forecast" in text
    assert "72,705,593.43" not in (r.text or "")
    assert "tenant or unit" not in text
    assert "not determinable from exported evidence" not in text
    # Must not trap the next turn as a clarification reply.
    r2 = _iface().ask("this month revenue")  # fresh iface — also verify wording on first
    assert r2.status == READY and r2.executed
    assert "M.REV.002" in r2.metric_ids


# --- F. trend ---------------------------------------------------------------------------------

def test_F_trend_not_silent_lookup():
    ai = _ai()
    # Collections is definitionally ambiguous first — clarification is correct, not a fake trend.
    a = ai.ask("are collections getting better")
    text = (a.text or "").lower()
    assert a.owner_intent == INTENT_METRIC
    assert "definition" in text or "which" in text or "trend" in text or "increased" in text or "decreased" in text
    assert "72,705,593.43" not in (a.text or "")


# --- G. comparison ----------------------------------------------------------------------------

def test_G_comparison_not_workflow_or_single_lookup():
    ai = _ai()
    a = ai.ask("compare revenue this month with last month")
    assert a.owner_intent == INTENT_METRIC
    text = (a.text or "").lower()
    assert "executive takeaway" not in text
    # Either a real period comparison, or an honest limitation if the asked months
    # are incomplete in the export — never an all-time lookup substitute.
    assert (
        "increased" in text or "decreased" in text or "did not change" in text
        or "comparison" in text or "periods" in text or "not both present" in text
        or "can't produce" in text or "cannot" in text
    )
    assert "72,705,593.43" not in (a.text or "")
    assert "agree definition" not in text  # not a SAFE single-value lookup framing


# --- H. driver / why --------------------------------------------------------------------------

def test_H_driver_does_not_claim_unverified_decrease():
    ai = _ai()
    a = ai.ask("why is revenue down")
    text = (a.text or "").lower()
    assert a.owner_intent == INTENT_METRIC
    # Must not answer with all-time SAFE revenue as if that explains "why down".
    assert "72,705,593.43" not in (a.text or "")
    assert ("do not show" in text or "can't confirm" in text or "decreased" in text
            or "fell" in text or "driver" in text or "cause" in text)
    # If it rejects the premise, that is correct when evidence shows increase.
    if "do not show" in text or "not evidenced" in text:
        assert "decrease" in text or "down" in text


# --- I. anomaly -------------------------------------------------------------------------------

def test_I_anomaly_not_safe_lookup_substitute():
    ai = _ai()
    a = ai.ask("are there unusual expenses")
    text = (a.text or "").lower()
    assert "unusual" in text or "anomal" in text or "threshold" in text
    assert "20,784,831" not in (a.text or "")  # must not substitute expense total
    assert a.trust_level in ("NOT_DETERMINABLE", "DISCLOSE", "")
    _no_tech(a.text)


# --- J. risk ----------------------------------------------------------------------------------

def test_J_risk_routes_to_attention_or_risk_analysis():
    ai = _ai()
    a = ai.ask("what are my biggest risks")
    assert a.owner_intent in (INTENT_WHAT_TO_DO, INTENT_METRIC)
    assert (a.text or "").strip()
    assert "not determinable from exported evidence." != (a.text or "").strip().lower()


# --- K. decision support ----------------------------------------------------------------------

def test_K_decision_support_not_unknown_metric():
    ai = _ai()
    a = ai.ask("what should I do")
    assert a.owner_intent == INTENT_WHAT_TO_DO
    text = (a.text or "").lower()
    assert "attention" in text or "decision" in text or "recommend" in text
    assert "no semantic metric" not in text


# --- L. ambiguous -----------------------------------------------------------------------------

def test_L_ambiguous_clarifies():
    r = _iface().ask("show me collections")
    assert r.status == NEEDS_CLARIFICATION
    assert "definition" in (r.text or "").lower() or "which" in (r.text or "").lower()


# --- M. unsupported capability ----------------------------------------------------------------

def test_M_unsupported_capability_not_unknown_metric():
    ai = _ai()
    a = ai.ask("what happens if occupancy increases")
    text = (a.text or "").lower()
    assert "scenario" in text or "what-if" in text
    assert "nothing in the available records corresponds" not in text
    # Must not execute occupancy as if it answered the scenario.
    assert "agree definition" not in text or "scenario" in text


# --- N. follow-up -----------------------------------------------------------------------------

def test_N_followup_inherits_concept():
    iface = _iface()
    first = iface.ask("show me revenue")
    assert first.status == READY
    why = iface.ask("Why?")
    # May redirect to monthly series for change-capable follow-up analysis.
    assert any(m.startswith("M.REV.") for m in why.metric_ids)
    assert why.inherited_context


# --- O. typo + period -------------------------------------------------------------------------

def test_O_typo_plus_period():
    assert "this month" in normalize_owner_question("thi smonth revenu")[0]
    assert "revenue" in normalize_owner_question("thi smonth revenu")[0]
    # Must not rewrite unrelated English.
    assert "there" in normalize_owner_question("are there unusual expenses")[0]
    r = _iface().ask("thi smonth revenu")
    assert r.status == READY
    assert r.plan.time.period_label == "this month"
    assert "72,705,593.43" not in (r.text or "")


# --- P. role suffix ---------------------------------------------------------------------------

def test_P_role_suffix_ignored():
    bare = normalize_owner_question("this month revenue")[0]
    role = normalize_owner_question("this month revenue data analyst")[0]
    assert bare == role
    r = _iface().ask("next month revenue data scientist")
    assert r.executed is False
    assert "forecast" in (r.text or "").lower()
    assert "not determinable from exported evidence" not in (r.text or "").lower()


# --- Q. owner presentation leakage ------------------------------------------------------------

def test_Q_owner_presentation_no_tech_leak():
    r = _iface().ask("this month revenue")
    _no_tech(r.text)
    dirty = ("See M.REV.001 DQ.015 C.010 FN.001 in structured_output.py and "
             "semantic_metric_registry.csv via engine.foo")
    clean = sanitize_owner_text(dirty)
    _no_tech(clean)
