"""
answer_renderer.py -- Phase 4. Deterministic answer construction, plus the guard that polices
what the LLM does with it.

Two objects, and the distinction between them is the whole safety design:

  * **The skeleton** is built deterministically from the Answer Contract. It contains every
    required field (metric_id, trust level, calculation, evidence, as-of, caveats, conflicts,
    validation status, confidence, limitations) and every number the answer is permitted to
    contain. It is complete and correct on its own -- if the LLM vanished, the skeleton would
    still be a valid answer.

  * **The verbalization** is the LLM's restatement of the skeleton. It is UNTRUSTED. It is
    checked by `guard()` before ever reaching a user, and rejected outright if it introduces a
    number, drops a caveat, produces a headline for a BLOCK metric, collapses a SHOW_BOTH
    family, omits the required NOT_DETERMINABLE phrase, or surfaces PII.

    "The natural-language renderer must not remove important caveats just to make the answer
     shorter."

  * **The owner draft** is a deterministic business-English restatement of the same facts,
    without metric IDs, DQ IDs, spec filenames, or Python dict dumps. If the LLM vanished, the
    owner draft is what the owner sees; the skeleton remains on RenderedAnswer.skeleton.

    A rejected verbalization is not retried into acceptance and is never partially used: the
    owner-facing deterministic draft is returned instead (the contract skeleton stays on
    RenderedAnswer.skeleton). Safety therefore does not depend on the model's cooperation.
"""
import re
from dataclasses import dataclass, field

from engine.result import NOT_DETERMINABLE_TEXT

# Columns excluded from the export as PII (data_inventory.md). No answer may contain a value
# for any of these, and no answer may claim to.
# NOTE on precision: terms here must not collide with ordinary accounting vocabulary. "bank
# account" was removed after it matched M.COL.003's own description ("cash inflow recognised in
# the ledger ... on the cash/bank accounts") -- a chart-of-accounts phrase, not personal data.
# "account number" and "ifsc" remain, since those name an identifier rather than a ledger.
PII_TERMS = (
    "phone", "mobile number", "email", "e-mail", "aadhaar", "aadhar", "pan number", "passport",
    "date of birth", "emergency contact", "guardian name", "ifsc", "account number",
    "home address", "residential address",
)

_NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")


@dataclass
class RenderedAnswer:
    question: str
    trust_level: str
    metric_ids: tuple
    skeleton: str                       # deterministic, contract-complete (engine/debug)
    text: str = ""                      # what the owner sees (verbalized, or the owner draft)
    verbalized: bool = False
    guard_violations: tuple = ()
    contract_fields: dict = field(default_factory=dict)
    reasoning_statements: tuple = ()
    clarification: object = None

    @property
    def safe(self):
        return not self.guard_violations or not self.verbalized


# --------------------------------------------------------------------------------------------
# Skeleton construction -- answer_contract.md 1's required fields, all of them.
# --------------------------------------------------------------------------------------------

