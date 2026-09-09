"""
structured_output.py -- Phase 4. The strict machine-readable contract between the LLM and the
deterministic engine.

    "Validate this object before execution. If invalid:
     LLM output -> validation failure -> no execution -> repair/clarification.
     Never execute an invalid plan."

Everything an LLM returns is treated as UNTRUSTED TEXT. This module is the only place that text
crosses into the deterministic system, and it crosses only as a set of already-known symbols:

  * `metric_ids`  must exist in semantic_metric_registry.csv
  * `concept`     must exist in concept_map.py
  * `dimensions`  must exist in business_dimensions.md (via dimension_resolver.KNOWN_DIMENSIONS)
  * `intent`      must be one of question_understanding_spec.md 2's catalogued intents
  * every other field is a bounded enum or a plain string that is re-parsed deterministically

There is no field through which a model can pass a table name, a column name, a SQL fragment, a
filter expression, or a numeric value. That is the structural reason the LLM cannot invent a
metric, query a CSV, or perform its own arithmetic -- not a prompt instruction it might ignore,
but the absence of any channel that would carry such a thing.
"""
import json
import re
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine import concept_map
from engine.dimension_resolver import KNOWN_DIMENSIONS
from engine.intent_models import ALL_INTENTS

REQUESTED_OUTPUTS = ("value", "explanation", "diagnosis", "recommendation", "summary")

# Fields the contract accepts. Anything else in the model's JSON is a contract violation, not
# an extra to be ignored: an unexpected key is evidence the model is trying to do something the
# contract does not describe.
ALLOWED_KEYS = {
    "intent", "concept", "metric_ids", "dimensions", "filters", "time_range", "comparison",
    "requested_output", "explanation_requested", "recommendation_requested",
    "clarification_needed", "clarification_reason",
}

# Patterns that must never appear in any free-text field. A model attempting to smuggle a query
# through `time_range` or `clarification_reason` is refused outright rather than sanitised.
_INJECTION_PATTERNS = (
    re.compile(r"\bselect\b.+\bfrom\b", re.I),
    re.compile(r"\b(insert|update|delete|drop|alter|truncate|union)\b\s", re.I),
    re.compile(r"--\s*$"),
    re.compile(r"/\*.*\*/", re.S),
    re.compile(r"\.csv\b", re.I),
    re.compile(r"\bjournal_lines\b|\bcoa_accounts\b|\btenant_transactions\b", re.I),
)

MAX_FREE_TEXT = 300


@dataclass(frozen=True)
class LLMPlanRequest:
    """The validated contract object. Construction is only possible via `parse_and_validate`,
    so an instance is by definition already checked against the semantic layer."""
    intent: tuple
    concept: str = ""
    metric_ids: tuple = ()
    dimensions: tuple = ()
    filters: dict = field(default_factory=dict)
    time_range: str = ""
    comparison: str = ""
    requested_output: str = "value"
    explanation_requested: bool = False
    recommendation_requested: bool = False
    clarification_needed: bool = False
    clarification_reason: str = ""
    raw: str = ""

    def as_dict(self):
        return {
            "intent": list(self.intent), "concept": self.concept,
            "metric_ids": list(self.metric_ids), "dimensions": list(self.dimensions),
            "filters": dict(self.filters), "time_range": self.time_range,
            "comparison": self.comparison, "requested_output": self.requested_output,
            "explanation_requested": self.explanation_requested,
            "recommendation_requested": self.recommendation_requested,
            "clarification_needed": self.clarification_needed,
            "clarification_reason": self.clarification_reason,
        }


@dataclass
class ValidationOutcome:
    request: object = None          # LLMPlanRequest, or None when invalid
    violations: tuple = ()
    repairable: bool = False        # whether a repair prompt is worth attempting

    @property
    def valid(self):
        return self.request is not None and not self.violations


