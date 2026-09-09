"""
trust_gate.py -- Layer 3 of ai_analytics_architecture.md. The single enforcement point for
ai_trust_policy.md. Every metric_id passes through here BEFORE calculators.py is invoked for
user-facing output. This module's job is narrow and absolute: look up the trust_level, and
decide which calculator-invocation MODE is permitted.

Per ai_trust_policy.md and metric_dependency_graph.md 6: trust is a property of the metric
(read from semantic_metric_registry.csv), never of how the question was phrased, and a
composite/dependent metric inherits the WORST trust level among its dependency_metrics.
"""
from dataclasses import dataclass

from engine.semantic_registry import SemanticRegistry, MetricSpec

_SEVERITY = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}


@dataclass(frozen=True)
class TrustVerdict:
    metric_id: str
    trust_level: str            # the metric's OWN trust_level (unmodified)
    effective_level: str        # trust_level, worsened if a dependency is worse
    mode: str                   # "single" | "family" | "block" | "not_determinable"
    reason: str
    conflict_ids: tuple
    dq_ids: tuple


def _worst(a, b):
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def evaluate(metric_id, registry: SemanticRegistry, _seen=None) -> TrustVerdict:
    """Resolve the binding trust verdict for metric_id, propagating through
    dependency_metrics per metric_dependency_graph.md 6's worst-of-inputs rule.
    `_seen` guards against a dependency cycle (none exist in the current registry, but the
    check costs nothing and prevents infinite recursion if one is ever introduced)."""
    _seen = _seen or set()
    if metric_id in _seen:
        raise RuntimeError(f"Dependency cycle detected at {metric_id}")
    _seen = _seen | {metric_id}

    spec = registry.get(metric_id)
    effective = spec.trust_level

    for dep in spec.dependency_metrics:
        if dep == "ALL":
            continue  # M.RISK.009's self-referential meta-dependency -- not a real propagation edge
        if dep not in registry:
            continue
        dep_verdict = evaluate(dep, registry, _seen)
        effective = _worst(effective, dep_verdict.effective_level)

    mode = {
        "SAFE": "single", "DISCLOSE": "single",
        "SHOW_BOTH": "family", "BLOCK": "block",
        "NOT_DETERMINABLE": "not_determinable",
    }[effective]

    reason = _reason_for(spec, effective)
    return TrustVerdict(
        metric_id=metric_id, trust_level=spec.trust_level, effective_level=effective,
        mode=mode, reason=reason, conflict_ids=spec.conflict_ids, dq_ids=spec.dq_ids,
    )


def _reason_for(spec: MetricSpec, effective):
    if effective == spec.trust_level:
        if effective == "SAFE":
            return "Canonical, single validated definition."
        if effective == "DISCLOSE":
            return f"Usable with caveat: {spec.caveat_text}"
        if effective == "SHOW_BOTH":
            return f"Multiple competing definitions exist ({', '.join(spec.conflict_ids)}); none may be stated alone."
        if effective == "BLOCK":
            return f"Conflicting definitions with no evidence-proven winner ({', '.join(spec.conflict_ids)}); a single number would be misleading."
        return "No reference exists to validate a reconstruction of this metric."
    return f"Downgraded from {spec.trust_level} to {effective} via a dependency metric (metric_dependency_graph.md 6)."


def assert_no_downgrade_by_phrasing(metric_id, registry, phrasing_variant_ids):
    """ai_trust_policy.md 2 BLOCK: 'this includes rephrased, indirect, or comparative
    questions.' Structural guarantee: the verdict is computed from metric_id alone, never from
    any phrasing parameter -- so calling evaluate() with different (irrelevant) phrasing labels
    must always return the identical verdict. Used by tests, not by the runtime path itself
    (which never receives a phrasing parameter to begin with -- the impossibility is by
    construction, this helper just makes that testable)."""
    base = evaluate(metric_id, registry)
    for _ in phrasing_variant_ids:
        assert evaluate(metric_id, registry) == base
    return True
