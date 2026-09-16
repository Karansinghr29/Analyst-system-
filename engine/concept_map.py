"""
concept_map.py -- Phase 3. The concept-to-metric-family lookup artifact that
question_understanding_spec.md 3.2 explicitly REQUIRES to exist:

    "The resolver must always check semantic_layer.md's concept groupings before finalizing a
     resolution -- a concept-to-metric-family mapping table, derived directly from
     semantic_layer.md's own section structure, is the required lookup artifact."

Two rules govern everything in this file:

1. **No business content is defined here.** Every entry maps a natural-language CONCEPT PHRASE
   to `metric_id`s that already exist in semantic_metric_registry.csv. The metrics' meanings,
   filters, grains, and trust levels all continue to come from the registry at runtime. This
   table is an index, not a definition. `verify_against_registry()` fails loudly if any
   metric_id here is not in the registry.

2. **Family membership is mandatory.** Where semantic_layer.md documents a multi-definition
   concept, the concept maps to the WHOLE family. A resolver that returned M.AR.001A alone for
   "tenant dues" would commit the specification violation 3.2 names explicitly.

Matching is deterministic keyword/phrase matching over the question text -- NOT a language
model, NOT embeddings, NOT fuzzy scoring. Its failure mode is safe: an unmatched question
resolves to zero concepts and returns NOT_DETERMINABLE rather than guessing a nearby metric
(3.1 step 5). Callers that DO have a language model (Phase 4) are expected to bypass the
phrase matcher and call `concept(name)` / the planner's structured entry point directly.
"""
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Concept:
    name: str
    metric_ids: tuple           # the WHOLE family where one exists
    is_family: bool
    family_rule: str            # why (or why not) this is a family
    phrases: tuple              # deterministic trigger phrases
    alternatives: tuple = ()    # related-but-distinct metrics to disclose, not merge
    note: str = ""
    domain: str = ""
    # Dimensions the metric's OWN definition already delivers, so a question asking for that
    # breakdown is satisfied by the metric itself rather than by an extra GROUP BY. M.EXP.002's
    # semantic_name is literally "Expenses by category" -- re-applying expense_category as an
    # additional grouping dimension would be an undocumented regrouping of an already-grouped
    # metric, which dimension_resolver.py correctly refuses.
    delivers_breakdown: tuple = ()
    # Filters the metric's OWN definition already applies. M.TEN.001's semantic_name is
    # "Staying tenants" -- the staying_status filter IS the metric, so re-applying it as a
    # user filter would be an undocumented refiltering of an already-filtered metric.
    delivers_filter: tuple = ()
    # More specific concepts that supersede this one when both match. "How many tenants are on
    # notice?" matches the generic "how many tenants" AND the specific "on notice"; the
    # specific reading is not an ambiguity to escalate, it is simply the correct one. Only
    # concepts naming a NARROWER subset of the same population may be listed here.
    superseded_by: tuple = ()