def _strip_code_fence(text):
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _find_json(text):
    """Models sometimes wrap JSON in prose. Extract the first balanced object rather than
    failing outright -- but never 'fix' the JSON's CONTENT, only locate it."""
    t = _strip_code_fence(text)
    try:
        return json.loads(t)
    except (json.JSONDecodeError, TypeError):
        pass
    start = t.find("{")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _check_free_text(value, field_name, violations):
    if not isinstance(value, str):
        violations.append(f"{field_name}: expected a string, got {type(value).__name__}")
        return ""
    if len(value) > MAX_FREE_TEXT:
        violations.append(f"{field_name}: exceeds {MAX_FREE_TEXT} characters")
        return ""
    for pat in _INJECTION_PATTERNS:
        if pat.search(value):
            violations.append(
                f"{field_name}: contains a query fragment or raw table/file reference. The "
                f"contract carries no channel for SQL, table names, or file paths -- the model "
                f"may name a metric_id and nothing else.")
            return ""
    return value.strip()


def parse_and_validate(text, registry: SemanticRegistry = None) -> ValidationOutcome:
    """The single gate. Returns a ValidationOutcome; `request` is None whenever ANY violation
    was found. A partially-valid object is never returned, because a caller holding one would
    be one forgotten check away from executing it."""
    registry = registry or SemanticRegistry()
    violations = []

    data = _find_json(text)
    if data is None:
        return ValidationOutcome(
            None, ("model output is not valid JSON and contains no balanced JSON object",),
            repairable=True)
    if not isinstance(data, dict):
        return ValidationOutcome(
            None, (f"model output parsed to {type(data).__name__}, expected an object",),
            repairable=True)

    unknown = set(data) - ALLOWED_KEYS
    if unknown:
        violations.append(
            f"unexpected field(s) {sorted(unknown)}: the contract is closed, and an unlisted "
            f"field is evidence of an action the contract does not describe")

    # --- intent ---------------------------------------------------------------------------
    raw_intent = data.get("intent", [])
    if isinstance(raw_intent, str):
        raw_intent = [raw_intent]
    if not isinstance(raw_intent, list) or not raw_intent:
        violations.append("intent: required, must be a non-empty list of catalogued intents")
        raw_intent = []
    intents = []
    for i in raw_intent:
        if not isinstance(i, str) or i not in ALL_INTENTS:
            violations.append(
                f"intent {i!r} is not one of question_understanding_spec.md 2's intents "
                f"{list(ALL_INTENTS)}")
        else:
            intents.append(i)

    # --- concept --------------------------------------------------------------------------
    concept = data.get("concept") or ""
    if concept:
        if not isinstance(concept, str):
            violations.append("concept: must be a string")
            concept = ""
        elif concept_map.concept(concept) is None:
            violations.append(
                f"concept {concept!r} is not in the concept map. The model may not introduce a "
                f"business concept the semantic layer does not already define "
                f"(ai_analytics_architecture.md 8).")
            concept = ""

    # --- metric_ids -----------------------------------------------------------------------
    raw_ids = data.get("metric_ids", [])
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    if not isinstance(raw_ids, list):
        violations.append("metric_ids: must be a list")
        raw_ids = []
    metric_ids = []
    for mid in raw_ids:
        if not isinstance(mid, str):
            violations.append(f"metric_id {mid!r}: must be a string")
        elif mid not in registry:
            violations.append(
                f"metric_id {mid!r} does not exist in semantic_metric_registry.csv. The model "
                f"may not invent a metric.")
        else:
            metric_ids.append(mid)

    # A model that names a concept AND metric_ids must not contradict itself -- that would be a
    # silent reinterpretation of the concept.
    if concept and metric_ids:
        c = concept_map.concept(concept)
        allowed = set(c.metric_ids) | set(c.alternatives)
        stray = [m for m in metric_ids if m not in allowed]
        if stray:
            violations.append(
                f"metric_ids {stray} are not part of concept {concept!r} "
                f"({list(c.metric_ids)}); the model may not silently reinterpret a concept.")

    # --- dimensions -----------------------------------------------------------------------
    raw_dims = data.get("dimensions", [])
    if isinstance(raw_dims, str):
        raw_dims = [raw_dims]
    if not isinstance(raw_dims, list):
        violations.append("dimensions: must be a list")
        raw_dims = []
    dimensions = []
    for d in raw_dims:
        if not isinstance(d, str) or d not in KNOWN_DIMENSIONS:
            violations.append(
                f"dimension {d!r} is not catalogued in business_dimensions.md. The model may "
                f"not invent a dimension or name a raw column.")
        else:
            dimensions.append(d)

    # --- filters --------------------------------------------------------------------------
    raw_filters = data.get("filters", {}) or {}
    filters = {}
    if not isinstance(raw_filters, dict):
        violations.append("filters: must be an object of {dimension: value}")
    else:
        for k, v in raw_filters.items():
            if k not in KNOWN_DIMENSIONS:
                violations.append(
                    f"filter key {k!r} is not a catalogued dimension. Filters may only be "
                    f"expressed over business_dimensions.md entries, never raw columns.")
                continue
            if not isinstance(v, (str, int, float, bool)):
                violations.append(f"filter {k!r}: value must be a scalar")
                continue
            if isinstance(v, str):
                cleaned = _check_free_text(v, f"filters[{k}]", violations)
                if cleaned:
                    filters[k] = cleaned
            else:
                filters[k] = v

    # --- free-text fields ------------------------------------------------------------------
    time_range = _check_free_text(data.get("time_range", "") or "", "time_range", violations)
    comparison = _check_free_text(data.get("comparison", "") or "", "comparison", violations)
    clarification_reason = _check_free_text(
        data.get("clarification_reason", "") or "", "clarification_reason", violations)

    # --- enums / booleans -------------------------------------------------------------------
    requested_output = data.get("requested_output", "value") or "value"
    if requested_output not in REQUESTED_OUTPUTS:
        violations.append(
            f"requested_output {requested_output!r} is not one of {list(REQUESTED_OUTPUTS)}")
        requested_output = "value"

    def _flag(name, default=False):
        v = data.get(name, default)
        if not isinstance(v, bool):
            violations.append(f"{name}: must be a boolean")
            return default
        return v

    explanation_requested = _flag("explanation_requested")
    recommendation_requested = _flag("recommendation_requested")
    clarification_needed = _flag("clarification_needed")

    # --- resolution completeness -------------------------------------------------------------
    if not concept and not metric_ids and not clarification_needed:
        violations.append(
            "the request resolves no concept and no metric_id, and does not ask for "
            "clarification -- there is nothing to execute and nothing to ask")

    if violations:
        # `repairable` distinguishes a malformed response (worth one repair attempt) from a
        # response that asked for something the semantic layer does not contain (never
        # repairable by re-prompting -- the metric genuinely does not exist).
        repairable = not any("does not exist in semantic_metric_registry" in v
                             or "is not in the concept map" in v
                             or "not catalogued in business_dimensions" in v
                             for v in violations)
        return ValidationOutcome(None, tuple(violations), repairable=repairable)

    return ValidationOutcome(
        LLMPlanRequest(
            intent=tuple(intents), concept=concept, metric_ids=tuple(metric_ids),
            dimensions=tuple(dimensions), filters=filters, time_range=time_range,
            comparison=comparison, requested_output=requested_output,
            explanation_requested=explanation_requested,
            recommendation_requested=recommendation_requested,
            clarification_needed=clarification_needed,
            clarification_reason=clarification_reason, raw=text,
        ), (), False)


def json_schema():
    """The schema, emitted into the prompt so the model is told exactly what is accepted.
    Generated from the same constants the validator enforces, so prompt and validator can
    never drift apart."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["intent"],
        "properties": {
            "intent": {"type": "array", "items": {"enum": list(ALL_INTENTS)}, "minItems": 1},
            "concept": {"type": "string",
                        "enum": [c.name for c in concept_map.all_concepts()]},
            "metric_ids": {"type": "array", "items": {"type": "string"}},
            "dimensions": {"type": "array", "items": {"enum": sorted(KNOWN_DIMENSIONS)}},
            "filters": {"type": "object"},
            "time_range": {"type": "string", "maxLength": MAX_FREE_TEXT},
            "comparison": {"type": "string", "maxLength": MAX_FREE_TEXT},
            "requested_output": {"enum": list(REQUESTED_OUTPUTS)},
            "explanation_requested": {"type": "boolean"},
            "recommendation_requested": {"type": "boolean"},
            "clarification_needed": {"type": "boolean"},
            "clarification_reason": {"type": "string", "maxLength": MAX_FREE_TEXT},
        },
    }
