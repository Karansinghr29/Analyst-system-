"""
forecasting.py -- deterministic revenue forecasting.

Every number this module produces is computed here, in Python, from the exported evidence. No
language model participates: the LLM's only role is to re-word a finished forecast, under the same
guard that polices every other answer.

TARGET
------
Monthly total INVOICED revenue:

    SUM(invoices.total_amount) grouped by invoices.billing_month

every invoice row as recorded -- no is_deleted, status, reversal or cancellation filter and no
deduplication -- over complete months of the operating era: from OPERATING_START to the last month
whose final day falls on or before EXPORT_SNAPSHOT_DATE. This is
invoiced revenue, not the ledger revenue reported by M.REV.001/M.REV.002: the two are different
definitions and are never mixed. Invoice totals are summed as recorded; duplicate invoice groups
(DQ.013) are not removed, because the evidence does not establish which copy is the valid one.

MODELS
------
Three models, evaluated on the same chronological validation months:

  1. Revenue-history baseline   -- Ridge regression on the revenue-history features only.
  2. Holt-Winters               -- additive trend and additive 12-month seasonality; the seasonal
                                   naive (same month last year) is reported alongside it.
  3. Multivariate Ridge         -- THE PRODUCTION MODEL. Revenue history, calendar, tenant and
                                   activity drivers, every one lagged.

The previous production method (damped Holt, ALPHA/BETA/PHI below) is kept only as a reported
comparison, so the change of method is measured rather than asserted.

Ridge is the mandated production configuration StandardScaler -> Ridge(alpha=RIDGE_ALPHA=5.0),
solved in closed form with numpy: predictors are standardised on the training window (population
standard deviation, as StandardScaler does), the intercept is unpenalised, and the penalty is
FIXED. There is no automatic model or penalty selection, and nothing is selected per horizon.

LEAKAGE RULE
------------
Every predictor for target month T describes a month strictly before T. `features_for()` is the
single code path that builds a feature vector -- for training rows, for validation rows and for
live forecasts -- so the rule is enforced in one place. Drivers are reconstructed from event DATES
(booking, onboarding, exit, notice), never from the current `staying_status` column, with one
documented exception: allotments whose status is Cancelled are excluded from the interval and
move-in/move-out/notice counts, because a cancelled allotment never occupied a bed.

Payments, electricity and expenses are NOT production features.

occupancy_pct_lag1 is the previous month's bed occupancy as defined by the production contract
(`monthly_occupancy()`): a physical bed is apartment_code + "|" + bed_code, occupied in month M when
an allotment on it has onboarding_date <= M's last day and actual_exit_date empty or >= M's first
day; the denominator is OCCUPANCY_BEDS_BEFORE (192) before OCCUPANCY_CAPACITY_CHANGE (2026-08) and
OCCUPANCY_BEDS_FROM (203) from it.

VALIDATION
----------
Chronological expanding-window walk-forward, one step ahead, over the last VALIDATION_MONTHS (12)
usable months, with at least MIN_TRAIN_ROWS (6) training months. For each validation month V,
models are trained only on target months strictly before V and see only revenue and drivers dated
before V. No random
split, no shuffling, no random cross-validation. MAE, RMSE, MAPE and R-squared are reported for
every model by `walk_forward_comparison()`, computed live so the figures cannot go stale.

MULTI-MONTH FORECASTS
---------------------
Revenue lags inside the forecast window are the model's own earlier predictions; revenue lags
before it are recorded actuals. Driver values for months after the last complete month are unknown
and are HELD FORWARD at the last complete month's observed values (HOLD_FORWARD_ASSUMPTION). Every
forecast point records which of its predictors were observed and which were generated.

Prediction intervals are EMPIRICAL -- the 10th/90th percentiles of the production procedure's own
walk-forward residuals at each horizon. No normality is assumed.
"""
import math
import re
from dataclasses import dataclass, field, replace

from engine.result import NOT_DETERMINABLE_TEXT

# The export snapshot. A month is usable only when the export covers all of it.
EXPORT_SNAPSHOT_DATE = "2026-08-29"

# The operating era. The single invoice before this (2023-02, Rs.2,000) is a pre-trading stub.
OPERATING_START = "2023-03"

# The previous production method, retained only as a reported comparison baseline.
ALPHA, BETA, PHI = 0.9, 0.4, 0.9
MIN_TRAIN_MONTHS = 18          # training window used by the retained damped-Holt comparison

