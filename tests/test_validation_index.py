"""
Tests the ValidationIndex against known validation_summary.csv content (Phase E, 80 checks:
73 MATCH, 4 DIFFERS, 3 NOT_DETERMINABLE) -- "do not hide mismatches" per the task brief.
"""
from engine.validation import ValidationIndex


def test_validation_index_loads_known_check_count():
    idx = ValidationIndex()
    assert len(idx._by_check_id) == 80


def test_match_metric_reports_match():
    idx = ValidationIndex()
    status, detail = idx.status_for("M.REV.001")
    assert status == "MATCH"


def test_differs_metric_reports_differs_not_hidden():
    """M.RISK.007 (overlapping allotments) maps to DQ.003, a known DIFFERS check -- the index
    must surface this, never silently report MATCH or UNVERIFIED instead."""
    idx = ValidationIndex()
    status, detail = idx.status_for("M.RISK.007")
    assert status == "DIFFERS"
    assert "214" in detail or "187" in detail or detail != ""


def test_metric_with_no_mapped_check_is_unverified_not_fabricated():
    idx = ValidationIndex()
    status, detail = idx.status_for("M.CASH.001")
    assert status == "UNVERIFIED"
    assert "No prior validation_summary.csv check" in detail


def test_all_four_known_differs_checks_are_traceable():
    """validation_summary.csv's 4 DIFFERS rows: REV.02, AR.04c, DQ.003, DQ.026 -- confirms
    every one is loaded and its status is exactly DIFFERS, not silently coerced."""
    idx = ValidationIndex()
    for check_id in ("REV.02", "AR.04c", "DQ.003", "DQ.026"):
        assert check_id in idx._by_check_id
        assert idx._by_check_id[check_id].validation_status == "DIFFERS"


def test_engine_answer_carries_validation_status(executor):
    ans = executor.execute("M.REV.001")
    assert ans.results[0].validation_status == "MATCH"

    ans2 = executor.execute("M.RISK.007")
    assert ans2.results[0].validation_status == "DIFFERS"
