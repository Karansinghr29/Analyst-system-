"""
collections_.py -- M.COL.001/002/003. Ported from scripts/validation/validate_collections.py
(COLL.01-03, all confirmed exact in Phase E, including the DQ.030 execution-proof).

Module named collections_ (trailing underscore) to avoid shadowing the stdlib `collections`
module.
"""
import pandas as pd

from engine.evidence_loader import load_table, money
from engine.calculators.base import CalcOutput
from engine.calculators import ledger as L


def _live_receipts():
    r = load_table("receipts")
    return r[r["is_deleted"].astype(str).str.lower() != "true"]


def calc_collections_application(spec):
    live = _live_receipts()
    total = round(float(money(live["amount_paid"]).sum()), 2)
    deposit = round(float(money(live.loc[live["receipt_type"] == "booking", "amount_paid"]).sum()), 2)
    return CalcOutput(
        value={"total": total, "deposit_collections": deposit, "non_deposit": round(total - deposit, 2)},
        unit="INR", evidence_sources=("T.receipts", "H.001"),
        provenance="SUM(receipts.amount_paid) WHERE NOT is_deleted; deposit subset WHERE receipt_type='booking'.",
        limitations="Excludes ~0.15% still-live undeduplicated flagged-duplicate receipts (DQ.014). Does not reconcile against the ledger by default (see M.COL.003).",
    )


def calc_collections_by_month(spec):
    live = _live_receipts().copy()
    live["month"] = pd.to_datetime(live["payment_date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    grouped = live.groupby("month")["amount_paid"].apply(lambda s: round(float(money(s).sum()), 2))
    series = {str(k.date()): v for k, v in grouped.items()}
    return CalcOutput(
        value=series, unit="INR/month", evidence_sources=("T.receipts",),
        provenance="GROUP BY date_trunc('month', payment_date).",
    )


def calc_collections_ledger(spec):
    m = L.ledger_excl_reversals()
    f = m[(m["source_table"] == "receipts") & (m["code"].isin(["1110", "1120"]))]
    total = round(float(f["debit"].sum()), 2)
    return CalcOutput(
        value=total, unit="INR",
        evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts", "H.001"),
        provenance="SUM(debit) WHERE source_table='receipts' AND account_code IN ('1110','1120'), reversal-excluded.",
        limitations="Rs.5,340,795.62 aggregate diagnostic gap vs application-level total (DQ.006/C.014) -- suspected repost-accumulation, not proven from an exported query.",
    )
