"""
validate_expenses.py -- ledger-derived expense reconstruction, category buckets, and the
proven P&L bucket gap / electricity account 5150 mechanism (DQ.015 / conflicts.md C.012/C.013).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from common import load_table, load_view, money, compare, record_validation, write_monthly

print("=== validate_expenses.py ===")

jl = load_table("journal_lines")
coa = load_table("coa_accounts")
coa["code"] = coa["code"].astype(str)
m = jl.merge(coa[["id", "code", "account_type", "normal_balance"]].rename(columns={"id": "account_id"}),
             on="account_id", how="left")
m["debit"] = money(m["debit"]).fillna(0)
m["credit"] = money(m["credit"]).fillna(0)

reversed_ids = set(jl.loc[jl["is_reversal_of"].notna(), "is_reversal_of"].dropna())
m = m[m["is_reversal_of"].isna() & ~m["journal_entry_id"].isin(reversed_ids)].copy()
m["signed_amount"] = m.apply(
    lambda r: (r["debit"] - r["credit"]) if r["normal_balance"] == "DEBIT" else (r["credit"] - r["debit"]),
    axis=1)
exp = m[m["account_type"] == "EXPENSE"].copy()
exp["month"] = pd.to_datetime(exp["entry_date"]).dt.to_period("M").dt.to_timestamp()

rows = []

# --- total expenses vs v_pnl ---
total_expenses = exp["signed_amount"].sum()
vpnl = load_view("v_pnl")
ref_total = money(vpnl["expenses"]).sum()
rows.append(compare("EXP.01", "Total expenses (all-time, ledger-derived, all 5xxx accounts)",
                     total_expenses, ref_total, "F.001 v_pnl (sum of monthly expenses)"))

# --- 9-bucket category reconstruction, matching v_pnl_by_category's LIKE patterns exactly ---
BUCKET_PATTERNS = [
    ("owner_rent", "510"), ("maintenance", "52"), ("housekeeping", "53"),
    ("utilities", "54"), ("property_ops", "55"), ("administrative", "56"),
    ("salaries", "57"), ("marketing", "58"), ("other_expenses", "59"),
]


def bucket_of(code):
    if not isinstance(code, str):
        return None
    for name, prefix in BUCKET_PATTERNS:
        if code.startswith(prefix):
            return name
    return None


exp["bucket"] = exp["code"].apply(bucket_of)
exp["is_electricity"] = exp["code"].astype(str).str.startswith("515")

sum_of_buckets = exp.loc[exp["bucket"].notna(), "signed_amount"].sum()
electricity_total = exp.loc[exp["is_electricity"], "signed_amount"].sum()
unbucketed = total_expenses - sum_of_buckets

print(f"  total_expenses={total_expenses:.2f}  sum_of_buckets={sum_of_buckets:.2f}  "
      f"unbucketed={unbucketed:.2f}  electricity(515%)={electricity_total:.2f}")

vpbc = load_view("v_pnl_by_category")
ref_sum_of_buckets = sum(money(vpbc[b]).sum() for b, _ in BUCKET_PATTERNS)
ref_electricity = money(vpbc["electricity"]).sum()
ref_total_expenses = money(vpbc["total_expenses"]).sum()

rows.append(compare("EXP.02", "sum_of_buckets (9 named categories, ledger-derived)",
                     round(sum_of_buckets, 2), round(ref_sum_of_buckets, 2), "F.002 v_pnl_by_category"))
rows.append(compare("EXP.03", "electricity bucket total (account 5150, '515%' pattern)",
                     round(electricity_total, 2), round(ref_electricity, 2), "F.002 v_pnl_by_category"))
rows.append(compare("EXP.04", "P&L bucket gap: unbucketed == electricity (proven identity)",
                     round(unbucketed, 2), round(electricity_total, 2),
                     "Internal identity, cross-checked against H.017",
                     explanation_ok="Confirms DQ.015/C.012: unbucketed expenses equal the electricity "
                                    "column exactly -- account 5150 is invisible to all 9 named buckets."))

# cross-check against H.017's own reported totals
h017 = load_table("H.017") if False else None
from common import load as _load
h017 = _load("H.017")
h017_total_te = money(h017["total_expenses"]).sum()
h017_unbucketed = money(h017["unbucketed"]).sum()
rows.append(compare("EXP.05", "Total expenses, 57-month sum, vs H.017", round(total_expenses, 2),
                     round(h017_total_te, 2), "H.017 pnl_bucket_gap"))
rows.append(compare("EXP.06", "Unbucketed total, 57-month sum, vs H.017", round(unbucketed, 2),
                     round(h017_unbucketed, 2), "H.017 pnl_bucket_gap"))

# --- monthly expense series vs v_pnl ---
recon_monthly = exp.groupby(["property_id", "month"], as_index=False, dropna=False)[
    "signed_amount"].sum().rename(columns={"signed_amount": "expenses_reconstructed"})
vpnl["month"] = pd.to_datetime(vpnl["month"])
monthly = recon_monthly.merge(vpnl[["property_id", "month", "expenses"]],
                               on=["property_id", "month"], how="outer").sort_values("month")
monthly["expenses"] = money(monthly["expenses"]).fillna(0)
monthly["expenses_reconstructed"] = monthly["expenses_reconstructed"].fillna(0)
monthly["abs_diff"] = (monthly["expenses_reconstructed"] - monthly["expenses"]).abs()
n_mismatch = (monthly["abs_diff"] > 0.5).sum()
rows.append(compare("EXP.07", "Expenses by month -- value mismatches", n_mismatch, 0,
                     "F.001 v_pnl", tolerance_pct=0,
                     explanation_ok="All overlapping (property,month) rows match exactly; row-count "
                                    "gap (if any) is the same income/expense-only-month effect as REV.02."))
write_monthly("expenses_by_month.csv", monthly.rename(columns={"expenses": "expenses_v_pnl_reference"}))
print(f"  monthly expenses: {len(monthly)} rows, {n_mismatch} value-mismatched >Rs.0.50")

record_validation(rows, append=True)
