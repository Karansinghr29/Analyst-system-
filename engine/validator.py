"""
validator.py -- Phase 2. The **Validator role** (ai_agent_roles.md 2) implementing the
Validation stage of analytics_execution_spec.md 8 and ai_analytics_architecture.md 9.

Phase 1 had `validation.py`, which only looked up a metric's historical status string in
validation_summary.csv. Phase 2 adds the two things 8 actually requires and 1 did not have:

  1. **The numbers, not just the verdict.** 9: "compare reconstructed vs. reference, compute
     absolute/percentage difference, flag DIFFERS rather than silently accepting." The
     ValidationVerdict below carries reconstructed/reference/absolute/percentage explicitly.

  2. **Internal sanity checks, which HALT rather than answer.** 8: "A result that fails an
     internal sanity check must never be silently emitted. Sanity checks include: non-negative
     counts, debit=credit balance identities for ledger sub-totals (enforce_journal_balanced's
     guarantee, business_dimensions.md 21 -- a violation here would indicate an execution-engine
     bug, not a business fact, and must halt rather than answer), and grain-consistency (a
     grouped result's row count should not exceed the ungrouped population)."

The Validator "must never present an unverified result with the same confidence framing as a
validated one" -- enforced here by returning UNVERIFIED (never MATCH) when no reference exists,
and by confidence.py consuming this verdict rather than the trust level alone.
"""
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

from engine.validation import ValidationIndex


class SanityCheckFailure(Exception):
    """analytics_execution_spec.md 8: a failed sanity check indicates an execution-engine bug,
    not a business fact. It must halt rather than answer."""


@dataclass(frozen=True)
class SanityCheck:
    name: str
    applicable: bool
    passed: bool
    detail: str


@dataclass(frozen=True)
class ValidationVerdict:
    metric_id: str
    status: str                      # MATCH | DIFFERS | PARTIAL | UNVERIFIED
    reconstructed_value: str
    reference_value: str
    absolute_difference: str
    percentage_difference: str
    reference_source: str
    check_ids: tuple
    explanation: str
    sanity_checks: tuple = field(default_factory=tuple)

    @property
    def sanity_passed(self):
        return all(c.passed for c in self.sanity_checks if c.applicable)

    @property
    def independently_validated(self):
        """True only when a real exported reference confirmed this metric. Drives
        answer_contract.md 3's distinction between HIGH and 'HIGH (by construction, not
        independently re-validated)'."""
        return self.status in ("MATCH", "DIFFERS", "PARTIAL")


# --- Sanity checks (analytics_execution_spec.md 8) --------------------------------------------

_COUNT_UNIT_HINTS = ("count", "beds", "tenants", "tickets", "invoices", "receipts", "rows",
                     "groups", "allotments", "entries", "pairs")


