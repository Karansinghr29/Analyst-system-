"""
dimension_resolution.py -- Phase 3, stage [3]. question_understanding_spec.md 4.

This module is the QUESTION-level layer only: it extracts dimension references from a question
and hands them to the existing Phase 1 `engine.dimension_resolver` for grain validation. It
deliberately does NOT reimplement grain checking, the degenerate-dimension guard, or the
KNOWN_DIMENSIONS catalogue -- those already exist and are already tested, and duplicating them
would create two sources of truth that could drift.

Division of responsibility:
    dimension_resolver.py  (Phase 1)  -- IS this dimension valid for this metric's grain?
    dimension_resolution.py (Phase 3) -- WHICH dimensions is this question asking about?
"""
import re
from dataclasses import dataclass

from engine.dimension_resolver import (
    resolve as _resolve_grain,
    resolve_for_comparison as _resolve_comparison_grain,
    KNOWN_DIMENSIONS, DEGENERATE_DIMENSIONS,
    UnsupportedDimensionError, DegenerateDimensionError,
)

# Re-exported so callers need only this module for Phase 3 work.
__all__ = ["extract", "resolve_for_question", "KNOWN_DIMENSIONS", "DEGENERATE_DIMENSIONS",
           "UnsupportedDimensionError", "DegenerateDimensionError", "DimensionRequest"]


# Question phrases -> catalogued dimension keys. Every key here is already in
# dimension_resolver.KNOWN_DIMENSIONS (asserted by verify_dimension_vocabulary below), which is
# itself derived from business_dimensions.md. No new dimension is introduced.
_BREAKDOWN_PHRASES = {
    "by month": "month", "per month": "month", "monthly": "month", "each month": "month",
    "month by month": "month", "by category": "expense_category",
    "per category": "expense_category", "by expense category": "expense_category",
    "by property": "property_id", "per property": "property_id",
    "by tenant": "tenant_id", "per tenant": "tenant_id", "for each tenant": "tenant_id",
    "by bed": "bed_id", "per bed": "bed_id",
    "by apartment": "apartment_id", "per apartment": "apartment_id",
    "by account": "account_code", "per account": "account_code",
    "by status": "staying_status", "per status": "staying_status",
    "by owner": "owner_id", "per owner": "owner_id",
    "by billing month": "billing_month", "by issue type": "issue_type_id",
}

# Phrases that request a COMPARISON ACROSS a dimension's values -- the case
# question_understanding_spec.md 4.2 requires be caught at dimension resolution when the
# dimension is degenerate ("which property is best").
_COMPARISON_PHRASES = {
    "which property": "property_id", "what property": "property_id",
    "best property": "property_id", "worst property": "property_id",
    "across properties": "property_id", "compare properties": "property_id",
    "which organization": "organization_id", "across organizations": "organization_id",
    "which tenant": "tenant_id", "which apartment": "apartment_id", "which bed": "bed_id",
    "which category": "expense_category", "which account": "account_code",
}

_STAYING_STATUSES = ("staying", "on-notice", "on notice", "booked", "exited", "cancelled")

# Words that follow "tenant" in a CONCEPT name rather than in a reference to one tenant.
# "tenant dues" names a measure; "tenant Sharma" names a person. Without this distinction the
# entity detector fires on the concept itself -- which happens whenever a follow-up is expanded
# with the concept name ("why did tenant dues change?") and produces a nonsensical clarification
# asking the owner to identify the tenant they never mentioned.
#
# Also: question_normalize may stem plurals ("tenants" -> "tenant"), so concept phrases like
# "how much do tenants owe" become "how much do tenant owe". "owe" must not be treated as a
# tenant name.
_CONCEPT_NOUNS = (
    "dues|lifecycle|count|counts|status|statuses|transactions|allotment|"
    "allotments|balance|balances|ledger|activity|record|records|data|"
    "numbers|figures|owe|owes|owing|owed|receivable|receivables|arrears|"
    "risk|risks|aging|ageing|list|lists|total|totals|amount|amounts|"
    "are|is|was|were|have|has|do|does|on|still|need|needs"
)


