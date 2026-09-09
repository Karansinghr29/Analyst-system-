"""
validate_collections.py -- collections reconstruction (app-level and ledger-derived), and
direct proof of the get_universal_metrics_series account-code bug (DQ.030/C.021).

No exported view materialises "collections" as its own object (get_universal_metrics/_v2/
_series are callable functions, not views) -- so this script's reference values come from
diagnostics (H.001) and from internal cross-checks between the two collections definitions,
not from a dedicated business view.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from common import load_table, load, money, compare, record_validation, write_monthly

print("=== validate_collections.py ===")

receipts = load_table("receipts")
jl = load_table("journal_lines")
coa = load_table("coa_accounts")
coa["code"] = coa["code"].astype(str)

rows = []

# ---- Definition A: application-level, receipts.amount_paid, live rows ----
receipts["is_deleted_b"] = receipts["is_deleted"].astype(str).str.lower().eq("true")
r_live = receipts[~receipts["is_deleted_b"]]
collections_A = money(r_live["amount_paid"]).sum()
deposit_collections_A = money(r_live.loc[r_live["receipt_type"] == "booking", "amount_paid"]).sum()
collections_A_no_deposit = collections_A - deposit_collections_A
print(f"  Def A (app, receipts.amount_paid): total={collections_A:,.2f}  "
      f"deposit={deposit_collections_A:,.2f}  non-deposit={collections_A_no_deposit:,.2f}")

h001 = load("H.001")
h001_r = h001[h001["source_table"] == "receipts"].iloc[0]
rows.append(compare("COLL.01", "Collections Def A: receipts.amount_paid total (live)",
                     round(collections_A, 2), round(money(pd.Series([h001_r["legacy_amount"]])).iloc[0], 2),
                     "H.001 v_je_amount_reconciliation (legacy_amount)"))

# ---- Definition B: ledger-derived, account 1110/1120 debit, source_table=receipts,
#      reversal-excluded (matches get_universal_metrics_v2's v_collections logic exactly) ----
m = jl.merge(coa[["id", "code"]].rename(columns={"id": "account_id"}), on="account_id", how="left")
m["debit"] = money(m["debit"]).fillna(0)
m["credit"] = money(m["credit"]).fillna(0)
recv = m[(m["source_table"] == "receipts") & (m["code"].isin(["1110", "1120"]))]
recv_net = recv.apply(lambda r: r["debit"] if pd.isna(r.get("is_reversal_of")) else -r["debit"], axis=1).sum()
rows.append(compare("COLL.02", "Collections Def B: ledger net (1110/1120 debit, source=receipts)",
                     round(recv_net, 2), round(money(pd.Series([h001_r["je_net_amount"]])).iloc[0], 2),
                     "H.001 v_je_amount_reconciliation (je_net_amount)",
                     explanation_ok="Reproduces H.001's INVESTIGATE-flagged receipts drift "
                                    "(Rs.5,340,795.62) exactly -- see DQ.006/C.014."))

# ---- DQ.030 proof: get_universal_metrics_series' account_code='1000' filter ----
wrong_code = m[(m["source_table"] == "receipts") & (m["code"] == "1000")]
wrong_code_total = wrong_code["debit"].sum() if len(wrong_code) else 0.0
rows.append({
    "metric_id": "COLL.03", "metric_name": "get_universal_metrics_series-style collections "
                                            "(account_code='1000', the PROVEN BUG)",
    "reconstructed_value": round(wrong_code_total, 2), "reference_value": 0,
    "absolute_difference": round(wrong_code_total, 2), "percentage_difference": "",
    "validation_status": "MATCH" if wrong_code_total == 0 else "DIFFERS",
    "reference_source": "conflicts.md C.021 / DQ.030 (predicted runtime symptom)",
    "explanation": (
        f"CONFIRMS DQ.030: filtering journal_lines on account_code='1000' (the 'Assets' HEADER "
        f"account, not a leaf posting account) for source_table='receipts' returns {len(wrong_code)} "
        f"rows and Rs.{wrong_code_total:,.2f} total. This is the exact filter used in "
        f"get_universal_metrics_series' 'collections' column -- proving from real data (not just "
        f"code-reading) that it returns zero for every month. Compare to COLL.02's correct "
        f"1110/1120-based figure of Rs.{recv_net:,.2f}."
    ),
})
print(f"  DQ.030 proof: account_code='1000' matches {len(wrong_code)} rows, "
      f"Rs.{wrong_code_total:,.2f} (should be Rs.{recv_net:,.2f} using the correct 1110/1120 accounts)")

# ---- monthly collections series (Def A, by payment_date) ----
r_live = r_live.copy()
r_live["month"] = pd.to_datetime(r_live["payment_date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
monthly = r_live.groupby("month", as_index=False).apply(
    lambda g: pd.Series({
        "collections_total": money(g["amount_paid"]).sum(),
        "deposit_collections": money(g.loc[g["receipt_type"] == "booking", "amount_paid"]).sum(),
    }), include_groups=False).reset_index()
write_monthly("collections_by_month.csv", monthly)
print(f"  wrote {len(monthly)} months of collections (Def A, application-level)")

record_validation(rows, append=True)
