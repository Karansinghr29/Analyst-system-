"""
maintenance.py -- M.MAINT.001/002. Ported from scripts/validation/validate_maintenance.py
(MAINT.01-06, all confirmed exact in Phase E, including the proven H.019 1613-vs-1611 mechanism).
"""
import pandas as pd

from engine.evidence_loader import load_table, money
from engine.calculators.base import CalcOutput


def calc_maintenance_volume(spec):
    mt = load_table("maintenance_tickets")
    return CalcOutput(
        value=int(len(mt)), unit="tickets",
        evidence_sources=("F.015", "T.maintenance_tickets"),
        provenance="COUNT(*) FROM maintenance_tickets. created_at IS the business date here (no other business-open date exists).",
        limitations="20-month coverage (2025-01 to 2026-08) -- the shortest operational domain in the package. No YoY comparison.",
    )


def calc_maintenance_cost(spec):
    mt = load_table("maintenance_tickets").copy()
    tr = load_table("ticket_resolutions")
    exp = load_table("expenses")
    it = load_table("issue_types")

    mt["month"] = pd.to_datetime(mt["created_at"], utc=True, errors="coerce").dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
    tr_ren = tr.rename(columns={"id": "ticket_resolution_id_pk"})
    mt_tr = mt.merge(tr_ren[["ticket_id", "ticket_resolution_id_pk"]].rename(columns={"ticket_id": "id"}), on="id", how="left")
    has_res = mt_tr[mt_tr["ticket_resolution_id_pk"].notna()].copy()
    no_res = mt_tr[mt_tr["ticket_resolution_id_pk"].isna()].copy()
    no_res["amount"] = pd.NA
    has_res_exp = has_res.merge(
        exp.loc[exp["ticket_resolution_id"].notna(), ["ticket_resolution_id", "amount"]]
           .rename(columns={"ticket_resolution_id": "ticket_resolution_id_pk"}),
        on="ticket_resolution_id_pk", how="left")
    mt_tr_exp = pd.concat([has_res_exp, no_res], ignore_index=True)
    path_a_total = round(float(money(mt_tr_exp["amount"]).fillna(0).sum()), 2)

    exp_b = exp[exp["ticket_resolution_id"].notna()].merge(
        it[["id", "name"]].rename(columns={"id": "issue_type_id", "name": "issue_type_name"}),
        on="issue_type_id", how="inner")
    path_b_total = round(float(money(exp_b["amount"]).sum()), 2)

    return CalcOutput(
        value={"path_a_total": path_a_total, "path_b_total": path_b_total},
        unit="INR", evidence_sources=("F.015", "F.016", "T.maintenance_tickets", "T.ticket_resolutions", "T.expenses", "T.issue_types"),
        provenance="Path A: tickets->ticket_resolutions->expenses (dated by ticket month). Path B: expenses.issue_type_id direct (dated by expense_date).",
        limitations="Structurally capable of disagreeing (C.023) but PROVEN, for this dataset, to produce an identical total. H.019's 1613-vs-1611 ticket-count gap is caused by 2 double-resolved tickets (proven mechanism).",
    )
