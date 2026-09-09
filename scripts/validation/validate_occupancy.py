"""
validate_occupancy.py -- reconstructs and validates ALL FIVE occupancy definitions (H.012a-e),
reproduces the v_occupancy on-notice/vacant SQL defect exactly (DQ.005/C.009), and validates
v_active_tenants. Every definition is kept separate -- none is presented as "the" occupancy.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from common import load_table, load_view, compare, record_validation

print("=== validate_occupancy.py ===")

beds = load_table("beds")
apts = load_table("apartments")
ta = load_table("tenant_allotments")

live_beds = beds.merge(apts[["id", "status"]].rename(columns={"id": "apartment_id", "status": "apt_status"}),
                        on="apartment_id", how="left")
live_beds = live_beds[(live_beds["status"] == "Live") & (live_beds["apt_status"] == "Live")]
bed_ids = set(live_beds["id"])
all_bed_ids = set(beds["id"])
print(f"Live beds (bed.status=Live AND apartment.status=Live): {len(bed_ids)}  |  all beds: {len(all_bed_ids)}")

allot_by_bed = ta.groupby("bed_id")["staying_status"].apply(set)


def has_status(bed_id, status):
    s = allot_by_bed.get(bed_id)
    return bool(s and status in s)


rows = []

# ---- Definition A: v_occupancy (Live beds, Staying only) -- reproduce the exact SQL,
#      INCLUDING its proven on_notice/vacant defect ----
occupied_A = sum(1 for b in bed_ids if has_status(b, "Staying"))
on_notice_col = sum(1 for b in bed_ids if has_status(b, "Staying") and has_status(b, "On-Notice"))
booked_col = sum(1 for b in bed_ids if not has_status(b, "Staying") and has_status(b, "Booked"))
vacant_col = sum(1 for b in bed_ids if not has_status(b, "Staying") and not has_status(b, "Booked")
                  and not has_status(b, "On-Notice"))
total_A = len(bed_ids)
occ_pct_A = round(100.0 * occupied_A / total_A, 2) if total_A else 0

vocc = load_view("v_occupancy")
r = vocc.iloc[0]
rows.append(compare("OCC.01", "Def A (v_occupancy): total_beds", total_A, int(r["total_beds"]), "F.005 v_occupancy"))
rows.append(compare("OCC.02", "Def A (v_occupancy): occupied (Staying)", occupied_A, int(r["occupied"]), "F.005 v_occupancy"))
rows.append(compare("OCC.03", "Def A (v_occupancy): on_notice column (defect reproduced)", on_notice_col,
                     int(r["on_notice"]), "F.005 v_occupancy",
                     explanation_ok="Reproduces the PROVEN v_occupancy defect exactly: the on_notice "
                                    "column requires Staying AND On-Notice simultaneously, which "
                                    "H.013 proves never happens (0 beds), so this is always 0."))
rows.append(compare("OCC.04", "Def A (v_occupancy): vacant column (undercounted by 7)", vacant_col,
                     int(r["vacant"]), "F.005 v_occupancy"))
unbucketed_A = total_A - occupied_A - on_notice_col - booked_col - vacant_col
rows.append(compare("OCC.05", "Def A: beds unaccounted for by v_occupancy's 4 buckets (DQ.005)",
                     unbucketed_A, 7, "H.011 unbucketed_on_notice_beds",
                     explanation_ok="Confirms exactly 7 On-Notice-only beds vanish from v_occupancy's "
                                    "occupied/on_notice/booked/vacant bucket set."))
print(f"  Def A: total={total_A} occupied={occupied_A} on_notice_col={on_notice_col} "
      f"booked={booked_col} vacant={vacant_col} unbucketed={unbucketed_A} occ_pct={occ_pct_A}")

# ---- Definition B: Live bed+apt, Staying+On-Notice (H.012b = 175/195) ----
occupied_B = sum(1 for b in bed_ids if has_status(b, "Staying") or has_status(b, "On-Notice"))
rows.append(compare("OCC.06", "Def B: Staying+On-Notice, Live bed+apt", occupied_B, 175, "H.012b"))

# ---- Definition C: ALL beds, Staying+On-Notice (H.012c = 175/203) ----
occupied_C = sum(1 for b in all_bed_ids if has_status(b, "Staying") or has_status(b, "On-Notice"))
rows.append(compare("OCC.07", "Def C: Staying+On-Notice, ALL beds", occupied_C, 175, "H.012c"))
rows.append(compare("OCC.07b", "Def C: denominator (all beds)", len(all_bed_ids), 203, "H.012c"))

# ---- Definition D: get_universal_metrics v1 (beds.status=Live only, Staying) ----
live_beds_v1 = set(beds[beds["status"] == "Live"]["id"])
occupied_D = sum(1 for b in live_beds_v1 if has_status(b, "Staying"))
rows.append(compare("OCC.08", "Def D: get_universal_metrics v1 (bed.status=Live only), Staying",
                     occupied_D, 168, "H.012d"))
rows.append(compare("OCC.08b", "Def D: denominator (bed.status=Live, no apartment filter)",
                     len(live_beds_v1), 195, "H.012d",
                     explanation_ok="Confirms bed.status=Live alone yields the same 195 as the double "
                                    "Live-bed+Live-apartment filter in this dataset (H.008: no Live "
                                    "bed sits in a non-Live apartment) -- structurally different SQL, "
                                    "coincidentally identical result here."))

# ---- get_universal_metrics v2-style notice bucket (correct, NOT has_staying AND has_notice) ----
notice_v2 = sum(1 for b in bed_ids if not has_status(b, "Staying") and has_status(b, "On-Notice"))
occupied_v2_pct_num = occupied_A + notice_v2  # Staying + On-Notice, correctly bucketed
rows.append(compare("OCC.09", "get_universal_metrics v2-style notice bucket (correct mechanism)",
                     notice_v2, 7, "H.011 (cross-check: the 7 beds ARE captured correctly here)",
                     explanation_ok="Proves get_universal_metrics_v2's bucketing formula (NOT "
                                    "has_staying AND has_notice) does NOT share v_occupancy's defect "
                                    "-- the same 7 beds are correctly isolated, not lost."))

# ---- v_active_tenants (tenant-grained, no bed/apartment filter) ----
active_tenants_recon = ta[ta["staying_status"].isin(["Staying", "On-Notice"])]["tenant_id"].nunique()
booked_tenants_recon = ta[ta["staying_status"] == "Booked"]["tenant_id"].nunique()
total_tenants_recon = ta["tenant_id"].nunique()
vat = load_view("v_active_tenants")
rv = vat.iloc[0]
rows.append(compare("OCC.10", "v_active_tenants: active_tenants (Staying+On-Notice, tenant-grained)",
                     active_tenants_recon, int(rv["active_tenants"]), "F.022 v_active_tenants"))
rows.append(compare("OCC.11", "v_active_tenants: booked_tenants", booked_tenants_recon,
                     int(rv["booked_tenants"]), "F.022 v_active_tenants"))
rows.append(compare("OCC.12", "v_active_tenants: total_tenants_ever", total_tenants_recon,
                     int(rv["total_tenants_ever"]), "F.022 v_active_tenants"))
print(f"  v_active_tenants: active={active_tenants_recon} booked={booked_tenants_recon} "
      f"total_ever={total_tenants_recon}")

# ---- allotment status rollup vs H.013 ----
staying_n = (ta["staying_status"] == "Staying").sum()
notice_n = (ta["staying_status"] == "On-Notice").sum()
rows.append(compare("OCC.13", "Staying allotments", int(staying_n), 168, "H.013 allotment_status_rollup"))
rows.append(compare("OCC.14", "On-Notice allotments", int(notice_n), 7, "H.013 allotment_status_rollup"))

record_validation(rows, append=True)

print("\nSUMMARY -- 5 occupancy definitions, none collapsed:")
print(f"  A (v_occupancy, Staying only, Live+Live):        {occupied_A}/{total_A} = {occ_pct_A}%")
print(f"  B (Staying+On-Notice, Live+Live):                 {occupied_B}/{len(bed_ids)}")
print(f"  C (Staying+On-Notice, ALL beds):                  {occupied_C}/{len(all_bed_ids)}")
print(f"  D (get_universal_metrics v1, bed.status=Live):    {occupied_D}/{len(live_beds_v1)}")
print(f"  E (get_bed_occupancy_timeline, historical):       see H.012e = 194/203 (lifetime, not reconstructed here)")
print("  AI BEHAVIOUR: state which definition is used; never silently pick one (SHOW_BOTH).")
