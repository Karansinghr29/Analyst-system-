"""
question_understanding.py -- Phase 3, pipeline stages [1]-[4] of
ai_analytics_architecture.md 3, specified by question_understanding_spec.md.

    [1] Intent  ->  [2] Metric resolution  ->  [3] Dimension resolution  ->  [4] Time resolution
                 ->  handed to the Trust & Conflict Gate (Layer 3, already built in Phase 2)

Two hard boundaries, both from the Phase 3 brief and from the spec itself:

  * **No language model.** Resolution is deterministic phrase matching over the required
    concept-to-family lookup artifact (concept_map.py). This layer is what an eventual LLM
    CALLS; it is not itself an LLM. A caller that already knows the concept can bypass the
    matcher entirely via `understand(question, concept_name=...)`.

  * **This layer never decides trust.** It resolves what was asked. Whether the resolved metric
    may be answered, and in what shape, is the Trust Gate's verdict -- delegated in
    analytics_planner.py, never recomputed here (ai_agent_roles.md 3: the Trust Gatekeeper's
    verdict is binding).

question_understanding_spec.md 1: "Each stage can terminate the pipeline early with a
clarification request or a NOT_DETERMINABLE result -- this is correct behavior, not a fallback
for failure."
"""
import re
from dataclasses import dataclass
from typing import Optional

from engine.semantic_registry import SemanticRegistry
from engine import concept_map
from engine import dimension_resolution as dimres
from engine import time_resolution as timeres
from engine.intent_models import (
    LOOKUP, FILTERED_LOOKUP, TREND, COMPARISON, ANOMALY, DRIVER, RISK_SCAN, RECOMMENDATION,
    META, INTENT_REASONING_CEILING, ClarificationRequest, ResolvedMetric, NOT_DETERMINABLE_TEXT,
)


# --- [1] Intent classification (question_understanding_spec.md 2) ------------------------------
# Ordered most-specific first: a question carrying both driver and recommendation markers gets
# BOTH intents ("A single question may carry more than one intent ... the system must decompose
# it into its constituent intents").

_INTENT_MARKERS = (
    (META, ("why can't you", "why cant you", "why can you not", "what does that mean",
            "what do you mean", "how do you define", "what is the definition",
            "why are there two", "which definition", "explain the conflict",
            "why do they disagree", "how reliable")),
    # "why" is the whole of the driver intent, and the tense that follows it is incidental.
    # "why revenue fell?" and "revenue yen koranjuthu?" (normalised to "revenue why decreased")
    # carry it without any of the auxiliaries the list below enumerates.
    (DRIVER, (" why ", "why did", "why has", "why was", "why were", "why are", "why is",
              "what caused", "what drove", "reason for", "root cause", "explain the drop",
              "explain the fall", "explain the rise", "why the", "what's behind",
              "whats behind")),
    (RECOMMENDATION, ("what should", "what do you recommend", "recommend", "what action",
                      "what next", "should we", "advise", "suggestion", "what to do")),
    (ANOMALY, ("anomaly", "anomalies", "unusual", "look off", "looks off", "strange",
               "out of the ordinary", "spike", "anything odd", "outlier", " odd ",
               "abnormal", "irregular", "out of place")),
    (RISK_SCAN, ("risk", "risks", "risky", "exposure", "losing money", "where are we losing",
                 "biggest problems", "what should i worry", "worry about", "should worry",
                 "concerns", "concerning", "data quality",
                 "data issues", "need attention", "needs attention", "require attention",
                 "problem areas", "trouble", "any problem", "any problems", "any issue",
                 "any issues", "anything to worry", "anything concerning",
                 "where is the problem", "where are the problems",
                 "area problem", "area problems")),
    (COMPARISON, ("compared to", "versus", " vs ", "better than", "worse than", "which property",
                  "which is best", "compare", "against last", "year on year", "year-on-year",
                  "yoy", "month on month",
                  # Directional change language is period comparison / change detection,
                  # not a bare lookup — even without the word "compare".
                  "increase", "increased", "increasing", "went up", "going up", "gone up",
                  "rise", "rose", "risen", "grew", "grown", "growing",
                  "decrease", "decreased", "decreasing", "went down", "going down",
                  "fall", "fell", "drop", "dropped", "lower than", "higher than",
                  "from last month", "than last month", "vs last month",
                  # Bare infinitives: "did revenue go up?" carries the same meaning as "went
                  # up" and was the only one of the pair recognised.
                  "go up", "go down", "goes up", "goes down", "come down", "came down")),
    # Trend is asked far more often by a verb of motion than by the word "trend": "how is
    # revenue doing?", "revenue epdi poguthu?" (normalised to "how trending"), "is revenue
    # improving?". Without these the question resolved to a bare lookup and came back with an
    # all-time total -- a level, answering a question about direction.
    (TREND, ("trend", "trending", "over time", "by month", "monthly", "each month",
             "month by month", "history of", "historical", "getting better", "getting worse",
             "improving", "worsening", "doing", "improve", "improved", "declining",
             "growing", "shrinking", "picking up", "holding up", "on track",
             # "What happened to revenue?" asks what the measure did over time, not what it
             # totals. Phrased with the measure as its object, so the bare "what's happening?"
             # -- the whole-business question -- is not caught here.
             "happened to", "happened with", "happening to", "happening with")),
)


