"""
role_scope.py -- what a role workspace is ABOUT, from links the registry already records.

A workspace used to be scoped by domain alone. Nine lenses share three domains, and five of the
nine declare all three, so domain scoping gave those five the same fifty-six measures. Scoring
capability words against metric descriptions made them look different, but it established
nothing: a word matching a description is not the metric belonging to the lens.

This module builds the chain from links that are already written down, and from nothing else:

    role  ->  capabilities            analyst_roles.py            (the role's declared list)
    capability  ->  implementing module   analysis_capability_registry.csv  `implemented_in`
    module  ->  metrics                 one of two recorded links:

      1. CALCULATOR. The module is a calculator, and `engine.calculators.REGISTRY` names the
         metrics it computes. A calculator computing a metric is the strongest link there is.

      2. DECLARED WORKING SET. The module defines, at module level, a collection of metric ids
         it operates over -- `COMPARABLE_MONTHLY_METRICS`, `BUSINESS_HEALTH_KPIS`. A module can
         implement several capabilities, so a set is attributed only to the capabilities whose
         `defined_by` specification clause is cited in the set's own annotation. When the
         annotation cites none of them, the set is the module's general working set and belongs
         to all of its capabilities.

The citation rule is what keeps this from being a keyword match. `RISK_COMPOSITE_METRICS` is
annotated with "analytics_execution_spec.md 2.8"; of the five capabilities its module implements,
only the risk scan is defined by 2.8. So the risk composites belong to the risk scan -- not to
`trend` or `drill_down`, which merely live in the same file.

WHAT THIS DOES NOT DO

It authorizes nothing. Every id it returns was already authorized for the role by domain, and a
metric the role may open stays openable everywhere else. It computes no figure, reads no
evidence, and never invents a link: a role whose capabilities reach nothing its domains contain
is reported as not determinable rather than given a selection.
"""
import importlib
import inspect
import re
from dataclasses import dataclass, field
from functools import lru_cache

from engine.capability_disclosure import CAPABILITY_REGISTRY_PATH, _read_registry

CALCULATOR_PACKAGE = "engine.calculators"

BASIS_DOMAIN = "declared_domain"
BASIS_CAPABILITY = "capability_links"
BASIS_NOT_DETERMINABLE = "not_determinable"

# Said once, in these exact words, on the payload and on the page. The owner is told plainly that
# this lens has no distinct scope of its own, rather than being shown a selection it has no
# recorded basis for.
NOT_DETERMINABLE_REASON = "Role distinction is not determinable from existing registry metadata."
NOT_DETERMINABLE_NOTE = NOT_DETERMINABLE_REASON

# How many measures lead. Enough to set the emphasis, few enough that leading means something.
FOREGROUND_LIMIT = 8

