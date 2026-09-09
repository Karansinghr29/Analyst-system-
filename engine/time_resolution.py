"""
time_resolution.py -- Phase 3, stage [4]. question_understanding_spec.md 5.

Four rules this module exists to enforce, all of them refusals rather than computations:

  5.1 step 2 -- the date field is ALWAYS the metric's documented `date_field`. `created_at` is
      never substituted; the one documented exception (M.MAINT.001/002, business_dimensions.md
      17) is honoured because the registry itself says so, not by special-casing here.
  5.1 step 3 -- a period outside the metric's `historical_policy` coverage returns the boundary,
      never a silently truncated or extrapolated figure.
  5.1 step 4 -- snapshot-only metrics cannot answer historical questions. Occupancy Defs A-D
      have no date parameter at all; "what was occupancy in March" must route to M.OCC.005, not
      to a re-filtered snapshot. v_tenant_aging is CURRENT_DATE-dependent, so a historical aging
      question is NOT_DETERMINABLE unless the date is the export snapshot date itself.
  5.3     -- no YoY/trend for maintenance (20 months) or EB (1-5 months), regardless of phrasing.

All reference dates are fixed to the export snapshot, never the machine clock: a question asked
twice must resolve to the same period (answer_contract.md 6 determinism).
"""
import re
from dataclasses import dataclass

from engine.intent_models import ResolvedTime, ResolvedComparison

# conflicts.md C.019 / DQ.018. The same constant Phase 2's execution.py uses.
EXPORT_SNAPSHOT_DATE = "2026-08-29"
SNAPSHOT_YEAR, SNAPSHOT_MONTH = 2026, 8

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})(?:-(\d{2}))?\b")
_YEAR = re.compile(r"\b(20\d{2})\b")

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Phrases that signal the question is about a PAST period rather than current state. Used to
# detect the snapshot/historical mismatch in 5.1 step 4.
_HISTORICAL_MARKERS = (
    "last month", "last year", "last quarter", "previous month", "previous year",
    "was ", "were ", "in march", "in april", "trend", "over time", "history",
    "historical", "monthly", "by month", "each month", "past ", "back then",
    "year on year", "year-on-year", "yoy", "month on month", "month-over-month",
)

# "last 3 months" and its ordinary synonyms. One pattern rather than four phrase lists, so a
# wording nobody enumerated ("recent 6 months") resolves on the same rule as the ones that were.
_MONTH_WINDOW = re.compile(
    r"(?<![a-z])(?:last|past|previous|recent|trailing|latest)\s+(?P<n>\d{1,2})\s+months?"
    r"(?![a-z])")

_MONTH_SPAN = re.compile(
    r"(?<![a-z])from\s+(september|february|november|december|january|october|august|march|april|june|july|sept|may|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b.{0,12}?\bto\s+(september|february|november|december|january|october|august|march|april|june|july|sept|may|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)(?![a-z])")

_YOY_MARKERS = ("year on year", "year-on-year", "yoy", "vs last year", "versus last year",
                "compared to last year", "same period last year")

_TREND_MARKERS = ("trend", "trending", "over time", "by month", "monthly", "each month",
                  "month by month", "history", "historical")

# Future relative periods and explicit forecast/prediction language. These are never answered
# by inventing values; the understander may still answer the recorded subject without them.
_FUTURE_PERIOD_MARKERS = (
    "next month", "next year", "next quarter", "coming month", "coming year",
    "upcoming month", "upcoming year", "following month", "the next month",
)
_FORECAST_MARKERS = (
    "forecast", "prediction", "predict", "projected", "projection", "estimate for",
    "will we make", "will we earn", "will we collect", "going to make", "going to earn",
    "expected revenue", "expected to",
)


def asks_unsupported_forecast(question):
    """True when the question asks for a future period or an explicit forecast/prediction.

    Returns (True, label) or (False, ""). Label is a short period/forecast tag for disclosure,
    not a computed date range to invent against.
    """
    q = (question or "").lower()
    # A month the records already cover is a historical question, whatever verb it was asked
    # with. "Forecast revenue for June 2026" names a recorded month, and the recorded figure is
    # the answer -- treating it as a forecast request refused a question the evidence answers.
    if _names_a_recorded_month(question):
        return False, ""
    for phrase in _FUTURE_PERIOD_MARKERS:
        if phrase in q:
            return True, phrase
    for phrase in _FORECAST_MARKERS:
        if phrase in q:
            return True, "forecast"
    return False, ""