# Past-tense and change language that the intent markers do not catch. "How did A12's rent
# change?" carries no comparison or trend marker, so it classifies as a plain lookup -- harmless
# for a metric with history behind it, and quietly wrong for one without.
_PAST_MARKERS = (
    " was ", " were ", " used to ", " previously ", " originally ", " before ",
    " change", " changed", " changing", " history", " historically", " last year",
    " last month", " earlier ", " since ",
)


def _asks_about_the_past(question):
    return any(m in f" {(question or '').lower()} " for m in _PAST_MARKERS)


# "How did revenue change?" asks how a measure moved between periods. The marker table below
# catches "increased", "went up", "compared to" and the rest, but not the plainest word for it,
# so the question fell through to a lookup and came back with the all-time total -- an answer to
# a question about a level, given to a question about a movement.
_MEASURE_MOVED = re.compile(
    r"(?<![a-z])(?:change[ds]?|changing|move[ds]?|movement|shift(?:ed)?|vari(?:ed|ation))"
    r"(?![a-z])")

# ...except when the question names no measure at all. "What changed?" is the whole-business
# review, which has its own workflow and must keep it; reading it as a period comparison would
# ask the owner which measure they meant when they deliberately named none.
_WHOLE_BUSINESS_CHANGE = (
    "what changed", "what has changed", "what's changed", "whats changed", "what moved",
    "any changes", "anything changed", "what changes", "anything change",
)


def _asks_how_a_measure_moved(padded_lower_question):
    q = padded_lower_question
    if any(phrase in q for phrase in _WHOLE_BUSINESS_CHANGE):
        return False
    return bool(_MEASURE_MOVED.search(q))


def classify_intents(question):
    """Returns a tuple of intents, most-specific first. Never empty: a question with no marker
    is a lookup (the base case), and gains FILTERED_LOOKUP if it carries a dimension filter."""
    q = f" {(question or '').lower()} "
    # "monthly rent" is the NAME of the recorded amount (the source column is literally
    # monthly_rental), the way "monthly salary" names a figure rather than a history of one.
    # Read as a TREND marker it turned "what's A12's monthly rent?" into a request for a
    # month-by-month rent series that no evidence supports. "monthly revenue" is left alone --
    # there the word does mean the series.
    q = q.replace("monthly rent", " rent ").replace("monthly rental", " rent ")
    found = []
    if _asks_how_a_measure_moved(q):
        found.append(COMPARISON)
    for intent, markers in _INTENT_MARKERS:
        if any(m in q for m in markers):
            found.append(intent)
    if not found:
        found = [LOOKUP]
    return tuple(found)


# --- [2] Metric resolution (question_understanding_spec.md 3) ----------------------------------

@dataclass(frozen=True)
class UnderstoodQuestion:
    question: str
    intents: tuple
    reasoning_ceiling: str
    metric: Optional[ResolvedMetric] = None
    dimension_request: Optional[dimres.DimensionRequest] = None
    time: Optional[object] = None                 # ResolvedTime (of the primary member)
    time_by_metric: Optional[dict] = None         # metric_id -> ResolvedTime, for every member
    time_note: str = ""                           # partial-family-coverage disclosure
    comparison: Optional[object] = None           # ResolvedComparison
    clarification: Optional[ClarificationRequest] = None
    not_determinable_reason: str = ""
    breakdown_requested: bool = False
    driver_requested: bool = False
    decision_requested: bool = False
    forecast_note: str = ""                       # unsupported forecast, recorded subject preserved
    provenance: tuple = ()

    @property
    def terminated_early(self):
        return self.clarification is not None or bool(self.not_determinable_reason)


