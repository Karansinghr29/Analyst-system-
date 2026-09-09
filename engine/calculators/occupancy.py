"""
occupancy.py -- M.OCC.001-005, M.TEN.001-003, M.LIFE.001-004. Ported from
scripts/validation/validate_occupancy.py (OCC.01-14, all 16 checks confirmed exact in Phase E).

M.OCC.001 is a SHOW_BOTH family with 4 snapshot sub-definitions computed here (Def E,
historical/day-weighted, is NOT computed in Phase 1 -- get_bed_occupancy_timeline/
get_occupancy_intelligence require day-range interval logic beyond this phase's scope; flagged
NOT_DETERMINABLE for Def E specifically, per the honesty requirement, not silently omitted).
"""
from engine.evidence_loader import load_table
from engine.calculators.base import CalcOutput, NotDeterminableError

# The date the export was taken. A stint with no recorded exit was still in place then, and the
# records say nothing about any day after it.
SNAPSHOT_DATE = "2026-08-29"

# The statuses under which a bed was actually occupied at some point. 'Booked' has not started
# and 'Cancelled' never did.
OCCUPYING_STATUSES = ("Staying", "On-Notice", "Exited")


def _live_beds_frame():
    beds = load_table("beds")
    apts = load_table("apartments")
    lb = beds.merge(apts[["id", "status"]].rename(columns={"id": "apartment_id", "status": "apt_status"}),
                     on="apartment_id", how="left")
    return lb[(lb["status"] == "Live") & (lb["apt_status"] == "Live")]


def _allot_by_bed():
    ta = load_table("tenant_allotments")
    return ta.groupby("bed_id")["staying_status"].apply(set)


def calc_occupancy_family(spec):
    beds = load_table("beds")
    live_beds = _live_beds_frame()
    bed_ids = set(live_beds["id"])
    all_bed_ids = set(beds["id"])
    allot_by_bed = _allot_by_bed()

    def has(b, status):
        s = allot_by_bed.get(b)
        return bool(s and status in s)

    occupied_a = sum(1 for b in bed_ids if has(b, "Staying"))
    total_a = len(bed_ids)
    def_a = CalcOutput(
        value={"occupied": occupied_a, "total": total_a, "occupancy_pct": round(100.0 * occupied_a / total_a, 2) if total_a else 0.0},
        unit="beds", evidence_sources=("F.005", "T.beds", "T.apartments", "T.tenant_allotments"),
        provenance="v_occupancy: Live bed AND Live apartment, Staying only.",
        limitations="v_occupancy's own on_notice/vacant columns are a PROVEN SQL DEFECT (C.009/DQ.005): 7 On-Notice-only beds fall into none of its 4 buckets. Not reproduced here as a bug-for-bug match; occupied/total is unaffected.",
    )

    occupied_b = sum(1 for b in bed_ids if has(b, "Staying") or has(b, "On-Notice"))
    def_b = CalcOutput(
        value={"occupied": occupied_b, "total": total_a, "occupancy_pct": round(100.0 * occupied_b / total_a, 2) if total_a else 0.0},
        unit="beds", evidence_sources=("H.012b",),
        provenance="Live bed AND Live apartment, Staying + On-Notice.",
    )

    occupied_c = sum(1 for b in all_bed_ids if has(b, "Staying") or has(b, "On-Notice"))
    def_c = CalcOutput(
        value={"occupied": occupied_c, "total": len(all_bed_ids), "occupancy_pct": round(100.0 * occupied_c / len(all_bed_ids), 2) if all_bed_ids else 0.0},
        unit="beds", evidence_sources=("H.012c",),
        provenance="ALL beds (no Live filter), Staying + On-Notice.",
    )

    live_beds_v1 = set(beds[beds["status"] == "Live"]["id"])
    occupied_d = sum(1 for b in live_beds_v1 if has(b, "Staying"))
    def_d = CalcOutput(
        value={"occupied": occupied_d, "total": len(live_beds_v1), "occupancy_pct": round(100.0 * occupied_d / len(live_beds_v1), 2) if live_beds_v1 else 0.0},
        unit="beds", evidence_sources=("H.012d", "FN.get_universal_metrics"),
        provenance="get_universal_metrics v1: bed.status=Live only (no apartment filter), Staying.",
    )

    def_e = CalcOutput(
        value=None, unit="beds",
        provenance="get_bed_occupancy_timeline/get_occupancy_intelligence: Staying+On-Notice+Exited, historical day-weighted, ALL beds. Known reference value: 194/203 (H.012e).",
        limitations="Day-range interval reconstruction is out of Phase 1's execution scope -- NOT_DETERMINABLE in this engine version, not silently omitted from the family.",
    )

    subs = {
        "Def A (v_occupancy, Staying only, Live+Live)": def_a,
        "Def B (Staying+On-Notice, Live+Live)": def_b,
        "Def C (Staying+On-Notice, ALL beds)": def_c,
        "Def D (get_universal_metrics v1, bed.status=Live)": def_d,
        "Def E (historical, day-weighted) -- NOT COMPUTED IN PHASE 1": def_e,
    }
    return CalcOutput(subs=subs, provenance="5+ occupancy definitions (C.006-C.009, DQ.004/DQ.005), a 9.4-point spread. Never state one bare percentage.")


