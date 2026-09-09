"""
descriptive.py -- deterministic descriptive analysis.

DESCRIPTIVE, not inferential. This module reports what the recorded data looks like. It runs no
hypothesis test, produces no p-value, offers no confidence interval, and makes no causal claim.
That is not a shortfall to be filled in later -- it is what the evidence supports, established by
investigation:

  * The monthly series are almost perfectly autocorrelated (revenue lag-1 rho = 0.990,
    collections 0.975). Correcting 41 monthly revenue observations for that leaves an EFFECTIVE
    sample size of 0.2. A test assuming independent observations would emit a number there, and
    the number would mean nothing.
  * Expressed as month-over-month CHANGES the same series behave far better (rho = 0.114 and
    -0.203). So every volatility-style statistic here is computed on changes, never on levels.
  * The strongest-looking relationship in the package -- revenue against collections, r = 0.983
    on levels -- is almost entirely "both grew". On changes it falls to 0.240. Level and change
    correlations are therefore ALWAYS returned together, and the presentation layer must never
    show the level figure alone.

Every threshold below is derived from the statistic being computed, not chosen by convention.
Each is stated in the output so a reader can see the rule that was applied.
"""
from dataclasses import dataclass, field
import math
import statistics as st

from engine.result import NOT_DETERMINABLE_TEXT

# --- minimums, each with its derivation -----------------------------------------------------------

# Quartiles are undefined below four points: a group with fewer has a median but no measurable
# spread, so it cannot honestly be compared with one that has. This is the point at which the
# requested statistic exists, not a business judgement about what counts as "enough".
MIN_GROUP_SIZE = 4

# Skewness has sampling standard deviation of roughly sqrt(6/n). Below 24 observations that
# exceeds 0.5, which is larger than most of the skew values worth reporting -- the estimate would
# be noisier than the thing it estimates.
MIN_SKEW_N = 24

# A correlation's standard error is about 1/sqrt(n-3). Twelve pairs puts it near 0.33, which is
# the loosest that still distinguishes a strong relationship from no relationship at all.
MIN_PAIRED_OBSERVATIONS = 12

# Two consecutive observations produce one change; a distribution of changes needs enough of them
# for a median and quartiles to exist, which is the same four-point floor as above.
MIN_SERIES_OBSERVATIONS = 5


@dataclass
class Summary:
    """A completed descriptive summary, or a refusal. Never both."""
    available: bool = False
    label: str = ""
    source: str = ""
    stats: dict = field(default_factory=dict)
    notes: tuple = ()
    not_determinable_reason: str = ""


# --- primitives ------------------------------------------------------------------------------------

def _percentile(ordered, pct):
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * pct
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _skew(values):
    """Sample skewness, or None when the sample is too small for the estimate to be worth more
    than the noise in it."""
    n = len(values)
    if n < MIN_SKEW_N:
        return None
    mean = st.mean(values)
    sd = st.pstdev(values)
    if sd == 0:
        return None
    return round(sum(((v - mean) / sd) ** 3 for v in values) / n, 3)


def _coefficient_of_variation(values, mean, sd):
    """CV only where it means something.

    A coefficient of variation divides spread by level, so it is interpretable only when the
    level is positive and the values do not straddle zero. On a zero-inflated column such as
    `balance_due` -- where 1,116 of 1,213 rows are zero -- CV is arithmetically computable and
    tells the reader nothing.
    """
    if mean is None or mean <= 0:
        return None
    if any(v < 0 for v in values):
        return None
    return round(sd / mean, 3)


