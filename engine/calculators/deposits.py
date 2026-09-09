"""
deposits.py -- M.DEP.001/002/003, M.RISK.003/004. Ported from
scripts/validation/validate_deposits.py (DEP.01-DEP.07, all confirmed in Phase E).
"""
from engine.evidence_loader import load_table, load, money
from engine.calculators.base import CalcOutput
from engine.calculators import ledger as L


def calc_deposit_held(spec):
    m = L.ledger_excl_reversals()
    f = m[(m["code"] == "2100") & (m["party_kind"] == "tenant")]
    total = round(float((f["credit"] - f["debit"]).sum()), 2)
    return CalcOutput(
        value=total, unit="INR",
        evidence_sources=("F.010", "T.journal_lines", "T.journal_entries", "T.coa_accounts"),
        provenance="SUM(credit-debit) WHERE account_code='2100' AND party_kind='tenant', reversal-excluded.",
    )


def calc_deposit_settlements(spec):
    ds = load_table("deposit_settlements")
    ds = ds.copy()
    ds["is_deleted_b"] = ds["is_deleted"].astype(str).str.lower().eq("true")
    live = ds[~ds["is_deleted_b"]]
    refund_total = round(float(money(live["refund_amount"]).sum()), 2)
    deduction_total = round(float(money(live["total_deductions"]).sum()), 2)
    return CalcOutput(
        value={"refund_amount_total": refund_total, "total_deductions": deduction_total},
        unit="INR", evidence_sources=("T.deposit_settlements", "H.001"),
        provenance="SUM(refund_amount)/SUM(total_deductions) WHERE NOT is_deleted. Ledger-posting gate: status IN ('completed','approved').",
        limitations="Rs.583,495.34 source-vs-ledger gap (10.3%), suspected 2x double-count mechanism in 23 of 43 drifting rows (DQ.008/C.016) -- not proven from an exported query definition.",
    )


def calc_deposit_refunds(spec):
    r = calc_deposit_settlements(spec)
    return CalcOutput(
        value=r.value["refund_amount_total"], unit="INR",
        evidence_sources=r.evidence_sources, provenance="SUM(refund_amount) WHERE NOT is_deleted (identical to M.DEP.002's refund component).",
        limitations=r.limitations,
    )


def calc_phantom_deposits(spec):
    ta = load_table("tenant_allotments").copy()
    ds = load_table("deposit_settlements").copy()
    ta["deposit_paid_n"] = money(ta["deposit_paid"]).fillna(0)
    ds["is_deleted_b"] = ds["is_deleted"].astype(str).str.lower().eq("true")
    ds_live_allot = set(ds[~ds["is_deleted_b"]]["allotment_id"].dropna())
    phantom = ta[(ta["deposit_paid_n"] > 0) &
                 (ta["staying_status"].isin(["Exited", "Cancelled"])) &
                 (~ta["id"].isin(ds_live_allot))]
    amount = round(float(phantom["deposit_paid_n"].sum()), 2)
    return CalcOutput(
        value={"allotment_count": int(len(phantom)), "amount_at_risk": amount},
        unit="mixed", evidence_sources=("H.045", "T.tenant_allotments", "T.deposit_settlements"),
        provenance="tenant_allotments WHERE deposit_paid>0 AND staying_status IN ('Exited','Cancelled') AND NOT EXISTS(matching live deposit_settlements row).",
        limitations="Real, unresolved financial exposure (DQ.011) -- an operational gap, not a reporting artifact.",
    )


def calc_deposit_anomalies(spec):
    try:
        anomalies = load("H.046")
    except KeyError:
        from engine.calculators.base import NotDeterminableError
        raise NotDeterminableError("H.046 (v_deposit_ledger_anomalies) not available.")
    by_type = anomalies["anomaly"].value_counts().to_dict()
    return CalcOutput(
        value={"total_rows": int(len(anomalies)), "by_type": by_type},
        unit="count", evidence_sources=("H.046",),
        provenance="v_deposit_ledger_anomalies: 3 possible anomaly types (premature_settlement, duplicate_open_settlement, transfer_double_count).",
        limitations=(
            "validate_deposit_settlement is a write-time-only constraint (DQ.012) -- does not "
            "re-validate existing rows if status changes retroactively. NOTE (found live in "
            "this pass, a small correction to data_quality_report.md's framing): all 22 rows "
            "currently exported are 'transfer_double_count' -- 0 rows of 'premature_settlement' "
            "or 'duplicate_open_settlement' are present in this specific export, though all "
            "3 types are structurally possible per the view's own SQL."
        ),
    )


def calc_deposit_risk(spec):
    phantom = calc_phantom_deposits(spec)
    anomalies = calc_deposit_anomalies(spec)
    return CalcOutput(
        subs={"Phantom deposits (M.RISK.004)": phantom, "Deposit ledger anomalies": anomalies},
        provenance="Union of phantom-deposit exposure and settlement-anomaly detection (M.RISK.003).",
    )
