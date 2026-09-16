"""
clarification_manager.py -- Phase 4. Decides when to ask instead of guessing, and phrases the
question in business language.

    "Ask clarification instead of guessing when:
       * multiple metric families match
       * multiple conflicting definitions are materially different
       * time range is ambiguous
       * requested dimension is unsupported
       * entity identity cannot be established from exported evidence
       * the requested comparison is outside historical coverage
     Clarification must be concise and business-friendly."

The decision is deterministic. The Phase 3 layer already produces a ClarificationRequest for the
cases it detects; this module adds the Phase-4-specific triggers (a model that reported its own
ambiguity, a model whose plan failed contract validation) and converts every one of them into
short business English -- the internal reason text cites spec sections, which is right for an
audit trail and wrong for a person.
"""
from dataclasses import dataclass

from engine.intent_models import ClarificationRequest

# One trigger per bullet in the brief, so the mapping is checkable rather than implied.
TRIGGER_MULTIPLE_FAMILIES = "multiple_metric_families"
TRIGGER_CONFLICTING_DEFINITIONS = "conflicting_definitions"
TRIGGER_AMBIGUOUS_TIME = "ambiguous_time_range"
TRIGGER_UNSUPPORTED_DIMENSION = "unsupported_dimension"
TRIGGER_UNKNOWN_ENTITY = "entity_not_identifiable"
TRIGGER_OUTSIDE_COVERAGE = "comparison_outside_coverage"
TRIGGER_MODEL_UNCERTAIN = "model_reported_ambiguity"
TRIGGER_INVALID_PLAN = "invalid_plan"

ALL_TRIGGERS = (TRIGGER_MULTIPLE_FAMILIES, TRIGGER_CONFLICTING_DEFINITIONS,
                TRIGGER_AMBIGUOUS_TIME, TRIGGER_UNSUPPORTED_DIMENSION, TRIGGER_UNKNOWN_ENTITY,
                TRIGGER_OUTSIDE_COVERAGE, TRIGGER_MODEL_UNCERTAIN, TRIGGER_INVALID_PLAN)


@dataclass(frozen=True)
class Clarification:
    trigger: str
    question: str            # business-friendly, shown to the user
    options: tuple           # concrete choices, each self-describing
    internal_reason: str     # spec-citing audit trail, not shown to the user
    # The choices are already named in the question itself, so no numbered list follows it. Used
    # for ordinary "which area?" ambiguity. A choice between competing DEFINITIONS is never
    # inline: each option there needs its own description, because the owner is deciding which
    # evidence-backed figure stands.
    inline: bool = False

    def render(self):
        from engine.owner_presentation import sanitize_owner_text
        if self.inline:
            return sanitize_owner_text(self.question)
        lines = [sanitize_owner_text(self.question)]
        for i, opt in enumerate(self.options, 1):
            lines.append(f"  {i}. {sanitize_owner_text(opt)}")
        return "\n".join(lines)


def inline_choices(options):
    """"a, b or c" -- the options as they would be said in one sentence."""
    names = [str(o).strip() for o in options or () if str(o).strip()]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " or " + names[-1]


def is_subject_menu(options):
    """True when the options are bare business-area names ("Revenue", "Tenant dues"), not
    self-describing definitions or periods. Only those read naturally inside one sentence."""
    names = [str(o).strip() for o in options or ()]
    return bool(names) and all(
        n and len(n.split()) <= 3 and not any(ch.isdigit() for ch in n)
        and not any(ch in n for ch in ":—-()") for n in names)


