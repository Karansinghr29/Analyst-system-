"""
owner_semantics.py -- the one deterministic owner-facing meaning of a finding, a movement and a
measure. Every product surface reads it from here.

WHY THIS MODULE EXISTS
----------------------
The engine already decides the numbers, the definitions, the periods, the trust postures and the
data-quality findings. What it did NOT decide, until now, was the layer directly above those: what
KIND of thing a finding is, what an owner is being asked to DO about it, and whether it belongs
under "needs attention" at all. Each surface answered those questions for itself, close to its own
rendering code, and they disagreed:

  * Owner Home counted a validated revenue RISE among the twenty-six items "needing attention",
    because the insight feed had one bucket for anything that was not a definition conflict. A
    business that grew was reported as a business with more problems.

  * The Data Quality page derived an owner action from the TRUST POSTURE of the measures a
    finding touched, so every BLOCK finding was told to "decide which definition is official" --
    including four findings that are not definitional at all and have a correct answer.

  * The Power BI pages, the AI answers and the workspace each restated some of this in their own
    words, with nothing making them agree.

So the classification moves here, beside the gate rather than beside a renderer, and every surface
projects the SAME decision. That is the whole point: one deterministic business meaning, one owner
semantic projection, every surface using the same meaning.

WHAT THIS MODULE MAY AND MAY NOT DO
-----------------------------------
It may CLASSIFY and it may WORD. It computes no figure, reads no evidence file, and changes no
trust level, severity, conflict, definition or finding. Everything below is derived from fields the
deterministic layer already produced -- a finding's own recorded issue, root cause, root-cause
confidence, status, affected measures and fixability; an insight's own trigger and trust level; a
change's own validated direction. Severity is deliberately never consulted: how bad a finding is
and what an owner can do about it are different questions, and a HIGH finding here is a date format
while a LOW one is a corrupt date.

Where a classification cannot be established, the fallback is the honest one -- review the records
-- and never an invented remedy.
"""
import re

NOT_DETERMINABLE_TEXT = "Not determinable from exported evidence."


# --- What an owner is being asked to do ---------------------------------------------------------
#
# Six categories, and the split that matters most is the first one: whether an item belongs on the
# "needs attention" list at all. A movement is a fact about the business, not a task. Counting it
# as a task is how a good month came to read as twenty-six problems.

DECISION_REQUIRED = "DECISION_REQUIRED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
MONITOR = "MONITOR"
POSITIVE_MOVEMENT = "POSITIVE_MOVEMENT"
NEGATIVE_MOVEMENT = "NEGATIVE_MOVEMENT"
INFORMATIONAL = "INFORMATIONAL"

ALL_ACTION_CATEGORIES = (DECISION_REQUIRED, REVIEW_REQUIRED, MONITOR,
                         POSITIVE_MOVEMENT, NEGATIVE_MOVEMENT, INFORMATIONAL)

# `home_group` is the ONE routing table that decides which block of Owner Home an item lands in.
# Every surface reads it rather than deciding for itself, which is what keeps a movement off the
# work list and a monitor item out of the attention count. `needs_attention` and `is_movement`
# are the same decision as two convenience flags.
GROUP_ATTENTION = "attention"
GROUP_MOVEMENTS = "movements"
GROUP_MONITOR = "monitor"
GROUP_SUPPORTING = "supporting"

ACTION_CATEGORIES = {
    DECISION_REQUIRED: {
        "label": "Decision needed",
        "owner_meaning": "Only the business can settle this. The records hold more than one "
                         "defensible answer and the system will not choose between them.",
        "home_group": GROUP_ATTENTION,
        "needs_attention": True, "is_movement": False, "order": 0,
    },
    REVIEW_REQUIRED: {
        "label": "Review needed",
        "owner_meaning": "Something in the records needs a person to look at it before the "
                         "figures it affects are relied on.",
        "home_group": GROUP_ATTENTION,
        "needs_attention": True, "is_movement": False, "order": 1,
    },
    MONITOR: {
        "label": "Worth knowing",
        "owner_meaning": "Nothing to correct. It changes how the affected figures should be "
                         "read, so it is stated rather than hidden.",
        "home_group": GROUP_MONITOR,
        "needs_attention": False, "is_movement": False, "order": 2,
    },
    # POSITIVE and NEGATIVE describe DIRECTION and nothing else. The exported evidence fixes no
    # materiality threshold and no direction-of-goodness -- whether a rise in expenses is bad, or
    # a fall in collections merely seasonal, is a business reading. So "positive" here means the
    # figure rose and "negative" means it fell, and neither claims the movement is good, bad,
    # large or worth acting on.
    POSITIVE_MOVEMENT: {
        "label": "Moved up",
        "owner_meaning": "A figure rose between two complete periods. Direction only: your "
                         "records set no threshold for what counts as a significant move.",
        "home_group": GROUP_MOVEMENTS,
        "needs_attention": False, "is_movement": True, "order": 3,
    },
    NEGATIVE_MOVEMENT: {
        "label": "Moved down",
        "owner_meaning": "A figure fell between two complete periods. Direction only: your "
                         "records set no threshold for what counts as a significant move.",
        "home_group": GROUP_MOVEMENTS,
        "needs_attention": False, "is_movement": True, "order": 4,
    },
    INFORMATIONAL: {
        "label": "For information",
        "owner_meaning": "Recorded because the records show it. It asks nothing of you.",
        "home_group": GROUP_SUPPORTING,
        "needs_attention": False, "is_movement": False, "order": 5,
    },
}

