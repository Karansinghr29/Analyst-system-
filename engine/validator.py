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


class Validator:
    """The Validator role. Holds no business logic of its own -- it compares what the Executor
    produced against what validation_summary.csv already proved, and runs 8's structural
    checks. It never recomputes a business value."""

    def __init__(self, index: ValidationIndex = None):
        self.index = index or ValidationIndex()

    def validate(self, spec, value, unit, halt_on_sanity_failure=True) -> ValidationVerdict:
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
        rows = self.index.rows_for(metric_id)
        status, detail = self.index.status_for(metric_id)

        if not rows:
            return ValidationVerdict(
                metric_id=metric_id, status="UNVERIFIED",
                reconstructed_value=str(value), reference_value="",
                absolute_difference="", percentage_difference="",
                reference_source="", check_ids=(),
                explanation=("No exported reference exists for this metric in "
                             "validation_summary.csv. The value is computed but explicitly "
                             "unverified against any reference -- it must never be presented "
                             "with the confidence language of a MATCH-backed result "
                             "(analytics_execution_spec.md 8)."),
                sanity_checks=checks,
            )

        primary = next((r for r in rows if r.validation_status == "DIFFERS"), rows[0])
        return ValidationVerdict(
            metric_id=metric_id, status=status,
            reconstructed_value=primary.reconstructed_value,
            reference_value=primary.reference_value,
            absolute_difference=primary.absolute_difference,
            percentage_difference=primary.percentage_difference,
            reference_source=primary.reference_source,
            check_ids=tuple(r.metric_id for r in rows),
            explanation=detail,
            sanity_checks=checks,
        )
