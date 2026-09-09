"""
evidence_loader.py  --  READ ONLY interface to the CSV evidence package.

The exported CSVs have opaque filenames ("Supabase Snippet Untitled query (43).csv").
`evidence/file_manifest.csv` maps every one of the 253 files to an object, identified
by CONTENT (header signature + exact row count vs M.006), never by filename.

This module is the only thing later deliverables should use to open a CSV.

    from evidence_loader import load, load_table, load_view, describe, keys

    je   = load_table("journal_entries")     # list[dict]
    pnl  = load_view("v_pnl")
    coa  = load("H.016")                     # by manifest key
    describe("F.001")

Manifest key namespaces
    M.*    metadata (schema/column/row-count/FK/temporal/sensitivity inventories)
    T.*    base table export
    F.001-F.028  business view export
    H.*    diagnostic export
    FN.*   function body / routine inventory / trigger wiring

Nothing here writes to disk.
"""
import csv
import os
import sys
from functools import lru_cache

# The package root, derived from this file's location rather than from the absolute path of
# the machine the export was built on -- that path is correct exactly once, on that machine,
# and a deployed copy of the same package sits somewhere else. `AI_ANALYTICS_BASE` overrides
# it where a deployment mounts the evidence elsewhere. The evidence itself is unchanged.
BASE = os.environ.get("AI_ANALYTICS_BASE") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(BASE, "evidence", "file_manifest.csv")

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

# Exports that are LIMITed samples, not full populations. Loading one of these
# emits a warning, because aggregating it as if complete yields wrong numbers.
TRUNCATED = {
    "H.028": "200 of 1213 allotments -- use H.052 for the full population",
    "H.036": "LIMIT 500 of 2204 rows -- use F.017 for the full population",
    "H.038": "200 of 33894 journal lines -- row trace only",
    "H.039": "200 of 16451 tenant_transactions -- row trace only",
    "H.040": "200 of 2227 drifting invoices -- use H.043 for the full population",
    "H.041": "200 of 5858 receipts -- row trace only",
}

# Byte-identical re-exports. Load either, never union both.
DUPLICATES = {
    "M.021": "FN.TRG", "H.001b": "H.001", "H.002b": "H.002",
    "H.010": "F.005", "H.015": "F.022", "H.054": "H.017",
    "H.020b": "H.020", "H.029": "F.028", "F.026": "F.025", "H.047": "F.027",
}


@lru_cache(maxsize=1)
def _manifest():
    with open(MANIFEST, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by_key, by_name = {}, {}
    for r in rows:
        by_key[r["key"]] = r
        by_name.setdefault(r["logical_name"], []).append(r)
    return rows, by_key, by_name


def keys(cls=None):
    """List manifest keys, optionally filtered by class
    ('base_table' | 'view' | 'diagnostic' | 'metadata' | 'functions')."""
    rows, _, _ = _manifest()
    return sorted(r["key"] for r in rows if cls is None or r["class"] == cls)


def _resolve(ref):
    rows, by_key, by_name = _manifest()
    if ref in by_key:
        return by_key[ref]
    for cand in (ref, "public." + ref, "market." + ref):
        if cand in by_name:
            hits = by_name[cand]
            if len(hits) > 1:
                pref = [h for h in hits if h["key"] not in DUPLICATES]
                hits = pref or hits
            return hits[0]
    raise KeyError(
        f"{ref!r} is not a manifest key or logical name. "
        f"Try keys() or grep evidence/file_manifest.csv."
    )


def load(ref, warn=True):
    """Load an evidence CSV as list[dict]. `ref` is a manifest key or a logical name."""
    m = _resolve(ref)
    k = m["key"]
    if warn and k in TRUNCATED:
        print(f"WARNING  {k} is a TRUNCATED sample: {TRUNCATED[k]}", file=sys.stderr)
    if warn and k in DUPLICATES:
        print(f"NOTE     {k} is byte-identical to {DUPLICATES[k]}; do not union both.",
              file=sys.stderr)
    path = os.path.join(BASE, m["file"])
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_table(name, warn=True):
    m = _resolve(name)
    if m["class"] != "base_table":
        raise ValueError(f"{name!r} resolves to {m['key']} (class={m['class']}), not a base table")
    return load(m["key"], warn=warn)


def load_view(name, warn=True):
    m = _resolve(name)
    if m["class"] != "view":
        raise ValueError(f"{name!r} resolves to {m['key']} (class={m['class']}), not a view")
    return load(m["key"], warn=warn)


def describe(ref):
    m = _resolve(ref)
    print(f"key           : {m['key']}")
    print(f"logical name  : {m['logical_name']}")
    print(f"class         : {m['class']}")
    print(f"rows x cols   : {m['rows']} x {m['cols']}   ({int(m['bytes']):,} bytes)")
    print(f"file          : {m['file']}")
    if m["note"]:
        print(f"note          : {m['note']}")
    if m["key"] in TRUNCATED:
        print(f"TRUNCATED     : {TRUNCATED[m['key']]}")
    if m["key"] in DUPLICATES:
        print(f"DUPLICATE OF  : {DUPLICATES[m['key']]}")
    return m


def snapshot():
    """Return the export window. Every CURRENT_DATE-dependent metric must cite this."""
    s = load("M.002", warn=False)[0]
    e = load("M.099", warn=False)[0]
    return {
        "start": s["snapshot_at"], "start_txn": s["txn_snapshot"],
        "end": e["snapshot_at"], "end_txn": e["txn_snapshot"],
        "counted_at": load("M.006", warn=False)[0]["counted_at"],
        "pg_version": s["pg_version"],
        "atomic": False,
        "caveat": ("Export spans 2h16m against a live DB; 56 transactions committed inside "
                   "the window. 5 tables (profiles, user_roles, maintenance_tickets, "
                   "ticket_logs, ai_logs) are +1 row vs M.006. No financial, ledger, "
                   "occupancy or tenancy table is affected."),
    }


if __name__ == "__main__":
    rows, _, _ = _manifest()
    import collections
    print("evidence files:", len(rows), dict(collections.Counter(r["class"] for r in rows)))
    print()
    for k, v in snapshot().items():
        print(f"  {k:12s}: {v}")
    print()
    if len(sys.argv) > 1:
        print()
        describe(sys.argv[1])
