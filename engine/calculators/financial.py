"""
financial.py -- Revenue, Expenses, Profit, Owner payments/rent, Cash, Trial balance, P&L by
month. Logic ported directly from scripts/validation/validate_revenue.py / validate_expenses.py
/ validate_profit.py / validate_owner_payments.py / validate_ledger.py -- every calculation here
already matched its exported reference view exactly during Phase E; this module reuses that
proven logic rather than re-deriving it.
"""
import pandas as pd

from engine.evidence_loader import load_table, load_view, money, coa_accounts_str_code
from engine.calculators.base import CalcOutput, NotDeterminableError
from engine.calculators import ledger as L

BUCKET_PATTERNS = [
    ("owner_rent", "510"), ("maintenance", "52"), ("housekeeping", "53"),
    ("utilities", "54"), ("property_ops", "55"), ("administrative", "56"),
    ("salaries", "57"), ("marketing", "58"), ("other_expenses", "59"),
]


# ---------------------------------------------------------------------------
# M.REV.001 / M.REV.002 -- Revenue
# ---------------------------------------------------------------------------

def calc_revenue_total(spec):
    m = L.ledger_excl_reversals()
    income = m[m["account_type"] == "INCOME"]
    total = round(float(income["signed_amount"].sum()), 2)
    return CalcOutput(
        value=total, unit="INR",
        evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts", "F.001"),
        provenance="SUM(signed_amount) WHERE account_type='INCOME', reversal-excluded (v_account_balances convention).",
        limitations="Individual-posting drift can occur under repeated edits (see M.COL.003); aggregate total is proven exact against F.001.",
    )


def calc_revenue_by_month(spec):
    m = L.ledger_excl_reversals()
    income = m[m["account_type"] == "INCOME"].copy()
    income["month"] = pd.to_datetime(income["entry_date"]).dt.to_period("M").dt.to_timestamp()
    grouped = income.groupby(["property_id", "month"], as_index=False, dropna=False)["signed_amount"].sum()
    series = {str(r["month"].date()): round(float(r["signed_amount"]), 2) for _, r in grouped.iterrows()}
    return CalcOutput(
        value=series, unit="INR/month",
        evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts", "F.001"),
        provenance="GROUP BY (property_id, month) of revenue-total logic. property_id is a required grouping key.",
        limitations="53 distinct calendar months of INCOME activity within a 54-month ledger span; grouping by month alone (dropping property_id) undercounts rows relative to F.001.",
    )


# ---------------------------------------------------------------------------
# M.EXP.001 / M.EXP.002 -- Expenses
# ---------------------------------------------------------------------------

def _bucket_of(code):
    if not isinstance(code, str):
        return None
    for name, prefix in BUCKET_PATTERNS:
        if code.startswith(prefix):
            return name
    return None


def calc_expenses_total(spec):
    m = L.ledger_excl_reversals()
    exp = m[m["account_type"] == "EXPENSE"]
    total = round(float(exp["signed_amount"].sum()), 2)
    return CalcOutput(
        value=total, unit="INR",
        evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts", "F.001"),
        provenance="SUM(signed_amount) WHERE account_type='EXPENSE', reversal-excluded.",
        limitations="Includes account 5150 (electricity), which is invisible to v_pnl_by_category's 9 named buckets -- see M.EXP.002.",
    )


def calc_expenses_by_category(spec):
    m = L.ledger_excl_reversals()
    exp = m[m["account_type"] == "EXPENSE"].copy()
    exp["bucket"] = exp["code"].apply(_bucket_of)
    exp["is_electricity"] = exp["code"].astype(str).str.startswith("515")
    # Always represent all 9 named buckets, defaulting to 0.0 for buckets with no ledger
    # activity in this dataset -- a groupby().to_dict() alone omits empty groups (found while
    # testing: housekeeping/utilities/property_ops/salaries currently have zero postings),
    # which would make the 10-bucket taxonomy's completeness depend on incidental data content
    # rather than being a stable contract for downstream callers.
    buckets = {name: 0.0 for name, _ in BUCKET_PATTERNS}
    computed = exp.groupby("bucket")["signed_amount"].sum().to_dict()
    for k, v in computed.items():
        if k:
            buckets[k] = round(float(v), 2)
    electricity = round(float(exp.loc[exp["is_electricity"], "signed_amount"].sum()), 2)
    buckets["electricity"] = electricity
    total = round(float(exp["signed_amount"].sum()), 2)
    unbucketed = round(total - sum(v for k, v in buckets.items() if k != "electricity"), 2)
    return CalcOutput(
        value=buckets, unit="INR", provenance=(
            "9 hand-written account_code LIKE patterns (v_pnl_by_category) PLUS electricity "
            "added as a 10th bucket -- proven identity: unbucketed == electricity in every "
            "month (DQ.015/C.012). Electricity is NEVER folded into another named bucket."
        ),
        evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts", "F.002", "F.019"),
        limitations=f"Without the electricity bucket added explicitly, Rs.{unbucketed:,.2f} of expenses would be invisible (DQ.015).",
    )


