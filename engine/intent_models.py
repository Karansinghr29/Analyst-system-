"""
intent_models.py -- Phase 3. The structured vocabulary shared by question_understanding.py and
analytics_planner.py: intents (question_understanding_spec.md 2), plan types
(analytics_execution_spec.md 2.1-2.8), and the Analytics Plan object itself.

Contains NO business content. Every metric_id, dimension, and date field referenced by these
objects is resolved from semantic_metric_registry.csv / business_dimensions.md at runtime --
nothing here defines or redefines a metric.

This module is pure data structure: no LLM, no embeddings, no retrieval, no I/O.
"""
from dataclasses import dataclass, field
from typing import Optional


# --- Intents (question_understanding_spec.md 2) ------------------------------------------------

LOOKUP = "lookup"
FILTERED_LOOKUP = "filtered_lookup"
TREND = "trend"
COMPARISON = "comparison"
ANOMALY = "anomaly"
DRIVER = "driver"
RISK_SCAN = "risk_scan"
RECOMMENDATION = "recommendation"
FOLLOW_UP = "follow_up"
META = "meta"

ALL_INTENTS = (LOOKUP, FILTERED_LOOKUP, TREND, COMPARISON, ANOMALY, DRIVER, RISK_SCAN,
               RECOMMENDATION, FOLLOW_UP, META)

# business_reasoning_spec.md's ladder ceiling per intent, as question_understanding_spec.md 2's
# "Downstream handling" column states it. Phase 3 records the ceiling; Phase 4+ enforces it
# during reasoning. Recorded here so a plan carries its own epistemic budget.
INTENT_REASONING_CEILING = {
    LOOKUP: "CALCULATION",
    FILTERED_LOOKUP: "CALCULATION",
    TREND: "OBSERVATION",
    COMPARISON: "OBSERVATION",
    ANOMALY: "INFERENCE",
    DRIVER: "HYPOTHESIS",
    RISK_SCAN: "OBSERVATION",
    RECOMMENDATION: "RECOMMENDATION",
    FOLLOW_UP: "CALCULATION",
    META: "FACT",
}


# --- Plan types (analytics_execution_spec.md 2.1-2.8) ------------------------------------------

PLAN_SINGLE_VALUE = "single_value_lookup"        # 2.1
PLAN_GROUPED = "grouped_lookup"                  # 2.2
PLAN_PERIOD_COMPARISON = "period_comparison"     # 2.3
PLAN_TREND = "trend_series"                      # 2.4
PLAN_ANOMALY = "anomaly_scan"                    # 2.5
PLAN_DRIVER = "driver_decomposition"             # 2.6
PLAN_EXPLAIN_CONFLICT = "explain_the_conflict"   # 2.7
PLAN_RISK_COMPOSITE = "risk_composite_scan"      # 2.8
PLAN_NONE = "no_plan"                            # terminated before planning

ALL_PLAN_TYPES = (PLAN_SINGLE_VALUE, PLAN_GROUPED, PLAN_PERIOD_COMPARISON, PLAN_TREND,
                  PLAN_ANOMALY, PLAN_DRIVER, PLAN_EXPLAIN_CONFLICT, PLAN_RISK_COMPOSITE,
                  PLAN_NONE)


# --- Plan status --------------------------------------------------------------------------------

READY = "READY"                              # executable as-is by Phase 2
BLOCKED = "BLOCKED"                          # trust gate says BLOCK -> explain-the-conflict only
NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"  # ambiguity the resolver must not settle itself
NOT_DETERMINABLE = "NOT_DETERMINABLE"        # no metric / degenerate dimension / no coverage
REJECTED = "REJECTED"                        # a structurally invalid plan was requested

ALL_STATUSES = (READY, BLOCKED, NEEDS_CLARIFICATION, NOT_DETERMINABLE, REJECTED)

NOT_DETERMINABLE_TEXT = "Not determinable from exported evidence."


# --- Resolution outputs -------------------------------------------------------------------------

@dataclass(frozen=True)
class ClarificationRequest:
    """question_understanding_spec.md 6. A legitimate pipeline outcome, not an error state."""
    kind: str            # "definitional" | "referential"
    question: str        # what to ask the user
    options: tuple       # the candidate interpretations, each already fully labelled
    reason: str
    evidence: str = ""


