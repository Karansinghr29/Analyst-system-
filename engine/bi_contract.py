"""
bi_contract.py -- Phase 6. The BI-consumable semantic contract a future Power BI / web
dashboard reads. No frontend is built here; this defines what one would be given.

The Phase 6 brief fixes the field list. Two of those fields carry the whole design:
`trust_level` and `conflicts`. A BI tool's native idiom is one number per tile, and that idiom
is exactly what a SHOW_BOTH/BLOCK metric must not be rendered into. So the contract makes the
refusal machine-readable rather than leaving it to a dashboard author's discretion:

    `headline_permitted = false`  ->  the tile MUST NOT render a single value
    `definitions = [...]`         ->  what to render instead, each separately labelled

A dashboard that ignores `headline_permitted` and renders `definitions[0]` has violated the
contract, and `validate_card()` detects exactly that, so the violation is catchable in CI rather
than discovered by an owner reading a wrong number off a tile.
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.execution import MetricExecutor
from engine.citation import chain_for
from engine.result import NOT_DETERMINABLE_TEXT

# Every field the Phase 6 brief 11 requires a metric to expose.
REQUIRED_CARD_FIELDS = (
    "metric_id", "display_name", "definition", "value", "unit", "period", "dimensions",
    "filters", "trust_level", "confidence", "evidence", "conflicts", "dq_issues",
    "calculation_trace", "comparison", "insight", "recommendation",
)


@dataclass
class MetricCard:
    """One BI tile's complete semantic payload."""
    metric_id: str
    display_name: str
    definition: str
    value: object = None                 # populated ONLY when headline_permitted
    unit: str = ""
    period: str = ""
    dimensions: tuple = ()
    filters: str = ""
    trust_level: str = ""
    confidence: str = ""
    evidence: tuple = ()
    conflicts: tuple = ()
    dq_issues: tuple = ()
    calculation_trace: str = ""
    comparison: object = None
    insight: object = None
    recommendation: str = ""

    # The BI-specific rendering contract.
    headline_permitted: bool = False
    definitions: tuple = ()              # (label, value) -- what to render when no headline
    render_directive: str = ""
    caveat: str = ""
    validation_status: str = ""
    limitations: str = ""
    not_determinable_reason: str = ""

    def as_dict(self):
        return {
            "metric_id": self.metric_id, "display_name": self.display_name,
            "definition": self.definition, "value": self.value, "unit": self.unit,
            "period": self.period, "dimensions": list(self.dimensions),
            "filters": self.filters, "trust_level": self.trust_level,
            "confidence": self.confidence, "evidence": list(self.evidence),
            "conflicts": list(self.conflicts), "dq_issues": list(self.dq_issues),
            "calculation_trace": self.calculation_trace, "comparison": self.comparison,
            "insight": self.insight, "recommendation": self.recommendation,
            "headline_permitted": self.headline_permitted,
            "definitions": [{"label": l, "value": v} for l, v in self.definitions],
            "render_directive": self.render_directive, "caveat": self.caveat,
            "validation_status": self.validation_status, "limitations": self.limitations,
            "not_determinable_reason": self.not_determinable_reason,
        }


# Rendering directives a dashboard must honour. These are instructions to the RENDERER, which is
# why they are part of the data rather than left to prose documentation.
RENDER_SINGLE_VALUE = "render_single_value"
RENDER_MULTI_DEFINITION = "render_all_definitions_labelled"
RENDER_BLOCKED = "render_conflict_explanation_no_headline"
RENDER_NOT_DETERMINABLE = "render_not_determinable_text"


