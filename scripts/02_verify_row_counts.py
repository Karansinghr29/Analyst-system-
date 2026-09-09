"""
02_verify_row_counts.py  --  READ ONLY

Re-derives section 3 of evidence_integrity_report.md from scratch.

For every exported base-table CSV, compares its actual data-row count against
M.006 `row_counts_exact` (the authoritative COUNT(*) taken at 2026-08-29 09:02:53Z).

Also reports:
  - public tables with rows that were NOT exported (should be zero)
  - public tables with 0 rows (recorded as EMPTY, not MISSING)
  - market tables (declared IN_SCOPE in M.000, none exported)

Does not modify any source CSV.
"""
import csv
import os
import sys

BASE = r"D:\data science\AI Analytics System"
MANIFEST = os.path.join(BASE, "evidence", "file_manifest.csv")
ROWCOUNTS = "Supabase Snippet Untitled query (6).csv"       # M.006
SCOPE = "Supabase Snippet Untitled query.csv"               # M.000
SNAP_START = "Supabase Snippet Untitled query (2).csv"      # M.002
SNAP_END = ("Supabase Snippet Untitled query - "
            "2026-08-29T164828.845.csv")                    # M.099

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def rd(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def count_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        next(r, None)
        return sum(1 for _ in r)


def main():
    os.chdir(BASE)

    start = rd(SNAP_START)[0]
    end = rd(SNAP_END)[0]
    counted_at = rd(ROWCOUNTS)[0]["counted_at"]
    print("snapshot START :", start["snapshot_at"], "txn", start["txn_snapshot"])
    print("row counts at  :", counted_at)
    print("snapshot END   :", end["snapshot_at"], "txn", end["txn_snapshot"])
    print()

    rc = {(r["table_schema"], r["table_name"]): int(r["exact_rows"]) for r in rd(ROWCOUNTS)}
    man = [m for m in rd(MANIFEST) if m["class"] == "base_table"]

    mismatches, matches = [], 0
    exported = set()
    for m in man:
        sch, tbl = m["logical_name"].split(".", 1)
        exported.add((sch, tbl))
        actual = count_rows(m["file"])
        expected = rc.get((sch, tbl))
        if expected is None:
            mismatches.append((tbl, None, actual, None))
        elif actual != expected:
            mismatches.append((tbl, expected, actual, actual - expected))
        else:
            matches += 1

    print("exported base-table CSVs :", len(man))
    print("row count MATCHES M.006  :", matches)
    print("row count DIFFERS        :", len(mismatches))
    print()
    if mismatches:
        print(f"{'table':28s} {'M.006':>8s} {'exported':>9s} {'delta':>7s}")
        for tbl, exp, act, d in sorted(mismatches):
            print(f"{tbl:28s} {str(exp):>8s} {act:>9d} {('%+d' % d) if d is not None else '?':>7s}")
        print()
        print("NOTE: the export ran over a 2h16m window against a LIVE database.")
        print("      A positive delta means rows were inserted after the count was taken.")
        print("      Verify each one by inspecting the newest rows in that CSV.")
        print()

    pub = {k for k in rc if k[0] == "public"}
    empty = sorted(k[1] for k in pub if rc[k] == 0)
    nonzero = {k for k in pub if rc[k] > 0}
    missing = sorted(k[1] for k in nonzero - exported)

    print("public base tables            :", len(pub))
    print("  with rows, exported         :", len(nonzero & exported), "of", len(nonzero))
    print("  with rows, NOT exported     :", len(missing), (missing if missing else "(none)"))
    print("  EMPTY (0 rows, not exported):", len(empty))
    for t in empty:
        print("      EMPTY:", t)
    print()

    mkt = sorted(k for k in rc if k[0] == "market")
    mkt_exported = [k for k in mkt if k in exported]
    print("market base tables            :", len(mkt),
          "(declared IN_SCOPE in M.000)")
    print("  exported                    :", len(mkt_exported))
    print("  rows unavailable offline    :", sum(rc[k] for k in mkt if k not in exported))
    for k in mkt:
        if rc[k] > 0:
            print(f"      {k[1]:34s} {rc[k]:>5d} rows  NOT EXPORTED")

    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
