"""
change_detection.py -- Phase 6. The "What changed?" engine.

What it does: for a metric with a monthly series, compare the latest complete period against the
previous comparable one and classify the direction of the change.

What it deliberately does NOT do: decide whether the change MATTERS.

    insight_generation_spec.md 2 condition 3: "this specification does not fix the threshold
    value (an implementation-phase/business decision)."

No materiality threshold exists anywhere in the exported evidence or in any specification. So
this module reports `MATERIALITY_UNDEFINED` for every change it detects. That is not a gap in
the implementation -- it is the honest state of the evidence, and the Phase 6 brief requires it
in those words: "If materiality threshold is not defined, state that it is unavailable rather
than inventing one."

Consequently the classification vocabulary has four values and one of them is deliberately
never produced: INCREASE / DECREASE / NO_CHANGE (exact equality only) / UNAVAILABLE. There is no
"immaterial" classification, because calling a change immaterial requires the threshold that
does not exist.
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine.result import NOT_DETERMINABLE_TEXT

INCREASE = "INCREASE"
DECREASE = "DECREASE"
NO_CHANGE = "NO_CHANGE"                  # exact equality; never a threshold judgement
UNAVAILABLE = "UNAVAILABLE"              # no comparable prior period exists

# The requested comparison names a period the snapshot has only PARTIALLY captured. Distinct
# from UNAVAILABLE: the data exists and a to-date figure can be stated, but the two periods are
# not like-for-like, so a change between them would be an artefact of the shorter window rather
# than a movement in the business.
PARTIAL_PERIOD = "PARTIAL_PERIOD"

MATERIALITY_UNDEFINED = (
    "Materiality is not determinable: insight_generation_spec.md 2 condition 3 leaves the "
    "threshold to a business decision, and no threshold exists in the exported evidence. The "
    "direction and size of the change are reported; whether it is significant is an owner "
    "judgement this system will not substitute for. " + NOT_DETERMINABLE_TEXT)

# Metrics that expose a month-keyed series and are therefore comparable period-over-period.
# Each is already validated at monthly grain (metric_reconstruction.md REV.02 / EXP / COLL).
COMPARABLE_MONTHLY_METRICS = ("M.REV.002", "M.PNL.001", "M.COL.002")

def comparable_metrics_for(dimension, registry=None):
    """Every registered metric that can be compared across months AT a given grain.

    Derived, not listed. A metric qualifies when two things the system already declares are both
    true of it:

      * its CALCULATOR accepts the narrowing -- the executor's own contract, so a metric that
        would refuse the filter is never offered one; and
      * its OUTPUT is a monthly series -- declared by the registry as a per-month unit.

    Both facts already exist for their own reasons, so a metric added to the registry later with
    an apartment-grained monthly series becomes comparable at that grain the moment it is
    registered, with nothing here to update. A hardcoded list would have to be remembered
    instead, and would silently be wrong the first time it was not.
    """
    import inspect

    from engine.calculators import REGISTRY, NOT_IMPLEMENTED

    registry = registry or SemanticRegistry()
    kwarg = f"{dimension}_code"
    out = []
    for metric_id in registry.all_ids():
        calc_fn = REGISTRY.get(metric_id)
        if calc_fn is None or calc_fn == NOT_IMPLEMENTED or not callable(calc_fn):
            continue
        try:
            accepts = kwarg in inspect.signature(calc_fn).parameters
        except (TypeError, ValueError):
            continue
        if not accepts:
            continue
        spec = registry.get(metric_id)
        # The registry states how a metric aggregates. "per month" is what makes it a series
        # rather than a single figure -- the same declaration that tells a reader whether the
        # metric answers "how much" or "how much, month by month".
        if "per month" in (spec.aggregation or "").lower():
            out.append(metric_id)
    return tuple(out)


@dataclass(frozen=True)
class Change:
    metric_id: str
    metric_name: str
    classification: str
    current_period: str = ""
    current_value: object = None
    previous_period: str = ""
    previous_value: object = None
    absolute_change: object = None
    percentage_change: object = None
    materiality: str = MATERIALITY_UNDEFINED
    trust_level: str = ""
    caveat: str = ""
    conflict_ids: tuple = ()
    dq_ids: tuple = ()
    evidence_sources: tuple = ()
    unavailable_reason: str = ""
    coverage_note: str = ""
    unit: str = ""                          # the engine's own unit, for presentation only

    # -- what the OWNER asked for, kept separate from what was computed -----------------------
    #
    # These exist so a caller can always tell the two apart. When a requested period cannot be
    # compared, the answer must say so against the period that was asked about -- not quietly
    # report a different pair of months under the original question.
    requested_current: str = ""
    requested_previous: str = ""
    current_is_partial: bool = False
    partial_current_value: object = None    # the to-date figure, when one exists
    partial_coverage_note: str = ""
    # A complete-month comparison offered as a clearly labelled ALTERNATIVE. Never a
    # substitute: it answers a different question and is presented as such.
    alternative: object = None              # Change | None

    @property
    def detected(self):
        """True only when a like-for-like change was actually computed.

        PARTIAL_PERIOD is deliberately excluded: a partial month against a full one is not a
        measured movement, and anything treating `detected` as "there is a change to report"
        must not pick it up.
        """
        return self.classification in (INCREASE, DECREASE, NO_CHANGE)

    @property
    def requested_comparison_met(self):
        """Whether the periods compared are the periods the question asked for."""
        if not (self.requested_current or self.requested_previous):
            return self.detected
        return bool(self.detected
                    and self.current_period == self.requested_current
                    and self.previous_period == self.requested_previous)


# The export snapshot. Any month whose end falls after it is only PARTIALLY captured.
EXPORT_SNAPSHOT_DATE = "2026-08-29"


def _complete_months(months):
    """Drop periods the export only partially covers, and report which were dropped.

    This matters more than it looks. The snapshot is 2026-08-29, so both 2026-09 (a few
    forward-dated postings) and 2026-08 (29 of 31 days) are incomplete. Comparing a partial
    month against a complete one manufactures a dramatic false signal -- on this dataset it
    reported revenue "falling 99.86%", which is an artifact of the export cut-off and not a
    business event. Reporting that to an owner as a change would be exactly the data-artifact-
    as-business-signal failure business_reasoning_spec.md 2's OBSERVATION gating rule exists to
    prevent.
    """
    import calendar
    keep, dropped = [], []
    for m in months:
        try:
            y, mo = int(m[:4]), int(m[5:7])
            month_end = f"{y}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"
        except (ValueError, IndexError):
            keep.append(m)
            continue
        if month_end <= EXPORT_SNAPSHOT_DATE:
            keep.append(m)
        else:
            dropped.append(m)
    return keep, dropped


def _series_of(answer):
    """The month-keyed dict a monthly metric returns, or None."""
    for r in answer.results:
        if isinstance(r.value, dict) and r.value:
            keys = list(r.value)
            if all(isinstance(k, str) and len(k) >= 7 and k[4] == "-" for k in keys[:3]):
                return r, r.value
    return None, None


def _numeric(v, component=None):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, dict):
        if component and component in v:
            return _numeric(v[component])
        # A composite month value (e.g. P&L's {revenue, expenses, ...}) is not a single series
        # unless the caller names which component is the change.
        return None
    return None


class ChangeDetector:
    def __init__(self, registry: SemanticRegistry = None, gate: TrustGate = None,
                 executor: MetricExecutor = None):
        self.registry = registry or SemanticRegistry()
        self.gate = gate or TrustGate(self.registry)
        self.executor = executor or MetricExecutor(registry=self.registry, gate=self.gate)

    def detect(self, metric_id, current_period=None, previous_period=None,
               series_component=None, **calc_kwargs):
        """Compare two periods of one metric.

        Default: the last two complete months in the series.
        When current/previous periods are supplied, those series keys are used so an explicit
        question period is not silently replaced by whatever months are latest.

        series_component: for composite monthly rows (P&L), which field to compare
        (e.g. 'expenses', 'revenue', 'net_profit').

        `calc_kwargs` are the narrowings the metric itself supports (e.g. `apartment_code`).
        They are handed to the executor unchanged, so the series compared is the one that
        metric produces under that narrowing -- a comparison of one apartment's months is the
        apartment metric's own series, not the estate series wearing an apartment label. A
        metric whose calculation cannot take the narrowing refuses in the executor, exactly as
        it does everywhere else.
        """
        if metric_id not in self.registry:
            return Change(metric_id=metric_id, metric_name=metric_id,
                          classification=UNAVAILABLE,
                          unavailable_reason=f"{metric_id!r} is not a semantic metric. "
                                             f"{NOT_DETERMINABLE_TEXT}")

        spec = self.registry.get(metric_id)
        decision = self.gate.authorize(metric_id)
        answer = self.executor.execute(metric_id, **calc_kwargs)

        base = dict(metric_id=metric_id, metric_name=spec.semantic_name,
                    trust_level=decision.effective_level, caveat=spec.caveat_text,
                    conflict_ids=spec.conflict_ids, dq_ids=spec.dq_ids,
                    coverage_note=spec.historical_policy[:200])

        if decision.effective_level in ("SHOW_BOTH", "BLOCK"):
            # A period comparison on a conflicted metric would need one definition to compare
            # against, and choosing one is exactly the silent resolution the trust policy
            # forbids. The conflict is the finding.
            return Change(classification=UNAVAILABLE,
                          unavailable_reason=(
                              f"{metric_id} is {decision.effective_level}: competing definitions "
                              f"exist, and comparing periods would require choosing one. "
                              f"Conflicting definitions exist."),
                          **base)

        result, series = _series_of(answer)
        if result is not None and getattr(result, "unit", ""):
            base["unit"] = result.unit
        if series is None:
            # Named by the measure, not by its identifier: the owner-facing sanitizer strips an
            # identifier and left this sentence beginning mid-clause, which read as a broken
            # answer rather than a reason. "Month-keyed series" went with it -- that is how the
            # data is shaped, not something an owner asked about.
            measure = getattr(answer, "metric_name", "") or "This measure"
            return Change(classification=UNAVAILABLE,
                          unavailable_reason=(
                              f"{measure} is not recorded month by month, so there is nothing "
                              f"to compare between periods. {NOT_DETERMINABLE_TEXT}"),
                          **base)

        months, excluded = _complete_months(sorted(series))
        if excluded:
            base["coverage_note"] = (
                f"Period(s) {', '.join(excluded)} excluded as incomplete at the export snapshot "
                f"({EXPORT_SNAPSHOT_DATE}). " + base["coverage_note"])

        # What the question asked for, recorded before anything is resolved against the series,
        # so every return below can be checked against it.
        base["requested_current"] = _match_series_key(series, current_period) or (
            current_period or "")
        base["requested_previous"] = _match_series_key(series, previous_period) or (
            previous_period or "")

        if current_period or previous_period:
            # Explicit question periods must be honored. Never silently replace with
            # the latest complete pair when the asked months are missing/incomplete.
            if not (current_period and previous_period):
                return Change(classification=UNAVAILABLE,
                              unavailable_reason=(
                                  f"A period comparison needs both the current and prior "
                                  f"periods the question asked for. {NOT_DETERMINABLE_TEXT}"),
                              **base)
            cur_p = _match_series_key(series, current_period)
            prev_p = _match_series_key(series, previous_period)
            if not cur_p or not prev_p:
                return Change(classification=UNAVAILABLE,
                              unavailable_reason=(
                                  f"The requested periods are not both present in the "
                                  f"exported series. {NOT_DETERMINABLE_TEXT}"),
                              **base)
            if cur_p not in months or prev_p not in months:
                # The requested comparison is NOT silently replaced by the latest complete
                # pair. Doing that answered a question the owner did not ask, under the
                # heading of the one they did -- the disclosure sat below a headline figure
                # for two different months, which reads as the requested answer.
                #
                # Instead: say plainly that the asked-for comparison cannot be established,
                # give the to-date figure where one exists, and attach the latest complete
                # comparison as a separate, clearly labelled alternative.
                incomplete = [p for p in (cur_p, prev_p) if p not in months]
                partial_value = None
                if cur_p in series:
                    partial_value = _numeric(series[cur_p], series_component)

                alternative = None
                if len(months) >= 2:
                    alternative = self.detect(
                        metric_id,
                        current_period=months[-1], previous_period=months[-2],
                        series_component=series_component, **calc_kwargs)

                return Change(
                    classification=PARTIAL_PERIOD,
                    current_period=cur_p, previous_period=prev_p,
                    current_is_partial=True,
                    partial_current_value=(round(partial_value, 2)
                                           if partial_value is not None else None),
                    partial_coverage_note=(
                        f"{', '.join(incomplete)} is not a whole period in this export: the "
                        f"records stop at {EXPORT_SNAPSHOT_DATE}."),
                    alternative=alternative,
                    unavailable_reason=(
                        f"The comparison you asked for covers {', '.join(incomplete)}, which "
                        f"the exported records capture only up to {EXPORT_SNAPSHOT_DATE}. "
                        f"Comparing a part-period against a whole one would show the shorter "
                        f"window, not a movement in the business, and no day-level series "
                        f"exists to shorten the earlier period to match."),
                    **base)
        else:
            if len(months) < 2:
                return Change(classification=UNAVAILABLE,
                              unavailable_reason=(
                                  f"{metric_id} has {len(months)} period(s) of coverage; a "
                                  f"comparison needs two. {NOT_DETERMINABLE_TEXT}"),
                              **base)
            cur_p, prev_p = months[-1], months[-2]

        cur_v, prev_v = (_numeric(series[cur_p], series_component),
                         _numeric(series[prev_p], series_component))

        base["evidence_sources"] = tuple(result.evidence_sources[:8])

        if cur_v is None or prev_v is None:
            return Change(classification=UNAVAILABLE,
                          current_period=cur_p, previous_period=prev_p,
                          current_value=series[cur_p], previous_value=series[prev_p],
                          unavailable_reason=(
                              f"{metric_id}'s monthly values are composite, so no single "
                              f"quantity changes between periods. Comparing one component "
                              f"would be a definition choice this layer may not make. "
                              f"{NOT_DETERMINABLE_TEXT}"),
                          **base)

        delta = round(cur_v - prev_v, 2)
        pct = round(delta / abs(prev_v) * 100, 2) if prev_v else None
        classification = INCREASE if delta > 0 else DECREASE if delta < 0 else NO_CHANGE

        if series_component:
            base["metric_name"] = f"{spec.semantic_name} ({series_component})"

        return Change(classification=classification,
                      current_period=cur_p, current_value=round(cur_v, 2),
                      previous_period=prev_p, previous_value=round(prev_v, 2),
                      absolute_change=delta, percentage_change=pct,
                      **base)

    def detect_all(self, metric_ids=None):
        """Every comparable KPI. Metrics that cannot be compared are RETURNED as UNAVAILABLE
        with their reason -- never dropped, or the briefing would imply nothing changed."""
        ids = metric_ids or COMPARABLE_MONTHLY_METRICS
        return tuple(self.detect(m) for m in ids)

    def summary(self, changes=None):
        changes = changes or self.detect_all()
        out = {INCREASE: [], DECREASE: [], NO_CHANGE: [], UNAVAILABLE: []}
        for c in changes:
            out[c.classification].append(c.metric_id)
        return {k: tuple(v) for k, v in out.items()}


def _match_series_key(series, period):
    """Map a period label/ISO start onto a key in a month-keyed series."""
    if not period or not series:
        return ""
    token = str(period)[:7]
    for key in series:
        if str(key).startswith(token):
            return key
    return ""


def ladder_for(change: Change):
    """business_reasoning_spec.md's chain for one detected change. The ladder STOPS at
    OBSERVATION: naming a cause requires driver analysis (root_cause.py), and asserting one
    here would be the unsupported causal claim the specification forbids."""
    if not change.detected:
        return {
            "FACT": change.unavailable_reason,
            "CALCULATION": "",
            "OBSERVATION": "",
            "materiality": change.materiality,
        }
    direction = "rose" if change.classification == INCREASE else (
        "fell" if change.classification == DECREASE else "was unchanged")
    return {
        "FACT": (f"{change.metric_name} for {change.current_period} is "
                 f"{change.current_value}; for {change.previous_period} it was "
                 f"{change.previous_value}."),
        "CALCULATION": (f"Change = {change.absolute_change}"
                        + (f" ({change.percentage_change}%)"
                           if change.percentage_change is not None else "")),
        "OBSERVATION": (f"{change.metric_name} {direction} between {change.previous_period} "
                        f"and {change.current_period}."),
        "materiality": change.materiality,
        "note": ("No cause is asserted at this stage. Establishing why the value moved requires "
                 "driver analysis over documented dependency edges "
                 "(analytics_execution_spec.md 2.6)."),
    }
