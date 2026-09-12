"""
forecasting.py -- deterministic revenue forecasting.

Every number this module produces is computed here, in Python, from the exported monthly revenue
series. No language model participates: the LLM's only role is to re-word a finished forecast,
under the same guard that polices every other answer.

WHY THIS METHOD
---------------
The method was chosen by rolling-origin out-of-sample backtest over the 41 contiguous complete
months of the operating era (2023-03 .. 2026-07), not by sophistication. Mean absolute
percentage error, 18-month minimum training window:

    method                     h=1     h=3
    damped Holt (chosen)      4.28%   8.20%
    naive (last value)        5.91%  10.64%
    moving average (3)       10.48%  14.45%
    linear trend             12.05%  14.20%
    regression on occupancy  31.50%  35.57%
    seasonal naive           47.30%  47.79%

Two of those results decided the design:

  * **Occupancy makes the forecast worse.** Revenue and occupied beds correlate at r=0.80 across
    the window, but both are simply rising -- on month-over-month CHANGES the correlation falls
    to 0.44, and using occupancy as a regressor produces 5-7x the error of a univariate model.
    It is therefore NOT used. See `evaluate_drivers()`, which reports this rather than hiding it.

  * **There is no usable seasonality.** Seasonal naive is the worst method tested, and 3.4 years
    is too short to separate a seasonal pattern from the growth ramp. (An apparent August trough
    -- 2023-08 at 20,400 -- was a revenue-by-month calculator defect that dropped one of the
    month's two (property, month) rows; the ledger records 448,141 for that month.)

Prediction intervals are EMPIRICAL -- the 10th/90th percentiles of the backtest's own residuals
at each horizon. No normality is assumed, because nothing in the evidence establishes one.
"""
import re
from dataclasses import dataclass, field, replace

from engine.result import NOT_DETERMINABLE_TEXT

# The export snapshot. A month is usable only when the export covers all of it.
EXPORT_SNAPSHOT_DATE = "2026-08-29"

# The operating era. Before this the ledger carries corrections, zeros and negative months from a
# pre-trading period; including them would fit a model to bookkeeping, not to the business.
OPERATING_START = "2023-03"

# Chosen by the sweep in the module docstring. High alpha (the recent level dominates) with a
# damped trend (growth is not extrapolated indefinitely).
ALPHA, BETA, PHI = 0.9, 0.4, 0.9

MIN_TRAIN_MONTHS = 18          # the backtest's minimum training window
MIN_OBSERVATIONS = 24          # below this, no forecast is offered at all

# Backtest error grows with horizon: 4.3% at 1 month, 8.2% at 3, 13.7% at 6, 19.5% at 12.
# Six months is where the error is still bounded and the number of validation folds (18) still
# supports the estimate. Beyond it the system declines rather than extrapolating.
MAX_HORIZON = 6

METHOD_NAME = "damped trend exponential smoothing (Holt, damped)"


# What the interval IS, carried with the forecast so no consumer can relabel it. These are not
# confidence intervals: nothing here estimates a sampling distribution or assumes normality. They
# are the 10th-90th percentiles of the method's OWN errors in backtesting at this horizon.
INTERVAL_BASIS = ("empirical 80% band: the 10th-90th percentiles of this method's own "
                  "out-of-sample backtest errors at this horizon. Not a statistical "
                  "confidence interval.")


@dataclass(frozen=True)
class ForecastPoint:
    period: str                 # "2026-08"
    value: float
    lower: float                # empirical band, see INTERVAL_BASIS -- NOT a confidence interval
    upper: float