def _names_a_recorded_month(question):
    """True when the question names one calendar month that is not in the future.

    Imported lazily: `forecasting` reads the period parser in this module, and the dependency
    only runs at call time.
    """
    label, start, _end = parse_period(question)
    if not start or not re.fullmatch(r"\d{4}-\d{2}", label or ""):
        return False
    from engine import forecasting

    return forecasting.horizon_for_period(label) <= 0


def strip_forecast_language(question):
    """Remove future/forecast phrasing. Used only for subject extraction — never to rewrite a
    forecast request into an all-time metric execution.
    """
    text = question or ""
    for phrase in sorted(_FUTURE_PERIOD_MARKERS + _FORECAST_MARKERS, key=len, reverse=True):
        text = re.sub(re.escape(phrase), " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,;:?!.-")
    return text


def has_explicit_period_intent(question):
    """True when the owner named a time period (relative, month name, ISO, or clear remnant).

    Used to forbid silent all-time execution when the period cannot be resolved.
    """
    q = (question or "").lower()
    if asks_unsupported_forecast(q)[0]:
        return True
    label, start, _end = parse_period(q)
    if label != "all-time" and start is not None:
        return True
    if label != "all-time" and label in ("this year", "last year", "this month", "last month",
                                          "next month", "next year", "next quarter"):
        return True
    # Residual signals after typo repair failures: month/year/quarter words with deixis,
    # or tokens that are near month names but not close enough to auto-correct.
    if re.search(r"\b(20\d{2})\b", q):
        return True
    if re.search(r"\b(this|last|next|current|previous|coming|upcoming)\s+"
                 r"(month|months|year|years|quarter|quarters)\b", q):
        return True
    for name in _MONTH_NAMES:
        if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", q):
            return True
    # Near-miss month tokens still count as period intent (typo that normalize missed).
    # Require same initial letter and edit distance 1 so ordinary English ("full", "really")
    # is never treated as a month name ("july", "april").
    _COMMON_NON_MONTH = frozenset({
        "full", "really", "early", "yearly", "monthly", "quarter", "period", "before",
        "after", "about", "around", "since", "until", "while", "where", "there", "their",
        "these", "those", "which", "whose", "what", "when", "from", "into", "over",
    })
    for tok in re.findall(r"[a-z]{4,}", q):
        if tok in _COMMON_NON_MONTH:
            continue
        if tok in _MONTH_NAMES:
            return True
        for name in ("january", "february", "march", "april", "june",
                     "july", "august", "september", "october", "november", "december"):
            if tok[0] != name[0]:
                continue
            if abs(len(tok) - len(name)) > 1:
                continue
            dist = sum(a != b for a, b in zip(tok, name)) + abs(len(tok) - len(name))
            if dist == 1:
                return True
    # A bare month/year/quarter word (outside "by month" trend phrasing) is period intent.
    if re.search(r"\b(month|months|year|years|quarter|quarters)\b", q):
        if not re.search(r"\b(by|per|each)\s+months?\b", q):
            if not re.search(r"\b(monthly|histor(?:y|ical)|trend|over time)\b", q):
                return True
    return False


def period_is_resolved(question):
    """True when parse_period found a concrete non-all-time period or a forecast label."""
    if asks_unsupported_forecast(question)[0]:
        return True
    label, start, _ = parse_period(question)
    return label != "all-time"


def is_bounded_period(resolved_time):
    """True when a real period was requested -- one month or a window of them.

    A single month already had this protection; a multi-month window did not, so "recent 3
    months revenue" resolved its window correctly and then executed the all-time total against
    it. The window is a period like any other, and answering it with every month on record is
    the same substitution the single-month guard exists to prevent.
    """
    if resolved_time is None:
        return False
    label = (resolved_time.period_label or "")
    if not label or label == "all-time":
        return False
    return bool(resolved_time.start)


def is_single_month_period(resolved_time):
    """True when ResolvedTime names one calendar month (this/last/named month)."""
    if resolved_time is None:
        return False
    label = (resolved_time.period_label or "")
    start = resolved_time.start or ""
    if label in ("this month", "last month", "current month", "previous month"):
        return True
    if re.match(r"^\d{4}-\d{2}$", label):
        return True
    if start and re.match(r"^\d{4}-\d{2}-\d{2}$", start):
        end = resolved_time.end or ""
        return bool(end and start[:7] == end[:7])
    return False


