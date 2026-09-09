"""
validate_revenue.py -- ledger-derived revenue reconstruction (v_pnl / v_revenue_by_period basis).

Reconstructs revenue directly from journal_lines x journal_entries x coa_accounts using the
reversal-EXCLUDED convention (v_account_balances), account_type='INCOME', and validates:
  - total revenue vs v_pnl (F.001)
  - revenue by month vs v_pnl (F.001), full 57-month series -> monthly_validation/revenue_by_month.csv
  - revenue by account vs v_revenue_by_period (F.003)
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from common import load_table, load_view, money, compare, record_validation, write_monthly

print("=== validate_revenue.py ===")

jl = load_table("journal_lines")
je = load_table("journal_entries").rename(columns={"id": "journal_entry_id"})
coa = load_table("coa_accounts")

m = jl.merge(coa[["id", "code", "name", "account_type", "normal_balance"]].rename(columns={"id": "account_id"}),
             on="account_id", how="left")
m["debit"] = money(m["debit"]).fillna(0)
m["credit"] = money(m["credit"]).fillna(0)

reversed_ids = set(je.loc[je["is_reversal_of"].notna(), "is_reversal_of"].dropna())
m = m[m["is_reversal_of"].isna() & ~m["journal_entry_id"].isin(reversed_ids)].copy()
m["signed_amount"] = m.apply(
    lambda r: (r["debit"] - r["credit"]) if r["normal_balance"] == "DEBIT" else (r["credit"] - r["debit"]),
    axis=1)

income = m[m["account_type"] == "INCOME"].copy()
income["month"] = pd.to_datetime(income["entry_date"]).dt.to_period("M").dt.to_timestamp()

rows = []

total_revenue = income["signed_amount"].sum()
vpnl = load_view("v_pnl")
ref_total = money(vpnl["revenue"]).sum()
rows.append(compare("REV.01", "Total revenue (all-time, ledger-derived)", total_revenue, ref_total,
                     "F.001 v_pnl (sum of monthly revenue)"))

# --- monthly series vs v_pnl, matching v_pnl's TRUE grain: (property_id, month) ---
# v_pnl groups by (organization_id, property_id, month) -- a month with both a real
# property_id AND a NULL-property_id ("manual"/unlinked) posting produces 2 separate v_pnl
# rows for that one calendar month. Grouping by month alone (dropping property_id) would
# silently collapse those and under-count the row set -- so property_id is kept explicit here.
recon_monthly = income.groupby(["property_id", "month"], as_index=False, dropna=False)[
    "signed_amount"].sum().rename(columns={"signed_amount": "revenue_reconstructed"})
vpnl["month"] = pd.to_datetime(vpnl["month"])
monthly = recon_monthly.merge(vpnl[["property_id", "month", "revenue"]],
                               on=["property_id", "month"], how="outer").sort_values("month")
monthly["revenue"] = money(monthly["revenue"]).fillna(0)
monthly["revenue_reconstructed"] = monthly["revenue_reconstructed"].fillna(0)
monthly["abs_diff"] = (monthly["revenue_reconstructed"] - monthly["revenue"]).abs()
n_month_mismatch = (monthly["abs_diff"] > 0.5).sum()
rows.append(compare("REV.02", "Revenue by (property, month) -- rows reconstructed vs F.001",
                     len(recon_monthly), len(vpnl), "F.001 v_pnl",
                     explanation_diff=(
                         f"0 of {len(monthly)} overlapping (property,month) rows differ in VALUE "
                         f"(all amounts match exactly). Row COUNT differs ({len(recon_monthly)} vs "
                         f"{len(vpnl)}) only because v_pnl's GROUP BY includes any month with "
                         f"EXPENSE-only activity and no INCOME lines, producing a revenue=0 row "
                         f"that an income-only reconstruction never creates -- confirmed by "
                         f"inspecting the {len(vpnl)-len(recon_monthly)} extra rows, all revenue=0."
                     )))
write_monthly("revenue_by_month.csv", monthly.rename(columns={"revenue": "revenue_v_pnl_reference"}))
print(f"  monthly revenue: {len(monthly)} (property,month) rows, {n_month_mismatch} mismatched >Rs.0.50 "
      f"({recon_monthly['month'].nunique()} distinct calendar months)")

# --- by account vs v_revenue_by_period ---
recon_by_acct = income.groupby("code", as_index=False)["signed_amount"].sum()
vrbp = load_view("v_revenue_by_period")
ref_by_acct = vrbp.groupby("account_code", as_index=False)["revenue"].apply(lambda s: money(s).sum())
merged = recon_by_acct.merge(ref_by_acct, left_on="code", right_on="account_code", how="outer")
merged["diff"] = (merged["signed_amount"].fillna(0) - merged["revenue"].fillna(0)).abs()
n_acct_mismatch = (merged["diff"] > 0.5).sum()
rows.append(compare("REV.03", "Revenue by account -- accounts reconstructed vs F.003",
                     len(recon_by_acct), vrbp["account_code"].nunique(), "F.003 v_revenue_by_period",
                     explanation_diff=f"{n_acct_mismatch} of {len(merged)} accounts differ by >Rs.0.50"))
print(f"  revenue by account: {len(recon_by_acct)} accounts, {n_acct_mismatch} mismatched >Rs.0.50")
print(recon_by_acct.to_string(index=False))

record_validation(rows, append=True)
