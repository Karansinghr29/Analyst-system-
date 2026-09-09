"""
Focused regression: Owner Overview presentation projection.

Asserts that the owner-facing projection of Overview tiles/insights does not leak
registry identifiers, specification filenames, database object names, or posture
prefixes. Does not exercise calculators, Trust Gate, or registries.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
OWNER_VIEW = FRONTEND / "owner_view.js"
RENDER = FRONTEND / "render.js"
DASHBOARD = FRONTEND / "views" / "dashboard.js"

FORBIDDEN = re.compile(
    r"(?:"
    r"\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b|"
    r"\b(?:DQ|C|FN|H|D)\.\d{3}[A-Za-z]?\b|"
    r"\b[\w.-]+\.md\b|"
    r"\b(?:SAFE|DISCLOSE|SHOW_BOTH|BLOCK|NOT_DETERMINABLE)\s*:|"
    r"\b(?:v_|vw_)[a-z0-9_]+\b|"
    r"\bget_universal[a-z0-9_]*\b"
    r")",
    re.IGNORECASE,
)


def _strip_js_comments(src):
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def test_overview_projection_module_is_wired():
    """The Overview must render through ownerView, not the raw diagnostic payload."""
    render = RENDER.read_text(encoding="utf-8")
    dash = DASHBOARD.read_text(encoding="utf-8")
    code = _strip_js_comments(render)
    assert OWNER_VIEW.exists()
    assert "from './owner_view.js'" in render or 'from "./owner_view.js"' in render
    assert "ownerView(" in render
    assert "ownerInsight(" in render
    assert "'View in Power BI'" not in code and '"View in Power BI"' not in code
    assert "Open in Power BI" in dash
    assert "Conflicts:" not in dash
    assert "Evidence:" not in dash
    assert "ownerDecision(" in dash
    assert "ownerAction(" in dash


def _project_with_node(payload):
    """Run the real ES module projection against a temp payload file."""
    uri = OWNER_VIEW.resolve().as_uri()
    with tempfile.TemporaryDirectory() as tmp:
        home_path = Path(tmp) / "home.json"
        runner_path = Path(tmp) / "run_overview_projection.mjs"
        home_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        runner_path.write_text(
            f"""
import {{ readFileSync }} from 'fs';
import {{ overviewOwnerText, ownerInsight, ownerDecision, ownerAction }} from {json.dumps(uri)};
const home = JSON.parse(readFileSync({json.dumps(str(home_path))}, 'utf8'));
const texts = [];
for (const section of ['business_health', 'operations', 'risks']) {{
  for (const tile of (home[section] || [])) {{
    texts.push(overviewOwnerText(tile));
  }}
}}
for (const insight of (home.insights || [])) {{
  const v = ownerInsight(insight);
  texts.push([v.finding, v.why, v.action].filter(Boolean).join('\\n'));
}}
for (const d of (home.decision_queue || [])) {{
  const v = ownerDecision(d);
  texts.push([v.posture, v.decision].filter(Boolean).join('\\n'));
}}
for (const a of (home.recommended_actions || [])) {{
  const v = ownerAction(a);
  texts.push([v.recommendation, v.confidence].filter(Boolean).join('\\n'));
}}
process.stdout.write(JSON.stringify(texts));
""",
            encoding="utf-8",
        )
        result = subprocess.run(
            ["node", str(runner_path)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
        )
    if result.returncode != 0:
        pytest.fail(f"Node projection failed: {result.stderr[:800]}")
    return json.loads(result.stdout)


def test_overview_owner_projection_hides_technical_tokens():
    """Serialized Overview owner text must not expose registry/spec/database vocabulary."""
    sys.path.insert(0, str(ROOT))
    from api.service import AnalyticsService

    home = AnalyticsService().owner_home()
    texts = _project_with_node(home)
    assert texts, "projection returned no owner text"

    leaks = []
    for text in texts:
        for match in FORBIDDEN.finditer(text or ""):
            leaks.append(f"{match.group(0)!r} in {text[:160]!r}")
    assert not leaks, "Overview projection leaked technical tokens:\n" + "\n".join(leaks[:20])

    joined = "\n".join(texts)
    assert "Tenant dues outstanding" in joined
    assert "Def A" not in joined
    assert "v_outstanding_receivables" not in joined