class TimeResolutionError(Exception):
    pass


def _parse_coverage(historical_policy):
    """Extract the documented coverage window from the registry's prose `historical_policy`.
    Returns (start, end) as ISO strings, or ('','') when the policy names no dates (snapshot
    metrics such as M.AR.001C: 'not a time series')."""
    dates = _ISO_DATE.findall(historical_policy or "")
    full = [f"{y}-{m}-{d or '01'}" for y, m, d in dates]
    if not full:
        return "", ""
    return min(full), max(full)


def _coverage_forbids_yoy(historical_policy):
    """5.3's guard, read from the registry's OWN text rather than a hard-coded metric list:
    metric_reconstruction.md wrote the prohibition into the historical_policy column itself
    ('Do not manufacture a YoY comparison for maintenance'), and the narrow-coverage domains
    state their month counts there too."""
    p = (historical_policy or "").lower()
    if "do not manufacture a yoy" in p or "do not manufacture a year" in p:
        return True, "The metric's own historical_policy forbids a YoY comparison."
    m = re.search(r"\((\d+)\s+months?", p)
    if m and int(m.group(1)) < 24:
        return True, (f"Coverage is {m.group(1)} months -- under the 24 months a "
                      f"year-on-year comparison requires (question_understanding_spec.md 5.3).")
    m2 = re.search(r"only (\d+) months?", p)
    if m2 and int(m2.group(1)) < 24:
        return True, (f"Coverage is only {m2.group(1)} months -- insufficient for a "
                      f"year-on-year comparison (5.3).")
    return False, ""


def _is_snapshot_only(spec):
    """5.1 step 4: metrics with no historical form at all."""
    p = (spec.historical_policy or "").lower()
    d = (spec.date_field or "").lower()
    return ("not a time series" in p or "current-state" in p or "current-value" in d
            or "not applicable" in d and "not applicable" in p)


def _is_current_date_dependent(spec):
    """M.RISK.002 / v_tenant_aging: buckets were computed once, at query time, against
    CURRENT_DATE and were not preserved as a series."""
    return "current_date" in (spec.date_field or "").lower()


def named_months(question):
    """Month names the question mentions, IN THE ORDER THE QUESTION MENTIONS THEM.

    Returns a tuple of (year, month_number), de-duplicated, first mention first.

    Order matters and used not to. The previous implementation walked `_MONTH_NAMES` and
    returned the first entry that matched, so the answer depended on the order of that
    dictionary rather than the order of the owner's words: "August revenue vs July revenue"
    resolved to July, because July precedes August in the table. The owner then received a
    comparison of two months they had not asked about.

    A year mentioned anywhere in the question applies to every month named in it; without one
    the snapshot year is used, exactly as before.
    """
    # Lowercased here rather than at the call site: this is called both from `parse_period`
    # (which already lowercases) and directly with the owner's raw words, and a month name
    # must be recognised either way.
    q = (question or "").lower()
    ym = _YEAR.search(q)
    year = int(ym.group(1)) if ym else SNAPSHOT_YEAR

    hits = []
    for name, num in _MONTH_NAMES.items():
        for m in re.finditer(r"(?<![a-z])" + name + r"(?![a-z])", q):
            hits.append((m.start(), len(name), num))

    # Longest match wins at a position, so "sept" is not also counted as "sep".
    hits.sort(key=lambda h: (h[0], -h[1]))
    out, seen, consumed = [], set(), -1
    for start, length, num in hits:
        if start < consumed:
            continue                      # inside a longer month name already taken
        consumed = start + length
        if num in seen:
            continue
        seen.add(num)
        out.append((year, num))
    return tuple(out)


def parse_month_pair(question):
    """An explicit two-month comparison, as (current_triple, baseline_triple), or None.

    "August revenue vs July revenue" names both periods itself. The first month mentioned is
    the one being asked about and the second is what it is measured against -- the reading any
    English speaker gives it. Nothing is inferred when only one month is named; that case still
    falls through to the ordinary one-period-plus-shift path.
    """
    months = named_months(question)
    if len(months) < 2:
        return None
    (cy, cm), (by, bm) = months[0], months[1]
    return (
        (f"{cy}-{cm:02d}", f"{cy}-{cm:02d}-01", _month_end(cy, cm)),
        (f"{by}-{bm:02d}", f"{by}-{bm:02d}-01", _month_end(by, bm)),
    )