# The five family rows of question_understanding_spec.md 3.2, plus the single-metric concepts
# needed to cover the domains the Phase 3 brief enumerates. Family rows are marked and carry
# the spec's own justification text.
CONCEPTS = (
    # ---- Families (question_understanding_spec.md 3.2) -------------------------------------
    Concept(
        name="tenant_dues",
        metric_ids=("M.AR.001A", "M.AR.001B", "M.AR.001C", "M.AR.001D"),
        is_family=True,
        family_rule=("question_understanding_spec.md 3.2: 'Tenant dues / receivables / "
                     "outstanding dues -> M.AR.001A-D. Never resolve to M.AR.001A alone.'"),
        phrases=("tenant dues", "tenants owe", "tenant owe", "tenants owes", "tenant owes",
                 "owed by tenants", "receivable", "receivables", "outstanding dues", "dues",
                 "owe us", "owes the most", "owed to us", "how much do tenants owe", "arrears",
                 "tenants owing", "owing us", "outstanding from tenants", "stuck with tenants",
                 "tenants still need to pay", "tenants still owe", "money is stuck",
                 "still due from tenants", "due from tenants",
                 "money is still due from tenants", "money still due from tenants",
                 # Owner phrasings of the same family. "Days outstanding" stays aging's: the
                 # longer phrase wins the match, so this bare word does not capture it.
                 "owes us", "who owes", "outstanding", "tenant outstanding",
                 "tenants outstanding", "outstanding amount"),
        alternatives=("M.AR.002", "M.AR.003", "M.RISK.001"),
        note="Other grains of the same concept exist: M.AR.002 (by tenant), M.AR.003 (by "
             "property), M.RISK.001 (risk framing).",
        domain="Financial",
    ),
    Concept(
        name="occupancy",
        metric_ids=("M.OCC.001",),
        is_family=True,
        family_rule=("question_understanding_spec.md 3.2: 'Occupancy -> M.OCC.001 (which itself "
                     "represents 5+ definitions). Never resolve to one bare percentage.' The 5 "
                     "definitions live WITHIN one metric_id, so the family is internal."),
        phrases=("occupancy", "occupied", "how full", "vacancy", "vacant beds", "beds occupied",
                 "occupancy rate", "occupancy percentage"),
        alternatives=("M.OCC.002", "M.OCC.003", "M.OCC.004", "M.OCC.005"),
        note="Occupancy at other grains: M.OCC.002 (property), M.OCC.003 (apartment), "
             "M.OCC.004 (bed), M.OCC.005 (historical/day-weighted).",
        domain="Operations",
    ),
    Concept(
        name="profit",
        metric_ids=("M.PROFIT.001",),
        is_family=True,
        family_rule=("question_understanding_spec.md 3.2: 'Profit -> M.PROFIT.001 (3 "
                     "definitions within one metric_id). Never resolve to the ledger figure "
                     "silently.'"),
        phrases=("profit", "profitable", "net income", "bottom line", "earnings",
                 "net profit", "gross profit", "how much profit", "what profit"),
        note="3 competing definitions within one metric_id (ledger Def A, get_universal_metrics "
             "Def B omitting owner rent, v2 Def C owner-rent-inclusive).",
        domain="Financial",
    ),
    Concept(
        name="owner_rent",
        metric_ids=("M.OWN.002",),
        is_family=True,
        family_rule=("question_understanding_spec.md 3.2: 'Owner rent / owner-rent-in-profit -> "
                     "M.OWN.002 (3 definitions within one metric_id). Never resolve to one of "
                     "the three silently.'"),
        phrases=("owner rent", "rent paid to owners", "owner rent expense"),
        alternatives=("M.OWN.001",),
        note="M.OWN.001 (owner payments source total) is a related but distinct metric.",
        domain="Financial",
    ),
    Concept(
        name="collections",
        metric_ids=("M.COL.001", "M.COL.003"),
        is_family=False,
        family_rule=("question_understanding_spec.md 3.2: 'Collections -> M.COL.001 "
                     "(application) and M.COL.003 (ledger) -- related but genuinely distinct, "
                     "NOT one family; resolver must disclose both exist.' Because they are not "
                     "a documented family, this is DEFINITIONAL AMBIGUITY under 6 and requires "
                     "clarification rather than a SHOW_BOTH family plan."),
        phrases=("collections", "collected", "money collected", "cash collected",
                 "how much did we collect", "receipts collected", "collected amount",
                 "rent collected", "collection", "amount collected"),
        alternatives=("M.COL.002",),
        note="M.COL.002 is the monthly series of the application-level definition.",
        domain="Financial",
    ),

    # ---- Single-metric concepts -------------------------------------------------------------
    Concept(
        # "rent" and "rental" are deliberately NOT trigger phrases here. Rent is the amount
        # recorded against a bed's allotment (M.RENT.001); revenue is the ledger-derived figure.
        # They are not the same quantity and no registry metric equates them, so matching a bare
        # "what is typical rent?" to revenue answered a rent question with a revenue total. The
        # explicit compounds "rental income" and "rental revenue" DO name the ledger figure and
        # stay here; the `rent` concept below owns the rest.
        name="revenue",
        metric_ids=("M.REV.001",),
        is_family=False,
        family_rule="Single canonical ledger-derived definition; no competing definition exists.",
        phrases=("revenue", "turnover", "income", "top line", "sales", "how much revenue",
                 "earn", "earned", "we earn", "business earn", "what did we make",
                 "how much did we make", "money we made", "money did we make",
                 "money we make", "rental income", "rental revenue"),
        alternatives=("M.REV.002",),
        note="M.REV.002 is the same definition grouped by month.",
        domain="Financial",
    ),
    Concept(
        name="revenue_by_month",
        metric_ids=("M.REV.002",),
        is_family=False,
        family_rule="Monthly grouping of M.REV.001's single definition.",
        phrases=("revenue by month", "monthly revenue", "revenue trend", "revenue per month"),
        domain="Financial",
        delivers_breakdown=("month",),
    ),
    # The apartment the ledger already records on every posting. Same rows, same convention,
    # one level finer -- not a second definition of revenue, so not a family.
    Concept(
        name="revenue_by_apartment",
        metric_ids=("M.REV.003",),
        is_family=False,
        family_rule="Apartment grouping of M.REV.001's single definition.",
        phrases=("revenue by apartment", "apartment revenue", "revenue per apartment",
                 "which apartment generated the most revenue", "apartment generated",
                 "revenue for apartment", "revenue by flat", "income by apartment",
                 "highest earning apartment", "apartment earned", "earned by apartment"),
        alternatives=("M.REV.004",),
        note=("Part of recorded revenue is posted without an apartment. That part is reported "
              "separately and is never divided across apartments."),
        domain="Financial",
        delivers_breakdown=("apartment",),
    ),
    # One apartment's revenue over time. Separate from revenue_by_apartment because it answers a
    # different shape of question and needs the apartment named -- the estate by apartment AND by
    # month is a table, not an answer.
    Concept(
        name="apartment_revenue_by_month",
        metric_ids=("M.REV.004",),
        is_family=False,
        family_rule="Monthly grouping of M.REV.003, restricted to one named apartment.",
        phrases=("apartment revenue by month", "revenue by month for apartment",
                 "apartment revenue trend", "revenue history for apartment",
                 "monthly revenue for apartment", "apartment revenue over time",
                 "how did apartment revenue change"),
        note=("Reported for one apartment at a time. A month with no posting against that "
              "apartment is absent rather than shown as a zero."),
        domain="Financial",
        delivers_breakdown=("month",),
    ),
    Concept(
        name="expenses_by_apartment",
        metric_ids=("M.EXP.003",),
        is_family=False,
        family_rule="Apartment grouping of M.EXP.001's single definition.",
        phrases=("expenses by apartment", "apartment expenses", "expenses per apartment",
                 "expense for apartment", "costs by apartment", "apartment costs",
                 "spending by apartment"),
        domain="Financial",
        delivers_breakdown=("apartment",),
    ),
    # Rent that was in force in a past month, dated by the stay that carried it. Distinct from
    # M.RENT.001 (today's position) and from M.RENT.003 (the published card).
    Concept(
        name="historical_rent",
        metric_ids=("M.RENT.002",),
        is_family=False,
        family_rule="One recorded value per bed per past month; the stay dates it.",
        # "rent in" is deliberately absent. As a phrase it swallows "current rent in A12" --
        # the matcher drops the shorter "rent" as a substring of it -- and routes a question
        # about today's position to the historical metric.
        phrases=("rent last year", "rent was", "rent recorded for", "historical rent",
                 "past rent", "rent back then", "what rent was charged",
                 "rent at that time", "rent that month", "rent for that month",
                 "rent charged then"),
        note=("The rent recorded on the stay occupying the bed in that month. A rent revision "
              "made inside one stay is not recorded anywhere in the export."),
        domain="Financial",
    ),
    Concept(
        name="rate_card",
        metric_ids=("M.RENT.003",),
        is_family=False,
        family_rule="One published rate per bed type per dated range.",
        phrases=("rate card", "published rate", "listed rent", "list price", "advertised rent",
                 "standard rent", "rate for a single room", "rate by bed type"),
        note=("A published rate for a TYPE of bed, not what any tenant was charged."),
        domain="Financial",
    ),
    Concept(
        name="historical_occupancy",
        metric_ids=("M.OCC.005",),
        is_family=True,
        family_rule=("Two supported readings of 'occupied in a month' -- at any point, or on the "
                     "month's last covered day. Both are returned; neither is chosen."),
        # No month name appears here. A phrase naming one month would answer for that month and
        # silently fail for the other eleven; the period a question names is the time layer's
        # job, not the concept matcher's.
        phrases=("historical occupancy", "occupancy history", "occupancy last year",
                 "occupancy over time", "occupancy trend", "occupancy by month",
                 "monthly occupancy", "how did occupancy change", "occupancy each month",
                 "past occupancy", "occupancy was", "occupancy month by month"),
        note=("Reconstructed from the dates on each stay. The two readings differ for a bed that "
              "changed hands mid-month."),
        domain="Operations",
        delivers_breakdown=("month",),
    ),
    Concept(
        name="rent",
        metric_ids=("M.RENT.001",),
        is_family=False,
        family_rule=("Single recorded field with one definition. It is not a family: the several "
                     "rents inside one apartment are different BEDS, not competing definitions "
                     "of one figure."),
        phrases=("rent", "rents", "monthly rent", "rent amount", "rent for", "rent does",
                 "rent is", "bed rent", "rent charged", "rent per bed"),
        note=("Rent is recorded per bed on the occupying allotment. It is NOT revenue, invoice "
              "amount, amount paid, balance due, owner rent or deposit, and none of those may "
              "be substituted for it. It carries no effective date, so it answers the current "
              "position only."),
        domain="Financial",
    ),
    Concept(
        name="expenses",
        metric_ids=("M.EXP.001",),
        is_family=False,
        family_rule="Single canonical ledger-derived total; the P&L bucket gap (DQ.015) "
                    "affects M.EXP.002's categorisation, not this total (proven).",
        phrases=("expenses", "expense", "costs", "spending", "how much did we spend",
                 "cost base", "outgoings", "spend", "spent", "what did we spend"),
        alternatives=("M.EXP.002", "M.PNL.001"),
        note="M.EXP.002 breaks the same total down by category. M.PNL.001 exposes the "
             "ledger monthly expense series used for period-scoped expense questions.",
        domain="Financial",
    ),
    Concept(
        name="expenses_by_category",
        metric_ids=("M.EXP.002",),
        is_family=False,
        family_rule="Category breakdown of M.EXP.001.",
        phrases=("expenses by category", "expense categories", "cost breakdown",
                 "spending by category", "where does the money go"),
        domain="Financial",
        delivers_breakdown=("expense_category",),
    ),
    Concept(
        name="invoices",
        metric_ids=("M.INV.001",),
        is_family=False,
        family_rule="Single definition; DQ.001's internal drift is a per-invoice caveat.",
        phrases=("invoice", "invoices", "billed", "billing amount", "invoiced"),
        alternatives=("M.INV.002",),
        domain="Financial",
    ),
    Concept(
        name="deposits",
        metric_ids=("M.DEP.001",),
        is_family=False,
        family_rule="Deposit held is a single exact balance (DQ.011/012 do not downgrade it).",
        phrases=("deposit", "deposits", "security deposit", "deposit held",
                 "deposits held"),
        alternatives=("M.DEP.002", "M.DEP.003", "M.RISK.003", "M.RISK.004"),
        note="Settlements (M.DEP.002), refunds (M.DEP.003) and deposit risk (M.RISK.003/004) "
             "are separate metrics.",
        domain="Financial",
    ),
    Concept(
        name="deposit_settlements",
        metric_ids=("M.DEP.002",),
        is_family=False,
        family_rule="Single definition, DISCLOSE via the C.016 settlement 2x pattern.",
        phrases=("deposit settlement", "deposit settlements", "settled deposits",
                 "deposit refund", "deposit refunds"),
        domain="Financial",
    ),
    Concept(
        name="owner_payments",
        metric_ids=("M.OWN.001",),
        is_family=False,
        family_rule="Source-total definition; distinct from the 3-definition owner-rent bucket.",
        phrases=("owner payment", "owner payments", "paid to owners", "payouts to owners",
                 "owner payout", "pay owners", "paid owners", "pay the owners"),
        alternatives=("M.OWN.002",),
        domain="Financial",
    ),
    Concept(
        name="cash",
        metric_ids=("M.CASH.001",),
        is_family=False,
        family_rule="Single running-total definition.",
        phrases=("cash", "cash balance", "bank balance", "how much cash", "liquidity"),
        domain="Financial",
    ),
    Concept(
        name="trial_balance",
        metric_ids=("M.TB.001",),
        is_family=False,
        family_rule="Single definition, presented under both reversal conventions (proven "
                    "identical, C.002) -- complementary sub-views, not competing definitions.",
        phrases=("trial balance", "accounting check", "books balance", "debits equal credits",
                 "accounting integrity"),
        domain="Financial",
    ),
    Concept(
        name="pnl",
        metric_ids=("M.PNL.001",),
        is_family=False,
        family_rule="Documented SAFE composite of M.REV.002 + M.EXP.001.",
        phrases=("p&l", "pnl", "profit and loss", "profit & loss", "income statement",
                 "monthly p&l"),
        domain="Financial",
        delivers_breakdown=("month",),
    ),
    Concept(
        name="staying_tenants",
        metric_ids=("M.TEN.001",),
        is_family=False,
        family_rule="Unambiguous enum count -- explicitly NOT downgraded by DQ.003 "
                    "(metric_dependency_graph.md 6; H.013 proves 0 overlap for this status).",
        phrases=("staying tenants", "current tenants", "active tenants", "how many tenants",
                 "tenant count", "residents"),
        alternatives=("M.TEN.002", "M.TEN.003"),
        domain="Operations",
        delivers_filter=("staying_status",),
        superseded_by=("on_notice_tenants", "booked_beds"),
    ),
    Concept(
        name="on_notice_tenants",
        metric_ids=("M.TEN.002",),
        is_family=False,
        family_rule="Unambiguous enum count.",
        phrases=("on notice", "on-notice", "leaving tenants", "tenants leaving",
                 "notice period"),
        domain="Operations",
        delivers_filter=("staying_status",),
    ),
    Concept(
        name="booked_beds",
        metric_ids=("M.TEN.003",),
        is_family=False,
        family_rule="Unambiguous enum count.",
        phrases=("booked beds", "bookings", "booked"),
        domain="Operations",
        delivers_filter=("staying_status",),
    ),
    Concept(
        name="move_ins",
        metric_ids=("M.LIFE.002",),
        is_family=False,
        family_rule="Single definition on onboarding_date.",
        phrases=("move in", "move-ins", "move ins", "moved in", "new tenants", "onboarding",
                 "onboarded"),
        domain="Operations",
    ),
    Concept(
        name="move_outs",
        metric_ids=("M.LIFE.003",),
        is_family=False,
        family_rule="Single definition on actual_exit_date.",
        phrases=("move out", "move-outs", "move outs", "moved out", "exits", "exited",
                 "churn", "vacated"),
        domain="Operations",
    ),
    Concept(
        name="tenant_lifecycle",
        metric_ids=("M.LIFE.001",),
        is_family=False,
        family_rule="Single derivation from the documented priority rule.",
        phrases=("lifecycle", "tenant lifecycle", "staying status", "tenant status"),
        alternatives=("M.LIFE.004",),
        domain="Operations",
    ),
    Concept(
        name="exit_reconciliation",
        metric_ids=("M.LIFE.004",),
        is_family=False,
        family_rule="Single-convention use of the AR ledger figure, disclosed -- explicitly "
                    "stays SAFE per metric_dependency_graph.md 6.",
        phrases=("exit reconciliation", "exit settlement", "final settlement",
                 "settle on exit"),
        domain="Operations",
    ),
    Concept(
        name="maintenance",
        metric_ids=("M.MAINT.001",),
        is_family=False,
        family_rule="Single ticket-volume definition. created_at IS the business date here -- "
                    "the one documented exception (business_dimensions.md 17).",
        phrases=("maintenance", "tickets", "maintenance tickets", "repairs", "complaints",
                 "issues raised"),
        alternatives=("M.MAINT.002",),
        domain="Operations",
    ),
    Concept(
        name="maintenance_cost",
        metric_ids=("M.MAINT.002",),
        is_family=False,
        family_rule="Two computation PATHS that agree exactly for this dataset (C.023 checked "
                    "and disproven) -- paths, not competing definitions, so still SAFE.",
        phrases=("maintenance cost", "maintenance spend", "repair cost", "cost of repairs"),
        domain="Operations",
    ),
    Concept(
        name="electricity",
        metric_ids=("M.EB.001",),
        is_family=False,
        family_rule="Single definition; DISCLOSE via DQ.028's billing_month text format.",
        phrases=("electricity", "eb", "power", "electricity cost", "power bill",
                 "electricity usage", "units consumed"),
        alternatives=("M.EB.002",),
        domain="Operations",
    ),
    Concept(
        name="eb_allocation",
        metric_ids=("M.EB.002",),
        is_family=False,
        family_rule="Single definition; same DQ.028 caveat.",
        phrases=("eb allocation", "electricity allocation", "electricity per tenant",
                 "power allocation"),
        domain="Operations",
    ),
    Concept(
        name="aging",
        metric_ids=("M.RISK.002",),
        is_family=False,
        family_rule="Single definition, inherently CURRENT_DATE-dependent (C.019/DQ.018).",
        phrases=("aging", "ageing", "overdue", "past due", "how overdue", "days outstanding",
                 "which tenants are overdue"),
        alternatives=("M.AR.001A", "M.AR.001B", "M.AR.001C", "M.AR.001D"),
        note="An overdue question also touches the tenant-dues family, which is BLOCK -- "
             "ai_evaluation_framework.md 3 marks this scenario 'Composite, SHOW_BOTH + "
             "DISCLOSE'.",
        domain="Risk & Data Quality",
    ),
    Concept(
        name="deposit_risk",
        metric_ids=("M.RISK.003",),
        is_family=False,
        family_rule="Single risk-framed definition.",
        phrases=("deposit risk", "phantom deposit", "phantom deposits", "deposit anomaly"),
        alternatives=("M.RISK.004",),
        domain="Risk & Data Quality",
    ),
    Concept(
        name="duplicates",
        metric_ids=("M.RISK.005",),
        is_family=False,
        family_rule="Single definition over the documented duplicate key.",
        phrases=("duplicate invoice", "duplicate invoices", "duplicate billing",
                 "double billed", "duplicates"),
        alternatives=("M.RISK.006",),
        domain="Risk & Data Quality",
    ),
    Concept(
        name="duplicate_receipts",
        metric_ids=("M.RISK.006",),
        is_family=False,
        family_rule="Single definition.",
        phrases=("duplicate receipt", "duplicate receipts", "double receipt"),
        domain="Risk & Data Quality",
    ),
    Concept(
        name="overlapping_allotments",
        metric_ids=("M.RISK.007",),
        is_family=False,
        family_rule="Single definition; the one metric with a documented reconstruction-method "
                    "discrepancy against its own reference (DIFFERS, 214 vs H.056's 187).",
        phrases=("overlapping allotment", "overlapping allotments", "double allocated",
                 "double booked", "bed conflict"),
        domain="Risk & Data Quality",
    ),
    Concept(
        name="reconciliation",
        metric_ids=("M.RISK.008",),
        is_family=False,
        family_rule="Single definition over the documented ledger/source comparison.",
        phrases=("reconciliation", "reconcile", "ledger vs source", "ledger drift",
                 "do the books match", "source reconciliation"),
        domain="Risk & Data Quality",
    ),
    Concept(
        name="data_quality",
        metric_ids=("M.RISK.009",),
        is_family=False,
        family_rule="Meta-metric over the registry's own trust distribution.",
        phrases=("data quality", "data-quality", "trust status", "how reliable is the data",
                 "how reliable", "can i trust", "data issues", "data problems"),
        domain="Risk & Data Quality",
    ),
)