def build_skeleton(plan, answers, reasoning=None):
    """Every field answer_contract.md 1 marks required. Nothing is summarised away here: the
    skeleton is the complete record, and abbreviation is the verbalizer's job -- under guard."""
    lines, fields = [], {}

    lines.append(f"QUESTION: {plan.question}")
    lines.append(f"TRUST POSTURE: {plan.trust_level}")
    fields["trust_level"] = plan.trust_level

    if plan.metric_ids:
        lines.append(f"METRIC PROVENANCE: {', '.join(plan.metric_ids)}")
        fields["metric_ids"] = list(plan.metric_ids)

    if plan.status == "NOT_DETERMINABLE":
        lines.append(f"RESULT: {NOT_DETERMINABLE_TEXT}")
        lines.append(f"REASON: {plan.not_determinable_reason}")
        fields["not_determinable"] = True
        return "\n".join(lines), fields

    if plan.status == "REJECTED":
        lines.append("RESULT: the requested analysis is not a valid plan.")
        for r in plan.rejection_reasons:
            lines.append(f"  - {r}")
        fields["rejected"] = True
        return "\n".join(lines), fields

    headline_permitted = plan.headline_permitted
    fields["headline_permitted"] = headline_permitted
    values = []

    for ans in answers:
        if ans.trust_level == "NOT_DETERMINABLE":
            lines.append(f"RESULT ({ans.metric_id}): {NOT_DETERMINABLE_TEXT}")
            lines.append(f"  REASON: {ans.not_determinable_reason}")
            continue

        if ans.blocked:
            lines.append(f"BLOCKED ({ans.metric_id}): no single figure may be stated.")
            lines.append(f"  WHY: {ans.blocked_reason}")

        for r in ans.results:
            label = "VALUE" if headline_permitted else "DEFINITION"
            lines.append(f"{label} [{r.metric_id} / {r.definition_label}]: {r.value} {r.unit}"
                         .rstrip())
            values.append(r.value)
            lines.append(f"  CALCULATION: {r.calculation_provenance[:300]}")
            lines.append(f"  EVIDENCE: {', '.join(str(e) for e in r.evidence_sources[:8])}")
            lines.append(f"  AS OF: {r.as_of}")
            lines.append(f"  VALIDATION: {r.validation_status}"
                         + (f" ({r.validation_reference[:160]})" if r.validation_reference else ""))
            lines.append(f"  CONFIDENCE: {r.confidence}")
            if r.limitations:
                lines.append(f"  LIMITATIONS: {r.limitations[:300]}")

        if ans.numeric_difference:
            for pair, diff in ans.numeric_difference.items():
                lines.append(f"  DIFFERENCE {pair}: {diff['absolute_difference']}"
                             + (f" ({diff['percentage_difference']}%)"
                                if diff.get("percentage_difference") is not None else ""))

        if ans.caveat:
            lines.append(f"MANDATORY CAVEAT [{ans.metric_id}]: {ans.caveat}")
            fields.setdefault("caveats", []).append(ans.caveat)
        if ans.conflict_ids:
            lines.append(f"CONFLICTS [{ans.metric_id}]: {', '.join(ans.conflict_ids)}")
            fields.setdefault("conflict_ids", []).extend(ans.conflict_ids)
        if ans.dq_ids:
            lines.append(f"DATA-QUALITY FINDINGS [{ans.metric_id}]: {', '.join(ans.dq_ids)}")
            fields.setdefault("dq_ids", []).extend(ans.dq_ids)
        if ans.follow_up:
            for f in ans.follow_up:
                lines.append(f"FOLLOW-UP AVAILABLE: {f}")

    if plan.time_note:
        lines.append(f"COVERAGE NOTE: {plan.time_note}")
    if plan.excluded_by_time:
        lines.append(f"EXCLUDED FOR THIS PERIOD: {', '.join(plan.excluded_by_time)}")

    if reasoning is not None:
        for s in reasoning.statements:
            if s.stage in ("OBSERVATION", "INFERENCE", "HYPOTHESIS", "RECOMMENDATION"):
                lines.append(f"{s.stage}: {s.text}"
                             + (f" [confidence: {s.confidence}]" if s.confidence else ""))
        for note in reasoning.dq_annotations:
            lines.append(f"DATA-QUALITY CHECK: {note}")

    fields["values"] = values
    return "\n".join(lines), fields


# --------------------------------------------------------------------------------------------
# The guard -- validates the LLM's verbalization against the skeleton.
# --------------------------------------------------------------------------------------------

def _numbers_in(text):
    out = set()
    for m in _NUMBER.finditer(text or ""):
        tok = m.group(0).replace(",", "").rstrip(".")
        if not tok or tok in ("-",):
            continue
        try:
            out.add(round(float(tok), 2))
        except ValueError:
            continue
    return out


def _owner_label_key(label):
    """The part of a definition label that survives into owner prose, lowercased.

    Sanitization removes database object names, so the raw label and the owner-visible label
    differ. This produces the owner-visible form so the guard compares like with like.
    """
    from engine import owner_presentation
    cleaned = owner_presentation.owner_definition_label(label).lower().strip()
    return cleaned[:18]


