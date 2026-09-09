"""
Phase 16: Power BI as a first-class product module in the Owner Analytics app.

Source-level tests (no browser). Confirms navigation, native BI workspace, trust-aware
rendering reuse, role-aware API binding, AI↔BI links, and the absence of a fake embed.
"""
import os
import re

from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "frontend")


def read(rel):
    with open(os.path.join(FRONTEND, rel), encoding="utf-8") as f:
        return f.read()


def test_power_bi_navigation_exists():
    app = read("app.js")
    assert "['#/bi/executive', 'Power BI']" in app or '"#/bi/executive"' in app
    assert "renderPowerBi" in app
    assert "hash.startsWith('#/bi/')" in app or "hash.startsWith(\"#/bi/\")" in app


def test_bi_workspace_and_five_dashboards_exist():
    src = read("views/powerbi.js")
    nav = read("bi_nav.js")
    for key in ("executive", "financial", "operations", "risk", "insights"):
        assert key in nav, key
        assert "data-bi-page" in src
    assert "data-bi-workspace" in src
    assert "renderPowerBi" in src
    assert "loading(" in src
    assert "emptyState(" in src
    assert "errorState(" in src


def test_bi_pages_use_existing_authorized_apis():
    src = read("views/powerbi.js")
    assert "api.ownerHome" in src
    assert "api.analyticsSection" in src
    assert "fetch(" not in src
    assert "metricTile(" in src


def test_bi_module_does_not_fake_an_embed_or_expose_secrets():
    blob = read("views/powerbi.js") + read("bi_nav.js") + read("app.js")
    assert "<iframe" not in blob.lower()
    assert "embed token" not in blob.lower() or "no embed token" in blob.lower()
    assert "powerbi-service-attach" in blob
    assert "data-available" in blob
    for secret in ("access_token", "embedToken", "client_secret", "SUPABASE_SERVICE"):
        assert secret not in blob


def test_ai_bi_navigation_is_wired():
    chat = read("views/chat.js")
    assert "data-role', 'bi-navigation'" in chat or 'data-role", "bi-navigation"' in chat
    assert "biKeyForAsk" in chat
    dash = read("views/dashboard.js")
    assert "#/bi/executive" in dash
    render = read("render.js")
    assert "View in Power BI" in render
    assert "open-bi" in render
    pbi = read("views/powerbi.js")
    assert "#/ask" in pbi
    assert "Ask AI Business Analyst" in pbi


def test_renderer_still_gates_headline_and_definitions():
    src = read("render.js")
    assert "tile.headline_permitted" in src
    assert src.index("tile.headline_permitted") < src.index("tile.display_value")
    assert "data-role', 'definitions'" in src or 'data-role", "definitions"' in src
    assert "data-role', 'caveat'" in src or 'data-role", "caveat"' in src
    assert "unavailable_reason" in src


def test_bi_module_does_not_decide_trust_or_hardcode_metric_rows():
    for rel in ("bi_nav.js", "views/powerbi.js"):
        src = read(rel)
        found = re.findall(r"\bM\.[A-Z]+\.\d+[A-Za-z]?\b", src)
        assert not found, found
        code = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", src)
        code = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`", '""', code)
        for level in ("SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"):
            assert not re.search(r"\b" + level + r"\b", code), (rel, level)


def test_bi_module_has_no_client_side_metric_calculation():
    for rel in ("bi_nav.js", "views/powerbi.js"):
        src = read(rel)
        for fmt in ("toFixed(", "toLocaleString(", "Intl.NumberFormat", "Math.round(",
                    "Math.sum", "reduce("):
            assert fmt not in src, (rel, fmt)
        assert "fetch(" not in src


def test_role_visibility_is_delegated_to_the_api():
    src = read("views/powerbi.js")
    assert "api.analyticsSection" in src
    assert "api.ownerHome" in src
    assert "financial_analyst" not in src
    assert "operations_analyst" not in src
    assert "hardcode" not in src.lower()


def test_payload_trust_contract_for_bi_consumption(registry):
    """The BI module renders API tiles; those tiles must still obey the gate."""
    gate = TrustGate(registry)
    profit = gate.authorize("M.PROFIT.001")
    assert profit.effective_level == "BLOCK"
    assert profit.headline_permitted is False
    occ = gate.authorize("M.OCC.001")
    assert occ.effective_level == "SHOW_BOTH"
    assert occ.headline_permitted is False
    nd = gate.authorize("M.OCC.003")
    assert nd.effective_level == "NOT_DETERMINABLE"
    assert nd.headline_permitted is False
    assert NOT_DETERMINABLE_TEXT


def test_phase15_power_bi_artifacts_remain():
    for name in ("powerbi_dataset_descriptor.json", "powerbi_production_pages.json",
                 "phase15_powerbi_production_spec.md"):
        assert os.path.exists(os.path.join(ROOT, name)), name