def _describe(values, *, label, source, total_rows=None, notes=()):
    """The shared descriptive block. Values must already be numeric and non-null."""
    n = len(values)
    if n == 0:
        return Summary(label=label, source=source,
                       not_determinable_reason=(
                           f"No usable values for {label}. {NOT_DETERMINABLE_TEXT}"))

    ordered = sorted(values)
    mean = st.mean(values)
    sd = st.pstdev(values) if n > 1 else 0.0
    zeros = sum(1 for v in values if v == 0)

    stats = {
        "count": n,
        "mean": round(mean, 2),
        "median": round(st.median(values), 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "std_dev": round(sd, 2) if n > 1 else None,
        "p25": round(_percentile(ordered, 0.25), 2) if n >= MIN_GROUP_SIZE else None,
        "p75": round(_percentile(ordered, 0.75), 2) if n >= MIN_GROUP_SIZE else None,
        "coefficient_of_variation": _coefficient_of_variation(values, mean, sd),
        "zero_count": zeros,
        "zero_pct": round(zeros / n * 100, 1),
        "skewness": _skew(values),
    }
    if total_rows is not None:
        missing = max(total_rows - n, 0)
        stats["missing_count"] = missing
        stats["missing_pct"] = round(missing / total_rows * 100, 1) if total_rows else 0.0

    extra = list(notes)
    if stats["p25"] is None:
        extra.append(f"No quartiles: fewer than {MIN_GROUP_SIZE} observations, so no spread "
                     f"can be measured.")
    if stats["skewness"] is None:
        extra.append(f"Skewness not reported: it needs at least {MIN_SKEW_N} observations to "
                     f"be worth more than the noise in it.")
    if stats["coefficient_of_variation"] is None:
        extra.append("Relative spread not reported: it is only meaningful for values that are "
                     "positive and do not straddle zero.")
    if stats["zero_pct"] >= 25:
        extra.append(f"{stats['zero_pct']}% of values are zero. The median and the share of "
                     f"zeros describe this column; the average does not.")

    return Summary(available=True, label=label, source=source, stats=stats,
                   notes=tuple(extra))


# --- 1. cross-sectional ------------------------------------------------------------------------------

# Columns the investigation found usable, with what an owner calls them. `expected_stay_days` is
# deliberately absent -- 1,198 of 1,213 rows are missing.
CROSS_SECTIONS = {
    "monthly_rent": ("tenant_allotments", "monthly_rental", "Monthly rent per allotment"),
    "deposit_paid": ("tenant_allotments", "deposit_paid", "Deposit recorded per allotment"),
    "balance_due": ("tenant_allotments", "balance_due", "Balance outstanding per allotment"),
}

UNSUPPORTED_CROSS_SECTIONS = {
    "expected_stay_days": (
        "Expected stay length is recorded for 15 of 1,213 allotments. A summary of 1% of the "
        "records would describe those fifteen, not the business. " + NOT_DETERMINABLE_TEXT),
}


def _numeric_column(table_name, column):
    """Numeric, non-null values of one column, plus the total row count."""
    from engine.evidence_loader import load_table

    table = load_table(table_name)
    if column not in table.columns:
        return None, 0
    values = []
    for raw in table[column].tolist():
        try:
            if raw is None:
                continue
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value != value:            # NaN
            continue
        values.append(value)
    return values, len(table)


def cross_section(name):
    """Descriptive summary of one recorded field across all allotments."""
    if name in UNSUPPORTED_CROSS_SECTIONS:
        return Summary(label=name, not_determinable_reason=UNSUPPORTED_CROSS_SECTIONS[name])
    if name not in CROSS_SECTIONS:
        return Summary(
            label=name,
            not_determinable_reason=(
                f"{name!r} is not a field this summary covers. Available: "
                f"{sorted(CROSS_SECTIONS)}. {NOT_DETERMINABLE_TEXT}"))

    table, column, label = CROSS_SECTIONS[name]
    values, total = _numeric_column(table, column)
    if values is None:
        return Summary(label=label,
                       not_determinable_reason=(
                           f"{label} is not present in the exported records. "
                           f"{NOT_DETERMINABLE_TEXT}"))
    return _describe(values, label=label, source="your allotment records", total_rows=total)


# --- 2. time series, on changes ------------------------------------------------------------------------

# The first month of sustained trading. Before it the ledger holds corrections and zeros; the
# forecaster establishes and documents the same boundary, and the two must not disagree about
# which months describe the business.
from engine.forecasting import OPERATING_START

SERIES_METRICS = {
    "revenue": ("M.REV.002", None, "Monthly revenue"),
    "collections": ("M.COL.002", None, "Monthly collections"),
    "expenses": ("M.PNL.001", "expenses", "Monthly expenses"),
}


def _monthly_values(metric_id, component=None, operating_only=True):
    """Complete months only, in order.

    A part-month would read as a collapse in trading, so months whose end falls after the export
    snapshot are excluded. `operating_only` additionally drops the pre-trading period, where the
    ledger carries corrections, zeros and negative months -- describing those as "monthly
    variation" would report bookkeeping as business behaviour. The boundary is the one the
    forecaster already established and documented, not a new judgement.
    """
    import calendar

    from engine.execution import MetricExecutor
    from engine.change_detection import _series_of, EXPORT_SNAPSHOT_DATE

    answer = MetricExecutor().execute(metric_id)
    _result, raw = _series_of(answer)
    if not raw:
        return []
    out = []
    for key in sorted(raw):
        year, month = int(key[:4]), int(key[5:7])
        end = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
        if end > EXPORT_SNAPSHOT_DATE:
            continue
        if operating_only and key[:7] < OPERATING_START:
            continue
        value = raw[key]
        if isinstance(value, dict):
            value = value.get(component)
        if isinstance(value, (int, float)):
            out.append((key[:7], float(value)))
    return out


def series_summary(name):
    """Month-to-month behaviour of a measure.

    Volatility statistics are computed on CHANGES, never on levels: the levels are dominated by
    growth, so their spread measures how much the business grew rather than how much it varies.
    Growth and volatility are reported as separate figures so neither is read as the other.
    """
    if name not in SERIES_METRICS:
        return Summary(
            label=name,
            not_determinable_reason=(
                f"{name!r} has no monthly series in this export. Only "
                f"{sorted(SERIES_METRICS)} do. {NOT_DETERMINABLE_TEXT}"))

    metric_id, component, label = SERIES_METRICS[name]
    points = _monthly_values(metric_id, component)
    if len(points) < MIN_SERIES_OBSERVATIONS:
        return Summary(
            label=label,
            not_determinable_reason=(
                f"{label} has {len(points)} complete months; at least "
                f"{MIN_SERIES_OBSERVATIONS} are needed to describe how it moves. "
                f"{NOT_DETERMINABLE_TEXT}"))

    periods = [p for p, _ in points]
    levels = [v for _, v in points]
    changes = [b - a for a, b in zip(levels, levels[1:])]
    pct_changes = [(b - a) / a * 100 for a, b in zip(levels, levels[1:]) if a > 0]

    summary = _describe(changes, label=f"{label}: month-to-month change",
                        source="your monthly records")
    if not summary.available:
        return summary

    # Growth is a separate fact from volatility, and stating them apart is the point.
    summary.stats["observations"] = len(levels)
    summary.stats["period_start"] = periods[0]
    summary.stats["period_end"] = periods[-1]
    summary.stats["latest_level"] = round(levels[-1], 2)
    summary.stats["median_pct_change"] = (round(st.median(pct_changes), 2)
                                          if pct_changes else None)
    summary.notes = summary.notes + (
        "These figures describe month-to-month movement, not the level of the measure. "
        "The level rose across this window, so a spread computed on levels would measure "
        "growth rather than variability.",
        f"Covers {periods[0]} onwards, when trading had begun. Earlier months in the ledger "
        f"are corrections and opening entries rather than trading, and including them would "
        f"describe bookkeeping as business variation.",
    )
    return summary


# --- 3. relationships ---------------------------------------------------------------------------------

def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 3)


