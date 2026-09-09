"""
apartment.py -- M.REV.003 / M.EXP.003, the apartment dimension the ledger already carries.

`journal_lines` is exported denormalised, with `apartment_id` and `bed_id` on the line itself.
The estate-level calculators group by (property_id, month) and drop that column; nothing about
the evidence required them to. Grouping by apartment instead is the same rows, the same
reversal-excluded convention and the same `signed_amount` -- one level finer, not a new measure.

What must NOT happen, and does not happen here: the postings that carry no apartment are left
unattributed and reported as their own figure under their own name. Spreading them across
apartments would be an allocation rule, and the records contain no such rule.

Two further exports describe expense allocation and are named as corroboration rather than used
as the population: `expense_bed_allocations` and `v_bed_expense_breakdown` cover the explicitly
bed-allocated subset only, which is a fraction of the expense base. Treating that subset as the
whole would understate every apartment.
"""
import pandas as pd

from engine.evidence_loader import load_table, money
from engine.calculators.base import CalcOutput, NotDeterminableError
from engine.calculators import ledger as L

# The row that holds what the records decline to place. Named, never divided.
UNATTRIBUTED = "Not attributed to an apartment"


def _apartment_codes():
    apartments = load_table("apartments")
    return {a_id: str(code).strip() for a_id, code in
            zip(apartments["id"], apartments["apartment_code"]) if code is not None}


def known_apartment_codes():
    return {code.upper() for code in _apartment_codes().values() if code}


def _require_known(apartment_code):
    """The honest limitation for an apartment the export does not contain, in the words the
    rent metric already uses. An apartment that does not exist and an apartment with nothing
    posted against it are different answers."""
    wanted = str(apartment_code).strip().upper()
    if wanted not in known_apartment_codes():
        raise NotDeterminableError(
            f"There is no apartment {apartment_code!r} in the exported records.")
    return wanted


def _by_apartment(account_type, apartment_code=None):
    """Signed amounts for one account type per apartment, with the unattributed part kept
    separate. Returns (per_apartment, total, unattributed).

    Naming an apartment NARROWS the breakdown to that apartment. It does not narrow the totals
    the note is written against: `total` and `unattributed` stay estate-wide, because the share
    of postings carrying no apartment is a fact about the whole ledger and is what makes the
    narrowed figure incomplete. The unattributed amount is never given to the named apartment.
    """
    m = L.ledger_excl_reversals()
    frame = m[m["account_type"] == account_type].copy()
    if frame.empty:
        raise NotDeterminableError(
            "The exported ledger holds no postings of this kind to attribute.")
    frame["apartment"] = frame["apartment_id"].map(_apartment_codes())
    total = round(float(frame["signed_amount"].sum()), 2)
    attributed = frame[frame["apartment"].notna()]
    per_apartment = {code: round(float(value), 2) for code, value in
                     attributed.groupby("apartment")["signed_amount"].sum().items()}
    unattributed = round(total - round(float(attributed["signed_amount"].sum()), 2), 2)

    if apartment_code:
        wanted = _require_known(apartment_code)
        per_apartment = {code: amount for code, amount in per_apartment.items()
                         if code.upper() == wanted}
        if not per_apartment:
            raise NotDeterminableError(
                f"No posting of this kind in the exported records is attributed to apartment "
                f"{wanted}.")
    return per_apartment, total, unattributed


def _attribution_note(kind, total, unattributed, narrowed=False):
    """What the apartment figures do and do not account for.

    The wording follows the shape of the answer. A full breakdown carries the unattributed row
    and says so; a single apartment's figure does not, and the note says instead that a part of
    the ledger is unattributed and that none of it has been given to this apartment. Both
    statements are the same fact, said against the figure actually shown.
    """
    share = (abs(unattributed) / abs(total) * 100.0) if total else 0.0
    if abs(unattributed) < 0.005:
        return (f"Every recorded rupee of {kind} carries the apartment it belongs to, so nothing "
                f"is left unaccounted for.")
    if narrowed:
        return (f"This is what the records post against this apartment. Across the whole ledger "
                f"Rs.{unattributed:,.2f} of {kind} ({share:.2f}%) is posted without any "
                f"apartment on the entry; none of it has been given to this apartment, because "
                f"the records carry no rule for dividing it.")
    return (f"Rs.{unattributed:,.2f} of {kind} ({share:.2f}%) is posted without an apartment on "
            f"the entry and is shown separately as unattributed. It is NOT spread across the "
            f"apartments: the records carry no rule for dividing it, and inventing one would put "
            f"a figure under an apartment the evidence does not place it in.")