@dataclass
class RevenueForecast:
    """A completed forecast, or a refusal. Never both."""
    available: bool = False
    method: str = ""
    horizon: int = 0
    points: tuple = ()
    training_start: str = ""
    training_end: str = ""
    observations: int = 0
    last_actual: float = None       # the final complete month, the forecast's starting point
    interval_basis: str = ""        # how `lower`/`upper` were derived; see INTERVAL_BASIS
    backtest: dict = field(default_factory=dict)
    drivers: tuple = ()
    limitations: tuple = ()
    not_determinable_reason: str = ""

    @property
    def direction(self):
        """Where the forecast sits relative to the LAST RECORDED month.

        Measured against the actual starting point rather than within the forecast itself, so a
        one-month forecast has a direction too. Reported as the model's own slope, never as a
        claim about what the business will do.
        """
        if not self.points or self.last_actual is None:
            return ""
        final = self.points[-1].value
        if final > self.last_actual:
            return "increase"
        if final < self.last_actual:
            return "decrease"
        return "flat"


# --- series ---------------------------------------------------------------------------------

def _month_key(ts):
    return f"{ts[:7]}"


def _month_end(year, month):
    import calendar
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def _next_month(key):
    y, m = int(key[:4]), int(key[5:7])
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def monthly_revenue_series(executor=None):
    """Complete monthly revenue, operating era only, in chronological order.

    Returns [(period_key, value), ...]. A month whose end falls after the export snapshot is
    excluded: a part-month would be read by the model as a collapse in trading.
    """
    from engine.execution import MetricExecutor
    from engine.change_detection import _series_of

    executor = executor or MetricExecutor()
    answer = executor.execute("M.REV.002")
    _result, raw = _series_of(answer)
    if not raw:
        return []

    out = []
    for key in sorted(raw):
        period = _month_key(key)
        year, month = int(period[:4]), int(period[5:7])
        if _month_end(year, month) > EXPORT_SNAPSHOT_DATE:
            continue                                  # incomplete at the snapshot
        if period < OPERATING_START:
            continue                                  # pre-trading ledger noise
        value = raw[key]
        if isinstance(value, (int, float)):
            out.append((period, float(value)))
    return out


# --- the model ------------------------------------------------------------------------------

def _holt(values, horizon, alpha=ALPHA, beta=BETA, phi=PHI):
    """Damped-trend exponential smoothing. Deterministic and dependency-free."""
    if len(values) < 2:
        return [float(values[-1])] * horizon if values else []
    level = float(values[0])
    trend = float(values[1] - values[0])
    for v in values[1:]:
        previous = level
        level = alpha * float(v) + (1 - alpha) * (level + phi * trend)
        trend = beta * (level - previous) + (1 - beta) * phi * trend
    out = []
    for step in range(1, horizon + 1):
        damping = sum(phi ** j for j in range(1, step + 1))
        out.append(level + damping * trend)
    return out


def _backtest(values, horizon):
    """Rolling-origin evaluation. Returns (mape, residuals, folds).

    Residuals are actual-minus-forecast at the horizon's final step, which is what the interval
    at that horizon has to cover.
    """
    residuals, pcts = [], []
    for cut in range(MIN_TRAIN_MONTHS, len(values) - horizon + 1):
        history = values[:cut]
        actual = values[cut:cut + horizon]
        predicted = _holt(history, horizon)
        if not predicted or len(actual) < horizon:
            continue
        residuals.append(actual[-1] - predicted[-1])
        for p, a in zip(predicted, actual):
            if a:
                pcts.append(abs(p - a) / abs(a) * 100.0)
    mape = round(sum(pcts) / len(pcts), 2) if pcts else None
    return mape, residuals, len(residuals)


def _percentile(sorted_values, pct):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * pct
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


# --- drivers --------------------------------------------------------------------------------