RELATIONSHIPS = {
    ("revenue", "collections"),
    ("revenue", "expenses"),
    ("collections", "expenses"),
}

CORRELATION_CAVEAT = (
    "Correlation is not causation. These figures say the two measures moved together in the "
    "records; they do not say one produced the other."
)


def relationship(first, second):
    """Both correlations, always together.

    The level figure alone is the misleading one: revenue against collections reads r = 0.98 on
    levels and 0.24 on changes, because on levels it is mostly recording that both grew. Neither
    number is returned without the other.
    """
    pair = (first, second)
    if pair not in RELATIONSHIPS and tuple(reversed(pair)) not in RELATIONSHIPS:
        return Summary(
            label=f"{first} and {second}",
            not_determinable_reason=(
                f"No paired monthly series exists for {first} and {second}. "
                f"{NOT_DETERMINABLE_TEXT}"))

    a = dict(_monthly_values(*SERIES_METRICS[first][:2]))
    b = dict(_monthly_values(*SERIES_METRICS[second][:2]))
    keys = sorted(set(a) & set(b))

    if len(keys) < MIN_PAIRED_OBSERVATIONS:
        return Summary(
            label=f"{first} and {second}",
            not_determinable_reason=(
                f"Only {len(keys)} months have both {first} and {second} recorded; at least "
                f"{MIN_PAIRED_OBSERVATIONS} are needed before a correlation says anything. "
                f"{NOT_DETERMINABLE_TEXT}"))

    xs = [a[k] for k in keys]
    ys = [b[k] for k in keys]
    dxs = [q - p for p, q in zip(xs, xs[1:])]
    dys = [q - p for p, q in zip(ys, ys[1:])]

    level_r = _pearson(xs, ys)
    change_r = _pearson(dxs, dys)

    notes = [CORRELATION_CAVEAT]
    if level_r is not None and change_r is not None and abs(level_r) - abs(change_r) > 0.3:
        notes.append(
            "The two figures disagree sharply. Both measures rose across this window, and the "
            "level figure mostly records that shared rise. The month-to-month figure is the one "
            "that describes whether they actually move together.")

    return Summary(
        available=True,
        label=f"{first} and {second}",
        source="your monthly records",
        stats={
            "paired_months": len(keys),
            "period_start": keys[0],
            "period_end": keys[-1],
            "correlation_levels": level_r,
            "correlation_changes": change_r,
        },
        notes=tuple(notes),
    )


