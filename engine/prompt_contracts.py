"""
prompt_contracts.py -- Phase 4. The prompts, and the rules embedded in them.

A prompt is a REQUEST for cooperation, never a guarantee of it. Everything stated here is also
enforced downstream in code (structured_output.py validates extraction; answer_renderer.py's
guard validates verbalization), so a model that ignores these instructions produces a rejected
plan or a discarded verbalization -- not an unsafe answer. The prompts exist to make the
cooperative path easy, not to be the safety mechanism.

The allowed vocabulary is generated FROM the semantic layer at prompt-build time, so a metric
added to or removed from semantic_metric_registry.csv changes the prompt automatically and the
prompt can never advertise a metric the validator would reject.
"""
import json

from engine.semantic_registry import SemanticRegistry
from engine import concept_map
from engine.dimension_resolver import KNOWN_DIMENSIONS, DEGENERATE_DIMENSIONS
from engine.intent_models import ALL_INTENTS
from engine import structured_output


EXTRACTION_SYSTEM = """\
You are the question-understanding stage of a business analytics system. Your ONLY job is to \
translate a natural-language question into a strict JSON object drawn from a fixed vocabulary.

You do NOT compute anything. You do NOT have access to any data. You never see a number, and \
you never produce one. A separate deterministic engine performs every calculation.

Hard rules:
  * Use ONLY the concept names, metric_ids, dimensions and intents listed below. If the \
question does not correspond to any of them, set "concept" to null and "clarification_needed" \
to true. Never invent a metric, a table, a column, or a business definition.
  * Never emit SQL, a file name, or a raw table/column name. There is no field for one.
  * If the question could mean two genuinely different things, set "clarification_needed": true \
and say why. Do NOT pick the more convenient interpretation.
  * For a concept marked FAMILY below, list the WHOLE family in metric_ids or leave metric_ids \
empty. Never select one member of a family.
  * Reply with the JSON object and nothing else.
"""

# Kept deliberately terse. Every call carries this, and measured on a local CPU model the
# verbalization latency tracks total input size steeply -- so each character of standing
# instruction is paid for on every question the owner asks. No rule was dropped in shortening
# it, and the guard enforces all of them regardless of what the prompt says.
VERBALIZATION_SYSTEM = """\
VERBALIZE. Restate this engine draft as short, clear business English for a business owner.

Rules:
  * Use ONLY numbers that already appear in the draft. Never compute, estimate, or round.
  * Never drop a caveat, conflict, limitation, or competing definition.
  * Present EVERY competing definition the draft lists, each with its label. Never pick a \
winner, average them, or call one "the real" figure.
  * If the draft states no single figure can be given, state no headline figure.
  * If the draft contains "Not determinable from exported evidence.", reproduce it verbatim.
  * No personal information about any individual.
  * No metric IDs, DQ IDs, conflict IDs, SQL, formulas, file names, table or column names, or \
raw dictionaries.
  * Do not change the trust posture. Do not invent materiality, causes, recommendations, or \
benchmarks.
"""


def _concept_catalogue(registry):
    lines = []
    for c in concept_map.all_concepts():
        tag = "FAMILY" if c.is_family else "single"
        if not c.is_family and len(c.metric_ids) > 1:
            tag = "AMBIGUOUS (distinct metrics -- must ask, never pick)"
        names = "; ".join(f"{m} = {registry.get(m).semantic_name}" for m in c.metric_ids)
        lines.append(f"  - {c.name} [{tag}]: {names}")
    return "\n".join(lines)


def build_extraction_prompt(question, registry: SemanticRegistry = None, context_note=""):
    registry = registry or SemanticRegistry()
    schema = json.dumps(structured_output.json_schema(), indent=2)

    degenerate = ", ".join(sorted(DEGENERATE_DIMENSIONS))
    parts = [
        "ALLOWED CONCEPTS (the only business concepts that exist in this system):",
        _concept_catalogue(registry),
        "",
        f"ALLOWED DIMENSIONS: {', '.join(sorted(KNOWN_DIMENSIONS))}",
        f"NOTE: {degenerate} each have exactly ONE value in this dataset, so no comparison "
        f"across them is possible.",
        "",
        f"ALLOWED INTENTS: {', '.join(ALL_INTENTS)}",
        "",
        "OUTPUT SCHEMA (reply with exactly this shape, no extra fields):",
        schema,
    ]
    if context_note:
        parts += ["", "CONVERSATION CONTEXT (use only to resolve references the question "
                      "leaves implicit; an explicit value in the question always wins):",
                  context_note]
    parts += ["", f"USER QUESTION: {question}"]
    return "\n".join(parts)