def parse_period(question):
    """Deterministic period extraction. Returns (label, start, end) with ISO strings, or
    ('all-time', None, None) when the question names no period."""
    q = (question or "").lower()

    m = _ISO_DATE.search(q)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if d:
            iso = f"{y}-{mo}-{d}"
            return iso, iso, iso
        return f"{y}-{mo}", f"{y}-{mo}-01", _month_end(int(y), int(mo))

    if "next month" in q or "coming month" in q or "upcoming month" in q or "following month" in q:
        y, mo = (SNAPSHOT_YEAR, SNAPSHOT_MONTH + 1) if SNAPSHOT_MONTH < 12 else (SNAPSHOT_YEAR + 1, 1)
        return "next month", f"{y}-{mo:02d}-01", _month_end(y, mo)

    if "next year" in q or "coming year" in q or "upcoming year" in q:
        y = SNAPSHOT_YEAR + 1
        return "next year", f"{y}-01-01", f"{y}-12-31"

    if "next quarter" in q:
        # Snapshot month is 1-indexed; next calendar quarter after the snapshot month.
        qtr_start_mo = ((SNAPSHOT_MONTH - 1) // 3 + 1) * 3 + 1
        y = SNAPSHOT_YEAR
        if qtr_start_mo > 12:
            qtr_start_mo = 1
            y += 1
        end_mo = qtr_start_mo + 2
        return ("next quarter", f"{y}-{qtr_start_mo:02d}-01", _month_end(y, end_mo))

    # When both "this month" and "last month" appear (comparison questions), the PRIMARY
    # period is the current one; baseline is resolved separately by resolve_comparison.
    has_this_month = "this month" in q or "current month" in q
    has_last_month = "last month" in q or "previous month" in q
    if has_this_month and has_last_month:
        return ("this month", f"{SNAPSHOT_YEAR}-{SNAPSHOT_MONTH:02d}-01",
                _month_end(SNAPSHOT_YEAR, SNAPSHOT_MONTH))

    if has_last_month:
        y, mo = (SNAPSHOT_YEAR, SNAPSHOT_MONTH - 1) if SNAPSHOT_MONTH > 1 else (SNAPSHOT_YEAR - 1, 12)
        return "last month", f"{y}-{mo:02d}-01", _month_end(y, mo)

    if has_this_month:
        return ("this month", f"{SNAPSHOT_YEAR}-{SNAPSHOT_MONTH:02d}-01",
                _month_end(SNAPSHOT_YEAR, SNAPSHOT_MONTH))

    # A rolling window of whole months: "last 3 months", "past 6 months", "recent 3 months",
    # "previous 3 months". One shape, four common wordings, and none of them resolved -- every
    # one fell through to all-time, so "last 3 months revenue" silently answered with the whole
    # ledger. The window ENDS at the last complete month, because the snapshot month is partial
    # and including it would report a part-month as a whole one.
    # An explicit span: "from June to August". Both months are named, and taking the first as
    # the period answers about June a question asked about three months. ("August vs July" is a
    # different shape -- two periods to compare, not one span -- and is left to the comparison
    # resolver, which is why only the "from ... to ..." wording is read as a span here.)
    span = _MONTH_SPAN.search(q)
    if span:
        first, second = _MONTH_NAMES.get(span.group(1)), _MONTH_NAMES.get(span.group(2))
        if first and second:
            year = int(_YEAR.search(q).group(1)) if _YEAR.search(q) else SNAPSHOT_YEAR
            start_year = year - 1 if second < first else year
            return (f"{start_year}-{first:02d} to {year}-{second:02d}",
                    f"{start_year}-{first:02d}-01", _month_end(year, second))

    window = _MONTH_WINDOW.search(q)
    if window:
        months = int(window.group("n"))
        if 1 <= months <= 36:
            end_y, end_mo = SNAPSHOT_YEAR, SNAPSHOT_MONTH
            if _month_end(end_y, end_mo) > EXPORT_SNAPSHOT_DATE:
                end_y, end_mo = (end_y, end_mo - 1) if end_mo > 1 else (end_y - 1, 12)
            start_index = (end_y * 12 + end_mo - 1) - (months - 1)
            start_y, start_mo = divmod(start_index, 12)
            start_mo += 1
            return (f"last {months} months",
                    f"{start_y}-{start_mo:02d}-01", _month_end(end_y, end_mo))

    if "last quarter" in q or "previous quarter" in q:
        # Quarter containing the month before the snapshot month's quarter.
        cur_q = (SNAPSHOT_MONTH - 1) // 3  # 0..3
        if cur_q == 0:
            y, qtr = SNAPSHOT_YEAR - 1, 3
        else:
            y, qtr = SNAPSHOT_YEAR, cur_q - 1
        start_mo = qtr * 3 + 1
        return ("last quarter", f"{y}-{start_mo:02d}-01", _month_end(y, start_mo + 2))

    if "this quarter" in q or "current quarter" in q:
        qtr = (SNAPSHOT_MONTH - 1) // 3
        start_mo = qtr * 3 + 1
        return ("this quarter", f"{SNAPSHOT_YEAR}-{start_mo:02d}-01",
                _month_end(SNAPSHOT_YEAR, start_mo + 2))

    if "last year" in q or "previous year" in q:
        y = SNAPSHOT_YEAR - 1
        return "last year", f"{y}-01-01", f"{y}-12-31"

    if "this year" in q or "current year" in q or "ytd" in q or "year to date" in q:
        return "this year", f"{SNAPSHOT_YEAR}-01-01", EXPORT_SNAPSHOT_DATE

    named = named_months(q)
    if named:
        y, num = named[0]
        return f"{y}-{num:02d}", f"{y}-{num:02d}-01", _month_end(y, num)

    ym = _YEAR.search(q)
    if ym:
        y = int(ym.group(1))
        return str(y), f"{y}-01-01", f"{y}-12-31"

    return "all-time", None, None


def _month_end(year, month):
    if month == 12:
        return f"{year}-12-31"
    import calendar
    return f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def resolve(spec, question="", explicit_period=None):
    """Stage [4]. Returns a ResolvedTime. Never raises for a business-level refusal -- the
    refusal is recorded on the object (within_coverage / yoy_permitted) so the planner can
    turn it into a NOT_DETERMINABLE plan with the boundary stated."""
    label, start, end = explicit_period or parse_period(question)
    cov_start, cov_end = _parse_coverage(spec.historical_policy)
    q = (question or "").lower()
    forecast_asked, forecast_label = asks_unsupported_forecast(question)

    wants_history = any(mk in q for mk in _HISTORICAL_MARKERS) or (start is not None)
    snapshot_only = _is_snapshot_only(spec)
    current_date_dependent = _is_current_date_dependent(spec)

    mode = "historical" if (wants_history and not snapshot_only) else "snapshot"

    within = True
    note = ""
    forecast_unsupported = False

    if forecast_asked and (label in ("next month", "next year", "next quarter")
                           or forecast_label == "forecast"
                           or (start and cov_end and start > cov_end)
                           or (start and start[:7] > EXPORT_SNAPSHOT_DATE[:7])):
        forecast_unsupported = True
        within = False
        if label == "all-time" and forecast_label == "forecast":
            label = "forecast"
        note = (
            f"A forecast for {forecast_label or label} cannot be determined from the available "
            f"exported evidence. The export is a recorded snapshot through "
            f"{EXPORT_SNAPSHOT_DATE}; future values are not invented.")

    elif snapshot_only and wants_history:
        within = False
        note = (f"{spec.metric_id} has no historical form -- its documented coverage is "
                f"'{spec.historical_policy}'. A past-period question cannot be answered by "
                f"re-filtering a snapshot definition that has no date parameter "
                f"(question_understanding_spec.md 5.1 step 4).")
        mode = "snapshot"

    elif current_date_dependent and start and start[:10] != EXPORT_SNAPSHOT_DATE:
        within = False
        note = (f"{spec.metric_id} is inherently CURRENT_DATE-dependent (conflicts.md C.019 / "
                f"DQ.018): its buckets were computed once at query time and not preserved as a "
                f"series. A historical position is only available for the export's own snapshot "
                f"date, {EXPORT_SNAPSHOT_DATE}.")

    elif start and cov_start and cov_end:
        if end and end < cov_start:
            within = False
            note = (f"The requested period ({label}) ends before this metric's documented "
                    f"coverage, which runs {cov_start} to {cov_end}.")
        elif start > cov_end:
            within = False
            # A start after coverage that is also a future relative period is a forecast gap.
            if forecast_asked or label.startswith("next "):
                forecast_unsupported = True
                note = (
                    f"A forecast for {label} cannot be determined from the available exported "
                    f"evidence. Documented coverage runs {cov_start} to {cov_end}.")
            else:
                note = (f"The requested period ({label}) starts after this metric's documented "
                        f"coverage, which runs {cov_start} to {cov_end}.")
        elif start < cov_start or (end and end > cov_end):
            note = (f"The requested period ({label}) extends beyond documented coverage "
                    f"({cov_start} to {cov_end}); only the covered portion is answerable, and "
                    f"the boundary is stated rather than the figure silently truncated.")

    yoy_forbidden, yoy_reason = _coverage_forbids_yoy(spec.historical_policy)
    asks_yoy = any(mk in q for mk in _YOY_MARKERS)
    asks_trend = any(mk in q for mk in _TREND_MARKERS)
    yoy_permitted = not (yoy_forbidden and (asks_yoy or asks_trend))
    yoy_note = yoy_reason if (yoy_forbidden and (asks_yoy or asks_trend)) else ""

    return ResolvedTime(
        date_field=spec.date_field,          # 5.1 step 2: the documented field, never substituted
        period_label=label, start=start, end=end, mode=mode,
        coverage_start=cov_start, coverage_end=cov_end,
        within_coverage=within, coverage_note=note,
        yoy_permitted=yoy_permitted, yoy_note=yoy_note,
        forecast_unsupported=forecast_unsupported,
    )


def resolve_comparison(spec, question="", current=None, baseline=None):
    """5.1 step 5: resolve BOTH periods independently and reject the comparison if either fails
    coverage or snapshot/historical compatibility. Comparing a snapshot-only metric across two
    dates is not meaningful and must be flagged, never silently computed."""
    cur = current or resolve(spec, question)

    # An explicit pair ("August vs July") states BOTH periods. Shifting back one month from the
    # first would answer a different question than the one asked.
    if baseline is None and current is None:
        pair = parse_month_pair(question)
        if pair is not None:
            cur_triple, base_triple = pair
            cur = resolve(spec, question, explicit_period=cur_triple)
            baseline = resolve(spec, question, explicit_period=base_triple)

    if baseline is None:
        if cur.period_label == "last month":
            base_label, base_start, base_end = _shift_months(cur, 1)
        elif cur.period_label == "this month":
            y, mo = (SNAPSHOT_YEAR, SNAPSHOT_MONTH - 1) if SNAPSHOT_MONTH > 1 else (SNAPSHOT_YEAR - 1, 12)
            base_label, base_start, base_end = "previous month", f"{y}-{mo:02d}-01", _month_end(y, mo)
        elif cur.start:
            base_label, base_start, base_end = _shift_months(cur, 1)
        else:
            base_label, base_start, base_end = "all-time", None, None
        baseline = resolve(spec, question, explicit_period=(base_label, base_start, base_end))

    if _is_snapshot_only(spec):
        return ResolvedComparison(
            baseline=baseline, current=cur, valid=False,
            reason=(f"{spec.metric_id} is snapshot-only ('{spec.historical_policy}'). "
                    f"Comparing it across two dates would mean reapplying snapshot logic at "
                    f"dates it was never designed to support -- flagged rather than computed "
                    f"(question_understanding_spec.md 5.1 step 5)."))

    if not cur.within_coverage or not baseline.within_coverage:
        failing = cur if not cur.within_coverage else baseline
        return ResolvedComparison(
            baseline=baseline, current=cur, valid=False,
            reason=f"One period falls outside documented coverage: {failing.coverage_note}")

    if not cur.yoy_permitted or not baseline.yoy_permitted:
        return ResolvedComparison(
            baseline=baseline, current=cur, valid=False,
            reason=cur.yoy_note or baseline.yoy_note)

    if cur.mode != baseline.mode:
        return ResolvedComparison(
            baseline=baseline, current=cur, valid=False,
            reason=(f"Snapshot/historical mismatch: current period is {cur.mode}, baseline is "
                    f"{baseline.mode}. analytics_execution_spec.md 2.3 requires both periods to "
                    f"use the identical metric definition and conventions."))

    return ResolvedComparison(baseline=baseline, current=cur, valid=True)


def _shift_months(rt, n):
    m = re.match(r"^(\d{4})-(\d{2})", rt.start or "")
    if not m:
        return "preceding period", None, None
    y, mo = int(m.group(1)), int(m.group(2))
    mo -= n
    while mo < 1:
        mo += 12
        y -= 1
    return f"{y}-{mo:02d}", f"{y}-{mo:02d}-01", _month_end(y, mo)
