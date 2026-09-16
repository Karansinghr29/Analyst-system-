"""
conversation_context.py -- Phase 4. Minimal conversational state for follow-up resolution.

    "Context must NEVER override explicit new user constraints.
     User: 'Show revenue for July.'  User: 'What about June?'
     The second question inherits the metric but changes only the time period."

That rule is the whole design. Inheritance is strictly ADDITIVE onto fields the new request
left empty; a field the user supplied explicitly is never touched. `inherited_fields` records
exactly what was carried forward, so a caller (and a test) can see what context contributed
rather than having to infer it.

State is per-conversation and in-memory only: no persistence, no retrieval index, no embeddings.
The brief forbids RAG/vector search, and none is needed -- resolving "what about June?" requires
the previous turn, not a search over history.
"""
from dataclasses import dataclass, field, replace

from engine.structured_output import LLMPlanRequest

# Phrases that signal a follow-up referring back to the previous turn rather than a fresh
# question. Deterministic, and used only to decide whether inheritance is appropriate at all --
# never to decide WHAT the answer is.
FOLLOWUP_MARKERS = (
    "what about", "how about", "and for", "and in", "same for", "that one",
    "break that down", "break it down", "drill into", "split that",
    "why", "why is that", "why did that", "what caused", "what drove",
    "the other definition", "other definition", "the other one", "show me the other",
    "which tenants are affected", "who is affected", "which ones",
    "and the", "what about last", "same question",
    # "Explain this" / "explain that" refer back as plainly as "why" does. A bare "explain"
    # is included too: it can only ever inherit into fields the new request left EMPTY, so a
    # question that names its own subject ("explain collections") keeps that subject.
    "explain this", "explain that", "explain", "tell me more", "what does that mean",
)

# Follow-ups that ask about the previous answer itself rather than a new aspect of its measure.
_EXPLAIN_BACK_MARKERS = ("explain this", "explain that", "explain it", "tell me more",
                         "what does that mean", "in simple terms", "simply")

# Markers of an EXPLICIT new constraint. When one is present for a field, that field is the
# user's, and context must not touch it.
_TIME_MARKERS = ("next month", "next year", "next quarter", "last month", "this month",
                 "last year", "this year", "last quarter",
                 "year to date", "ytd", "january", "february", "march", "april", "may",
                 "june", "july", "august", "september", "october", "november", "december",
                 "forecast", "prediction")


@dataclass
class Turn:
    question: str
    request: object = None       # LLMPlanRequest
    plan: object = None          # AnalyticsPlan
    answer: object = None        # RenderedAnswer
    trust_level: str = ""
    metric_ids: tuple = ()
    definitions_shown: tuple = ()