def evaluate_drivers(executor=None):
    """What was tested as a predictor, and what the test said.

    Reported whether or not a driver was used. A driver that was evaluated and rejected is a
    finding the owner is entitled to, not an absence to stay quiet about.
    """
    return (
        {
            "driver": "occupied beds",
            "verdict": "REJECTED",
            "evidence": (
                "Revenue and occupied beds move together across the window (r = 0.80), but both "
                "are simply rising. On month-to-month changes the relationship weakens to "
                "r = 0.44, and using occupied beds to predict revenue produced 31.5% error "
                "against 4.3% for the chosen method -- roughly seven times worse."),
        },
        {
            "driver": "occupancy rate",
            "verdict": "NOT_DERIVABLE",
            "evidence": (
                "A monthly occupancy rate cannot be reconstructed from this export. Bed records "
                "carry no start or end date, so the number of beds available in a past month is "
                "unknown; reconstructing it from apartment dates puts occupancy above 100% in "
                "most months, which is an artefact of the reconstruction rather than a "
                "measurement. " + NOT_DETERMINABLE_TEXT),
        },
        {
            "driver": "calendar seasonality",
            "verdict": "REJECTED",
            "evidence": (
                "A seasonal model was the least accurate of every method tested (47% error). "
                "The apparent August dip is a single irregular month in 2023, and three and a "
                "half years is too short to separate a seasonal pattern from the growth trend."),
        },
    )


# --- public entry point -----------------------------------------------------------------------

def forecast_revenue(horizon=1, executor=None):
    """Forecast total monthly revenue `horizon` months beyond the last complete month."""
    try:
        horizon = int(horizon)
    except (TypeError, ValueError):
        horizon = 1

    if horizon < 1:
        return RevenueForecast(
            available=False,
            not_determinable_reason="A forecast needs a horizon of at least one month.")

    if horizon > MAX_HORIZON:
        return RevenueForecast(
            available=False,
            not_determinable_reason=(
                f"I can forecast up to {MAX_HORIZON} months ahead. Beyond that the method's "
                f"own error grows past 15% in testing and there is too little history to "
                f"measure it reliably, so a longer forecast would be a guess dressed as a "
                f"figure. {NOT_DETERMINABLE_TEXT}"))

    series = monthly_revenue_series(executor)
    if len(series) < MIN_OBSERVATIONS:
        return RevenueForecast(
            available=False,
            observations=len(series),
            not_determinable_reason=(
                f"Forecasting needs at least {MIN_OBSERVATIONS} complete months of revenue; "
                f"the export provides {len(series)}. {NOT_DETERMINABLE_TEXT}"))

    periods = [p for p, _ in series]
    values = [v for _, v in series]

    predicted = _holt(values, horizon)
    mape, residuals, folds = _backtest(values, horizon)

    # Empirical 80% band from the backtest's own residuals at this horizon. Applied around each
    # step; the band is the method's demonstrated error, not an assumed distribution.
    band_low = band_high = None
    if len(residuals) >= 5:
        ordered = sorted(residuals)
        band_low = _percentile(ordered, 0.10)
        band_high = _percentile(ordered, 0.90)

    points, key = [], periods[-1]
    for step, value in enumerate(predicted, start=1):
        key = _next_month(key)
        lower = round(value + band_low, 2) if band_low is not None else None
        upper = round(value + band_high, 2) if band_high is not None else None
        points.append(ForecastPoint(period=key, value=round(value, 2),
                                    lower=lower, upper=upper))

    limitations = [
        "A forecast is a projection of the recorded trend, not a commitment. It assumes trading "
        "continues broadly as it has.",
    ]
    if band_low is None:
        limitations.append(
            "No prediction interval is offered at this horizon: too few validation folds exist "
            "to measure the method's error. " + NOT_DETERMINABLE_TEXT)
    if mape is not None and mape > 12:
        limitations.append(
            f"At {horizon} months the method's tested error is {mape}%, which is wide enough "
            f"that the direction is more reliable than the figure.")

    return RevenueForecast(
        available=True,
        method=METHOD_NAME,
        horizon=horizon,
        points=tuple(points),
        training_start=periods[0],
        training_end=periods[-1],
        observations=len(series),
        last_actual=values[-1],
        interval_basis=INTERVAL_BASIS if band_low is not None else "",
        backtest={
            "mape_pct": mape,
            "folds": folds,
            "min_training_months": MIN_TRAIN_MONTHS,
            "compared_against": {"naive_last_value_mape_pct": _naive_mape(values, horizon)},
        },
        drivers=evaluate_drivers(executor),
        limitations=tuple(limitations),
    )