@dataclass(frozen=True)
class DimensionRequest:
    """What the QUESTION asked for, before grain validation."""
    filters: dict            # dimension -> value
    group_by: tuple          # requested breakdown dimensions
    compare_across: str       # a dimension the question wants to rank/compare across, or ""
    unresolved_entities: tuple  # entity references present but not resolvable to a row key
    matched_phrases: tuple


def extract(question):
    """Deterministic dimension extraction from question text. Returns a DimensionRequest.
    Never guesses an entity: an unresolvable reference is recorded in `unresolved_entities`
    (question_understanding_spec.md 4.3 -- 'never a fuzzy/partial name match that could
    silently resolve to the wrong entity')."""
    q = (question or "").lower()
    # "monthly rent" is the recorded amount's own name (the source column is monthly_rental),
    # not a request to break rent down by month. Left in place it produced a month grouping on
    # a metric with no month grain, and the owner got a dimension rejection for asking a plain
    # question. "monthly revenue" keeps its meaning -- there the word does ask for the series.
    q = q.replace("monthly rent", " rent ").replace("monthly rental", " rent ")
    filters, group_by, matched = {}, [], []

    compare_across = ""
    for phrase, dim in _COMPARISON_PHRASES.items():
        if phrase in q:
            compare_across = dim
            matched.append(phrase)
            break

    for phrase, dim in _BREAKDOWN_PHRASES.items():
        if phrase in q and dim not in group_by:
            group_by.append(dim)
            matched.append(phrase)

    for status in _STAYING_STATUSES:
        if re.search(r"(?<![a-z])" + re.escape(status) + r"(?![a-z])", q):
            canonical = {"on notice": "On-Notice", "on-notice": "On-Notice"}.get(
                status, status.capitalize())
            filters["staying_status"] = canonical
            matched.append(status)
            break

    # Entity references the exported evidence cannot resolve to a row key. 27 PII columns are
    # excluded from the export (data_inventory.md), so a tenant named in a question generally
    # CANNOT be identified -- that is NOT_DETERMINABLE, not a best-guess match (4.3).
    # A COMPARISON across an entity dimension ("which tenant owes the most?") is a RANKING
    # request, not a reference to one specific entity. It needs no entity resolution -- and
    # treating it as one would ask the user to name the very tenant they are asking us to find.
    unresolved = []
    if not is_ranking_request(q, compare_across):
        # An apartment IS identifiable from the export: apartment_code is a non-PII column, so
        # a code the question names can be checked against the actual apartments rather than
        # guessed at. This is the one entity reference 4.3's PII argument does not cover -- and
        # resolving it is what lets a question about one apartment be answered as one rather
        # than silently widened to the estate.
        apartment = resolve_apartment_code(question)
        if apartment:
            filters["apartment_id"] = apartment
            matched.append(apartment)

        if not apartment and names_unknown_apartment(question):
            unresolved.append("apartment_id")

        for pat, kind in ((r"\bthis tenant\b", "tenant_id"),
                          (r"\btenant (?!" + _CONCEPT_NOUNS + r")[a-z]+\b", "tenant_id"),
                          (r"\bbed [a-z0-9-]+\b", "bed_id"),
                          (r"\bapartment [a-z0-9-]+\b", "apartment_id")):
            if kind == "apartment_id" and apartment:
                continue          # resolved above; not an unresolvable reference
            if re.search(pat, q):
                unresolved.append(kind)
    # De-duplicate while preserving order.
    seen, uniq = set(), []
    for u in unresolved:
        if u not in seen:
            seen.add(u)
            uniq.append(u)

    return DimensionRequest(
        filters=filters, group_by=tuple(group_by), compare_across=compare_across,
        unresolved_entities=tuple(uniq), matched_phrases=tuple(matched),
    )