_METRIC_ID = re.compile(r"^M\.[A-Z]+\.\d+[A-Z]?$")
_ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*[\(\[{]")


@dataclass(frozen=True)
class WorkspaceScope:
    scope_ids: tuple            # what the workspace is about, in registry order
    foreground_ids: tuple       # what leads, in the role's own capability order
    basis: str                  # which rule produced the scope
    note: str = ""              # owner-facing sentence, when the scope needs one
    reason: str = ""            # technical sentence, for the audit trail
    provenance: dict = field(default_factory=dict)   # metric id -> how the role reaches it


def _module_name(path):
    """'engine/calculators/financial.py' -> 'engine.calculators.financial'."""
    return str(path or "").strip().replace("\\", "/")[:-3].replace("/", ".")


def _cites(annotation, defined_by):
    """Does this annotation cite this specification clause?

    Matched as a whole citation: "analytics_execution_spec.md 2.2" does not match an annotation
    that cites 2.25, and an empty `defined_by` cites nothing.
    """
    clause = str(defined_by or "").strip()
    if not clause:
        return False
    return re.search(re.escape(clause) + r"(?![\w.])", annotation) is not None


def _defined_working_sets(module):
    """Collections of metric ids this module DEFINES, each with its own annotation.

    Only an assignment in this module's source counts. A set imported from elsewhere is that
    other module's declaration, and counting it here would attribute one module's working set to
    every module that happens to use it.
    """
    try:
        lines = inspect.getsource(module).splitlines()
    except (OSError, TypeError):
        return {}
    sets = {}
    for index, line in enumerate(lines):
        match = _ASSIGNMENT.match(line)
        if not match:
            continue
        name = match.group(1)
        value = getattr(module, name, None)
        if not isinstance(value, (tuple, list, frozenset, set)) or not value:
            continue
        if not all(isinstance(v, str) and _METRIC_ID.match(v) for v in value):
            continue
        # The comment block directly above the assignment, stopping at the first line that is
        # not a comment -- a neighbouring constant's comment is not this set's annotation.
        above = []
        cursor = index - 1
        while cursor >= 0 and lines[cursor].lstrip().startswith("#"):
            above.insert(0, lines[cursor])
            cursor -= 1
        # And the assignment itself, whose inline comments are part of the declaration.
        body, depth, cursor = [], 0, index
        while cursor < len(lines):
            body.append(lines[cursor])
            depth += sum(lines[cursor].count(c) for c in "([{")
            depth -= sum(lines[cursor].count(c) for c in ")]}")
            if depth <= 0:
                break
            cursor += 1
        sets[name] = (tuple(value), "\n".join(above + body))
    return sets


@lru_cache(maxsize=1)
def capability_links():
    """Every capability's metrics, each with how the link was established.

    Returns {capability_id: {metric_id: provenance_sentence}}. Built once: every input is a file
    in the repository or a module already loaded, so the answer cannot change while running.
    """
    from engine.calculators import REGISTRY

    rows = _read_registry(CAPABILITY_REGISTRY_PATH)
    by_module = {}
    for row in rows:
        by_module.setdefault(_module_name(row.get("implemented_in")), []).append(row)

    # 1. Calculators: the metrics each calculator module computes.
    computed = {}
    for metric_id, calculator in REGISTRY.items():
        owner = getattr(calculator, "__module__", None)
        if owner:
            computed.setdefault(owner, []).append(metric_id)

    links = {}
    for module_name, module_rows in by_module.items():
        if module_name.startswith(CALCULATOR_PACKAGE + "."):
            for row in module_rows:
                for metric_id in computed.get(module_name, ()):
                    links.setdefault(row["capability_id"], {})[metric_id] = (
                        f"computed by {module_name}")
            continue

        # 2. Declared working sets, attributed by citation.
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for set_name, (ids, annotation) in _defined_working_sets(module).items():
            cited = [r for r in module_rows if _cites(annotation, r.get("defined_by"))]
            targets = cited or module_rows
            how = ("cited by its annotation" if cited
                   else "module-wide, no capability cited")
            for row in targets:
                for metric_id in ids:
                    links.setdefault(row["capability_id"], {}).setdefault(
                        metric_id, f"{module_name}.{set_name} ({how})")
    return links


def workspace_scope(role, authorized_ids):
    """What this role's workspace is about, and what it leads with.

    `authorized_ids` is what the role may see, in registry order. The scope never leaves it.

      * A role that declares ONE domain owns that domain outright -- the role registry documents
        `domains` as the registry domain values the lens owns, and one domain is a complete,
        precise statement of ownership. Its capability links are not a complete inventory of
        what it owns (the risk lens's capabilities reach four of its nine measures), so they
        decide what leads, not what is shown.

      * A role that declares SEVERAL domains has declared breadth, not specificity. Its
        capabilities are what say what it is for, so its scope is what they reach.

      * A role whose capabilities reach nothing in its domains keeps its domains, and is reported
        as not determinable. It is not given a selection it has no basis for.
    """
    authorized = tuple(authorized_ids)
    allowed = set(authorized)
    position = {metric_id: i for i, metric_id in enumerate(authorized)}
    links = capability_links()

    reached, provenance = [], {}
    for capability in role.capabilities or ():
        linked = links.get(capability, {})
        for metric_id in sorted((m for m in linked if m in allowed), key=position.get):
            provenance.setdefault(metric_id, []).append(f"{capability}: {linked[metric_id]}")
            if metric_id not in reached:
                reached.append(metric_id)

    foreground = tuple(reached[:FOREGROUND_LIMIT])
    frozen = {m: tuple(v) for m, v in provenance.items()}

    if len(set(role.domains or ())) == 1:
        return WorkspaceScope(scope_ids=authorized, foreground_ids=foreground,
                              basis=BASIS_DOMAIN, provenance=frozen)
    if reached:
        chosen = set(reached)
        return WorkspaceScope(scope_ids=tuple(m for m in authorized if m in chosen),
                              foreground_ids=foreground, basis=BASIS_CAPABILITY,
                              provenance=frozen)
    return WorkspaceScope(scope_ids=authorized, foreground_ids=(),
                          basis=BASIS_NOT_DETERMINABLE, note=NOT_DETERMINABLE_NOTE,
                          reason=NOT_DETERMINABLE_REASON, provenance=frozen)