def guard_workflow(verbalized, draft):
    """Guard a verbalization of a whole-business workflow answer (briefing, what changed, what
    to do, what to trust).

    Same contract as `guard()`, expressed against the deterministic OWNER DRAFT because a
    workflow answer has no single plan or metric result to check against. The draft is what the
    engine computed, so it is the source of truth exactly as the skeleton is for a metric answer.

    What this refuses:
      * any number that is not already in the draft -- the model may not compute
      * the internal identifiers, spec filenames and dict dumps the draft never contained
      * PII, on the same terms as the metric guard
      * dropping the exact NOT_DETERMINABLE sentence when the draft carried it
      * inventing materiality, a cause, or a benchmark the draft did not state
    """
    from engine import owner_presentation

    v = []
    text = verbalized or ""
    low = text.lower()

    if not text.strip():
        return ("verbalization is empty",)

    # 1. No new numbers. The draft already holds every figure the engine computed.
    draft_nums = _numbers_in(draft)
    for n in _numbers_in(text):
        if n in draft_nums:
            continue
        if float(n).is_integer() and 0 <= n <= 3000:
            continue            # counts, years and list ordinals
        v.append(f"verbalization introduces the number {n}, which is not in the draft")

    # 2. Nothing internal. The draft is already sanitized, so anything the sanitizer would
    #    remove is something the model added.
    if owner_presentation.sanitize_owner_text(text) != text.strip():
        for pattern, what in ((owner_presentation._METRIC_ID, "a metric ID"),
                              (owner_presentation._DQ_ID, "a data-quality ID"),
                              (owner_presentation._CONFLICT_ID, "a conflict ID"),
                              (owner_presentation._INSIGHT_ID, "an insight ID"),
                              (owner_presentation._SPEC_FILE, "a specification filename"),
                              (owner_presentation._DB_OBJECT, "a database object name"),
                              (owner_presentation._DICT_DUMP, "a raw data dump")):
            if pattern.search(text):
                v.append(f"verbalization exposes {what} to the owner")

    # 3. The exact refusal sentence survives when the draft made it.
    if NOT_DETERMINABLE_TEXT in draft and NOT_DETERMINABLE_TEXT not in text:
        v.append(f"verbalization omits the required phrase {NOT_DETERMINABLE_TEXT!r}")

    # 4. No invented judgement. The specifications fix no materiality threshold, so a claim
    #    that a movement is significant is a fabrication however confidently it is phrased.
    for phrase in ("significant", "significantly", "material increase", "material decline",
                   "materially", "worryingly", "alarmingly", "dramatic", "sharp decline",
                   "healthy margin", "industry standard", "benchmark", "above average",
                   "below average", "underperform", "outperform"):
        if phrase in low and phrase not in draft.lower():
            v.append(f"verbalization asserts a judgement the evidence does not support "
                     f"({phrase!r})")

    # 5. No invented causation. Causes come from the documented dependency graph, never from
    #    the wording layer noticing two things moved together.
    for phrase in ("because of", "caused by", "due to the", "driven by", "as a result of",
                   "this is why", "the reason is"):
        if phrase in low and phrase not in draft.lower():
            v.append(f"verbalization asserts a cause the evidence does not support "
                     f"({phrase!r})")

    # 6. No PII.
    for term in PII_TERMS:
        if term in low:
            v.append(f"verbalization references PII ({term!r}); 27 PII columns are excluded "
                     f"from the export and no answer may surface or imply them")
            break

    return tuple(v)


# A narrative is a few sentences. Anything shorter says nothing; anything longer is not the
# requested shape and is more surface for an unsupported claim.
NARRATIVE_MIN_CHARS = 40
NARRATIVE_MAX_CHARS = 1200

# Causal wording the narrative may use only where the facts themselves carry it. Matched as
# phrases or whole words, so "because" is refused but "cause" inside another word is not.
_NARRATIVE_CAUSAL = (r"\bbecause\b", r"\bdriven by\b", r"\bdrove\b", r"\bcaused\b",
                     r"\bcausing\b", r"\bdue to\b", r"\bas a result of\b", r"\bled to\b",
                     r"\bleads to\b", r"\bresulted in\b", r"\bresponsible for\b",
                     r"\bthanks to\b", r"\bowing to\b", r"\bthe reason\b",
                     r"\bresulted from\b", r"\bexplained by\b", r"\baccounted for by\b")


# A judgement of size or importance. The facts carry materiality only as an open question, so a
# sentence that ANSWERS it -- "a significant increase", "a small dip" -- is the model deciding.
# Sentences that keep the question open ("whether ... is significant") are exempt.
_NARRATIVE_JUDGEMENT = (
    r"\bsignificant(?:ly)?\b",
    r"\b(?:large|small|big|huge|modest|slight|sharp|strong|weak|healthy|worrying|concerning|impressive|substantial|notable|dramatic|minor|major|marginal) (?:increase|decrease|rise|fall|drop|growth|movement|change|jump|decline|dip|gain|loss)\b",
)
_OPEN_QUESTION_MARKERS = ("whether", "not set by the records", "owner judgement",
                          "not determinable")


