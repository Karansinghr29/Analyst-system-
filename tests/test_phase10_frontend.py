"""
Phase 10: the Owner Application.

Frontend contract tests, trust regression through the rendered payloads, accessibility and
responsive checks, and proof that the anti-drift validator actually catches violations.

The tests parse the served HTML/CSS/JS with Python, so the suite runs in the existing pytest
harness with no browser or node dependency. What they verify is the shipped source — which is
also the source the browser receives, because Phase 10 deliberately has no build step.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT
from api.service import AnalyticsService, create_app
from api.auth import suite_authenticator, bearer_headers

FRONTEND = os.path.join(ROOT, "frontend")
_CACHE = {}


def read(name):
    with open(os.path.join(FRONTEND, name), encoding="utf-8") as f:
        return f.read()


def js_modules():
    out = {}
    for base, _d, files in os.walk(FRONTEND):
        for f in files:
            if f.endswith(".js"):
                p = os.path.join(base, f)
                out[os.path.relpath(p, FRONTEND).replace("\\", "/")] = open(
                    p, encoding="utf-8").read()
    return out


@pytest.fixture(scope="module")
def client(registry):
    if "client" not in _CACHE:
        from fastapi.testclient import TestClient
        svc = AnalyticsService(registry=registry,
                               db_path=os.path.join(tempfile.mkdtemp(), "p10.db"))
        client = TestClient(create_app(svc, authenticator=suite_authenticator()))
        client.headers.update(bearer_headers())
        _CACHE["client"] = client
    return _CACHE["client"]


@pytest.fixture(scope="module")
def gate(registry):
    return TrustGate(registry)


@pytest.fixture(scope="module")
def home(client):
    if "home" not in _CACHE:
        _CACHE["home"] = client.get("/api/owner/home").json()
    return _CACHE["home"]


class TestApplicationShell:
    def test_the_app_is_served(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "<div id=\"app\">" in r.text

    @pytest.mark.parametrize("asset", [
        "/static/app.js", "/static/api.js", "/static/render.js", "/static/trust.js",
        "/static/styles.css", "/static/views/dashboard.js", "/static/views/metric.js",
        "/static/views/chat.js", "/static/views/workspace.js",
        "/static/views/analytics.js", "/static/views/powerbi.js", "/static/bi_nav.js",
    ])
    def test_every_module_is_served(self, client, asset):
        r = client.get(asset)
        assert r.status_code == 200 and len(r.content) > 0

    def test_the_page_declares_a_noscript_fallback(self):
        html = read("index.html")
        assert "<noscript>" in html
        assert "No figures are shown without it" in html, (
            "a partial render could omit a caveat or a competing definition, so the "
            "no-JS state must refuse rather than degrade")

    def test_the_page_has_a_skip_link_and_lang(self):
        html = read("index.html")
        assert 'lang="en"' in html
        assert "skip-link" in html


class TestNoBusinessLogicInTheFrontend:
    """The Phase 10 constraint, checked against the shipped source."""

    def test_only_api_js_performs_io(self):
        for name, src in js_modules().items():
            if name == "api.js":
                continue
            for io_call in ("fetch(", "XMLHttpRequest", "WebSocket(", "EventSource("):
                assert io_call not in src, f"{name} performs I/O ({io_call})"

    def test_no_module_hardcodes_a_metric_id(self):
        for name, src in js_modules().items():
            found = re.findall(r"\bM\.[A-Z]+\.\d+[A-Za-z]?\b", src)
            assert not found, f"{name} hardcodes metric ids {found}"

    def test_no_module_contains_sql(self):
        for name, src in js_modules().items():
            assert not re.search(r"\bselect\b[\s\S]{0,200}?\bfrom\b", src, re.IGNORECASE), name

    def test_no_module_decides_a_trust_level(self):
        """Trust must be read from the payload. A client that could derive it could disagree
        with the gate, and the answer would still look authoritative."""
        for name, src in js_modules().items():
            for level in ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
                # Allow the string only inside comments; strip them first.
                code = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", src)
                code = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`", '""', code)
                assert not re.search(r"\b" + level + r"\b", code), (
                    f"{name} references trust level {level} in code")

    def test_the_renderer_gates_on_headline_permitted(self):
        src = read("render.js")
        assert "headline_permitted" in src
        assert src.index("tile.headline_permitted") < src.index("tile.display_value")

    def test_formatting_is_not_performed_client_side(self):
        """A UI that formats can round a figure away from what the engine computed."""
        for name, src in js_modules().items():
            for fmt in ("toFixed(", "toLocaleString(", "Intl.NumberFormat", "Math.round("):
                assert fmt not in src, f"{name} formats a number ({fmt})"


class TestTrustRegressionThroughPayloads:
    def test_every_tile_matches_the_gate(self, home, registry, gate):
        tiles = home["business_health"] + home["operations"] + home["risks"]
        for t in tiles:
            assert t["trust"]["trust_level"] == gate.authorize(t["metric_id"]).effective_level

    def test_block_tiles_carry_no_value_and_no_chart(self, client, registry, gate):
        found = False
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level != "BLOCK":
                continue
            found = True
            tile = client.get(f"/api/metrics/{mid}").json()["tile"]
            assert tile["value"] is None
            assert tile["display_value"] == ""
            assert tile["chart_type"] == "none"
            assert tile["headline_permitted"] is False
        assert found

    def test_show_both_tiles_carry_every_definition(self, client, registry, gate):
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level != "SHOW_BOTH":
                continue
            tile = client.get(f"/api/metrics/{mid}").json()["tile"]
            assert tile["value"] is None
            if tile["definitions"]:
                assert len(tile["definitions"]) >= 2

    def test_not_determinable_carries_the_exact_phrase(self, client, registry, gate):
        found = False
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level != "NOT_DETERMINABLE":
                continue
            found = True
            tile = client.get(f"/api/metrics/{mid}").json()["tile"]
            assert NOT_DETERMINABLE_TEXT in tile["unavailable_reason"]
            assert tile["value"] is None
        assert found

    def test_the_three_cockpit_refusals_are_present(self, home):
        blocked = [t for t in home["business_health"] + home["operations"]
                   if not t["headline_permitted"]]
        ids = {t["metric_id"] for t in blocked}
        assert {"M.AR.001A", "M.PROFIT.001", "M.OCC.001"} <= ids

    def test_disclose_tiles_carry_their_caveat(self, home):
        tiles = home["business_health"] + home["operations"]
        disclose = [t for t in tiles if t["trust"]["trust_level"] == "DISCLOSE"]
        assert disclose
        for t in disclose:
            assert t["caveat"].strip()

    def test_conflict_view_never_picks_a_winner(self, client, registry, gate):
        for mid in registry.all_ids():
            if gate.authorize(mid).effective_level not in ("SHOW_BOTH", "BLOCK"):
                continue
            cv = client.get(f"/api/metrics/{mid}/conflict").json()
            assert cv["headline_permitted"] is False
            assert "business decision" in cv["which_should_we_use"]

    def test_workspaces_agree_on_trust(self, client, registry, gate):
        from engine import analyst_roles
        for role in analyst_roles.all_roles():
            ws = client.get(f"/api/roles/{role.role_id}/workspace").json()
            for t in ws["tiles"]:
                assert t["trust"]["trust_level"] == \
                    gate.authorize(t["metric_id"]).effective_level


class TestChatAndContinuity:
    def test_an_answer_carries_its_evidence_chain(self, client):
        r = client.post("/api/ask",
                        json={"question": "How much revenue did we make?"}).json()
        assert len(r["evidence_chain"]) == 10
        assert r["trust_level"] == "SAFE"

    def test_a_block_answer_permits_no_headline(self, client):
        r = client.post("/api/ask", json={"question": "What's our profit?"}).json()
        assert r["trust_level"] == "BLOCK"
        assert r["headline_permitted"] is False

    def test_conversation_continuity_across_requests(self, client):
        first = client.post("/api/ask",
                            json={"question": "How much did we collect?"}).json()
        cid = first["conversation_id"]
        assert first["status"] == "NEEDS_CLARIFICATION"
        second = client.post("/api/ask",
                             json={"question": "The ledger one",
                                   "conversation_id": cid}).json()
        assert second["metric_ids"] == ["M.COL.003"], (
            "the clarification did not survive the request boundary")

    def test_the_chat_view_surfaces_guard_violations(self):
        """Presenting the fallback silently would misrepresent whose words the answer is."""
        src = read("views/chat.js")
        assert "guard_violations" in src
        assert "overridden" in src.lower()

    def test_the_chat_view_renders_the_evidence_chain(self):
        src = read("views/chat.js")
        assert "evidence_chain" in src
        assert "Why are you saying this?" in src


class TestAccessibility:
    def test_trust_is_never_conveyed_by_colour_alone(self):
        css = read("styles.css")
        js = read("trust.js")
        assert ".trust-text" in css and ".trust-glyph" in css
        assert "trust-text" in js and "trust-glyph" in js

    def test_tiles_carry_an_aria_label_with_the_trust_posture(self):
        src = read("render.js")
        assert "aria-label" in src
        assert "ariaLabel(tile.title, tile.trust)" in src

    def test_tiles_are_keyboard_reachable(self):
        src = read("render.js")
        assert "tabindex" in src
        assert "keydown" in src
        assert "'Enter'" in src

    def test_there_is_a_visible_focus_style(self):
        assert ":focus-visible" in read("styles.css")

    def test_live_regions_are_announced(self):
        assert "aria-live" in read("render.js")
        assert "aria-live" in read("views/chat.js")

    def test_reduced_motion_is_respected(self):
        assert "prefers-reduced-motion" in read("styles.css")

    def test_form_inputs_have_labels(self):
        for name in ("views/chat.js", "app.js"):
            src = read(name)
            if "input" in src:
                assert "label" in src, f"{name} has an input with no label"


class TestResponsive:
    def test_breakpoints_exist(self):
        css = read("styles.css")
        assert css.count("@media") >= 3

    def test_conflicts_are_never_hidden_at_any_breakpoint(self):
        """Space pressure is exactly when the temptation to show one number appears."""
        css = read("styles.css")
        hide = re.compile(
            r"\.(definition-list|definition-cards|tile-refusal|metric-refusal|"
            r"conflict-decision)[^{]*\{[^}]*display\s*:\s*none",
            re.IGNORECASE | re.DOTALL)
        assert not hide.search(css)

    def test_grids_collapse_to_one_column_on_narrow_screens(self):
        css = read("styles.css")
        assert "grid-template-columns: 1fr" in css

    def test_dark_mode_is_supported(self):
        assert "prefers-color-scheme: dark" in read("styles.css")


class TestValidatorCatchesViolations:
    """A validator that never fails proves nothing."""

    def _run(self):
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts",
                                          "validate_phase10_consistency.py")],
            capture_output=True, text=True, cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def test_the_validator_passes_on_the_real_frontend(self):
        r = self._run()
        assert r.returncode == 0, r.stdout[-4000:]
        assert "No inconsistency" in r.stdout

    def test_the_validator_catches_injected_arithmetic(self):
        target = os.path.join(FRONTEND, "views", "_probe.js")
        with open(target, "w", encoding="utf-8") as f:
            f.write("export function bad(tile) { return tile.value * 2; }\n")
        try:
            r = self._run()
            assert r.returncode != 0
            assert "[2]" in r.stdout
        finally:
            os.remove(target)

    def test_the_validator_catches_injected_io(self):
        target = os.path.join(FRONTEND, "views", "_probe.js")
        with open(target, "w", encoding="utf-8") as f:
            f.write("export async function bad() { return fetch('/elsewhere'); }\n")
        try:
            r = self._run()
            assert r.returncode != 0
            assert "[1]" in r.stdout
        finally:
            os.remove(target)

    def test_the_validator_catches_a_hardcoded_metric_id(self):
        target = os.path.join(FRONTEND, "views", "_probe.js")
        with open(target, "w", encoding="utf-8") as f:
            f.write("export const PINNED = { id: M.REV.001 };\n")
        try:
            r = self._run()
            assert r.returncode != 0
            assert "[3]" in r.stdout
        finally:
            os.remove(target)

    def test_the_validator_catches_client_side_trust_logic(self):
        target = os.path.join(FRONTEND, "views", "_probe.js")
        with open(target, "w", encoding="utf-8") as f:
            f.write("export function bad(t) { return t.level === BLOCK; }\n")
        try:
            r = self._run()
            assert r.returncode != 0
            assert "[4]" in r.stdout
        finally:
            os.remove(target)


class TestIntegrity:
    def test_source_csvs_are_byte_identical(self):
        import csv as _csv
        import hashlib
        with open(os.path.join(ROOT, "evidence", "file_manifest.csv"),
                  encoding="utf-8-sig") as f:
            rows = list(_csv.DictReader(f))
        h = hashlib.sha256()
        for r in rows:
            with open(os.path.join(ROOT, r["file"]), "rb") as fh:
                h.update(fh.read())
        assert h.hexdigest() == (
            "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26")

    def test_no_build_artifacts_exist(self):
        """The zero-build decision is what makes the source scan meaningful."""
        for forbidden in ("node_modules", "dist", "build", "package-lock.json"):
            assert not os.path.exists(os.path.join(FRONTEND, forbidden))