MIN_OBSERVATIONS = 24          # complete months of revenue below which no forecast is offered
MAX_HORIZON = 6                # beyond this, drivers are held flat for too long to mean anything

# Ridge (production and revenue-history baseline).
MIN_TRAIN_ROWS = 6             # feature rows a Ridge fit needs before it may predict
VALIDATION_MONTHS = 12         # walk-forward test period: the last 12 usable months
RIDGE_ALPHA = 5.0              # mandated production penalty: StandardScaler -> Ridge(alpha=5.0)
HW_PERIOD = 12                 # Holt-Winters season length, in months

METHOD_NAME = ("multivariate Ridge regression on lagged invoiced revenue, calendar, tenant and "
               "activity drivers")
REVENUE_TARGET = "SUM(invoices.total_amount) grouped by invoices.billing_month"

REVENUE_HISTORY_FEATURES = ("rev_lag1", "rev_lag2", "rev_lag3", "rev_lag12", "rev_roll3_lag")
CALENDAR_FEATURES = ("month_num", "year")
DRIVER_FEATURES = ("tenants_lag1", "occupancy_pct_lag1", "active_tenants_occ_lag1",
                   "avg_monthly_rental_lag1", "new_bookings_lag1", "move_outs_lag1",
                   "move_ins_lag1", "notice_count_lag1")
RIDGE_FEATURES = REVENUE_HISTORY_FEATURES + CALENDAR_FEATURES + DRIVER_FEATURES

# Each driver feature is its monthly base value taken from the month before the target.
_DRIVER_BASE = {f: f[: -len("_lag1")] for f in DRIVER_FEATURES}

# Where each production feature comes from. Carried with the forecast so the lineage is inspectable.
FEATURE_SOURCES = {
    "rev_lag1": ("invoices", "total_amount, billing_month", "SUM per billing month", "T-1"),
    "rev_lag2": ("invoices", "total_amount, billing_month", "SUM per billing month", "T-2"),
    "rev_lag3": ("invoices", "total_amount, billing_month", "SUM per billing month", "T-3"),
    "rev_lag12": ("invoices", "total_amount, billing_month", "SUM per billing month", "T-12"),
    "rev_roll3_lag": ("invoices", "total_amount, billing_month",
                      "mean of the three monthly sums", "T-1, T-2, T-3"),
    "month_num": ("calendar", "target month", "month number 1-12", "known in advance"),
    "year": ("calendar", "target month", "calendar year", "known in advance"),
    "tenants_lag1": ("invoices", "tenant_id, billing_month",
                     "COUNT DISTINCT tenant_id billed in the month", "T-1"),
    "occupancy_pct_lag1": ("tenant_allotments, beds, apartments",
                           "onboarding_date, actual_exit_date, bed_id; bed_code; apartment_code",
                           "100 * COUNT DISTINCT apartment_code|bed_code with onboarding_date <= "
                           "month end and actual_exit_date NULL or >= month start / 192 beds "
                           "before 2026-08, 203 from 2026-08", "T-1"),
    "active_tenants_occ_lag1": ("tenant_allotments",
                                "tenant_id, onboarding_date, actual_exit_date, staying_status",
                                "COUNT DISTINCT tenant_id with onboarding_date <= month end and "
                                "actual_exit_date NULL or >= month start; Cancelled excluded",
                                "T-1"),
    "avg_monthly_rental_lag1": ("tenant_allotments",
                                "monthly_rental, onboarding_date, actual_exit_date, staying_status",
                                "AVG monthly_rental over the same active allotments (non-null "
                                "values; recorded zeros counted)", "T-1"),
    "new_bookings_lag1": ("tenant_allotments", "booking_date",
                          "COUNT allotments with booking_date in the month (all statuses)", "T-1"),
    "move_outs_lag1": ("tenant_allotments", "actual_exit_date, staying_status",
                       "COUNT allotments with actual_exit_date in the month; Cancelled excluded",
                       "T-1"),
    "move_ins_lag1": ("tenant_allotments", "onboarding_date, staying_status",
                      "COUNT allotments with onboarding_date in the month; Cancelled excluded",
                      "T-1"),
    "notice_count_lag1": ("tenant_allotments", "notice_date, staying_status",
                          "COUNT allotments with notice_date in the month; Cancelled excluded",
                          "T-1"),
}

# Every required feature is derivable from the export; kept so a future gap is recorded here.
NOT_DETERMINABLE_FEATURES = {}