# Scaffolding the narrative framework itself could leak: the facts contract's field names, the
# sentence-plan labels the prompt uses, and the prompt's own headings. Targeted to this framework's
# vocabulary, so ordinary owner prose ("the change is reconciled across ...") is untouched.
_NARRATIVE_SCAFFOLDING = (
    r"\b(?:components|caveats|materiality|causal_evidence|movement|metric)\.(?:lead|meaning|items|specific|posture|statement|direction|change|name)\b",
    r"\b(?:causal_evidence|must_include|deterministic_answer|narrative_facts|trust_level|owner_status|change_pct|partial_period|metric_why)\b",
    r"\bcomponents lead\b",
    r"\b(?:materiality|causal[ _-]evidence|components?|caveats?) statement\b",
    r"\b(?:materiality|causal[ _-]evidence|components?|caveats?|posture|specific caveats?)\s*:",
    r"(?:authoritative json|\btrust level\s*:|\breminder\s*:|\bfacts\s*\()",
    r'"[a-z_]+"\s*:',
)


def _fact_strings(value):
    """Every string leaf in the facts, in order. The source a narrative may draw on."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _fact_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _fact_strings(item)
    elif isinstance(value, str):
        yield value


def guard_metric_narrative(text, facts, draft, other_measure_names=()):
    """Check a Local LLM narrative against the facts it was given and the deterministic answer.

    Returns a tuple of violations; empty means the narrative may replace the answer. It composes
    `guard_workflow` -- no new numbers, nothing internal, the refusal sentence kept, no invented
    judgement or cause, no PII -- and adds what a single-measure narrative also owes: the
    measure named, no other measure named, the posture respected, the caveat kept, a sane length.
    """
    from engine import owner_presentation

    facts = facts or {}
    narrative = (text or "").strip()
    if not narrative:
        return ("narrative is empty",)

    source = "\n".join([draft or ""] + list(_fact_strings(facts)))
    # A figure the facts carry with a sign may be written without one, or with an ASCII minus,
    # and still be the same recorded figure. Both spellings are admitted; nothing else is.
    signed = " ".join(f"{n} {-n}" for n in _numbers_in(source))
    violations = list(guard_workflow(narrative, source + "\n" + signed))

    low = narrative.lower()
    source_low = source.lower()

    if len(narrative) < NARRATIVE_MIN_CHARS or len(narrative) > NARRATIVE_MAX_CHARS:
        violations.append(f"narrative length {len(narrative)} is outside "
                          f"{NARRATIVE_MIN_CHARS}-{NARRATIVE_MAX_CHARS} characters")

    # Internal identifiers, stated explicitly even though the workflow guard covers them when the
    # sanitizer would change the text.
    if owner_presentation._METRIC_ID.search(narrative):
        violations.append("narrative exposes a metric ID")
    for pattern, what in ((owner_presentation._SPEC_FILE, "a file name"),
                          (owner_presentation._DB_OBJECT, "a database object name")):
        if pattern.search(narrative):
            violations.append(f"narrative exposes {what}")

    for sentence in facts.get("must_include") or ():
        if sentence and sentence not in narrative:
            violations.append(f"narrative omits the required sentence {sentence!r}")

    for sentence in re.split(r"(?<=[.!?])\s+", low):
        if any(marker in sentence for marker in _OPEN_QUESTION_MARKERS):
            continue
        for pattern in _NARRATIVE_JUDGEMENT:
            if re.search(pattern, sentence):
                violations.append(f"narrative judges the movement's size or importance "
                                  f"({pattern!r})")
                break

    for pattern in _NARRATIVE_SCAFFOLDING:
        if re.search(pattern, low):
            violations.append(f"narrative contains framework scaffolding or a field label "
                              f"({pattern!r})")
            break

    for pattern in _NARRATIVE_CAUSAL:
        if re.search(pattern, low) and not re.search(pattern, source_low):
            violations.append(f"narrative asserts a cause the facts do not state ({pattern!r})")

    metric = facts.get("metric") or {}
    name = (metric.get("name") or "").strip()
    trust = (metric.get("trust_level") or "").upper()

    if name and name.lower() not in low:
        violations.append("narrative does not name the measure it explains")

    # The verified context the deterministic answer carries. A narrative that replaces that answer
    # may re-word it, never thin it: where the facts hold the periods, the values, the change and
    # its percentage, each must still be there. Figures are matched on their digits, so a sign or
    # currency symbol written differently is not read as a missing figure.
    movement = facts.get("movement") or {}
    if movement.get("available"):
        def digits(value):
            return re.sub(r"[^0-9.,]", "", value or "").strip(".,")
        required = [
            ("previous period", (movement.get("previous") or {}).get("period")),
            ("previous value", digits((movement.get("previous") or {}).get("value"))),
            ("current period", (movement.get("current") or {}).get("period")),
            ("current value", digits((movement.get("current") or {}).get("value"))),
            ("change", digits(movement.get("change"))),
            ("percentage change", movement.get("change_pct")),
        ]
        for what, needle in required:
            if needle and needle.lower() not in low:
                violations.append(f"narrative drops the verified {what}")

    # Where the facts carry a reconciliation, every part that moved is named with its amount. A
    # part that did not move is not required, and a part the facts do not list cannot be required.
    components = facts.get("components") or {}
    if components.get("available"):
        for item in components.get("items") or ():
            if not item.get("required"):
                continue
            label = (item.get("label") or "").strip()
            amount = re.sub(r"[^0-9.,]", "", item.get("amount") or "").strip(".,")
            if label and label.lower() not in low:
                violations.append(f"narrative does not name the component {label!r}")
            elif amount and amount not in narrative:
                violations.append(f"narrative drops the amount of the component {label!r}")

    # Specific caveats are required, whatever the posture: each is a limitation the owner needs to
    # read this movement, sourced from the engine's evidence rather than from the posture's
    # general sentence.
    for caveat in ((facts.get("caveats") or {}).get("specific") or ()):
        text_of = (caveat.get("text") if isinstance(caveat, dict) else caveat) or ""
        if text_of and not _caveat_survives(text_of, narrative):
            violations.append("narrative drops a specific caveat")

    # The two statuses the facts decide. Neither may be dropped when the narrative replaces the
    # verified answer: that the records leave significance to the owner, and that they do not show
    # why the movement happened.
    if movement.get("available"):
        if not any(marker in low for marker in ("not set by the records", "owner judgement",
                                                "owner judgment")):
            violations.append("narrative drops the materiality status")
        if "not show why" not in low:
            violations.append("narrative drops the causal-evidence status")

    # Other measures: a name the facts do not carry is a measure the narrative wandered into.
    # The facts' own names are removed first, so "Revenue" inside "Revenue by month" is not read
    # as a second measure.
    allowed = {name.lower()} | {(d.get("name") or "").lower()
                                for d in facts.get("drivers") or ()}
    allowed |= {(c.get("label") or "").lower()
                for c in (facts.get("components") or {}).get("items") or ()}
    scrubbed = low
    for known in sorted((a for a in allowed if a), key=len, reverse=True):
        scrubbed = scrubbed.replace(known, " ")
    for other in other_measure_names or ():
        key = (other or "").strip().lower()
        if key and key not in allowed and re.search(r"\b" + re.escape(key) + r"\b", scrubbed):
            violations.append(f"narrative names another measure ({other!r})")

    if trust in ("SHOW_BOTH", "BLOCK"):
        if not any(w in low for w in ("competing", "definition", "no single", "conflict",
                                      "disagree", "blocked")):
            violations.append(f"{trust} narrative does not say the definitions compete")
    if trust == "NOT_DETERMINABLE" and NOT_DETERMINABLE_TEXT not in narrative:
        violations.append("NOT_DETERMINABLE narrative omits the required sentence")
    caveat = metric.get("caveat") or ""
    if trust == "DISCLOSE" and caveat and not _caveat_survives(caveat, narrative):
        violations.append("DISCLOSE narrative drops the caveat")

    return tuple(violations)


def guard(verbalized, skeleton, plan, answers):
    """Check an LLM verbalization against the deterministic skeleton. Returns a tuple of
    violations; empty means the verbalization may be shown to the user."""
    v = []
    text = verbalized or ""
    low = text.lower()

    if not text.strip():
        return ("verbalization is empty",)

    # 1. No new numbers. Every figure must already be in the skeleton. Years and small
    #    ordinals are excluded -- they are prose, not claims about the business.
    skeleton_nums = _numbers_in(skeleton)
    for n in _numbers_in(text):
        if n in skeleton_nums:
            continue
        if float(n).is_integer() and 0 <= n <= 3000:
            continue        # counts, years, list ordinals already present as context
        v.append(f"verbalization introduces the number {n}, which is not in the skeleton")

    # 2. BLOCK must not carry a headline figure.
    if plan.trust_level == "BLOCK":
        if not any(w in low for w in ("cannot", "conflict", "disagree", "no single",
                                      "not possible", "blocked", "competing")):
            v.append("BLOCK answer does not explain why no single figure can be given")
        labels = [_owner_label_key(r.definition_label) for a in answers for r in a.results]
        present = sum(1 for lab in labels if lab and lab in low)
        if labels and present < 2:
            v.append("BLOCK answer does not present the competing definitions separately")

    # 3. SHOW_BOTH must not collapse.
    if plan.trust_level == "SHOW_BOTH":
        labels = [_owner_label_key(r.definition_label) for a in answers for r in a.results]
        shown = sum(1 for lab in labels if lab and lab in low)
        if shown < min(2, len(labels)):
            v.append(f"SHOW_BOTH answer presents {shown} of {len(labels)} competing "
                     f"definitions -- it must present all of them")
        for phrase in ("the real number is", "the correct figure is", "the true occupancy",
                       "we should use", "the actual profit is", "best estimate"):
            if phrase in low:
                v.append(f"SHOW_BOTH answer picks a winner ({phrase!r})")

    # 4. NOT_DETERMINABLE must use the exact phrase.
    nd = (plan.status == "NOT_DETERMINABLE"
          or all(a.trust_level == "NOT_DETERMINABLE" for a in answers) and answers)
    if nd and NOT_DETERMINABLE_TEXT not in text:
        v.append(f"NOT_DETERMINABLE answer omits the required phrase {NOT_DETERMINABLE_TEXT!r}")
    if nd:
        for phrase in ("approximately", "roughly", "estimate", "about rs", "in the region of",
                       "ballpark"):
            if phrase in low:
                v.append(f"NOT_DETERMINABLE answer offers an estimate ({phrase!r})")

    # 5. Mandatory caveats survive.
    for ans in answers:
        if ans.trust_level == "DISCLOSE" and ans.caveat:
            if not _caveat_survives(ans.caveat, text):
                v.append(f"mandatory caveat for {ans.metric_id} was dropped from the "
                         f"verbalization")

    # 6. Evidence references survive on the skeleton, not in owner prose. Metric IDs, DQ IDs,
    #    and file names belong on RenderedAnswer.skeleton / the evidence chain. Requiring them
    #    in the verbalization forced internal identifiers into the owner-facing answer.

    # 7. No PII may be surfaced or promised.
    for term in PII_TERMS:
        if term in low:
            v.append(f"verbalization references PII ({term!r}); 27 PII columns are excluded "
                     f"from the export and no answer may surface or imply them")
            break

    return tuple(v)


def _caveat_survives(caveat, text):
    """A caveat need not be quoted verbatim -- ai_evaluation_framework.md 1.2 permits "an
    equivalent faithful paraphrase" -- but its CONTENT must not be dropped. Approximated by
    requiring a reasonable share of the caveat's distinctive words to appear."""
    words = [w for w in re.findall(r"[a-z_]{5,}", caveat.lower())]
    if not words:
        return True
    low = text.lower()
    hits = sum(1 for w in set(words) if w in low)
    return hits >= max(2, len(set(words)) // 6)


def render(plan, answers, reasoning=None, verbalized=None, question=""):
    """Assemble the final answer. If a verbalization is supplied and passes the guard, it is
    used; otherwise the deterministic owner draft is returned and the violations are recorded.
    The contract-complete skeleton is always retained on RenderedAnswer.skeleton."""
    from engine import owner_presentation

    skeleton, fields = build_skeleton(plan, answers, reasoning)
    owner_draft = owner_presentation.present_metric_answer(plan, answers, reasoning)

    out = RenderedAnswer(
        question=question or plan.question, trust_level=plan.trust_level,
        metric_ids=tuple(plan.metric_ids), skeleton=skeleton, text=owner_draft,
        contract_fields=fields,
        reasoning_statements=reasoning.statements if reasoning else (),
    )

    if verbalized is not None:
        violations = guard(verbalized, skeleton, plan, answers)
        if violations:
            out.guard_violations = violations
            out.text = owner_draft       # fall back; never partially use a bad verbalization
            out.verbalized = False
        else:
            out.text = owner_presentation.sanitize_owner_text(verbalized)
            out.verbalized = True

    return out
