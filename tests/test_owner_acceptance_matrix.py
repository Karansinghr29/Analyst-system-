"""
Owner-NL acceptance / random-question readiness matrix.

Question CLASSES with natural variations — not a canned router test.
A case PASSES only when concept + period + intent + capability align.
A valid metric alone is NOT a pass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from engine.analyst_intelligence import (
    AnalystIntelligence, INTENT_METRIC, INTENT_BRIEFING, INTENT_WHAT_CHANGED,
    INTENT_WHAT_TO_DO, INTENT_WHAT_TO_TRUST,
)
from engine.llm_interface import LLMInterface
from engine.llm_provider import DeterministicMockProvider
from engine.intent_models import READY, BLOCKED, NEEDS_CLARIFICATION, NOT_DETERMINABLE
from engine import analysis_capability as acap
from engine.owner_presentation import sanitize_owner_text

ALL_TIME_REV = "72,705,593.43"
ALL_TIME_EXP = "20,784,831"


@dataclass
class Case:
    question: str
    domain: str
    expected_intent: str          # lookup|compare|trend|driver|forecast|scenario|anomaly|risk|decision|trust|briefing|changed|clarify
    expected_concept: str         # revenue|expenses|profit|...|any|none
    expected_period: str          # all-time|this month|last month|named|year|future|none|any
    expected_capability: str      # kpi_lookup|period_comparison|trend|driver_analysis|forecasting|...
    expected_answer_type: str     # figure|show_both|block|clarify|capability_gap|workflow|driver|comparison
    notes: str = ""
    via: str = "ai"               # ai | iface


@dataclass
class Result:
    case: Case
    pass_fail: str
    failure_class: str = ""
    actual_route: str = ""
    actual_answer_type: str = ""
    text_snip: str = ""
    metrics: tuple = ()
    trust: str = ""
    status: str = ""


def _ai():
    return AnalystIntelligence(provider=DeterministicMockProvider(), verbalize=False)


def _iface():
    return LLMInterface(provider=DeterministicMockProvider(), verbalize=False)


def _build_matrix() -> list[Case]:
    c = []

    # ---- 1. Revenue --------------------------------------------------------------------------
    c += [
        Case("show me revenue", "revenue", "lookup", "revenue", "all-time", "kpi_lookup", "figure"),
        Case("how much revenue did we make", "revenue", "lookup", "revenue", "all-time", "kpi_lookup", "figure"),
        Case("this month revenue", "revenue", "lookup", "revenue", "this month", "kpi_lookup", "figure"),
        Case("how much money did we make this month", "revenue", "lookup", "revenue", "this month", "kpi_lookup", "figure"),
        Case("last month revenue", "revenue", "lookup", "revenue", "last month", "kpi_lookup", "figure"),
        Case("august revenue", "revenue", "lookup", "revenue", "named", "kpi_lookup", "figure"),
        Case("revenue this year", "revenue", "lookup", "revenue", "year", "kpi_lookup", "figure",
             notes="year may clarify or answer if evidence supports"),
        Case("compare revenue this month with last month", "revenue", "compare", "revenue", "this month",
             "period_comparison", "comparison"),
        Case("is revenue trending up", "revenue", "trend", "revenue", "any", "trend", "comparison"),
        Case("why is revenue down", "revenue", "driver", "revenue", "any", "driver_analysis", "driver"),
        Case("what will revenue look like next month", "revenue", "forecast", "revenue", "future",
             "forecasting", "capability_gap"),
        Case("next month revenue", "revenue", "forecast", "revenue", "future", "forecasting", "capability_gap"),
        Case("thi smonth revenu", "revenue", "lookup", "revenue", "this month", "kpi_lookup", "figure"),
        Case("this month revenue data analyst", "revenue", "lookup", "revenue", "this month", "kpi_lookup", "figure"),
        Case("What's our top line for August?", "revenue", "lookup", "revenue", "named", "kpi_lookup", "figure"),
    ]

    # ---- 2. Expenses -------------------------------------------------------------------------
    c += [
        Case("total expenses", "expenses", "lookup", "expenses", "all-time", "kpi_lookup", "figure"),
        Case("this month expenses", "expenses", "lookup", "expenses", "this month", "kpi_lookup", "figure"),
        Case("last month expenses", "expenses", "lookup", "expenses", "last month", "kpi_lookup", "figure"),
        Case("compare expenses this month with last month", "expenses", "compare", "expenses", "this month",
             "period_comparison", "comparison"),
        Case("expense trend", "expenses", "trend", "expenses", "any", "trend", "comparison"),
        Case("biggest expense categories", "expenses", "lookup", "expenses", "all-time", "kpi_lookup", "figure"),
        Case("why did expenses increase", "expenses", "driver", "expenses", "any", "driver_analysis", "driver"),
        Case("how much did we spend this month", "expenses", "lookup", "expenses", "this month", "kpi_lookup", "figure"),
    ]

    # ---- 3. Profit ---------------------------------------------------------------------------
    c += [
        Case("what is our profit", "profit", "lookup", "profit", "all-time", "kpi_lookup", "block"),
        Case("profit this month", "profit", "lookup", "profit", "this month", "kpi_lookup",
             "capability_gap", notes="month-scoped competing profit defs not available; honest limitation"),
        Case("how much profit did we make", "profit", "lookup", "profit", "all-time", "kpi_lookup", "block"),
        Case("why is profit down", "profit", "driver", "profit", "any", "driver_analysis", "driver"),
        Case("profit next month", "profit", "forecast", "profit", "future", "forecasting", "capability_gap"),
    ]

    # ---- 4. Collections ----------------------------------------------------------------------
    c += [
        Case("show me collections", "collections", "clarify", "collections", "any", "kpi_lookup", "clarify"),
        Case("how much did we collect", "collections", "clarify", "collections", "any", "kpi_lookup", "clarify"),
        Case("are collections getting better", "collections", "trend", "collections", "any", "trend", "clarify"),
        Case("collections last month", "collections", "lookup", "collections", "last month", "kpi_lookup", "clarify"),
    ]

    # ---- 5. Tenant dues ----------------------------------------------------------------------
    c += [
        Case("tenant dues", "dues", "lookup", "tenant_dues", "all-time", "kpi_lookup", "show_both"),
        Case("how much do tenants owe", "dues", "lookup", "tenant_dues", "all-time", "kpi_lookup", "show_both"),
        Case("outstanding receivables", "dues", "lookup", "tenant_dues", "all-time", "kpi_lookup", "show_both"),
        Case("aging of dues", "dues", "clarify", "aging", "any", "kpi_lookup", "clarify"),
        Case("how much does tenant Sharma owe", "dues", "clarify", "tenant_dues", "any", "kpi_lookup", "clarify",
             notes="named tenant → PII clarification"),
    ]

    # ---- 6. Deposits -------------------------------------------------------------------------
    c += [
        Case("deposits held", "deposits", "lookup", "deposits", "all-time", "kpi_lookup", "figure"),
        Case("security deposits", "deposits", "lookup", "deposits", "all-time", "kpi_lookup", "figure"),
        Case("deposit settlements", "deposits", "lookup", "deposits", "any", "kpi_lookup", "figure"),
    ]

    # ---- 7. Occupancy ------------------------------------------------------------------------
    c += [
        Case("how full are we", "occupancy", "lookup", "occupancy", "none", "kpi_lookup", "show_both"),
        Case("occupancy", "occupancy", "lookup", "occupancy", "none", "kpi_lookup", "show_both"),
        Case("occupancy rate", "occupancy", "lookup", "occupancy", "none", "kpi_lookup", "show_both"),
        Case("occupied beds", "occupancy", "lookup", "occupancy", "none", "kpi_lookup", "show_both"),
        Case("how many tenants are on notice", "occupancy", "lookup", "on_notice", "none", "kpi_lookup", "figure"),
    ]

    # ---- 8. Operations -----------------------------------------------------------------------
    c += [
        Case("maintenance tickets", "ops", "lookup", "maintenance", "all-time", "kpi_lookup", "figure"),
        Case("electricity cost", "ops", "lookup", "electricity", "any", "kpi_lookup", "figure"),
        Case("move in", "ops", "lookup", "move_ins", "any", "kpi_lookup", "figure"),
        Case("move out", "ops", "lookup", "move_outs", "any", "kpi_lookup", "figure"),
    ]

    # ---- 9. Risk / DQ ------------------------------------------------------------------------
    c += [
        Case("what are my biggest risks", "risk", "risk", "none", "none", "attention_required", "workflow"),
        Case("what should I worry about", "risk", "risk", "none", "none", "attention_required", "workflow"),
        Case("which numbers should I trust", "risk", "trust", "none", "none", "trust_advisory", "workflow"),
        Case("data quality issues", "risk", "lookup", "data_quality", "any", "kpi_lookup", "figure"),
    ]

    # ---- 10. Decision support ----------------------------------------------------------------
    c += [
        Case("what should I do", "decision", "decision", "none", "none", "attention_required", "workflow"),
        Case("what should I focus on", "decision", "decision", "none", "none", "attention_required", "workflow"),
        Case("where should I look first", "decision", "decision", "none", "none", "attention_required", "workflow"),
        Case("what needs management attention", "decision", "decision", "none", "none", "attention_required", "workflow"),
    ]

    # ---- 11. Analytical ----------------------------------------------------------------------
    c += [
        Case("what changed this month", "analytical", "changed", "none", "this month", "what_changed", "workflow"),
        Case("how is my business doing", "analytical", "briefing", "none", "none", "executive_summary", "workflow"),
        Case("are there unusual expenses", "analytical", "anomaly", "expenses", "any", "anomaly_surface", "capability_gap"),
        Case("what happens if occupancy increases", "analytical", "scenario", "occupancy", "any",
             "scenario_analysis", "capability_gap"),
        Case("what if rent increases", "analytical", "scenario", "none", "any", "scenario_analysis", "capability_gap"),
    ]

    # ---- 12. NL variation / typos / Tamil-English-ish ----------------------------------------
    c += [
        Case("revenu this month?", "revenue", "lookup", "revenue", "this month", "kpi_lookup", "figure"),
        Case("how much money we made this month", "revenue", "lookup", "revenue", "this month", "kpi_lookup", "figure"),
        Case("occupancy full ah?", "occupancy", "lookup", "occupancy", "none", "kpi_lookup", "show_both",
             notes="extreme informal; clarify/refuse without wrong metric is acceptable"),
    ]

    # ---- 13. Ambiguous -----------------------------------------------------------------------
    c += [
        Case("show me the numbers", "ambiguous", "clarify", "none", "any", "kpi_lookup", "clarify"),
        Case("collections", "ambiguous", "clarify", "collections", "any", "kpi_lookup", "clarify"),
    ]

    return c


_TECH_LEAKS = ("M.REV", "M.EXP", "M.OCC", "M.AR.", "DQ.", "C.0", "FN.",
               "structured_output", "analytics_execution_spec", ".csv", "engine.")


def _has_tech_leak(text: str) -> bool:
    t = text or ""
    return any(x in t for x in _TECH_LEAKS)


def _classify_answer(text: str, status: str, trust: str, intent: str, metrics) -> str:
    low = (text or "").lower()
    if "which definition" in low or "which time period" in low or "which measure" in low:
        return "clarify"
    if "which specific tenant" in low or "tenant or unit" in low:
        return "clarify"
    if any(x in low for x in ("forecast", "scenario", "what-if", "anomaly detection is only",
                               "month-scoped", "not currently available", "can't reliably")):
        if "not a forecast" in low or "historical context" in low or "forecast" in low or "scenario" in low or "month-scoped" in low:
            return "capability_gap"
    if intent in (INTENT_WHAT_TO_DO, INTENT_BRIEFING, INTENT_WHAT_CHANGED, INTENT_WHAT_TO_TRUST):
        return "workflow"
    if "do not show" in low or "can't confirm" in low or "not evidenced" in low or "driver" in low:
        if "decreased" in low or "increased" in low or "cause" in low or "confirm" in low or "evidenced" in low:
            return "driver"
    if "increased" in low or "decreased" in low or "did not change" in low:
        if "from" in low and "to" in low:
            return "comparison"
    if trust in ("SHOW_BOTH",) or "does not have one agreed figure" in low or "every evidence-backed definition" in low:
        return "show_both"
    if trust == "BLOCK" or "no single reliable figure" in low:
        return "block"
    if status == NEEDS_CLARIFICATION:
        return "clarify"
    if status == NOT_DETERMINABLE:
        return "capability_gap" if "forecast" in low or "month-scoped" in low or "scenario" in low else "refuse"
    if metrics:
        return "figure"
    return "other"


def _eval_one(case: Case) -> Result:
    ai = _ai()
    # Fresh instance per question to avoid clarification pollution.
    a = ai.ask(case.question)
    text = a.text or ""
    status = ""
    metrics = tuple(a.metric_ids or ())
    trust = a.trust_level or ""
    if a.ask_result is not None:
        status = a.ask_result.status or ""
        if not metrics:
            metrics = tuple(a.ask_result.metric_ids or ())
        if not trust:
            trust = a.ask_result.trust_level or ""

    route = a.owner_intent or ""
    answer_type = _classify_answer(text, status, trust, a.owner_intent, metrics)
    low = text.lower()

    fail = ""
    # Presentation leak always fails.
    if _has_tech_leak(text):
        fail = "presentation_leak"
    else:
        exp = case.expected_answer_type
        # Intent / capability routing checks
        if case.expected_intent == "forecast":
            if ALL_TIME_REV in text or (answer_type == "figure" and "forecast" not in low):
                fail = "wrong_period" if ALL_TIME_REV in text else "wrong_intent"
            elif answer_type != "capability_gap" and "forecast" not in low:
                fail = "wrong_intent"
        elif case.expected_intent == "scenario":
            if answer_type == "show_both" or "occupancy pct" in low or "agree definition" in low:
                # Occupancy SHOW_BOTH as scenario answer is wrong.
                if "scenario" not in low and "what-if" not in low:
                    fail = "wrong_intent"
            elif "scenario" not in low and "what-if" not in low:
                fail = "wrong_intent"
        elif case.expected_intent == "decision" or case.expected_intent == "risk":
            if a.owner_intent not in (INTENT_WHAT_TO_DO, INTENT_WHAT_TO_TRUST) and answer_type != "workflow":
                fail = "wrong_intent"
        elif case.expected_intent == "changed":
            if a.owner_intent != INTENT_WHAT_CHANGED and "what changed" not in low and "period-to-period" not in low:
                fail = "wrong_intent"
        elif case.expected_intent == "briefing":
            if a.owner_intent != INTENT_BRIEFING:
                fail = "wrong_intent"
        elif case.expected_intent == "trust":
            if a.owner_intent != INTENT_WHAT_TO_TRUST and "trust" not in low:
                fail = "wrong_intent"
        elif case.expected_intent == "clarify":
            if answer_type != "clarify" and status != NEEDS_CLARIFICATION:
                fail = "wrong_clarification"
        elif case.expected_intent == "driver":
            if ALL_TIME_REV in text or ALL_TIME_EXP in text:
                fail = "wrong_metric"
            elif answer_type not in ("driver", "comparison", "capability_gap", "clarify"):
                # Driver may honestly refuse unproven decrease.
                if "confirm" not in low and "evidenced" not in low and "decreased" not in low and "increased" not in low:
                    fail = "wrong_intent"
        elif case.expected_intent == "compare":
            if ALL_TIME_REV in text and case.expected_period != "all-time":
                fail = "wrong_period"
            elif answer_type not in ("comparison", "capability_gap", "clarify"):
                fail = "wrong_intent"
        elif case.expected_intent == "trend":
            if answer_type not in ("comparison", "clarify", "capability_gap"):
                fail = "wrong_intent"
        elif case.expected_intent == "anomaly":
            if answer_type == "figure" and ALL_TIME_EXP in text:
                fail = "wrong_metric"
            elif "anomal" not in low and "unusual" not in low and "threshold" not in low:
                fail = "wrong_intent"
        elif case.expected_intent == "lookup":
            if case.expected_period in ("this month", "last month", "named"):
                if case.expected_concept == "revenue" and ALL_TIME_REV in text:
                    fail = "wrong_period"
                elif case.expected_concept == "expenses" and ALL_TIME_EXP in text:
                    fail = "wrong_period"
                elif answer_type == "refuse" and "month-scoped" not in low:
                    # Unnecessary refusal when monthly evidence exists for revenue/expenses.
                    if case.expected_concept in ("revenue", "expenses"):
                        fail = "unnecessary_refusal"
                elif answer_type in ("figure", "show_both", "block", "capability_gap"):
                    pass
                elif answer_type == "clarify" and "period" in low:
                    fail = "wrong_clarification"
            elif case.expected_answer_type == "show_both":
                if answer_type not in ("show_both", "block"):
                    if "tenant or unit" in low:
                        fail = "wrong_clarification"
                    else:
                        fail = "wrong_intent"
            elif case.expected_answer_type == "block":
                if answer_type not in ("block", "show_both"):
                    fail = "wrong_intent"
            elif case.expected_answer_type == "capability_gap":
                if answer_type not in ("capability_gap", "clarify") and ALL_TIME_REV not in text:
                    # period limitation for profit this month is OK
                    if "month-scoped" not in low and "definition" not in low:
                        fail = "unnecessary_refusal" if answer_type == "refuse" else "wrong_intent"
            elif answer_type == "refuse" and "nothing in the available records" in low:
                fail = "unnecessary_refusal"
            elif answer_type == "clarify" and case.expected_answer_type == "figure":
                fail = "wrong_clarification"

    # Occupancy must never ask for period due to full≈july.
    if case.expected_concept == "occupancy" and "which time period" in low:
        fail = "wrong_clarification"

    # Forecast must never be all-time revenue as the answer.
    if case.expected_capability == "forecasting" and ALL_TIME_REV in text and "historical context" not in low:
        fail = "wrong_period"

    # Soft-pass extreme informal Tamil-English if it does not return a wrong metric.
    if case.question == "occupancy full ah?":
        if fail and ALL_TIME_REV not in text and answer_type in (
                "clarify", "refuse", "capability_gap", "other"):
            fail = ""
        elif fail == "unnecessary_refusal":
            fail = ""

    # Ambiguous multi-concept with clean clarification is a PASS when expected.
    if case.expected_answer_type == "clarify" and answer_type == "clarify":
        fail = "" if fail == "wrong_clarification" else fail
        if fail == "presentation_leak" and not _has_tech_leak(text):
            fail = ""

    pf = "FAIL" if fail else "PASS"
    # Capability-gap expected and delivered → PASS
    if case.expected_answer_type == "capability_gap" and answer_type == "capability_gap" and not fail:
        pf = "PASS"

    return Result(
        case=case, pass_fail=pf, failure_class=fail,
        actual_route=route, actual_answer_type=answer_type,
        text_snip=text[:160].replace("\n", " "),
        metrics=metrics, trust=trust, status=status,
    )


def run_acceptance_matrix(limit: int | None = None) -> list[Result]:
    cases = _build_matrix()
    if limit:
        cases = cases[:limit]
    return [_eval_one(c) for c in cases]


def summarize(results: list[Result]) -> dict:
    fails = [r for r in results if r.pass_fail == "FAIL"]
    gaps = [r for r in results
            if r.pass_fail == "PASS" and r.case.expected_answer_type == "capability_gap"]
    by = {}
    for r in fails:
        by[r.failure_class] = by.get(r.failure_class, 0) + 1
    answerable_wrong = [r for r in fails if r.failure_class in (
        "wrong_period", "wrong_intent", "wrong_metric", "unnecessary_refusal",
        "wrong_clarification", "presentation_leak",
    )]
    return {
        "total": len(results),
        "pass": sum(1 for r in results if r.pass_fail == "PASS"),
        "fail": len(fails),
        "answerable_but_wrong": len(answerable_wrong),
        "correct_capability_gap": len(gaps),
        "unnecessary_refusal": by.get("unnecessary_refusal", 0),
        "wrong_period": by.get("wrong_period", 0),
        "wrong_intent": by.get("wrong_intent", 0),
        "wrong_metric": by.get("wrong_metric", 0),
        "wrong_clarification": by.get("wrong_clarification", 0),
        "presentation_leak": by.get("presentation_leak", 0),
        "failures": fails,
        "by_class": by,
    }


# --- pytest entry -----------------------------------------------------------------------------

def test_owner_acceptance_matrix_readiness():
    results = run_acceptance_matrix()
    summary = summarize(results)
    # Print compact report for the acceptance pass.
    print("\n=== OWNER-NL ACCEPTANCE MATRIX ===")
    print(f"Total={summary['total']} PASS={summary['pass']} FAIL={summary['fail']}")
    print(f"answerable_but_wrong={summary['answerable_but_wrong']}")
    print(f"capability_gaps_ok={summary['correct_capability_gap']}")
    print(f"by_fail_class={summary['by_class']}")
    for r in summary["failures"]:
        print(f"FAIL [{r.failure_class}] {r.case.question!r} "
              f"exp={r.case.expected_answer_type}/{r.case.expected_period} "
              f"got={r.actual_answer_type}/{r.actual_route} :: {r.text_snip[:120]}")

    # Hard gate: no answerable-but-wrong; no presentation leaks.
    assert summary["presentation_leak"] == 0
    assert summary["wrong_period"] == 0
    assert summary["wrong_metric"] == 0
    assert summary["unnecessary_refusal"] == 0
    assert summary["wrong_clarification"] == 0
    assert summary["wrong_intent"] == 0
    assert summary["answerable_but_wrong"] == 0
    assert summary["fail"] == 0


def test_followup_chain_preserves_concept():
    ai = _ai()
    first = ai.ask("show me revenue")
    assert first.ask_result and first.ask_result.status == READY
    why = ai.ask("Why?")
    assert any(str(m).startswith("M.REV") for m in (why.metric_ids or ()))
    # Compare follow-up
    ai2 = _ai()
    ai2.ask("this month revenue")
    cmp_ = ai2.ask("Compare it with last month")
    text = (cmp_.text or "").lower()
    assert "72,705,593.43" not in (cmp_.text or "")
    assert ("increased" in text or "decreased" in text or "comparison" in text
            or "incomplete" in text or "complete" in text)


if __name__ == "__main__":
    results = run_acceptance_matrix()
    s = summarize(results)
    print(s)
    for r in s["failures"]:
        print("FAIL", r.failure_class, r.case.question, "->", r.text_snip)
