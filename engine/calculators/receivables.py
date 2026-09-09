"""
receivables.py -- the 4-way tenant-dues conflict (M.AR.001A-D), the single most consequential
BLOCK family in the semantic layer. Logic ported from
scripts/validation/validate_receivables.py (AR.01-AR.04c, all confirmed in Phase E).

M.AR.001A and M.AR.001B are separate metric_ids (SHOW_BOTH, not BLOCK) -- each returns a single
value with its own trust posture. M.AR.001C and M.AR.001D are also separate metric_ids (BLOCK).
This module provides one calculator per metric_id PLUS a combined 4-way view used by
M.AR.002/M.AR.003/M.RISK.001, which explicitly must never collapse to one number.
"""
import pandas as pd

from engine.evidence_loader import load_table, money, coa_accounts_str_code
from engine.calculators.base import CalcOutput
from engine.calculators import ledger as L


def _ar_lines_incl():
    """Raw journal_lines on account 1200, party_kind='tenant' -- reversal-INCLUDED (Def B basis)."""
    m = L.ledger_incl_reversals()
    return m[(m["code"] == "1200") & (m["party_kind"] == "tenant")]


def _ar_lines_excl():
    """Same, reversal-EXCLUDED (Def A basis)."""
    m = L.ledger_excl_reversals()
    return m[(m["code"] == "1200") & (m["party_kind"] == "tenant")]


def calc_ar_def_a(spec, tenant_id=None, allotment_id=None):
    """M.AR.001A: v_outstanding_receivables -- reversal-excluded."""
    f = _ar_lines_excl()
    if allotment_id is not None:
        f = f[f["allotment_id"] == allotment_id]
    elif tenant_id is not None:
        f = f[f["party_id"] == tenant_id]
    total = round(float(f["signed_amount"].sum()), 2)
    return CalcOutput(
        value=total, unit="INR",
        evidence_sources=("F.006", "T.journal_lines", "T.journal_entries", "T.coa_accounts"),
        provenance="SUM(signed_amount) WHERE account_code='1200' AND party_kind='tenant', reversal-excluded.",
        limitations="Does not include deposit_held/booking_advance -- see M.AR.001B for those.",
    )


def calc_ar_def_b(spec, tenant_id=None, allotment_id=None):
    """M.AR.001B: v_tenant_current_dues -- reversal-included, plus deposit_held/booking_advance."""
    m = L.ledger_incl_reversals()
    f = m[m["party_kind"] == "tenant"]
    if allotment_id is not None:
        f = f[f["allotment_id"] == allotment_id]
    elif tenant_id is not None:
        f = f[f["party_id"] == tenant_id]
    ar = float((f.loc[f["code"] == "1200", "debit"] - f.loc[f["code"] == "1200", "credit"]).sum())
    dep = float((f.loc[f["code"] == "2100", "credit"] - f.loc[f["code"] == "2100", "debit"]).sum())
    adv = float((f.loc[f["code"] == "2400", "credit"] - f.loc[f["code"] == "2400", "debit"]).sum())
    return CalcOutput(
        value={"ar_balance": round(ar, 2), "deposit_held": round(dep, 2), "booking_advance": round(adv, 2)},
        unit="INR", evidence_sources=("F.007", "T.journal_lines", "T.journal_entries", "T.coa_accounts"),
        provenance="Per-account SUM for 1200/2100/2400, reversal-included, party_kind='tenant'.",
        limitations="charge_count/payment_count (not computed here) are NOT reversal-neutral even though dollar totals are.",
    )


def calc_ar_def_c(spec, tenant_id=None, allotment_id=None):
    """M.AR.001C: application tenant_allotments.balance_due -- BLOCK."""
    ta = load_table("tenant_allotments")
    f = ta
    if allotment_id is not None:
        f = f[f["id"] == allotment_id]
    elif tenant_id is not None:
        f = f[f["tenant_id"] == tenant_id]
    total = round(float(money(f["balance_due"]).sum()), 2)
    return CalcOutput(
        value=total, unit="INR",
        evidence_sources=("T.tenant_allotments",),
        provenance="tenant_allotments.balance_due, as stored. Writer not among the 25 exported function bodies.",
        limitations="~12x the ledger total (Def A/B) at the portfolio level; 68 allotments show a phantom app-side balance where the ledger shows zero.",
    )


def calc_ar_def_d(spec, tenant_id=None, allotment_id=None):
    """M.AR.001D: tenant_transactions (frozen legacy) -- BLOCK. Two sub-variants preserved."""
    tt = load_table("tenant_transactions")
    cp = tt[tt["ledger_type"].isin(["CHARGE", "PAYMENT"])].copy()
    if allotment_id is not None:
        cp = cp[cp["allotment_id"] == allotment_id]
    elif tenant_id is not None:
        cp = cp[cp["tenant_id"] == tenant_id]
    cp["signed"] = cp.apply(
        lambda r: money(pd.Series([r["amount"]])).iloc[0] if r["direction"] == "DEBIT"
        else -money(pd.Series([r["amount"]])).iloc[0], axis=1)
    by_allot = cp.groupby("allotment_id")["signed"].sum()
    unclipped = round(float(by_allot.sum()), 2)
    floored = round(float(by_allot.clip(lower=0).sum()), 2)
    return CalcOutput(
        value={"unclipped": unclipped, "floored_at_zero": floored}, unit="INR",
        evidence_sources=("T.tenant_transactions",),
        provenance="SUM(DEBIT)-SUM(CREDIT) on CHARGE/PAYMENT rows per allotment; unclipped and GREATEST(...,0)-floored variants both preserved.",
        limitations="Frozen: all rows created_at 2026-04-17 to 2026-04-28, never wired to a live posting trigger (DQ.019). ~120x the ledger total.",
    )


def calc_ar_four_way(spec, tenant_id=None, allotment_id=None):
    """The M.AR.002/M.AR.003/M.RISK.001 view: all four definitions, never collapsed."""
    a = calc_ar_def_a(spec, tenant_id, allotment_id)
    b = calc_ar_def_b(spec, tenant_id, allotment_id)
    c = calc_ar_def_c(spec, tenant_id, allotment_id)
    d = calc_ar_def_d(spec, tenant_id, allotment_id)
    subs = {
        "Def A: v_outstanding_receivables (reversals excluded)": a,
        "Def B: v_tenant_current_dues (reversals included)": b,
        "Def C: application tenant_allotments.balance_due": c,
        "Def D: tenant_transactions (frozen legacy)": d,
    }
    return CalcOutput(subs=subs, provenance="4-way tenant-balance conflict (C.001/C.003/C.005, DQ.002/DQ.019). Def A==Def B for the total (proven); Def C and Def D each disagree by 1-2 orders of magnitude.")
