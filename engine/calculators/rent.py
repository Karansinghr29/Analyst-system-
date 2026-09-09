"""
rent.py -- M.RENT.001, the rent currently recorded on each occupied bed.

The grain is the finding, and it is not the one the question usually assumes. `monthly_rental`
sits on `tenant_allotments`, one row per tenant-on-a-bed stint, and the application's own
`get_occupancy_intelligence` resolves it per BED:

    bed_rent as (
      select distinct on (bed_id) bed_id, coalesce(monthly_rental, 0) as monthly_rental
      from stint order by bed_id, onboarding_date desc
    )

That settles two things the column name alone could not. It is per bed, and it is monthly --
the same function converts it with `* occupied_days / 30.0`, which is only meaningful for a
monthly amount.

It also shows what an apartment-level rent would cost. 32 of the 37 apartments holding a
current allotment carry MORE THAN ONE rent right now; A12 alone runs Rs.14,500, Rs.15,500 and
Rs.19,500 across four occupied beds. Any single "rent for A12" would therefore be a figure
chosen by whoever wrote the aggregation, not a figure the records contain. This calculator
returns the beds and their rents, and leaves the choosing undone.

Two deliberate departures from the application's expression:

  * `coalesce(monthly_rental, 0)` is NOT copied. It makes a bed with no rent recorded
    indistinguishable from a bed genuinely let at zero, and both exist here. A missing value
    stays missing.
  * `distinct on (bed_id) ... order by onboarding_date desc` runs over Staying, On-Notice AND
    Exited stints, so it yields the LAST KNOWN rent for a bed, occupied or long empty. For a
    question about current rent that is the wrong set, so the live filter
    (`staying_status='Staying' AND actual_exit_date IS NULL`) is applied first and the
    onboarding-date rule then breaks any remaining tie. In this export it breaks none: all 168
    current allotments sit on 168 distinct beds.
"""
import re

from engine.calculators.base import CalcOutput, NotDeterminableError
from engine.evidence_loader import load_table

# The staying_status that means "occupying the bed now". On-Notice tenants have given notice and
# are still in place, but their allotment is ending; Booked has not started. Neither is the
# unambiguous current occupant, and the registry filter names 'Staying' alone.
CURRENT_STATUS = "Staying"

EVIDENCE = ("T.tenant_allotments", "T.beds", "T.apartments", "FN.get_occupancy_intelligence")