class QuestionUnderstander:
    def __init__(self, registry: SemanticRegistry = None):
        self.registry = registry or SemanticRegistry()

    # -- public entry point --------------------------------------------------------------------

    def understand(self, question, concept_name=None, metric_id=None) -> UnderstoodQuestion:
        """`concept_name` / `metric_id` let a caller that has already resolved the concept
        (a Phase 4 LLM, or a test) skip the phrase matcher without skipping any of the
        validation that follows it."""
        from engine.question_normalize import normalize_owner_question

        original_question = question or ""
        question, stripped_roles = normalize_owner_question(original_question)
        prov = []
        if stripped_roles:
            prov.append(f"[0] stripped role address labels {list(stripped_roles)} "
                        f"(routing uses the business question only)")

        if not question.strip():
            return UnderstoodQuestion(
                question=original_question, intents=(LOOKUP,), reasoning_ceiling="CALCULATION",
                clarification=ClarificationRequest(
                    kind="referential",
                    question="What would you like to know about the business?",
                    options=("Revenue", "Collections", "Tenant dues", "Occupancy",
                             "Biggest risks"),
                    reason=("The message named a role or title only, with no business subject. "
                            "Asking which measure to answer avoids inventing one."),
                ),
                provenance=tuple(prov + ["[0] empty after role-label strip -> clarification"]),
            )

        intents = classify_intents(question)
        ceiling = max((INTENT_REASONING_CEILING[i] for i in intents),
                      key=lambda s: _LADDER.index(s))
        prov.append(f"[1] intents={list(intents)} (question_understanding_spec.md 2)")

        # question_understanding_spec.md 6.1, "Which property is best?": this question has NO
        # metric-resolution ambiguity -- it is well-formed but asks to compare across a
        # degenerate dimension. The spec requires it terminate at DIMENSION resolution with the
        # specific "only 1 property exists" statement, "not a generic NOT_DETERMINABLE" -- so
        # the guard must run BEFORE metric resolution, or an unmatched concept would produce
        # exactly the generic message 4.2 forbids.
        early_dims = dimres.extract(question)
        if early_dims.compare_across in dimres.DEGENERATE_DIMENSIONS:
            prov.append(f"[3] degenerate-dimension guard fired before metric resolution: the "
                        f"question compares across {early_dims.compare_across!r} "
                        f"(question_understanding_spec.md 4.2 / 6.1)")
            return UnderstoodQuestion(
                question=question, intents=intents, reasoning_ceiling=ceiling,
                dimension_request=early_dims,
                not_determinable_reason=(
                    f"Only 1 distinct value of {early_dims.compare_across!r} exists in the "
                    f"exported data (business_dimensions.md). There is nothing to compare, so "
                    f"no ranking can be produced -- this is a fact about the exported data, not "
                    f"a limitation of the calculation. {NOT_DETERMINABLE_TEXT}"),
                provenance=tuple(prov))

        resolved, clarification, nd_reason = self._resolve_metric(
            question, intents, concept_name, metric_id, prov)
        if clarification is not None or nd_reason:
            # Prefer a short clarification when the subject is still unspecified after noise
            # removal, rather than a bare "Not determinable" dump for an underspecified ask.
            if (nd_reason and clarification is None and not concept_name and not metric_id
                    and not concept_map.match(question)
                    and LOOKUP in intents and len(intents) == 1
                    and (len(question.split()) <= 5
                         or any(p in question.lower() for p in (
                             "the numbers", "some numbers", "the figures", "the data",
                             "show me numbers", "give me numbers")))):
                return UnderstoodQuestion(
                    question=question, intents=intents, reasoning_ceiling=ceiling,
                    clarification=ClarificationRequest(
                        kind="referential",
                        question="Which measure should I look up?",
                        options=("Revenue", "Collections", "Tenant dues", "Occupancy",
                                 "Expenses"),
                        reason=("The question did not name a catalogued business concept. "
                                "Clarifying the subject avoids guessing a nearby metric."),
                    ),
                    provenance=tuple(prov + ["[2] underspecified lookup -> clarification"]),
                )
            return UnderstoodQuestion(
                question=question, intents=intents, reasoning_ceiling=ceiling,
                metric=resolved, clarification=clarification,
                not_determinable_reason=nd_reason, provenance=tuple(prov))

        # Explicit period that still failed to resolve must NEVER fall through to all-time.
        if (timeres.has_explicit_period_intent(question)
                and not timeres.period_is_resolved(question)
                and not timeres.asks_unsupported_forecast(question)[0]):
            prov.append("[4] explicit period intent unresolved -> clarification "
                        "(never silent all-time)")
            return UnderstoodQuestion(
                question=question, intents=intents, reasoning_ceiling=ceiling,
                metric=resolved,
                clarification=ClarificationRequest(
                    kind="referential",
                    question=("Which time period should I use? I could not resolve the period "
                              "in your question, and I will not answer with an all-time figure "
                              "by default."),
                    options=("This month", "Last month", "August 2026",
                             "This year", "All recorded time"),
                    reason=("An explicit period was requested but could not be resolved to a "
                            "documented coverage window. Silent all-time execution would "
                            "misrepresent the question."),
                ),
                provenance=tuple(prov),
            )

        dim_request = dimres.extract(question)

        # A metric whose own definition already delivers the requested breakdown (M.EXP.002 IS
        # "Expenses by category"; M.REV.002 IS "Revenue by month") satisfies that request by
        # itself. Re-applying the same dimension as an extra GROUP BY would be an undocumented
        # regrouping of an already-grouped metric, which dimension_resolver.py correctly
        # refuses -- so the dimension is consumed here rather than passed on.
        delivered, delivered_filters = (), ()
        c = concept_map.concept(resolved.concept)
        if c is not None and (c.delivers_breakdown or c.delivers_filter):
            delivered = tuple(d for d in dim_request.group_by if d in c.delivers_breakdown)
            delivered_filters = tuple(d for d in dim_request.filters
                                      if d in c.delivers_filter)
            if delivered or delivered_filters:
                dim_request = dimres.DimensionRequest(
                    filters={k: v for k, v in dim_request.filters.items()
                             if k not in delivered_filters},
                    group_by=tuple(d for d in dim_request.group_by if d not in delivered),
                    compare_across=dim_request.compare_across,
                    unresolved_entities=dim_request.unresolved_entities,
                    matched_phrases=dim_request.matched_phrases,
                )
            if delivered:
                prov.append(f"[3] breakdown {list(delivered)} is delivered by "
                            f"{resolved.metric_ids[0]}'s own definition, not applied as an "
                            f"extra grouping")
            if delivered_filters:
                prov.append(f"[3] filter {list(delivered_filters)} is already applied by "
                            f"{resolved.metric_ids[0]}'s own definition "
                            f"({self.registry.get(resolved.metric_ids[0]).semantic_name!r}), "
                            f"not re-applied on top")

        prov.append(f"[3] dimensions requested: filters={dim_request.filters}, "
                    f"group_by={list(dim_request.group_by)}, "
                    f"compare_across={dim_request.compare_across!r} "
                    f"(question_understanding_spec.md 4)")
        if dim_request.filters and FILTERED_LOOKUP not in intents and LOOKUP in intents:
            intents = tuple(FILTERED_LOOKUP if i == LOOKUP else i for i in intents)

        # Time must be resolved for EVERY family member, not just the first. Members of one
        # family can carry genuinely different time semantics: the AR family's Def A/B are
        # ledger-backed and historical, while Def C is the application's currently-stored
        # balance ("not a time series") and Def D is a frozen 2026-04 migration snapshot.
        # Resolving against metric_ids[0] alone would silently assume A's semantics for all
        # four -- exactly the snapshot/historical substitution 5.1 step 4 forbids.
        primary = self.registry.get(resolved.metric_ids[0])
        forecast_asked, forecast_label = timeres.asks_unsupported_forecast(question)
        if forecast_asked:
            # Forecasting is its own capability. Do NOT execute an all-time (or any) metric
            # lookup as if it answered the future-period question. Return an owner-facing
            # capability gap — not a clarification that traps the next unrelated question.
            from engine import analysis_capability as acap
            subject = resolved.concept.replace("_", " ")
            cap = acap.lookup_capability("forecasting")
            label = forecast_label or "next period"
            forecast_note = (
                f"I can show historical {subject}, but I can't reliably forecast {label} "
                f"because a forecasting method isn't currently available."
            )
            prov.append(f"[4] capability=forecasting (NOT_IMPLEMENTED); refusing silent "
                        f"all-time execution for future request ({label!r})")
            return UnderstoodQuestion(
                question=question, intents=intents, reasoning_ceiling=ceiling,
                metric=resolved, dimension_request=dim_request,
                forecast_note=forecast_note,
                not_determinable_reason=forecast_note,
                provenance=tuple(prov),
            )

        time_question = question
        forecast_note = ""
        time_by_metric = {mid: timeres.resolve(self.registry.get(mid), time_question)
                          for mid in resolved.metric_ids}
        rtime = time_by_metric[resolved.metric_ids[0]]

        # Guard: explicit period intent must not collapse to all-time after resolve.
        if (timeres.has_explicit_period_intent(question)
                and (rtime is None or rtime.period_label == "all-time")
                and not forecast_asked):
            prov.append("[4] resolved time collapsed to all-time despite explicit period "
                        "intent -> clarification")
            return UnderstoodQuestion(
                question=question, intents=intents, reasoning_ceiling=ceiling,
                metric=resolved, dimension_request=dim_request, time=rtime,
                time_by_metric=time_by_metric,
                clarification=ClarificationRequest(
                    kind="referential",
                    question=("Which time period should I use? I will not answer with an "
                              "all-time figure when a specific period was requested."),
                    options=("This month", "Last month", "This year", "All recorded time"),
                    reason="Explicit period intent must not silently become all-time.",
                ),
                provenance=tuple(prov),
            )

        answerable = [m for m, t in time_by_metric.items() if t.within_coverage]
        unanswerable = [m for m, t in time_by_metric.items() if not t.within_coverage]
        prov.append(f"[4] date_field={primary.date_field!r} (documented, never substituted); "
                    f"period={rtime.period_label!r}; mode={rtime.mode}; "
                    f"within_coverage={rtime.within_coverage} "
                    f"(question_understanding_spec.md 5)")

        if unanswerable and not answerable:
            prov.append(f"[4] no member of the resolved family can answer this period: "
                        f"{unanswerable}")
            return UnderstoodQuestion(
                question=question, intents=intents, reasoning_ceiling=ceiling,
                metric=resolved, dimension_request=dim_request, time=rtime,
                time_by_metric=time_by_metric,
                forecast_note=forecast_note,
                not_determinable_reason=(
                    f"No definition of {resolved.concept.replace('_', ' ')} can answer this "
                    f"period. "
                    + " ".join(time_by_metric[m].coverage_note for m in unanswerable)
                    + f" {NOT_DETERMINABLE_TEXT}"),
                provenance=tuple(prov))

        time_note = ""
        if unanswerable:
            time_note = (
                f"{len(unanswerable)} of {len(resolved.metric_ids)} competing definitions "
                f"cannot answer this period and are excluded from it, which is itself a "
                f"disclosure rather than a silent narrowing: "
                + "; ".join(f"{m} -- {time_by_metric[m].coverage_note}" for m in unanswerable))
            prov.append(f"[4] partial family coverage: {unanswerable} cannot answer this "
                        f"period (question_understanding_spec.md 5.1 step 4)")

        comparison = None
        if COMPARISON in intents or DRIVER in intents:
            comparison = timeres.resolve_comparison(primary, time_question, current=rtime)
            prov.append(f"[4] comparison baseline={comparison.baseline.period_label!r}, "
                        f"valid={comparison.valid} "
                        f"(question_understanding_spec.md 5.1 step 5)")

        # A metric the registry declares CURRENT STATE ONLY holds a value with no effective
        # date and no record of what it was changed from. Any question about an earlier period,
        # or about how the value moved, is unanswerable from it -- and answering with today's
        # figure would present the present as the past. Refused here, with the metric's own
        # reason, rather than falling through to the generic "no monthly series" message, which
        # would tell the owner to ask for the all-time figure instead. There is no such figure:
        # what exists is today's, and today's is not what was asked for.
        if resolved is not None and resolved.metric_ids:
            spec0 = self.registry.get(resolved.metric_ids[0])
            policy = (getattr(spec0, "historical_policy", "") or "").strip().upper()
            if policy.startswith("CURRENT STATE ONLY"):
                asks_past = (
                    getattr(rtime, "period_label", "") not in ("", "all-time")
                    or DRIVER in intents or COMPARISON in intents or TREND in intents
                    or _asks_about_the_past(question)
                )
                if asks_past:
                    label = getattr(rtime, "period_label", "") or "an earlier period"
                    if label == "all-time":
                        label = "an earlier period"
                    subject = (spec0.semantic_name or "this measure").lower()
                    prov.append("[4] current-state-only metric asked about the past -> refused "
                                "(no effective date exists on the recorded value)")
                    return UnderstoodQuestion(
                        question=question, intents=intents, reasoning_ceiling=ceiling,
                        metric=resolved, dimension_request=dim_request, time=rtime,
                        time_by_metric=time_by_metric,
                        not_determinable_reason=(
                            f"The records hold {subject} as it stands now. No date is attached "
                            f"to say when it took effect, and no earlier value is kept, so "
                            f"there is nothing to read back to {label}. I can tell you the "
                            f"position today. {NOT_DETERMINABLE_TEXT}"),
                        provenance=tuple(prov),
                    )

        # When a single calendar month is requested, OR the intent needs period movement
        # (driver / comparison / trend), prefer a monthly-series alternative so execution
        # does not answer with an all-time total that cannot support the analysis.
        #
        # CRITICAL: resolve the monthly sibling via concept OR reverse metric_id map.
        # Forced metric_id paths (clarification reply / model proposal) set
        # concept="explicit:M.…" and must still find M.REV.002 / M.PNL.001 / M.COL.002.
        needs_monthly = (
            timeres.is_single_month_period(rtime)
            or DRIVER in intents
            or COMPARISON in intents
            or TREND in intents
        )
        if needs_monthly:
            monthly_alt = self._monthly_series_alternative(resolved)
            if monthly_alt and monthly_alt in self.registry and monthly_alt != resolved.metric_ids[0]:
                resolved = self._as_monthly_resolved(resolved, monthly_alt)
                time_by_metric = {monthly_alt: timeres.resolve(
                    self.registry.get(monthly_alt), time_question)}
                rtime = time_by_metric[monthly_alt]
                if COMPARISON in intents or DRIVER in intents:
                    comparison = timeres.resolve_comparison(
                        self.registry.get(monthly_alt), time_question, current=rtime)
                prov.append(f"[4] redirected to monthly series {monthly_alt} for "
                            f"period/change-capable analysis (not all-time total)")

        # A window of several months is a real period, and no calculator aggregates one. The
        # pipeline can serve ONE period, so a window was answered either with the all-time
        # total or -- worse, once the window resolved -- with a single month's figure carrying
        # the window's label. Both are substitutions. Refused here, naming what can be asked
        # instead, rather than returning a figure for a period nobody asked about.
        if (timeres.is_bounded_period(rtime) and not timeres.is_single_month_period(rtime)
                and rtime.start and rtime.end and rtime.start[:7] != rtime.end[:7]
                and resolved is not None and resolved.metric_ids):
            subject = (resolved.concept or "this measure").replace("_", " ")
            subject = subject.replace("explicit:", "")
            label = getattr(rtime, "period_label", "") or "that span"
            prov.append("[4] multi-month window requested; no aggregation over a window exists "
                        "-> refusing rather than answering with one month or with all-time")
            return UnderstoodQuestion(
                question=question, intents=intents, reasoning_ceiling=ceiling,
                metric=resolved, dimension_request=dim_request, time=rtime,
                time_by_metric=time_by_metric,
                not_determinable_reason=(
                    f"I can't total {subject} across {label} as one figure: the records are "
                    f"kept month by month and nothing here adds a span of them together. "
                    f"{NOT_DETERMINABLE_TEXT} Ask for a single month, or ask how {subject} "
                    f"changed, and I can answer from the monthly records."),
                provenance=tuple(prov))

        # An explicit month period on an all-time-only metric must NOT execute as all-time.
        if (timeres.is_single_month_period(rtime)
                and resolved is not None and resolved.metric_ids):
            mid0 = resolved.metric_ids[0]
            sname = (self.registry.get(mid0).semantic_name or "").lower()
            if not self._is_period_series_name(sname):
                monthly_alt = self._monthly_series_alternative(resolved)
                if monthly_alt and monthly_alt != mid0:
                    resolved = self._as_monthly_resolved(resolved, monthly_alt)
                    time_by_metric = {monthly_alt: timeres.resolve(
                        self.registry.get(monthly_alt), time_question)}
                    rtime = time_by_metric[monthly_alt]
                    prov.append(f"[4] late redirect to monthly series {monthly_alt} "
                                f"(period must not execute as all-time)")
                else:
                    subject = resolved.concept.replace("_", " ").replace("explicit:", "")
                    label = getattr(rtime, "period_label", None) or "that period"
                    prov.append("[4] period-scoped ask on all-time-only metric -> limitation "
                                "(never silent all-time substitute)")
                    return UnderstoodQuestion(
                        question=question, intents=intents, reasoning_ceiling=ceiling,
                        metric=resolved, dimension_request=dim_request, time=rtime,
                        time_by_metric=time_by_metric,
                        # The exact phrase is REQUIRED on a NOT_DETERMINABLE plan, and its
                        # absence here made the plan fail Phase 3 validation -- so the owner
                        # was shown a generic "rephrase your question" instead of this
                        # explanation, which blamed their wording for a limit of the evidence.
                        not_determinable_reason=(
                            f"I can show the recorded all-time {subject} figure, but I don't have "
                            f"a month-scoped series that answers {label} for this measure. "
                            f"{NOT_DETERMINABLE_TEXT} "
                            f"Ask for all-time {subject}, or for a measure that has monthly "
                            f"evidence (for example revenue or the monthly P&L)."
                        ),
                        provenance=tuple(prov),
                    )

        return UnderstoodQuestion(
            question=question, intents=intents, reasoning_ceiling=ceiling,
            metric=resolved, dimension_request=dim_request, time=rtime,
            time_by_metric=time_by_metric, time_note=time_note, comparison=comparison,
            breakdown_requested=bool(dim_request.group_by) or bool(delivered),
            driver_requested=DRIVER in intents,
            decision_requested=RECOMMENDATION in intents,
            forecast_note=forecast_note,
            provenance=tuple(prov),
        )

    @staticmethod
    def _is_period_series_name(semantic_name):
        s = (semantic_name or "").lower()
        return any(t in s for t in ("month", "monthly", "p&l", "pnl", "by day"))

    def _monthly_series_alternative(self, resolved):
        """Pick a documented monthly/period series sibling for this resolution."""
        if resolved is None or not resolved.metric_ids:
            return ""
        concept_name = resolved.concept or ""
        if concept_name.startswith("explicit:"):
            concept_name = ""
        candidates = concept_map.period_series_candidates(
            concept_name=concept_name or None,
            metric_ids=resolved.metric_ids,
        )
        primary = resolved.metric_ids[0]
        for alt in candidates:
            if alt == primary or alt not in self.registry:
                continue
            # Profit's competing definitions are BLOCK/SHOW_BOTH. Never silently
            # redirect a profit question to the SAFE ledger P&L net.
            owning = concept_map.concept(resolved.concept) if resolved.concept else None
            if owning is None:
                for cand in concept_map.all_concepts():
                    if primary in cand.metric_ids:
                        owning = cand
                        break
            if owning is not None and owning.name == "profit" and alt == "M.PNL.001":
                continue
            # A concept can hold several genuinely different definitions, and a monthly series
            # belongs to ONE of them. `Collections by month` is registered as a grouping of the
            # application-level figure, so offering it for the ledger-derived definition
            # answers with a measure the owner did not choose, under the name of the one they
            # did. The registry already records the ownership, in the series' own declared
            # dependencies; where it records none, the previous behaviour stands.
            deps = tuple(self.registry.get(alt).dependency_metrics or ())
            if deps and primary in self.registry and primary not in deps:
                continue
            name = (self.registry.get(alt).semantic_name or "").lower()
            if self._is_period_series_name(name):
                return alt
        return ""

    def _as_monthly_resolved(self, resolved, monthly_alt):
        """Rewrite resolution onto a monthly series, restoring a business concept name."""
        concept_name = resolved.concept or ""
        if concept_name.startswith("explicit:") or not concept_name:
            for cand in concept_map.all_concepts():
                if (monthly_alt in cand.metric_ids or monthly_alt in cand.alternatives
                        or any(m in cand.metric_ids or m in cand.alternatives
                               for m in resolved.metric_ids)):
                    if cand.name not in ("revenue_by_month", "expenses_by_category"):
                        concept_name = cand.name
                        break
        return ResolvedMetric(
            concept=concept_name or resolved.concept,
            metric_ids=(monthly_alt,),
            is_family=False,
            family_rule=resolved.family_rule,
            alternatives=resolved.alternatives,
            note=(resolved.note + " ; analysis uses monthly series "
                  f"{monthly_alt}").strip(" ;"),
        )

    # -- stage [2] internals -------------------------------------------------------------------

    def _resolve_metric(self, question, intents, concept_name, metric_id, prov):
        """Returns (ResolvedMetric|None, ClarificationRequest|None, not_determinable_reason)."""

        if metric_id is not None:
            if metric_id not in self.registry:
                return None, None, (
                    f"{metric_id!r} is not a semantic metric. {NOT_DETERMINABLE_TEXT}")
            # Even an explicitly-named metric_id must expand to its family: 3.2's rule is about
            # what gets ANSWERED, not about how the request was phrased.
            family = tuple(self.registry.family_members(metric_id))
            prov.append(f"[2] metric_id supplied directly: {metric_id}; expanded to family "
                        f"{list(family)} (question_understanding_spec.md 3.2)")
            return ResolvedMetric(
                concept=f"explicit:{metric_id}", metric_ids=family,
                is_family=len(family) > 1,
                family_rule="Caller supplied a metric_id; family expansion is still mandatory.",
            ), None, ""

        if concept_name is not None:
            c = concept_map.concept(concept_name)
            if c is None:
                return None, None, (
                    f"{concept_name!r} is not a catalogued concept. {NOT_DETERMINABLE_TEXT}")
            hits = [(c, concept_name)]
        else:
            hits = concept_map.match(question)

        # Named-tenant + owe/dues wording often fails phrase match because the person name
        # sits between "tenant" and "owe". Preserve the dues concept and let entity resolution
        # ask for an identifier — never invent a substitute metric, never silent all-tenant total.
        if not hits:
            qlow = (question or "").lower()
            dims = dimres.extract(question)
            if ("tenant_id" in (dims.unresolved_entities or ())
                    and any(w in qlow for w in ("owe", "owes", "owing", "dues", "receivable",
                                                 "arrears"))):
                c = concept_map.concept("tenant_dues")
                if c is not None:
                    hits = [(c, "tenant+owe with unresolved entity")]
                    prov.append("[2] tenant+owe with unresolved entity -> tenant_dues concept; "
                                "entity clarification required (no silent population total)")

        if not hits and RISK_SCAN in intents:
            # question_understanding_spec.md 6.1: "Who are our risky tenants?" / "Where are we
            # losing money?" -- "Does not resolve to one metric", "genuinely multi-metric, each
            # retaining its own trust label". ai_evaluation_framework.md 3 lists "What are our
            # biggest business risks?" as a Composite. A risk scan is therefore NOT a failed
            # metric resolution; the composite IS the resolution.
            from engine.analytics_planner import RISK_COMPOSITE_METRICS
            present = tuple(m for m in RISK_COMPOSITE_METRICS if m in self.registry)
            prov.append(f"[2] risk-scan intent with no single-concept match -> composite over "
                        f"{list(present)} (question_understanding_spec.md 6.1; "
                        f"analytics_execution_spec.md 2.8)")
            return ResolvedMetric(
                concept="risk_composite", metric_ids=present, is_family=False,
                family_rule=("analytics_execution_spec.md 2.8: each contributing metric runs "
                             "its own plan and keeps its own metric_id and trust label. No "
                             "composite risk-scoring metric exists in the registry, and one is "
                             "never invented at execution time."),
                note="Presented as a labelled list, never a merged score.",
            ), None, ""

        if not hits and ANOMALY in intents:
            # An anomaly scan is a trend series over SOME metric (analytics_execution_spec.md
            # 2.5). "Did anything look off?" names none, so there is no series to scan. That is
            # referential ambiguity about the subject, not an absent metric -- ask, don't guess.
            prov.append("[2] anomaly intent with no metric named -> clarification "
                        "(analytics_execution_spec.md 2.5 requires a series to scan)")
            return None, ClarificationRequest(
                kind="referential",
                question="Which measure should I scan for anomalies?",
                options=("revenue (M.REV.002)", "expenses (M.EXP.001)",
                         "collections (M.COL.002)", "maintenance volume (M.MAINT.001)"),
                reason=("An anomaly scan is a trend series compared against its own history "
                        "(analytics_execution_spec.md 2.5). No measure was named, and choosing "
                        "one would be a silent decision about what 'looked off' means."),
            ), ""

        if not hits and DRIVER in intents:
            # "What caused this change?" asked with no prior turn has no referent -- "this
            # change" points at nothing. That is referential ambiguity about the subject, not an
            # absent metric, so the honest response is to ask which measure rather than to
            # report that no metric exists (which would be false: many do).
            prov.append("[2] driver intent with no subject named and no prior context -> "
                        "clarification (question_understanding_spec.md 6, referential)")
            return None, ClarificationRequest(
                kind="referential",
                question="Which measure would you like me to explain the change in?",
                options=("revenue (M.REV.002)", "collections (M.COL.002)",
                         "expenses (M.EXP.001)", "the monthly P&L (M.PNL.001)"),
                reason=("A driver analysis decomposes the change in ONE named measure over its "
                        "documented dependency edges (analytics_execution_spec.md 2.6). No "
                        "measure was named and no previous turn established one, so there is "
                        "nothing to decompose."),
            ), ""

        if not hits and RECOMMENDATION in intents:
            # question_understanding_spec.md 6.1: "Question Understanding's job here is only to
            # establish scope (management-wide, not one metric), then hand off; the actual
            # recommendation logic is entirely downstream." That downstream layer (Business
            # Reasoning, business_reasoning_spec.md) is NOT part of this phase, so the honest
            # answer names the missing LAYER rather than claiming no evidence exists.
            prov.append("[2] recommendation intent: scope established as management-wide; "
                        "recommendation logic is downstream (question_understanding_spec.md 6.1)")
            return None, None, (
                f"Scope resolved: management-wide, not a single metric "
                f"(question_understanding_spec.md 6.1). Producing a recommendation requires the "
                f"full FACT->CALCULATION->OBSERVATION->INFERENCE->HYPOTHESIS->RECOMMENDATION "
                f"chain specified in business_reasoning_spec.md, which is a later phase than "
                f"this planning layer. This layer therefore hands off rather than answering. "
                f"{NOT_DETERMINABLE_TEXT}")

        if not hits:
            from engine import analysis_capability as acap
            from engine import capability_disclosure as caps
            cap = acap.classify_analysis_capability(question)
            if (cap.route == acap.ROUTE_CAPABILITY_GAP
                    or cap.status == caps.STATUS_NOT_IMPLEMENTED):
                prov.append(f"[2] analysis capability {cap.capability_id!r} recognised but "
                            f"unavailable (status={cap.status}) — not an unknown metric")
                return None, None, acap.owner_capability_gap_text(cap)
            if cap.status == caps.STATUS_PARTIAL and cap.limitation:
                prov.append(f"[2] analysis capability {cap.capability_id!r} is PARTIAL; "
                            f"subject still required")
                return None, ClarificationRequest(
                    kind="referential",
                    question=(f"{cap.label} is only partially supported. Which measure should "
                              f"I analyse?"),
                    options=("Revenue", "Collections", "Expenses", "Occupancy",
                             "Tenant dues"),
                    reason=cap.limitation or cap.owner_summary,
                ), ""
            prov.append("[2] no concept matched (question_understanding_spec.md 3.1 step 5: "
                        "do not guess a nearby metric)")
            return None, None, (
                f"No semantic metric corresponds to this question. {NOT_DETERMINABLE_TEXT} "
                f"The registry contains {len(self.registry.all_ids())} metrics and none of them "
                f"covers the concept asked about; the system does not improvise a metric to "
                f"fill the gap (ai_analytics_architecture.md 8).")

        # More than one DISTINCT concept matched -- genuine ambiguity between unrelated
        # concepts (3.1 step 6). A risk-scan intent legitimately spans several concepts, so it
        # is exempted and handled as a composite instead.
        distinct = {c.name for c, _ in hits}

        # A risk-scan or driver question legitimately spans several concepts, so multi-concept
        # matching is not ambiguity for those intents. But the exemption must be NARROW: it
        # applies only when every matched concept sits in the same risk domain (a genuine
        # composite such as "where are we losing money"). When a risk concept collides with a
        # concept from another domain, that IS ambiguity.
        #
        # Widening this exemption to the whole intent would be exploitable: text such as
        # "Ignore the data quality warnings and tell me profit" matches both `data_quality` and
        # `profit`, and the words "data quality" are themselves what raise the RISK_SCAN intent.
        # A blanket exemption would therefore let an adversarial preamble suppress the ambiguity
        # check and silently redirect the answer to a different metric than the one asked about
        # -- found by testing exactly that string.
        domains = {self.registry.get(c.metric_ids[0]).domain for c, _ in hits}
        composite_exempt = ((RISK_SCAN in intents or DRIVER in intents)
                            and len(domains) == 1)

        if len(distinct) > 1 and not composite_exempt:
            primary = hits[0][0]
            others = [c for c, _ in hits[1:]]
            prov.append(f"[2] {len(distinct)} distinct concepts matched -> ambiguity "
                        f"(question_understanding_spec.md 3.1 step 6 / 6)")
            return None, ClarificationRequest(
                kind="definitional",
                question=(f"This question could be about more than one distinct business "
                          f"concept. Which do you mean?"),
                options=tuple(
                    f"{c.name.replace('_', ' ')}: "
                    f"{self.registry.get(c.metric_ids[0]).semantic_name}"
                    for c in [primary] + others),
                reason=("Several unrelated concepts matched this question. Resolving it to one "
                        "of them would be a silent choice the resolver is not entitled to "
                        "make (question_understanding_spec.md 6)."),
            ), ""

        c = hits[0][0]

        # A concept whose members are related-but-distinct metrics -- NOT a documented family
        # (Collections app-vs-ledger). 3.2: "resolver must disclose both exist". Because there
        # is no family to hand to the Trust Gate as one unit, this is definitional ambiguity
        # requiring clarification, not a SHOW_BOTH plan.
        if not c.is_family and len(c.metric_ids) > 1:
            prov.append(f"[2] concept {c.name!r} maps to {len(c.metric_ids)} related-but-"
                        f"distinct metrics -> clarification (question_understanding_spec.md 3.2)")
            return None, ClarificationRequest(
                kind="definitional",
                question=f"Which definition of {c.name.replace('_', ' ')} do you mean?",
                options=tuple(
                    f"{mid}: {self.registry.get(mid).semantic_name} "
                    f"[{self.registry.get(mid).trust_level}]"
                    for mid in c.metric_ids),
                reason=c.family_rule,
                evidence=c.note,
            ), ""

        prov.append(f"[2] concept={c.name!r} -> {list(c.metric_ids)}; "
                    f"is_family={c.is_family}. {c.family_rule}")
        return ResolvedMetric(
            concept=c.name, metric_ids=c.metric_ids, is_family=c.is_family,
            family_rule=c.family_rule, alternatives=c.alternatives, note=c.note,
        ), None, ""


_LADDER = ("FACT", "CALCULATION", "OBSERVATION", "INFERENCE", "HYPOTHESIS", "RECOMMENDATION")