# Which block of Owner Home each group is, in reading order. The blocks are named here rather
# than in the page so that adding a category cannot leave an item with nowhere to go.
HOME_GROUPS = (GROUP_ATTENTION, GROUP_MOVEMENTS, GROUP_MONITOR, GROUP_SUPPORTING)


def home_group(category):
    """Which Owner Home block an item belongs in. An unrecognised category is treated as
    supporting information rather than as work: inventing urgency is the worse failure."""
    return ACTION_CATEGORIES.get(category, {}).get("home_group", GROUP_SUPPORTING)


def needs_attention(category):
    return bool(ACTION_CATEGORIES.get(category, {}).get("needs_attention"))


def is_movement(category):
    return bool(ACTION_CATEGORIES.get(category, {}).get("is_movement"))


def category_order(category):
    return ACTION_CATEGORIES.get(category, {}).get("order", len(ALL_ACTION_CATEGORIES))


# --- The owner-facing projection of a trust posture ---------------------------------------------
#
# The canonical levels are unchanged and remain authoritative -- SAFE, DISCLOSE, SHOW_BOTH, BLOCK,
# NOT_DETERMINABLE are what the gate issues, what the DOM carries, and what every downstream check
# reads. This is the ONE short phrase an owner sees in their place, so that five surfaces cannot
# invent five different words for the same posture.
OWNER_TRUST_STATUS = {
    "SAFE": "Verified",
    "DISCLOSE": "Usable with limitation",
    "SHOW_BOTH": "Definitions differ",
    "BLOCK": "Decision blocked",
    "NOT_DETERMINABLE": "Cannot be determined",
}


def owner_trust_status(trust_level):
    """The owner's word for a posture. An unrecognised level is never guessed at -- it reads as
    undeterminable, which is what an unknown posture actually means."""
    return OWNER_TRUST_STATUS.get(trust_level, OWNER_TRUST_STATUS["NOT_DETERMINABLE"])


def definitions_line(count):
    """The posture line for a measure holding competing definitions, said for the number it holds.

    "Multiple definitions -- review both" was written when two was the only case, and occupancy
    holds five. Telling an owner to review "both" of five readings is wrong in a way they will
    notice, and it quietly suggests the other three do not count. The count is the tile's own, so
    this needs no rule about any particular measure.
    """
    if count == 2:
        return "Two definitions — review both"
    if count > 2:
        return f"{count} definitions — review the alternatives"
    return "Multiple definitions — review the alternatives"


# --- What kind of thing a data-quality finding IS -----------------------------------------------
#
# This is the concept that decides what an owner can do about a finding, and it is not the same
# question as how the measures it touches are gated. Nine kinds, each a claim the register's own
# fields either support or do not.

KIND_DEFINITION_CONFLICT = "definition_conflict"
KIND_PROVEN_DEFECT = "proven_defect"
KIND_CATEGORY_BREAKDOWN = "category_breakdown"
KIND_SOURCE_LEDGER_DIFFERENCE = "source_ledger_difference"
KIND_FORMAT_DEFECT = "format_defect"
KIND_MISSING_VALIDATION = "missing_validation"
KIND_SUSPECTED_ISSUE = "suspected_issue"
KIND_LIMITATION = "limitation"
KIND_PROVEN_ISSUE_UNRESOLVED = "proven_issue_unresolved"

ALL_DQ_KINDS = (KIND_DEFINITION_CONFLICT, KIND_PROVEN_DEFECT, KIND_CATEGORY_BREAKDOWN,
                KIND_SOURCE_LEDGER_DIFFERENCE, KIND_FORMAT_DEFECT, KIND_MISSING_VALIDATION,
                KIND_SUSPECTED_ISSUE, KIND_LIMITATION, KIND_PROVEN_ISSUE_UNRESOLVED)