class ClarificationManager:
    def __init__(self, registry=None):
        from engine.semantic_registry import SemanticRegistry
        self.registry = registry or SemanticRegistry()

    # -- Phase 3 clarifications, rephrased for a person -------------------------------------

    def from_plan(self, plan):
        """Convert a Phase 3 ClarificationRequest into business English."""
        cr = plan.clarification
        if cr is None:
            return None
        if cr.kind == "referential":
            # Entity/PII cases use the stock tenant wording. Period / forecast / capability
            # clarifications already carry owner-facing questions — pass them through.
            q = (cr.question or "").strip()
            low = q.lower()
            entity_shaped = (
                "which specific entity" in low
                or "personal identifying" in low
                or "tenant or unit" in low
                or (low.startswith("which specific") and "period" not in low
                    and "forecast" not in low and "time" not in low)
            )
            if entity_shaped or not q:
                question = ("Which specific tenant or unit do you mean? Personal identifying "
                            "details aren't part of the exported data, so I can't match a name -- "
                            "an ID from the system would let me look it up.")
            elif is_subject_menu(cr.options):
                # "Which measure should I look up?" followed by a numbered list read as a command
                # menu. The same choice, asked the way a person would ask it.
                return Clarification(
                    trigger=TRIGGER_AMBIGUOUS_TIME,
                    question=f"Which area would you like me to look at: "
                             f"{inline_choices(cr.options).lower()}?",
                    options=cr.options,
                    internal_reason=cr.reason,
                    inline=True,
                )
            else:
                question = q if q.endswith("?") else q
            return Clarification(
                trigger=TRIGGER_UNKNOWN_ENTITY if entity_shaped else TRIGGER_AMBIGUOUS_TIME,
                question=question,
                options=cr.options,
                internal_reason=cr.reason,
            )
        return Clarification(
            trigger=TRIGGER_CONFLICTING_DEFINITIONS,
            question=self._business_phrasing(cr),
            options=tuple(self._describe_option(o) for o in cr.options),
            internal_reason=cr.reason,
        )

    def _business_phrasing(self, cr: ClarificationRequest):
        q = cr.question.strip()
        if q.endswith("?"):
            return q
        return f"{q}?"

    def _describe_option(self, option):
        """Options arrive as "M.COL.001: Collections (application-level) [DISCLOSE]".
        Owner-facing text leads with the business name and omits internal metric IDs."""
        if ":" in option:
            mid, rest = option.split(":", 1)
            mid = mid.strip()
            if mid in self.registry:
                spec = self.registry.get(mid)
                return f"{spec.semantic_name} — {spec.description[:120]}"
        # Strip any bare metric ids that slipped into option text.
        from engine.owner_presentation import sanitize_owner_text
        return sanitize_owner_text(option)

    # -- Phase 4 triggers -----------------------------------------------------------------------

    def from_model_uncertainty(self, request, question):
        """The model reported its own ambiguity. Trusted as a signal to ASK -- never as a
        licence to pick."""
        return Clarification(
            trigger=TRIGGER_MODEL_UNCERTAIN,
            question=("I want to make sure I answer the right question. "
                      + (request.clarification_reason or
                         "Your question could be read more than one way.")
                      + " Which did you mean?"),
            options=tuple(
                f"{self.registry.get(m).semantic_name}"
                for m in request.metric_ids if m in self.registry) or
                    ("Please name the measure you're interested in.",),
            internal_reason=f"model set clarification_needed=true: "
                            f"{request.clarification_reason!r}",
        )

    def from_invalid_plan(self, violations, question):
        """A plan that failed contract validation. The user sees a plain request; the spec-level
        violations stay in the audit trail. Critically, this path NEVER executes anything."""
        semantic = [v for v in violations
                    if "does not exist in semantic_metric_registry" in v
                    or "is not in the concept map" in v
                    or "not catalogued in business_dimensions" in v]
        if semantic:
            q = ("I can only report measures that are defined in this system, and I couldn't "
                 "match your question to one of them. Could you rephrase it, or tell me which "
                 "area you mean — revenue, collections, tenant dues, deposits, occupancy, "
                 "expenses, profit, owner payments, maintenance, electricity, tenant "
                 "lifecycle, accounting, or data quality?")
        else:
            q = ("I couldn't turn that into a well-formed analysis request. Could you rephrase "
                 "it a little more specifically?")
        return Clarification(
            trigger=TRIGGER_INVALID_PLAN,
            question=q,
            options=("Name a business area", "Name a specific measure",
                     "Ask what measures are available"),
            internal_reason="; ".join(violations),
        )

    def from_ambiguous_selection(self, labels, question):
        """The user explicitly tried to select a definition, but their wording fits more than
        one of the definitions they were shown. Asking is the only safe response: picking would
        be the silent narrowing ai_trust_policy.md forbids, and ignoring the attempt would leave
        an explicit instruction unacknowledged."""
        return Clarification(
            trigger=TRIGGER_CONFLICTING_DEFINITIONS,
            question=("More than one of these definitions matches what you asked for. "
                      "Which did you mean?"),
            options=tuple(labels) or ("Please name one of the definitions shown above.",),
            internal_reason=(
                f"conversation_state.detect_selection_attempt found a selection verb in "
                f"{question!r} but {len(labels)} candidate definitions; narrowing on an "
                f"ambiguous selection would be a silent resolution of a competing-definition "
                f"conflict (ai_trust_policy.md)."),
        )

    def from_unsupported_dimension(self, plan):
        return Clarification(
            trigger=TRIGGER_UNSUPPORTED_DIMENSION,
            question=("That breakdown isn't available for this measure. Would you like the "
                      "overall figure instead, or a different breakdown?"),
            options=("Overall figure", "A different breakdown"),
            internal_reason="; ".join(plan.rejection_reasons),
        )

    def from_coverage_limit(self, plan):
        t = plan.time
        window = (f"{t.coverage_start} to {t.coverage_end}"
                  if t and t.coverage_start else "the exported period")
        return Clarification(
            trigger=TRIGGER_OUTSIDE_COVERAGE,
            question=(f"That period isn't fully covered by the exported data, which runs "
                      f"{window}. Would you like the figure for the covered period instead?"),
            options=(f"Use {window}", "Choose a different period"),
            internal_reason=plan.not_determinable_reason,
        )

    # -- routing -------------------------------------------------------------------------------

    def for_plan(self, plan):
        """Pick the right clarification for a plan that did not reach READY/BLOCKED, or None if
        the plan needs no clarification (a genuine NOT_DETERMINABLE is an ANSWER, not a
        question -- an absent metric is not made present by asking again)."""
        if plan.clarification is not None:
            return self.from_plan(plan)
        if plan.status == "REJECTED":
            return self.from_unsupported_dimension(plan)
        if plan.status == "NOT_DETERMINABLE" and plan.time is not None and (
                not plan.time.within_coverage or not plan.time.yoy_permitted):
            return self.from_coverage_limit(plan)
        return None
