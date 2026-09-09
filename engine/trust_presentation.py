"""
trust_presentation.py -- Phase 8. The owner-facing translation of the trust vocabulary.

Phase 8 brief 14: "do not overwhelm normal users with technical terminology. For Owner UX,
translate them into business-friendly language while preserving machine-readable trust state."

Both halves matter. The owner sees "No single reliable figure — definitions conflict"; the DOM
still carries `data-trust="BLOCK"`. Translation is a presentation concern that never replaces the
machine state, because every downstream check -- the validator, the tests, the render directives
-- reads the machine state, not the label.

Nothing here decides trust. It only renders a verdict `engine/gate.py` already issued.
"""
from dataclasses import dataclass

NOT_DETERMINABLE_TEXT = "Not determinable from exported evidence."

# Severity ordering for visual prominence. Higher = more prominent, because a conflict the owner
# cannot see is a conflict that does not exist for them.
PROMINENCE = {"SAFE": 0, "DISCLOSE": 1, "NOT_DETERMINABLE": 2, "SHOW_BOTH": 3, "BLOCK": 4}


@dataclass(frozen=True)
class TrustPresentation:
    trust_level: str          # the machine state, unchanged and authoritative
    owner_label: str          # the long form, one clause, used where a chip is too terse
    owner_explanation: str    # one sentence, business language
    tone: str                 # neutral | caution | conflict | unavailable
    icon: str
    headline_permitted: bool
    prominence: int

    @property
    def owner_status(self):
        """The ONE short phrase an owner sees in place of the posture.

        Held in `engine/owner_semantics.py` rather than here so that a single table serves every
        surface -- a tile chip, a finding card, an AI answer, a decision-support section. The
        canonical `trust_level` beside it is unchanged and stays authoritative; this never
        replaces it, and nothing downstream decides anything from this string.
        """
        from engine import owner_semantics as osem
        return osem.owner_trust_status(self.trust_level)

    @property
    def badge(self):
        """Compatibility only. Returns `owner_status`.

        `badge` was a second, separately-worded short label -- "Caveat applies", "Conflict",
        "Unavailable" against the canonical "Usable with limitation", "Decision blocked", "Cannot
        be determined". Two short labels for one posture is two answers to one question, and which
        of them an owner saw depended on which surface they were looking at.

        The stored strings are gone; the field name stays because `scripts/build_phase8_registries`
        writes a `badge` column into `ui_metric_registry.csv` and the frontend reads it as a
        fallback for an older payload. It is now an alias, not an authority.
        """
        return self.owner_status

    def as_dict(self):
        return {
            "trust_level": self.trust_level, "owner_label": self.owner_label,
            "owner_explanation": self.owner_explanation, "badge": self.badge,
            "owner_status": self.owner_status,
            "tone": self.tone, "icon": self.icon,
            "headline_permitted": self.headline_permitted, "prominence": self.prominence,
        }


_PRESENTATIONS = {
    "SAFE": TrustPresentation(
        trust_level="SAFE",
        owner_label="Reliable",
        owner_explanation="This figure has one agreed definition and was checked against the "
                          "source records.",
        tone="neutral", icon="check",
        headline_permitted=True, prominence=PROMINENCE["SAFE"]),

    "DISCLOSE": TrustPresentation(
        trust_level="DISCLOSE",
        owner_label="Usable, with a caveat",
        owner_explanation="This figure is usable, but a known limitation affects it. The "
                          "limitation is shown with the number, not hidden behind it.",
        tone="caution", icon="info",
        headline_permitted=True, prominence=PROMINENCE["DISCLOSE"]),

    "SHOW_BOTH": TrustPresentation(
        trust_level="SHOW_BOTH",
        owner_label="Multiple definitions — review both",
        owner_explanation="More than one evidence-backed definition of this measure exists, and "
                          "they give different answers. All of them are shown; choosing between "
                          "them is a business decision.",
        tone="conflict", icon="split",
        headline_permitted=False, prominence=PROMINENCE["SHOW_BOTH"]),

    "BLOCK": TrustPresentation(
        trust_level="BLOCK",
        owner_label="No single reliable figure — definitions conflict",
        owner_explanation="The available definitions of this measure disagree materially, so "
                          "stating one number would be misleading. Each definition and its value "
                          "are shown, along with the decision needed to settle it.",
        tone="conflict", icon="alert",
        headline_permitted=False, prominence=PROMINENCE["BLOCK"]),

    "NOT_DETERMINABLE": TrustPresentation(
        trust_level="NOT_DETERMINABLE",
        owner_label="Cannot be determined from the available evidence",
        owner_explanation=NOT_DETERMINABLE_TEXT + " The exported records do not contain what "
                          "this measure would need. No estimate is shown in its place.",
        tone="unavailable", icon="minus",
        headline_permitted=False, prominence=PROMINENCE["NOT_DETERMINABLE"]),
}