def _rent(raw):
    """The recorded rent as a number, or None when nothing was recorded. Zero is a value."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if value != value else value


def current_rent_rows(apartment_code=None):
    """One row per currently occupied bed. Pure lookup: no arithmetic on the rent at all.

    Each row carries `rent=None` where nothing was recorded, so a caller can tell a missing
    entry from a recorded zero. Rows are ordered by bed code for a stable answer.
    """
    allotments = load_table("tenant_allotments")
    apartments = load_table("apartments")
    beds = load_table("beds")

    codes = {a_id: str(code) for a_id, code in
             zip(apartments["id"], apartments["apartment_code"]) if code is not None}
    bed_codes = {b_id: str(code) for b_id, code in
                 zip(beds["id"], beds["bed_code"]) if code is not None}

    wanted = str(apartment_code).strip().upper() if apartment_code else ""

    rows = []
    columns = ("apartment_id", "bed_id", "monthly_rental", "staying_status",
               "actual_exit_date", "onboarding_date", "tenant_id")
    for values in zip(*(allotments[c] for c in columns)):
        record = dict(zip(columns, values))
        if str(record["staying_status"]).strip() != CURRENT_STATUS:
            continue
        exit_date = record["actual_exit_date"]
        if exit_date is not None and str(exit_date).strip() not in ("", "nan", "NaT", "None"):
            continue
        code = codes.get(record["apartment_id"], "")
        if wanted and code.upper() != wanted:
            continue
        rows.append({
            "apartment": code,
            "bed": bed_codes.get(record["bed_id"], ""),
            "rent": _rent(record["monthly_rental"]),
            "onboarding_date": str(record["onboarding_date"] or ""),
        })

    # The application's tie-break, kept: the latest allotment on a bed wins. It changes nothing
    # in this export, and stating the rule is what makes the result reproducible if it ever does.
    latest = {}
    for row in rows:
        key = (row["apartment"], row["bed"])
        held = latest.get(key)
        if held is None or row["onboarding_date"] > held["onboarding_date"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda r: (r["apartment"], r["bed"]))


def known_apartment_codes():
    """Apartment codes the export actually contains, for entity resolution."""
    apartments = load_table("apartments")
    return {str(code).strip().upper() for code in apartments["apartment_code"]
            if code is not None and str(code).strip()}


def calc_current_rent_by_bed(spec, apartment_code=None):
    """M.RENT.001. Returns {bed label: rent}, or raises when the request cannot be served."""
    if apartment_code:
        wanted = str(apartment_code).strip().upper()
        if wanted not in known_apartment_codes():
            raise NotDeterminableError(
                f"There is no apartment {apartment_code!r} in the exported records.")

    rows = current_rent_rows(apartment_code)
    if not rows:
        if apartment_code:
            raise NotDeterminableError(
                f"Apartment {str(apartment_code).strip().upper()} has no bed currently "
                f"occupied, so no rent is in force for it.")
        raise NotDeterminableError("No bed is currently occupied, so no rent is in force.")

    scope = (f" in apartment {str(apartment_code).strip().upper()}" if apartment_code
             else " across the estate")
    missing = sum(1 for r in rows if r["rent"] is None)
    zeros = sum(1 for r in rows if r["rent"] == 0)

    limitations = [
        "Rent is recorded per bed. The beds in one apartment often carry different rents, so "
        "there is no single apartment rent to state.",
        "This is the rent recorded on the current allotment. It carries no effective date, so "
        "it describes the position now and cannot be read back to an earlier period.",
    ]
    if zeros:
        limitations.append(
            f"{zeros} of these beds record a rent of zero. That is kept as recorded; the "
            f"export does not establish whether it is a genuine zero-rent arrangement or a "
            f"rent that was never entered.")
    if missing:
        limitations.append(
            f"{missing} of these beds have no rent recorded at all, and are shown as such "
            f"rather than as zero.")

    return CalcOutput(
        value={f"{r['apartment']} bed {r['bed']}".strip(): r["rent"] for r in rows},
        unit="INR",
        evidence_sources=EVIDENCE,
        provenance=(
            f"tenant_allotments.monthly_rental WHERE staying_status='{CURRENT_STATUS}' AND "
            f"actual_exit_date IS NULL{scope}, one row per bed (latest onboarding_date wins, "
            f"matching get_occupancy_intelligence's bed_rent rule). No aggregation applied."),
        limitations=" ".join(limitations),
    )


# ---------------------------------------------------------------------------
# M.RENT.002 -- the rent recorded for a bed in a PAST month
# ---------------------------------------------------------------------------
#
# M.RENT.001's historical policy says CURRENT STATE ONLY, because `monthly_rental` carries no
# effective date. That is true of the column and too broad as a statement about the evidence.
#
# Each allotment row is a stint on a bed, bounded by `onboarding_date` and `actual_exit_date`.
# The rent on that row is therefore dated by the stint that holds it: for any past month, the
# stint occupying the bed in that month is identifiable, and so is the rent recorded against it.
# 1,003 of the exited stints carry an exit date, so the intervals close.
#
# What remains genuinely unavailable is a rent REVISION applied inside a stint. The table has
# `created_at` and no `updated_at`, and `audit_logs` holds no tenant_allotments row and no
# mention of `monthly_rental` at all. So one stint yields one rent for its whole length, and
# this calculator never invents a second one inside it.
#
# `bed_rates` is a different thing again and is reported separately, never as the charged rent:
# it is a published rate card by bed type with `from_date`/`to_date`, which says what a bed of
# that type was listed at, not what any tenant was actually charged.

SNAPSHOT_DATE = "2026-08-29"
OCCUPYING_STATUSES = ("Staying", "On-Notice", "Exited")
RATE_CARD_EVIDENCE = ("T.bed_rates",)


def _parse_month(period):
    """The requested month as (start, end), or None when nothing usable was asked for."""
    import pandas as pd

    text = str(period or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})", text)
    if not match:
        return None
    start = pd.Timestamp(int(match.group(1)), int(match.group(2)), 1)
    return start, start + pd.offsets.MonthEnd(1)


def historical_rent_rows(period, apartment_code=None):
    """One row per bed occupied in the requested month, with the rent recorded on the stint that
    occupied it. Pure lookup: the rent is the recorded value, unchanged."""
    import pandas as pd

    window = _parse_month(period)
    if window is None:
        # No month is assumed and none is defaulted: the latest month would answer a question
        # nobody asked, under the heading of the one they did.
        raise NotDeterminableError(
            "Historical rent needs a month or period to identify the rent recorded for that "
            "time. Name the month and the rent recorded against each bed for it is shown.")
    start, end = window

    allotments = load_table("tenant_allotments").copy()
    apartments = load_table("apartments")
    beds = load_table("beds")
    codes = {a_id: str(code) for a_id, code in
             zip(apartments["id"], apartments["apartment_code"]) if code is not None}
    bed_codes = {b_id: str(code) for b_id, code in
                 zip(beds["id"], beds["bed_code"]) if code is not None}

    allotments["start"] = pd.to_datetime(allotments["onboarding_date"], errors="coerce")
    allotments["end"] = pd.to_datetime(allotments["actual_exit_date"], errors="coerce").fillna(
        pd.Timestamp(SNAPSHOT_DATE))
    live = allotments[allotments["staying_status"].isin(OCCUPYING_STATUSES)]
    covering = live[live["start"].notna() & (live["start"] <= end) & (live["end"] >= start)]

    wanted = str(apartment_code).strip().upper() if apartment_code else ""
    rows = []
    for _, record in covering.iterrows():
        code = codes.get(record["apartment_id"], "")
        if wanted and code.upper() != wanted:
            continue
        rows.append({
            "apartment": code,
            "bed": bed_codes.get(record["bed_id"], ""),
            "rent": _rent(record["monthly_rental"]),
            "onboarding_date": str(record["onboarding_date"] or ""),
        })
    latest = {}
    for row in rows:
        key = (row["apartment"], row["bed"])
        held = latest.get(key)
        if held is None or row["onboarding_date"] > held["onboarding_date"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda r: (r["apartment"], r["bed"]))


def rate_card_rows(period=None):
    """The published rate card, filtered to the ranges covering a month when one is given.

    This is what a bed TYPE was listed at, with the dates that listing applied. It is not
    evidence of what any tenant paid, and is returned under its own name so the two are never
    read as one figure.
    """
    import pandas as pd

    rates = load_table("bed_rates").copy()
    rates["from"] = pd.to_datetime(rates["from_date"], errors="coerce")
    rates["to"] = pd.to_datetime(rates["to_date"], errors="coerce").fillna(
        pd.Timestamp("2999-12-31"))
    window = _parse_month(period) if period else None
    if window is not None:
        start, end = window
        rates = rates[(rates["from"] <= end) & (rates["to"] >= start)]
    out = {}
    for _, r in rates.iterrows():
        label = f"{str(r['bed_type']).strip()}, {str(r['toilet_type']).strip()} bathroom"
        rate = _rent(r["monthly_rate"])
        if rate is not None:
            out[label] = rate
    return out


def calc_historical_rent_by_bed(spec, period=None, apartment_code=None):
    """M.RENT.002. The rent recorded against each bed occupied in a named past month."""
    if apartment_code:
        wanted = str(apartment_code).strip().upper()
        if wanted not in known_apartment_codes():
            # The same sentence the current-rent metric uses. An apartment that does not exist
            # and an apartment that was empty that month are different answers.
            raise NotDeterminableError(
                f"There is no apartment {apartment_code!r} in the exported records.")
    rows = historical_rent_rows(period, apartment_code)
    if not rows:
        scope = f" in apartment {str(apartment_code).strip().upper()}" if apartment_code else ""
        raise NotDeterminableError(
            f"The exported records show no bed occupied{scope} in that month, so no rent was "
            f"in force for one.")

    missing = sum(1 for r in rows if r["rent"] is None)
    zeros = sum(1 for r in rows if r["rent"] == 0)
    limitations = [
        "This is the rent recorded on the stay that occupied each bed in that month, so it is "
        "the rent that was in force then, not today's.",
        "One stay carries one recorded rent for its whole length. If a rent was changed part-way "
        "through a stay, the records do not show it: the allotment carries no revision date and "
        "the change log holds no rent change at all.",
        "Rent is recorded per bed, so there is no single apartment rent for a past month either.",
    ]
    if zeros:
        limitations.append(
            f"{zeros} of these beds record a rent of zero, kept as recorded.")
    if missing:
        limitations.append(
            f"{missing} of these beds have no rent recorded at all, and are shown as such "
            f"rather than as zero.")

    return CalcOutput(
        value={f"{r['apartment']} bed {r['bed']}".strip(): r["rent"] for r in rows},
        unit="INR",
        # The rate card is NOT evidence for this figure. It is a listing by bed type; this is
        # what a stay recorded. Attaching it here would blur exactly the distinction this metric
        # exists to keep -- it belongs to M.RENT.003, which is the metric that reads it.
        evidence_sources=EVIDENCE,
        provenance=(
            f"tenant_allotments.monthly_rental of the stint whose "
            f"[onboarding_date, COALESCE(actual_exit_date, {SNAPSHOT_DATE})] interval covers "
            f"{period}, one row per bed (latest onboarding_date wins). No aggregation applied."),
        limitations=" ".join(limitations),
    )


def calc_rate_card(spec, period=None):
    """M.RENT.003. The published monthly rate by bed type, with the dates it applied."""
    rows = rate_card_rows(period)
    if not rows:
        raise NotDeterminableError(
            "The exported rate card covers no bed type for that period.")
    return CalcOutput(
        value=rows, unit="INR",
        evidence_sources=RATE_CARD_EVIDENCE,
        provenance=("bed_rates.monthly_rate by (bed_type, toilet_type), restricted to the rate "
                    "rows whose [from_date, to_date] range covers the requested period."),
        limitations=(
            "This is the published rate for a type of bed, with the dates it applied. It is not "
            "what any tenant was charged: the rent actually recorded against a bed is held on "
            "the stay occupying it and often differs from the card."),
    )