class BIContractBuilder:
    def __init__(self, registry: SemanticRegistry = None, gate: TrustGate = None,
                 executor: MetricExecutor = None):
        self.registry = registry or SemanticRegistry()
        self.gate = gate or TrustGate(self.registry)
        self.executor = executor or MetricExecutor(registry=self.registry, gate=self.gate)

    def card(self, metric_id, comparison=None, insight=None, **calc_kwargs):
        """`calc_kwargs` are the narrowings the caller asked for (e.g. `apartment_code`).

        They are handed to the executor unchanged. A calculator that does not declare one
        REFUSES there rather than ignoring it, so a filtered card either honours the filter or
        says it cannot -- it never returns the estate-wide figure under the narrower label.
        """
        if metric_id not in self.registry:
            return MetricCard(
                metric_id=metric_id, display_name=metric_id, definition="",
                trust_level="NOT_DETERMINABLE", headline_permitted=False,
                render_directive=RENDER_NOT_DETERMINABLE,
                not_determinable_reason=f"{metric_id!r} is not a semantic metric. "
                                        f"{NOT_DETERMINABLE_TEXT}")

        spec = self.registry.get(metric_id)
        answer = self.executor.execute(metric_id, **calc_kwargs)
        chain = chain_for(spec)
        first = answer.results[0] if answer.results else None

        card = MetricCard(
            metric_id=metric_id,
            display_name=spec.display_name or spec.semantic_name,
            definition=spec.definition,
            unit=first.unit if first else "",
            period=first.as_of if first else spec.historical_policy[:160],
            dimensions=tuple(d.strip() for d in spec.dimensions.split(";") if d.strip()),
            filters=spec.filters,
            trust_level=answer.trust_level,
            confidence=answer.confidence,
            # A metric whose declared sources resolve to no manifest key still has provenance --
            # it is just not EXPORTED evidence. M.RISK.009 is the case: it is a meta-metric over
            # this project's own registry, so no CSV underlies it. Falling back to the declared
            # source keeps a tile from rendering a value with a blank provenance field, while
            # the note keeps it honest about what that provenance is.
            evidence=(chain.resolved_keys or
                      (f"declared source (not exported evidence): {spec.source_objects[:120]}",)),
            conflicts=answer.conflict_ids,
            dq_issues=answer.dq_ids,
            calculation_trace=(first.calculation_provenance if first else spec.definition),
            comparison=comparison,
            insight=insight,
            caveat=answer.caveat,
            validation_status=first.validation_status if first else "",
            limitations=first.limitations if first else "",
        )

        if answer.trust_level == "NOT_DETERMINABLE":
            card.headline_permitted = False
            card.render_directive = RENDER_NOT_DETERMINABLE
            card.not_determinable_reason = answer.not_determinable_reason
            return card

        if answer.headline_permitted:
            card.headline_permitted = True
            card.value = answer.headline
            card.render_directive = RENDER_SINGLE_VALUE
        else:
            card.headline_permitted = False
            card.value = None
            card.definitions = tuple((r.definition_label, r.value) for r in answer.results)
            card.render_directive = (RENDER_BLOCKED if answer.trust_level == "BLOCK"
                                     else RENDER_MULTI_DEFINITION)

        for s in (answer.results[0].validation_detail or {}).get("detail", "") if first else "":
            break
        return card

    def dashboard(self, metric_ids):
        return tuple(self.card(m) for m in metric_ids)


def validate_card(card: MetricCard):
    """The contract a consuming dashboard must satisfy. Returns violations."""
    v = []
    d = card.as_dict()
    for f in REQUIRED_CARD_FIELDS:
        if f not in d:
            v.append(f"missing required field {f!r}")

    if not card.metric_id:
        v.append("no metric_id")
    if not card.trust_level:
        v.append("no trust_level")

    if card.trust_level in ("SHOW_BOTH", "BLOCK"):
        if card.headline_permitted:
            v.append(f"{card.trust_level} card permits a headline value")
        if card.value is not None:
            v.append(f"{card.trust_level} card carries a single value")
        if len(card.definitions) < 2:
            v.append(f"{card.trust_level} card exposes {len(card.definitions)} definition(s); "
                     f"a dashboard cannot render the conflict from fewer than 2")
        if not card.conflicts and card.trust_level == "BLOCK":
            v.append("BLOCK card names no conflict, so a tile could not explain the refusal")
        if card.render_directive not in (RENDER_MULTI_DEFINITION, RENDER_BLOCKED):
            v.append(f"{card.trust_level} card carries directive {card.render_directive!r}")

    if card.trust_level == "DISCLOSE" and not card.caveat.strip():
        v.append("DISCLOSE card carries no caveat, so a tile would render it as unqualified")

    if card.trust_level == "NOT_DETERMINABLE":
        if card.value is not None:
            v.append("NOT_DETERMINABLE card carries a value")
        if NOT_DETERMINABLE_TEXT not in (card.not_determinable_reason or ""):
            v.append("NOT_DETERMINABLE card omits the exact required phrase")

    if card.trust_level in ("SAFE", "DISCLOSE"):
        if not card.headline_permitted:
            v.append(f"{card.trust_level} card withholds a headline it is entitled to show")
        if not card.evidence:
            v.append("card exposes a value with no evidence reference")

    if not card.calculation_trace:
        v.append("card exposes no calculation trace")
    return tuple(v)


def validate_dashboard(cards):
    out = {}
    for c in cards:
        problems = validate_card(c)
        if problems:
            out[c.metric_id] = problems
    return out
