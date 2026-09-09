"""
descriptive_routing.py -- which owner questions reach the descriptive engine.

Routing only. Nothing here computes a statistic, chooses a definition, or touches trust; it
decides which of `engine/descriptive.py`'s entry points a question is asking for, and says so
explicitly when the answer is "none of them".

The rule that keeps this from swallowing the rest of the product: a question routes here only
when it carries BOTH

    an analysis-type marker  ("typical", "vary", "volatile", "distribution", "compare on", ...)
    AND a subject the descriptive engine can actually serve (rent, deposits, revenue, ...)

"What is our revenue?" is a lookup and stays one. "Revenue this month vs last month" is a period
comparison and stays one. "Why did revenue drop?" is driver analysis and stays that. None of
them carry an analysis-type marker over a servable subject, so none of them arrive here -- which
is the point: words like "average", "compare" and "change" appear throughout ordinary owner
questions, and matching on them alone would quietly re-route half the product.

Two further restraints are deliberate:

  * Central tendency alone does not route a monthly SERIES. "What is average revenue?" is a
    lookup about a level; the series summary describes month-to-month movement, which is a
    different question. Only spread, movement or shape markers pull a series in here.
  * The refusals below are split. Significance, intervals and causal claims are refused wherever
    they appear, because no other part of the product offers them. Anomaly verdicts, occupancy
    history and property comparison are refused only inside an otherwise-descriptive question,
    because existing routing already answers those on its own terms and must keep doing so.
"""
import re

from engine import descriptive
from engine.result import NOT_DETERMINABLE_TEXT

# --- what the question is asking FOR -------------------------------------------------------------

# A typical value: "what's typical rent", "average rent", "median rent".
_CENTRAL_MARKERS = (
    "typical", "average", "median", "usual", "normal range", "on average",
)

# Spread: "how much do deposits vary", "how variable are rents", "is revenue volatile".
_SPREAD_MARKERS = (
    "vary", "varies", "variable", "variability", "variation in", "volatile", "volatility",
    "spread of", "spread in", "how consistent", "how steady", "steady or", "fluctuate",
    "fluctuation", "range of", "dispersion",
)

# Shape: "what's the distribution of rent".
_SHAPE_MARKERS = ("distribution", "histogram", "percentile", "quartile", "skew",
                  "standard deviation")

# Movement of a monthly series: "how much does revenue change each month".
_MOVEMENT_MARKERS = (
    "month to month", "month-to-month", "each month", "per month", "monthly movement",
    "move month", "moves month", "change each month", "changes each month",
    "typical monthly change", "monthly change", "from month",
)

# Relationship between two measures: "do collections track revenue".
_RELATIONSHIP_MARKERS = (
    "track", "tracks", "related to", "relationship between", "relationship with",
    "correlate", "correlated", "correlation", "move together", "linked to", "connected to",
    "go together", "moves with", "move with",
)

# Grouped comparison: "how do apartments compare on rent".
_GROUP_MARKERS = (
    "compare on", "compare by", "compare across", "by apartment", "per apartment",
    "across apartments", "apartments compare", "apartment compare", "highest typical",
    "highest average", "highest median", "lowest typical", "lowest average", "lowest median",
    "which apartments", "which apartment", "compare on rent",
)

_ANALYSIS_MARKERS = (_CENTRAL_MARKERS + _SPREAD_MARKERS + _SHAPE_MARKERS
                     + _MOVEMENT_MARKERS + _RELATIONSHIP_MARKERS + _GROUP_MARKERS)

# A monthly series is pulled in by how it MOVES, never by a bare central-tendency word.
_SERIES_MARKERS = _SPREAD_MARKERS + _SHAPE_MARKERS + _MOVEMENT_MARKERS

# --- what the question is asking ABOUT ------------------------------------------------------------

# Owner phrasings -> the descriptive engine's own names.
_CROSS_SECTION_SUBJECTS = {
    "monthly_rent": ("rent", "rents", "rental", "rentals", "monthly rent"),
    "deposit_paid": ("deposit", "deposits", "security deposit", "security deposits"),
    "balance_due": ("balance due", "balances due", "outstanding balance"),
}

_SERIES_SUBJECTS = {
    "revenue": ("revenue", "income", "turnover", "sales"),
    "collections": ("collection", "collections", "cash collected", "receipts"),
    "expenses": ("expense", "expenses", "costs", "spending"),
}

