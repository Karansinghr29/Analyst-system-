"""
dimension_resolver.py -- grain protection (ai_analytics_architecture.md 6) and dimension
validation against business_dimensions.md's catalogued dimensions.

Validates a requested {dimension: value} filter set against a metric's documented grain BEFORE
execution -- a filter the metric's grain does not support is rejected here, not silently
dropped or silently applied by the calculator.
"""
from dataclasses import dataclass

from engine.semantic_registry import MetricSpec

# Dimensions proven degenerate in this exported dataset (business_dimensions.md 2-3):
# exactly 1 organization, 1 property. A filter/group-by on these is structurally meaningless
# here -- not an error in the request, but a fact about the data that must be disclosed,
# per question_understanding_spec.md 4.2.
DEGENERATE_DIMENSIONS = {"organization_id", "property_id"}

KNOWN_DIMENSIONS = {
    "organization_id", "property_id", "apartment_id", "bed_id", "tenant_id", "allotment_id",
    "staying_status", "invoice_id", "invoice_type", "receipt_id", "receipt_type",
    "deposit_settlement_id", "expense_category", "account_code", "owner_id",
    "owner_payment_id", "maintenance_ticket_id", "issue_type_id", "billing_month",
    "journal_entry_id", "source_table", "month",
}


class UnsupportedDimensionError(Exception):
    pass


class DegenerateDimensionError(Exception):
    """The dimension exists and is well-formed, but this exported dataset has only 1 distinct
    value for it -- a comparison/grouping request is answered with this fact, not a computed
    (spuriously single-row) ranking. question_understanding_spec.md 4.2."""


@dataclass(frozen=True)
class ResolvedDimensions:
    filters: dict          # dimension -> value, confirmed compatible with the metric's grain
    group_by: tuple         # dimensions to group by, confirmed compatible
    degenerate_used: tuple  # any degenerate dimensions referenced (informational, not fatal
                             # unless used for a COMPARISON -- see resolve_for_comparison)


_NEGATIVE_PHRASES = ("not applicable", "not carried", "aggregated away", "not natively")

_GRAIN_KEY_ALIASES = {
    "organization_id": "org", "property_id": "property",
    "tenant_id": "tenant/allotment", "allotment_id": "tenant/allotment",
    "bed_id": "tenant/allotment",
}


def _grain_supports(spec: MetricSpec, dimension):
    """Parses spec.grain's semicolon-separated 'key=value' clauses (the format
    'org=organization_id; property=...; tenant/allotment=...' used throughout
    semantic_metric_registry.csv) and checks whether the CLAUSE FOR THIS DIMENSION says
    something other than one of the negative phrases above. A naive whole-string substring
    match would incorrectly match dimension names that appear ONLY inside a negative clause
    (e.g. 'tenant/allotment=Not applicable' contains the substring 'tenant') -- this parses
    per-clause specifically to avoid that false positive, found and fixed while testing."""
    key = _GRAIN_KEY_ALIASES.get(dimension, dimension.replace("_id", ""))
    for clause in spec.grain.split(";"):
        clause = clause.strip()
        if "=" not in clause:
            continue
        ckey, cval = clause.split("=", 1)
        if ckey.strip().lower() == key.lower():
            cval_l = cval.strip().lower()
            return not any(neg in cval_l for neg in _NEGATIVE_PHRASES)
    # Fallback: dimension not named as a grain clause at all (e.g. account_code, billing_month
    # on financial metrics) -- consult the `dimensions` column the same way, clause-unaware
    # (that column is a flat list, not key=value pairs).
    d = spec.dimensions.lower()
    return dimension.lower().replace("_id", "") in d or dimension in d


def resolve(spec: MetricSpec, filters=None, group_by=None):
    filters = filters or {}
    group_by = tuple(group_by or ())

    for dim in list(filters) + list(group_by):
        if dim not in KNOWN_DIMENSIONS:
            raise UnsupportedDimensionError(
                f"{dim!r} is not a catalogued dimension (business_dimensions.md). "
                f"Not determinable from exported evidence."
            )
        if not _grain_supports(spec, dim):
            raise UnsupportedDimensionError(
                f"{spec.metric_id}'s grain ({spec.grain}) does not document support for "
                f"dimension {dim!r}. Refusing to apply an undocumented filter/grouping."
            )

    degenerate = tuple(d for d in list(filters) + list(group_by) if d in DEGENERATE_DIMENSIONS)
    return ResolvedDimensions(filters=filters, group_by=group_by, degenerate_used=degenerate)


def resolve_for_comparison(spec: MetricSpec, compare_dimension):
    """Special-cased per question_understanding_spec.md 4.2: a request to COMPARE ACROSS a
    degenerate dimension (e.g. 'which property performs best') must fail with the specific,
    informative DegenerateDimensionError, not a generic resolve()."""
    if compare_dimension in DEGENERATE_DIMENSIONS:
        raise DegenerateDimensionError(
            f"Only 1 distinct value of {compare_dimension!r} exists in the exported data "
            f"(business_dimensions.md). There is nothing to compare."
        )
    return resolve(spec, group_by=(compare_dimension,))
