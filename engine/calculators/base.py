"""
base.py -- the calculator contract every metric-family module implements against.

A calculator function has signature:  calc(spec: MetricSpec) -> CalcOutput

CalcOutput.value is a plain number/dict for a single-definition metric, OR CalcOutput.subs is a
dict[label -> CalcOutput] for a metric whose registry `definition` documents multiple competing
sub-definitions within one metric_id (occupancy's 5+ Defs, profit's 3 Defs, owner rent's 3
Defs) -- execution.py inspects `subs` and, if present, NEVER touches `value` directly; this is
the structural guarantee that a family calculator cannot accidentally collapse to one number.

Calculators must raise NotDeterminableError (never return a fabricated value) when required
evidence is unavailable.
"""
from dataclasses import dataclass, field
from typing import Optional


class NotDeterminableError(Exception):
    """Raised by a calculator when the exported evidence cannot support the requested
    computation. Caught by execution.py and turned into a NOT_DETERMINABLE MetricAnswer --
    never caught-and-approximated."""


@dataclass
class CalcOutput:
    value: object = None
    unit: str = "count"
    evidence_sources: tuple = field(default_factory=tuple)
    provenance: str = ""
    limitations: str = ""
    subs: Optional[dict] = None   # label -> CalcOutput, for family metrics