def _naive_mape(values, horizon):
    """The benchmark the chosen method had to beat, recomputed so the claim is checkable."""
    pcts = []
    for cut in range(MIN_TRAIN_MONTHS, len(values) - horizon + 1):
        last = values[cut - 1]
        for a in values[cut:cut + horizon]:
            if a:
                pcts.append(abs(last - a) / abs(a) * 100.0)
    return round(sum(pcts) / len(pcts), 2) if pcts else None


def scenario_forecast(occupancy_rate=None, occupied_beds=None, executor=None):
    """"What would revenue be at 80% occupancy?" -- refused, with the reason.

    Answering it needs a fitted relationship between occupancy and revenue that survives
    validation. The relationship was tested and did not: see `evaluate_drivers()`. Producing a
    figure anyway would mean inventing the coefficient the evidence declined to supply.
    """
    return RevenueForecast(
        available=False,
        drivers=evaluate_drivers(executor),
        not_determinable_reason=(
            "I can't give a revenue figure for a chosen occupancy level. A scenario like that "
            "needs a validated relationship between occupancy and revenue, and the one in these "
            "records does not hold up: occupancy and revenue rise together over time, but "
            "occupancy does not predict revenue month to month -- using it made the forecast "
            "about seven times less accurate. A monthly occupancy rate cannot be reconstructed "
            "from this export either, because bed records carry no dates. "
            + NOT_DETERMINABLE_TEXT))


# --- natural-language capability metadata ------------------------------------------------------

# Phrases that ask for a forecast, mapped to the horizon in months. Deterministic: the model
# never chooses the horizon, because a misread horizon changes the answer silently.
_HORIZON_PHRASES = (
    ("next quarter", 3), ("this quarter", 3), ("coming quarter", 3),
    ("next 12 months", 12), ("next twelve months", 12), ("next year", 12),
    ("next 6 months", 6), ("next six months", 6),
    ("next 3 months", 3), ("next three months", 3),
    ("next 2 months", 2), ("next two months", 2),
    ("next month", 1), ("coming month", 1), ("following month", 1),
    ("next few months", 3),
)

# A scenario question fixes a driver level ("at 80% occupancy") rather than asking for a
# projection of the trend. Answered separately, and refused, by `scenario_forecast`.
SCENARIO_MARKERS = ("if occupancy", "at 80", "at 75", "at 90", "occupancy reaches",
                    "occupancy hits", "occupancy is", "occupancy were", "occupancy goes")


def parse_horizon(question):
    """Months requested, or 1 when a forecast is asked without a period.

    Returns (horizon, phrase). A number the owner states explicitly wins over any default.
    """
    import re

    text = (question or "").lower()
    for phrase, months in _HORIZON_PHRASES:
        if phrase in text:
            return months, phrase

    m = re.search(r"\bnext\s+(\d{1,2})\s+months?\b", text)
    if m:
        return int(m.group(1)), m.group(0)
    return 1, "next month"


# A question may name the month it wants instead of counting months forward. "Forecast revenue
# for October 2026" and "next 3 months" ask for the same thing in different units, and only the
# second was understood: `parse_horizon` found no phrase it recognised and fell back to its
# default of 1, so every named future month was answered with the FIRST forecast month. The
# owner asked about October and was shown August, with nothing in the answer to say so.
_FUTURE_TENSE = re.compile(
    r"(?<![a-z])(?:will|forecast|forecasted|predict|prediction|project(?:ed|ion)?|expect(?:ed)?"
    r"|going\s+to|outlook)(?![a-z])", re.I)