def calc_revenue_by_apartment(spec, apartment_code=None):
    """M.REV.003. Recorded income per apartment, from the apartment on each posting.

    `apartment_code` narrows the breakdown to one apartment. The measure is already at
    apartment grain, so this is the filter doing what the grain supports -- not a wider figure
    wearing a narrower label.
    """
    per_apartment, total, unattributed = _by_apartment("INCOME", apartment_code)
    value = dict(sorted(per_apartment.items()))
    # The unattributed amount belongs to the ledger, not to any apartment, so it is shown only
    # alongside the full breakdown. Placing it beside a single apartment's figure would read as
    # that apartment's, which is the one reading the records do not support.
    if not apartment_code:
        value[UNATTRIBUTED] = unattributed
    return CalcOutput(
        value=value, unit="INR",
        evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts",
                          "T.apartments"),
        provenance=("SUM(signed_amount) WHERE account_type='INCOME' GROUP BY the apartment "
                    "recorded on the journal line, reversal-excluded -- the same rows and the "
                    "same convention as the estate revenue total."),
        limitations=(_attribution_note("revenue", total, unattributed, bool(apartment_code)) +
                     " These are ledger postings, not rent: rent is what was agreed for a bed, "
                     "and this is what was recorded as earned."),
    )


def _by_apartment_month(account_type, kind, apartment_code):
    """One named apartment's postings of one kind, month by month.

    The whole estate by apartment AND by month is a table rather than an answer, so the caller
    must say which apartment it means. Without one this returns the honest requirement rather
    than picking an apartment or widening to the estate.
    """
    if not apartment_code:
        raise NotDeterminableError(
            f"A month-by-month {kind} history is reported for one apartment at a time. Name the "
            f"apartment to see its history.")
    wanted = _require_known(apartment_code)

    m = L.ledger_excl_reversals()
    frame = m[m["account_type"] == account_type].copy()
    codes = {k: v.upper() for k, v in _apartment_codes().items()}
    frame["apartment"] = frame["apartment_id"].map(codes)
    mine = frame[frame["apartment"] == wanted].copy()
    if mine.empty:
        raise NotDeterminableError(
            f"No {kind} posting in the exported records is attributed to apartment {wanted}.")
    mine["month"] = pd.to_datetime(mine["entry_date"]).dt.to_period("M").dt.to_timestamp()
    series = {str(month.date()): round(float(value), 2) for month, value in
              mine.groupby("month")["signed_amount"].sum().items()}
    return CalcOutput(
        value=series, unit="INR/month",
        evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts",
                          "T.apartments"),
        provenance=(f"SUM(signed_amount) WHERE account_type='{account_type}' AND "
                    f"apartment={wanted} GROUP BY month, reversal-excluded."),
        limitations=(f"Only months in which this apartment has a recorded {kind} posting appear. "
                     f"A month absent from the series had nothing posted against this apartment; "
                     f"it is not shown as zero, because the records do not state a zero."),
    )


def calc_revenue_by_apartment_month(spec, apartment_code=None):
    """M.REV.004. One named apartment's income, month by month."""
    return _by_apartment_month("INCOME", "revenue", apartment_code)


def calc_expenses_by_apartment_month(spec, apartment_code=None):
    """M.EXP.004. One named apartment's expenses, month by month.

    The same rows M.EXP.003 totals for this apartment, grouped by month instead of collapsed --
    the apartment and the date are both already on the posting, so this is one grouping, not a
    second measure of expense.
    """
    return _by_apartment_month("EXPENSE", "expense", apartment_code)


def calc_expenses_by_apartment(spec, apartment_code=None):
    """M.EXP.003. Recorded expense per apartment, from the apartment on each posting."""
    per_apartment, total, unattributed = _by_apartment("EXPENSE", apartment_code)
    value = dict(sorted(per_apartment.items()))
    if not apartment_code:
        value[UNATTRIBUTED] = unattributed

    allocated_rows, allocated_total = 0, 0.0
    try:
        alloc = load_table("expense_bed_allocations")
        allocated_rows = len(alloc)
        allocated_total = round(float(money(alloc["allocated_amount"]).sum()), 2)
    except Exception:
        pass
    corroboration = ""
    if allocated_rows:
        corroboration = (f" Separately, the source system records {allocated_rows} explicit "
                         f"expense-to-bed allocations totalling Rs.{allocated_total:,.2f}. That "
                         f"is a subset of the expenses above, not a second measure of them, and "
                         f"is not added to them.")
    return CalcOutput(
        value=value, unit="INR",
        evidence_sources=("T.journal_lines", "T.journal_entries", "T.coa_accounts",
                          "T.apartments", "T.expense_bed_allocations"),
        provenance=("SUM(signed_amount) WHERE account_type='EXPENSE' GROUP BY the apartment "
                    "recorded on the journal line, reversal-excluded -- the same rows and the "
                    "same convention as the estate expense total."),
        limitations=(_attribution_note("expenses", total, unattributed, bool(apartment_code))
                     + corroboration +
                     " Owner rent and electricity are posted with an apartment on every line; "
                     "the estate-wide electricity bucket caveat applies here too."),
    )
