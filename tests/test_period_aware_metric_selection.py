"""
PERIOD_AWARE_METRIC_SELECTION_AND_EXECUTION

Shared contract: a resolved period must be enforced at metric selection and
presentation. All-time totals must never silently answer a month-scoped ask.

Covers the failure class evidenced by:
  - revenue this month evlo  → must not execute M.REV.001 all-time
  - August expenses          → must not execute M.EXP.001 all-time
  - last month collection    → must not become generic NOT_DETERMINABLE when a
                               period-capable series exists (after definition choice)
"""
from engine.llm_interface import LLMInterface
from engine.llm_provider import DeterministicMockProvider
from engine.question_understanding import QuestionUnderstander
from engine.semantic_registry import SemanticRegistry
from engine.intent_models import READY, NEEDS_CLARIFICATION, NOT_DETERMINABLE
from engine.question_normalize import normalize_owner_question

ALL_TIME_REV = "72,705,593.43"
ALL_TIME_EXP = "20,784,831"


def _iface():
    return LLMInterface(provider=DeterministicMockProvider(), verbalize=False)


def _assert_period_revenue(q):
    r = _iface().ask(q)
    assert r.status == READY and r.executed, (q, r.status, (r.text or "")[:160])
    assert "M.REV.001" not in (r.metric_ids or ()), (q, r.metric_ids)
    assert "M.REV.002" in r.metric_ids, (q, r.metric_ids)
    assert ALL_TIME_REV not in (r.text or ""), (q, r.text)
    assert r.plan is not None and r.plan.time is not None
    assert r.plan.time.period_label != "all-time", (q, r.plan.time.period_label)


def _assert_period_expenses(q):
    r = _iface().ask(q)
    assert r.status == READY and r.executed, (q, r.status, (r.text or "")[:160])
    assert "M.EXP.001" not in (r.metric_ids or ()), (q, r.metric_ids)
    assert "M.PNL.001" in r.metric_ids or "M.EXP.002" in r.metric_ids, (q, r.metric_ids)
    assert ALL_TIME_EXP not in (r.text or ""), (q, r.text)
    assert r.plan.time is not None and r.plan.time.period_label != "all-time"


# ---------------------------------------------------------------------------
# Revenue period class
# ---------------------------------------------------------------------------

def test_revenue_period_variants_select_monthly_series():
    for q in (
        "revenue this month",
        "this month revenue",
        "current month revenue",
        "this month's revenue",
        "revenue this month evlo",
        "revenue last month",
        "August revenue",
        "August 2026 revenue",
    ):
        _assert_period_revenue(q)


def test_forced_all_time_revenue_metric_id_still_redirects_for_period():
    """Model/clarification paths that force M.REV.001 must not keep all-time."""
    u = QuestionUnderstander(SemanticRegistry())
    und = u.understand("revenue this month evlo", metric_id="M.REV.001")
    assert und.metric is not None
    assert und.metric.metric_ids == ("M.REV.002",), und.metric.metric_ids
    assert und.time is not None and und.time.period_label != "all-time"
    assert not und.not_determinable_reason


# ---------------------------------------------------------------------------
# Expenses period class
# ---------------------------------------------------------------------------

def test_expenses_period_variants_select_period_series():
    for q in (
        "August expenses",
        "expenses this month",
        "this month expenses",
        "last month expenses",
        "August 2026 expenses",
    ):
        _assert_period_expenses(q)


def test_forced_all_time_expense_metric_id_still_redirects_for_period():
    u = QuestionUnderstander(SemanticRegistry())
    und = u.understand("August expenses", metric_id="M.EXP.001")
    assert und.metric is not None
    assert "M.EXP.001" not in und.metric.metric_ids
    assert und.metric.metric_ids[0] in ("M.PNL.001", "M.EXP.002")
    assert und.time is not None and und.time.period_label != "all-time"


# ---------------------------------------------------------------------------
# Collections period class — clarification preserved, then period executed
# ---------------------------------------------------------------------------

def test_collections_period_clarifies_then_executes_monthly_series():
    for q in (
        "collection this month",
        "this month collection",
        "last month collection",
        "money collected this month",
        "collection last month",
        "last month collection epdi",
    ):
        iface = _iface()
        r1 = iface.ask(q)
        assert r1.status == NEEDS_CLARIFICATION, (q, r1.status, (r1.text or "")[:160])
        text = (r1.text or "").lower()
        assert "definition" in text or "collections" in text, (q, text[:160])
        assert "not determinable from exported evidence" not in text, q

        # Pick application-level definition (option 1); period must survive.
        r2 = iface.ask("1")
        assert r2.status == READY and r2.executed, (q, r2.status, (r2.text or "")[:200])
        assert "M.COL.002" in r2.metric_ids, (q, r2.metric_ids)
        assert "M.COL.001" not in (r2.metric_ids or ()), (q, r2.metric_ids)
        assert r2.plan.time is not None and r2.plan.time.period_label != "all-time", q
        assert "not determinable from exported evidence" not in (r2.text or "").lower() or (
            "month" in (r2.text or "").lower()
        ), (q, r2.text)


def test_forced_col001_with_period_redirects_to_monthly():
    u = QuestionUnderstander(SemanticRegistry())
    und = u.understand("last month collection", metric_id="M.COL.001")
    assert und.metric is not None
    assert und.metric.metric_ids == ("M.COL.002",), und.metric.metric_ids
    assert und.time is not None and und.time.period_label == "last month"


# ---------------------------------------------------------------------------
# Cross-domain: occupancy / another period-capable family if available
# ---------------------------------------------------------------------------

def test_period_enforcement_not_revenue_specific_occupancy_or_dues_safe():
    """Smoke: period ask on another concept must not silently become all-time primary."""
    iface = _iface()
    # Occupancy this month — whatever metric is chosen, must not be an all-time substitute
    # that drops the period from the plan.
    r = iface.ask("occupancy this month")
    if r.status == READY and r.plan is not None and r.plan.time is not None:
        assert r.plan.time.period_label != "all-time"
    elif r.status == NEEDS_CLARIFICATION:
        assert "which" in (r.text or "").lower() or "definition" in (r.text or "").lower()
    else:
        # Honest limitation is OK; generic empty refusal is not when period was named.
        assert r.plan is None or r.plan.time is None or r.plan.time.period_label != "all-time" \
            or r.status == NOT_DETERMINABLE


def test_normalize_preserves_period_particles_for_collections():
    nq, _ = normalize_owner_question("last month collection epdi")
    assert "last month" in nq
    assert "collection" in nq