def present(trust_level):
    """The owner-facing presentation of a trust verdict. Unknown levels are not guessed at."""
    p = _PRESENTATIONS.get(trust_level)
    if p is None:
        return TrustPresentation(
            trust_level=trust_level or "UNKNOWN",
            owner_label="Cannot be determined from the available evidence",
            owner_explanation=NOT_DETERMINABLE_TEXT,
            tone="unavailable", icon="minus",
            headline_permitted=False, prominence=PROMINENCE["NOT_DETERMINABLE"])
    return p


def all_presentations():
    return tuple(_PRESENTATIONS.values())


# --- Insight categories (Phase 8 brief 2) -------------------------------------------------------
# The owner-facing grouping of the insight feed. Each maps to conditions the insight engine
# ALREADY produces -- no category is invented, and one of them is deliberately hard to earn.

CAT_CRITICAL = "critical"
CAT_ATTENTION = "attention"
CAT_POSITIVE = "positive"
CAT_OPPORTUNITY = "opportunity"
CAT_DATA_QUALITY = "data_quality"
CAT_DEFINITION_CONFLICT = "definition_conflict"

INSIGHT_CATEGORIES = {
    CAT_CRITICAL: {"icon": "red", "label": "Critical",
                   "rule": "A CRITICAL-severity finding from data_quality_registry.csv."},
    CAT_ATTENTION: {"icon": "orange", "label": "Attention Required",
                    "rule": "A HIGH-severity finding, or a documented risk boundary crossed."},
    CAT_POSITIVE: {"icon": "green", "label": "Positive",
                   "rule": "A validated favourable change over complete periods. Direction only "
                           "-- materiality is undefined, so no change is called 'good enough'."},
    CAT_OPPORTUNITY: {"icon": "bulb", "label": "Opportunity",
                      "rule": "Only where the evidence supports one. No opportunity is inferred "
                              "from a metric merely existing, so this category is usually "
                              "empty -- which is the honest state, not a rendering bug."},
    CAT_DATA_QUALITY: {"icon": "warning", "label": "Data Quality",
                       "rule": "A reliability problem affecting how a figure should be read."},
    CAT_DEFINITION_CONFLICT: {"icon": "split", "label": "Definition Conflict",
                              "rule": "Competing evidence-backed definitions that materially "
                                      "change interpretation."},
}


def categorise_insight(insight, dq_severity=""):
    """Map an engine insight onto an owner-facing category.

    Derived from what the insight already carries -- its trigger, its trust level, and the DQ
    severity recorded in the register. Nothing here re-judges importance.
    """
    sev = (dq_severity or "").upper()

    # A finding whose SUBJECT is the conflict itself belongs under Definition Conflict.
    if insight.trigger == "definition_conflict":
        return CAT_DEFINITION_CONFLICT

    # Severity is checked BEFORE trust level. A CRITICAL data-quality finding that happens to
    # touch a conflicted metric is still a critical issue -- categorising it by trust level
    # first buried every CRITICAL finding under "Definition Conflict", where an owner scanning
    # for urgent problems would not look for it.
    if sev == "CRITICAL":
        return CAT_CRITICAL
    if sev == "HIGH":
        return CAT_ATTENTION

    if insight.trust_level in ("SHOW_BOTH", "BLOCK"):
        return CAT_DEFINITION_CONFLICT
    if insight.trigger == "dq_severity":
        return CAT_DATA_QUALITY
    if insight.trigger == "risk_boundary":
        return CAT_ATTENTION
    return CAT_ATTENTION


def categorise_change(change):
    """A validated period change, categorised for the owner feed.

    Only DIRECTION is used. No change is called large, small, good or bad, because materiality
    is undefined -- `insight_generation_spec.md` 2 condition 3 leaves the threshold to a business
    decision and none exists in the evidence. A rising figure is reported as rising; whether that
    is good is the owner's judgement.
    """
    if not getattr(change, "detected", False):
        return None
    if change.classification == "INCREASE":
        # An increase is favourable for inflow measures and unfavourable for outflow ones. That
        # direction-of-goodness is a business reading, so the category stays neutral-positive
        # ("a validated change occurred") rather than asserting benefit.
        return CAT_POSITIVE
    if change.classification == "DECREASE":
        return CAT_ATTENTION
    return None