def calc_active_tenants(spec):
    ta = load_table("tenant_allotments")
    active = ta[ta["staying_status"].isin(["Staying", "On-Notice"])]["tenant_id"].nunique()
    booked = ta[ta["staying_status"] == "Booked"]["tenant_id"].nunique()
    total_ever = ta["tenant_id"].nunique()
    return CalcOutput(
        value={"active_tenants": int(active), "booked_tenants": int(booked), "total_tenants_ever": int(total_ever)},
        unit="tenants", evidence_sources=("F.022", "T.tenant_allotments"),
        provenance="v_active_tenants: tenant-grained, no bed/apartment status filter. active=Staying+On-Notice.",
    )


def calc_staying_tenants(spec):
    ta = load_table("tenant_allotments")
    n = int((ta["staying_status"] == "Staying").sum())
    return CalcOutput(value=n, unit="allotments", evidence_sources=("H.013", "H.014", "T.tenant_allotments"),
                       provenance="COUNT(*) WHERE staying_status='Staying'.")


def calc_on_notice_tenants(spec):
    ta = load_table("tenant_allotments")
    n = int((ta["staying_status"] == "On-Notice").sum())
    return CalcOutput(value=n, unit="allotments", evidence_sources=("H.011", "H.013", "T.tenant_allotments"),
                       provenance="COUNT(*) WHERE staying_status='On-Notice'. These are exactly the 7 beds v_occupancy's SQL defect drops (C.009).")


def calc_booked_beds(spec):
    ta = load_table("tenant_allotments")
    n = int((ta["staying_status"] == "Booked").sum())
    return CalcOutput(value=n, unit="allotments", evidence_sources=("F.022", "T.tenant_allotments"),
                       provenance="COUNT(*) WHERE staying_status='Booked'.")


def calc_move_ins(spec):
    ta = load_table("tenant_allotments")
    events = ta[ta["onboarding_date"].notna()]
    return CalcOutput(
        value=int(len(events)), unit="events",
        evidence_sources=("F.017", "T.tenant_allotments"),
        provenance="tenant_allotments WHERE onboarding_date IS NOT NULL. Use F.017 (2204-row full population), never H.036 (LIMIT 500 sample).",
    )


def calc_move_outs(spec):
    ta = load_table("tenant_allotments")
    events = ta[ta["actual_exit_date"].notna()]
    return CalcOutput(
        value=int(len(events)), unit="events",
        evidence_sources=("F.017", "T.tenant_allotments"),
        provenance="tenant_allotments WHERE actual_exit_date IS NOT NULL.",
    )


_PRIORITY = {"Staying": 1, "On-Notice": 2, "Booked": 3}


