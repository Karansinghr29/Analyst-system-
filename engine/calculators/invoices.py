"""
invoices.py -- M.INV.001/002. Filters/aggregation per business_logic.md 3, confirmed against
H.001/H.049 in Phase E (invoices are not one of the 12 dedicated validate_*.py scripts, but the
same reconstruction logic underlies M.PROFIT.001 Def B and M.RISK.005, both validated).
"""
from engine.evidence_loader import load_table, money
from engine.calculators.base import CalcOutput


def _live_invoices():
    inv = load_table("invoices")
    return inv[inv["is_deleted"].astype(str).str.lower() != "true"]


def calc_invoice_billed_amount(spec):
    live = _live_invoices()
    total = round(float(money(live["total_amount"]).sum()), 2)
    return CalcOutput(
        value=total, unit="INR",
        evidence_sources=("T.invoices", "H.001"),
        provenance="SUM(invoices.total_amount) WHERE NOT is_deleted.",
        limitations="6.8% of live invoices (356 of 5214) are duplicate rows across 322 groups, no application-level dedup mechanism (DQ.013/C.020). 42.7% show amount_paid+balance != total_amount internally (DQ.001, CRITICAL).",
    )


def calc_invoice_count(spec):
    live = _live_invoices()
    by_type = live["invoice_type"].value_counts().to_dict()
    return CalcOutput(
        value={"total": int(len(live)), "by_type": by_type}, unit="invoices",
        evidence_sources=("T.invoices", "H.035"),
        provenance="COUNT(*) FROM invoices WHERE NOT is_deleted, grouped by invoice_type.",
        limitations="Duplicate-aware count would be 5214-356=4858 unique (allotment,billing_month,invoice_type) invoices (DQ.013).",
    )
