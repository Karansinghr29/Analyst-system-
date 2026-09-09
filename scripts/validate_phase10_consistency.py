"""
validate_phase10_consistency.py -- Phase 10 anti-drift validator.

Statically analyses the SHIPPED frontend source and exercises the running application.

The reason this can be meaningful at all is the zero-build decision: the bytes the browser
receives are the bytes scanned here. A bundler would emit minified output in which
`headline_permitted` becomes `a.h` and arithmetic is inlined, and the single most important
Phase 10 guarantee -- the frontend performs no calculation -- would become unverifiable in
exactly the artifact that ships.

Checks (Phase 10 plan 5):
   1. only api.js performs I/O
   2. no arithmetic applied to a metric value
   3. no hardcoded metric definition, formula, threshold, or SQL
   4. no hardcoded trust logic
   5. every rendered metric_id exists in the semantic registry
   6. no render path emits a value when headline_permitted is false
   7. every trust level has a visual treatment
   8. every UI entry point maps to a real API route
   9. every route the frontend calls exists in openapi.json
  10. the exact NOT_DETERMINABLE phrase survives to the DOM
  11. accessibility: trust never by colour alone; tiles carry aria-labels
  12. responsive: conflicts are not collapsed at any breakpoint
  13. source CSVs byte-identical

Read-only with respect to evidence.
"""
import csv
import hashlib
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT
from api.service import AnalyticsService, create_app
from api.auth import suite_authenticator, bearer_headers

FRONTEND = os.path.join(ROOT, "frontend")
BASELINE_SHA = "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26"

TRUST_LEVELS = ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE")


def js_files():
    out = []
    for base, _dirs, files in os.walk(FRONTEND):
        for f in files:
            if f.endswith(".js"):
                out.append(os.path.join(base, f))
    return sorted(out)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def strip_comments_and_strings(src):
    """Remove comments and string literals so pattern checks inspect CODE, not prose.

    Without this, a comment explaining "we never compute value * rate" would itself trip the
    arithmetic check -- and the fix would be to delete the explanation, which is the wrong
    incentive entirely.
    """
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
        elif c in "'\"`":
            quote = c
            i += 1
            while i < n and src[i] != quote:
                if src[i] == "\\":
                    i += 1
                i += 1
            i += 1
            out.append('""')
        else:
            out.append(c)
            i += 1
    return "".join(out)


