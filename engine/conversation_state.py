"""
conversation_state.py -- Phase 5. The multi-turn capabilities Phase 4 left open: clarification
lifecycle, explicit definition selection, and user correction.

This module extends `conversation_context.py` rather than replacing it; that module's
additive-only inheritance rule is unchanged and still governs every field carried forward.

The rule that shapes everything here
------------------------------------
    "Never reinterpret an unanswered clarification as permission to choose a definition."

A SHOW_BOTH/BLOCK family may be narrowed to one definition in exactly one circumstance: the user
explicitly selected it, in their own turn, after being shown the alternatives. Not because they
seemed impatient, not because they repeated the question, not because the model proposed one,
and not because a clarification went unanswered. `DefinitionSelection` records who chose, which
turn they chose in, and what they were shown -- so an audit can distinguish a user's decision
from the system's inference, which is the whole point.

Narrowing still discloses: selecting a definition changes which figure is headline, never the
fact that competing definitions exist.
"""
import re
from dataclasses import dataclass, field

# --- Clarification lifecycle (Phase 5 objective 4) ----------------------------------------------

CLAR_REQUIRED = "REQUIRED"                        # asked, awaiting an answer
CLAR_ANSWERED = "ANSWERED"                        # the user chose one of the options
CLAR_REJECTED = "REJECTED"                        # the user declined to choose
CLAR_STILL_AMBIGUOUS = "STILL_AMBIGUOUS"          # the user replied, but not decisively
CLAR_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"   # no answer could resolve it

ALL_CLARIFICATION_STATES = (CLAR_REQUIRED, CLAR_ANSWERED, CLAR_REJECTED, CLAR_STILL_AMBIGUOUS,
                            CLAR_INSUFFICIENT_EVIDENCE)

_REJECTION_PHRASES = ("don't know", "dont know", "not sure", "no idea", "whichever",
                      "you decide", "you choose", "doesn't matter", "doesnt matter",
                      "either", "any of them", "just pick", "surprise me", "skip")

_ORDINALS = {"first": 0, "1st": 0, "one": 0, "1": 0,
             "second": 1, "2nd": 1, "two": 1, "2": 1,
             "third": 2, "3rd": 2, "three": 2, "3": 2,
             "fourth": 3, "4th": 3, "four": 3, "4": 3,
             "fifth": 4, "5th": 4, "five": 4, "5": 4}

_CORRECTION_PHRASES = ("no, i meant", "no i meant", "i meant", "actually", "sorry, i meant",
                       "not that", "that's not what", "thats not what", "correction",
                       "rather than", "instead i want", "i actually want")


@dataclass
class PendingClarification:
    """A question put to the user, and everything needed to interpret their reply."""
    trigger: str
    question: str
    options: tuple                 # what the user was shown, in order
    option_metric_ids: tuple = ()  # metric_id per option, where each maps to one
    asked_at_turn: int = -1
    state: str = CLAR_REQUIRED
    resolution: str = ""           # the chosen option, once answered
    resolved_metric_id: str = ""
    # The owner question that triggered clarification. Selection replies ("1", option
    # text) must NOT replace this — period/concept live on the original question.
    original_question: str = ""


@dataclass(frozen=True)
class DefinitionSelection:
    """An EXPLICIT user choice of one definition from a competing set. The provenance fields are
    not decoration: they are the evidence that the narrowing was the user's decision."""
    concept: str
    metric_id: str = ""            # when the family members are separate metric_ids
    definition_label: str = ""     # when the definitions live inside one metric_id
    selected_at_turn: int = -1
    user_text: str = ""            # the exact turn in which they chose
    alternatives_shown: tuple = ()

    def disclosure(self):
        """Even a selected definition discloses that others exist -- selection changes which
        figure leads, never the fact of the conflict."""
        alts = ", ".join(a for a in self.alternatives_shown
                         if a not in (self.metric_id, self.definition_label))
        return (f"Using the {self.definition_label or self.metric_id} definition of "
                f"{self.concept.replace('_', ' ')}, which you selected"
                + (f". The competing definitions ({alts}) still exist and still disagree; "
                   f"this selection applies to how the answer is presented, not to which "
                   f"definition is authoritative for the business." if alts else "."))


def detect_rejection(text):
    t = (text or "").lower().strip()
    return any(p in t for p in _REJECTION_PHRASES)


def detect_correction(text):
    """A user correcting the system. Returns the corrected remainder, or None.
    A correction REPLACES context -- it is the one case where inherited state must be dropped,
    because the user is telling us the inherited state was wrong."""
    t = (text or "").strip()
    low = t.lower()
    for phrase in _CORRECTION_PHRASES:
        idx = low.find(phrase)
        if idx != -1:
            remainder = t[idx + len(phrase):].strip(" ,:-")
            return remainder or t
    return None