def build_repair_prompt(question, previous_output, violations, registry=None):
    """One bounded repair attempt. The violations are stated plainly so a cooperative model can
    correct a malformed response -- but a violation of the SEMANTIC vocabulary (an invented
    metric) is never sent for repair, because re-prompting cannot make a nonexistent metric
    exist (see structured_output.ValidationOutcome.repairable)."""
    return "\n".join([
        "Your previous response did not satisfy the contract.",
        "",
        "PREVIOUS RESPONSE:",
        (previous_output or "")[:2000],
        "",
        "CONTRACT VIOLATIONS:",
        *(f"  - {v}" for v in violations),
        "",
        "Reply again with a single valid JSON object obeying the schema. If the question "
        "cannot be expressed within the allowed vocabulary, return "
        '{"intent": ["lookup"], "clarification_needed": true, "clarification_reason": "..."} '
        "rather than inventing a value.",
        "",
        f"USER QUESTION: {question}",
    ])


METRIC_WHY_NARRATIVE_SYSTEM = """\
NARRATE. You explain one measure's recorded movement to a business owner, in plain English.

The JSON facts you receive are authoritative. You are the wording layer only.

Rules:
  * Use ONLY the facts and strings supplied in the JSON. Copy every figure exactly as written, \
including its currency symbol and sign.
  * Do not calculate, round, convert or otherwise transform any number. Do not introduce any \
numeric value that is not already written in the JSON.
  * "components" reconcile the movement: they show how the change is distributed. They are NOT \
causal evidence and NOT drivers. Use "components.meaning" for how to describe them.
  * Never use these words or phrases, or any equivalent: "because", "because of", "driven by", \
"caused by", "led to", "resulted from", "due to", "as a result of", "explained by", \
"accounted for by". The records establish no cause for this movement.
  * Do not judge materiality. Never call the movement significant, large, small, healthy, \
worrying or similar. Keep the JSON's materiality statement's meaning.
  * If "must_include" lists a sentence, end your answer with that exact sentence, character for \
character, including the final full stop.
  * Keep the meaning of every limitation.
  * Respect the trust level: SAFE states the figures; DISCLOSE states the figures AND the \
caveat; SHOW_BOTH and BLOCK never give a single figure; NOT_DETERMINABLE gives no figure and \
explains what is missing.
  * Never mention internal IDs, file names, table or column names, database objects, code, \
formulas or how the system works.
  * Do not make recommendations. Do not mention any other measure than the ones named in the JSON.
  * Refer to the measure by the exact name in metric.name, as the subject of the first \
sentence. Do not write "the recorded movement of" or put "The" before the measure name.

Write the answer in this order, using only the parts that are present in the JSON:
  1. What moved: "<metric.name> <movement.direction> from <movement.previous.value> in \
<movement.previous.period> to <movement.current.value> in <movement.current.period>, a change of \
<movement.change> (<movement.change_pct>)."
  2. The components, if components.available is true, in ONE sentence that starts with \
components.lead and names every item whose "required" is true, each as "<label> <direction> by \
<amount>", joined naturally (for example with "while" and "and"). Then components.meaning.
  3. The materiality statement (materiality.statement).
  4. The causal-evidence statement (causal_evidence.statement) ONLY if components.available is \
false. When components are shown, components.meaning already says this; do not repeat it.
  5. The must_include sentence, last, exactly as written.

Output: 3 to 6 short plain-text sentences. No headings, no markdown, no lists, no JSON, no \
preamble.
"""