# Occupancy denominator of the production contract: physical beds before and from the month the
# A33/A34 beds were added. `occupancy_validation()` reconciles both figures with the bed records.
OCCUPANCY_CAPACITY_CHANGE = "2026-08"
OCCUPANCY_BEDS_BEFORE = 192
OCCUPANCY_BEDS_FROM = 203
OCCUPANCY_ADDED_APARTMENTS = ("A33", "A34")


EXCLUDED_FROM_PRODUCTION = ("payments", "electricity", "expenses")

HOLD_FORWARD_ASSUMPTION = (
    "For months after the last complete month, occupancy, tenant counts, average rent, bookings, "
    "move-ins, move-outs and notices are not yet known. They are held at the last complete month's "
    "recorded values, and earlier months inside the forecast use the model's own projected "
    "revenue in place of actuals.")


# What the interval IS, carried with the forecast so no consumer can relabel it. These are not
# confidence intervals: nothing here estimates a sampling distribution or assumes normality. They
# are the 10th-90th percentiles of the production procedure's OWN errors at this horizon.
INTERVAL_BASIS = ("empirical 80% band: the 10th-90th percentiles of this method's own "
                  "out-of-sample walk-forward backtest errors at this horizon. Not a statistical "
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
    target: str = ""                              # the quantity forecast; see REVENUE_TARGET
    features: tuple = ()                          # the production predictors, in model order
    feature_provenance: tuple = ()                # per point: observed vs generated predictors
    model_comparison: dict = field(default_factory=dict)
    driver_assumption: str = ""                   # see HOLD_FORWARD_ASSUMPTION

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


# --- calendar helpers -----------------------------------------------------------------------

def _month_key(ts):
    return f"{ts[:7]}"


def _month_end(year, month):
    import calendar
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def _next_month(key):
    y, m = int(key[:4]), int(key[5:7])
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def _add_months(key, n):
    y, m = int(key[:4]), int(key[5:7])
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


# --- the target series --------------------------------------------------------------------------

def monthly_revenue_series(executor=None):
    """Complete monthly invoiced revenue, operating era only, in chronological order.

    Returns [(period_key, value), ...] where value is SUM(invoices.total_amount) over every invoice
    row whose billing_month is that period, with no is_deleted, status, reversal or cancellation
    filter and no deduplication. A month whose end falls after the export snapshot is excluded --
    a part-month would be read by the model as a collapse in trading -- and so is anything before
    the operating era. `executor` is accepted for signature compatibility and not used.
    """
    from engine.evidence_loader import load_table, money

    invoices = load_table("invoices")
    totals = (money(invoices["total_amount"]).fillna(0)
              .groupby(invoices["billing_month"].astype(str)).sum())

    out = []
    for period in sorted(totals.index):
        if not re.fullmatch(r"\d{4}-\d{2}", period):
            continue
        year, month = int(period[:4]), int(period[5:7])
        if _month_end(year, month) > EXPORT_SNAPSHOT_DATE:
            continue                                  # incomplete at the snapshot
        if period < OPERATING_START:
            continue                                  # pre-trading stub
        out.append((period, round(float(totals[period]), 2)))
    return out


# --- the drivers --------------------------------------------------------------------------------

def monthly_occupancy(periods):
    """Bed occupancy percentage FOR each month in `periods`, as the production contract defines it.

      physical bed   apartment_code + "|" + bed_code of the allotment's bed
      occupied in M  onboarding_date <= M's last day AND (actual_exit_date empty OR
                     actual_exit_date >= M's first day); no status filter
      denominator    OCCUPANCY_BEDS_BEFORE before OCCUPANCY_CAPACITY_CHANGE, OCCUPANCY_BEDS_FROM
                     from it

    Every test compares a dated event with the month's own dates. Returns
    ({period: pct}, {period: (occupied_beds, denominator)}).
    """
    import pandas as pd
    from engine.evidence_loader import load_table

    def dates(series):
        return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_localize(None)

    apartments = load_table("apartments")
    beds = load_table("beds")
    allotments = load_table("tenant_allotments")

    code_of = dict(zip(apartments["id"], apartments["apartment_code"]))
    physical = dict(zip(beds["id"], beds["apartment_id"].map(code_of).astype(str) + "|"
                        + beds["bed_code"].astype(str)))
    bed = allotments["bed_id"].map(physical)
    onboarding = dates(allotments["onboarding_date"])
    exit_date = dates(allotments["actual_exit_date"])

    pct, detail = {}, {}
    for period in periods:
        start = pd.Timestamp(f"{period}-01")
        end = pd.Timestamp(_month_end(int(period[:4]), int(period[5:7])))
        occupied = bed[(onboarding <= end) & (exit_date.isna() | (exit_date >= start))].dropna().nunique()
        capacity = (OCCUPANCY_BEDS_BEFORE if period < OCCUPANCY_CAPACITY_CHANGE
                    else OCCUPANCY_BEDS_FROM)
        pct[period] = 100.0 * occupied / capacity
        detail[period] = (int(occupied), capacity)
    return pct, detail


def monthly_drivers(periods):
    """Driver values FOR each month in `periods`: {period: {base_name: value}}.

    These are same-month values. They enter the model only through `features_for()`, which reads
    them from the month before the target, so a month's own activity never predicts that month.
    """
    import pandas as pd
    from engine.evidence_loader import load_table, money

    def dates(series):
        return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_localize(None)

    invoices = load_table("invoices")
    live = invoices[invoices["is_deleted"].astype(str).str.lower() != "true"]
    billed = live.groupby(live["billing_month"].astype(str))["tenant_id"].nunique()

    allotments = load_table("tenant_allotments")
    booking = dates(allotments["booking_date"])
    real = allotments["staying_status"].astype(str) != "Cancelled"
    onboarding = dates(allotments["onboarding_date"])
    exit_date = dates(allotments["actual_exit_date"])
    notice = dates(allotments["notice_date"])
    rent = money(allotments["monthly_rental"])
    tenant = allotments["tenant_id"]

    occupancy, _detail = monthly_occupancy(periods)

    out = {}
    for period in periods:
        start = pd.Timestamp(f"{period}-01")
        end = pd.Timestamp(_month_end(int(period[:4]), int(period[5:7])))
        in_month = lambda s: (s >= start) & (s <= end)
        active = real & (onboarding <= end) & (exit_date.isna() | (exit_date >= start))
        rents = rent[active].dropna()
        out[period] = {
            "tenants": float(billed.get(period, 0)),
            "occupancy_pct": float(occupancy[period]),
            "active_tenants_occ": float(tenant[active].nunique()),
            "avg_monthly_rental": float(rents.mean()) if len(rents) else 0.0,
            "new_bookings": float(in_month(booking).sum()),
            "move_outs": float((real & in_month(exit_date)).sum()),
            "move_ins": float((real & in_month(onboarding)).sum()),
            "notice_count": float((real & in_month(notice)).sum()),
        }
    return out


def features_for(target, revenue_at, drivers_at):
    """The production feature vector for target month `target`.

    `revenue_at(period)` and `drivers_at(period)` are only ever asked about months BEFORE
    `target`. Training, validation and live forecasting all build features here, so the leakage
    rule holds in one place rather than in three.
    """
    lag1, lag2, lag3 = (revenue_at(_add_months(target, -k)) for k in (1, 2, 3))
    row = {
        "rev_lag1": lag1, "rev_lag2": lag2, "rev_lag3": lag3,
        "rev_lag12": revenue_at(_add_months(target, -12)),
        "rev_roll3_lag": (lag1 + lag2 + lag3) / 3.0,
        "month_num": float(int(target[5:7])),
        "year": float(int(target[:4])),
    }
    previous = drivers_at(_add_months(target, -1))
    for feature in DRIVER_FEATURES:
        row[feature] = float(previous[_DRIVER_BASE[feature]])
    return row


@dataclass(frozen=True)
class FeatureTable:
    periods: tuple        # complete target months, chronological and contiguous
    revenue: dict         # period -> invoiced revenue
    drivers: dict         # period -> same-month driver values
    rows: tuple           # target months with a full feature vector (12 months of history)
    features: dict        # period -> production feature vector built from observed data


def build_feature_table(series=None):
    """The observed training table. Returns None when the series is not contiguous."""
    series = series if series is not None else monthly_revenue_series()
    if not series:
        return None
    periods = tuple(p for p, _ in series)
    for earlier, later in zip(periods, periods[1:]):
        if _next_month(earlier) != later:
            return None                          # a missing month would silently shift every lag
    revenue = dict(series)
    drivers = monthly_drivers(periods)
    rows = tuple(periods[12:])
    features = {T: features_for(T, revenue.__getitem__, drivers.__getitem__) for T in rows}
    return FeatureTable(periods, revenue, drivers, rows, features)


# --- the models ---------------------------------------------------------------------------------

def _ridge_fit(X, y, alpha):
    """Closed-form Ridge. Standardised predictors, unpenalised intercept. Returns a predictor."""
    import numpy as np

    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    mean, scale = X.mean(axis=0), X.std(axis=0)
    scale[scale == 0] = 1.0
    Z = (X - mean) / scale
    y_mean = y.mean()
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - y_mean))

    def predict(X_new):
        return ((np.asarray(X_new, dtype=float) - mean) / scale) @ beta + y_mean
    return predict