@dataclass(frozen=True)
class ResolvedMetric:
    """Output of question_understanding_spec.md 3. `metric_ids` is ALWAYS the whole family when
    the concept is a family -- 3.2: 'Family resolution is mandatory, not optional.'"""
    concept: str
    metric_ids: tuple
    is_family: bool
    family_rule: str          # why this resolved to a family (or did not)
    alternatives: tuple = ()  # related-but-distinct metrics the user should know exist
    note: str = ""


@dataclass(frozen=True)
class ResolvedTime:
    """Output of question_understanding_spec.md 5."""
    date_field: str            # the metric's DOCUMENTED date_field -- never substituted
    period_label: str          # "all-time", "2026-07", "last month", ...
    start: Optional[str] = None
    end: Optional[str] = None
    mode: str = "snapshot"     # "snapshot" | "historical"
    coverage_start: str = ""
    coverage_end: str = ""
    within_coverage: bool = True
    coverage_note: str = ""
    yoy_permitted: bool = True
    yoy_note: str = ""
    # True when the question asked for a future period or an explicit forecast/prediction
    # the export cannot support. Never invent a forecast value.
    forecast_unsupported: bool = False


@dataclass(frozen=True)
class ResolvedComparison:
    """analytics_execution_spec.md 2.3. Both periods resolved independently, and the comparison
    rejected if either fails coverage or snapshot/historical compatibility."""
    baseline: ResolvedTime
    current: ResolvedTime
    valid: bool
    reason: str = ""


@dataclass(frozen=True)
class ExecutionCall:
    """Exactly what to hand engine.execution.MetricExecutor.execute(). Requirement 3: the plan
    must be passable directly into Phase 2 execution."""
    metric_id: str
    kwargs: dict = field(default_factory=dict)
    label: str = ""


@dataclass(frozen=True)
class AnalyticsPlan:
    """The machine-readable Analytics Plan. Consumed by Phase 2's MetricExecutor; produced only
    by analytics_planner.plan()."""
    question: str
    status: str
    intents: tuple
    plan_type: str
    reasoning_ceiling: str

    metric: Optional[ResolvedMetric] = None
    metric_ids: tuple = ()
    time: Optional[ResolvedTime] = None
    time_note: str = ""            # partial-family-coverage disclosure (5.1 step 4)
    excluded_by_time: tuple = ()   # family members that cannot answer the requested period
    comparison: Optional[ResolvedComparison] = None
    # Owner-facing note when a forecast was requested but only recorded evidence can answer.
    forecast_note: str = ""

    filters: dict = field(default_factory=dict)
    group_by: tuple = ()
    degenerate_dimensions_used: tuple = ()

    # Trust is DELEGATED to engine.gate.TrustGate -- these fields record its verdict verbatim,
    # they are never computed in this layer (requirement: "trust handling is delegated to the
    # existing Trust Gate").
    trust_level: str = ""
    execution_mode: str = ""
    headline_permitted: bool = False
    required_disclosures: tuple = ()
    trust_reason: str = ""

    breakdown_requested: bool = False
    driver_requested: bool = False
    decision_requested: bool = False

    execution_calls: tuple = ()
    clarification: Optional[ClarificationRequest] = None
    rejection_reasons: tuple = ()
    not_determinable_reason: str = ""
    provenance: tuple = ()      # which spec rule drove each decision, for auditability

    @property
    def executable(self):
        """READY and BLOCKED are both executable: analytics_execution_spec.md 2.7 requires a
        BLOCK metric's competing definitions to be computed (internally) so the system can state
        the size of the disagreement. What BLOCK forbids is a headline, not computation."""
        return self.status in (READY, BLOCKED) and bool(self.execution_calls)

    def summary(self):
        parts = [f"[{self.status}] {self.plan_type}",
                 f"intents={','.join(self.intents)}"]
        if self.metric_ids:
            parts.append(f"metrics={','.join(self.metric_ids)}")
        if self.trust_level:
            parts.append(f"trust={self.trust_level}")
        if self.clarification:
            parts.append(f"clarify={self.clarification.kind}")
        if self.rejection_reasons:
            parts.append(f"rejected={len(self.rejection_reasons)}")
        return " | ".join(parts)


# --- Schema validation --------------------------------------------------------------------------