# An apartment code as the export writes it: a letter, two digits, an optional trailing letter
# (D13A, D23B). The shape narrows the search; membership in the exported set is what decides.
_APARTMENT_TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]\d{2}[A-Za-z]?)(?![A-Za-z0-9])")


def _known_apartment_codes():
    from engine.calculators.rent import known_apartment_codes

    return known_apartment_codes()


def resolve_apartment_code(question):
    """The apartment a question names, verified against the exported apartments. "" for none.

    Never a partial or fuzzy match: a token that looks like a code but is not one of the codes
    the export contains resolves to nothing, and the caller refuses rather than picking the
    nearest. That is the same rule 4.3 applies to tenants, held to here even though apartment
    codes are not PII-excluded and CAN be resolved.
    """
    known = _known_apartment_codes()
    for match in _APARTMENT_TOKEN.finditer(question or ""):
        token = match.group(1).upper()
        if token in known:
            return token
    return ""


def unknown_apartment_token(question):
    """The apartment-shaped token a question names that no apartment matches. "" if none.

    This is the difference between refusing and quietly widening. "What is the rent for Z99?"
    names one apartment; with no such apartment the honest reply is that it is not in the
    records -- not the estate-wide rent list, which answers a question nobody asked. The token
    is returned so the refusal can name it, rather than asking the owner to be more specific
    about something they were already specific about.
    """
    known = _known_apartment_codes()
    for match in _APARTMENT_TOKEN.finditer(question or ""):
        token = match.group(1).upper()
        if token not in known:
            return token
    return ""


def names_unknown_apartment(question):
    """True when the question names something shaped like an apartment that does not exist."""
    return bool(unknown_apartment_token(question))


def is_ranking_request(question_lower, compare_across=""):
    """True when the question asks WHICH entity ranks highest, rather than naming a specific
    one. A ranking is answered at the entity grain over all entities; it resolves no single
    entity and therefore triggers no entity-identity clarification."""
    if compare_across:
        return True
    return any(p in question_lower for p in
               ("which tenant", "which bed", "which apartment", "which owner",
                "top tenant", "highest", "the most", "the largest"))


def resolve_for_question(spec, request: DimensionRequest):
    """Validate an extracted DimensionRequest against a metric's grain, by DELEGATING to the
    Phase 1 resolver. Returns (ResolvedDimensions, problems, degenerate_comparison_reason).

    Refusals are returned rather than raised so the planner can turn each into the correct plan
    status -- a degenerate comparison becomes NOT_DETERMINABLE with the specific 'only 1
    property exists' statement (4.2), an unsupported dimension becomes REJECTED.
    """
    problems, degenerate_reason = [], ""

    if request.compare_across:
        try:
            _resolve_comparison_grain(spec, request.compare_across)
        except DegenerateDimensionError as e:
            degenerate_reason = str(e)
        except UnsupportedDimensionError as e:
            problems.append(str(e))

    try:
        resolved = _resolve_grain(spec, filters=dict(request.filters),
                                  group_by=request.group_by)
    except (UnsupportedDimensionError, DegenerateDimensionError) as e:
        problems.append(str(e))
        resolved = None

    return resolved, tuple(problems), degenerate_reason


def verify_dimension_vocabulary():
    """Exit criterion: 'every dimension reference resolves to business_dimensions.md'. Every
    dimension key this module can emit must already be catalogued by the Phase 1 resolver
    (whose KNOWN_DIMENSIONS is derived from business_dimensions.md). Returns problems."""
    problems = []
    for phrase, dim in list(_BREAKDOWN_PHRASES.items()) + list(_COMPARISON_PHRASES.items()):
        if dim not in KNOWN_DIMENSIONS:
            problems.append(f"phrase {phrase!r} maps to {dim!r}, which is not a catalogued "
                            f"dimension in business_dimensions.md")
    if "staying_status" not in KNOWN_DIMENSIONS:
        problems.append("staying_status is not catalogued")
    return problems
