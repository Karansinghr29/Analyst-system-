"""
gate.py -- Phase 2. The Trust & Conflict Gate as a HARD, BINDING gate (Layer 3 of
ai_analytics_architecture.md; the "Trust Gatekeeper" role of ai_agent_roles.md 2).

What Phase 1 had, and why it was not enough
-------------------------------------------
Phase 1's execution.py computed a metric and THEN labelled the answer with a trust level. That
satisfies disclosure but violates the architecture's **directionality rule**:

    "Layer 4 (Analytics Execution) may never compute a number that Layer 3 (Trust & Conflict
     Gate) has not already cleared -- trust checking happens BEFORE execution, not as a post-hoc
     filter on the answer, because a BLOCK metric must never even be *computed and then hidden*;
     it must never be computed for user-facing output at all (it may still be computed
     internally for the AI's own reasoning about *why* it's blocked)."

Phase 2 therefore makes authorization a separate, mandatory, *prior* step that returns a
`GateDecision`, and routes BLOCK output into an explicitly internal-only channel that carries no
headline. ai_agent_roles.md 3: "The Trust Gatekeeper's verdict is binding on every downstream
role. No later role may reinterpret or soften a BLOCK verdict."

The gate combines THREE independent sources of trust, and takes the worst of all three:
  1. the metric's own `trust_level`                      (semantic_metric_registry.csv)
  2. metric -> metric dependency propagation             (trust_gate.evaluate, Phase 1)
  3. DQ/conflict -> metric propagation                   (propagation.documented_floor, Phase 2)

Source 3 is new in Phase 2 and is what makes the trust assignment *auditable* rather than
taken on faith from a CSV column.
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine.trust_gate import evaluate as trust_evaluate, TrustVerdict
from engine import propagation

_SEVERITY = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}

# Execution modes the gate may authorize.
MODE_SINGLE = "single"                # one headline value permitted
MODE_FAMILY = "family"                # ALL competing definitions required; no headline
MODE_INTERNAL_ONLY = "internal_only"  # BLOCK: compute for disclosure/reasoning, never headline
MODE_REFUSE = "refuse"                # NOT_DETERMINABLE: do not compute for user-facing output


class GateViolation(Exception):
    """Raised when a caller attempts an operation the gate did not authorize. This is a
    programming error in the engine, never a business outcome -- it must fail loudly rather than
    degrade into a plausible-looking answer."""


@dataclass(frozen=True)
class GateDecision:
    metric_id: str
    verdict: TrustVerdict
    effective_level: str
    execution_mode: str
    headline_permitted: bool
    caveat_required: bool
    required_definitions: tuple      # every metric_id that MUST be computed together
    required_disclosures: tuple      # conflict_ids + dq_ids that MUST appear in the answer
    propagation_justification: str   # metric_dependency_graph.md 6 audit trail
    reason: str
    own_level: str                   # the metric's intrinsic trust_level, before propagation
    dependency_level: str            # worst level reached via dependency_metrics
    documented_floor: str            # worst level required by metric_dependency_graph.md 6

    def assert_headline_permitted(self):
        if not self.headline_permitted:
            raise GateViolation(
                f"{self.metric_id}: trust level {self.effective_level} forbids a single headline "
                f"number. {self.reason}"
            )

    def assert_definitions_complete(self, produced_labels):
        """SHOW_BOTH/BLOCK families must never be narrowed. ai_evaluation_framework.md 1.2:
        'confirm the answer structurally contains ALL competing definitions, not a subset.'"""
        if self.execution_mode not in (MODE_FAMILY, MODE_INTERNAL_ONLY):
            return True
        if len(produced_labels) < 2:
            raise GateViolation(
                f"{self.metric_id}: {self.effective_level} requires the full set of competing "
                f"definitions; only {len(produced_labels)} was produced ({produced_labels})."
            )
        return True


class TrustGate:
    """The single authorization point. Nothing in the engine may invoke a calculator for
    user-facing output without first holding a GateDecision from this class."""

    def __init__(self, registry: SemanticRegistry = None):
        self.registry = registry or SemanticRegistry()

    def authorize(self, metric_id) -> GateDecision:
        if metric_id not in self.registry:
            # ai_analytics_architecture.md 8: an unresolvable metric is NOT_DETERMINABLE, never
            # an improvised calculation.
            return GateDecision(
                metric_id=metric_id, verdict=None, effective_level="NOT_DETERMINABLE",
                execution_mode=MODE_REFUSE, headline_permitted=False, caveat_required=False,
                required_definitions=(), required_disclosures=(),
                propagation_justification="",
                reason=f"{metric_id!r} does not exist in semantic_metric_registry.csv.",
                own_level="NOT_DETERMINABLE", dependency_level="NOT_DETERMINABLE",
                documented_floor="NOT_DETERMINABLE",
            )

        spec = self.registry.get(metric_id)
        verdict = trust_evaluate(metric_id, self.registry)

        floor = propagation.documented_floor(metric_id)
        effective = verdict.effective_level
        if floor is not None and _SEVERITY[floor] > _SEVERITY[effective]:
            effective = floor

        mode = {
            "SAFE": MODE_SINGLE, "DISCLOSE": MODE_SINGLE,
            "SHOW_BOTH": MODE_FAMILY, "BLOCK": MODE_INTERNAL_ONLY,
            "NOT_DETERMINABLE": MODE_REFUSE,
        }[effective]

        required = ()
        if mode in (MODE_FAMILY, MODE_INTERNAL_ONLY):
            required = tuple(self.registry.family_members(metric_id))

        reason = verdict.reason
        if floor is not None and _SEVERITY[floor] > _SEVERITY[verdict.effective_level]:
            reason = (f"Raised to {effective} by metric_dependency_graph.md 6's documented "
                      f"propagation floor. {reason}")

        return GateDecision(
            metric_id=metric_id, verdict=verdict, effective_level=effective,
            execution_mode=mode,
            headline_permitted=(mode == MODE_SINGLE),
            caveat_required=(effective == "DISCLOSE"),
            required_definitions=required,
            required_disclosures=tuple(spec.conflict_ids) + tuple(spec.dq_ids),
            propagation_justification=propagation.justification(metric_id),
            reason=reason,
            own_level=spec.trust_level,
            dependency_level=verdict.effective_level,
            documented_floor=floor or "SAFE",
        )

    # -- ai_analytics_architecture.md 7: prevention of metric mixing ---------------------------

    def authorize_combination(self, metric_ids, operation="arithmetic"):
        """Architecture 7. Combining two metric_ids is permitted ONLY when
        metric_dependency_graph.md documents the combination. Three prohibited classes:

          1. Same-family members (e.g. M.AR.001A + M.AR.001C) -- would double-count competing
             definitions of one concept.
          2. Any member whose gate verdict forbids a headline -- a BLOCK/SHOW_BOTH input
             poisons the composite ("EVERY composite KPI inherits the WORST trust level of its
             inputs", metric_dependency_graph.md 7).
          3. Different `date_field` bases (the M.OWN.002 / DQ.017 scenario) -- "the date_field
             is part of a metric's identity for mixing-prevention purposes, not an
             interchangeable parameter."

        Returns (permitted: bool, effective_level: str, reasons: tuple). Never raises for a
        business-level refusal -- refusal IS the correct answer, and the caller must surface it.
        """
        reasons = []
        decisions = [self.authorize(m) for m in metric_ids]

        unknown = [d.metric_id for d in decisions if d.verdict is None]
        if unknown:
            return False, "NOT_DETERMINABLE", (
                f"Unknown metric_id(s) {unknown}: not in semantic_metric_registry.csv.",)

        families = {}
        for mid in metric_ids:
            fam = tuple(self.registry.family_members(mid))
            if len(fam) > 1:
                families.setdefault(fam, []).append(mid)
        for fam, members in families.items():
            if len(members) > 1:
                reasons.append(
                    f"Cross-family arithmetic refused: {members} are competing definitions of "
                    f"one concept (family {list(fam)}); combining them would double-count "
                    f"(ai_analytics_architecture.md 7 mechanism 2).")

        worst = "SAFE"
        for d in decisions:
            if _SEVERITY[d.effective_level] > _SEVERITY[worst]:
                worst = d.effective_level
            if not d.headline_permitted:
                reasons.append(
                    f"{d.metric_id} is {d.effective_level} and may not contribute a single "
                    f"number to a composite (metric_dependency_graph.md 7 worst-of-inputs).")

        if operation in ("arithmetic", "trend"):
            bases = {mid: date_basis_columns(self.registry.get(mid).date_field)
                     for mid in metric_ids}
            named = {m: b for m, b in bases.items() if b}
            if len(named) > 1:
                ids = list(named)
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        a, b = ids[i], ids[j]
                        if not (named[a] & named[b]):
                            reasons.append(
                                f"Time-basis mixing refused: {a} is based on "
                                f"{sorted(named[a])} and {b} on {sorted(named[b])}, with no "
                                f"shared date column (ai_analytics_architecture.md 7 "
                                f"mechanism 3 -- the date_field is part of a metric's "
                                f"identity, not an interchangeable parameter).")

        # Architecture 7 mechanism 2: a combination is documented ONLY if some registry metric
        # already declares all of these metric_ids as its own dependencies -- i.e. the semantic
        # layer already names this composite. "revenue - expenses = net_profit for a SINGLE,
        # NAMED profit definition is valid WITHIN that definition."
        requested = set(metric_ids)
        covering = [mid for mid in self.registry.all_ids()
                    if requested <= set(self.registry.get(mid).dependency_metrics)]
        if len(metric_ids) > 1:
            if not covering:
                reasons.append(
                    f"Undocumented combination: no metric in semantic_metric_registry.csv "
                    f"declares {sorted(requested)} as its dependencies, so this composite is "
                    f"not a registry metric (ai_analytics_architecture.md 6.3 / 7 mechanism 2 "
                    f"-- decompose into the documented components or return "
                    f"'Not determinable from exported evidence.', never synthesize a new ratio).")
            else:
                # The composite IS documented -- but it inherits the covering metric's trust
                # level. This is the guard that stops "profit" being reconstructed as
                # SAFE-revenue minus SAFE-expenses, bypassing M.PROFIT.001's BLOCK verdict.
                for cov in covering:
                    cov_level = self.authorize(cov).effective_level
                    if _SEVERITY[cov_level] > _SEVERITY[worst]:
                        worst = cov_level
                    if cov_level != "SAFE":
                        reasons.append(
                            f"This combination is the documented composite {cov} "
                            f"({self.registry.get(cov).semantic_name}), whose own trust level is "
                            f"{cov_level}. The composite inherits it -- computing it from its "
                            f"components would bypass {cov}'s verdict "
                            f"(ai_agent_roles.md 3: the Trust Gatekeeper's verdict is binding).")

        return (not reasons), worst, tuple(reasons)


# Known business date columns in this schema, drawn from business_dimensions.md 1 and the
# date_field column's own vocabulary. `date_field` in the registry is prose (it documents
# per-definition nuance), so mixing-prevention must compare the underlying COLUMNS it names,
# never the prose strings -- two metrics both reading entry_date describe it differently.
_DATE_COLUMNS = (
    "entry_date", "bill_date", "paid_date", "due_date", "invoice_date", "billing_month",
    "expense_date", "payment_date", "settlement_date", "actual_exit_date", "onboarding_date",
    "detected_at", "created_at",
)


def date_basis_columns(date_field_text):
    """Extract the set of real date columns a metric's prose `date_field` names. Returns an
    empty set for 'Not applicable' / snapshot metrics -- an empty set asserts nothing about
    mixing (an unknown basis is not evidence of a DIFFERENT basis)."""
    text = (date_field_text or "").lower()
    return {c for c in _DATE_COLUMNS if c in text}