def _matrix(table, periods, names):
    return [[table.features[p][name] for name in names] for p in periods]


def _ridge_predict_one(table, target, names):
    """A Ridge prediction for `target` trained on observed rows strictly before it."""
    train = [T for T in table.rows if T < target]
    X, y = _matrix(table, train, names), [table.revenue[T] for T in train]
    return float(_ridge_fit(X, y, RIDGE_ALPHA)(_matrix(table, [target], names))[0]), RIDGE_ALPHA


def _holt(values, horizon, alpha=ALPHA, beta=BETA, phi=PHI):
    """Damped-trend exponential smoothing -- the previous production method, kept for comparison."""
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


def _holt_winters(values, horizon, period=HW_PERIOD):
    """Additive-trend, additive-season Holt-Winters. Smoothing weights are chosen by in-sample
    one-step error over `values` only. None when fewer than two full seasons are available."""
    values = [float(v) for v in values]
    if len(values) < 2 * period:
        return None
    first = sum(values[:period]) / period
    second = sum(values[period:2 * period]) / period
    best = None
    for a in (0.1, 0.3, 0.5, 0.7, 0.9):
        for b in (0.05, 0.1, 0.2):
            for g in (0.05, 0.1, 0.3):
                level, trend = first, (second - first) / period
                season = [v - first for v in values[:period]]
                sse = 0.0
                for t in range(period, len(values)):
                    sse += (values[t] - (level + trend + season[t - period])) ** 2
                    previous = level
                    level = a * (values[t] - season[t - period]) + (1 - a) * (level + trend)
                    trend = b * (level - previous) + (1 - b) * trend
                    season.append(g * (values[t] - level) + (1 - g) * season[t - period])
                if best is None or sse < best[0]:
                    best = (sse, level, trend, season)
    _, level, trend, season = best
    n = len(values)
    return [level + step * trend + season[n - period + (step - 1) % period]
            for step in range(1, horizon + 1)]