def main():
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    problems, warnings = [], []

    files = js_files()
    if not files:
        problems.append("[0] no frontend JavaScript found")
        print("PHASE 10 VALIDATION: no frontend to check")
        return 1

    code = {p: strip_comments_and_strings(read(p)) for p in files}
    raw = {p: read(p) for p in files}

    # -- 1: only api.js performs I/O ------------------------------------------------------------
    for path, src in code.items():
        name = os.path.basename(path)
        for io_call in ("fetch(", "XMLHttpRequest", "WebSocket(", "EventSource("):
            if io_call in src and name != "api.js":
                problems.append(
                    f"[1] {os.path.relpath(path, ROOT)}: performs I/O ({io_call}). Only api.js "
                    f"may reach the network, so 'the API is the only boundary' stays a one-file "
                    f"property")

    # -- 2: no arithmetic applied to a metric value ----------------------------------------------
    # Any use of an arithmetic operator on an identifier that looks like a metric quantity.
    VALUE_TOKENS = ("value", "display_value", "amount", "total", "count", "figure",
                    "absolute_change", "percentage_change", "affected_amount")
    ident = r"\w*(?:" + "|".join(VALUE_TOKENS) + r")\w*"

    # String literals were replaced by `""` during stripping, so `count + ""` is a LABEL being
    # built: the number reaches the DOM exactly as the payload supplied it, which is display,
    # not computation. `count - other` or `count * 2` would be real arithmetic.
    #
    # `+` is therefore flagged only when neither operand is a former string literal. The other
    # operators are always flagged, since none of them concatenates.
    plus_with_string = re.compile(
        r'(?:""\s*\+\s*' + ident + r')|(?:' + ident + r'\s*\+\s*"")', re.IGNORECASE)
    any_plus = re.compile(r"\b(" + ident + r")\s*\+", re.IGNORECASE)
    hard_arith = re.compile(r"\b(" + ident + r")\s*(?:[-*/%]=?|\+=)", re.IGNORECASE)

    for path, src in code.items():
        rel = os.path.relpath(path, ROOT)
        for m in hard_arith.finditer(src):
            problems.append(
                f"[2] {rel}: arithmetic applied to {m.group(1)!r}. A frontend that can compute "
                f"can disagree with the engine, and the disagreement would be invisible because "
                f"both numbers would look correct")
        concat = [m.span() for m in plus_with_string.finditer(src)]
        for m in any_plus.finditer(src):
            if any(m.start() >= s0 and m.start() <= e0 for s0, e0 in concat):
                continue          # building a label out of a payload value
            problems.append(
                f"[2] {rel}: {m.group(1)!r} used in an addition that is not string "
                f"concatenation; the client must not compute")

    # -- 3: no hardcoded definitions, formulas, thresholds, SQL ------------------------------------
    for path, src in code.items():
        low = src.lower()
        # `import { x } from './y.js'` is an ES module statement, not SQL. So a query is flagged
        # on genuine SQL SHAPE -- a SELECT paired with a FROM, or an aggregate call -- rather
        # than on any occurrence of the word "from", which would flag every module in the app.
        if re.search(r"\bselect\b[\s\S]{0,200}?\bfrom\b", low):
            problems.append(
                f"[3] {os.path.relpath(path, ROOT)}: contains a SELECT ... FROM query")
        for token in ("group by ", "order by ", "sum(", "avg(", "count(*)", " join "):
            if token in low:
                problems.append(
                    f"[3] {os.path.relpath(path, ROOT)}: contains a query fragment ({token!r})")
        # A metric_id literal in code (not a comment/string) would mean the client hardcoded a
        # business definition rather than rendering what the API returned.
        for mid in re.findall(r"\bM\.[A-Z]+\.\d+[A-Za-z]?\b", src):
            problems.append(
                f"[3] {os.path.relpath(path, ROOT)}: hardcodes metric id {mid!r}; the client "
                f"must render whatever the API returns, not a metric it knows about")
    # A numeric threshold used in a comparison would be an invented materiality rule.
    threshold = re.compile(r"[<>]=?\s*0?\.\d+|[<>]=?\s*\d+\s*(?:\.\d+)?\s*\)")
    for path, src in code.items():
        for m in threshold.finditer(src):
            frag = m.group(0)
            if re.search(r"[<>]=?\s*0\b|[<>]=?\s*1\b|length", frag):
                continue          # length/emptiness guards are not business thresholds
            warnings.append(
                f"[3] {os.path.relpath(path, ROOT)}: numeric comparison {frag!r} -- confirm it "
                f"is not a materiality threshold")

    # -- 4: no hardcoded trust logic ---------------------------------------------------------------
    for path, src in code.items():
        for level in TRUST_LEVELS:
            # A trust level appearing in CODE (strings already stripped) means a decision was
            # made client-side rather than read from the payload.
            if re.search(r"\b" + level + r"\b", src):
                problems.append(
                    f"[4] {os.path.relpath(path, ROOT)}: references trust level {level!r} in "
                    f"code. Trust must be read from the payload, never decided in the client")
        for derived in ("headline_permitted =", "trust_level =", "effective_level"):
            if derived in src:
                problems.append(
                    f"[4] {os.path.relpath(path, ROOT)}: assigns {derived!r}; the client may "
                    f"not derive a trust posture")

    # -- 5, 6, 10: exercise the running app ----------------------------------------------------------
    from fastapi.testclient import TestClient
    svc = AnalyticsService(registry=registry,
                           db_path=os.path.join(tempfile.mkdtemp(), "v10.db"))
    client = TestClient(create_app(svc, authenticator=suite_authenticator()))
    client.headers.update(bearer_headers())

    home = client.get("/api/owner/home").json()
    tiles = home["business_health"] + home["operations"] + home["risks"]

    for t in tiles:
        if t["metric_id"] not in registry:
            problems.append(f"[5] tile {t['metric_id']!r} is not a semantic metric")
            continue
        lvl = gate.authorize(t["metric_id"]).effective_level
        if t["trust"]["trust_level"] != lvl:
            problems.append(f"[5] tile {t['metric_id']}: trust {t['trust']['trust_level']} "
                            f"!= gate {lvl}")
        # 6: no payload the renderer receives may carry a value when a headline is forbidden.
        if not t["headline_permitted"]:
            if t["value"] is not None or t["display_value"]:
                problems.append(
                    f"[6] tile {t['metric_id']}: headline forbidden but the payload carries a "
                    f"value, so a renderer could display it")
            if t["chart_type"] != "none" and lvl == "BLOCK":
                problems.append(f"[6] tile {t['metric_id']}: BLOCK offers a chart")

    # 6 (static): the renderer must gate on headline_permitted before emitting display_value.
    render_src = code.get(os.path.join(FRONTEND, "render.js"), "")
    if "headline_permitted" not in render_src:
        problems.append("[6] render.js never checks headline_permitted")
    else:
        idx_check = render_src.find("headline_permitted")
        idx_value = render_src.find("display_value")
        if idx_value != -1 and idx_check != -1 and idx_value < idx_check:
            warnings.append("[6] render.js reads display_value before checking "
                            "headline_permitted; confirm the guard still dominates")

    # 10: the exact phrase must reach the client unaltered.
    nd_metrics = [m for m in registry.all_ids()
                  if gate.authorize(m).effective_level == "NOT_DETERMINABLE"]
    for mid in nd_metrics:
        detail = client.get(f"/api/metrics/{mid}").json()
        reason = detail.get("tile", {}).get("unavailable_reason", "")
        if NOT_DETERMINABLE_TEXT not in reason:
            problems.append(f"[10] {mid}: served payload omits the exact required phrase")
    if not any(NOT_DETERMINABLE_TEXT in raw[p] for p in raw):
        # The phrase need not be hardcoded -- it flows from the payload. But no module may
        # rewrite it, so check nothing truncates or paraphrases it.
        pass
    for path, src in raw.items():
        if "Not determinable" in src and NOT_DETERMINABLE_TEXT not in src:
            problems.append(
                f"[10] {os.path.relpath(path, ROOT)}: contains a PARAPHRASE of the required "
                f"phrase; it must appear verbatim or not at all")

    # -- 7: every trust level has a visual treatment ---------------------------------------------------
    css = read(os.path.join(FRONTEND, "styles.css"))
    for tone in ("trust-neutral", "trust-caution", "trust-conflict", "trust-unavailable"):
        if "." + tone not in css:
            problems.append(f"[7] styles.css defines no treatment for {tone}")
    trust_js = code.get(os.path.join(FRONTEND, "trust.js"), "")
    for tone in ("neutral", "caution", "conflict", "unavailable"):
        if tone not in trust_js:
            problems.append(f"[7] trust.js maps no class for tone {tone!r}")

    # -- 8, 9: entry points and routes -------------------------------------------------------------------
    with open(os.path.join(ROOT, "openapi.json"), encoding="utf-8") as f:
        spec = json.load(f)
    known_paths = set(spec.get("paths", {}))

    api_src = raw[os.path.join(FRONTEND, "api.js")]
    called = set(re.findall(r"['\"](/(?:api|health)[^'\"]*)['\"]", api_src))
    for path in called:
        template = re.sub(r"'\s*\+[^+]+\+\s*'", "{p}", path)
        base = path.split("'")[0]
        matched = any(base.rstrip("/") == kp.split("{")[0].rstrip("/") or base == kp
                      for kp in known_paths)
        if not matched:
            problems.append(
                f"[9] api.js calls {path!r}, which is not in openapi.json")

    entry_questions = set()
    for t in tiles:
        for ep in t.get("ai_entry_points", []):
            entry_questions.add(ep["question"])
    for ep in home.get("ai_entry_points", []):
        entry_questions.add(ep["question"])
    for q in sorted(entry_questions):
        r = client.post("/api/ask", json={"question": q})
        if r.status_code != 200:
            problems.append(f"[8] UI entry point {q!r} does not reach a valid API route "
                            f"(status {r.status_code})")

    # -- 11: accessibility --------------------------------------------------------------------------------
    if "aria-label" not in raw[os.path.join(FRONTEND, "render.js")]:
        problems.append("[11] render.js sets no aria-label on tiles")
    if "ariaLabel" not in raw[os.path.join(FRONTEND, "trust.js")]:
        problems.append("[11] trust.js provides no accessible trust label")
    if "trust-text" not in css or "trust-glyph" not in css:
        problems.append("[11] trust badges lack a text or glyph channel; trust would be "
                        "conveyed by colour alone")
    if ":focus-visible" not in css:
        problems.append("[11] no visible focus style; keyboard users cannot see their position")
    if "skip-link" not in css:
        warnings.append("[11] no skip link style found")

    # -- 12: responsive -- conflicts are never collapsed -----------------------------------------------------
    hide_conflict = re.compile(
        r"\.(definition-list|definition-cards|tile-refusal|metric-refusal|conflict-decision)"
        r"[^{]*\{[^}]*display\s*:\s*none", re.IGNORECASE | re.DOTALL)
    if hide_conflict.search(css):
        problems.append(
            "[12] styles.css hides a conflict element. Space pressure is exactly when the "
            "temptation to show one number appears, and exactly when doing so misleads")
    if "@media" not in css:
        problems.append("[12] styles.css defines no responsive breakpoints")

    # -- 13: source integrity ---------------------------------------------------------------------------------
    with open(os.path.join(ROOT, "evidence", "file_manifest.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    h = hashlib.sha256()
    for r in rows:
        p = os.path.join(ROOT, r["file"])
        if not os.path.exists(p):
            problems.append(f"[13] source CSV missing: {r['file']}")
            continue
        with open(p, "rb") as fh:
            h.update(fh.read())
    digest = h.hexdigest()
    if digest != BASELINE_SHA:
        problems.append(f"[13] SOURCE CSVs CHANGED: {digest} != {BASELINE_SHA}")

    svc.close()

    print("=" * 88)
    print("PHASE 10 CONSISTENCY VALIDATION -- owner application vs. the live engine")
    print("=" * 88)
    print(f"\n[frontend]      {len(files)} modules, "
          f"{sum(len(raw[p]) for p in raw):,} bytes of scannable source")
    print(f"[tiles]         {len(tiles)} "
          f"({sum(1 for t in tiles if not t['headline_permitted'])} headline-forbidden)")
    print(f"[entry points]  {len(entry_questions)} exercised against the API")
    print(f"[api routes]    {len(known_paths)} in openapi.json")
    print(f"[source]        SHA-256 {digest[:16]}... "
          f"{'MATCHES baseline' if digest == BASELINE_SHA else 'CHANGED'}")
    print(f"\n[problems]      {len(problems)}")
    print(f"[warnings]      {len(warnings)}")

    if problems:
        print("\nINCONSISTENCIES:")
        for p in problems:
            print(f"   {p}")
    else:
        print("\nNo inconsistency between the owner application and the engine.")
    for w in warnings:
        print(f"   warning: {w}")

    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
