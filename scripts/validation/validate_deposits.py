"""
validate_deposits.py -- deposit-held balance, deposit settlement source-vs-ledger drift
(the 2x pattern, DQ.008), and phantom-deposit exposure (DQ.011).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from common import load_table, load_view, load, money, compare, record_validation

print("=== validate_deposits.py ===")

jl = load_table("journal_lines")
coa = load_table("coa_accounts")
coa["code"] = coa["code"].astype(str)
ta = load_table("tenant_allotments")
ds = load_table("deposit_settlements")

rows = []

# --- deposit_held (account 2100), reversal-excluded, vs v_advance_balances (F.010) ---
m = jl.merge(coa[["id", "code"]].rename(columns={"id": "account_id"}), on="account_id", how="left")
m["debit"] = money(m["debit"]).fillna(0)
m["credit"] = money(m["credit"]).fillna(0)
reversed_ids = set(jl.loc[jl["is_reversal_of"].notna(), "is_reversal_of"].dropna())
excl = m[m["is_reversal_of"].isna() & ~m["journal_entry_id"].isin(reversed_ids)]
dep_lines = excl[(excl["code"] == "2100") & (excl["party_kind"] == "tenant")]
deposit_held_total = (dep_lines["credit"] - dep_lines["debit"]).sum()

vadv = load_view("v_advance_balances")
ref_deposit_held = money(vadv["deposit_held"]).sum()
rows.append(compare("DEP.01", "Deposit held total (account 2100, reversal-excluded)",
                     round(deposit_held_total, 2), round(ref_deposit_held, 2),
                     "F.010 v_advance_balances"))

# --- booking_advance (account 2400) ---
adv_lines = excl[(excl["code"] == "2400") & (excl["party_kind"] == "tenant")]
booking_adv_total = (adv_lines["credit"] - adv_lines["debit"]).sum()
ref_booking_adv = money(vadv["booking_advance"]).sum()
rows.append(compare("DEP.02", "Booking advance total (account 2400, reversal-excluded)",
                     round(booking_adv_total, 2), round(ref_booking_adv, 2), "F.010 v_advance_balances"))

# --- deposit_settlements: source total vs ledger, reproducing the ~2x mechanism (DQ.008) ---
ds["is_deleted_b"] = ds["is_deleted"].astype(str).str.lower().eq("true")
ds_live = ds[~ds["is_deleted_b"]]
source_refund_total = money(ds_live["refund_amount"]).sum()

set_lines = m[(m["source_table"] == "deposit_settlements") & (m["code"].isin(["1110", "1120"]))]
ledger_net = set_lines.apply(
    lambda r: r["credit"] if pd.isna(r.get("is_reversal_of")) else -r["credit"], axis=1).sum()

h001 = load("H.001")
h001_ds = h001[h001["source_table"] == "deposit_settlements"].iloc[0]
rows.append(compare("DEP.03", "deposit_settlements source total (refund_amount, live)",
                     round(source_refund_total, 2), round(money(pd.Series([h001_ds["legacy_amount"]])).iloc[0], 2),
                     "H.001 v_je_amount_reconciliation"))
rows.append(compare("DEP.04", "deposit_settlements ledger net (forward - reversal credit, 11xx accounts)",
                     round(ledger_net, 2), round(money(pd.Series([h001_ds["je_net_amount"]])).iloc[0], 2),
                     "H.001 v_je_amount_reconciliation",
                     explanation_ok="Reproduces H.001's INVESTIGATE-flagged Rs.583,495.34 gap exactly "
                                    "-- see DQ.008/C.016 for the suspected 2x-double-count mechanism."))

# --- Reproduce the exact 2x pattern on entry_count=3 settlements (DQ.008/C.016) ---
je = load_table("journal_entries").rename(columns={"id": "journal_entry_id"})
ds_entries = je[je["source_table"] == "deposit_settlements"]
entry_counts = ds_entries.groupby("source_id").size()
three_entry_ids = entry_counts[entry_counts == 3].index
n_three_entry = len(three_entry_ids)
rows.append({
    "metric_id": "DEP.05", "metric_name": "deposit_settlements with exactly 3 journal_entries (1 edit-repost cycle)",
    "reconstructed_value": int(n_three_entry), "reference_value": 37,
    "absolute_difference": abs(int(n_three_entry) - 37), "percentage_difference": "",
    "validation_status": "MATCH" if abs(int(n_three_entry) - 37) <= 1 else "DIFFERS",
    "reference_source": "H.050 (37 of 43 drifting rows have entry_count=3, per conflicts.md C.016)",
    "explanation": "Confirms the entry_count=3 cluster size that underlies DQ.008's suspected "
                   "2x-double-count diagnostic-query mechanism.",
})
print(f"  deposit_held={deposit_held_total:,.2f}  booking_advance={booking_adv_total:,.2f}")
print(f"  settlements with entry_count==3: {n_three_entry}")

# --- phantom deposits (v_diag_deposit_phantom logic, DQ.011) ---
ta["deposit_paid_n"] = money(ta["deposit_paid"]).fillna(0)
ds_allot_ids = set(ds_live["allotment_id"].dropna())
phantom = ta[(ta["deposit_paid_n"] > 0) &
             (ta["staying_status"].isin(["Exited", "Cancelled"])) &
             (~ta["id"].isin(ds_allot_ids))]
h045 = load("H.045")
rows.append(compare("DEP.06", "Phantom deposits: deposit held, no live tenant, no settlement row",
                     len(phantom), len(h045), "H.045 v_diag_deposit_phantom",
                     explanation_ok="Reproduces DQ.011's 32-allotment phantom-deposit exposure exactly."))
phantom_amount = phantom["deposit_paid_n"].sum()
print(f"  phantom deposits: {len(phantom)} allotments, Rs.{phantom_amount:,.2f} at risk "
      f"(H.045 does not export this sum -- computed here from tenant_allotments.deposit_paid)")
rows.append({
    "metric_id": "DEP.07", "metric_name": "Phantom deposit amount at risk (sum of deposit_paid)",
    "reconstructed_value": round(phantom_amount, 2), "reference_value": "",
    "absolute_difference": "", "percentage_difference": "",
    "validation_status": "NOT_DETERMINABLE",
    "reference_source": "H.045 does not export a summed amount -- this is a new figure computed "
                         "directly from tenant_allotments.deposit_paid for the 32 phantom rows.",
    "explanation": "No reference view sums this amount; recorded as a first computation, not a "
                   "validated reconciliation.",
})

record_validation(rows, append=True)