def _backtest(values, horizon):
    """Rolling-origin evaluation of the retained damped-Holt comparison. (mape, residuals, folds)."""
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


def _metrics(actual, predicted):
    errors = [a - p for a, p in zip(actual, predicted)]
    n = len(errors)
    mean_actual = sum(actual) / n
    sst = sum((a - mean_actual) ** 2 for a in actual)
    sse = sum(e * e for e in errors)
    return {
        "MAE": round(sum(abs(e) for e in errors) / n, 2),
        "RMSE": round(math.sqrt(sse / n), 2),
        "MAPE_pct": round(sum(abs(e) / abs(a) for e, a in zip(errors, actual)) / n * 100, 2),
        "R2": round(1 - sse / sst, 4) if sst else None,
        "n": n,
    }


# --- validation ---------------------------------------------------------------------------------

MODEL_LABELS = {
    "revenue_history_ridge": "Revenue-history baseline (Ridge on revenue lags only)",
    "holt_winters": "Holt-Winters (additive trend and 12-month season)",
    "seasonal_naive": "Seasonal naive (same month last year)",
    "naive_last_value": "Naive (same as the previous month)",
    "multivariate_ridge": "Multivariate Ridge (production)",
    "previous_damped_holt": "Previous production method: damped Holt (comparison only)",
}
PRODUCTION_MODEL = "multivariate_ridge"

# Plain names for the owner. Internal labels such as "damped Holt" are not owner vocabulary.
OWNER_MODEL_NAMES = {
    "revenue_history_ridge": "a regression on past revenue alone",
    "holt_winters": "a seasonal trend method",
    "seasonal_naive": "repeating the same month last year",
    "naive_last_value": "simply repeating the previous month's figure",
    "previous_damped_holt": "the trend method this forecast previously used",
}


