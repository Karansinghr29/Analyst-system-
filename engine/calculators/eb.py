"""
eb.py -- M.EB.001/002. Ported from scripts/validation/validate_eb.py (EB.01-08, all confirmed
exact in Phase E).
"""
from engine.evidence_loader import load_table, money
from engine.calculators.base import CalcOutput


def calc_eb_usage_cost(spec):
    ep = load_table("eb_payments")
    er = load_table("electricity_readings")
    total_bill = round(float(money(ep["bill_amount"]).sum()), 2)
    total_units = round(float(money(er["units_consumed"]).sum()), 2)
    return CalcOutput(
        value={"total_bill_amount": total_bill, "total_units_consumed": total_units},
        unit="mixed", evidence_sources=("T.eb_payments", "T.electricity_readings"),
        provenance="SUM(eb_payments.bill_amount); SUM(electricity_readings.units_consumed).",
        limitations="eb_payments spans only 2 months (2026-04 to 2026-06) -- narrowest coverage of any financial domain (DQ.021/DQ.028). eb_monitoring_readings is a 1-day snapshot, no trend. billing_month uses 'Mon-YY' text, incompatible with invoices/expenses' 'YYYY-MM' without conversion.",
    )


def calc_eb_tenant_allocation(spec):
    ets = load_table("eb_tenant_shares")
    total_charge = round(float(money(ets["tenant_eb_charge"]).sum()), 2)
    n = int(len(ets))
    return CalcOutput(
        value={"total_tenant_eb_charge": total_charge, "row_count": n},
        unit="mixed", evidence_sources=("T.eb_tenant_shares",),
        provenance="per_day_rate = ROUND(total_apartment_bill/total_tenant_days); tenant_eb_charge = per_day_rate*stay_days. Formula reverse-engineered, PROVEN exact over the full 801-row population (not merely a 5-row sample).",
        limitations="Relationship to invoices.electricity_amount is Not determinable from exported evidence (no view/function joins the two). billing_month format issue (DQ.028) applies.",
    )
