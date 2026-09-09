"""
validate_receivables.py -- reconstructs and cross-validates ALL FOUR competing tenant/allotment
balance definitions (conflicts.md C.001/C.003/C.005, DQ.002/DQ.019). None is collapsed into
the others -- all four are computed independently and compared pairwise.

  Def 1: tenant_allotments.balance_due          (application-stored column)
  Def 2: tenant_transactions                    (frozen legacy ledger, DEBIT-CREDIT on CHARGE/PAYMENT)
  Def 3: raw journal_lines on account 1200       (reversals INCLUDED  -- v_tenant_current_dues basis)
  Def 4: v_account_balances on account 1200      (reversals EXCLUDED -- v_outstanding_receivables basis)
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from common import load_table, load_view, money, compare, record_validation

print("=== validate_receivables.py ===")

ta = load_table("tenant_allotments")
tt = load_table("tenant_transactions")
jl = load_table("journal_lines")
coa = load_table("coa_accounts")
coa["code"] = coa["code"].astype(str)

rows = []

# --- Def 1: application-stored balance_due ---
def1_total = money(ta["balance_due"]).sum()

# --- Def 2: tenant_transactions, CHARGE/PAYMENT only ---
# Two sub-variants coexist because neither H.052's nor H.044's generating SQL is among the 54
# exported view definitions -- their exact per-allotment floor rule is not directly readable:
#   2a: unclipped SUM(DEBIT)-SUM(CREDIT) per allotment (can go negative, nets across allotments)
#   2b: same, but GREATEST(sum, 0) per allotment (matches v_diag_allotment_balance_drift's
#       explicit GREATEST(agg.computed_balance, 0) formula, business_logic.md 4.5)
tt_cp = tt[tt["ledger_type"].isin(["CHARGE", "PAYMENT"])].copy()
tt_cp["signed"] = tt_cp.apply(
    lambda r: money(pd.Series([r["amount"]])).iloc[0] if r["direction"] == "DEBIT"
    else -money(pd.Series([r["amount"]])).iloc[0], axis=1)
def2_by_allot_unclipped = tt_cp.groupby("allotment_id")["signed"].sum()
def2_by_allot = def2_by_allot_unclipped.clip(lower=0)  # 2b, GREATEST(...,0) -- used below
def2_total = def2_by_allot.sum()
def2_total_unclipped = def2_by_allot_unclipped.sum()

# --- Def 3: raw journal_lines on 1200, reversals INCLUDED ---
m = jl.merge(coa[["id", "code"]].rename(columns={"id": "account_id"}), on="account_id", how="left")
m["debit"] = money(m["debit"]).fillna(0)
m["credit"] = money(m["credit"]).fillna(0)
ar_lines = m[(m["code"] == "1200") & (m["party_kind"] == "tenant")]
def3_by_allot = (ar_lines["debit"] - ar_lines["credit"]).groupby(ar_lines["allotment_id"]).sum()
def3_total = def3_by_allot.sum()

# --- Def 4: v_account_balances convention, reversals EXCLUDED ---
reversed_ids = set(jl.loc[jl["is_reversal_of"].notna(), "is_reversal_of"].dropna())
ar_excl = ar_lines[ar_lines["is_reversal_of"].isna() & ~ar_lines["journal_entry_id"].isin(reversed_ids)]
def4_by_allot = (ar_excl["debit"] - ar_excl["credit"]).groupby(ar_excl["allotment_id"]).sum()
def4_total = def4_by_allot.sum()

print(f"  Def1 (app balance_due)      total = {def1_total:,.2f}  over {(money(ta['balance_due'])>0).sum()} allotments >0")
print(f"  Def2 (tenant_transactions)  total = {def2_total:,.2f}  over {(def2_by_allot>0).sum()} allotments >0")
print(f"  Def3 (ledger, incl revers.) total = {def3_total:,.2f}  over {(def3_by_allot>0).sum()} allotments >0")
print(f"  Def4 (ledger, excl revers.) total = {def4_total:,.2f}  over {(def4_by_allot>0).sum()} allotments >0")

# --- validate Def3/Def4 against the exported views (F.006/F.007) ---
vout = load_view("v_outstanding_receivables")
vcur = load_view("v_tenant_current_dues")
ref_def4 = money(vout["outstanding"]).sum()
ref_def3 = money(vcur["ar_balance"]).sum()
rows.append(compare("AR.01", "Def4: ledger AR (reversals excluded) total", round(def4_total, 2),
                     round(ref_def4, 2), "F.006 v_outstanding_receivables"))
rows.append(compare("AR.02", "Def3: ledger AR (reversals included) total", round(def3_total, 2),
                     round(ref_def3, 2), "F.007 v_tenant_current_dues"))
rows.append(compare("AR.03", "Def3 == Def4 (reversal convention makes no difference to AR total)",
                     round(def3_total, 2), round(def4_total, 2), "Internal identity (C.002 proof)",
                     explanation_ok="Proves reversal-excluded and reversal-included conventions "
                                    "yield an IDENTICAL AR total -- reversals net to zero exactly."))

# --- the 4-way disagreement itself, never collapsed ---
merged = pd.DataFrame({"def1_app": money(ta.set_index("id")["balance_due"])})
merged["def2_tenant_transactions"] = def2_by_allot.reindex(merged.index).fillna(0)
merged["def3_ledger_incl"] = def3_by_allot.reindex(merged.index).fillna(0)
merged["def4_ledger_excl"] = def4_by_allot.reindex(merged.index).fillna(0)
n_disagree_1v2 = ((merged["def1_app"].fillna(0) - merged["def2_tenant_transactions"]).abs() > 1).sum()
rows.append(compare("AR.04a", "Def2 unclipped total (CHARGE/PAYMENT, SUM per allotment, can net negative)",
                     round(def2_total_unclipped, 2), 9968023.32, "conflicts.md C.003/C.005 (H.052 export)",
                     explanation_ok="EXACT match -- proves H.052's 'def2_tenant_transactions' column is "
                                    "the unclipped per-allotment SUM(DEBIT)-SUM(CREDIT) over "
                                    "CHARGE/PAYMENT rows only, with negative per-allotment balances "
                                    "allowed to net against positive ones in the total."))
rows.append({
    "metric_id": "AR.04b",
    "metric_name": "Def2 floored total (GREATEST(sum,0) per allotment, H.044/v_diag_allotment_balance_drift convention)",
    "reconstructed_value": round(def2_total, 2), "reference_value": "",
    "absolute_difference": round(def2_total - def2_total_unclipped, 2), "percentage_difference": "",
    "validation_status": "NOT_DETERMINABLE",
    "reference_source": "No exported aggregate uses this exact floored-total form to compare "
                         "against (H.044 exports per-allotment drift rows, not a pre-summed total).",
    "explanation": (
        f"Two legitimate sub-variants of 'Def2 = tenant_transactions balance' exist and are BOTH "
        f"recorded rather than collapsed: unclipped (AR.04a, Rs.{def2_total_unclipped:,.2f}, "
        f"matches H.052 exactly) vs GREATEST(...,0)-floored per allotment "
        f"(this row, Rs.{def2_total:,.2f}), which matches the explicit floor formula documented "
        f"in v_diag_allotment_balance_drift (business_logic.md 4.5). The Rs.{def2_total-def2_total_unclipped:,.2f} "
        f"gap between them is exactly the sum of allotments with a negative net "
        f"CHARGE/PAYMENT balance that the floored variant clips to zero. Neither is proven more "
        f"'correct' than the other from the exported evidence -- both are preserved."
    ),
})
rows.append({
    "metric_id": "AR.04c", "metric_name": "Allotments where Def1 (app) and Def2-floored disagree by >Rs.1",
    "reconstructed_value": int(n_disagree_1v2), "reference_value": 873,
    "absolute_difference": abs(int(n_disagree_1v2) - 873), "percentage_difference": "",
    "validation_status": "DIFFERS",
    "reference_source": "conflicts.md C.005 (H.052 export, Def1 vs Def2-UNCLIPPED comparison)",
    "explanation": (
        f"This script compares Def1 against Def2-FLOORED (n={n_disagree_1v2}); conflicts.md's "
        f"873 figure compared Def1 against Def2-UNCLIPPED (H.052's own basis, confirmed exact "
        f"in AR.04a). The two disagreement counts differ because flooring changes which "
        f"allotments read as zero. Both counts are real and neither supersedes the other -- "
        f"they answer 'how does Def1 disagree with Def2' under two different Def2 sub-rules."
    ),
})
print(f"  Def1 vs Def2 disagree (>Rs.1): {n_disagree_1v2} of {len(merged)} allotments")
print(f"  ALL FOUR DEFINITIONS -- totals: app={def1_total:,.0f}  tenant_tx={def2_total:,.0f}  "
      f"ledger_incl={def3_total:,.0f}  ledger_excl={def4_total:,.0f}")
print("  SEMANTIC STATUS: Conflicting definitions exist. No single figure is authoritative.")
print("  AI BEHAVIOUR: SHOW_BOTH / BLOCK a single-number answer until an owner decision is made.")

record_validation(rows, append=True)