def validation_months(table):
    """The last VALIDATION_MONTHS usable months, each with at least MIN_TRAIN_ROWS training rows
    and enough history for every compared model."""
    periods = list(table.periods)
    usable = [T for i, T in enumerate(table.rows)
              if i >= MIN_TRAIN_ROWS and periods.index(T) >= 2 * HW_PERIOD]
    return tuple(usable[-VALIDATION_MONTHS:])


def walk_forward_comparison(table=None):
    """One-month-ahead expanding-window walk-forward, same months for every model."""
    table = table if table is not None else build_feature_table()
    if table is None:
        return {}
    months = validation_months(table)
    if not months:
        return {}
    predictions = {name: [] for name in MODEL_LABELS}
    actuals = []
    for V in months:
        history = [table.revenue[p] for p in table.periods if p < V]
        value, _alpha = _ridge_predict_one(table, V, RIDGE_FEATURES)
        predictions["multivariate_ridge"].append(value)
        predictions["revenue_history_ridge"].append(
            _ridge_predict_one(table, V, REVENUE_HISTORY_FEATURES)[0])
        predictions["holt_winters"].append(_holt_winters(history, 1)[0])
        predictions["seasonal_naive"].append(table.revenue[_add_months(V, -12)])
        predictions["naive_last_value"].append(table.revenue[_add_months(V, -1)])
        predictions["previous_damped_holt"].append(_holt(history, 1)[0])
        actuals.append(table.revenue[V])
    models = {name: dict(_metrics(actuals, preds), label=MODEL_LABELS[name])
              for name, preds in predictions.items()}
    most_accurate = min(models, key=lambda name: models[name]["MAPE_pct"])
    return {
        "design": "expanding-window walk-forward, one month ahead, over the last "
                  f"{VALIDATION_MONTHS} usable months, trained strictly before each validation "
                  f"month on at least {MIN_TRAIN_ROWS} months",
        "validation_months": months,
        "horizon_months": 1,
        "models": models,
        "production_model": PRODUCTION_MODEL,
        "most_accurate_by_mape": most_accurate,
        "ridge_alpha": RIDGE_ALPHA,
    }


def _ridge_path(table, origin, horizon):
    """Forecast origin+1 .. origin+horizon from information up to and including `origin` only.

    Returns (predictions, provenance, alpha). Revenue after `origin` is the model's own
    projection; drivers after `origin` are held at `origin`'s observed values.
    """
    train = [T for T in table.rows if T <= origin]
    X, y = _matrix(table, train, RIDGE_FEATURES), [table.revenue[T] for T in train]
    alpha = RIDGE_ALPHA
    predict = _ridge_fit(X, y, alpha)

    predicted, provenance = {}, []
    held = table.drivers[origin]
    for step in range(1, horizon + 1):
        target = _add_months(origin, step)
        revenue_at = lambda p: table.revenue[p] if p <= origin else predicted[p]
        drivers_at = lambda p: table.drivers[p] if p <= origin else held
        row = features_for(target, revenue_at, drivers_at)
        predicted[target] = float(predict([[row[name] for name in RIDGE_FEATURES]])[0])

        generated = [name for name, lag in (("rev_lag1", 1), ("rev_lag2", 2), ("rev_lag3", 3),
                                            ("rev_lag12", 12))
                     if _add_months(target, -lag) > origin]
        if any(name in generated for name in ("rev_lag1", "rev_lag2", "rev_lag3")):
            generated.append("rev_roll3_lag")
        if _add_months(target, -1) > origin:
            generated.extend(DRIVER_FEATURES)
        provenance.append({
            "period": target,
            "observed": tuple(n for n in RIDGE_FEATURES if n not in generated),
            "generated": tuple(n for n in RIDGE_FEATURES if n in generated),
        })
    return predicted, tuple(provenance), alpha


def _ridge_backtest(table, horizon):
    """Walk-forward evaluation of the exact production procedure at `horizon`.

    Returns (mape, residuals, folds, naive_mape). Each origin trains only on rows up to itself.
    Forecast steps fall inside the same test period as `validation_months()`, so the one-month
    figure is the walk-forward comparison's own.
    """
    last = table.periods[-1]
    test = set(validation_months(table))
    origins = [O for i, O in enumerate(table.rows)
               if i >= MIN_TRAIN_ROWS - 1 and _add_months(O, 1) in test
               and _add_months(O, horizon) <= last]
    residuals, pcts, naive = [], [], []
    for origin in origins:
        predicted, _prov, _alpha = _ridge_path(table, origin, horizon)
        for step in range(1, horizon + 1):
            target = _add_months(origin, step)
            actual = table.revenue[target]
            if actual:
                pcts.append(abs(predicted[target] - actual) / abs(actual) * 100.0)
                naive.append(abs(table.revenue[origin] - actual) / abs(actual) * 100.0)
        final = _add_months(origin, horizon)
        residuals.append(table.revenue[final] - predicted[final])
    mape = round(sum(pcts) / len(pcts), 2) if pcts else None
    naive_mape = round(sum(naive) / len(naive), 2) if naive else None
    return mape, residuals, len(residuals), naive_mape