@dataclass
class ConversationContext:
    turns: list = field(default_factory=list)
    max_turns: int = 20

    # Phase 5 additions. `pending_clarification` is the open question, if any;
    # `definition_selections` records EXPLICIT user choices of one competing definition,
    # keyed by concept. Both are consulted only where the code below says so -- neither is
    # allowed to silently influence a fresh, unrelated question.
    pending_clarification: object = None
    definition_selections: dict = field(default_factory=dict)
    # Whole-business workflow from the previous turn (briefing / what-to-do / ...). Used only
    # so a bare follow-up can repeat that workflow; never to override a named concept.
    last_owner_intent: str = ""

    # -- state --------------------------------------------------------------------------------

    def record(self, turn: Turn):
        self.turns.append(turn)
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    # -- clarification lifecycle (Phase 5 objective 4) ------------------------------------------

    def open_clarification(self, clarification, option_metric_ids=(),
                           original_question=""):
        from engine.conversation_state import PendingClarification, CLAR_REQUIRED
        self.pending_clarification = PendingClarification(
            trigger=clarification.trigger, question=clarification.question,
            options=tuple(clarification.options), option_metric_ids=tuple(option_metric_ids),
            asked_at_turn=len(self.turns), state=CLAR_REQUIRED,
            original_question=(original_question or "").strip())
        return self.pending_clarification

    def answer_clarification(self, text):
        """Interpret a reply to an open clarification. Returns the resulting state.

        The critical branch is the last one: a reply that does not decisively select an option
        leaves the clarification OPEN. It is never treated as permission to choose -- "Never
        reinterpret an unanswered clarification as permission to choose a definition."
        """
        from engine import conversation_state as cs
        pc = self.pending_clarification
        if pc is None:
            return None

        if cs.detect_rejection(text):
            pc.state = cs.CLAR_REJECTED
            return pc

        idx = cs.detect_selection(text, pc.options, pc.option_metric_ids)
        if idx is not None:
            pc.state = cs.CLAR_ANSWERED
            pc.resolution = pc.options[idx]
            if pc.option_metric_ids and idx < len(pc.option_metric_ids):
                pc.resolved_metric_id = pc.option_metric_ids[idx]
            return pc

        pc.state = cs.CLAR_STILL_AMBIGUOUS
        return pc

    def close_clarification(self):
        self.pending_clarification = None

    @property
    def awaiting_clarification(self):
        from engine.conversation_state import CLAR_REQUIRED, CLAR_STILL_AMBIGUOUS
        return (self.pending_clarification is not None
                and self.pending_clarification.state in (CLAR_REQUIRED, CLAR_STILL_AMBIGUOUS))

    # -- explicit definition selection ------------------------------------------------------------

    def select_definition(self, selection):
        """Record an EXPLICIT user choice. Only ever called from a turn in which the user
        selected a definition they had already been shown."""
        self.definition_selections[selection.concept] = selection
        return selection

    def selected_definition(self, concept):
        return self.definition_selections.get(concept)

    def clear_selection(self, concept):
        self.definition_selections.pop(concept, None)

    def last_definitions_shown(self):
        prev = self.last
        return tuple(prev.definitions_shown) if prev else ()

    @property
    def last(self):
        return self.turns[-1] if self.turns else None

    def clear(self):
        """Reset the WHOLE conversation, not just its turn list.

        An open clarification and a recorded definition selection are conversation state exactly
        as much as the turns are. Leaving them behind meant a reset context still believed it
        was awaiting an answer, so the next unrelated question was consumed as a reply to a
        question the user could no longer see -- and a definition the user had selected for one
        concept persisted into a conversation that never mentioned it.
        """
        self.turns = []
        self.pending_clarification = None
        self.definition_selections = {}
        self.last_owner_intent = ""

    # -- follow-up detection --------------------------------------------------------------------

    @staticmethod
    def looks_like_followup(question):
        # Trailing punctuation is stripped, not just "?": an owner typing "Why." means exactly
        # what "Why?" means, and treating the two differently would be a parsing artefact
        # visible to them as an inconsistent product.
        q = (question or "").lower().strip().rstrip("?.!").strip()
        if q in ("why", "why though", "and", "how so"):
            return True
        return any(m in q for m in FOLLOWUP_MARKERS)

    def resolve(self, request: LLMPlanRequest, question=""):
        """Apply context to a newly-extracted request. Returns (request, inherited_fields).

        Inheritance happens ONLY into fields the new request left empty. Every branch below is
        an `if not <field>` -- there is no code path that overwrites a value the user supplied.
        """
        from engine import conversation_state as cs

        prev = self.last
        if prev is None or prev.request is None:
            return request, ()

        # A CORRECTION replaces context rather than extending it. This is the one case where
        # inherited state must be dropped: the user is telling us the prior state was wrong, so
        # carrying it forward would preserve the very error they are correcting.
        if cs.detect_correction(question or "") is not None:
            return request, ("correction:context_dropped",)

        if not self.looks_like_followup(question or ""):
            return request, ()

        inherited = []
        updates = {}
        prior = prev.request

        # Metric / concept: inherited when the follow-up names none.
        if not request.concept and not request.metric_ids:
            if prior.concept:
                updates["concept"] = prior.concept
                inherited.append("concept")
            if prior.metric_ids:
                updates["metric_ids"] = prior.metric_ids
                inherited.append("metric_ids")

        # Time: inherited ONLY when the follow-up states no period of its own. "What about
        # June?" supplies its own period, so July must not be carried forward.
        if not request.time_range and not _states_a_period(question):
            if prior.time_range:
                updates["time_range"] = prior.time_range
                inherited.append("time_range")

        # Dimensions / filters: additive only.
        if not request.dimensions and prior.dimensions:
            updates["dimensions"] = prior.dimensions
            inherited.append("dimensions")
        if not request.filters and prior.filters:
            updates["filters"] = dict(prior.filters)
            inherited.append("filters")

        if not request.comparison and prior.comparison:
            updates["comparison"] = prior.comparison
            inherited.append("comparison")

        # "Why?" upgrades the intent to a driver question about the SAME metric -- it does not
        # change what is being measured.
        q = (question or "").lower().strip().rstrip("?.!").strip()
        if q in ("why", "why though") or q.startswith("why"):
            if "driver" not in request.intent:
                updates["intent"] = tuple(dict.fromkeys(tuple(request.intent) + ("driver",)))
                updates["explanation_requested"] = True
                inherited.append("intent:driver")
        # "Explain that" / "tell me more" asks about the answer just given, so it keeps what that
        # question asked -- a movement stays a movement -- rather than becoming a bare lookup of
        # the same measure. Only when the follow-up states no analysis of its own.
        elif (any(m in q for m in _EXPLAIN_BACK_MARKERS)
              and tuple(request.intent) in ((), ("lookup",)) and prior.intent
              and {"concept", "metric_ids"} & set(inherited)):
            updates["intent"] = tuple(prior.intent)
            updates["explanation_requested"] = True
            inherited.append("intent:previous")

        if not updates:
            return request, ()
        return replace(request, **updates), tuple(inherited)

    def followup_seed(self, question):
        """An EMPTY request for a follow-up the model could not interpret on its own.

        A bare "Why?" is genuinely uninterpretable in isolation, so the question-understanding
        stage rightly rejects it -- but it is perfectly interpretable given the previous turn,
        and the owner means it as an ordinary follow-up rather than a new question.

        This returns a request with NOTHING filled in. Every field is then populated by
        `resolve()` from the previous turn using the same additive inheritance any other
        follow-up gets, so there is exactly one inheritance code path rather than two. Returns
        None unless this really is a follow-up and the previous turn really had a subject --
        without both, the honest answer is still to ask.

        This invents no concept and asserts no figure. The inherited request is planned and
        gated from scratch like any other, so a follow-up cannot reach an answer its own
        question would not have been allowed to reach.
        """
        if not self.looks_like_followup(question or ""):
            return None

        # A follow-up that names a subject of its own is NOT a bare reference back. "Explain
        # collections" reads as a follow-up by phrasing, but it says what it is about; seeding
        # it from the previous turn would answer a different question than the one asked, which
        # is the failure this whole system exists to prevent. When the model could not read
        # such a question, asking for clarification is the honest response.
        from engine import concept_map
        if concept_map.match(question or ""):
            return None

        prev = self.last
        if prev is None or prev.request is None:
            return None
        if not (getattr(prev.request, "concept", "") or
                getattr(prev.request, "metric_ids", ())):
            return None
        return LLMPlanRequest(intent=("lookup",))

    # -- prompt context ---------------------------------------------------------------------------

    def context_note(self):
        """A short, factual summary handed to the extraction prompt so the model can resolve
        references. It states what the previous turn WAS -- it never instructs the model to
        reuse it, because the inheritance decision is made in code above, not by the model."""
        prev = self.last
        if prev is None or prev.request is None:
            return ""
        parts = [f"Previous question: {prev.question!r}"]
        if prev.request.concept:
            parts.append(f"previous concept: {prev.request.concept}")
        if prev.metric_ids:
            parts.append(f"previous metric_ids: {', '.join(prev.metric_ids)}")
        if prev.request.time_range:
            parts.append(f"previous time range: {prev.request.time_range}")
        if prev.trust_level:
            parts.append(f"previous trust level: {prev.trust_level}")
        if prev.definitions_shown:
            parts.append(f"definitions already shown: {', '.join(prev.definitions_shown)}")
        return "; ".join(parts)


def _states_a_period(question):
    q = (question or "").lower()
    if any(m in q for m in _TIME_MARKERS):
        return True
    import re
    return bool(re.search(r"\b(20\d{2})(-\d{2})?\b", q))
