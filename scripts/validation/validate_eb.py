"""
validate_eb.py -- EB/electricity usage, tenant allocation formula verification, and the proven
billing_month format defect (DQ.028). No EB business view is exported, so validation here is
internal-consistency and cross-table format verification rather than view comparison.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import re
import pandas as pd
from common import load_table, money, compare, record_validation

print("=== validate_eb.py ===")

er = load_table("electricity_readings")
ets = load_table("eb_tenant_shares")
ep = load_table("eb_payments")
inv = load_table("invoices")
exp_ = load_table("expenses")
op = load_table("owner_payments")

rows = []

# ---- EB tenant-allocation formula verification (business_logic.md 12.1) ----
ets["total_apartment_bill_n"] = money(ets["total_apartment_bill"])
ets["total_tenant_days_n"] = money(ets["total_tenant_days"])
ets["per_day_rate_n"] = money(ets["per_day_rate"])
ets["tenant_stay_days_n"] = money(ets["tenant_stay_days"])
ets["tenant_eb_charge_n"] = money(ets["tenant_eb_charge"])

calc_rate = (ets["total_apartment_bill_n"] / ets["total_tenant_days_n"]).round(0)
calc_charge = calc_rate * ets["tenant_stay_days_n"]
rate_match = (calc_rate == ets["per_day_rate_n"])
charge_match = ((calc_charge - ets["tenant_eb_charge_n"]).abs() < 0.5)

rows.append(compare("EB.01", "eb_tenant_shares.per_day_rate == ROUND(bill/tenant_days)",
                     int(rate_match.sum()), len(ets), "Formula verification (business_logic.md 12.1)",
                     tolerance_pct=0,
                     explanation_ok="Confirms the ROUND(total_apartment_bill/total_tenant_days) "
                                    "formula holds for the full 801-row population, not just the "
                                    "5-row sample checked in business_logic.md."))
rows.append(compare("EB.02", "eb_tenant_shares.tenant_eb_charge == per_day_rate * stay_days",
                     int(charge_match.sum()), len(ets), "Formula verification",
                     tolerance_pct=0))
print(f"  per_day_rate formula holds: {rate_match.sum()}/{len(ets)}")
print(f"  tenant_eb_charge formula holds: {charge_match.sum()}/{len(ets)}")

# ---- billing_month format defect (DQ.028), full-population re-verification ----
YYYYMM = re.compile(r"^\d{4}-\d{2}$")


def pct_conforming(series, pattern):
    s = series.dropna().astype(str)
    if len(s) == 0:
        return 100.0, 0
    ok = s.str.match(pattern)
    return round(100.0 * ok.sum() / len(s), 2), int((~ok).sum())

er_pct, er_bad = pct_conforming(er["billing_month"], YYYYMM)
ets_pct, ets_bad = pct_conforming(ets["billing_month"], YYYYMM)
inv_pct, inv_bad = pct_conforming(inv["billing_month"], YYYYMM)
exp_pct, exp_bad = pct_conforming(exp_["billing_month"], YYYYMM)
op_pct, op_bad = pct_conforming(op["payment_month"], YYYYMM)

rows.append(compare("EB.03", "electricity_readings.billing_month conforming to YYYY-MM (%)",
                     er_pct, 0.0, "DQ.028 (proven 0% conformance -- uses Mon-YY instead)",
                     tolerance_pct=0,
                     explanation_ok="Confirms DQ.028: 0% of electricity_readings.billing_month "
                                    "values match the YYYY-MM format every other billing_month "
                                    "column uses (all use 'Mon-YY' e.g. 'Apr-25')."))
rows.append(compare("EB.04", "eb_tenant_shares.billing_month conforming to YYYY-MM (%)",
                     ets_pct, 0.0, "DQ.028", tolerance_pct=0))
rows.append(compare("EB.05", "invoices.billing_month conforming to YYYY-MM (%)",
                     inv_pct, 100.0, "DQ.028 (control group)", tolerance_pct=0))
rows.append(compare("EB.06", "expenses.billing_month conforming to YYYY-MM (%)",
                     exp_pct, 100.0, "DQ.028 (control group)", tolerance_pct=0))
rows.append(compare("EB.07", "owner_payments.payment_month conforming to YYYY-MM (%)",
                     op_pct, 100.0, "DQ.028 (control group)", tolerance_pct=0))
print(f"  format conformance: electricity_readings={er_pct}% eb_tenant_shares={ets_pct}% "
      f"invoices={inv_pct}% expenses={exp_pct}% owner_payments={op_pct}%")

# ---- EB coverage summary (no view to validate against; recorded as first computation) ----
ep_bill = pd.to_datetime(ep["bill_date"], errors="coerce")
rows.append({
    "metric_id": "EB.08", "metric_name": "eb_payments date coverage (months)",
    "reconstructed_value": int(ep_bill.dt.to_period("M").nunique()), "reference_value": 2,
    "absolute_difference": abs(int(ep_bill.dt.to_period("M").nunique()) - 2), "percentage_difference": "",
    "validation_status": "MATCH" if ep_bill.dt.to_period("M").nunique() == 2 else "DIFFERS",
    "reference_source": "M.025 temporal_profile / evidence_integrity_report.md 9",
    "explanation": "Confirms eb_payments spans only 2 calendar months -- the narrowest coverage "
                   "of any financial table in the package.",
})

record_validation(rows, append=True)