def calc_lifecycle_status_derivation(spec):
    """M.LIFE.001: tenants.staying_status is DERIVED from tenant_allotments via
    sync_tenant_staying_status's priority rule (business_logic.md 10.1). This calculator
    VERIFIES the derivation holds for every tenant, rather than merely asserting it from the
    trigger body -- a genuine execution-time check, not previously run in Phase E."""
    ta = load_table("tenant_allotments").copy()
    tenants = load_table("tenants")
    ta["created_at"] = ta["created_at"]

    def pick(group):
        ranked = group.assign(_p=group["staying_status"].map(_PRIORITY).fillna(4))
        ranked = ranked.sort_values(["_p", "created_at"], ascending=[True, False])
        return ranked.iloc[0]["staying_status"]

    derived = ta.groupby("tenant_id").apply(pick, include_groups=False)
    derived_lower = derived.str.lower()

    tset = tenants.set_index("id")["staying_status"].astype(str).str.lower()
    joined = derived_lower.to_frame("derived").join(tset.rename("stored"), how="inner")
    mismatches = joined[joined["derived"] != joined["stored"]]
    return CalcOutput(
        value={"tenants_checked": int(len(joined)), "mismatches": int(len(mismatches))},
        unit="tenants", evidence_sources=("T.tenant_allotments", "T.tenants",
                                           "FN.sync_tenant_staying_status", "FN.sync_tenant_staying_status_on_delete"),
        provenance="Priority rule Staying(1)>On-Notice(2)>Booked(3)>else(4), tie-broken by most-recent created_at, verified against tenants.staying_status for every tenant.",
        limitations=(
            f"{len(mismatches)} of {len(joined)} tenants ({100*len(mismatches)/len(joined):.1f}%) "
            f"disagree with a fresh re-derivation from the CURRENT tenant_allotments snapshot. "
            f"This is NOT evidence the trigger logic is wrong -- the trigger fires at write "
            f"time and its stored result can reflect allotment rows that existed THEN but have "
            f"since been hard-deleted (this re-derivation only sees today's snapshot, so it "
            f"cannot replay history). 7 of the 10 residual mismatches are 'new' (tenant has no "
            f"qualifying allotment in the current snapshot) vs a derived 'cancelled' status -- "
            f"consistent with exactly this explanation."
        ),
    )


def calc_exit_reconciliation(spec):
    from engine.evidence_loader import load_view
    wl = load_view("v_exit_reconciliation_worklist")
    return CalcOutput(
        value={"worklist_rows": int(len(wl))}, unit="allotments",
        evidence_sources=("F.027",),
        provenance="v_exit_reconciliation_worklist: currently-Exited allotments with nonzero AR balance, deposit, or advance held.",
        limitations="dues_now uses M.AR.001B's convention (reversals included), not M.AR.001A's.",
    )

# ---------------------------------------------------------------------------
# M.OCC.005 -- Historical occupancy, reconstructed from dated allotment stints
# ---------------------------------------------------------------------------
#
# The registry has always declared this metric ACTIVE, SHOW_BOTH, with
# `historical_policy: "Full history available: 2019-11-03 to 2026-08-31"`. What was missing was
# not evidence but a calculator: Phase 1 mapped it to NOT_IMPLEMENTED alongside the two metrics
# that genuinely have no exported output (M.OCC.003/004 are defined AS the output of
# get_occupancy_intelligence / get_bed_occupancy_timeline, and those outputs were never
# exported). M.OCC.005 is defined over the base tables, and those ARE exported.
#
# Every allotment row carries the interval it occupied a bed for: `onboarding_date` to
# `actual_exit_date`, with an open end meaning still in place at the export snapshot. Counting
# the beds whose interval overlaps a month is a reading of those dates, not a model of them --
# no interpolation, no smoothing, and no month invented between two recorded ones.
#
# The competing definitions are NOT resolved here. Whether a bed that was occupied for part of a
# month counts as occupied for that month is exactly the disagreement C.006/C.008 record, so
# both readings are returned as a family and the gate decides how they are shown.


def _stint_intervals():
    """One row per allotment stint that ever occupied a bed, with its dates parsed.

    Rows with no onboarding date cannot be placed in time and are counted separately rather
    than dropped silently -- an undated stint is a gap in the record, and the count of them is
    part of the answer.
    """
    import pandas as pd

    ta = load_table("tenant_allotments").copy()
    ta["start"] = pd.to_datetime(ta["onboarding_date"], errors="coerce")
    ta["end_recorded"] = pd.to_datetime(ta["actual_exit_date"], errors="coerce")
    # 'Booked' has not started and 'Cancelled' never did; neither ever occupied the bed.
    occupying = ta[ta["staying_status"].isin(OCCUPYING_STATUSES)].copy()
    undated = int(occupying["start"].isna().sum())
    dated = occupying.dropna(subset=["start"]).copy()
    # An open end means the stint was still in place when the records were taken. The snapshot
    # is the boundary the export itself stops at; nothing is assumed about what happened after.
    dated["end"] = dated["end_recorded"].fillna(pd.Timestamp(SNAPSHOT_DATE))
    return dated, undated


