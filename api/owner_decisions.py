"""
owner_decisions.py -- Phase 13. Read-only ledger for recorded owner decisions.

The harness may READ this file. Nothing in the application writes it. An empty or
missing file means no waivers: live data that differs from the trusted export stays
QUARANTINED.

Numeric metric drift cannot be waived. A decision that claims to convert an unrelated
value mismatch into equivalence is ignored (treated as absent).
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECISIONS_PATH = os.path.join(ROOT, "phase13_owner_decisions.json")

# Kinds the harness will honour. metric_value is intentionally absent.
ALLOWED_KINDS = frozenset()


def load_owner_decisions(path=None):
    """Return a tuple of decision dicts. Never creates or mutates the file."""
    target = path or DECISIONS_PATH
    if not os.path.exists(target):
        return ()
    with open(target, encoding="utf-8") as f:
        raw = json.load(f)
    items = raw.get("decisions") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return ()
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = (item.get("kind") or "").strip()
        if kind not in ALLOWED_KINDS:
            continue
        out.append(item)
    return tuple(out)