_APARTMENT_WORDS = ("apartment", "apartments", "flat", "flats")


def subject_of(question):
    """The subject a question names, among the ones this module can serve. "" for none.

    This is where "rent" and "apartment" resolve. `concept_map` deliberately does not carry
    them: rent is a field recorded against an allotment, apartment is a grouping, and neither
    is a registry metric. Before this existed, "rent" was a trigger phrase on the revenue
    concept, so a rent question that missed descriptive routing came back with a revenue total
    -- a different quantity presented as the answer. Kept as one named function so that
    resolution is testable rather than an accident of the classifier's internals.
    """
    text = _prepare(question)
    if _mentions(text, _APARTMENT_WORDS):
        return "apartment"
    cross = _find_subjects(text, _CROSS_SECTION_SUBJECTS)
    if cross:
        return cross[0]
    series = _find_subjects(text, _SERIES_SUBJECTS)
    return series[0] if series else ""


# --- what this capability must refuse rather than answer narrowly ------------------------------------

# Refused wherever they appear: no other part of the product offers inference, and answering the
# descriptive part instead would substitute a narrower question for the one asked.
_HARD_REFUSALS = (
    ("significance_testing", (
        "statistically significant", "statistical significance", "significance test",
        "significance testing", "p value", "p-value", "hypothesis test", "significant at",
        "statistically", "test for significance",
    )),
    ("confidence_intervals", (
        "confidence interval", "confidence intervals", "margin of error",
    )),
    ("causal_analysis", (
        "causal", "cause and effect", "does higher", "does more", "cause higher",
        "causes higher", "cause lower", "causes lower", "cause revenue", "causes revenue",
        "lead to", "leads to", "prove that", "correlation imply", "imply causation",
    )),
)

# Refused only inside an otherwise-descriptive question. Existing routing already answers these
# on its own terms -- the anomaly path already returns NOT_DETERMINABLE, occupancy has its own
# handling -- and intercepting them everywhere would change answers this task must not touch.
_SOFT_REFUSALS = (
    ("anomaly_verdict", ("anomaly", "anomalies", "anomalous", "abnormal", "outlier",
                         "outliers")),
    ("occupancy_rate_history", ("occupancy rate", "occupancy over", "occupancy each month",
                                "occupancy by month", "historical occupancy")),
    ("property_comparison", ("compare properties", "across properties", "property comparison",
                             "by property", "which property")),
)


class Route:
    """What the question resolved to. `kind` is None when descriptive analysis is not the answer."""

    def __init__(self, kind=None, target=None, second=None, subject="", refusal="",
                 refusal_id=""):
        self.kind = kind                 # cross_section | series | relationship | apartments
        self.target = target
        self.second = second             # the other measure, for a relationship
        self.subject = subject           # owner-facing noun, for wording
        self.refusal = refusal           # a stated reason this cannot be answered
        self.refusal_id = refusal_id

    @property
    def matched(self):
        """True when this question belongs to the descriptive capability at all."""
        return bool(self.kind) or bool(self.refusal)

    def __repr__(self):
        return (f"Route(kind={self.kind!r}, target={self.target!r}, second={self.second!r}, "
                f"refusal={self.refusal_id or None!r})")


# "rental income" and "rental revenue" name the ledger figure, not the recorded rent field.
# They are rewritten before subject matching so "rental" cannot claim them for rent -- the same
# distinction concept_map draws, kept consistent on both sides of the routing boundary.
_REVENUE_COMPOUNDS = ("rental income", "rental revenue", "rent revenue")


def _prepare(question):
    text = f" {(question or '').lower()} "
    for compound in _REVENUE_COMPOUNDS:
        text = text.replace(compound, " revenue ")
    return text


def _mentions(text, phrases):
    return any(p in text for p in phrases)


def _find_subjects(text, table):
    """Subjects present, in the order the question names them."""
    found = []
    for name, phrases in table.items():
        for phrase in sorted(phrases, key=len, reverse=True):
            if re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", text):
                found.append((text.index(phrase), name))
                break
    return [name for _pos, name in sorted(found)]