def build_metric_why_prompt(facts):
    """The facts, and nothing else the model could mistake for evidence.

    The deterministic answer is left out on purpose: it is the fallback, and handing the model
    a finished paragraph invites it to paraphrase that paragraph's wording instead of narrating
    the facts. It is still what the guard checks the narrative against.
    """
    shown = {k: v for k, v in (facts or {}).items() if k != "deterministic_answer"}
    return "\n".join([
        f"TRUST LEVEL: {shown.get('metric', {}).get('trust_level', '')}",
        "",
        "FACTS (authoritative JSON):",
        json.dumps(shown, ensure_ascii=False, indent=2),
        "",
        "Reminder: keep the periods and values, the change and its percentage. Name every "
        "component whose required is true, with its direction and amount. The components "
        "reconcile the movement; they are not causes. Do not say what drove, caused or explains "
        "the movement, and do not repeat the same point twice.",
    ] + ([f"End with exactly: {' '.join(shown.get('must_include') or [])}"]
         if shown.get("must_include") else []))


def build_verbalization_prompt(skeleton_text, trust_level, question):
    """The skeleton is the source of truth. It is passed in full, and the trust level is
    restated at the top so the constraint is adjacent to the content it governs."""
    rules = {
        "SAFE": "Present the figure in business English. Do not include metric IDs, file names, "
                "SQL, or registry names.",
        "DISCLOSE": "Present the figure AND its caveat in business English. The caveat is "
                    "mandatory -- never omit or soften it. Do not include internal IDs.",
        "SHOW_BOTH": "Present EVERY competing definition, clearly labelled, with the numeric "
                     "difference between them. You may explain why they differ. You may NOT "
                     "choose one, average them, or imply one is correct.",
        "BLOCK": "Do NOT state a single headline figure. Explain why no single figure can be "
                 "given, then list the competing definitions the draft lists, keeping each "
                 "one's label ('Def A', 'Def B', ...) exactly as the draft writes it, on its "
                 "own line, with its figure. Keep any next step already in the draft. Do not "
                 "invent a recommendation.",
        "NOT_DETERMINABLE": 'State exactly: "Not determinable from exported evidence." Then '
                            "explain specifically what is missing, in owner language. Do not "
                            "estimate.",
        "SHOW_BOTH_FAMILY": (
            "List every competing definition on its own line, keeping each label ('Def A', "
            "'Def B', ...) exactly as the draft writes it, with its figure. Be brief: one "
            "line each, no commentary. Do not choose one, average them, or imply one is "
            "correct."),
        "WORKFLOW": (
            "Keep the draft's headings and order. Be brief. Copy every figure exactly, "
            "including its currency symbol. Keep every caveat and every contested measure. "
            "Do not rank, score, or call anything significant. If the draft contains the "
            'sentence "Not determinable from exported evidence.", reproduce it verbatim.'),
    }.get(trust_level, "Present only what the draft contains.")

    return "\n".join([
        f"TRUST LEVEL: {trust_level}",
        f"RULE FOR THIS TRUST LEVEL: {rules}",
        "",
        f"USER QUESTION: {question}",
        "",
        "ANSWER SKELETON",
        skeleton_text,
    ])


def verify_prompt_vocabulary(registry: SemanticRegistry = None):
    """Guard: the prompt must never advertise a symbol the validator would reject. Returns
    problems (empty = prompt and validator agree)."""
    registry = registry or SemanticRegistry()
    problems = []
    prompt = build_extraction_prompt("test", registry)
    for c in concept_map.all_concepts():
        if c.name not in prompt:
            problems.append(f"concept {c.name!r} is not advertised in the extraction prompt")
        for mid in c.metric_ids:
            if mid not in registry:
                problems.append(f"prompt advertises unknown metric_id {mid!r}")
    schema = structured_output.json_schema()
    for name in schema["properties"]["concept"]["enum"]:
        if concept_map.concept(name) is None:
            problems.append(f"schema advertises unknown concept {name!r}")
    for dim in schema["properties"]["dimensions"]["items"]["enum"]:
        if dim not in KNOWN_DIMENSIONS:
            problems.append(f"schema advertises uncatalogued dimension {dim!r}")
    return problems