def detect_selection(text, options, option_metric_ids=()):
    """Did the user explicitly pick one of the options they were shown?

    Deliberately strict. It matches an ordinal ("the second one"), an explicit metric_id, or a
    distinctive phrase from exactly ONE option. If two options match, or none does, this returns
    None and the clarification stays open -- an ambiguous reply is not a decision.
    """
    if not text or not options:
        return None
    t = text.lower().strip()

    # An explicit metric_id is unambiguous.
    for i, mid in enumerate(option_metric_ids or ()):
        if mid and mid.lower() in t:
            return i

    m = re.search(r"\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|[1-5])\b", t)
    if m and ("option" in t or "the " in t or t.strip() == m.group(1)):
        idx = _ORDINALS.get(m.group(1))
        if idx is not None and idx < len(options):
            return idx

    # A label prefix, which is how competing definitions are actually named back to us. The
    # occupancy family is shown as "Def A (v_occupancy, ...)", "Def B (...)", so "Def A" is the
    # natural reply -- and it is short enough that the distinctive-token pass below skips it
    # (its words are under the 4-character minimum). Matched first, and only when it identifies
    # exactly one option.
    label_hits = [i for i, opt in enumerate(options)
                  if _label_key(opt) and _label_key(opt) == _label_key(t)]
    if len(label_hits) == 1:
        return label_hits[0]

    # A distinctive word from exactly one option.
    matches = []
    for i, opt in enumerate(options):
        tokens = [w for w in re.findall(r"[a-z][a-z_-]{3,}", opt.lower())
                  if w not in ("definition", "total", "amount", "value", "level", "metric",
                               "collected", "recorded", "tenants", "which", "the")]
        if any(tok in t for tok in tokens):
            matches.append(i)
    if len(matches) == 1:
        return matches[0]
    return None


_LABEL_PREFIX = re.compile(r"^\s*(?:the\s+)?(def(?:inition)?\s*[a-z0-9]+)\b", re.I)


def _label_key(text):
    """Normalise a 'Def A' / 'Definition A' / 'def a' style prefix to a comparable key, or ''."""
    m = _LABEL_PREFIX.match(text or "")
    if not m:
        return ""
    return re.sub(r"[^a-z0-9]", "", m.group(1).lower())


# --- Definition-selection detection for SHOW_BOTH families ---------------------------------------

# Phrases by which a user explicitly selects a definition. Each requires BOTH an explicit
# selection verb AND a definition reference -- "use the live occupancy definition" selects;
# "what is occupancy" does not, and neither does "the live one is higher".
_SELECT_VERBS = ("use ", "show me the ", "go with ", "i want the ", "give me the ",
                 "switch to ", "based on ", "using ", "apply the ", "pick the ", "choose the ")
_DEFINITION_WORDS = ("definition", "def ", "version", "basis", "convention", "measure")


def detect_selection_attempt(text, available_definitions):
    """Distinguish the three outcomes a selection turn can have, which a bare index cannot:

        (index, ())          -- the user selected exactly one definition
        (None, candidates)   -- the user TRIED to select, but their words fit more than one
        (None, ())           -- no selection was attempted at all

    The middle case is why this exists. "Use the live occupancy definition" contains a selection
    verb, but the word "live" appears in three of the five occupancy labels (Defs A and B are
    "Live+Live"; Def D is "bed.status=Live"). Returning a bare None there makes an attempted
    selection indistinguishable from silence, and the turn falls through to an ordinary
    SHOW_BOTH answer -- so the user's explicit instruction is neither honoured nor acknowledged.
    Surfacing the candidates lets the caller ask WHICH, which is the only safe response: picking
    one would be the silent narrowing this whole system exists to prevent.
    """
    if not text or not available_definitions:
        return None, ()
    t = (text or "").lower()
    if not any(v in t for v in _SELECT_VERBS):
        return None, ()

    idx = detect_definition_selection(text, available_definitions)
    if idx is not None:
        return idx, ()

    # A selection verb was present but resolved to zero or several labels. Report every label
    # the user's words could plausibly have meant, so the follow-up question is concrete.
    candidates = []
    for i, label in enumerate(available_definitions):
        # Strip the "Def A"/"Definition B" prefix before extracting distinctive words. Left in,
        # its "def" token is a substring of the user's own word "definition", so EVERY label
        # would match every selection turn and the candidate list would be meaningless.
        body = _LABEL_PREFIX.sub("", label).lower()
        words = {w for w in re.findall(r"[a-z]{4,}", body)
                 if w not in ("definition", "with", "only", "computed", "phase", "from",
                              "that", "this", "have", "been", "into")}
        if any(w in t for w in words):
            candidates.append(i)
    return None, tuple(candidates)


def detect_definition_selection(text, available_definitions):
    """Return the index of the definition the user explicitly selected, or None.

    `available_definitions` is the labelled set they were shown. This never fires on a bare
    restatement of the question: the turn must contain a selection verb AND either the word
    "definition" (or a synonym) or a distinctive token from exactly one label.
    """
    if not text or not available_definitions:
        return None
    t = (text or "").lower()

    if not any(v in t for v in _SELECT_VERBS):
        return None

    matches = []
    for i, label in enumerate(available_definitions):
        tokens = [w for w in re.findall(r"[a-z][a-z_]{3,}", label.lower())
                  if w not in ("definition", "tenant", "dues", "occupancy", "profit", "total",
                               "value", "only", "live", "from", "with", "the")]
        distinctive = [w for w in re.findall(r"[a-z][a-z_]{3,}", label.lower())
                       if w not in ("definition", "the", "and", "for", "with", "only")]
        if any(tok in t for tok in tokens) or any(d in t for d in distinctive):
            matches.append(i)

    if len(matches) == 1:
        return matches[0]

    # "use the live occupancy definition" -- a definition word plus one adjective that appears
    # in exactly one label.
    if any(w in t for w in _DEFINITION_WORDS):
        narrowed = []
        for i, label in enumerate(available_definitions):
            words = set(re.findall(r"[a-z]{4,}", label.lower()))
            if any(w in t for w in words - {"definition", "tenant", "dues", "total"}):
                narrowed.append(i)
        if len(narrowed) == 1:
            return narrowed[0]
    return None
