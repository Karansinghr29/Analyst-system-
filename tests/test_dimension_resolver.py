"""
Grain protection and dimension-resolution tests (ai_analytics_architecture.md 6,
question_understanding_spec.md 4).
"""
import pytest

from engine.dimension_resolver import (
    resolve, resolve_for_comparison, UnsupportedDimensionError, DegenerateDimensionError,
)


class TestGrainProtection:
    def test_known_dimension_on_supporting_metric_resolves(self, registry):
        spec = registry.get("M.REV.001")  # grain includes property_id
        rd = resolve(spec, filters={"property_id": "x"})
        assert rd.filters == {"property_id": "x"}

    def test_unknown_dimension_is_rejected(self, registry):
        spec = registry.get("M.REV.001")
        with pytest.raises(UnsupportedDimensionError):
            resolve(spec, filters={"not_a_real_dimension": "x"})

    def test_dimension_not_in_metrics_grain_is_rejected(self, registry):
        """M.OWN.001's grain does not document tenant_id support (owner payments have no
        tenant relationship) -- a tenant_id filter must be refused, not silently applied."""
        spec = registry.get("M.OWN.001")
        with pytest.raises(UnsupportedDimensionError):
            resolve(spec, filters={"tenant_id": "x"})


class TestDegenerateDimension:
    def test_property_comparison_refused_with_specific_reason(self, registry):
        spec = registry.get("M.OCC.001")
        with pytest.raises(DegenerateDimensionError, match="1 distinct value"):
            resolve_for_comparison(spec, "property_id")

    def test_organization_comparison_also_refused(self, registry):
        spec = registry.get("M.REV.001")
        with pytest.raises(DegenerateDimensionError):
            resolve_for_comparison(spec, "organization_id")

    def test_non_degenerate_dimension_comparison_is_allowed(self, registry):
        spec = registry.get("M.AR.002")
        rd = resolve_for_comparison(spec, "tenant_id")
        assert rd.group_by == ("tenant_id",)

    def test_property_dimension_actually_degenerate_in_data(self):
        """Confirms the degenerate-dimension guard reflects reality: exactly 1 property."""
        from engine.evidence_loader import load_table
        props = load_table("properties")
        assert len(props) == 1
