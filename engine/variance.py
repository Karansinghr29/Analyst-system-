"""
variance.py -- the components behind a movement the change detector already reported.

This module does not detect a movement, decide a period, or judge trust. It takes a `Change`
the detector has already produced and asks one narrow question: can the rows that made that
movement be split into named parts that add back up to it exactly?

Only a genuine PARTITION qualifies. A component set here is the same rows the metric itself
summed, grouped one level finer, under the metric's own conventions -- the same reversal
exclusion, the same live-row filter, the same month derivation. Nothing is modelled, allocated,
apportioned or estimated: if a rupee is in the total it is in exactly one component, and if it
is in a component it is in the total.

The reconciliation is checked, not assumed, and it is checked three ways:

    sum(components in the current period)  == the movement's current value
    sum(components in the previous period) == the movement's previous value
    sum(component movements)               == the movement's own change

All three must hold to the cent. Any of them failing means the split is not a split of this
measure, and the honest answer -- that a component-level explanation is not available from the
exported evidence -- is returned instead of a bridge that looks exact and is not. That outcome
is a result, not a failure.

What is deliberately NOT decomposable here:

  * profit -- its definitions are BLOCKED; a bridge would make a blocked measure look answered
  * P&L by month -- its monthly value is composite, so the detector reports no single movement
    to reconcile against, and choosing one component as "the" movement would be a definition
    decision this layer may not make
  * occupancy, maintenance, risk and data-quality findings -- these are counts and conditions,
    not sums with an additive structure, and a financial-style bridge over them would be a
    shape imposed on evidence that does not have it
"""
from dataclasses import dataclass, field

import pandas as pd

from engine.evidence_loader import load_table, money
from engine.calculators import ledger as L

# A rupee. Everything here is already rounded to two places by the calculators, so a difference
# below half a paisa is float representation and anything above it is a real gap.
TOLERANCE = 0.005

UNAVAILABLE = ("A component-level explanation is not available from the exported evidence.")


@dataclass(frozen=True)
class Component:
    label: str
    current_value: float
    previous_value: float
    change: float


@dataclass(frozen=True)
class Decomposition:
    metric_id: str = ""
    available: bool = False
    components: tuple = ()
    total_change: float = 0.0
    unavailable_reason: str = ""
    # The parts and the whole, kept separate so the caller can state the relationship rather
    # than assert it.
    component_sum: float = 0.0
    basis: str = ""                       # what the parts ARE, in the owner's words
    caveats: tuple = field(default_factory=tuple)


# -- component sources -----------------------------------------------------------------------
#
# One per decomposable measure. Each returns {period_key: {component_label: amount}} using the
# SAME grouping keys and the SAME conventions as the metric's own calculator, so the parts are
# that metric's rows and not a second reading of the evidence.


def _revenue_components():
    """M.REV.002's own rows, grouped by the income account they were posted to.

    `calc_revenue_by_month` sums INCOME `signed_amount` over the reversal-excluded ledger,
    grouped by (property_id, month). This adds the account as a third key and accumulates into
    the month, so the account names are a partition of exactly that sum. The account NAME is
    used, never its code: "Rental Income" is what the business calls it.
    """
    m = L.ledger_excl_reversals()
    income = m[m["account_type"] == "INCOME"].copy()
    if income.empty:
        return {}
    income["month"] = pd.to_datetime(income["entry_date"]).dt.to_period("M").dt.to_timestamp()
    grouped = income.groupby(["property_id", "month", "name"], dropna=False)["signed_amount"].sum()
    out = {}
    for (_prop, month, name), value in grouped.items():
        key = str(month.date())
        label = str(name).strip() or "Unnamed income account"
        bucket = out.setdefault(key, {})
        bucket[label] = round(bucket.get(label, 0.0) + float(value), 2)
    return out


# The receipt categories the collections tile itself already shows. Reusing them keeps one
# vocabulary for one measure: an owner reading "Deposits" beside the total reads the same word
# beside the movement.
_RECEIPT_LABELS = {"booking": "Deposits"}
_RECEIPT_DEFAULT = "Rent and other"


