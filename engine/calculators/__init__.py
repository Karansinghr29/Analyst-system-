"""
calculators -- registry mapping metric_id -> calculator function.

Every metric_id in semantic_metric_registry.csv is listed here. Metrics whose calculation
genuinely cannot be executed from the exported evidence within Phase 1's scope (M.OCC.003,
M.OCC.004 -- get_occupancy_intelligence's day-range interval logic; M.CASH.001 is implemented
but flagged unvalidated, not omitted) map to `NOT_IMPLEMENTED`, and execution.py returns
NOT_DETERMINABLE for them rather than raising an unhandled error -- this is a deliberate,
reported gap (see the Phase 1 report), not a silent omission.
"""
from engine.calculators import financial as _fin
from engine.calculators import receivables as _ar
from engine.calculators import deposits as _dep
from engine.calculators import occupancy as _occ
from engine.calculators import maintenance as _maint
from engine.calculators import eb as _eb
from engine.calculators import invoices as _inv
from engine.calculators import collections_ as _col
from engine.calculators import risk_dq as _risk
from engine.calculators import rent as _rent
from engine.calculators import apartment as _apt

NOT_IMPLEMENTED = "NOT_IMPLEMENTED_PHASE_1"

REGISTRY = {
    # Financial
    "M.REV.001": _fin.calc_revenue_total,
    "M.REV.002": _fin.calc_revenue_by_month,
    "M.COL.001": _col.calc_collections_application,
    "M.COL.002": _col.calc_collections_by_month,
    "M.COL.003": _col.calc_collections_ledger,
    "M.INV.001": _inv.calc_invoice_billed_amount,
    "M.INV.002": _inv.calc_invoice_count,
    "M.AR.001A": _ar.calc_ar_def_a,
    "M.AR.001B": _ar.calc_ar_def_b,
    "M.AR.001C": _ar.calc_ar_def_c,
    "M.AR.001D": _ar.calc_ar_def_d,
    "M.AR.002": _ar.calc_ar_four_way,
    "M.AR.003": _ar.calc_ar_four_way,
    "M.DEP.001": _dep.calc_deposit_held,
    "M.DEP.002": _dep.calc_deposit_settlements,
    "M.DEP.003": _dep.calc_deposit_refunds,
    "M.RENT.001": _rent.calc_current_rent_by_bed,
    # Phase 17 -- evidence that was catalogued but never loaded. Each of these reads a dimension
    # or a table the export already contains; none of them introduces a new business rule.
    "M.RENT.002": _rent.calc_historical_rent_by_bed,
    "M.RENT.003": _rent.calc_rate_card,
    "M.REV.003": _apt.calc_revenue_by_apartment,
    "M.REV.004": _apt.calc_revenue_by_apartment_month,
    "M.EXP.003": _apt.calc_expenses_by_apartment,
    "M.EXP.004": _apt.calc_expenses_by_apartment_month,
    "M.EXP.001": _fin.calc_expenses_total,
    "M.EXP.002": _fin.calc_expenses_by_category,
    "M.OWN.001": _fin.calc_owner_payments_total,
    "M.OWN.002": _fin.calc_owner_rent_family,
    "M.PROFIT.001": _fin.calc_profit_family,
    "M.PNL.001": _fin.calc_pnl_by_month,
    "M.CASH.001": _fin.calc_cash_balance,
    "M.TB.001": _fin.calc_trial_balance,

    # Operations
    "M.OCC.001": _occ.calc_occupancy_family,
    "M.OCC.002": _occ.calc_occupancy_family,   # degenerate property grain -- see dimension_resolver
    "M.OCC.003": NOT_IMPLEMENTED,
    "M.OCC.004": NOT_IMPLEMENTED,
    "M.TEN.001": _occ.calc_staying_tenants,
    "M.TEN.002": _occ.calc_on_notice_tenants,
    "M.TEN.003": _occ.calc_booked_beds,
    # M.OCC.005 was grouped with OCC.003/004 as a scope gap. It is not the same case: those two
    # are DEFINED as the output of functions whose rows were never exported, while this one is
    # defined over tenant_allotments, beds and apartments -- all exported, all dated. The
    # registry has always said so ("Full history available: 2019-11-03 to 2026-08-31").
    "M.OCC.005": _occ.calc_historical_occupancy,
    "M.LIFE.001": _occ.calc_lifecycle_status_derivation,
    "M.LIFE.002": _occ.calc_move_ins,
    "M.LIFE.003": _occ.calc_move_outs,
    "M.LIFE.004": _occ.calc_exit_reconciliation,
    "M.MAINT.001": _maint.calc_maintenance_volume,
    "M.MAINT.002": _maint.calc_maintenance_cost,
    "M.EB.001": _eb.calc_eb_usage_cost,
    "M.EB.002": _eb.calc_eb_tenant_allocation,

    # Risk / DQ
    "M.RISK.001": _ar.calc_ar_four_way,
    "M.RISK.002": _risk.calc_aging,
    "M.RISK.003": _dep.calc_deposit_risk,
    "M.RISK.004": _dep.calc_phantom_deposits,
    "M.RISK.005": _risk.calc_duplicate_invoices,
    "M.RISK.006": _risk.calc_duplicate_receipts,
    "M.RISK.007": _risk.calc_overlapping_allotments,
    "M.RISK.008": _risk.calc_ledger_source_reconciliation,
    "M.RISK.009": _risk.calc_dq_trust_score,
}