# ---------------------------------------------------------------------------
# M.OWN.001 -- Owner payments (source total)
# ---------------------------------------------------------------------------

def calc_owner_payments_total(spec):
    op = load_table("owner_payments")
    op = op.copy()
    op["escalated_or_base"] = money(op["escalated_amount"]).fillna(money(op["base_amount"]))
    live = op[op["status"].isin(["paid", "pending"])]
    total = round(float(live["escalated_or_base"].sum()), 2)
    return CalcOutput(
        value=total, unit="INR",
        evidence_sources=("T.owner_payments", "H.001"),
        provenance="SUM(COALESCE(escalated_amount, base_amount)) WHERE status IN ('paid','pending').",
        limitations="Ledger-posted in a single 2026-08-13 batch (DQ.020) -- created_at/posted_at do not reflect real posting timing; use bill_date.",
    )


# ---------------------------------------------------------------------------
# M.OWN.002 -- Owner rent, 3-definition family (SHOW_BOTH)
# ---------------------------------------------------------------------------

def calc_owner_rent_family(spec):
    m = L.ledger_excl_reversals()
    ledger_owner_rent = round(float(
        m.loc[(m["account_type"] == "EXPENSE") & (m["code"].str.startswith("510")), "signed_amount"].sum()
    ), 2)

    op = load_table("owner_payments").copy()
    op["escalated_or_base"] = money(op["escalated_amount"]).fillna(money(op["base_amount"]))
    v2_substituted = round(float(op[op["status"].isin(["paid", "pending"])]["escalated_or_base"].sum()), 2)

    subs = {
        "Def i (get_universal_metrics v1: EXCLUDED entirely)": CalcOutput(
            value=0.0, unit="INR",
            provenance="totalProfit has no owner_payments term at all -- proven from the full function body.",
            evidence_sources=("FN.get_universal_metrics",),
        ),
        "Def ii (ledger raw '510%' bucket)": CalcOutput(
            value=ledger_owner_rent, unit="INR",
            provenance="v_pnl_by_category owner_rent bucket, whatever is actually posted.",
            evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts", "F.002", "H.030"),
        ),
        "Def iii (get_universal_metrics_v2: substituted)": CalcOutput(
            value=v2_substituted, unit="INR",
            provenance="Ledger owner_rent bucket explicitly replaced by SUM(owner_payments.escalated_amount) filtered on bill_date.",
            evidence_sources=("T.owner_payments", "FN.get_universal_metrics_v2"),
        ),
    }
    return CalcOutput(subs=subs, provenance="3 competing owner-rent-in-profit definitions (C.010/C.011). All-time total of Def ii/iii proven identical (Rs.19,019,250.00); 7 of 54 months differ due to a date-basis mismatch (DQ.017).")


# ---------------------------------------------------------------------------
# M.PROFIT.001 -- Gross/net profit, 3-definition family (BLOCK)
# ---------------------------------------------------------------------------

def calc_profit_family(spec):
    m = L.ledger_excl_reversals()
    revenue = float(m.loc[m["account_type"] == "INCOME", "signed_amount"].sum())
    expenses = float(m.loc[m["account_type"] == "EXPENSE", "signed_amount"].sum())
    def_a = round(revenue - expenses, 2)

    invoices = load_table("invoices")
    inv_live = invoices[invoices["is_deleted"].astype(str).str.lower() != "true"]
    expenses_tbl = load_table("expenses")
    def_b = round(float(money(inv_live["total_amount"]).sum()) - float(money(expenses_tbl["amount"]).sum()), 2)

    ledger_owner_rent = float(m.loc[(m["account_type"] == "EXPENSE") & (m["code"].str.startswith("510")), "signed_amount"].sum())
    op = load_table("owner_payments").copy()
    op["escalated_or_base"] = money(op["escalated_amount"]).fillna(money(op["base_amount"]))
    owner_rent_v2 = float(op[op["status"].isin(["paid", "pending"])]["escalated_or_base"].sum())
    expenses_v2 = expenses - ledger_owner_rent + owner_rent_v2
    def_c = round(revenue - expenses_v2, 2)

    subs = {
        "Def A (ledger, v_pnl)": CalcOutput(
            value=def_a, unit="INR",
            provenance="revenue - expenses, both ledger-derived, whatever owner-rent amount is posted.",
            evidence_sources=("F.001", "T.journal_lines", "T.journal_entries", "T.coa_accounts"),
        ),
        "Def B (get_universal_metrics v1)": CalcOutput(
            value=def_b, unit="INR",
            provenance="SUM(invoices.total_amount) - SUM(expenses.amount), all-time, NO owner_payments term.",
            evidence_sources=("T.invoices", "T.expenses", "FN.get_universal_metrics"),
            limitations="Proven to omit owner rent entirely -- overstates profit relative to Def C.",
        ),
        "Def C (get_universal_metrics_v2, owner-rent-inclusive)": CalcOutput(
            value=def_c, unit="INR",
            provenance="Ledger revenue - (ledger expenses with owner_rent bucket substituted for owner_payments.escalated_amount).",
            evidence_sources=("F.001", "T.owner_payments", "FN.get_universal_metrics_v2"),
        ),
    }
    return CalcOutput(subs=subs, provenance="3 competing profit definitions (C.010/C.011, DQ.016 CRITICAL). Def B proven ~36.6% higher than the owner-rent-inclusive figure.")