# One kind, one owner action, one action category. The action is the sentence every surface says
# about a finding of that kind; the category is where that finding sits on Owner Home. Nothing
# here proposes a remedy the evidence does not support: where the records establish a problem but
# not its correction, the action asks for a review and names no fix.
DQ_KINDS = {
    KIND_DEFINITION_CONFLICT: {
        "category": DECISION_REQUIRED,
        "owner_action": ("Management needs to decide which definition should be used as the "
                         "official business measure. Until then, the competing figures should be "
                         "shown together."),
        "owner_lead": "{subject} is recorded under more than one definition, and they disagree.",
        "owner_lead_bare": "This is recorded under more than one definition, and they disagree.",
    },
    KIND_PROVEN_DEFECT: {
        "category": REVIEW_REQUIRED,
        "owner_action": ("The underlying data or calculation needs to be corrected before this "
                         "measure is treated as reliable."),
        "owner_lead": "A calculation behind {subject} is not producing what it is meant to "
                      "produce.",
        "owner_lead_bare": "A calculation behind this is not producing what it is meant to "
                           "produce.",
    },
    KIND_CATEGORY_BREAKDOWN: {
        "category": REVIEW_REQUIRED,
        # Said carefully: a breakdown that omits a category is wrong about the SPLIT, and saying
        # the total is wrong would claim a defect the evidence does not show.
        "owner_action": ("The category breakdown needs to be corrected so every affected amount "
                         "is represented in it. The totals themselves are not in question."),
        "owner_lead": "A breakdown of {subject} leaves part of the amount out of its categories.",
        "owner_lead_bare": "A breakdown leaves part of the amount out of its categories.",
    },
    KIND_SOURCE_LEDGER_DIFFERENCE: {
        "category": REVIEW_REQUIRED,
        "owner_action": ("The source and ledger records should be reconciled before this "
                         "difference is treated as resolved."),
        "owner_lead": "The original records and the ledger disagree about {subject}.",
        "owner_lead_bare": "The original records and the ledger disagree.",
    },
    KIND_FORMAT_DEFECT: {
        "category": REVIEW_REQUIRED,
        "owner_action": ("The affected data format should be corrected so the records can be "
                         "interpreted consistently."),
        "owner_lead": "Some values in {subject} are stored in a shape the other records cannot "
                      "read.",
        "owner_lead_bare": "Some values are stored in a shape the other records cannot read.",
    },
    KIND_MISSING_VALIDATION: {
        "category": REVIEW_REQUIRED,
        "owner_action": ("The missing validation should be added so this part of the data can be "
                         "checked reliably."),
        "owner_lead": "Part of {subject} has never been checked, so nothing is known either way.",
        "owner_lead_bare": "This has never been checked, so nothing is known either way.",
    },
    KIND_SUSPECTED_ISSUE: {
        "category": REVIEW_REQUIRED,
        "owner_action": ("Review the affected records to determine whether the suspected issue is "
                         "a real data problem or an expected business process."),
        "owner_lead": "A pattern in {subject} that may be a fault or may be ordinary business.",
        "owner_lead_bare": "A pattern that may be a fault or may be ordinary business.",
    },
    KIND_PROVEN_ISSUE_UNRESOLVED: {
        "category": REVIEW_REQUIRED,
        "owner_action": "Review the affected records to determine the appropriate correction.",
        "owner_lead": "Records in {subject} do not agree with each other.",
        "owner_lead_bare": "The affected records do not agree with each other.",
    },
    KIND_LIMITATION: {
        "category": MONITOR,
        "owner_action": ("No immediate action is indicated. Keep this limitation in mind when "
                         "interpreting the affected figures."),
        "owner_lead": "A limitation in how {subject} was recorded.",
        "owner_lead_bare": "A limitation in how these records were made.",
    },
}