_BY_NAME = {c.name: c for c in CONCEPTS}


def period_series_candidates(concept_name=None, metric_ids=()):
    """Ordered metric_ids that may answer a period-scoped ask for this concept/family.

    Used by planning to prefer a monthly series over an all-time total when the owner
    named a calendar period. Looks up the concept's alternatives, and also reverse-maps
    from any known metric_id (including `explicit:M.…` resolution paths) so a forced
    metric_id still finds its documented monthly sibling.
    """
    seen = []
    def _add(mid):
        if mid and mid not in seen:
            seen.append(mid)

    c = concept(concept_name) if concept_name else None
    if c is not None:
        for mid in tuple(c.alternatives) + tuple(c.metric_ids):
            _add(mid)

    for mid in tuple(metric_ids or ()):
        _add(mid)
        for cand in all_concepts():
            if mid in cand.metric_ids or mid in cand.alternatives:
                for m in tuple(cand.alternatives) + tuple(cand.metric_ids):
                    _add(m)
    return tuple(seen)


def concept(name):
    return _BY_NAME.get(name)


def all_concepts():
    return CONCEPTS


# Diagnostic / data-quality metrics that must never be presented as a financial headline
# (Phase 3 requirement 5: "using a diagnostic/DQ metric as a financial headline"). Derived from
# the registry's own `domain` column, not hand-listed -- see is_diagnostic().
DIAGNOSTIC_DOMAIN = "Risk & Data Quality"


