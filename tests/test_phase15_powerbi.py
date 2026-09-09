"""
Phase 15: Power BI consumes authorized engine/API payloads. It is not a calculation engine.
"""
import csv
import json
import os

from engine.bi_contract import (BIContractBuilder, validate_card,
                                RENDER_MULTI_DEFINITION, RENDER_BLOCKED,
                                RENDER_NOT_DETERMINABLE)
from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_dataset_descriptor_covers_all_50_metrics_and_forbids_authoring():
    desc = json.loads(open(os.path.join(ROOT, "powerbi_dataset_descriptor.json"),
                           encoding="utf-8").read())
    assert "No measure may be authored in the BI tool" in desc["authoring_rule"]
    ids = [m["metric_id"] for m in desc["measures"]]
    ids += [m["metric_id"] for m in desc["conflict_tables"]]
    ids += [m["metric_id"] for m in desc["unavailable_measures"]]
    assert desc["counts"]["total"] == 50
    assert len(set(ids)) == 50
    blob = json.dumps(desc).lower()
    assert "service_role" not in blob
    assert "password=" not in blob


def test_production_pages_bind_to_existing_api_not_sql():
    pages = json.loads(open(os.path.join(ROOT, "powerbi_production_pages.json"),
                            encoding="utf-8").read())
    names = [p["page"] for p in pages["pages"]]
    for required in ("Executive Overview", "Financial", "Operations",
                     "Risk & Data Quality", "Insights / Attention",
                     "Trust / Definition disclosures"):
        assert required in names
    blob = json.dumps(pages).lower()
    assert "sql" in pages["refresh"]["must_not"][0].lower() or "sql" in blob
    assert "postgres" in blob or "sql" in blob
    assert pages["role_visibility"]["source"].startswith("role_view_registry")
    for page in pages["pages"]:
        assert page["api"], page["page"]
        for path in page["api"]:
            assert path.startswith("/api/"), path


def test_owner_dashboard_registry_matches_the_gate(registry):
    gate = TrustGate(registry)
    path = os.path.join(ROOT, "owner_dashboard_registry.csv")
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows
    for row in rows:
        mid = row["metric_id"]
        d = gate.authorize(mid)
        permitted = row["headline_permitted"].strip() in ("True", "true", "1")
        assert permitted == d.headline_permitted, mid
        assert row["trust_level"] == d.effective_level, mid


def test_power_bi_cards_preserve_trust_render_rules(registry):
    bi = BIContractBuilder(registry=registry)
    occ = bi.card("M.OCC.001")
    assert occ.headline_permitted is False
    assert occ.value is None
    assert occ.render_directive == RENDER_MULTI_DEFINITION
    assert len(occ.definitions) >= 2
    assert validate_card(occ) == ()

    profit = bi.card("M.PROFIT.001")
    assert profit.headline_permitted is False
    assert profit.value is None
    assert profit.render_directive == RENDER_BLOCKED
    assert validate_card(profit) == ()

    nd = bi.card("M.OCC.003")
    assert nd.headline_permitted is False
    assert nd.value is None
    assert nd.render_directive == RENDER_NOT_DETERMINABLE
    assert NOT_DETERMINABLE_TEXT in (nd.not_determinable_reason or "")


def test_production_spec_keeps_supabase_quarantined_and_source_agnostic():
    spec = open(os.path.join(ROOT, "phase15_powerbi_production_spec.md"),
                encoding="utf-8").read()
    assert "QUARANTINED" in spec
    assert "Do **not** author DAX" in spec or "must not calculate" in spec.lower()
    assert "/api/" in spec
    assert "Remaining external Power BI Service steps" in spec