def dq_action_kind(row):
    """What kind of thing this finding is, read off its own recorded fields.

    Reads `issue`, `root_cause`, `root_cause_confidence`, `status`, `metrics_affected` and
    `offline_fix_possible`. Does NOT read `severity`: how serious a finding is and what can be
    done about it are different questions, and conflating them is what produced the wrong advice
    this classification replaces.

    The tests run from the most specific claim to the least, and each looks for something the
    record ACTUALLY STATES -- a status of conflicting definitions, a root cause calling the
    behaviour expected, a column saying no fix applies because there is nothing to fix. A finding
    matching none of them falls to `proven_issue_unresolved`, which asks for a review and proposes
    no remedy: the honest answer when the evidence establishes a problem and not its correction.
    """
    issue = str(row.get("issue", "") or "").lower()
    cause = str(row.get("root_cause", "") or "").lower()
    status = str(row.get("status", "") or "").strip().lower()
    confidence = str(row.get("root_cause_confidence", "") or "").strip().lower()
    # The register's own column naming the measures a finding touches, which is where a finding
    # says in its own words that it touches none.
    measures = str(row.get("metrics_affected", "") or "").strip().lower()
    fixable = str(row.get("offline_fix_possible", "") or "").strip().upper()
    scope = " ".join((issue, cause, str(row.get("affected_rows", "") or "").lower()))

    # Competing definitions of one thing. Stated either in the status, or in the finding itself --
    # "competing ... definitions", "non-interchangeable ... definitions", or two calculation paths
    # that can disagree.
    if "conflicting definitions" in status:
        return KIND_DEFINITION_CONFLICT
    if "definition" in issue and ("competing" in issue or "non-interchangeable" in issue):
        return KIND_DEFINITION_CONFLICT
    if "paths" in issue and "disagree" in issue:
        return KIND_DEFINITION_CONFLICT

    # A check that does not exist. Its absence is stated in the finding, its cause, or in the row
    # count column, which says there is no row count because there is no check.
    if "no exported orphan" in scope or "coverage gap" in scope:
        return KIND_MISSING_VALIDATION

    # The record calls the behaviour expected. Tested before the defect rule, so a root cause that
    # says "not a defect" is never read as one.
    if "not a defect" in confidence or "not a defect" in cause:
        return KIND_LIMITATION

    if any(word in issue for word in ("format", "corrupt", "placeholder", "epoch date")):
        return KIND_FORMAT_DEFECT

    if "source amount vs ledger amount" in issue:
        return KIND_SOURCE_LEDGER_DIFFERENCE

    if "categor" in issue and ("exclude" in issue or "bucket" in issue):
        return KIND_CATEGORY_BREAKDOWN

    # Proven, and the finding names what is WRONG with it rather than only what was observed.
    if confidence.startswith("proven") and any(
            word in issue for word in ("defect", "omits", "wrong", "incorrect")):
        return KIND_PROVEN_DEFECT

    # Nothing to act on: the finding touches no measure, or the record states that no fix applies
    # either offline or live because the finding is a property of the records, not a fault in them.
    if measures.startswith("none") or fixable == "N/A":
        return KIND_LIMITATION

    # Records that contradict each other arithmetically. Established regardless of whether the
    # cause behind them is only suspected.
    if "inconsistency" in issue or "!=" in issue:
        return KIND_PROVEN_ISSUE_UNRESOLVED

    if (confidence.startswith("suspected") or confidence.startswith("unverified")
            or status == "unverified"):
        return KIND_SUSPECTED_ISSUE

    return KIND_PROVEN_ISSUE_UNRESOLVED


def dq_owner_action(kind):
    return DQ_KINDS[kind]["owner_action"]


def dq_action_category(kind):
    return DQ_KINDS[kind]["category"]


def dq_owner_lead(kind, subject=""):
    """The opening sentence for a finding whose own wording cannot be shown to an owner.

    Composed from the KIND and the subject -- the fields -- rather than by editing the recorded
    sentence, which this project has already learned produces worse English than the object name
    it removes. The recorded wording stays intact under the technical details.
    """
    spec = DQ_KINDS[kind]
    return spec["owner_lead"].format(subject=subject) if subject else spec["owner_lead_bare"]


# --- What an insight or a movement asks of an owner ----------------------------------------------

def insight_action_category(trigger, trust_level, dq_kind=""):
    """Where a standing finding belongs on Owner Home.

    The order matters, and it was wrong. Reading the TRUST POSTURE before the finding's kind sent
    every finding that merely TOUCHES a conflicted measure to the decision list -- a wrong account
    code behind collections, a date format in the electricity records, invoice rows that do not add
    up -- and told the owner to hold a definition vote about a defect with a correct answer. It is
    the same mistake the data-quality actions made before this layer existed, in a second place.

    So:
      1. An insight whose SUBJECT is the conflict says so in its trigger, and only that earns the
         decision list on the strength of being a conflict.
      2. Otherwise the finding's own kind decides, because the kind is what says whether anyone
         can act and how.
      3. The posture is consulted only when there is no finding to read -- there, a conflicted
         measure with nothing else known about it is genuinely a decision.

    Severity is not consulted anywhere.
    """
    if trigger == "definition_conflict":
        return DECISION_REQUIRED
    if dq_kind:
        return dq_action_category(dq_kind)
    if trust_level in ("SHOW_BOTH", "BLOCK"):
        return DECISION_REQUIRED
    if trigger in ("dq_severity", "risk_boundary"):
        return REVIEW_REQUIRED
    return INFORMATIONAL