def occupancy_validation():
    """Checks on the contract occupancy over the complete target months, and the reconciliation
    of its two denominators with the physical beds in the bed records."""
    from engine.evidence_loader import load_table

    periods = [p for p, _ in monthly_revenue_series()]
    pct, _detail = monthly_occupancy(periods)
    apartments = load_table("apartments")
    beds = load_table("beds")
    code = beds["apartment_id"].map(dict(zip(apartments["id"], apartments["apartment_code"])))
    physical = code.astype(str) + "|" + beds["bed_code"].astype(str)
    return {
        "months": len(pct),
        "above_100": sum(1 for value in pct.values() if value > 100),
        "physical_beds": int(physical.nunique()),
        "physical_beds_before_added": int(physical[~code.isin(OCCUPANCY_ADDED_APARTMENTS)].nunique()),
    }


# --- drivers ----------------------------------------------------------------------------------

def evaluate_drivers(executor=None):
    """What the production model uses, what it cannot use, and what it excludes by design.

    Reported whether or not a driver is used. A driver that could not be derived is a finding the
    owner is entitled to, not an absence to stay quiet about.
    """
    check = occupancy_validation()
    used = (
        ("revenue history", "Invoiced revenue one, two, three and twelve months earlier, and the "
                            "average of the last three months."),
        ("calendar", "The month number and year of the month being forecast."),
        ("tenants billed", "Distinct tenants invoiced in the previous month."),
        ("occupancy rate", (
            "Bed occupancy in the previous month: beds with a tenant staying at any point in "
            f"that month, divided by {OCCUPANCY_BEDS_BEFORE} beds before "
            f"{OCCUPANCY_CAPACITY_CHANGE} and {OCCUPANCY_BEDS_FROM} beds from it, when the "
            f"{' and '.join(OCCUPANCY_ADDED_APARTMENTS)} beds were added. The bed records hold "
            f"{check['physical_beds']} beds, {check['physical_beds_before_added']} of them outside "
            f"{' and '.join(OCCUPANCY_ADDED_APARTMENTS)}. Across {check['months']} months, "
            f"{check['above_100']} are above 100%.")),
        ("active tenants", "Distinct tenants holding an allotment during the previous month."),
        ("average monthly rent", "Average recorded monthly rent across those allotments."),
        ("new bookings", "Bookings recorded in the previous month."),
        ("move-ins", "Tenants who moved in during the previous month."),
        ("move-outs", "Tenants who moved out during the previous month."),
        ("notices", "Notices recorded in the previous month."),
    )
    drivers = [{"driver": name, "verdict": "USED", "evidence": text} for name, text in used]
    drivers.append({
        "driver": "payments, electricity and expenses",
        "verdict": "EXCLUDED",
        "evidence": "Not used by the production model, by specification.",
    })
    return tuple(drivers)


# --- public entry point -----------------------------------------------------------------------