# --- 4. apartment comparison ----------------------------------------------------------------------------

def apartment_comparison(field_name="monthly_rent"):
    """Apartment-level descriptive comparison, with thin groups shown rather than hidden.

    Ranking by median rent puts three apartments at the extremes that have a single allotment
    each. Dropping them would make the ranking look complete while quietly excluding part of the
    estate; ranking them would present one observation as a finding. They are listed separately,
    named, and counted.
    """
    from engine.evidence_loader import load_table

    if field_name != "monthly_rent":
        return Summary(
            label=field_name,
            not_determinable_reason=(
                f"Apartment comparison covers monthly rent only. {NOT_DETERMINABLE_TEXT}"))

    allotments = load_table("tenant_allotments")
    apartments = load_table("apartments")
    codes = dict(zip(apartments["id"], apartments["apartment_code"]))

    grouped = {}
    for apartment_id, raw in zip(allotments["apartment_id"], allotments["monthly_rental"]):
        code = codes.get(apartment_id)
        if not code:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value != value:
            continue
        grouped.setdefault(str(code), []).append(value)

    if not grouped:
        return Summary(label="Monthly rent by apartment",
                       not_determinable_reason=(
                           f"No apartment-level rent records. {NOT_DETERMINABLE_TEXT}"))

    comparable, insufficient = [], []
    for code, values in grouped.items():
        row = {
            "apartment": code,
            "count": len(values),
            "median": round(st.median(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
        }
        if len(values) >= MIN_GROUP_SIZE:
            ordered = sorted(values)
            row["p25"] = round(_percentile(ordered, 0.25), 2)
            row["p75"] = round(_percentile(ordered, 0.75), 2)
            comparable.append(row)
        else:
            insufficient.append(row)

    comparable.sort(key=lambda r: r["median"], reverse=True)
    insufficient.sort(key=lambda r: r["apartment"])

    return Summary(
        available=True,
        label="Monthly rent by apartment",
        source="your allotment records",
        stats={
            "minimum_group_size": MIN_GROUP_SIZE,
            "apartments_total": len(grouped),
            "apartments_compared": len(comparable),
            "apartments_insufficient": len(insufficient),
            "comparable": tuple(comparable),
            "insufficient": tuple(insufficient),
        },
        notes=(
            f"Apartments with fewer than {MIN_GROUP_SIZE} recorded allotments are listed "
            f"separately and are not ranked: below four records there are no quartiles, so "
            f"there is no spread to compare against.",
            "This compares what was charged where. It does not explain why the amounts differ.",
        ),
    )


# --- 5. what this module will not do -----------------------------------------------------------------------

UNSUPPORTED = {
    "significance_testing": (
        "No significance test is offered. The monthly series repeat themselves almost exactly "
        "from one month to the next, which leaves 41 months of revenue carrying the weight of "
        "well under one independent observation. A test would return a number, and the number "
        "would not mean anything. " + NOT_DETERMINABLE_TEXT),
    "confidence_intervals": (
        "No confidence intervals are offered on these figures. They would claim a precision the "
        "sample does not support. " + NOT_DETERMINABLE_TEXT),
    "causal_analysis": (
        "This is descriptive analysis. It reports what the records show moving together and "
        "never why. No causal relationship is claimed or tested. " + NOT_DETERMINABLE_TEXT),
    "occupancy_rate_history": (
        "A monthly occupancy rate cannot be reconstructed: bed records carry no start or end "
        "date, so the number of beds available in a past month is unknown. "
        + NOT_DETERMINABLE_TEXT),
    "property_comparison": (
        "The records contain one property, so there is nothing to compare it with. This is a "
        "fact about the exported data, not a limitation of the calculation. "
        + NOT_DETERMINABLE_TEXT),
    "expected_stay_days": UNSUPPORTED_CROSS_SECTIONS["expected_stay_days"],
    "anomaly_verdict": (
        "No figure is labelled an anomaly. Deciding that a movement is abnormal needs a "
        "threshold that does not exist in these records. " + NOT_DETERMINABLE_TEXT),
}


def unsupported(name):
    """Why a named analysis is not offered. Returns "" for anything not deliberately excluded."""
    return UNSUPPORTED.get(name, "")


CAPABILITY_STATEMENT = (
    "Descriptive analysis: what the recorded figures look like -- counts, typical values, "
    "spread, and how measures moved together. It is not significance testing and not causal "
    "analysis, and it does not claim either."
)
