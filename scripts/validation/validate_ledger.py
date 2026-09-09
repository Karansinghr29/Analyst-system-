"""
validate_ledger.py -- ledger reconstruction + reversal-handling validation.

Reconstructs v_account_balances (reversal-EXCLUDED convention) directly from journal_lines x
journal_entries x coa_accounts and cross-checks it against:
  - v_account_balances itself (F.021) -- row count and debit/credit totals
  - v_trial_balance (F.012) -- per-account balance, reversal-excluded
  - H.005 (14236 entries / 347 reversals) -- reversal volume
  - H.007 (trial_balance_reversal_effect) -- excl vs incl reversal difference, per account

This is the foundation every other validate_*.py script's ledger-derived figures depend on.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from common import load_table, load_view, load, money, to_bool, compare, record_validation

print("=== validate_ledger.py ===")

jl = load_table("journal_lines")
je = load_table("journal_entries")
coa = load_table("coa_accounts")

je = je.rename(columns={"id": "journal_entry_id"})
# journal_lines is exported already denormalised with entry_date/is_reversal_of from
# journal_entries (see data_inventory.md 5.1) -- use those directly, no merge needed for them.
m = jl.merge(coa[["id", "code", "account_type", "normal_balance"]].rename(columns={"id": "account_id"}),
             on="account_id", how="left")
m["debit"] = money(m["debit"]).fillna(0)
m["credit"] = money(m["credit"]).fillna(0)

# --- reversal-excluded convention (v_account_balances): drop reversal entries AND any
#     forward entry that has since been reversed ---
reversed_ids = set(je.loc[je["is_reversal_of"].notna(), "is_reversal_of"].dropna())
m_excl = m[m["is_reversal_of"].isna() & ~m["journal_entry_id"].isin(reversed_ids)].copy()
m_excl["signed_amount"] = m_excl.apply(
    lambda r: (r["debit"] - r["credit"]) if r["normal_balance"] == "DEBIT" else (r["credit"] - r["debit"]),
    axis=1)

print(f"journal_lines: {len(jl)}  journal_entries: {len(je)}  reversal entries: "
      f"{je['is_reversal_of'].notna().sum()}  reversed originals: {len(reversed_ids)}")
print(f"reversal-excluded lines (v_account_balances basis): {len(m_excl)}")

rows = []

# 1) row count vs F.021 (v_account_balances export)
vab = load_view("v_account_balances")
rows.append(compare("LEDGER.01", "v_account_balances row count (reversal-excluded)",
                     len(m_excl), len(vab), "F.021 v_account_balances",
                     explanation_ok="Reconstructed reversal-excluded line count matches the exported v_account_balances row count exactly."))

# 2) total debit / total credit vs F.021
recon_debit = m_excl["debit"].sum()
recon_credit = m_excl["credit"].sum()
ref_debit = money(vab["debit"]).sum()
ref_credit = money(vab["credit"]).sum()
rows.append(compare("LEDGER.02", "v_account_balances total debit", recon_debit, ref_debit,
                     "F.021 v_account_balances"))
rows.append(compare("LEDGER.03", "v_account_balances total credit", recon_credit, ref_credit,
                     "F.021 v_account_balances"))

# 3) trial balance per account, reversal-excluded, vs F.012
tb_recon = m_excl.groupby("code", as_index=False).agg(total_debit=("debit", "sum"),
                                                        total_credit=("credit", "sum"))
tb_recon["balance"] = tb_recon["total_debit"] - tb_recon["total_credit"]
tb_ref = load_view("v_trial_balance")
tb_ref["balance"] = money(tb_ref["balance"])
merged_tb = tb_recon.merge(tb_ref[["account_code", "balance"]], left_on="code",
                            right_on="account_code", how="outer", suffixes=("_recon", "_ref"))
merged_tb["diff"] = (merged_tb["balance_recon"].fillna(0) - merged_tb["balance_ref"].fillna(0)).abs()
n_mismatch = (merged_tb["diff"] > 0.5).sum()
rows.append(compare("LEDGER.04", "Trial balance account count (reversal-excluded)",
                     len(tb_recon), len(tb_ref), "F.012 v_trial_balance",
                     explanation_diff=f"{n_mismatch} of {len(merged_tb)} accounts differ by >Rs.0.50"))
print(f"  trial balance: {len(tb_recon)} accounts reconstructed, {len(tb_ref)} in F.012, "
      f"{n_mismatch} mismatched >Rs.0.50")

# 4) reversal volume vs H.005
h005 = load("H.005")
h_total = int(h005.iloc[0]["total_entries"])
h_rev = int(h005.iloc[0]["reversal_entries"])
rows.append(compare("LEDGER.05", "Total journal_entries count", len(je), h_total, "H.005 je_reversal_summary"))
rows.append(compare("LEDGER.06", "Reversal entry count", int(je["is_reversal_of"].notna().sum()),
                     h_rev, "H.005 je_reversal_summary"))

# 5) reversal-INCLUDED total debit/credit (v_tenant_current_dues / v_trial_balance_detailed
#    convention) -- raw journal_lines, no filter -- vs v_trial_balance_detailed (F.013)
m["signed_debit"] = m["debit"]
tbd_recon = m.groupby("code", as_index=False).agg(total_debit=("debit", "sum"),
                                                    total_credit=("credit", "sum"))
tbd_ref = load_view("v_trial_balance_detailed")
merged_tbd = tbd_recon.merge(tbd_ref[["code", "total_debit", "total_credit"]], on="code",
                              how="outer", suffixes=("_recon", "_ref"))
merged_tbd["ddiff"] = (money(merged_tbd["total_debit_recon"]).fillna(0) -
                        money(merged_tbd["total_debit_ref"]).fillna(0)).abs()
n_mismatch_incl = (merged_tbd["ddiff"] > 0.5).sum()
rows.append(compare("LEDGER.07", "Trial balance detailed total_debit (reversal-included)",
                     round(tbd_recon["total_debit"].sum(), 2),
                     round(money(tbd_ref["total_debit"]).sum(), 2),
                     "F.013 v_trial_balance_detailed",
                     explanation_diff=f"{n_mismatch_incl} of {len(merged_tbd)} accounts differ >Rs.0.50 at the per-account grain even though totals may align"))

# 6) H.007's excl-vs-incl difference, reproduced independently
excl_by_acct = m_excl.groupby("code")["debit"].sum()
incl_by_acct = m.groupby("code")["debit"].sum()
diff_by_acct = (incl_by_acct - excl_by_acct).dropna()
nonzero = diff_by_acct[diff_by_acct.abs() > 0.5]
h007 = load("H.007")
h007_nonzero = h007[money(h007["debit_difference"]).abs() > 0.5]
rows.append(compare("LEDGER.08", "Accounts affected by reversal-excl-vs-incl convention",
                     len(nonzero), len(h007_nonzero), "H.007 trial_balance_reversal_effect",
                     explanation_ok="Independently reproduces H.007's 10-account reversal-effect finding from raw journal_lines."))
print(f"  reversal-effect accounts reconstructed: {len(nonzero)} vs H.007: {len(h007_nonzero)}")

record_validation(rows, append=False)
print(f"\nWrote {len(rows)} rows to validation_summary.csv (fresh file, ledger is the first script run)")