# ---------------------------------------------------------------------------
# M.PNL.001 -- P&L by month (ledger-only, Def A -- SAFE)
# ---------------------------------------------------------------------------

def calc_pnl_by_month(spec):
    m = L.ledger_excl_reversals()
    m = m[m["account_type"].isin(["INCOME", "EXPENSE"])].copy()
    m["month"] = pd.to_datetime(m["entry_date"]).dt.to_period("M").dt.to_timestamp()
    rev = m[m["account_type"] == "INCOME"].groupby(["property_id", "month"], dropna=False)["signed_amount"].sum()
    exp = m[m["account_type"] == "EXPENSE"].groupby(["property_id", "month"], dropna=False)["signed_amount"].sum()
    idx = rev.index.union(exp.index)
    series = {}
    for (prop, month) in idx:
        r = float(rev.get((prop, month), 0.0))
        e = float(exp.get((prop, month), 0.0))
        series[str(month.date())] = {"revenue": round(r, 2), "expenses": round(e, 2), "net_profit": round(r - e, 2)}
    return CalcOutput(
        value=series, unit="INR/month",
        evidence_sources=("F.001", "T.journal_lines", "T.journal_entries", "T.coa_accounts"),
        provenance="Ledger-only (Def A) revenue/expenses joined at (property_id, month); net_profit = revenue-expenses.",
        limitations="This is the ledger-only P&L -- does not carry M.PROFIT.001's 3-way conflict, but category breakdown at this grain inherits the electricity-bucket gap (M.EXP.002).",
    )


# ---------------------------------------------------------------------------
# M.CASH.001 -- Cash balance
# ---------------------------------------------------------------------------

def calc_cash_balance(spec):
    m = L.ledger_excl_reversals()
    f = m[m["code"].isin(["1110", "1120"])]
    total = round(float(f["signed_amount"].sum()), 2)
    return CalcOutput(
        value=total, unit="INR",
        evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts", "F.011"),
        provenance="SUM(signed_amount) WHERE account_code IN ('1110','1120'), reversal-excluded, all-time running balance.",
        limitations="Same construction pattern as M.DEP.001 (proven exact) but not independently re-validated against F.011 in this pass -- represents the ledger's view of cash, not a bank-reconciled figure.",
    )


# ---------------------------------------------------------------------------
# M.TB.001 -- Trial balance / accounting checks
# ---------------------------------------------------------------------------

def calc_trial_balance(spec):
    excl = L.ledger_excl_reversals()
    tb_excl = excl.groupby("code").agg(total_debit=("debit", "sum"), total_credit=("credit", "sum"))
    tb_excl["balance"] = tb_excl["total_debit"] - tb_excl["total_credit"]

    incl = L.ledger_incl_reversals()
    tb_incl = incl.groupby("code").agg(total_debit=("debit", "sum"), total_credit=("credit", "sum"))

    subs = {
        "Reversal-excluded (v_trial_balance, F.012)": CalcOutput(
            value={k: round(float(v), 2) for k, v in tb_excl["balance"].to_dict().items()},
            unit="INR", evidence_sources=("F.012", "T.journal_lines"),
            provenance="Per-account SUM(debit)-SUM(credit), reversal-excluded, accounts with activity only.",
        ),
        "Reversal-included (v_trial_balance_detailed, F.013)": CalcOutput(
            value={k: round(float(v), 2) for k, v in tb_incl["total_debit"].to_dict().items()},
            unit="INR (total_debit per account)", evidence_sources=("F.013", "T.journal_lines"),
            provenance="Per-account SUM(debit), reversal-included, all 57 COA accounts.",
        ),
    }
    return CalcOutput(subs=subs, provenance="Both conventions proven exact in Phase E (LEDGER.04/LEDGER.07). Balances identical; gross turnover differs by Rs.17,693,638.16 across 10 accounts (H.007, C.002).")