def forecast_revenue(horizon=1, executor=None):
    """Forecast monthly invoiced revenue `horizon` months beyond the last complete month."""
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
                f"I can forecast up to {MAX_HORIZON} months ahead. Further out, the tenant and "
                f"booking activity the forecast depends on would have to be held unchanged for "
                f"so long that the projection would stop reflecting anything recorded, so a "
                f"longer forecast would be a guess dressed as a figure. {NOT_DETERMINABLE_TEXT}"))

    series = monthly_revenue_series(executor)
    if len(series) < MIN_OBSERVATIONS:
        return RevenueForecast(
            available=False,
            observations=len(series),
            not_determinable_reason=(
                f"Forecasting needs at least {MIN_OBSERVATIONS} complete months of invoiced "
                f"revenue; the export provides {len(series)}. {NOT_DETERMINABLE_TEXT}"))

    table = build_feature_table(series)
    if table is None or len(table.rows) <= MIN_TRAIN_ROWS:
        return RevenueForecast(
            available=False,
            observations=len(series),
            not_determinable_reason=(
                "The invoiced revenue history has a gap or too few months with a full year of "
                f"prior history to fit the forecast model. {NOT_DETERMINABLE_TEXT}"))

    origin = table.periods[-1]
    predicted, provenance, alpha = _ridge_path(table, origin, horizon)
    mape, residuals, folds, naive_mape = _ridge_backtest(table, horizon)
    comparison = walk_forward_comparison(table)

    # Empirical 80% band from the procedure's own residuals at this horizon; the band is the
    # method's demonstrated error, not an assumed distribution.
    band_low = band_high = None
    if len(residuals) >= 5:
        ordered = sorted(residuals)
        band_low = _percentile(ordered, 0.10)
        band_high = _percentile(ordered, 0.90)

    points = []
    for step in range(1, horizon + 1):
        key = _add_months(origin, step)
        value = predicted[key]
        lower = round(value + band_low, 2) if band_low is not None else None
        upper = round(value + band_high, 2) if band_high is not None else None
        points.append(ForecastPoint(period=key, value=round(value, 2), lower=lower, upper=upper))

    limitations = [
        "A forecast is a projection from recorded history, not a commitment. It assumes trading "
        "continues broadly as it has.",
        "This forecasts invoiced revenue -- the total of invoices raised for each billing month, "
        "including invoices that appear more than once for the same tenant and month. It is a "
        "different measure from the revenue recorded in the accounts.",
    ]
    if horizon > 1:
        limitations.append(HOLD_FORWARD_ASSUMPTION)
    models = comparison.get("models", {})
    if models:
        production = models[PRODUCTION_MODEL]["MAPE_pct"]
        better = sorted((m["MAPE_pct"], name) for name, m in models.items()
                        if name != PRODUCTION_MODEL and m["MAPE_pct"] < production)
        if better:
            listed = "; ".join(f"{OWNER_MODEL_NAMES[name]} was off by about {mape}%"
                               for mape, name in better)
            limitations.append(
                f"On the same test months, one month ahead, simpler methods were more accurate "
                f"than this forecast's model, which was off by about {production}% on average: "
                f"{listed}.")
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
        training_start=table.periods[0],
        training_end=origin,
        observations=len(series),
        last_actual=table.revenue[origin],
        interval_basis=INTERVAL_BASIS if band_low is not None else "",
        backtest={
            "mape_pct": mape,
            "folds": folds,
            "min_training_months": MIN_TRAIN_ROWS,
            "ridge_alpha": alpha,
            "compared_against": {"naive_last_value_mape_pct": naive_mape},
        },
        drivers=evaluate_drivers(executor),
        limitations=tuple(limitations),
        target=REVENUE_TARGET,
        features=RIDGE_FEATURES,
        feature_provenance=provenance,
        model_comparison=comparison,
        driver_assumption=HOLD_FORWARD_ASSUMPTION if horizon > 1 else "",
    )


def _naive_mape(values, horizon):
    """Last-value benchmark over the retained comparison's folds, recomputed so it is checkable."""
    pcts = []
    for cut in range(MIN_TRAIN_MONTHS, len(values) - horizon + 1):
        last = values[cut - 1]
        for a in values[cut:cut + horizon]:
            if a:
                pcts.append(abs(last - a) / abs(a) * 100.0)
    return round(sum(pcts) / len(pcts), 2) if pcts else None


def scenario_forecast(occupancy_rate=None, occupied_beds=None, executor=None):
    """"What would revenue be at 80% occupancy?" -- refused, with the reason.

    Occupancy enters the model as one lagged predictor among measures that move together. The
    model is not validated for setting one of them to a chosen level, so a figure would rest on a
    relationship the evidence does not establish.
    """
    return RevenueForecast(
        available=False,
        drivers=evaluate_drivers(executor),
        not_determinable_reason=(
            "I can't give a revenue figure for a chosen occupancy level. Last month's occupancy "
            "is one of several recorded measures the forecast uses, alongside tenant counts, "
            "rent, bookings, move-ins, move-outs and notices, and those measures move together. "
            "Its predictions were tested only on recorded months, not as a what-if tool: setting "
            "occupancy to a chosen level while holding everything else fixed describes a "
            "situation the records never contain, so any figure would rest on a relationship "
            "the evidence does not establish. " + NOT_DETERMINABLE_TEXT))


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