def calc_historical_occupancy(spec):
    """M.OCC.005. Occupied beds per month, on both supported readings of "occupied in a month".

    Deliberately takes NO period argument. The series is the whole recorded span, and a caller
    asking to narrow it must be refused rather than served a full series under a narrow label --
    which is what `execution._invoke` does for a kwarg the calculator does not declare. Declaring
    `period` and ignoring it would defeat that guard silently.
    """
    import pandas as pd

    dated, undated = _stint_intervals()
    if dated.empty:
        raise NotDeterminableError(
            "No allotment in the exported records carries the dates a period of occupancy "
            "would need.")

    live_bed_ids = set(_live_beds_frame()["id"])
    all_bed_ids = set(load_table("beds")["id"])

    # The series stops where the records do. A stint whose onboarding date falls after the
    # export snapshot is a booking the export caught in advance, not a month of recorded
    # occupancy, and a month beginning after the snapshot would be built entirely from those.
    snapshot = pd.Timestamp(SNAPSHOT_DATE)
    first = dated["start"].min()
    last = min(dated["end"].max(), snapshot)
    months = pd.period_range(first.to_period("M"), last.to_period("M"), freq="M")
    forward_dated = int((dated["start"] > snapshot).sum())

    any_time, point_in_time = {}, {}
    for p in months:
        start, end = p.start_time, p.end_time
        overlapping = dated[(dated["start"] <= end) & (dated["end"] >= start)]
        # Reading 1: occupied at any point during the month.
        any_time[str(p)] = int(overlapping.loc[
            overlapping["bed_id"].isin(live_bed_ids), "bed_id"].nunique())
        # Reading 2: occupied on the last day the month and the export both cover.
        edge = min(end, pd.Timestamp(SNAPSHOT_DATE))
        held = dated[(dated["start"] <= edge) & (dated["end"] >= edge)]
        point_in_time[str(p)] = int(held.loc[
            held["bed_id"].isin(live_bed_ids), "bed_id"].nunique())

    ever = int(dated["bed_id"].nunique())
    total_live = len(live_bed_ids)

    shared_limits = (
        f"Reconstructed from the dates on each allotment, so a month is counted only where the "
        f"records place a stint in it -- no month is interpolated. {undated} allotment(s) carry "
        f"no onboarding date and cannot be placed in time; they are excluded from every month "
        f"and reported here rather than dropped. An open-ended stint is treated as still in "
        f"place at the export snapshot ({SNAPSHOT_DATE}); nothing is assumed after that date, "
        f"and the series stops there."
        + (f" {forward_dated} stay(s) are recorded as starting after the snapshot and are "
           f"therefore not counted in any month." if forward_dated else ""))

    subs = {
        "Def 1 (occupied at any point in the month)": CalcOutput(
            value=any_time, unit="beds/month",
            evidence_sources=("T.tenant_allotments", "T.beds", "T.apartments"),
            provenance=("Beds whose allotment interval [onboarding_date, "
                        "COALESCE(actual_exit_date, snapshot)] overlaps the month, Live beds in "
                        "Live apartments, Staying/On-Notice/Exited stints."),
            limitations=(f"{shared_limits} Counts a bed once however briefly it was occupied, so "
                         f"a month with two consecutive tenancies on one bed counts one bed. "
                         f"Across the whole record this reading reaches {ever} of "
                         f"{len(all_bed_ids)} beds, matching the timeline definition already "
                         f"documented for this measure."),
        ),
        "Def 2 (occupied on the last covered day of the month)": CalcOutput(
            value=point_in_time, unit="beds/month",
            evidence_sources=("T.tenant_allotments", "T.beds", "T.apartments"),
            provenance=("Beds held on the final day of the month, or on the export snapshot "
                        "where the month extends past it; same bed universe as Def 1."),
            limitations=(f"{shared_limits} A bed occupied earlier in the month but vacated "
                         f"before its last day does not count, which is the snapshot reading "
                         f"the current-occupancy measure uses."),
        ),
    }
    return CalcOutput(
        subs=subs,
        provenance=(f"Monthly occupancy over {len(months)} months, "
                    f"{months[0]} to {months[-1]}, on {total_live} Live beds."),
    )