def classify(question):
    """The descriptive route for this question, or a Route that matched nothing."""
    text = _prepare(question)

    for name, markers in _HARD_REFUSALS:
        if _mentions(text, markers):
            return Route(refusal=descriptive.unsupported(name), refusal_id=name)

    if not _mentions(text, _ANALYSIS_MARKERS):
        return Route()

    for name, markers in _SOFT_REFUSALS:
        if _mentions(text, markers):
            return Route(refusal=descriptive.unsupported(name), refusal_id=name)

    cross = _find_subjects(text, _CROSS_SECTION_SUBJECTS)
    series = _find_subjects(text, _SERIES_SUBJECTS)

    # Grouped comparison: apartments plus the one field the engine can group by.
    if _mentions(text, _APARTMENT_WORDS) and _mentions(text, _GROUP_MARKERS + _CENTRAL_MARKERS):
        if "monthly_rent" in cross or not cross:
            return Route(kind="apartments", target="monthly_rent", subject="rent by apartment")

    # Relationship: two monthly measures and a relationship marker.
    if _mentions(text, _RELATIONSHIP_MARKERS) and len(series) >= 2:
        return Route(kind="relationship", target=series[0], second=series[1],
                     subject=f"{series[0]} and {series[1]}")

    # Cross-sectional: a per-allotment field. These are single snapshots with no monthly series,
    # so any analysis marker is enough once the subject is one of them.
    if cross:
        return Route(kind="cross_section", target=cross[0],
                     subject=cross[0].replace("_", " "))

    # Monthly series: how the measure MOVES. A bare "average revenue" is a level lookup and is
    # deliberately left to the existing metric routing.
    if series and _mentions(text, _SERIES_MARKERS):
        return Route(kind="series", target=series[0], subject=series[0])

    return Route()


def period_conflict(question):
    """The requested period, when the question asks for one these figures cannot honour.

    The descriptive summaries describe the whole recorded window. Answering "what was typical
    rent in July?" with the all-time figure would answer a different question than the one asked,
    which is exactly the substitution the period layer exists to prevent. Returns the period
    label, or "" when the question named none.
    """
    from engine import time_resolution as timeres

    text = _prepare(question)
    # These phrases describe HOW a measure is summarised, not WHICH period is wanted.
    for phrase in ("month to month", "month-to-month", "each month", "per month",
                   "by month", "monthly", "from month to month"):
        text = text.replace(phrase, " ")

    label, start, _end = timeres.parse_period(text)
    if not start or label == "all-time":
        return ""
    return label


def period_refusal(label):
    """Owner wording for a period these figures cannot be narrowed to."""
    return (
        f"These figures describe the whole recorded period rather than a single one, so I "
        f"cannot narrow them to {label}. Asking without a period gives the overall picture; "
        f"asking for the figure itself gives {label}. {NOT_DETERMINABLE_TEXT}"
    )


def run(route):
    """Execute a resolved route against the descriptive engine. Computes nothing itself."""
    if route.kind == "cross_section":
        return descriptive.cross_section(route.target)
    if route.kind == "series":
        return descriptive.series_summary(route.target)
    if route.kind == "relationship":
        return descriptive.relationship(route.target, route.second)
    if route.kind == "apartments":
        return descriptive.apartment_comparison(route.target)
    return None


# The registry metric that governs each described column, where one exists. This is how the
# Trust Gate reaches a descriptive answer: `tenant_allotments.balance_due` is metric M.AR.001C,
# which is BLOCK, so describing that column inherits the block rather than quietly bypassing it.
# `monthly_rental` has no metric -- it is a recorded field, not a reconciled figure -- and the
# presentation layer says so instead of claiming a trust level it was not given.
GOVERNING_METRICS = {
    "cross_section": {
        "monthly_rent": (),
        "deposit_paid": ("M.RISK.004",),
        "balance_due": ("M.AR.001C",),
    },
    "series": {
        "revenue": ("M.REV.002",),
        "collections": ("M.COL.002",),
        "expenses": ("M.PNL.001",),
    },
    "apartments": {"monthly_rent": ()},
}


def governing_metric_ids(route):
    """Metric ids the Trust Gate must authorize before this answer is shown."""
    if route.kind == "relationship":
        first = GOVERNING_METRICS["series"].get(route.target, ())
        second = GOVERNING_METRICS["series"].get(route.second, ())
        return tuple(first) + tuple(second)
    return tuple(GOVERNING_METRICS.get(route.kind, {}).get(route.target, ()))
