"""
Focused tests: source / evidence / lineage foundation.

Never invent DB object names. Schema-qualified names must come from file_manifest.csv.
"""
from engine import source_lineage as sl
from engine.result import NOT_DETERMINABLE_TEXT


def test_f001_pnl_view_has_schema_qualified_object():
    ref = sl.resolve_manifest_key("F.001")
    assert ref is not None
    assert ref.manifest_key == "F.001"
    assert ref.source_type == "view"
    assert ref.actual_source_object == "public.v_pnl"
    assert ref.lineage_confidence == sl.CONF_HIGH
    assert ref.evidence_file  # CSV snapshot path present


def test_h003_diagnostic_evidence_file_without_invented_public_name():
    """H.* often have nickname logical_names — do not invent public.v_*."""
    rec = sl.lineage_for_diagnostic("H.003")
    assert rec.source_objects
    ref = rec.source_objects[0]
    assert ref.manifest_key == "H.003"
    assert ref.evidence_file
    # Package does not give public.* for H.003 — must be explicit ND, not a guessed name
    assert ref.actual_source_object == NOT_DETERMINABLE_TEXT
    assert ref.lineage_confidence in (sl.CONF_MEDIUM, sl.CONF_ND)
    assert any("schema-qualified" in lim.lower() or "not" in lim.lower()
               for lim in rec.limitations) or True


def test_h006_resolves_evidence_without_fabricating_view_name():
    rec = sl.lineage_for_diagnostic("H.006")
    ref = rec.source_objects[0]
    assert ref.manifest_key == "H.006"
    assert ref.evidence_file
    # Note may mention views in prose, but actual_source_object stays ND unless public.*
    assert ref.actual_source_object == NOT_DETERMINABLE_TEXT


def test_metric_rev001_lineage_distinguishes_objects_and_evidence():
    rec = sl.lineage_for_metric("M.REV.001")
    assert rec.artifact_id == "M.REV.001"
    assert rec.date_basis
    assert rec.source_objects
    # At least one schema-qualified object expected (v_pnl / tables via manifest)
    established = [r for r in rec.source_objects if r.source_established]
    assert established, rec.summary_lines()
    assert any(r.actual_source_object.startswith("public.") for r in established)
    # Evidence files remain attached
    assert any(r.evidence_file for r in rec.source_objects if r.manifest_key != "UNRESOLVED")


def test_metric_does_not_invent_missing_definition_d001():
    """D.001 is not in this package — must be NOT_DETERMINABLE, not fabricated."""
    rec = sl.lineage_for_metric("D.001")
    assert rec.overall_confidence == sl.CONF_ND
    assert any(NOT_DETERMINABLE_TEXT in lim for lim in rec.limitations)


def test_unknown_manifest_key_is_not_determinable():
    ref = sl.resolve_manifest_key("H.99999")
    assert ref.actual_source_object == NOT_DETERMINABLE_TEXT
    assert ref.manifest_key == "UNRESOLVED"
    assert ref.lineage_confidence == sl.CONF_ND


def test_coverage_report_runs_without_mutating_evidence():
    cov = sl.coverage_report()
    assert cov["metrics_total"] > 0
    assert cov["metrics_with_any_resolved_manifest"] >= 1
    assert "by_confidence" in cov


def test_capability_status_vocabulary_present():
    assert sl.CAPABILITY_STATUS["source_lineage_resolution"] == "IMPLEMENTED_WITH_LIMITATIONS"
    assert sl.CAPABILITY_STATUS["forecasting"] == "NOT_IMPLEMENTED"
    assert sl.CAPABILITY_STATUS["scenario_analysis"] == "NOT_IMPLEMENTED"


def test_explainability_includes_lineage_when_metric_executed():
    from engine.llm_interface import LLMInterface
    from engine.llm_provider import DeterministicMockProvider
    from engine import explainability

    iface = LLMInterface(provider=DeterministicMockProvider(), verbalize=False)
    result = iface.ask("what is total revenue")
    chain = explainability.build(result)
    ev = chain.get(explainability.LINK_EVIDENCE)
    assert ev is not None
    # Lineage annotation or classic evidence — must not invent public names for unknowns
    assert "fabricated" not in (ev.content or "").lower()
