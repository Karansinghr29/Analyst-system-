"""
root_cause.py -- Phase 6. The "Why?" engine: driver analysis over DOCUMENTED dependency edges.

analytics_execution_spec.md 2.6 fixes the method and its limit:

    "decompose the change into its constituent sub-components using metric_dependency_graph.md's
     documented dependency edges ... never into an undocumented ad-hoc decomposition. Where the
     top-level metric is itself in conflict (e.g. M.PROFIT.001, BLOCK), driver decomposition may
     still run PER-DEFINITION ... but must never merge the two decompositions into one
     narrative."

The hard boundary this module enforces is epistemic, not computational. The exported evidence
contains no experiment, no control, and no causal model -- so nothing here can establish that
one metric CAUSED another to move. What it can establish is that a documented dependency edge
exists and that the component moved in the same window. That is a pattern, and it is labelled
one: every driver statement is emitted as OBSERVATION or HYPOTHESIS, never as a proven cause.

    business_reasoning_spec.md 2, HYPOTHESIS: "must be phrased with explicit hedge language
    ('consistent with,' 'suggests,' 'would explain if confirmed') -- never with
    FACT/CALCULATION-register language ('is caused by,' 'the reason is')."
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine.change_detection import ChangeDetector, Change, INCREASE, DECREASE, UNAVAILABLE
from engine.result import NOT_DETERMINABLE_TEXT
from engine import business_reasoning

# The epistemic status a driver claim may carry. There is deliberately no "CAUSE".
PATTERN_ONLY = "PATTERN_ONLY"        # a documented edge exists and both moved in the window
EDGE_ONLY = "EDGE_ONLY"              # the edge is documented but the component is not comparable
NO_EDGE = "NO_EDGE"                  # no documented dependency; nothing may be claimed

CAUSAL_DISCLAIMER = (
    "This is a correlation over a documented dependency edge, not a demonstrated cause. The "
    "exported evidence contains no experiment or control that could establish causation, so no "
    "causal claim is made.")


@dataclass(frozen=True)
class Driver:
    metric_id: str
    metric_name: str
    status: str                      # PATTERN_ONLY / EDGE_ONLY / NO_EDGE
    edge_source: str                 # where the dependency is documented
    change: object = None            # the component's own Change, when comparable
    trust_level: str = ""
    conflict_ids: tuple = ()
    dq_ids: tuple = ()
    note: str = ""


@dataclass(frozen=True)
class RootCauseAnalysis:
    metric_id: str
    metric_name: str
    target_change: object = None
    drivers: tuple = ()
    per_definition: tuple = ()       # for a conflicted target: one decomposition per definition
    statements: tuple = ()           # business_reasoning.Statement, epistemically labelled
    trust_level: str = ""
    limitations: tuple = ()
    not_determinable_reason: str = ""

    @property
    def determinable(self):
        return not self.not_determinable_reason


class RootCauseAnalyzer:
    def __init__(self, registry: SemanticRegistry = None, gate: TrustGate = None,
                 executor: MetricExecutor = None, detector: ChangeDetector = None):
        self.registry = registry or SemanticRegistry()
        self.gate = gate or TrustGate(self.registry)
        self.executor = executor or MetricExecutor(registry=self.registry, gate=self.gate)
        self.detector = detector or ChangeDetector(self.registry, self.gate, self.executor)

    def analyze(self, metric_id):
        if metric_id not in self.registry:
            return RootCauseAnalysis(
                metric_id=metric_id, metric_name=metric_id,
                not_determinable_reason=f"{metric_id!r} is not a semantic metric. "
                                        f"{NOT_DETERMINABLE_TEXT}")

        spec = self.registry.get(metric_id)
        decision = self.gate.authorize(metric_id)
        target = self.detector.detect(metric_id)

        drivers = self._drivers_for(metric_id)
        limitations = []

        # A conflicted target decomposes PER DEFINITION, never into one merged narrative (2.6).
        per_definition = ()
        if decision.effective_level in ("SHOW_BOTH", "BLOCK"):
            per_definition = tuple(
                {"definition": m, "drivers": self._drivers_for(m)}
                for m in (decision.required_definitions or (metric_id,))
                if m in self.registry)
            limitations.append(
                f"{metric_id} is {decision.effective_level}: the decomposition is presented per "
                f"definition and is never merged into a single explanation "
                f"(analytics_execution_spec.md 2.6). Conflicting definitions exist.")

        if not target.detected and decision.effective_level not in ("SHOW_BOTH", "BLOCK"):
            limitations.append(
                f"No period change could be established for {metric_id}: "
                f"{target.unavailable_reason}")

        if not drivers:
            limitations.append(
                f"metric_dependency_graph.md documents no dependency edge from {metric_id}, so "
                f"no driver decomposition is available for it. {NOT_DETERMINABLE_TEXT}")

        statements = self._ladder(spec, decision, target, drivers)

        return RootCauseAnalysis(
            metric_id=metric_id, metric_name=spec.semantic_name,
            target_change=target, drivers=drivers, per_definition=per_definition,
            statements=statements, trust_level=decision.effective_level,
            limitations=tuple(limitations),
        )

    # -- drivers -------------------------------------------------------------------------------

    def _drivers_for(self, metric_id):
        """Only DOCUMENTED edges. The registry's `dependency_metrics` column is the graph's own
        machine-readable form, so nothing here is inferred from a name or a resemblance."""
        spec = self.registry.get(metric_id)
        out = []
        for dep in spec.dependency_metrics:
            if dep == "ALL" or dep not in self.registry:
                continue
            dep_spec = self.registry.get(dep)
            dep_decision = self.gate.authorize(dep)
            dep_change = self.detector.detect(dep)

            if dep_change.detected:
                status, note = PATTERN_ONLY, CAUSAL_DISCLAIMER
            else:
                status = EDGE_ONLY
                note = (f"The dependency edge is documented, but no period comparison is "
                        f"available for {dep}: {dep_change.unavailable_reason}")

            out.append(Driver(
                metric_id=dep, metric_name=dep_spec.semantic_name, status=status,
                edge_source=f"semantic_metric_registry.csv dependency_metrics of {metric_id}; "
                            f"metric_dependency_graph.md",
                change=dep_change if dep_change.detected else None,
                trust_level=dep_decision.effective_level,
                conflict_ids=dep_spec.conflict_ids, dq_ids=dep_spec.dq_ids, note=note,
            ))
        return tuple(out)

    # -- the epistemic ladder --------------------------------------------------------------------

    def _ladder(self, spec, decision, target, drivers):
        S = business_reasoning.Statement
        out = []

        if target.detected:
            out.append(S(stage=business_reasoning.FACT,
                         text=(f"{spec.semantic_name} was {target.current_value} in "
                               f"{target.current_period} and {target.previous_value} in "
                               f"{target.previous_period}."),
                         metric_ids=(spec.metric_id,), trust_level=decision.effective_level))
            out.append(S(stage=business_reasoning.CALCULATION,
                         text=(f"Change = {target.absolute_change}"
                               + (f" ({target.percentage_change}%)"
                                  if target.percentage_change is not None else "")),
                         metric_ids=(spec.metric_id,), trust_level=decision.effective_level))
            out.append(S(stage=business_reasoning.OBSERVATION,
                         text=(f"{spec.semantic_name} "
                               f"{'rose' if target.classification == INCREASE else 'fell'} "
                               f"between {target.previous_period} and {target.current_period}. "
                               f"{target.materiality}"),
                         metric_ids=(spec.metric_id,), trust_level=decision.effective_level))

        moved = [d for d in drivers if d.status == PATTERN_ONLY]
        if moved:
            out.append(S(stage=business_reasoning.INFERENCE,
                         text=(f"{len(moved)} documented component(s) of "
                               f"{spec.semantic_name} also changed over the same period: "
                               + "; ".join(f"{d.metric_name} "
                                           f"{d.change.absolute_change}" for d in moved)
                               + f". The dependency edges are documented in "
                                 f"metric_dependency_graph.md, so the relationship itself is "
                                 f"evidence-backed."),
                         metric_ids=tuple(d.metric_id for d in moved),
                         trust_level=business_reasoning._worst(
                             [d.trust_level for d in moved] + [decision.effective_level]),
                         confidence=business_reasoning.PROVEN))
            for d in moved:
                out.append(S(stage=business_reasoning.HYPOTHESIS,
                             text=(f"The movement in {d.metric_name} is consistent with the "
                                   f"change in {spec.semantic_name}, and would explain part of "
                                   f"it if confirmed. {CAUSAL_DISCLAIMER}"),
                             metric_ids=(d.metric_id,), trust_level=d.trust_level,
                             dq_ids=d.dq_ids, conflict_ids=d.conflict_ids,
                             confidence=business_reasoning.SUSPECTED))
        return tuple(out)


def unsupported_causal_claim(text):
    """Guard used by the answer layer and by tests: does this text assert a cause the evidence
    cannot support? Returns the offending phrase, or ''."""
    low = (text or "").lower()
    for phrase in business_reasoning.FACT_REGISTER_PHRASES:
        if phrase in low:
            return phrase
    for phrase in ("caused by", "due to the fact", "driven by", "the cause is", "explains the"):
        if phrase in low:
            return phrase
    return ""
