"""
analysis_capability.py -- Generic analytical-capability classification for Owner questions.

This is NOT a canned-question router. It classifies the TYPE of analysis requested
(forecast, scenario, trend, driver, change detection, executive synthesis, …) from
analysis-language markers, then looks up whether that capability is implemented in
`analysis_capability_registry.csv` (plus a few known product capabilities that are not
yet registered).

Routing stays inside the existing Owner pipeline:
  question → capability class → existing workflow / planner / capability-gap answer

The LLM never gains a calculation path here.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine import capability_disclosure as caps
from engine import time_resolution as timeres
from engine import forecasting

# Owner-facing routes consumed by AnalystIntelligence.ask
ROUTE_METRIC = "metric"
ROUTE_BRIEFING = "briefing"
ROUTE_WHAT_CHANGED = "what_changed"
ROUTE_WHAT_TO_DO = "what_to_do"
ROUTE_WHAT_TO_TRUST = "what_to_trust"
ROUTE_CAPABILITY_GAP = "capability_gap"
# Descriptive analysis IS implemented (engine/descriptive.py). It is a route of its own
# rather than a metric route because it answers about the SHAPE of recorded figures --
# typical value, spread, how two measures moved together -- which the metric path, built
# to return one number for one period, has no way to express.
ROUTE_DESCRIPTIVE = "descriptive"

# Product capabilities that are required but not yet rows in the registry CSV.
_VIRTUAL_CAPABILITIES = {
    "forecasting": {
        "status": caps.STATUS_NOT_IMPLEMENTED,
        "label": "Forecasting",
        "owner_summary": (
            "I can show historical figures, but I can't reliably forecast future periods "
            "because a forecasting method isn't currently available. Future values are "
            "not invented."
        ),
    },
    "scenario_analysis": {
        "status": caps.STATUS_NOT_IMPLEMENTED,
        "label": "Scenario / what-if analysis",
        "owner_summary": (
            "Scenario and what-if analysis is a valid analytical request, but the required "
            "inputs and methodology are not implemented yet. Hypothetical outcomes are not invented."
        ),
    },
}

# Analysis-type markers only — never full owner questions. Most-specific first.
# (capability_id, markers, default_route)
_CAPABILITY_MARKERS = (
    ("forecasting", (
        "forecast", "prediction", "predict", "projected", "projection",
        "next month", "next year", "next quarter", "will we make", "will we earn",
        "will we collect", "going to make", "expected to", "coming month",
    ), ROUTE_CAPABILITY_GAP),
    ("scenario_analysis", (
        "what if", "what happens if", "scenario", "if we increase", "if we decrease",
        "if occupancy", "if rent", "should i increase", "should we increase",
        "should i raise", "assume that", "assuming ",
    ), ROUTE_CAPABILITY_GAP),
    ("statistical_summary", (
        "distribution", "histogram", "standard deviation", "percentile", "quartile",
        "statistically", "variance of", "mean and", "median and",
        # Central tendency asked of something the descriptive capability does not summarise.
        # The descriptive router runs BEFORE this table, so "typical rent" is answered there;
        # what reaches here is a request like "typical revenue", where no such statistic is
        # offered -- the investigation established the revenue mean describes a window of
        # growth rather than a typical month. It gets the honest capability limitation instead
        # of the all-time total, which is a different quantity wearing the question's label.
        "typical", "usually", "on average", "usual amount",
    ), ROUTE_CAPABILITY_GAP),
    ("what_changed", (
        "what changed", "what has changed", "what's changed", "whats changed",
        "what moved", "any changes",
    ), ROUTE_WHAT_CHANGED),
    ("attention_required", (
        # Keep singular+plural stems: plural stem can rewrite "needs"→"need".
        "needs attention", "need attention", "needs my attention", "need my attention",
        "require attention", "requires a decision",
        "biggest risk", "biggest risks", "what should i worry", "what should i focus",
        "what should i do", "what should we do", "where should i start", "look at first",
        "where should i look", "look first", "management attention", "needs management",
        "priority", "priorities", "needs action", "need action", "what needs action",
        "what need action",
        "major risk", "anything risky",
        # Open-ended worry / problem language — not full canned questions.
        "worry about", "should worry", "anything to worry", "any problem", "any problems",
        "any issue", "any issues", "anything concerning", "concerning",
        "where is the problem", "where are the problems", "problem areas",
        "area problem", "area problems",
    ), ROUTE_WHAT_TO_DO),
    ("trust_advisory", (
        "which numbers should i trust", "which numbers can i trust", "can i trust",
        "how reliable", "data problems", "data quality", "unreliable",
    ), ROUTE_WHAT_TO_TRUST),
    ("executive_summary", (
        "how is the business", "how's the business", "how is my business",
        "how's my business", "how are we doing", "business summary", "executive summary",
        "management briefing", "business overview", "company overview",
        "overall picture", "business health", "important business insights",
    ), ROUTE_BRIEFING),
    ("anomaly_surface", (
        "anomaly", "anomalies", "unusual", "look off", "looks off", "outlier",
        "spike", "anything odd", "out of the ordinary",
    ), ROUTE_METRIC),
    ("driver_analysis", (
        # Bare "why" is the driver intent itself; the auxiliary that follows is incidental and
        # absent from most natural phrasings ("why revenue fell?", "revenue why decreased").
        " why ",
        "why did", "why has", "why was", "why were", "why are", "why is",
        "what caused", "what drove", "root cause", "what's behind", "whats behind",
        "reason for", "explain the drop", "explain the rise", "explain the fall",
        "losing money", "where are we losing", "where we losing",
    ), ROUTE_METRIC),
    ("trend", (
        "getting better", "getting worse", "trending", "over time", "by month",
        "month by month", "historical", "are collections", "improving", "worsening",
    ), ROUTE_METRIC),
    ("period_comparison", (
        "compared to", "compared with", "versus", " vs ", "better than", "worse than",
        "year on year", "year-on-year", "yoy", "month on month", "compare ",
        "this month with last", "this month vs last", "this month to last",
        "increase", "increased", "went up", "going up", "decrease", "decreased",
        "went down", "going down", "from last month", "than last month",
    ), ROUTE_METRIC),
    ("segmentation", (
        "which property", "which properties", "performing best", "performing better",
        "rank", "ranking", "by property", "by tenant", "segment", "breakdown by",
    ), ROUTE_METRIC),
    ("business_risk_scan", (
        "how risky", "risk position", "risk exposure", "receivables position",
    ), ROUTE_METRIC),
    ("kpi_lookup", (
        "how much", "what is", "what's", "show me", "tell me", "look up",
    ), ROUTE_METRIC),
)

_INTENT_TO_CAPABILITY = {
    "anomaly": "anomaly_surface",
    "driver": "driver_analysis",
    "trend": "trend",
    "comparison": "period_comparison",
    "risk_scan": "business_risk_scan",
    "recommendation": "attention_required",
    "meta": "trust_advisory",
    "lookup": "kpi_lookup",
    "filtered_lookup": "kpi_lookup",
}


@dataclass(frozen=True)
class CapabilityClassification:
    capability_id: str
    label: str
    status: str
    route: str
    owner_summary: str = ""
    limitation: str = ""
    intents: tuple = ()

    @property
    def is_available(self):
        return self.status == caps.STATUS_IMPLEMENTED

    @property
    def is_gap(self):
        return self.status in (caps.STATUS_NOT_IMPLEMENTED, "") or (
            self.route == ROUTE_CAPABILITY_GAP and self.status != caps.STATUS_IMPLEMENTED
        )


_DISCLOSURE = None


def _disclosure():
    global _DISCLOSURE
    if _DISCLOSURE is None:
        _DISCLOSURE = caps.CapabilityDisclosure()
    return _DISCLOSURE


def lookup_capability(capability_id: str) -> dict:
    """Registry row plus virtual product capabilities. Never invents a method."""
    cid = (capability_id or "").strip()
    if not cid:
        return {"capability_id": "", "status": "", "label": "", "limitation": "",
                "owner_summary": ""}
    if cid in _VIRTUAL_CAPABILITIES:
        meta = _VIRTUAL_CAPABILITIES[cid]
        return {
            "capability_id": cid,
            "status": meta["status"],
            "label": meta["label"],
            "limitation": meta["owner_summary"],
            "owner_summary": meta["owner_summary"],
        }
    for row in _disclosure().rows:
        if (row.get("capability_id") or "").strip() == cid:
            status = (row.get("status") or "").strip().upper()
            limitation = (row.get("limitation") or "").strip()
            label = caps._label(cid)
            if status == caps.STATUS_NOT_IMPLEMENTED:
                summary = (
                    f"{label} is a valid analytical request, but it is not implemented "
                    f"against the available evidence yet."
                )
            elif status == caps.STATUS_PARTIAL:
                summary = (
                    f"{label} is only partially supported. "
                    + (limitation or "Some required thresholds or methods are not defined.")
                )
            else:
                summary = f"{label} is available from the deterministic analytics layer."
            return {
                "capability_id": cid,
                "status": status,
                "label": label,
                "limitation": limitation,
                "owner_summary": summary,
            }
    return {
        "capability_id": cid,
        "status": caps.STATUS_NOT_IMPLEMENTED,
        "label": caps._label(cid),
        "limitation": "",
        "owner_summary": (
            f"{caps._label(cid)} is a valid analytical request, but it is not implemented "
            f"against the available evidence yet."
        ),
    }


def supported_forecast(question: str) -> bool:
    """True when a forecast question is one `engine/forecasting.py` actually answers.

    Deliberately the SAME condition the forecast branch in the question pipeline tests, so the
    classifier and the executor cannot disagree about what is supported: a forward-looking
    question about revenue, that is not a driver-conditioned scenario. Everything else -- a
    forecast of a measure with no validated model, or a 'what if occupancy were 80%' -- keeps
    the capability-gap answer it already had.

    Horizon is NOT tested here. `forecast_revenue` refuses a horizon beyond its measured
    accuracy with its own reason, and that refusal is a better answer than a generic gap.
    """
    if forecasting.asks_scenario(question):
        return False
    forecast_asked, _ = timeres.asks_unsupported_forecast(question)
    if not (forecast_asked or forecasting.asks_forecast(question)):
        return False
    from engine import concept_map
    return any(c.name == "revenue" for c, _ in concept_map.match(question or ""))


def classify_analysis_capability(question: str) -> CapabilityClassification:
    """Classify the requested analysis type from markers + intents. No question hardcoding."""
    from engine.question_understanding import classify_intents

    q = f" {(question or '').lower()} "
    intents = classify_intents(question)

    # Explicit future/forecast language wins even when a KPI subject is also present.
    forecast_asked, _ = timeres.asks_unsupported_forecast(question)
    if forecast_asked or forecasting.asks_forecast(question):
        # Revenue forecasting is IMPLEMENTED -- deterministically, by engine/forecasting.py,
        # whose method was chosen by out-of-sample backtest, and recorded as implemented in the
        # capability registry. Classifying it as a gap contradicted the registry and left the
        # owner told that no forecasting method exists while one was running underneath. It
        # routes as a metric question so the existing forecast branch in the question pipeline
        # answers it; nothing about the generic refusal below changes.
        if supported_forecast(question):
            meta = lookup_capability("revenue_forecast")
            return CapabilityClassification(
                capability_id="revenue_forecast", label=meta["label"],
                status=meta["status"] or caps.STATUS_IMPLEMENTED,
                route=ROUTE_METRIC, owner_summary=meta["owner_summary"],
                limitation=meta["limitation"], intents=intents,
            )
    if forecast_asked:
        meta = lookup_capability("forecasting")
        return CapabilityClassification(
            capability_id="forecasting", label=meta["label"], status=meta["status"],
            route=ROUTE_CAPABILITY_GAP, owner_summary=meta["owner_summary"],
            limitation=meta["limitation"], intents=intents,
        )

    # Descriptive analysis, before the generic markers. The `statistical_summary` marker set
    # below overlaps it ("distribution", "percentile", "standard deviation") and would otherwise
    # answer a servable question with a capability gap. The descriptive router matches only on an
    # analysis marker OVER a subject the engine can serve, so a distribution question about
    # something it cannot describe still falls through to that gap, correctly.
    from engine import descriptive_routing
    desc = descriptive_routing.classify(question)
    if desc.matched:
        meta = lookup_capability("descriptive_analysis")
        return CapabilityClassification(
            capability_id="descriptive_analysis", label=meta["label"],
            status=meta["status"] or caps.STATUS_IMPLEMENTED,
            route=ROUTE_DESCRIPTIVE, owner_summary=meta["owner_summary"],
            limitation=meta["limitation"], intents=intents,
        )

    # `kpi_lookup`'s markers are the generic openings of almost any question -- "how much",
    # "what is", "show me". They sit last precisely because they must not outrank a specific
    # analysis type, but last still beats the intent fallback below, so "how much did revenue
    # move?" matched "how much" and classified as a lookup while question understanding had
    # already read it as a comparison. Two classifiers disagreeing about the same question is a
    # latent defect even while the intent is what drives execution.
    #
    # The rule: a generic lookup opening yields to whatever intent understanding established.
    # It is not a rule about movement questions specifically -- any question whose intent is
    # something other than a lookup keeps that reading rather than losing it to "how much".
    intent_capability = _INTENT_TO_CAPABILITY.get(intents[0] if intents else "lookup",
                                                  "kpi_lookup")

    # "Forecast revenue for June 2026" names a month the records already cover. The word
    # "forecast" matched the forecasting markers and produced a capability gap for a question
    # the evidence answers outright. The same rule the pipeline applies elsewhere: a recorded
    # month is a historical question whatever verb asked for it.
    named = forecasting.parse_target_month(question)
    names_recorded_month = bool(named and forecasting.horizon_for_period(named) <= 0)

    for capability_id, markers, route in _CAPABILITY_MARKERS:
        if any(m in q for m in markers):
            if capability_id == "forecasting" and names_recorded_month:
                continue       # keep looking: this is a question about a month already recorded
            if capability_id == "kpi_lookup" and intent_capability != "kpi_lookup":
                break          # fall through to the intent fallback, which agrees with [1]
            meta = lookup_capability(capability_id)
            status = meta["status"] or caps.STATUS_IMPLEMENTED
            # Registry-backed gaps / partials that were marker-matched as metric should still
            # surface as capability-aware when the method itself is not available.
            effective_route = route
            if capability_id in _VIRTUAL_CAPABILITIES:
                effective_route = ROUTE_CAPABILITY_GAP
            elif status == caps.STATUS_NOT_IMPLEMENTED:
                effective_route = ROUTE_CAPABILITY_GAP
            return CapabilityClassification(
                capability_id=capability_id, label=meta["label"], status=status,
                route=effective_route, owner_summary=meta["owner_summary"],
                limitation=meta["limitation"], intents=intents,
            )

    # Fall back to intent → capability when no analysis-type marker fired.
    primary = intents[0] if intents else "lookup"
    capability_id = _INTENT_TO_CAPABILITY.get(primary, "kpi_lookup")
    route = ROUTE_WHAT_TO_DO if capability_id == "attention_required" else ROUTE_METRIC
    if capability_id == "trust_advisory":
        route = ROUTE_WHAT_TO_TRUST
    meta = lookup_capability(capability_id)
    status = meta["status"] or caps.STATUS_IMPLEMENTED
    if status == caps.STATUS_NOT_IMPLEMENTED:
        route = ROUTE_CAPABILITY_GAP
    return CapabilityClassification(
        capability_id=capability_id, label=meta["label"], status=status,
        route=route, owner_summary=meta["owner_summary"],
        limitation=meta["limitation"], intents=intents,
    )


def owner_capability_gap_text(classification: CapabilityClassification, subject: str = "") -> str:
    """Concise owner prose for a recognised analysis type that cannot run yet."""
    subject = (subject or "").strip()
    if classification.capability_id == "forecasting":
        label = subject or "this measure"
        return (
            f"I can show historical {label}, but I can't reliably forecast the next period "
            f"because a forecasting method isn't currently available."
        )
    lead = classification.owner_summary or (
        f"{classification.label} is not available from the current analytics capabilities."
    )
    lines = [lead]
    if subject:
        lines.append(
            f"I recognised this as a request about {subject}, but I cannot invent the "
            f"{classification.label.lower()} result."
        )
    if classification.limitation and classification.limitation not in lead:
        # Keep owner-facing; strip will happen in presentation if IDs leak.
        lines.append(classification.limitation)
    lines.append(
        "Ask about recorded figures, trends, what changed, risks, or drivers — those "
        "capabilities are available today."
    )
    return "\n".join(lines)