# Which category asks more of an owner. Used when one item carries several findings: grouping may
# not soften what its strongest member asks for.
_CATEGORY_DEMAND = {
    DECISION_REQUIRED: 3, REVIEW_REQUIRED: 2, MONITOR: 1,
    POSITIVE_MOVEMENT: 0, NEGATIVE_MOVEMENT: 0, INFORMATIONAL: 0,
}


def most_demanding(categories):
    """The strongest ask among several. Empty in, empty out -- never a default of INFORMATIONAL,
    which would silently downgrade a group whose categories were not recognised."""
    present = [c for c in categories or () if c in _CATEGORY_DEMAND]
    if not present:
        return ""
    return max(present, key=lambda c: _CATEGORY_DEMAND[c])


def change_action_category(classification):
    """Where a validated period movement belongs.

    A movement is a fact about the business, never a task, so neither category counts toward
    "needs attention". See the note on POSITIVE_MOVEMENT above: these name the DIRECTION the
    figure moved and claim nothing about whether that is good or big enough to act on.
    """
    if classification == "INCREASE":
        return POSITIVE_MOVEMENT
    if classification == "DECREASE":
        return NEGATIVE_MOVEMENT
    return None


# --- Owner-safe wording tests --------------------------------------------------------------------
#
# Both are DAMAGE TESTS. They decide whether a sentence the records already wrote can be shown to
# an owner AS WRITTEN; they never edit one. A sentence that fails is replaced by a composed one and
# kept, whole and unedited, under the technical details -- where this vocabulary belongs and is the
# right vocabulary to use.

# A bare snake_case identifier -- `tenant_transactions`, `balance_due`. The product-wide sanitiser
# removes database views, functions and `table.column` pairs, and deliberately does not guess at
# every lowercase word with an underscore in it.
_BARE_IDENTIFIER = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")

# Words that belong to the machine rather than to the business. A sentence containing one is
# describing the system's own plumbing -- a table, a view, a diagnostic, a deletion convention --
# and an owner reading it learns nothing about their business from it.
_MACHINE_WORDS = re.compile(
    r"\b(?:schemas?|tables?|rows?|columns?|views?|functions?|triggers?|quer(?:y|ies)|sql|joins?"
    r"|indexe?s?|polymorphic|referential|orphans?|diagnostics?|soft-delete[d]?|hard-delete[d]?"
    r"|non-atomic|epoch|nulls?|grain|timestamps?|boolean|foreign key|primary key|dedup\w*"
    r"|backfill\w*|in_scope|leaf)\b"
    # "bucket" is matched anywhere in a word: the register writes "buckets", "unbucketed" and
    # "bucketed" of the same internal thing, and all three are equally unreadable.
    r"|bucket"
    # A chart-of-accounts code, which identifies a ledger account to the system and nothing at all
    # to an owner: "account 5150".
    r"|\baccount\s+\d+\b"
    # The gate's own vocabulary and the record identifiers behind a finding. The registry's
    # caveat column is written for the people who maintain the semantic layer and opens with the
    # posture in its machine form -- "SHOW_BOTH: present every definition with its label ... See
    # conflicts.md C.001;C.002". Every one of those is right for the audit trail and unreadable
    # as an owner-facing limitation, and `owner_status` already says the posture in the owner's
    # words.
    r"|\b(?:SAFE|DISCLOSE|SHOW_BOTH|BLOCK|NOT_DETERMINABLE)\b"
    r"|\b[A-Za-z0-9_.-]+\.md\b"
    r"|\b(?:C|DQ|H|F|T|M|INS)\.\d+[A-Za-z0-9.]*\b"
    # A metric identifier: "M.AR.001A", "M.PROFIT.001". The record-id rule above expects digits
    # straight after the prefix, so every metric id slipped past it -- which is how one measure's
    # registry description came to name another measure by its identifier in an owner-safe field.
    r"|\bM\.[A-Z]+\.\d+[A-Za-z]?\b",
    re.IGNORECASE)


def names_an_object(text):
    return bool(_BARE_IDENTIFIER.search(str(text or "")))


def speaks_machine(text):
    return bool(_MACHINE_WORDS.search(str(text or "")))


def owner_safe(text):
    """Can this sentence be shown to an owner exactly as the records wrote it?"""
    return not names_an_object(text) and not speaks_machine(text)