def _numeric_leaves(value):
    """Every numeric scalar inside a result value (scalar, dict, or nested dict)."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        out = []
        for v in value.values():
            out.extend(_numeric_leaves(v))
        return out
    return []


def check_finite(value):
    """A NaN or infinity reaching a result is always an execution-engine defect (a bad merge,
    a divide-by-zero, a dtype coercion failure) -- never a business fact."""
    leaves = _numeric_leaves(value)
    if not leaves:
        return SanityCheck("finite_numeric", False, True, "No numeric leaves to check.")
    bad = [v for v in leaves if isinstance(v, float) and (math.isnan(v) or math.isinf(v))]
    return SanityCheck(
        "finite_numeric", True, not bad,
        "All numeric values finite." if not bad else f"{len(bad)} non-finite value(s): {bad[:5]}")


def check_non_negative_count(value, unit):
    """8: 'non-negative counts'. Only applies where the unit declares the value IS a count --
    monetary values may legitimately be negative (a credit balance, a net loss)."""
    u = (unit or "").lower()
    if not any(h in u for h in _COUNT_UNIT_HINTS):
        return SanityCheck("non_negative_count", False, True,
                           f"Unit {unit!r} is not a count; check not applicable.")
    leaves = _numeric_leaves(value)
    negatives = [v for v in leaves if v < 0]
    return SanityCheck(
        "non_negative_count", True, not negatives,
        "All counts >= 0." if not negatives else f"{len(negatives)} negative count(s): {negatives[:5]}")


@lru_cache(maxsize=1)
def _ledger_totals():
    """The global debit=credit identity enforce_journal_balanced guarantees
    (business_dimensions.md 21). Computed once per process from immutable evidence."""
    from engine.evidence_loader import load_table, money
    jl = load_table("journal_lines")
    debit = float(money(jl["debit"]).fillna(0).sum())
    credit = float(money(jl["credit"]).fillna(0).sum())
    return round(debit, 2), round(credit, 2)


def check_ledger_balanced(source_objects):
    """8: 'debit=credit balance identities for ledger sub-totals'. Applies to every
    ledger-derived metric. A violation means the execution engine mis-read journal_lines --
    it must halt, because every ledger metric downstream would be wrong."""
    if "journal_lines" not in (source_objects or ""):
        return SanityCheck("ledger_debit_credit_identity", False, True,
                           "Metric is not ledger-derived; check not applicable.")
    debit, credit = _ledger_totals()
    ok = abs(debit - credit) < 0.01
    return SanityCheck(
        "ledger_debit_credit_identity", True, ok,
        f"journal_lines total debit {debit:,.2f} vs credit {credit:,.2f} "
        f"(difference {abs(debit - credit):,.2f}).")


def check_grain_consistency(value, spec):
    """8: 'a grouped result's row count should not exceed the ungrouped population'. For a
    dict-valued (grouped) result, the number of groups can never exceed the number of source
    rows the grouping was built from. Where the source population is not cheaply knowable the
    check reports itself as not applicable rather than inventing a bound."""
    if not isinstance(value, dict):
        return SanityCheck("grain_consistency", False, True,
                           "Result is not grouped; check not applicable.")
    n_groups = len(value)
    population = _population_for(spec)
    if population is None:
        return SanityCheck(
            "grain_consistency", False, True,
            f"{n_groups} group(s); source population not cheaply determinable for this "
            f"metric, so no upper bound is asserted (stated rather than assumed).")
    return SanityCheck(
        "grain_consistency", n_groups <= population, n_groups <= population,
        f"{n_groups} group(s) vs source population {population} row(s).")


def _population_for(spec):
    """Row count of the metric's primary source table, from file_manifest.csv's own `rows`
    column -- the manifest is authoritative and already row-count-verified (Deliverable A), so
    this needs no table load."""
    from engine.evidence_loader import manifest
    primary = (spec.source_objects or "").split(",")[0].strip().split(";")[0].strip()
    if not primary:
        return None
    key = f"T.{primary}"
    try:
        rows = manifest()
    except Exception:
        return None
    for _, r in rows.iterrows():
        if str(r.get("key")) == key:
            try:
                return int(r.get("rows"))
            except (TypeError, ValueError):
                return None
    return None


# --- Live value reconciliation ----------------------------------------------------------------
#
# A validation_summary.csv row records what an OFFLINE reconstruction once matched; it says
# nothing about the value the calculator just produced. For the metrics below the Validator
# instead reads the exported reference rows and compares them with the live output, figure by
# figure. It still recomputes no business value: the reference is the exported view itself.

# One paisa, per month and per component. Both sides are rupee amounts to 2 decimals, so any
# real difference is at least this large and rounding alone never reaches it.
PNL_MONTHLY_TOLERANCE_INR = 0.01
_PNL_COMPONENTS = ("revenue", "expenses", "net_profit")


def reconcile_pnl_by_month(value, tolerance=PNL_MONTHLY_TOLERANCE_INR):
    """M.PNL.001 against v_pnl (F.001), month by month.

    v_pnl is exported at (property_id, month) grain with month = date_trunc('month', entry_date)
    written YYYY-MM-01 -- the same month key the calculator emits. Its rows are summed per month
    (property and no-property rows alike), then revenue, expenses and net profit are compared for
    every month in either side. Returns (status, detail) where status is MATCH or DIFFERS.
    """
    from engine.evidence_loader import load_view
    ref = load_view("v_pnl")
    ref = ref.assign(_month=ref["month"].astype(str).str[:10])
    reference = ref.groupby("_month")[list(_PNL_COMPONENTS)].sum()
    produced = value if isinstance(value, dict) else {}

    months = sorted(set(reference.index) | set(produced))
    mismatches, worst = [], 0.0
    for month in months:
        if month not in produced:
            mismatches.append(f"{month}: missing from the calculator output")
            continue
        if month not in reference.index:
            mismatches.append(f"{month}: not present in v_pnl")
            continue
        for component in _PNL_COMPONENTS:
            diff = float(produced[month].get(component, float("nan"))) - float(reference.at[month, component])
            if not abs(diff) <= tolerance:
                mismatches.append(f"{month} {component}: differs by {diff:,.2f}")
            if abs(diff) > worst:
                worst = abs(diff)

    totals_produced = {c: round(sum(float(v.get(c, 0.0)) for v in produced.values()), 2)
                       for c in _PNL_COMPONENTS}
    totals_reference = {c: round(float(reference[c].sum()), 2) for c in _PNL_COMPONENTS}
    return ("MATCH" if not mismatches else "DIFFERS"), {
        "months_compared": len(months), "months_mismatched": len({m.split(" ")[0].rstrip(":") for m in mismatches}),
        "mismatches": mismatches, "max_abs_difference": round(worst, 2),
        "totals_produced": totals_produced, "totals_reference": totals_reference,
        "tolerance": tolerance,
    }


def _pnl_monthly_verdict(metric_id, value, checks):
    status, d = reconcile_pnl_by_month(value)
    ref_rev = d["totals_reference"]["revenue"]
    gap = abs(d["totals_produced"]["revenue"] - ref_rev)
    if status == "MATCH":
        explanation = (f"All {d['months_compared']} months match v_pnl (F.001) on revenue, expenses "
                       f"and net profit within Rs.{d['tolerance']:.2f} per figure, compared value by "
                       f"value against the exported rows.")
    else:
        shown = "; ".join(d["mismatches"][:6]) + (" ..." if len(d["mismatches"]) > 6 else "")
        explanation = (f"{d['months_mismatched']} of {d['months_compared']} months differ from v_pnl "
                       f"(F.001) beyond Rs.{d['tolerance']:.2f}: {shown}")
    return ValidationVerdict(
        metric_id=metric_id, status=status,
        reconstructed_value=str(d["totals_produced"]),
        reference_value=str(d["totals_reference"]),
        absolute_difference=f"{d['max_abs_difference']:.2f}",
        percentage_difference=(f"{gap / abs(ref_rev) * 100:.4f}" if ref_rev else ""),
        reference_source="F.001 v_pnl, summed per month, compared month by month",
        check_ids=("PNL.MONTHLY.F001",),
        explanation=explanation,
        sanity_checks=checks,
    )


LIVE_REFERENCE_CHECKS = {
    "M.PNL.001": _pnl_monthly_verdict,
}


# --- Comparable stored references ---------------------------------------------------------------
#
# A validation_summary.csv row may decide a live result's status ONLY through an entry below.
# Each entry names the stored check, the exact part of the live value it measures (the value
# selector) and what kind of figure it is. An entry exists only where the stored reference is the
# same definition, unit, time basis and grain as that live value, and measures the same kind of
# thing (amount against amount, count against count).
#
# Every other stored row mapped to a metric -- row counts, format checks, identity checks, drift
# counts, a different formula, a different grain -- is SUPPORTING EVIDENCE. It is reported in the
# explanation and can never set MATCH or DIFFERS.
#
# Tolerances: an INR amount must agree within one paisa (Rs.0.01), because both sides are rupee
# amounts to two decimals and rounding alone never reaches a paisa. A count must agree exactly.

TOLERANCE_INR = 0.01
KIND_INR = "INR"
KIND_COUNT = "COUNT"


@dataclass(frozen=True)
class ReferenceCheck:
    check_id: str        # the validation_summary.csv row
    kind: str            # KIND_INR | KIND_COUNT
    selector: tuple      # () = the whole scalar value; ("key",) = value["key"]; ("sum", k1, ...)


def _ref(check_id, kind, *selector):
    return ReferenceCheck(check_id, kind, tuple(selector))


_PNL_BUCKETS = ("owner_rent", "maintenance", "housekeeping", "utilities", "property_ops",
                "administrative", "salaries", "marketing", "other_expenses")

# (metric_id, definition key) -> (comparable checks, leaves derived from compared leaves).
# The definition key is the letter/numeral after "Def" in the result's label ("Def A", "Def ii"),
# or None for a single-definition metric. A family definition is validated only by a reference
# for THAT definition; nothing is stamped across the whole family.
COMPARABLE_REFERENCES = {
    ("M.REV.001", None): ((_ref("REV.01", KIND_INR),), ()),
    ("M.COL.001", None): ((_ref("COLL.01", KIND_INR, "total"),), ()),
    ("M.AR.001A", "A"): ((_ref("AR.01", KIND_INR),), ()),
    ("M.AR.001B", "B"): ((_ref("AR.02", KIND_INR, "ar_balance"),), ()),
    ("M.AR.001D", "D"): ((_ref("AR.04a", KIND_INR, "unclipped"),), ()),
    ("M.DEP.001", None): ((_ref("DEP.01", KIND_INR),), ()),
    ("M.DEP.002", None): ((_ref("DEP.03", KIND_INR, "refund_amount_total"),), ()),
    ("M.EXP.001", None): ((_ref("EXP.01", KIND_INR),), ()),
    ("M.EXP.002", None): ((_ref("EXP.02", KIND_INR, "sum", *_PNL_BUCKETS),
                           _ref("EXP.03", KIND_INR, "electricity")), ()),
    # PROFIT.03 is owner_payments COALESCE(escalated, base) WHERE status IN (paid, pending) -- this
    # metric's own definition. OWNPAY.01 sums ALL rows, a different filter, so it only supports.
    ("M.OWN.001", None): ((_ref("PROFIT.03", KIND_INR),), ()),
    ("M.OWN.002", "ii"): ((_ref("PROFIT.04", KIND_INR),), ()),
    ("M.OWN.002", "iii"): ((_ref("PROFIT.03", KIND_INR),), ()),
    ("M.PROFIT.001", "A"): ((_ref("PROFIT.01", KIND_INR),), ()),
    ("M.OCC.001", "A"): ((_ref("OCC.02", KIND_COUNT, "occupied"),
                          _ref("OCC.01", KIND_COUNT, "total")), ("occupancy_pct",)),
    ("M.OCC.001", "B"): ((_ref("OCC.06", KIND_COUNT, "occupied"),
                          _ref("OCC.01", KIND_COUNT, "total")), ("occupancy_pct",)),
    ("M.OCC.001", "C"): ((_ref("OCC.07", KIND_COUNT, "occupied"),
                          _ref("OCC.07b", KIND_COUNT, "total")), ("occupancy_pct",)),
    ("M.OCC.001", "D"): ((_ref("OCC.08", KIND_COUNT, "occupied"),
                          _ref("OCC.08b", KIND_COUNT, "total")), ("occupancy_pct",)),
    ("M.TEN.001", None): ((_ref("OCC.13", KIND_COUNT),), ()),
    ("M.TEN.002", None): ((_ref("OCC.14", KIND_COUNT),), ()),
    # MAINT.06 is the live ticket-row count; MAINT.01 is the view's 1,613, which double-counts two
    # tickets through a join, so it only supports.
    ("M.MAINT.001", None): ((_ref("MAINT.06", KIND_COUNT),), ()),
    ("M.MAINT.002", None): ((_ref("MAINT.02", KIND_INR, "path_a_total"),
                             _ref("MAINT.04", KIND_INR, "path_b_total")), ()),
    ("M.RISK.004", None): ((_ref("DEP.06", KIND_COUNT, "allotment_count"),), ()),
    ("M.RISK.005", None): ((_ref("DQ.013", KIND_COUNT, "duplicate_groups"),
                            _ref("DQ.013b", KIND_COUNT, "excess_rows")), ()),
    ("M.RISK.007", None): ((_ref("DQ.003", KIND_COUNT),), ()),
}

_DEFINITION_KEY = re.compile(r"\bDef\s+(iii|ii|i|[A-Z])\b")


def definition_key(label):
    """"Tenant dues -- Def B: ..." -> "B"; "Def ii (ledger ...)" -> "ii"; no "Def" -> None."""
    match = _DEFINITION_KEY.search(str(label or ""))
    return match.group(1) if match else None


def _as_number(text):
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def _select(value, selector):
    """The part of the live value a reference measures, or None if the value does not hold it."""
    def num(v):
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    if not selector:
        return num(value)
    if not isinstance(value, dict):
        return None
    if selector[0] == "sum":
        parts = [num(value.get(k)) for k in selector[1:]]
        return None if any(p is None for p in parts) else sum(parts)
    return num(value.get(selector[0]))


def _numeric_keys(value):
    if not isinstance(value, dict):
        return set()
    return {k for k, v in value.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


class Validator:
    """The Validator role. Holds no business logic of its own -- it compares what the Executor
    produced against what validation_summary.csv already proved, and runs 8's structural
    checks. It never recomputes a business value. For metrics in LIVE_REFERENCE_CHECKS it
    compares the live value itself against the exported reference rows."""

    def __init__(self, index: ValidationIndex = None):
        self.index = index or ValidationIndex()

    def validate(self, spec, value, unit, halt_on_sanity_failure=True,
                 definition_label=None) -> ValidationVerdict:
        checks = (
            check_finite(value),
            check_non_negative_count(value, unit),
            check_ledger_balanced(spec.source_objects if spec is not None else ""),
            check_grain_consistency(value, spec) if spec is not None else
                SanityCheck("grain_consistency", False, True, "No spec supplied."),
        )
        failed = [c for c in checks if c.applicable and not c.passed]
        if failed and halt_on_sanity_failure:
            raise SanityCheckFailure(
                f"{getattr(spec, 'metric_id', '<unknown>')}: "
                + "; ".join(f"{c.name}: {c.detail}" for c in failed)
                + " -- analytics_execution_spec.md 8 requires this halt rather than emitting "
                  "a result that failed an internal sanity check."
            )

        metric_id = getattr(spec, "metric_id", "")
        live_check = LIVE_REFERENCE_CHECKS.get(metric_id)
        if live_check is not None:
            return live_check(metric_id, value, checks)

        return self._compare_stored(metric_id, definition_key(definition_label), value, checks)

    def _compare_stored(self, metric_id, def_key, value, checks):
        """Compare the live value with the comparable stored references for this definition.

        MATCH or DIFFERS is set only by a comparison actually made here, on the live value, through
        an entry in COMPARABLE_REFERENCES. Stored rows without such an entry are supporting
        evidence. A definition whose numeric parts are only partly covered is PARTIAL, and the
        uncompared parts are named.
        """
        supporting = tuple(r.metric_id for r in self.index.rows_for(metric_id))
        entry = COMPARABLE_REFERENCES.get((metric_id, def_key))

        def unverified(reason):
            return ValidationVerdict(
                metric_id=metric_id, status="UNVERIFIED",
                reconstructed_value=str(value), reference_value="",
                absolute_difference="", percentage_difference="",
                reference_source="", check_ids=(),
                explanation=reason + (
                    f" Stored checks {', '.join(supporting)} remain supporting evidence only: "
                    f"they do not measure this definition's live value (a count, a format or "
                    f"identity check, a different formula or a different grain)."
                    if supporting else ""),
                sanity_checks=checks,
            )

        if entry is None:
            return unverified(
                "Not compared: no reference of the same definition, unit, time basis and grain "
                "is wired to this value, so it is calculated from the records but not "
                "independently checked.")
        if value is None:
            return unverified("Not compared: the calculation produced no value.")

        refs, derived = entry
        compared, failures, covered, sources = [], [], set(), []
        worst, worst_ref = 0.0, None
        for rc in refs:
            row = self.index.row(rc.check_id)
            live = _select(value, rc.selector)
            reference = _as_number(row.reference_value) if row is not None else None
            if live is None or reference is None:
                continue
            diff = live - reference
            ok = (abs(diff) <= TOLERANCE_INR if rc.kind == KIND_INR
                  else float(live) == float(reference))
            where = rc.selector[0] if len(rc.selector) == 1 else (
                "sum of named parts" if rc.selector else "value")
            compared.append((rc.check_id, where, live, reference))
            sources.append(f"{rc.check_id}: {row.reference_source}")
            if len(rc.selector) == 1:
                covered.add(rc.selector[0])
            if not ok:
                failures.append(f"{rc.check_id} {where}: live {live:,.2f} vs reference "
                                f"{reference:,.2f}")
            if abs(diff) >= worst:
                worst, worst_ref = abs(diff), reference

        if not compared:
            return unverified("Not compared: the wired reference value is not available.")

        uncovered = sorted(_numeric_keys(value) - covered - set(derived)) if refs and any(
            rc.selector for rc in refs) else []
        rule = f"INR within Rs.{TOLERANCE_INR:.2f}, counts exact"
        done = "; ".join(f"{cid} ({where}) {live:,.2f} = {ref:,.2f}" if not any(
            f.startswith(cid) for f in failures) else f"{cid} ({where}) {live:,.2f} vs {ref:,.2f}"
            for cid, where, live, ref in compared)
        if failures:
            status = "DIFFERS"
            explanation = f"Compared with the live value ({rule}) and differs: {'; '.join(failures)}."
        elif uncovered:
            status = "PARTIAL"
            explanation = (f"Compared with the live value ({rule}): {done}. Not compared: "
                           f"{', '.join(uncovered)} (no reference of the same definition).")
        else:
            status = "MATCH"
            explanation = f"Compared with the live value ({rule}): {done}."
        return ValidationVerdict(
            metric_id=metric_id, status=status,
            reconstructed_value="; ".join(f"{w}={l:.2f}" for _, w, l, _ in compared),
            reference_value="; ".join(f"{w}={r:.2f}" for _, w, _, r in compared),
            absolute_difference=f"{worst:.2f}",
            percentage_difference=(f"{worst / abs(worst_ref) * 100:.4f}"
                                   if worst_ref not in (None, 0) else ""),
            reference_source="; ".join(sources),
            check_ids=tuple(cid for cid, _, _, _ in compared),
            explanation=explanation,
            sanity_checks=checks,
        )