def _collections_components():
    """M.COL.002's own rows, grouped by the receipt category the collections total already
    splits on (`receipt_type='booking'` versus the rest)."""
    receipts = load_table("receipts")
    live = receipts[receipts["is_deleted"].astype(str).str.lower() != "true"].copy()
    if live.empty:
        return {}
    live["month"] = pd.to_datetime(live["payment_date"], errors="coerce").dt.to_period(
        "M").dt.to_timestamp()
    live["amount"] = money(live["amount_paid"])
    out = {}
    for (month, kind), value in live.groupby(["month", "receipt_type"], dropna=False)["amount"].sum().items():
        if pd.isna(month):
            continue
        label = _RECEIPT_LABELS.get(str(kind).strip().lower(), _RECEIPT_DEFAULT)
        bucket = out.setdefault(str(month.date()), {})
        bucket[label] = round(bucket.get(label, 0.0) + float(value), 2)
    return out


# metric -> (component source, what the parts are, caveats that belong to the split itself)
SOURCES = {
    "M.REV.002": (_revenue_components, "income category", ()),
    "M.COL.002": (_collections_components, "receipt category",
                  ("Receipts flagged as duplicates that are still recorded as live are "
                   "included here exactly as they are in the total.",)),
}


def _numeric(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def decompose(change):
    """The components behind one reported movement, or an honest refusal.

    A decomposition is offered ONLY for a movement the detector actually measured. A partial
    period, an unavailable comparison and a blocked measure all fail that test before any
    component is looked at, so no bridge can be built over a movement that was never reported.
    """
    metric_id = getattr(change, "metric_id", "")
    if metric_id not in SOURCES:
        return Decomposition(metric_id=metric_id, available=False)

    if not getattr(change, "detected", False):
        # No measured movement to explain. Saying so is the whole answer; a component list
        # beside a comparison the engine declined to make would read as that comparison.
        return Decomposition(metric_id=metric_id, available=False)

    total_change = _numeric(getattr(change, "absolute_change", None))
    current_total = _numeric(getattr(change, "current_value", None))
    previous_total = _numeric(getattr(change, "previous_value", None))
    if total_change is None or current_total is None or previous_total is None:
        return Decomposition(metric_id=metric_id, available=False,
                             unavailable_reason=UNAVAILABLE)

    source, basis, caveats = SOURCES[metric_id]
    try:
        series = source()
    except Exception:
        # Evidence that will not load is evidence that cannot support a split.
        return Decomposition(metric_id=metric_id, available=False,
                             unavailable_reason=UNAVAILABLE)

    current = series.get(change.current_period)
    previous = series.get(change.previous_period)
    if current is None or previous is None:
        return Decomposition(metric_id=metric_id, available=False,
                             unavailable_reason=UNAVAILABLE)

    labels = sorted(set(current) | set(previous))
    components = tuple(
        Component(label=label,
                  current_value=round(float(current.get(label, 0.0)), 2),
                  previous_value=round(float(previous.get(label, 0.0)), 2),
                  change=round(float(current.get(label, 0.0)) - float(previous.get(label, 0.0)), 2))
        for label in labels)

    component_sum = round(sum(c.change for c in components), 2)
    current_sum = round(sum(c.current_value for c in components), 2)
    previous_sum = round(sum(c.previous_value for c in components), 2)

    reconciles = (abs(current_sum - current_total) < TOLERANCE
                  and abs(previous_sum - previous_total) < TOLERANCE
                  and abs(component_sum - total_change) < TOLERANCE)
    if not reconciles:
        # The parts are not the parts of this total. Presenting them anyway would put a bridge
        # under a figure it does not reach.
        return Decomposition(metric_id=metric_id, available=False,
                             unavailable_reason=UNAVAILABLE)

    # Largest mover first: the reader is asking what drove the change, and the answer to that
    # is a ranking by size of contribution, not by name.
    ordered = tuple(sorted(components, key=lambda c: abs(c.change), reverse=True))
    return Decomposition(
        metric_id=metric_id, available=True, components=ordered,
        total_change=round(total_change, 2), component_sum=component_sum,
        basis=basis, caveats=tuple(caveats))