REQUIRED_PLAN_FIELDS = ("question", "status", "intents", "plan_type", "reasoning_ceiling")


def validate_plan_schema(plan: AnalyticsPlan, registry=None):
    """Structural validity of a plan object, independent of whether its answer is correct.
    Exit criterion: 'every generated Analytics Plan is schema-valid'. Returns a list of
    violations (empty = valid)."""
    v = []

    for f in REQUIRED_PLAN_FIELDS:
        if not getattr(plan, f, None):
            v.append(f"missing required field {f!r}")

    if plan.status not in ALL_STATUSES:
        v.append(f"status {plan.status!r} is not one of {ALL_STATUSES}")
    if plan.plan_type not in ALL_PLAN_TYPES:
        v.append(f"plan_type {plan.plan_type!r} is not one of {ALL_PLAN_TYPES}")
    for i in plan.intents:
        if i not in ALL_INTENTS:
            v.append(f"intent {i!r} is not a catalogued intent")
    if plan.reasoning_ceiling not in set(INTENT_REASONING_CEILING.values()):
        v.append(f"reasoning_ceiling {plan.reasoning_ceiling!r} is not a ladder stage")

    # Every metric reference must resolve to the semantic registry.
    if registry is not None:
        for mid in plan.metric_ids:
            if mid not in registry:
                v.append(f"metric_id {mid!r} does not resolve to semantic_metric_registry.csv")
        for call in plan.execution_calls:
            if call.metric_id not in registry:
                v.append(f"execution call {call.metric_id!r} does not resolve to the registry")

    # Status-specific shape rules.
    if plan.status == READY:
        if not plan.execution_calls:
            v.append("READY plan has no execution calls")
        if not plan.metric_ids:
            v.append("READY plan resolves no metric")
        if plan.clarification is not None:
            v.append("READY plan also carries a clarification request")
    elif plan.status == BLOCKED:
        if plan.plan_type != PLAN_EXPLAIN_CONFLICT:
            v.append(f"BLOCKED plan must use {PLAN_EXPLAIN_CONFLICT}, got {plan.plan_type}")
        if plan.headline_permitted:
            v.append("BLOCKED plan permits a headline")
        if not plan.required_disclosures:
            v.append("BLOCKED plan discloses no conflict/DQ ids")
    elif plan.status == NEEDS_CLARIFICATION:
        if plan.clarification is None:
            v.append("NEEDS_CLARIFICATION plan carries no ClarificationRequest")
        elif not plan.clarification.options:
            v.append("clarification request offers no options")
        if plan.execution_calls:
            v.append("NEEDS_CLARIFICATION plan must not be executable -- "
                     "question_understanding_spec.md 6: the pipeline does not execute "
                     "speculatively against multiple candidate resolutions")
    elif plan.status == NOT_DETERMINABLE:
        if NOT_DETERMINABLE_TEXT not in plan.not_determinable_reason:
            v.append(f"NOT_DETERMINABLE plan must contain the exact phrase "
                     f"{NOT_DETERMINABLE_TEXT!r}")
        if plan.execution_calls:
            v.append("NOT_DETERMINABLE plan must not be executable")
    elif plan.status == REJECTED:
        if not plan.rejection_reasons:
            v.append("REJECTED plan states no reason")
        if plan.execution_calls:
            v.append("REJECTED plan must not be executable")

    # SHOW_BOTH / BLOCK may never be planned as a single-value lookup.
    if plan.trust_level in ("SHOW_BOTH", "BLOCK") and plan.plan_type == PLAN_SINGLE_VALUE:
        v.append(f"{plan.trust_level} metric planned as a single-value lookup -- "
                 f"analytics_execution_spec.md 2.7 requires the explain-the-conflict plan")
    if plan.trust_level in ("SHOW_BOTH", "BLOCK") and plan.headline_permitted:
        v.append(f"{plan.trust_level} plan permits a headline")

    # A comparison plan must actually carry a comparison.
    if plan.plan_type == PLAN_PERIOD_COMPARISON and plan.comparison is None:
        v.append("period_comparison plan carries no resolved comparison")

    if not isinstance(plan.provenance, tuple) or not plan.provenance:
        v.append("plan carries no provenance -- every planning decision must be traceable "
                 "to the spec rule that drove it")

    return v
