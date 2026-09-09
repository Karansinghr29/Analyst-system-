"""
owner_presentation.py -- owner-facing wording only.

Every number, trust posture, competing definition, caveat, and recommendation here is copied
from an object the deterministic engine already produced. This module does not calculate, pick
a SHOW_BOTH winner, change a trust level, or invent materiality, causes, or benchmarks.

The contract-complete skeleton remains on RenderedAnswer.skeleton / the evidence chain. The
string this module returns is what the owner chat UI may show.
"""
import re

from engine.result import NOT_DETERMINABLE_TEXT
from engine import trust_presentation as tp
from engine.change_detection import INCREASE, DECREASE, NO_CHANGE, UNAVAILABLE

# -- identifiers that belong in the engine/debug layer, never in owner prose --------------------

_METRIC_ID = re.compile(r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b")
_DQ_ID = re.compile(r"\bDQ\.\d{3}\b")
_CONFLICT_ID = re.compile(r"\bC\.\d{3}\b")
_INSIGHT_ID = re.compile(r"\bINS\.[A-Z0-9._-]+\b")
_FINDING_ID = re.compile(r"\bH\.\d{3}\b")
_SPEC_FILE = re.compile(r"\b[\w.-]+\.(?:md|csv|py|json)\b", re.I)
# Database view/function names. `v_outstanding_receivables` and `get_universal_metrics`
# are implementation objects, as internal as a metric ID, and were reaching owner prose
# through definition labels.
_DB_OBJECT = re.compile(r"\b(?:v_[a-z0-9_]+|vw_[a-z0-9_]+|get_[a-z0-9_]+)\b", re.I)
# Removing an identifier can leave a dangling possessive: "M.PNL.001's monthly values"
# became "'s monthly values".
_ORPHAN_POSSESSIVE = re.compile(r"(?:(?<=^)|(?<=[\s(]))['\u2019]s\b")
_DICT_DUMP = re.compile(r"\{[^{}]{0,500}\}")
_TRUST_PREFIX = re.compile(
    r"^\s*(SAFE|DISCLOSE|SHOW_BOTH|BLOCK|NOT_DETERMINABLE)\s*:\s*", re.I)
# The same posture written as a CLAUSE inside an engine sentence rather than as a prefix:
# "This metric's trust level is NOT_DETERMINABLE: no reference exists...". The prefix rule above
# only anchors at the start, so this form survived it and put a trust token in front of an owner.
# The badge beside the text already states the posture in the owner's words, so the clause goes
# and the reason after it stays.
_TRUST_CLAUSE = re.compile(
    r"\bThis metric's trust level is (?:SAFE|DISCLOSE|SHOW_BOTH|BLOCK|NOT_DETERMINABLE)\s*:\s*",
    re.I)
_SEE_LEFTOVER = re.compile(r"\bSee\s*[.,;]+\s*", re.I)

# Provenance clauses. Each names a specification, a section, or a conflict record, and each
# is removed whole so the sentence around it stays grammatical.
_CITATION_CLAUSES = (
    # "(insight_generation_spec.md 2 condition 1)" and the bare "(2 condition 1)" left
    # behind once the filename has gone.
    re.compile(r"\s*\((?:see\s+)?[^()]*?\bcondition\s+\d+[^()]*\)", re.I),
    re.compile(r"\s*\([^()]*?\b(?:section|clause|rule)\s+[\d.]+[^()]*\)", re.I),
    # "because <spec> classifies it CRITICAL" -> "because it is classified CRITICAL"
    # The bare section reference left once the filename has gone: "because 2 condition 1
    # classifies it CRITICAL".
    re.compile(r"\s*\b[\d.]+\s+condition\s+\d+\b", re.I),
    re.compile(r"\bbecause\s+classifies\s+it\b", re.I),
    # "See <ref> for the full comparison." once <ref> has gone.
    re.compile(r"\b(?:see|per|refer to)\s+for\s+[^.;]*[.;]", re.I),
    # A dangling reference left by a removed identifier: "the conflict behind before ..."
    re.compile(r"\bbehind\s+(?=before\b)", re.I),
    re.compile(r"\bof\s+(?=is\s+authoritative)", re.I),
)

# Table/column references such as "tenant_allotments.balance_due". A column name is as
# internal as a view name; both describe how a figure is stored, never what it means.
_TABLE_COLUMN = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\.[a-z][a-z0-9_]*\b")

# Build-phase language. "NOT COMPUTED IN PHASE 1" is a note to the implementers.
_PHASE_NOTE = re.compile(r"\bNOT COMPUTED IN PHASE\s*\d+\s*:?\s*", re.I)

# A bare figure of five digits or more, written without grouping. Grouping changes how a
# number is READ, never what it is; four digits and fewer are left alone so a year stays
# a year.
_UNGROUPED = re.compile(r"(?<![\d,.\u20b9])(\d{5,})(\.\d+)?(?![\d,])")

_CHANGE_WORDS = {
    INCREASE: "increased",
    DECREASE: "decreased",
    NO_CHANGE: "did not change",
    UNAVAILABLE: "could not be compared",
}

MATERIALITY_OWNER = (
    "Whether a period change is large enough to matter is not determinable from exported "
    "evidence: no significance threshold exists in the records. The direction and size are "
    "shown; judging importance is a business decision. " + NOT_DETERMINABLE_TEXT
)

ABSENT_CONCEPT_OWNER = (
    "Nothing in the available records corresponds to this question, and no substitute "
    "measure is invented in its place."
)


def owner_not_determinable_reason(reason):
    raw = reason or ""
    low = raw.lower()
    # Capability-aware gaps are already owner prose — keep them, don't map to "absent concept".
    if ("valid analytical request" in low or "not implemented" in low
            or "forecasting is" in low
            or ("scenario" in low and "what-if" in low)
            or "partially supported" in low):
        return sanitize_owner_text(raw)
    if ("no semantic metric" in low or "none of them covers the concept" in low
            or "does not improvise" in low or "structurally absent" in low):
        return ABSENT_CONCEPT_OWNER
    cleaned = sanitize_owner_text(raw)
    return cleaned


def _citation_replacement(pattern):
    """Most citation clauses vanish; two leave a word behind so the sentence still reads."""
    source = pattern.pattern
    if "classifies" in source:
        return "because it is classified"
    if "behind" in source:
        return "behind it "
    if "authoritative" in source:
        return "of this measure "
    return ""


def _group_digits(match):
    """Add thousands separators to a bare figure. The quantity is untouched."""
    whole, frac = match.group(1), match.group(2) or ""
    try:
        return f"{int(whole):,}{frac}"
    except ValueError:
        return match.group(0)


def sanitize_owner_text(text):
    """Strip internal IDs, spec filenames, and dict dumps. Does not add claims."""
    t = text or ""
    t = _METRIC_ID.sub("", t)
    t = _DQ_ID.sub("", t)
    t = _CONFLICT_ID.sub("", t)
    t = _INSIGHT_ID.sub("", t)
    t = _FINDING_ID.sub("", t)
    t = re.sub(r"\bFN\.\d{3}\b", "", t)
    t = _SPEC_FILE.sub("", t)
    t = _DB_OBJECT.sub("", t)
    t = _TABLE_COLUMN.sub("", t)
    t = _PHASE_NOTE.sub("", t)
    t = _DICT_DUMP.sub("", t)
    t = _ORPHAN_POSSESSIVE.sub("", t)
    for pattern in _CITATION_CLAUSES:
        t = pattern.sub(_citation_replacement(pattern), t)
    t = _UNGROUPED.sub(_group_digits, t)
    t = _TRUST_PREFIX.sub("", t)
    t = _TRUST_CLAUSE.sub("", t)
    t = _SEE_LEFTOVER.sub("", t)
    t = re.sub(r"\b(?:engine|api|frontend|tests)(?:\.\w+)+\b", "", t)
    t = re.sub(r"\(\s*[,;]*\s*\)", "", t)
    t = re.sub(r"\[\s*]", "", t)
    # "Def A (, Staying only)" -> "Def A (Staying only)". Cosmetic only: identifier
    # removal leaves the punctuation that used to surround it, and nothing is added.
    t = re.sub(r"\(\s*[,;]\s*", "(", t)
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s*[,;]\s*\)", ")", t)
    t = re.sub(r"\s+\)", ")", t)
    # A sentence left starting with the punctuation that followed a stripped subject.
    t = re.sub(r"(?m)^[ \t]*[,;:]+[ \t]*", "", t)
    # A line reduced to nothing but a bare separator.
    t = re.sub(r"(?m)^[ \t]*[:\u2013-]+[ \t]*$", "", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    # A colon whose list was the identifiers just removed. "...as one figure: M.AR.001A,
    # M.PROFIT.001." became "...as one figure:,." -- punctuation introducing nothing.
    t = re.sub(r":[\s,;]*(?=[.!?]|$)", "", t)
    t = re.sub(r"[,;]\s*[,;]+", ",", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def format_owner_value(value, unit=""):
    """Display an engine value without Python dict/list reprs.

    Grouping separators and the rupee sign only -- the same treatment
    `view_models.format_value` gives a dashboard tile, so the chat and the dashboard show one
    figure in one shape. No rounding beyond the two decimals the engine already carries, and no
    arithmetic: 72705593.43 becomes 72,705,593.43, never a different quantity.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, dict):
        return "; ".join(
            f"{str(k).replace('_', ' ')}: {format_owner_value(v, unit)}"
            for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return "; ".join(format_owner_value(v, unit) for v in value)
    if isinstance(value, (int, float)):
        u = (unit or "").upper()
        if "INR" in u or "RS" in u or "\u20b9" in (unit or ""):
            return f"\u20b9{value:,.2f}"
        if isinstance(value, float) and not float(value).is_integer():
            return f"{value:,.2f}"
        return f"{value:,.0f}"
    return str(value)


def owner_family_name(name):
    """The family's own name, without one member's definition suffix.

    Some family members are registered with the family name and their own definition in one
    string ("Tenant dues -- Def A: ..."). Used as a heading above the list of definitions, that
    repeats the first definition twice and reads as a stutter. Splitting is presentation only:
    no definition is dropped, and the full list still follows.
    """
    text = (name or "").strip()
    for sep in (" -- Def ", " -- def ", " \u2014 Def "):
        if sep in text:
            text = text.split(sep)[0].strip()
            break
    # "(3 definitions)" / "(5+ definitions)" is a note about the conflict, and the sentence
    # around the name states the count already.
    text = re.sub(r"\s*\(\d+\+?\s*definitions?\)", "", text, flags=re.I)
    return text.strip()


#
# Definition labels written in implementation vocabulary.
#
# Each names a real, distinct definition, so none may ever be dropped or merged -- but
# "V1, bed.status=Live" tells an owner nothing about how it differs from the one above it. What
# distinguishes these definitions is a business distinction, and that is what each replacement
# states. Order matters: the specific rules come first, because the generic ones below would
# collapse three genuinely different definitions into one repeated label.
#
_IMPLEMENTATION_LABELS = (
    (re.compile(r"not computed in phase\s*\d*", re.I),
     "Not currently available from the exported evidence"),
    (re.compile(r"v1.*bed\.status\s*=\s*live", re.I), "Active-bed definition"),
    (re.compile(r"bed\.status\s*=\s*live", re.I), "Active-bed definition"),
    # Owner rent and profit are each defined three ways, and what separates them is how owner
    # rent is treated.
    (re.compile(r"get_universal_metrics[^)]*excluded", re.I),
     "Application definition, owner rent left out"),
    (re.compile(r"get_universal_metrics[^)]*inclusive", re.I),
     "Application definition, owner rent counted"),
    (re.compile(r"get_universal_metrics[^)]*substituted", re.I),
     "Application definition, owner rent substituted"),
    (re.compile(r"ledger raw[^)]*bucket", re.I), "Ledger definition, from the owner-rent account"),
    (re.compile(r"get_universal_metrics(?:\s*v?\d)?", re.I), "Application definition"),
    (re.compile(r"tenant_transactions", re.I), "Legacy ledger definition"),
    (re.compile(r"\bledger\b", re.I), "Ledger definition"),
    (re.compile(r"^(?:def\s+[a-z0-9]+\s*[(:]\s*)?v1(?![a-z0-9])", re.I), "Application definition"),
    # Occupancy's definitions differ over who counts as resident and which beds count.
    (re.compile(r"staying\s*\+\s*on-?notice.*all beds", re.I),
     "Residents and those on notice, all beds"),
    (re.compile(r"staying\s*\+\s*on-?notice", re.I), "Residents and those on notice, active beds"),
    (re.compile(r"staying only", re.I), "Residents only, active beds"),
    (re.compile(r"day-?weighted", re.I), "Day-weighted over time"),
)


def owner_definition_labels(labels):
    """Every competing definition of one measure, labelled for the owner and kept DISTINCT.

    Uniqueness is enforced afterwards and is not optional: two definitions that read alike would
    collapse a disclosed conflict into an apparent duplicate, which is the one outcome SHOW_BOTH
    exists to prevent. Where a replacement would collide, that definition keeps its own longer
    wording instead.
    """
    projected, seen = [], set()
    for index, label in enumerate(labels or ()):
        text = owner_definition_label(label)
        if not text or text.lower() in seen:
            # A label that shortened to nothing, or to something already used, is numbered
            # instead. Numbering keeps it distinct without asserting a distinction the
            # shortened wording no longer carries.
            text = f"Definition {index + 1}"
        seen.add(text.lower())
        projected.append(text)
    return tuple(projected)


def owner_definition_label(label):
    """One competing definition, labelled for the owner.

    Drops the family prefix a member label repeats ("Tenant dues -- Def A: X" -> "Def A: X"),
    removes internal database object names, and restates an implementation label as the business
    distinction it actually draws. Every definition keeps a distinct label, which is what
    SHOW_BOTH requires -- shortening must never make two of them read alike.
    """
    original = str(label or "")
    for pattern, replacement in _IMPLEMENTATION_LABELS:
        if pattern.search(original):
            return replacement

    text = sanitize_owner_text(original).strip()
    for sep in (" -- ", " \u2014 "):
        if sep in text:
            head, tail = text.split(sep, 1)
            tail = tail.strip().lstrip(":").strip()
            if tail:
                text = tail
            break
    # "Def A" is a registry label, not something an owner can act on. What distinguishes the
    # definitions is the description beside it, so that description becomes the label and the
    # enumerator is dropped. Uniqueness is enforced by `owner_definition_labels`, which is what
    # keeps two definitions from reading alike after this shortening.
    text = re.sub(r"^\s*Def\s+[A-Za-z0-9]+\s*[:.]?\s*", "", text, flags=re.I)
    text = re.sub(r":\s*\(", " (", text)
    text = re.sub(r"^\(\s*", "", text)
    text = re.sub(r"\s*\)$", "", text)
    text = text.strip()
    return text[:1].upper() + text[1:] if text else ""


def format_owner_quantity(value, unit="", magnitude=False):
    """The complete owner-facing quantity, unit included.

    Currency renders as the rupee sign rather than a trailing "INR", so the owner reads
    a money figure the way money is written. A non-currency unit is appended as a word.
    `magnitude=True` drops a leading minus, for use beside an explicit direction word.
    """
    render = format_owner_magnitude if magnitude else format_owner_value
    text = render(value, unit)
    if not text:
        return ""
    u = (unit or "").strip()
    if not u:
        return text
    if text.startswith("₹") or "INR" in u.upper() or u.upper() in ("RS", "RS."):
        return text
    return f"{text} {u}"


def format_owner_magnitude(value, unit=""):
    """A change magnitude, with the sign carried by the direction word rather than the number.

    "decreased by -221,734.74" is a double negative that reads as an increase. The engine's own
    classification already states the direction, so the magnitude is rendered unsigned. The
    quantity is unchanged -- only a leading minus is dropped from the rendering.
    """
    text = format_owner_value(value, unit)
    if text.startswith("-"):
        return text[1:]
    if text.startswith("\u20b9-"):
        return "\u20b9" + text[2:]
    return text


_DIRECTIVE_MARKERS = (
    "present every definition",
    "present all definitions",
    "never silently pick",
    "do not state a single",
    "do not state one",
    "must not state",
    "do not pick",
    "never pick a winner",
    "blocked: do not",
    "ai_handling",
    "for the full comparison",
)


def _is_directive(sentence):
    """True when a sentence instructs the system rather than informing the owner."""
    low = sentence.lower()
    return any(marker in low for marker in _DIRECTIVE_MARKERS)


def _drop_directives(text):
    kept = []
    for sentence in re.split(r"(?<=[.;])\s+", text or ""):
        if sentence.strip() and not _is_directive(sentence):
            kept.append(sentence.strip())
    return " ".join(kept)


def owner_caveat(caveat):
    if not (caveat or "").strip():
        return ""
    return sanitize_owner_text(_drop_directives(caveat))


def owner_limitations(limitations):
    """Translate engine limitation strings; never drop the underlying constraint."""
    out = []
    for raw in limitations or ():
        text = raw or ""
        low = text.lower()
        if "materiality is undefined" in low or "materiality is not determinable" in low:
            out.append(MATERIALITY_OWNER)
        elif "anomaly" in low and "material" in low:
            out.append(
                "Two documented insight types — unusual spikes, and changes large enough to "
                "matter — cannot fire, because no threshold for either exists in the records. "
                "They are reported as unavailable rather than silently skipped. "
                + NOT_DETERMINABLE_TEXT)
        elif "competing definitions" in low:
            out.append(
                "Some measures cannot be stated as one figure because competing definitions "
                "exist. Each definition is shown separately; choosing between them is a "
                "business decision.")
        else:
            cleaned = sanitize_owner_text(text)
            if cleaned:
                out.append(cleaned)
    # Preserve order, drop exact duplicates after translation.
    seen = set()
    unique = []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return tuple(unique)


def _trust_line(trust_level):
    p = tp.present(trust_level)
    return p.owner_label, p.owner_explanation


def _section(title, body_lines):
    """One owner-facing section.

    Identical lines are collapsed. Removing an identifier can make several distinct engine
    findings render as the same sentence, and eleven copies of one recommendation buries
    the ones that actually differ. Only EXACT duplicates go: nothing that says something
    new is dropped.
    """
    body, seen = [], set()
    for ln in body_lines:
        if ln is None:
            continue
        text = str(ln).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        body.append(ln)
    if not body:
        return []
    return [title, *body, ""]


# --------------------------------------------------------------------------------------------
# Metric answers (Phase 4 render path)
# --------------------------------------------------------------------------------------------

def _definition_lines(answers, note_attr):
    """Every competing definition, once each.

    A metric family is executed as several member metrics, and each member's answer carries
    the WHOLE family's definitions. Rendering them per answer printed the same four
    definitions four times over -- a wall of repetition that also made the answer too long for
    the wording layer to restate.

    Deduplication is by label AND value, so two genuinely different figures are never merged;
    only an exact repeat is dropped. Nothing is chosen between, and nothing is omitted.
    """
    lines, seen, notes = [], set(), []
    for ans in answers:
        for r in ans.results:
            entry = (f"• {owner_definition_label(r.definition_label)}: "
                     f"{format_owner_quantity(r.value, r.unit)}")
            if entry not in seen:
                seen.add(entry)
                lines.append(entry)
        note = owner_caveat(getattr(ans, note_attr, "") or "")
        if note and note not in notes:
            notes.append(note)
    return lines + notes


def _extract_month_from_series(value, plan):
    """Return (is_series, amount_or_none).

    is_series False → caller should use the raw value as a non-series figure.
    is_series True → amount is the month match, or None if that month is absent.

    Composite month values (P&L rows with revenue/expenses/net_profit) are reduced to the
    component implied by the resolved concept, so a period-scoped expense question is not
    answered with a whole P&L object.
    """
    if not isinstance(value, dict) or plan is None or plan.time is None:
        return False, value
    start = getattr(plan.time, "start", None) or ""
    if not start:
        return False, value
    month_key = start[:7]
    component = _series_component_for_plan(plan)
    for key, amount in value.items():
        if str(key).startswith(month_key):
            if isinstance(amount, dict) and component:
                if component in amount:
                    return True, amount[component]
                return True, None
            return True, amount
    return True, None


def _series_component_for_plan(plan):
    """Which field of a composite monthly row answers the owner's concept."""
    concept = ""
    if plan is not None and plan.metric is not None:
        concept = (plan.metric.concept or "").lower()
    return {
        "expenses": "expenses",
        "revenue": "revenue",
        "profit": "net_profit",
        "pnl": "net_profit",
        "p_and_l": "net_profit",
    }.get(concept, "")


def _owner_figure_from_answer(ans, plan):
    """Pick the owner-facing quantity for one answer, honouring a requested month when present.

    Contract: a resolved non-all-time period must never be answered with an all-time scalar
    merely because the executed metric had no series shape. That substitution is refused.
    """
    from engine import time_resolution as timeres
    unit = ans.results[0].unit if ans.results else ""
    raw = ans.headline
    if raw is None and ans.results:
        raw = ans.results[0].value
    is_series, picked = _extract_month_from_series(raw, plan)
    if is_series and picked is None:
        label = getattr(plan.time, "period_label", "") or "that period"
        return None, unit, label
    if is_series:
        return picked, unit.replace("/month", "").strip() or unit, None
    # Non-series value + explicit single-month period = silent all-time substitution risk.
    if (plan is not None and plan.time is not None
            and timeres.is_single_month_period(plan.time)):
        label = getattr(plan.time, "period_label", "") or "that period"
        return None, unit, label
    return raw, unit, None


def present_metric_answer(plan, answers, reasoning=None):
    """Owner prose for one executed (or not-determinable) metric question."""
    if plan is not None and plan.status == "NOT_DETERMINABLE":
        forecast_note = sanitize_owner_text(getattr(plan, "forecast_note", "") or "")
        if forecast_note:
            return forecast_note
        extra = owner_not_determinable_reason(plan.not_determinable_reason)
        low = (extra or "").lower()
        if extra and (
                "forecast" in low or "not currently available" in low
                or "valid analytical request" in low or "can't reliably" in low
                or "cannot invent" in low or "month-scoped" in low
                or "don't have a month-scoped" in low):
            return sanitize_owner_text(extra)
        lines = [NOT_DETERMINABLE_TEXT]
        if extra and extra != NOT_DETERMINABLE_TEXT:
            lines.append("")
            lines.append(extra)
        return sanitize_owner_text("\n".join(lines))

    answers = tuple(answers or ())
    if answers and all(a.trust_level == "NOT_DETERMINABLE" for a in answers):
        reason = answers[0].not_determinable_reason if answers else ""
        lines = [NOT_DETERMINABLE_TEXT]
        extra = owner_not_determinable_reason(reason)
        if extra and extra != NOT_DETERMINABLE_TEXT:
            lines += ["", extra]
        return sanitize_owner_text("\n".join(lines))

    trust = (plan.trust_level if plan is not None else "") or (
        answers[0].trust_level if answers else "")
    label, explanation = _trust_line(trust)
    lines = []

    forecast_note = sanitize_owner_text(getattr(plan, "forecast_note", "") or "")
    if forecast_note:
        lines.append(forecast_note)
        lines.append("")

    if trust == "BLOCK":
        lines.append("No single reliable figure can be stated: the available definitions "
                     "disagree, and choosing one would be a business decision.")
        lines.append(explanation)
        lines.append("")
        lines.append("The definitions currently supported by the records:")
        lines += _definition_lines(answers, "blocked_reason")
    elif trust == "SHOW_BOTH":
        lines.append("This question does not have one agreed figure.")
        lines.append(explanation)
        lines.append("")
        lines.append("Every evidence-backed definition is shown; none is selected as the answer:")
        lines += _definition_lines(answers, "caveat")
    else:
        for ans in answers:
            name = ans.metric_name or "This measure"
            # When a monthly P&L series answers an expenses/revenue/profit concept,
            # label the measure by the concept the owner asked about.
            if plan is not None and plan.metric is not None:
                concept = (plan.metric.concept or "").replace("_", " ")
                if concept in ("expenses", "revenue", "profit") and "p&l" in name.lower():
                    name = concept.capitalize()
            raw = ans.headline
            if raw is None and ans.results:
                raw = ans.results[0].value
            is_series, _ = _extract_month_from_series(raw, plan)
            if is_series and plan is not None and plan.time is not None:
                name = re.sub(r"\s+by\s+month\b", "", name, flags=re.I).strip() or name
                period_label = getattr(plan.time, "period_label", "") or ""
                if period_label and period_label not in ("all-time",) and period_label not in name.lower():
                    name = f"{name} ({period_label})"
            quantity, unit, missing_period = _owner_figure_from_answer(ans, plan)
            if missing_period:
                lines.append(
                    f"No recorded figure is available for {missing_period} in the "
                    f"exported evidence. {NOT_DETERMINABLE_TEXT}")
            elif quantity is not None and not isinstance(quantity, dict):
                lines.append(f"{name} is {format_owner_quantity(quantity, unit)}.")
            elif (ans.results and not isinstance(ans.results[0].value, dict)
                  and not (plan is not None and plan.time is not None
                           and getattr(plan.time, "period_label", "") not in
                           ("", "all-time", None))):
                r0 = ans.results[0]
                lines.append(f"{name} is {format_owner_quantity(r0.value, r0.unit)}.")
            if trust == "DISCLOSE" or ans.caveat:
                lines.append(explanation)
                if ans.caveat:
                    lines.append(owner_caveat(ans.caveat))
            elif trust == "SAFE":
                lines.append(explanation)

    if reasoning is not None:
        why = []
        recs = []
        for s in reasoning.statements:
            if s.stage in ("OBSERVATION", "INFERENCE", "HYPOTHESIS"):
                why.append(f"• {sanitize_owner_text(s.text)}")
            elif s.stage == "RECOMMENDATION" and (s.text or "").strip():
                recs.append(f"• {sanitize_owner_text(s.text)}")
        lines += _section("Why", why)
        lines += _section("What to do next", recs)

    return sanitize_owner_text("\n".join(ln for ln in lines if ln is not None).strip())


def present_driver_answer(question, plan, answers, root_cause, reasoning=None):
    """Owner prose for a driver/why question — must not silently become a lookup.

    Establishes whether the claimed direction of change is evidenced. If not, says so.
    Never presents an all-time total as the answer to "why is it down?".
    """
    from engine.change_detection import DECREASE, INCREASE, NO_CHANGE, UNAVAILABLE

    q = (question or "").lower()
    claims_down = any(w in q for w in (
        "down", "fall", "fell", "drop", "dropped", "decline", "decreased", "lower", "worse",
    ))
    claims_up = any(w in q for w in (
        "up", "rise", "rose", "increase", "increased", "higher", "better", "grow", "grew",
    ))

    lines = []
    target = getattr(root_cause, "target_change", None) if root_cause else None
    name = (getattr(root_cause, "metric_name", None)
            or (plan.metric.concept.replace("_", " ") if plan and plan.metric else "This measure"))

    if root_cause is None or (root_cause.not_determinable_reason and not target):
        lines.append(
            f"I can't run a driver analysis for {name} from the available evidence yet."
        )
        if root_cause and root_cause.limitations:
            lines.append(sanitize_owner_text(root_cause.limitations[0]))
        return sanitize_owner_text("\n".join(lines))

    if target is None or not getattr(target, "detected", False):
        reason = ""
        if target is not None:
            reason = sanitize_owner_text(getattr(target, "unavailable_reason", "") or "")
        lines.append(
            f"I can't confirm a period-to-period change for {name} from the available "
            f"evidence, so I won't invent a cause."
        )
        if claims_down:
            lines.append(
                "Your question assumes it went down; that decrease is not established here."
            )
        if claims_up:
            lines.append(
                "Your question assumes it went up; that increase is not established here."
            )
        if reason:
            lines.append(reason)
        lines.append("Ask for this month versus last month if you want a recorded comparison.")
        return sanitize_owner_text("\n".join(lines))

    classification = target.classification
    if claims_down and classification != DECREASE:
        lines.append(
            f"The records do not show {name} decreasing between "
            f"{target.previous_period} and {target.current_period} "
            f"(direction: {classification.lower().replace('_', ' ')}). "
            f"I will not explain a decrease that is not evidenced."
        )
        lines.append(
            f"Recorded values: {format_owner_quantity(target.previous_value)} → "
            f"{format_owner_quantity(target.current_value)}."
        )
        return sanitize_owner_text("\n".join(lines))
    if claims_up and classification != INCREASE:
        lines.append(
            f"The records do not show {name} increasing between "
            f"{target.previous_period} and {target.current_period}. "
            f"I will not explain an increase that is not evidenced."
        )
        return sanitize_owner_text("\n".join(lines))

    direction = {
        INCREASE: "increased", DECREASE: "decreased", NO_CHANGE: "did not change",
    }.get(classification, "changed")
    lines.append(
        f"{name} {direction} from {format_owner_quantity(target.previous_value)} "
        f"({target.previous_period}) to {format_owner_quantity(target.current_value)} "
        f"({target.current_period})."
    )
    lines.append(sanitize_owner_text(getattr(target, "materiality", "") or ""))

    drivers = tuple(getattr(root_cause, "drivers", ()) or ())
    pattern = [d for d in drivers if d.status == "PATTERN_ONLY"]
    if pattern:
        lines.append("")
        lines.append("Documented related movements (patterns, not proven causes):")
        for d in pattern:
            ch = d.change
            if ch is None:
                continue
            lines.append(
                f"• {d.metric_name}: {format_owner_quantity(ch.previous_value)} → "
                f"{format_owner_quantity(ch.current_value)} "
                f"({ch.classification.lower().replace('_', ' ')})"
            )
        lines.append(
            "These are correlations over documented dependency edges, not demonstrated causes."
        )
    else:
        lines.append(
            "No driver components with a comparable period change are available for this "
            "measure, so a contribution breakdown cannot be stated."
        )

    for lim in getattr(root_cause, "limitations", ()) or ():
        cleaned = sanitize_owner_text(lim)
        if cleaned and cleaned not in lines:
            lines.append(cleaned)

    return sanitize_owner_text("\n".join(ln for ln in lines if ln).strip())


def present_anomaly_answer(plan, answers):
    """Anomaly questions must not be answered as a SAFE plain lookup of the total."""
    subject = ""
    if plan is not None and plan.metric is not None:
        subject = plan.metric.concept.replace("_", " ")
    lines = [
        "Anomaly detection is only partially supported: no significance threshold is defined "
        "in the records, so I cannot mark values as unusual.",
    ]
    if subject:
        lines.append(
            f"Showing the recorded {subject} total would not answer whether anything is "
            f"anomalous, so I am not substituting that lookup for an anomaly scan."
        )
    return sanitize_owner_text("\n".join(lines))


# The observed change is a FACT. Only its significance is unknown. Reporting both in one
# "not determinable" breath told the owner the measurement itself was unreliable, when what is
# actually missing is a business threshold only they can set.
MATERIALITY_OWNER_SENTENCE = (
    "Whether that is materially significant cannot be determined, because no business "
    "threshold for significance is defined in your records."
)


def _month_name(period):
    """'2026-08-01' -> 'August 2026'. Presentation of a period the engine already chose."""
    m = re.match(r"^(\d{4})-(\d{2})", str(period or ""))
    if not m:
        return str(period or "")
    names = ("January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December")
    year, mon = int(m.group(1)), int(m.group(2))
    if not 1 <= mon <= 12:
        return str(period)
    return f"{names[mon - 1]} {year}"


def present_comparison_answer(change, plan=None):
    """Period comparison / 'compare this with last' -- never a single-period lookup.

    Three outcomes, kept distinct because collapsing them misleads:

      * the requested comparison was computed -> state the change as the fact it is, then
        state separately that judging its significance needs a threshold only the owner has;
      * the requested period is only partly captured -> say so about the period ASKED FOR,
        give the to-date figure, and offer the whole-month comparison as a labelled
        alternative rather than as the answer;
      * nothing comparable exists -> say that.
    """
    from engine.change_detection import (INCREASE, DECREASE, NO_CHANGE, PARTIAL_PERIOD)

    # The plan may already hold the SPECIFIC reason a comparison is impossible -- "only 1
    # distinct value of property_id exists", say. It is established before any comparison is
    # attempted, so it is the reason the owner needs and the only one they can act on.
    plan_reason = owner_not_determinable_reason(
        getattr(plan, "not_determinable_reason", "") or "")

    if change is None:
        # No comparison was even attempted. Without the plan's reason there is nothing to say
        # beyond the generic refusal.
        return plan_reason or "I can't produce a period comparison from the available evidence."

    # -- the requested period is not yet whole -------------------------------------------------
    if getattr(change, "classification", "") == PARTIAL_PERIOD:
        measure = change.metric_name or "This measure"
        asked = _month_name(getattr(change, "requested_current", "") or change.current_period)
        against = _month_name(getattr(change, "requested_previous", "")
                              or change.previous_period)
        # Worded here rather than echoing the engine's own reason string: that one is written
        # for the audit trail and names series keys, and the owner needs the month.
        from engine.change_detection import EXPORT_SNAPSHOT_DATE
        lines = [
            f"I can't reliably compare {asked} with {against} yet.",
            f"{asked} is only partly captured: your records in this export stop at "
            f"{EXPORT_SNAPSHOT_DATE}. Measuring a part-month against a whole one would show "
            f"the shorter window rather than a real movement, and there is no day-by-day "
            f"series available to shorten {against} to match.",
        ]
        partial = getattr(change, "partial_current_value", None)
        if partial is not None:
            lines.append(
                f"{measure} for {asked} so far is {format_owner_quantity(partial, change.unit)}. That is a "
                f"part-month total, not a full month, so it is not comparable with {against}.")
        alt = getattr(change, "alternative", None)
        if alt is not None and getattr(alt, "detected", False):
            alt_dir = {INCREASE: "increased", DECREASE: "decreased",
                       NO_CHANGE: "did not change"}.get(alt.classification, "changed")
            alt_pct = (f" ({format_owner_magnitude(alt.percentage_change)}%)"
                       if alt.percentage_change is not None else "")
            lines.append(
                f"A different question you may want instead -- the most recent two whole "
                f"months: {measure} {alt_dir} by "
                f"{format_owner_magnitude(alt.absolute_change, alt.unit)}{alt_pct} between "
                f"{_month_name(alt.previous_period)} and {_month_name(alt.current_period)}.")
            lines.append(MATERIALITY_OWNER_SENTENCE)
        return sanitize_owner_text("\n".join(ln for ln in lines if ln).strip())

    if not getattr(change, "detected", False):
        # An earlier stage may already have established WHY this cannot be compared, and its
        # reason is the specific one -- "only 1 distinct value of property_id exists", say.
        # The change object carries no such reason, because the pipeline stopped before a
        # comparison was ever attempted; the plan does. Leading with the generic sentence threw
        # that away and told the owner nothing they could act on.
        change_reason = sanitize_owner_text(getattr(change, "unavailable_reason", "") or "")

        if plan_reason:
            # The specific reason stands on its own. The generic line adds nothing once the
            # actual limitation has been stated.
            lines = [plan_reason]
            if change_reason and change_reason not in plan_reason:
                lines.append(change_reason)
            return sanitize_owner_text("\n".join(lines))

        lines = [
            "I can't produce a period comparison from the available evidence.",
        ]
        if change_reason:
            lines.append(change_reason)
        return sanitize_owner_text("\n".join(lines))

    name = change.metric_name or "This measure"
    direction = {
        INCREASE: "increased", DECREASE: "decreased", NO_CHANGE: "did not change",
    }.get(change.classification, "changed")

    pct = (f" ({format_owner_magnitude(change.percentage_change)}%)"
           if change.percentage_change is not None else "")
    if change.classification == NO_CHANGE:
        headline = (f"{name} did not change between {_month_name(change.previous_period)} "
                    f"and {_month_name(change.current_period)}.")
    else:
        headline = (
            f"{name} {direction} by {format_owner_magnitude(change.absolute_change, change.unit)}{pct} "
            f"between {_month_name(change.previous_period)} and "
            f"{_month_name(change.current_period)}, from "
            f"{format_owner_quantity(change.previous_value, change.unit)} to "
            f"{format_owner_quantity(change.current_value, change.unit)}.")

    lines = [headline]
    coverage = sanitize_owner_text(getattr(change, "coverage_note", "") or "")
    if coverage and "incomplete" in coverage.lower():
        lines.append(coverage.split(". ")[0].rstrip(".") + ".")
    # A separate sentence, about significance only. The figure above is measured, not uncertain.
    lines.append(MATERIALITY_OWNER_SENTENCE)
    return sanitize_owner_text("\n".join(ln for ln in lines if ln).strip())


# --------------------------------------------------------------------------------------------
# Whole-business workflows
# --------------------------------------------------------------------------------------------

# How many items of a long list a briefing shows before saying how many remain.
BRIEFING_LIST_LIMIT = 5


def _trimmed(lines, limit=BRIEFING_LIST_LIMIT, noun="item"):
    """Show the first `limit` lines and say plainly how many were not shown.

    Never a silent truncation: the remainder is counted in the owner's own words, and every
    item stays available through the question that produced it.
    """
    items = list(lines)
    if len(items) <= limit:
        return items
    hidden = len(items) - limit
    plural = noun if hidden == 1 else noun + "s"
    return items[:limit] + [
        f"{hidden} further {plural} are not listed here. Ask \"What needs my attention?\" "
        f"to see them all."]


def present_briefing(summary):
    """Six-section owner briefing from an ExecutiveSummary. No IDs, dumps, or spec filenames."""
    health = tuple(summary.business_health or ())
    ops = tuple(summary.operations or ())
    presentable = [l for l in health + ops if l.presentable]
    conflicted = [l for l in health + ops if not l.presentable]
    n_attention = len(summary.attention_required or ())

    takeaway = [
        f"This is the business picture from the {summary.generated_as_of} records."
    ]
    if presentable:
        takeaway.append(f"{len(presentable)} measures can be stated as a single figure.")
    if conflicted:
        takeaway.append(
            f"{len(conflicted)} measures cannot: more than one evidence-backed definition "
            "exists, and choosing between them is a business decision.")
    if n_attention:
        takeaway.append(
            f"{n_attention} items need an owner decision before a single figure can be used.")

    facts = []
    for line in health + ops:
        facts.append(_kpi_fact(line))

    attention = []
    for a in (summary.attention_required or ()):
        decision = owner_caveat(a.get("decision") or "")
        if decision:
            label, _ = _trust_line(a.get("trust") or "")
            attention.append(f"• {label}: {decision}")
    for r in (summary.risks or ())[:8]:
        obs = owner_caveat(r.get("observation") or "")
        if obs:
            attention.append(f"• {obs}")

    changed = _change_lines(summary.what_changed or ())

    actions = []
    for a in (summary.what_to_do or ()):
        rec = owner_caveat(a.get("recommendation") or "")
        if rec:
            actions.append(f"• {rec}")

    caveats = list(owner_limitations(summary.limitations))

    parts = []
    parts += _section("Executive takeaway", takeaway)
    parts += _section("Key numbers", facts)
    parts += _section("What needs attention", _trimmed(attention, noun="item"))
    parts += _section("What changed", changed)
    parts += _section("What to do next", _trimmed(actions, noun="step"))
    # Caveats are never trimmed. A limitation the owner does not see is a limitation that does
    # not exist as far as their decision is concerned.
    parts += _section("Important caveat", [f"• {c}" for c in caveats])
    return sanitize_owner_text("\n".join(parts).strip())


def _kpi_fact(line):
    name = owner_family_name(line.display_name)
    if line.trust_level == "NOT_DETERMINABLE":
        extra = owner_not_determinable_reason(line.reason)
        return f"• {name}: {NOT_DETERMINABLE_TEXT}" + (f" {extra}" if extra else "")
    if not line.presentable:
        # The conflict itself is stated here in full. The competing figures are not inlined:
        # a briefing covering sixteen measures would become a wall of numbers, and asking
        # about this one measure returns every definition, labelled, with no winner picked.
        count = len(line.definitions or ())
        label, _ = _trust_line(line.trust_level)
        how_many = (f"{count} evidence-backed definitions disagree"
                    if count else "the evidence carries competing definitions")
        body = (f"• {name}: no single figure can be stated - {how_many}. "
                f"Ask about {name.lower()} to see each one.")
        if line.caveat:
            body += f" {owner_caveat(line.caveat)}"
        return body
    body = f"• {name}: {format_owner_quantity(line.value, line.unit)}"
    if line.caveat:
        body += f" — {owner_caveat(line.caveat)}"
    return body


def _reason_with_subject(reason, name):
    """Restore the subject that a stripped identifier took with it.

    A reason written as "M.PNL.001's monthly values are composite" sanitizes down to
    "monthly values are composite", which reads as a fragment. The line that carries it
    already names the measure, so the subject comes back as a pronoun -- repeating the name
    would stutter ("P&L by month: ... P&L by month's monthly values ..."). Same subject,
    no new claim.
    """
    text = (reason or "").strip()
    if not text:
        return text
    first = text.split(" ", 1)[0]
    if first[:1].islower():
        if name and text.lower().startswith(name.lower()):
            return text
        return f"Its {text}"
    return text


def _change_lines(changes):
    lines = []
    for c in changes:
        if isinstance(c, dict):
            name = c.get("name") or c.get("metric_name") or "This measure"
            classification = c.get("classification") or ""
            if classification == UNAVAILABLE or classification == "UNAVAILABLE":
                reason = _reason_with_subject(
                    owner_not_determinable_reason(c.get("reason") or ""), name)
                lines.append(
                    f"• {name}: a period comparison is not available. "
                    f"{reason}".rstrip())
                continue
            word = _CHANGE_WORDS.get(classification, classification.lower())
            abs_c = format_owner_quantity(c.get("absolute_change"),
                                          c.get("unit") or "", magnitude=True)
            pct = c.get("percentage_change")
            pct_s = f" ({format_owner_magnitude(pct)}%)" if pct is not None else ""
            prev = c.get("previous_period") or ""
            curr = c.get("current_period") or ""
            span = f" from {prev} to {curr}" if prev and curr else ""
            lines.append(f"• {name} {word} by {abs_c}{pct_s}{span}.")
        else:
            name = c.metric_name
            if not c.detected:
                reason = _reason_with_subject(
                    owner_not_determinable_reason(c.unavailable_reason), name)
                lines.append(
                    f"• {name}: a period comparison is not available. "
                    f"{reason}".rstrip())
                continue
            word = _CHANGE_WORDS.get(c.classification, c.classification.lower())
            abs_c = format_owner_quantity(c.absolute_change,
                                          getattr(c, "unit", "") or "", magnitude=True)
            pct_s = (f" ({format_owner_magnitude(c.percentage_change)}%)"
                     if c.percentage_change is not None else "")
            span = ""
            if c.previous_period and c.current_period:
                span = f" from {c.previous_period} to {c.current_period}"
            lines.append(f"• {name} {word} by {abs_c}{pct_s}{span}.")
    if lines:
        lines.append(MATERIALITY_OWNER)
    return lines


def present_what_changed(changes):
    detected = [c for c in changes if getattr(c, "detected", False)]
    takeaway = (
        "These are the period-to-period movements the records support. Whether any movement "
        "is large enough to matter is not judged here."
    )
    parts = []
    parts += _section("Executive takeaway", [takeaway])
    parts += _section("Key numbers", _change_lines(changes))
    if not detected:
        parts += _section(
            "What changed",
            ["No complete comparable periods produced a movement that can be stated."])
    parts += _section("Important caveat", [MATERIALITY_OWNER])
    return sanitize_owner_text("\n".join(parts).strip())


def present_what_to_do(summary):
    attention = []
    for a in (summary.attention_required or ()):
        decision = owner_caveat(a.get("decision") or "")
        if decision:
            label, _ = _trust_line(a.get("trust") or "")
            attention.append(f"• {label}: {decision}")
    for r in (summary.risks or ())[:12]:
        obs = owner_caveat(r.get("observation") or "")
        if obs:
            attention.append(f"• {obs}")

    actions = []
    for a in (summary.what_to_do or ()):
        rec = owner_caveat(a.get("recommendation") or "")
        if rec:
            actions.append(f"• {rec}")

    n = len(summary.attention_required or ())
    takeaway = (
        f"{n} items need an owner decision because competing definitions exist, or because "
        "a documented risk was already raised by the insight layer. No new priority score "
        "is invented."
    )
    parts = []
    parts += _section("Executive takeaway", [takeaway])
    parts += _section("What needs attention", _trimmed(attention, noun="item"))
    parts += _section("What to do next", _trimmed(actions, noun="step"))
    parts += _section("Important caveat", [f"• {c}" for c in owner_limitations(summary.limitations)])
    return sanitize_owner_text("\n".join(parts).strip())


# --------------------------------------------------------------------------------------------
# Condensed skeletons for the wording layer
# --------------------------------------------------------------------------------------------
#
# The wording layer is handed a SMALL, question-relevant set of facts -- not the whole
# management briefing. Two reasons, and the second is the important one:
#
#   1. A local model restating eight thousand characters takes minutes on CPU and times out,
#      so the owner never saw a verbalized answer at all.
#   2. Asking a model to restate everything invites it to summarise, and a model choosing what
#      to leave out of a conflict disclosure is exactly the decision it must never make.
#
# So the choice of what to include is made HERE, deterministically, and the model only re-words
# what it is given. Every condenser keeps the whole of anything that is load-bearing: every
# competing definition, every trust posture, the materiality caveat. What it drops is bulk --
# the eleventh identically-worded recommendation, the full metric roster.
#
# `present_*` remains the complete deterministic answer and remains the fallback.

MATERIALITY_SHORT = (
    "Whether a movement is large enough to matter is a business judgement: no significance\n"
    "threshold exists in the records. " + NOT_DETERMINABLE_TEXT
)

CONDENSED_KEY_NUMBERS = 4
CONDENSED_LIST = 3


def _first_sentence(text):
    """The claim, without the standing disclaimer that follows it in every sibling item."""
    body = (text or "").strip()
    if not body:
        return ""
    for end in (". ", "; "):
        if end in body:
            return body.split(end)[0].strip() + "."
    return body


def _short_fact(line):
    """One measure, in as few words as state it honestly."""
    name = owner_family_name(line.display_name)
    if line.trust_level == "NOT_DETERMINABLE":
        return f"• {name}: {NOT_DETERMINABLE_TEXT}"
    if not line.presentable:
        count = len(line.definitions or ())
        how_many = (f"{count} definitions disagree" if count
                    else "competing definitions exist")
        return (f"• {name}: no single figure can be stated - {how_many}. "
                f"Ask about {name.lower()} to see each one.")
    return f"• {name}: {format_owner_quantity(line.value, line.unit)}"


def condense_briefing(summary):
    """A short executive summary: the headline measures, what is contested, what needs a
    decision, and the one caveat that governs all of it."""
    health = tuple(summary.business_health or ())
    ops = tuple(summary.operations or ())
    lines = health + ops
    presentable = [l for l in lines if l.presentable]
    contested = [l for l in lines if not l.presentable]

    n_attention = len(summary.attention_required or ())
    takeaway = [
        f"As at {summary.generated_as_of}. {len(presentable)} measures have one agreed "
        f"figure; {len(contested)} do not.",
    ]
    if n_attention:
        takeaway.append(f"{n_attention} items need an owner decision.")

    facts = [_short_fact(l) for l in presentable[:CONDENSED_KEY_NUMBERS]]

    # Every contested measure is still named -- a conflict is never dropped to save space --
    # but they share one line instead of a paragraph each. The competing figures behind each
    # are one question away, and the line says so.
    if contested:
        names = ", ".join(owner_family_name(l.display_name) for l in contested)
        facts.append(
            f"• No single figure can be stated for: {names}. Competing evidence-backed "
            f"definitions disagree; ask about one to see every definition.")

    attention = []
    for a in (summary.attention_required or ())[:2]:
        decision = _first_sentence(owner_caveat(a.get("decision") or ""))
        if decision:
            attention.append(f"• {decision}")
    remaining = n_attention - len(attention)
    if remaining > 0:
        attention.append(f"{remaining} further items are not listed here.")

    changed = [_first_sentence(ln)
               for ln in _change_lines(tuple(summary.what_changed or ())[:2])]

    parts = []
    parts += _section("Executive takeaway", takeaway)
    parts += _section("Key numbers", facts)
    parts += _section("What needs attention", attention)
    parts += _section("What changed", changed[:2])
    parts += _section("Important caveat", [MATERIALITY_SHORT])
    return sanitize_owner_text("\n".join(parts).strip())


def condense_what_to_do(summary):
    """The few decisions actually waiting on the owner."""
    n = len(summary.attention_required or ())
    takeaway = [f"{n} items need an owner decision. No priority score is invented, so these "
                f"are not ranked."]

    attention = []
    for a in (summary.attention_required or ())[:CONDENSED_LIST]:
        decision = _first_sentence(owner_caveat(a.get("decision") or ""))
        if decision:
            attention.append(f"• {decision}")
    if n > len(attention):
        attention.append(f"{n - len(attention)} further items are not listed here.")

    # "What to do next" repeated the attention list almost word for word. Only steps that say
    # something the attention list did not are carried.
    seen = {a.lower() for a in attention}
    actions = []
    for a in (summary.what_to_do or ())[:CONDENSED_LIST]:
        rec = _first_sentence(owner_caveat(a.get("recommendation") or ""))
        if rec and f"• {rec}".lower() not in seen:
            actions.append(f"• {rec}")

    parts = []
    parts += _section("Executive takeaway", takeaway)
    parts += _section("What needs attention", attention)
    parts += _section("What to do next", actions[:2])
    return sanitize_owner_text("\n".join(parts).strip())


def condense_what_changed(changes):
    """Only the movements the records actually support."""
    lines = [_first_sentence(ln)
             for ln in _change_lines(tuple(changes)[:CONDENSED_LIST])]
    parts = []
    parts += _section(
        "Executive takeaway",
        ["These are the period-to-period movements the records support. Whether any is large "
         "enough to matter is not judged here."])
    parts += _section("What changed", lines[:CONDENSED_LIST])
    parts += _section("Important caveat", [MATERIALITY_SHORT])
    return sanitize_owner_text("\n".join(parts).strip())


def condense_what_to_trust(buckets):
    """How many measures sit at each posture. The full roster stays on the dashboard."""
    facts = []
    for lv in ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
        ids = list(buckets.get(lv, []))
        if not ids:
            continue
        label, explanation = _trust_line(lv)
        facts.append(f"• {label} ({len(ids)}): {explanation}")
    parts = []
    parts += _section(
        "Executive takeaway",
        ["Each measure keeps the reliability the records already assigned. Nothing here "
         "upgrades or downgrades a figure."])
    parts += _section("Key numbers", facts)
    return sanitize_owner_text("\n".join(parts).strip())


def present_what_to_trust(buckets, names_for):
    """buckets: trust_level -> iterable of metric_ids. names_for(mid) -> display name."""
    parts = []
    parts += _section(
        "Executive takeaway",
        ["Each measure keeps the reliability the records already assigned. "
         "Nothing here upgrades or downgrades a figure."])
    facts = []
    for lv in ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
        ids = list(buckets.get(lv, []))
        label, explanation = _trust_line(lv)
        facts.append(f"• {label} ({len(ids)}): {explanation}")
        for mid in ids:
            facts.append(f"  – {names_for(mid)}")
    parts += _section("Key numbers", facts)
    return sanitize_owner_text("\n".join(parts).strip())


# --------------------------------------------------------------------------------------------
# Forecast
# --------------------------------------------------------------------------------------------

def present_forecast(forecast, question=""):
    """Owner wording for an already-computed forecast. Computes nothing.

    The method's tested error is stated with the figure, because a projection without its
    accuracy invites the owner to read it as a measurement.
    """
    if forecast is None:
        return "I can't produce a forecast from the available evidence."

    if not getattr(forecast, "available", False):
        return sanitize_owner_text(
            getattr(forecast, "not_determinable_reason", "")
            or "I can't produce a forecast from the available evidence.")

    points = list(forecast.points)
    lines = []

    if len(points) == 1:
        p = points[0]
        lines.append(
            f"Projected revenue for {_month_name(p.period + '-01')} is "
            f"{format_owner_quantity(p.value, 'INR')}.")
        if p.lower is not None and p.upper is not None:
            lines.append(
                f"On past accuracy the outcome would usually fall between "
                f"{format_owner_quantity(p.lower, 'INR')} and "
                f"{format_owner_quantity(p.upper, 'INR')}.")
    else:
        lines.append(f"Projected revenue for the next {len(points)} months:")
        for p in points:
            band = ""
            if p.lower is not None and p.upper is not None:
                band = (f" (usually between {format_owner_quantity(p.lower, 'INR')} and "
                        f"{format_owner_quantity(p.upper, 'INR')})")
            lines.append(f"\u2022 {_month_name(p.period + '-01')}: "
                         f"{format_owner_quantity(p.value, 'INR')}{band}")

    direction = getattr(forecast, "direction", "")
    if direction and forecast.last_actual is not None:
        word = {"increase": "higher than", "decrease": "lower than",
                "flat": "level with"}.get(direction, "compared with")
        lines.append(
            f"That is {word} the last complete month "
            f"({format_owner_quantity(forecast.last_actual, 'INR')}).")

    mape = (forecast.backtest or {}).get("mape_pct")
    if mape is not None:
        lines.append(
            f"This projection continues the trend in your recorded revenue. Tested against "
            f"months the model had not seen, it was off by about {mape}% on average at this "
            f"range.")

    for limitation in (forecast.limitations or ()):
        lines.append(limitation)

    # A driver that was tested and rejected is a finding, not an absence.
    rejected = [d for d in (forecast.drivers or ())
                if d.get("verdict") in ("REJECTED", "NOT_DERIVABLE")
                and "occup" in d.get("driver", "").lower()]
    if rejected:
        lines.append(
            "Occupancy was tested as a predictor and is not used: it tracks revenue only "
            "because both have been rising, and adding it made the projection materially less "
            "accurate.")

    return sanitize_owner_text("\n".join(ln for ln in lines if ln).strip())


# --------------------------------------------------------------------------------------------
# Descriptive analysis
# --------------------------------------------------------------------------------------------

DESCRIPTIVE_LIST_LIMIT = 6


def _rupees(value):
    return format_owner_quantity(value, "INR")


def _descriptive_cross_section(summary):
    stats = summary.stats
    lines = [f"Typical {summary.label.lower()} is {_rupees(stats['median'])} "
             f"across {stats['count']:,} recorded allotments."]

    # A quartile range that collapses to a single value says nothing the median has not
    # already said; the zero-share note the engine attaches is what describes such a column.
    if (stats.get("p25") is not None and stats.get("p75") is not None
            and stats["p25"] != stats["p75"]):
        lines.append(f"Half of them sit between {_rupees(stats['p25'])} and "
                     f"{_rupees(stats['p75'])}.")
    lines.append(f"The full recorded range runs from {_rupees(stats['min'])} to "
                 f"{_rupees(stats['max'])}, and the average is {_rupees(stats['mean'])}.")

    if stats.get("missing_count"):
        lines.append(f"{stats['missing_count']:,} allotments have no value recorded for this "
                     f"({stats['missing_pct']}% of the records), and are not included above.")
    lines.extend(_recorded_zero_note(stats, summary.label))
    return lines


def _recorded_zero_note(stats, label):
    """What a recorded zero does and does not establish.

    A zero in this column is a value that was entered, and it is counted as entered -- it is not
    dropped, filtered or read as missing. What the export does NOT settle is which of two things
    each zero means. Saying so is the difference between reporting the records and interpreting
    them, and the range line above ("from Rs.0 to ...") reads as a charged amount unless this is
    said. Withheld where zeros dominate the column: the engine already attaches its own note
    there, and two notes about the same zeros is one too many.
    """
    zeros = stats.get("zero_count") or 0
    if not zeros or (stats.get("zero_pct") or 0) >= 25:
        return []
    return [
        f"{zeros:,} of the {stats['count']:,} records hold a recorded value of zero "
        f"({stats['zero_pct']}%), and they are counted above as recorded. The export does not "
        f"establish which they are: a genuine zero arrangement, or a value that was never "
        f"entered and was stored as zero. Both would look identical here, so neither reading "
        f"is assumed."
    ]


def _descriptive_series(summary):
    stats = summary.stats
    label = summary.label.split(":")[0].strip().lower()
    lines = [f"Across {stats['observations']} complete months of {label}, the typical "
             f"month-to-month move is {_rupees(stats['median'])}."]

    if stats.get("p25") is not None and stats.get("p75") is not None:
        # The direction words carry the sign, so the magnitudes are rendered unsigned --
        # "a fall of -390,610" is a double negative that reads as a rise.
        lines.append(f"Half of the months moved between {_rupees(stats['p25'])} and "
                     f"{_rupees(stats['p75'])}; the largest fall was "
                     f"{format_owner_quantity(stats['min'], 'INR', magnitude=True)} and the "
                     f"largest rise "
                     f"{format_owner_quantity(stats['max'], 'INR', magnitude=True)}.")
    if stats.get("std_dev") is not None:
        lines.append(f"Month-to-month moves scatter around that by about "
                     f"{_rupees(stats['std_dev'])}.")
    if stats.get("median_pct_change") is not None:
        lines.append(f"In percentage terms the typical month changes by "
                     f"{stats['median_pct_change']}%. That is growth; the figures above are "
                     f"how much the movement itself varies. The two are different things.")
    if stats.get("latest_level") is not None:
        lines.append(f"The most recent complete month came in at "
                     f"{_rupees(stats['latest_level'])}.")
    return lines


def _descriptive_relationship(summary):
    stats = summary.stats
    changes = stats.get("correlation_changes")
    levels = stats.get("correlation_levels")
    lines = []

    if changes is not None:
        strength = ("move together closely" if abs(changes) >= 0.7 else
                    "move together to a moderate degree" if abs(changes) >= 0.4 else
                    "barely move together")
        lines.append(f"Month to month, {summary.label} {strength}: the month-to-month "
                     f"correlation is {round(changes, 2)}, measured over "
                     f"{stats['paired_months']} months where both were recorded.")
    if levels is not None:
        lines.append(f"Compared as totals rather than as movements the figure is "
                     f"{round(levels, 2)}, which is the higher of the two and the easier one "
                     f"to over-read.")
    return lines


def _descriptive_apartments(summary):
    stats = summary.stats
    comparable = list(stats["comparable"])
    insufficient = list(stats["insufficient"])
    lines = [f"{stats['apartments_compared']} of {stats['apartments_total']} apartments have "
             f"enough recorded allotments to compare on rent."]

    shown = comparable[:DESCRIPTIVE_LIST_LIMIT]
    if shown:
        lines.append("Highest typical rent first:")
        for row in shown:
            lines.append(f"\u2022 {row['apartment']}: typical {_rupees(row['median'])} "
                         f"(from {row['count']} allotments, "
                         f"{_rupees(row['min'])} to {_rupees(row['max'])})")
        remaining = len(comparable) - len(shown)
        if remaining > 0:
            lines.append(f"\u2022 and {remaining} more apartments below these.")

        # Rents cluster on a handful of round figures, so most of this "ranking" is ties.
        # Listing them in order without saying so implies a difference that is not there.
        tied = sum(1 for r in comparable if r["median"] == shown[0]["median"])
        if tied > 1:
            lines.append(f"{tied} apartments share that same top figure of "
                         f"{_rupees(shown[0]['median'])}, so the order between them is not a "
                         f"difference in rent.")

    # The per-apartment ranges above are the reason this has to be said here as well as on the
    # rent summary: a range reading "from Rs.0" looks like an apartment that was let for
    # nothing, and only the record itself says zero -- not what the zero means.
    with_zero = [r["apartment"] for r in comparable + insufficient if r["min"] == 0]
    if with_zero:
        names = ", ".join(with_zero[:DESCRIPTIVE_LIST_LIMIT])
        more = len(with_zero) - min(len(with_zero), DESCRIPTIVE_LIST_LIMIT)
        tail = f" and {more} more" if more > 0 else ""
        lines.append(
            f"{len(with_zero)} apartments include at least one allotment with a recorded rent "
            f"of zero ({names}{tail}). Those zeros are counted as recorded, and the lowest "
            f"figure shown for those apartments is one of them. The export does not say "
            f"whether each is a genuine zero-rent arrangement or a rent that was never "
            f"entered, so neither is assumed.")

    if insufficient:
        names = ", ".join(r["apartment"] for r in insufficient[:DESCRIPTIVE_LIST_LIMIT])
        more = len(insufficient) - min(len(insufficient), DESCRIPTIVE_LIST_LIMIT)
        tail = f" and {more} more" if more > 0 else ""
        # Named, never dropped: two of these carry the highest rent in the estate, and a
        # ranking that quietly excluded them would look complete while hiding that.
        lines.append(f"Insufficient data to rank: {names}{tail}.")
    return lines


_DESCRIPTIVE_BODY = {
    "cross_section": _descriptive_cross_section,
    "series": _descriptive_series,
    "relationship": _descriptive_relationship,
    "apartments": _descriptive_apartments,
}


def present_descriptive(summary, route):
    """Owner wording for an already-computed descriptive summary. Computes nothing.

    Every figure here was final before this function saw it. What this adds is the ordering an
    owner reads in -- the typical value first, the spread second, and the caveats the engine
    attached kept in full rather than summarised away.
    """
    if summary is None:
        return "I can't describe that from the available records."
    if not summary.available:
        return sanitize_owner_text(
            summary.not_determinable_reason
            or "I can't describe that from the available records.")

    body = _DESCRIPTIVE_BODY.get(route.kind)
    lines = body(summary) if body else []
    lines.extend(summary.notes or ())
    return sanitize_owner_text("\n".join(ln for ln in lines if ln).strip())


# --------------------------------------------------------------------------------------------
# Rent (M.RENT.001) -- a per-bed figure, never collapsed to one number
# --------------------------------------------------------------------------------------------

RENT_LIST_LIMIT = 8


def present_rent_answer(plan, answers):
    """Owner wording for recorded rent. Computes nothing and totals nothing.

    Rent lives on the allotment occupying a bed, and the beds inside one apartment routinely
    carry different rents -- A12 runs three at once. So this lists what each occupied bed
    records. It does not average them, and it does not present any one of them as "the rent for
    A12", because the records do not contain such a figure and inventing one would mean choosing
    on the owner's behalf which bed speaks for the apartment.
    """
    if plan is not None and getattr(plan, "status", "") == "NOT_DETERMINABLE":
        return sanitize_owner_text(
            owner_not_determinable_reason(plan.not_determinable_reason)
            or NOT_DETERMINABLE_TEXT)

    rows = {}
    limitations = ()
    for ans in answers or ():
        for res in ans.results:
            if isinstance(res.value, dict):
                rows.update(res.value)
            limitations = limitations or tuple(
                l for l in (getattr(res, "limitations", "") or "",) if l)

    if not rows:
        return sanitize_owner_text(
            "No rent is recorded against a currently occupied bed for that. "
            + NOT_DETERMINABLE_TEXT)

    apartments = sorted({str(k).split(" bed ")[0] for k in rows})
    scope = apartments[0] if len(apartments) == 1 else ""
    values = [v for v in rows.values() if v is not None]
    distinct = sorted(set(values))

    lines = []
    if scope and len(distinct) == 1:
        lines.append(f"Every occupied bed in {scope} records the same rent, "
                     f"{format_owner_quantity(distinct[0], 'INR')} a month.")
    elif scope:
        lines.append(f"{scope} does not have one rent. Rent is recorded per bed, and its "
                     f"{len(rows)} occupied beds record {len(distinct)} different amounts, "
                     f"from {format_owner_quantity(distinct[0], 'INR')} to "
                     f"{format_owner_quantity(distinct[-1], 'INR')} a month.")
    else:
        lines.append(f"Rent is recorded per bed. {len(rows)} beds are currently occupied.")

    shown = sorted(rows.items())[:RENT_LIST_LIMIT]
    for key, value in shown:
        label = str(key).replace(" bed ", ", bed ")
        if value is None:
            lines.append(f"\u2022 {label}: no rent recorded")
        else:
            lines.append(f"\u2022 {label}: {format_owner_quantity(value, 'INR')} a month")
    remaining = len(rows) - len(shown)
    if remaining > 0:
        lines.append(f"\u2022 and {remaining} more occupied beds.")

    zeros = [k for k, v in rows.items() if v == 0]
    if zeros:
        lines.append(
            f"{len(zeros)} of these record a rent of zero. That is kept as recorded: the "
            f"export does not establish whether it is a genuine zero-rent arrangement or a "
            f"rent that was never entered.")

    lines.append("This is the rent in force now. It carries no effective date in the records, "
                 "so it cannot be read back to an earlier period.")
    for limitation in limitations:
        lines.append(limitation)
    return sanitize_owner_text("\n".join(ln for ln in lines if ln).strip())


# --------------------------------------------------------------------------------------------
# Insights, in the owner's language
# --------------------------------------------------------------------------------------------
#
# The engine composes an insight's prose from its own vocabulary: record identifiers, the
# specification clause that classified it, the internal status of the finding. That text is
# correct and belongs in the audit trail. Rendered on the Owner Home it produced sentences like
#
#   "This is a standing, currently-recorded condition (status: MEASURED) affecting Profit / P&L,
#    not a one-off reading. It is surfaced without being asked because DQ.016 classifies it
#    CRITICAL (insight_generation_spec.md 2 condition 1)."
#
# -- and stripping the identifiers out of it left worse: "because classifies it CRITICAL
# ( 2 condition 1)". Deleting a noun mid-sentence leaves wreckage; the sentence has to be
# written for the owner instead.
#
# So this composes from the insight's STRUCTURED fields -- its category, the measures it
# affects, the amount and row count it carries, its confidence -- and answers the four questions
# an owner actually has: what is happening, why it matters, what they need to decide, and what
# the evidence cannot settle. No figure is recomputed and no disclosure is dropped.

# What the engine's confidence grades mean to someone who did not write them.
_CONFIDENCE_OWNER = {
    "PROVEN": "This is measured directly in the records, not inferred.",
    "MEASURED": "This is measured directly in the records, not inferred.",
    "SUSPECTED": "The records point to this, but do not on their own prove it.",
    "SPLIT": "The records support more than one reading of this, and both are shown.",
    "MEDIUM": "This is read from the records as they stand; it is not a prediction.",
    "LOW": "The records give only weak support for this.",
}

# The system's own flag is not a business priority, and must not be presented as one.
CLASSIFICATION_CAVEAT = (
    "This was flagged by the system's own rules about the evidence, not ranked by business "
    "impact: no validated priority score exists in the records, so the ordering here is not a "
    "judgement about what matters most to the business.")


# The owner's half of the engine's materiality note. Same substance -- no threshold exists, and
# none is invented -- without the specification clause that only the audit trail needs.
OWNER_MATERIALITY = (
    "No business threshold is defined for deciding whether a change of this size matters. "
    "The direction and the size are shown; whether that is significant is your judgement, and "
    "this system will not substitute for it.")


_DIRECTION_WORDS = {"INCREASE": "rose", "DECREASE": "fell", "NO_CHANGE": "unchanged",
                    "PARTIAL_PERIOD": "not yet complete", "UNAVAILABLE": "not comparable"}


def owner_direction(classification):
    """A movement in the word an owner uses for it."""
    return _DIRECTION_WORDS.get((classification or "").strip().upper(),
                                (classification or "").strip().lower())


def owner_period_label(period):
    """A period key as a month an owner recognises. "2026-07-01" -> "July 2026"."""
    text = (period or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", text):
        return _month_name(text if len(text) > 7 else text + "-01")
    return text


def owner_as_of(as_of):
    """The snapshot date, said plainly. "export snapshot 2026-08-29" is how the engine names
    its own boundary; an owner reads a date."""
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", as_of or "")
    if not match:
        return sanitize_owner_text(as_of or "")
    year, month, day = match.groups()
    return f"{int(day)} {_month_name(f'{year}-{month}-01').split()[0]} {year}"


def owner_coverage_note(note):
    """The coverage note an owner can read.

    The engine writes it for the audit trail: "Period(s) 2026-08-01, 2026-09-01 excluded as
    incomplete at the export snapshot (2026-08-29). 53 distinct calendar months of INCOME
    activity within the ledger's 54-month span." Only the first half is about the answer the
    owner is looking at, and the period keys in it are dates they never typed.
    """
    text = sanitize_owner_text(note or "")
    if not text:
        return ""
    first = text.split(". ")[0]
    if "excluded as incomplete" not in first:
        return text
    # The excluded months are listed BEFORE the snapshot date, which the engine puts in
    # parentheses. Reading them off position alone went wrong the moment a month appeared in
    # both -- August was both an excluded month and the month the snapshot falls in, and
    # de-duplicating them silently promoted September into the snapshot's place.
    # Split at the LAST bracket: the sentence opens with "Period(s)", whose own bracket would
    # otherwise take the whole clause with it.
    head = first.rsplit("(", 1)[0]
    months = re.findall(r"(\d{4}-\d{2})(?:-\d{2})?", head)
    excluded = [_month_name(m + "-01") for m in dict.fromkeys(months)]
    if not excluded:
        return first + "."
    listed = " and ".join(excluded) if len(excluded) < 3 else (
        ", ".join(excluded[:-1]) + " and " + excluded[-1])
    verb = "is" if len(excluded) == 1 else "are"
    return (f"{listed} {verb} left out: the records stop part-way through, so counting "
            f"{'it' if len(excluded) == 1 else 'them'} would compare a part-month with a "
            f"whole one.")


# Engine limitations written in the vocabulary of the specification that mandates them. The
# substance is unchanged; the words are the owner's.
_OWNER_LIMITATIONS = (
    ("materiality is undefined",
     "No threshold exists in your records for deciding whether a change is big enough to "
     "matter, so none of the movements below is called significant or insignificant."),
    ("insight triggers",
     "Two kinds of finding cannot be produced at all -- unusual spikes, and changes large "
     "enough to matter -- because deciding either needs a threshold your records do not "
     "define. They are reported as unavailable rather than quietly skipped."),
    ("kpi(s) carry competing definitions",
     "Some measures have more than one definition in your records, and each is shown "
     "separately rather than combined into one figure."),
)


def owner_limitation(text):
    """One engine limitation, said in business language. Unrecognised text is passed through
    sanitized rather than dropped -- a limitation nobody translated is still a limitation."""
    cleaned = sanitize_owner_text(text or "")
    low = cleaned.lower()
    for marker, owner_text in _OWNER_LIMITATIONS:
        if marker in low:
            return owner_text
    return cleaned


def owner_confidence(grade):
    """The engine's confidence grade in the owner's words. Unknown grades pass through empty
    rather than as a token the owner has no way to read."""
    return _CONFIDENCE_OWNER.get((grade or "").strip().upper(), "")


# The registry names a measure after the rule that detects it. Where that name asserts more
# than the evidence establishes, the owner sees the observation instead. Exact match only, and
# the measure, its figures and its records are untouched -- this is the name, not the finding.
_MEASURE_RENAMES = {
    "duplicate invoices": "Repeated invoice groups",
    # Read under an apartment heading, "for one apartment" is the registry explaining its own
    # grain. The owner already chose the apartment.
    "revenue by month for one apartment": "Apartment revenue",
    "expenses by month for one apartment": "Apartment expenses",
    # The same three substitutions the tile headings make, so a measure has one name wherever it
    # appears -- on a card, in a sentence, and in an export.
    "gross/net profit": "Profit",
    "tenant dues": "Tenant dues outstanding",
    "current occupancy": "Occupancy",
    # It counts how many measures sit at each posture. A "score" is a single number that goes up
    # or down and can be good or bad; this is a distribution and is neither. The registry name is
    # unchanged and still names the metric on every technical surface.
    "data-quality score / trust status": "Data trust overview",
}


#
# The parts of a composite figure, named for an owner.
#
# A composite measure's value is a dictionary -- {"total": ..., "deposit_collections": ...} --
# and the field names in it are the engine's, not anyone's business vocabulary. Rendered as they
# are, a collections tile reads "deposit_collections: Rs.116,000.00".
#
# This mapping used to live only in the browser, which meant a second surface rendering the same
# tile had no way to reach it and printed the raw keys instead. It belongs here, beside the rest
# of the owner wording, so every surface names a part the same way.
#
# Naming only: no part is added, dropped, reordered, summed or promoted to a headline. A key with
# no entry keeps its own words, humanised.
#
_OWNER_PART_LABELS = {
    "total": "Total",
    "total amount": "Total",
    "deposit collections": "Deposits",
    "deposits": "Deposits",
    "deposit": "Deposits",
    "non deposit": "Rent and other",
    "rent and other": "Rent and other",
    "ar balance": "Outstanding",
    "deposit held": "Held as deposits",
    "booking advance": "Booking advances",
    "unclipped": "As recorded",
    "floored at zero": "With negatives treated as zero",
    "total bill amount": "Billed",
    "total units consumed": "Units consumed",
    "total tenant eb charge": "Charged to tenants",
    "path a total": "First recorded path",
    "path b total": "Second recorded path",
    "row count": "Records",
    "allotment count": "Allotments affected",
    "amount at risk": "Amount involved",
    "duplicate groups": "Allotment-months with more than one invoice",
    "excess rows": "Additional invoices in those groups",
    "legacy amount": "Source system",
    "je net amount": "Ledger",
    "diff": "Difference",
    "unposted source amount": "Recorded but never posted",
    "verdict": "Assessment",
    "occupied": "Occupied beds",
    "occupancy pct": "Occupancy",
}


def owner_part_label(key):
    """The owner's name for one part of a composite value."""
    normalised = str(key or "").strip().lower().replace("_", " ")
    if normalised in _OWNER_PART_LABELS:
        return _OWNER_PART_LABELS[normalised]
    return normalised[:1].upper() + normalised[1:] if normalised else ""


def owner_value_parts(value, formatter):
    """A composite value's parts, each named and formatted, in the engine's own order.

    Built from the value DICTIONARY rather than by parsing the formatted string back apart --
    the structure is still available at this point, so nothing has to be recovered from prose.
    `formatter` is the engine's own value formatter; this function produces no figure of its own.

    Returns [] for anything that is not a composite, which is the signal to render the single
    formatted figure instead.
    """
    if not isinstance(value, dict) or not value:
        return ()
    parts = []
    for key, raw in value.items():
        if isinstance(raw, dict):
            # A nested group -- the reconciliation figure carries one per source table. Each
            # inner part keeps its own name, prefixed by the group's.
            group = owner_part_label(key)
            for inner_key, inner in raw.items():
                parts.append({"label": f"{group} — {owner_part_label(inner_key)}",
                              "value": formatter(inner)})
            continue
        parts.append({"label": owner_part_label(key), "value": formatter(raw)})
    return tuple(parts)


def owner_measure_name(name):
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", owner_family_name(name or "")).strip()
    return _MEASURE_RENAMES.get(cleaned.lower(), cleaned)


def owner_subject_names(metric_ids, registry):
    """The measures an insight affects, named the way the owner sees them elsewhere."""
    names = []
    for mid in metric_ids or ():
        if registry is None or mid not in registry:
            continue
        name = owner_measure_name(registry.get(mid).semantic_name or "")
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _affected_phrase(amount, count):
    parts = []
    if count:
        parts.append(f"{int(count):,} records")
    if amount:
        parts.append(format_owner_quantity(amount, "INR"))
    if not parts:
        return ""
    return " and ".join(parts)


#
# Findings whose owner-facing wording the detection rule alone does not license.
#
# A detector that groups invoices by (allotment, billing month, invoice type) and reports the
# groups holding more than one row has found repetition, which is a fact. Whether that
# repetition is a duplicate is a different claim, and the exported records do not carry what
# would settle it: a mid-month proration, a room change and a genuine double-billing all look
# the same from here. The engine's own name for the rule is a detector name; used as the
# owner's sentence it states a conclusion the evidence has not reached.
#
# What this does NOT do: remove the finding, change its counts, change its amount, change its
# category, or touch its trust posture. The figures below are the ones the engine produced,
# rendered with the noun the evidence supports.
#
_UNPROVEN_FINDINGS = {
    "DQ.013": {
        "noun": "invoice groups",
        "what": "The records contain multiple invoices for some allotment-month combinations",
        "why": ("The exported evidence does not establish whether these represent duplicate "
                "billing or legitimate proration/room changes."),
        "action": ("Review the affected invoice groups and confirm which are intended billing. "
                   "Until that review is done they should not be treated as duplicates."),
        "changes_it": ("Settling this needs the billing intent behind each group -- proration "
                       "rules, room changes and cancellations -- which the exported records do "
                       "not carry."),
    },
}


def evidence_status(dq_ids):
    """Whether the records establish a finding, or only show the pattern behind it.

    "observed" is not a weaker version of "established" -- it is a different statement. One says
    the records disagree with each other and that is provable from the export; the other says
    something recurs and the export cannot say why. An exceptions view has to keep them apart.
    """
    for dq in dq_ids or ():
        if dq in _UNPROVEN_FINDINGS:
            return "observed"
    return "established"


def _unproven_finding_view(finding, amount, count):
    """One finding stated as the observation it is, with its own counts and amount unchanged."""
    parts = []
    if count:
        parts.append(f"{int(count):,} {finding['noun']}")
    if amount:
        parts.append(format_owner_quantity(amount, "INR"))
    covering = " and ".join(parts)
    what = finding["what"] + (f", covering {covering}." if covering else ".")
    return (sanitize_owner_text(what), sanitize_owner_text(finding["why"]),
            sanitize_owner_text(finding["action"]),
            sanitize_owner_text(finding["changes_it"]))


def owner_insight_view(insight, category, subject_names):
    """The four owner-facing strings for one insight, built from its structured fields.

    Returns (what_happened, why_it_matters, recommended_action, what_would_change_it).
    """
    subjects = _joined_names(subject_names)
    amount = getattr(insight, "affected_amount", None)
    count = getattr(insight, "affected_count", None)
    affected = _affected_phrase(amount, count)
    definitions = len(getattr(insight, "conflict_ids", ()) or ())

    # WHICH KIND of finding this is, from the record family it came from -- never displayed.
    # Branching on the trust posture instead put data-quality conditions through the
    # definition-conflict wording, so a recording problem was described to the owner as
    # "more than one definition of profit", which is a different thing entirely.
    kind = (getattr(insight, "insight_id", "") or "").upper()
    is_conflict = kind.startswith("INS.CONFLICT") or category == "definition_conflict"
    dq_ids = tuple(getattr(insight, "dq_ids", ()) or ())

    if any(d in _UNPROVEN_FINDINGS for d in dq_ids):
        return _unproven_finding_view(
            next(_UNPROVEN_FINDINGS[d] for d in dq_ids if d in _UNPROVEN_FINDINGS),
            amount, count)

    if is_conflict:
        measure = subjects or "this measure"
        gap = format_owner_quantity(amount, "INR") if amount else ""
        what = (f"The records hold more than one definition of {measure}, and they do not agree"
                + (f" -- they differ by {gap}." if gap else "."))
        why = (f"Any decision that needs a single {measure} figure is on hold until you say "
               f"which definition is the official one. Every definition is still shown, with "
               f"its own figure.")
        decide = (f"Decide which definition of {measure} the business treats as authoritative. "
                  f"Until then no one of the competing figures should be acted on.")
    elif kind.startswith("INS.DQ") or category in ("critical", "data_quality"):
        measure = subjects or "several recorded figures"
        plural = bool(subject_names) and len(subject_names) > 1
        verb = "are" if plural or not subject_names else "is"
        what = (f"A recording problem in your data currently affects {measure}"
                + (f", covering {affected}." if affected else "."))
        why = (f"Figures drawn from {measure} inherit that problem, so they may not mean what "
               f"they appear to mean until it is looked at.")
        decide = (f"Review the affected records before {measure} {verb} used for a decision.")
    else:
        measure = subjects or "this area"
        what = (f"{measure.capitalize()} currently shows a condition worth looking at"
                + (f", covering {affected}." if affected else "."))
        why = ("It is reported because the records show it now, not because anything predicts "
               "it. Nothing is estimated.")
        decide = (f"Review the {measure.lower()} worklist and confirm whether each row needs "
                  f"anything done about it.")

    limitation = _CONFIDENCE_OWNER.get(
        (getattr(insight, "confidence", "") or "").upper(), "")
    if definitions and is_conflict:
        # Only a definition conflict leaves a choice open. A recording problem carries conflict
        # records too, and telling the owner to choose between definitions there points them at
        # a decision that is not theirs to make.
        limitation = (limitation + " " if limitation else "") + (
            "Choosing between the definitions is a business decision; the evidence does not "
            "settle it.")
    # The caveat about the system's flag not being a business priority is true of every item
    # on the page, so it is stated once beneath the section rather than appended to each of
    # sixteen cards -- repeated that many times it stops being read at all.

    return (sanitize_owner_text(what), sanitize_owner_text(why),
            sanitize_owner_text(decide), sanitize_owner_text(limitation))


# Two names read as a subject; five read as a dump. The rest are still affected and the
# sentence says so, rather than listing every one of them.
_SUBJECT_LIMIT = 2


def _joined_names(names):
    names = [n for n in (names or ()) if n]
    names = [n for n in names
             if not any(other != n and n.lower().startswith(other.lower() + " ")
                        for other in names)]
    if not names:
        return ""
    if len(names) == 1:
        return names[0].lower()
    shown = [n.lower() for n in names[:_SUBJECT_LIMIT]]
    joined = " and ".join(shown)
    remaining = len(names) - len(shown)
    if not remaining:
        return joined
    noun = "other measure" if remaining == 1 else "other measures"
    return f"{joined} and {remaining} {noun}"


# --------------------------------------------------------------------------------------------
# The attention queue, grouped by business subject
# --------------------------------------------------------------------------------------------
#
# The queue is one row per insight record, and the records are finer-grained than the decisions
# they imply. Four separate recording problems affecting receivables produced four cards that
# said the same thing, and the owner reads eleven rows to find five decisions. Grouping them by
# SUBJECT rather than by record is what makes the section legible.
#
# What grouping must not do: merge a definition conflict into a recording problem. They need
# different things from the owner -- one a decision about which figure is official, the other a
# look at the underlying records -- so they stay in separate groups even when they touch the
# same measure.

# Subjects the registry names in its own terms, said the way the rest of the Owner Home says
# them. The tile headings already make these substitutions; the queue was not.
_QUEUE_SUBJECTS = {
    "gross/net profit": "Profit",
    "current occupancy": "Occupancy",
    "tenant dues": "Tenant dues",
}

_SEVERITY = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}


def owner_subject_of(names):
    """The one business subject a set of affected measures is about, in the owner's words.

    Public because more than the decision queue needs it now: Owner Home groups its attention
    feed by the same subject, so a subject cannot be one card in one list and three in another.
    """
    return _queue_subject(names)


def _queue_subject(names):
    """The business subject of a queue row, in the owner's words."""
    for name in names or ():
        cleaned = owner_measure_name(name)
        if cleaned:
            return _QUEUE_SUBJECTS.get(cleaned.lower(), cleaned)
    return ""


def _worst_posture(levels):
    """The strongest posture in a group. Grouping may not soften a member's trust verdict."""
    present = [l for l in levels if l]
    if not present:
        return ""
    return max(present, key=lambda l: _SEVERITY.get(l, 0))


def group_owner_decisions(rows, subjects_by_insight):
    """One card per business issue, from the queue's own rows.

    `rows` are the attention-queue entries; `subjects_by_insight` maps an insight id to the
    owner-facing names of the measures it affects. Nothing is dropped: every row lands in
    exactly one group, and a group states every subject it covers.
    """
    decisions, reviews = {}, []
    for row in rows or ():
        insight_id = (row.get("insight_id") or "").upper()
        subject = _queue_subject(subjects_by_insight.get(row.get("insight_id"), ()))
        if insight_id.startswith("INS.CONFLICT"):
            key = subject or "This measure"
            entry = decisions.setdefault(key, {"trusts": [], "ids": []})
            entry["trusts"].append(row.get("trust", ""))
            entry["ids"].append(row.get("insight_id"))
        else:
            reviews.append((subject, row))

    out = []
    for subject, entry in decisions.items():
        out.append({
            "insight_id": entry["ids"][0],
            "trust": _worst_posture(entry["trusts"]),
            "title": f"{subject} — decision needed",
            "decision": (
                f"Several evidence-backed definitions exist and they give different answers. "
                f"Decide which one the business treats as authoritative before "
                f"{subject.lower()} figures are used for decisions."),
            "conflict_ids": [],
            "kind": "decision",
        })

    if reviews:
        named = []
        for subject, _row in reviews:
            if subject and subject not in named:
                named.append(subject)
        listed = (", ".join(named[:-1]) + " and " + named[-1]) if len(named) > 1 else (
            named[0] if named else "several measures")
        out.append({
            "insight_id": reviews[0][1].get("insight_id"),
            "trust": _worst_posture([r.get("trust", "") for _s, r in reviews]),
            "title": "Recording differences — review needed",
            "decision": (
                f"Source and ledger records differ for {listed.lower()}. Review the affected "
                f"records before relying on those figures."),
            "conflict_ids": [],
            # A recording problem is not a definition conflict, and the trust posture's own
            # label says "definitions conflict". Shown on this card it would tell the owner
            # the wrong thing about what is wrong.
            "kind": "review",
        })
    return tuple(out)