def parse_target_month(question):
    """The calendar month a question names, as "YYYY-MM". "" when it names none.

    Delegates to the shared period parser rather than matching month names again here, so a
    forecast resolves the requested month by exactly the same rules as every other question.
    """
    from engine import time_resolution as timeres

    # A forecast has ONE target. "Compare August revenue with July revenue" names two months
    # and is a comparison; taking the first as a forecast target turned a comparison into a
    # projection of one of its two sides.
    if len(set(timeres.named_months(question))) > 1:
        return ""

    label, start, _end = timeres.parse_period(question)
    if not start or not re.fullmatch(r"\d{4}-\d{2}", label or ""):
        return ""
    return label


def horizon_for_period(period):
    """How many months ahead `period` is, counted from the last complete operating month.

    Returns 0 or less when the month is not in the future -- a named month that is already
    recorded is a historical question, and answering it with a projection would replace a
    fact with an estimate.
    """
    if not period or not re.fullmatch(r"\d{4}-\d{2}", period):
        return 0
    series = monthly_revenue_series()
    if not series:
        return 0
    base = series[-1][0]
    by, bm = int(base[:4]), int(base[5:7])
    ty, tm = int(period[:4]), int(period[5:7])
    return (ty - by) * 12 + (tm - bm)


# Past-tense wording keeps a question historical even when the month it names is not yet
# recorded. "What WAS revenue in October 2026?" asks what the records hold; they hold nothing,
# and saying so is the honest answer. Answering it with a projection would replace a question
# about fact with an estimate.
_PAST_TENSE = re.compile(
    r"(?<![a-z])(?:was|were|did|had|actual|actuals|actually|recorded|so\s+far|to\s+date)"
    r"(?![a-z])", re.I)


def asks_future_month(question):
    """True when the question names a month the records cannot reach, and is not asked in the
    past tense.

    Forward-looking wording is NOT required. "November revenue" carries no verb at all, and no
    amount of coverage checking will ever produce a November figure -- the export stops before
    it. Demanding "will" or "forecast" meant such a question was answered with "that period
    isn't fully covered by the exported data", which is true, useless, and treats a future
    target as a historical gap.
    """
    period = parse_target_month(question)
    if not period or horizon_for_period(period) <= 0:
        return False
    return not _PAST_TENSE.search(question or "")


def forecast_month(period):
    """The forecast for one named month, or None when that month is not in the future.

    Computes nothing new: it runs the same projection out to the requested month and returns
    the point for that month, so the value, the interval and the tested error are the ones
    belonging to that horizon rather than to some shorter one. A month past the supported
    horizon returns the refusal `forecast_revenue` already gives, with its own reason.
    """
    horizon = horizon_for_period(period)
    if horizon <= 0:
        return None
    forecast = forecast_revenue(horizon)
    if not forecast.available:
        return forecast
    wanted = tuple(p for p in forecast.points if p.period == period)
    if not wanted:
        return forecast
    return replace(forecast, points=wanted, horizon=horizon)


def asks_scenario(question):
    """True when the question fixes an occupancy level rather than asking for a projection."""
    text = (question or "").lower()
    return any(marker in text for marker in SCENARIO_MARKERS)


# Forward-looking phrasings the period layer does not treat as an explicit forecast request.
# Kept here rather than added to the period parser, so the shared period/comparison semantics
# stay exactly as they are.
_FORWARD_MARKERS = (
    "likely to increase", "likely to decrease", "likely to rise", "likely to fall",
    "likely to grow", "expect revenue", "revenue outlook", "outlook for revenue",
    "how much revenue can we expect", "what can we expect",
)


def asks_forecast(question):
    """True when the question looks forward, including phrasings the period layer misses.

    A named future month counts. "What will revenue be in October 2026?" carries no relative
    period phrase, so nothing upstream recognised it as forward-looking and it was answered as
    a coverage gap -- the export does not reach October, which is true and beside the point.
    """
    text = (question or "").lower()
    return (any(marker in text for marker in _FORWARD_MARKERS)
            or asks_scenario(question)
            or asks_future_month(question))
