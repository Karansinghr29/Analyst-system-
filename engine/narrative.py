"""
narrative.py -- the guarded Local LLM narrative layer, as one reusable boundary.

The deterministic engine decides every number, every definition, every trust posture and every
statement about materiality and cause. A narrative only re-says a result the engine has already
finished, and only when that result is safe to re-say:

    deterministic result -> eligibility -> structured facts -> local model -> guard -> narrative
                                                                                  \\-> deterministic fallback

A narrative KIND (today: the metric-card "why") is described once, as a `NarrativeSpec`: the facts
contract it narrates, the system prompt and prompt builder, the guard that decides acceptance, and
which measures it is switched on for. Everything else -- calling the provider, timing it out,
guarding, sanitising, falling back -- is shared by `generate()`, so a second kind or a second
measure adds facts and a spec, never a second pipeline.

What this module never does: calculate, choose a definition, decide trust, decide materiality,
or establish a cause. Eligibility is read off facts the engine produced; the model is never asked.
"""
from dataclasses import dataclass

from engine import answer_renderer, prompt_contracts
from engine import owner_presentation as op
from engine.llm_provider import LLMUnavailable

# What the owner is told when a narrative was attempted and not used. The reason is logged by the
# caller; it never reaches the owner.
FALLBACK_NOTE = ("The wording layer was not used, so the verified deterministic explanation is "
                 "shown instead.")

# Postures a narrative may state as a factual explanation. SHOW_BOTH and BLOCK would ask the wording
# layer to speak over competing definitions; NOT_DETERMINABLE has no figure to explain.
NARRATABLE_TRUST = ("SAFE", "DISCLOSE")


@dataclass(frozen=True)
class NarrativeSpec:
    """One kind of narrative. Metric-specific facts come from the engine; this is the shared rest."""
    action: str                  # the metric-card action it narrates
    contract: str                # the facts contract name the builder produces
    system_prompt: str
    build_prompt: object         # facts -> prompt text
    guard: object                # (text, facts, draft, other_measure_names=...) -> violations
    enabled_metrics: tuple       # switched on explicitly, measure by measure
    max_tokens: int = 400
    # The narrative is fetched in the background after the verified answer is on screen, so this
    # only bounds how long one background request may hold a worker.
    timeout_seconds: int = 90


WHY = NarrativeSpec(
    action="why",
    contract="metric_why.v1",
    system_prompt=prompt_contracts.METRIC_WHY_NARRATIVE_SYSTEM,
    build_prompt=prompt_contracts.build_metric_why_prompt,
    guard=answer_renderer.guard_metric_narrative,
    enabled_metrics=("M.REV.002", "M.COL.002"),
)

# The Analyst's answer to a whole-business question ("how is the business doing?"). Not scoped to
# one measure, so it has no enabled measures: it is narrated wherever the Local LLM is switched on
# and the facts pass `business_health_eligibility`.
BUSINESS_HEALTH = NarrativeSpec(
    action="business_health",
    contract="business_health.v1",
    system_prompt=prompt_contracts.BUSINESS_HEALTH_NARRATIVE_SYSTEM,
    build_prompt=prompt_contracts.build_business_health_prompt,
    guard=answer_renderer.guard_business_health_narrative,
    enabled_metrics=(),
    max_tokens=900,
    timeout_seconds=150,
)

SPECS = {WHY.action: WHY}


def spec_for(action, metric_id):
    """The spec that narrates this action for this measure, or None when it is not switched on."""
    spec = SPECS.get(action)
    return spec if spec is not None and metric_id in spec.enabled_metrics else None


def why_eligibility(facts):
    """Whether a `metric_why.v1` result may be narrated at all, and every reason it may not.

    Read off the engine's own facts. A measure that is switched on is still not narrated on a day
    its result fails any of these -- a partial month, a posture that became conflicted, a movement
    the detector could not establish.
    """
    facts = facts or {}
    reasons = []
    if facts.get("contract") != WHY.contract:
        reasons.append("no structured why facts")
        return False, tuple(reasons)
    trust = ((facts.get("metric") or {}).get("trust_level") or "").upper()
    if trust not in NARRATABLE_TRUST:
        reasons.append(f"trust posture {trust or 'unknown'} is not narrated as a factual "
                       f"explanation")
    movement = facts.get("movement") or {}
    if not movement.get("available"):
        reasons.append("no period-to-period movement was established")
    if movement.get("partial_period"):
        reasons.append("the current period is only partly recorded")
    for field in ("materiality", "causal_evidence"):
        if not isinstance(facts.get(field), dict) or not (facts[field].get("statement") or ""):
            reasons.append(f"no {field.replace('_', '-')} statement")
    return not reasons, tuple(reasons)


def business_health_eligibility(facts):
    """Whether a `business_health.v1` package may be narrated, and every reason it may not.

    There must be something verified to say -- a stated figure or an established movement -- and
    where movements are reported, the materiality and causal statements that go with them.
    """
    facts = facts or {}
    if facts.get("contract") != BUSINESS_HEALTH.contract:
        return False, ("no structured business-health facts",)
    reasons = []
    if not facts.get("figures") and not facts.get("movements"):
        reasons.append("no stated figure and no established movement")
    if facts.get("movements"):
        for field in ("materiality", "causal_evidence"):
            if not isinstance(facts.get(field), dict) or not (facts[field].get("statement") or ""):
                reasons.append(f"no {field.replace('_', '-')} statement")
    return not reasons, tuple(reasons)


def eligibility_for(spec, facts):
    """Dispatch to the kind's own eligibility rule."""
    if spec is WHY:
        return why_eligibility(facts)
    if spec is BUSINESS_HEALTH:
        return business_health_eligibility(facts)
    return False, (f"no eligibility rule for {spec.action!r}",)


def generate(spec, provider, facts, draft, other_measure_names=()):
    """Ask the provider for a narrative and keep it only if the guard accepts all of it.

    Returns (narrative, ()) or (None, reasons). Whole-output decision: never a partial merge.
    """
    try:
        response = provider.complete(spec.build_prompt(facts), system=spec.system_prompt,
                                     max_tokens=spec.max_tokens, temperature=0.0)
    except LLMUnavailable as exc:
        return None, (f"local model unavailable: {exc}",)
    except Exception as exc:                     # a timeout or transport fault
        return None, (f"local model failed: {type(exc).__name__}",)

    text = getattr(response, "text", "")
    if not isinstance(text, str):
        return None, ("local model returned no text",)
    violations = spec.guard(text, facts, draft, other_measure_names=other_measure_names)
    if violations:
        return None, tuple(violations)
    return op.sanitize_owner_text(text.strip()), ()