def is_diagnostic(metric_id, registry):
    return registry.get(metric_id).domain == DIAGNOSTIC_DOMAIN


# Small closed set of filler tokens allowed between phrase words. Arbitrary content words
# (especially other concept names like "profit") must NOT count as fillers, or
# "how much profit did we make" would falsely match revenue's "how much did we make".
_PHRASE_FILLERS = frozenset({
    "a", "an", "the", "our", "my", "your", "we", "you", "us", "of", "for", "in", "on",
    "to", "from", "at", "by", "and", "or", "as", "so", "do", "did", "does", "have",
    "has", "had", "been", "be", "is", "are", "was", "were", "this", "that", "these",
    "those", "money", "cash", "total", "overall", "please", "just", "really",
})


def _phrase_pattern(phrase):
    """Exact contiguous phrase match (word-bounded)."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])")


def _flexible_phrase_pattern(phrase):
    """Multi-word phrase match that allows a few intervening filler tokens only.

    So 'how much did we make' still matches 'how much money did we make' without adding
    every surface variant as a canned question string. Single-token phrases stay exact.
    Content words (including other concept names) are never skipped as fillers.
    """
    words = [w for w in (phrase or "").lower().split() if w]
    if len(words) <= 1:
        return _phrase_pattern(phrase)
    filler = r"(?:\s+(?:" + "|".join(sorted(_PHRASE_FILLERS)) + r")){0,2}\s+"
    body = filler.join(re.escape(w) for w in words)
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")


_COMPILED = tuple(
    (c, tuple((_phrase_pattern(p), _flexible_phrase_pattern(p), p) for p in c.phrases))
    for c in CONCEPTS
)


def match(question):
    """Deterministic concept matching. Returns concepts whose trigger phrases appear in the
    question, longest-phrase-first so that 'maintenance cost' beats 'maintenance' and
    'revenue by month' beats 'revenue'. Never fuzzy, never scored, never probabilistic.

    Returns a list of (Concept, matched_phrase) ordered by match specificity."""
    q = (question or "").lower()
    hits = []
    for c, patterns in _COMPILED:
        best = ""
        for exact_pat, flex_pat, phrase in patterns:
            if (exact_pat.search(q) or flex_pat.search(q)) and len(phrase) > len(best):
                best = phrase
        if best:
            hits.append((c, best))
    hits.sort(key=lambda h: len(h[1]), reverse=True)

    # Drop a concept whose only matched phrase is a strict substring of a longer concept's
    # matched phrase -- "maintenance" inside "maintenance cost" is the same mention, not a
    # second concept. This is textual de-duplication, never a semantic choice between two
    # genuinely different concepts (those are preserved and become ambiguity).
    kept = []
    for c, phrase in hits:
        if any(phrase != other and phrase in other for _, other in hits):
            continue
        kept.append((c, phrase))

    # A generic concept yields to a more specific one that matched alongside it. This is NOT a
    # choice between competing DEFINITIONS of one concept (that would be ambiguity the resolver
    # must escalate) -- it is a narrower subset of the same population being named explicitly,
    # e.g. "how many tenants ... on notice" is unambiguously the On-Notice count.
    names = {c.name for c, _ in kept}
    kept = [(c, ph) for c, ph in kept
            if not any(sup in names for sup in c.superseded_by)]

    # A bare qualifier names a concept only when nothing else is named. "Outstanding" on its own
    # is the owner's word for tenant dues; in "deposit refunds outstanding" it only describes the
    # deposit refunds, and reading it as a second subject would ask about an ambiguity the owner
    # never raised.
    if len(kept) > 1:
        kept = [(c, ph) for c, ph in kept if ph not in _QUALIFIER_PHRASES] or kept
    return kept


# Phrases that are qualifiers as often as they are subjects. Matched like any other phrase, but
# they yield to any other concept named in the same question.
_QUALIFIER_PHRASES = frozenset({"outstanding"})


def verify_against_registry(registry):
    """Guard for the exit criterion 'every metric reference resolves to the semantic registry'
    and 'no business definition is duplicated or invented'. Returns a list of problems."""
    problems = []
    for c in CONCEPTS:
        for mid in tuple(c.metric_ids) + tuple(c.alternatives):
            if mid not in registry:
                problems.append(f"concept {c.name!r} references unknown metric_id {mid!r}")
        if not c.metric_ids:
            problems.append(f"concept {c.name!r} maps to no metric")
        if not c.family_rule:
            problems.append(f"concept {c.name!r} states no family rule")
        for mid in c.metric_ids:
            if c.domain and registry.get(mid).domain != c.domain:
                problems.append(
                    f"concept {c.name!r} declares domain {c.domain!r} but {mid} is "
                    f"{registry.get(mid).domain!r} in the registry")
    return problems
