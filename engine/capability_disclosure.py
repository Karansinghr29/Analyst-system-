"""
capability_disclosure.py -- Phase 14. What the analytics layer can and cannot do, per section.

This module invents nothing. It reads `analysis_capability_registry.csv` (built in Phase 6 from
the specifications) and `analyst_roles.py` (whose roles already carry `domains`), and joins them
so an owner-facing section can state its own limits in its own words.

The reason this exists as a first-class surface rather than a footnote: the specifications
deliberately DECLINE to fix several thresholds -- materiality, anomaly bounds, statistical
method. A product that quietly omits those capabilities looks complete; a product that quietly
invents them is wrong. The third option, and the only honest one, is to name the capability, say
it is not supported, and say why. `NOT_IMPLEMENTED` and `PARTIAL` rows are therefore surfaced to
the owner with the same prominence as the implemented ones.

No capability is added here. If a capability is missing from the registry it is missing from the
product, and that is the correct outcome rather than something to paper over in the view layer.
"""
import csv
import os

from engine import analyst_roles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPABILITY_REGISTRY_PATH = os.path.join(ROOT, "analysis_capability_registry.csv")

STATUS_IMPLEMENTED = "IMPLEMENTED"
STATUS_PARTIAL = "PARTIAL"
STATUS_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"

# The four owner-facing sections. The first three are metric domains as spelled in
# semantic_metric_registry.csv; the fourth is the reasoning layer, which owns no metric domain
# of its own because it reasons ACROSS all of them.
SECTION_FINANCIAL = "financial"
SECTION_OPERATIONS = "operations"
SECTION_RISK = "risk"
SECTION_INSIGHTS = "insights"

SECTIONS = (SECTION_FINANCIAL, SECTION_OPERATIONS, SECTION_RISK, SECTION_INSIGHTS)

# section key -> (owner-facing title, registry domain or None, owner-facing purpose)
SECTION_SPEC = {
    SECTION_FINANCIAL: (
        "Financial", "Financial",
        "Money in, money owed, and what the ledger can prove about profitability."),
    SECTION_OPERATIONS: (
        "Operations", "Operations",
        "How the property is running day to day -- occupancy, maintenance, utilities, billing."),
    SECTION_RISK: (
        "Risk & Data Quality", "Risk & Data Quality",
        "Where the underlying records are incomplete, contradictory, or unverified, and which "
        "figures that affects."),
    SECTION_INSIGHTS: (
        "Business Insights", None,
        "What changed, what needs attention, and what the evidence does and does not support "
        "concluding."),
}

# The reasoning lenses. They serve every domain, so their capabilities belong to the
# cross-cutting section rather than to any single one.
CROSS_CUTTING_ROLES = ("business_analyst", "data_scientist", "bi_analyst",
                       "management_reporting_analyst", "decision_support_analyst")


def _read_registry(path=CAPABILITY_REGISTRY_PATH):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _roles_of(row):
    return tuple(r.strip() for r in (row.get("roles") or "").split(";") if r.strip())


class CapabilityDisclosure:
    """Answers 'what analysis can this section actually do?' from the registry alone."""

    def __init__(self, path=CAPABILITY_REGISTRY_PATH):
        self.rows = _read_registry(path)
        self._role_domains = {r.role_id: r.domains for r in analyst_roles.all_roles()}

    # -- placement ---------------------------------------------------------------------------

    def sections_for(self, row):
        """Which owner-facing sections a capability belongs to.

        Derived, not declared: a capability's roles determine its domains, and its domains
        determine its sections. A capability owned only by reasoning lenses lands in Business
        Insights, because that is the section that reasons across domains.
        """
        roles = _roles_of(row)
        if not roles:
            return ()
        if all(r in CROSS_CUTTING_ROLES for r in roles):
            return (SECTION_INSIGHTS,)

        domains = set()
        for r in roles:
            domains.update(self._role_domains.get(r, ()))

        out = []
        for key in (SECTION_FINANCIAL, SECTION_OPERATIONS, SECTION_RISK):
            if SECTION_SPEC[key][1] in domains:
                out.append(key)
        # A capability spanning every domain is also a cross-domain reasoning capability.
        if len(out) == 3:
            out.append(SECTION_INSIGHTS)
        return tuple(out)

    # -- owner-facing payload -----------------------------------------------------------------

    def for_section(self, section_key):
        """Capabilities of one section, split by whether they are actually supported.

        `limitations` carries the registry's own limitation text verbatim. Several of those
        sentences end with the exact NOT_DETERMINABLE phrase, and it is passed through
        unaltered -- paraphrasing it would soften a refusal the evidence requires.
        """
        supported, partial, unsupported = [], [], []
        for row in self.rows:
            if section_key not in self.sections_for(row):
                continue
            item = {
                "capability_id": row.get("capability_id", ""),
                "label": _label(row.get("capability_id", "")),
                "status": (row.get("status") or "").strip().upper(),
                "defined_by": row.get("defined_by", ""),
                "limitation": (row.get("limitation") or "").strip(),
            }
            if item["status"] == STATUS_IMPLEMENTED:
                supported.append(item)
            elif item["status"] == STATUS_PARTIAL:
                partial.append(item)
            else:
                unsupported.append(item)

        # Deduplicate the limitation sentences: several capabilities share the same underlying
        # reason (no threshold is fixed anywhere in the specifications), and repeating it four
        # times reads as four separate problems rather than one.
        seen, limitations = set(), []
        for item in partial + unsupported:
            text = item["limitation"]
            if text and text not in seen:
                seen.add(text)
                limitations.append(text)

        return {
            "supported": tuple(sorted(supported, key=lambda i: i["label"])),
            "partial": tuple(sorted(partial, key=lambda i: i["label"])),
            "unsupported": tuple(sorted(unsupported, key=lambda i: i["label"])),
            "limitations": tuple(limitations),
        }

    def summary(self):
        counts = {}
        for row in self.rows:
            status = (row.get("status") or "").strip().upper()
            counts[status] = counts.get(status, 0) + 1
        return {"total": len(self.rows), "by_status": counts}


def _label(capability_id):
    """`trend_analysis` -> `Trend analysis`. Presentation only."""
    if not capability_id:
        return ""
    words = capability_id.replace("_", " ").strip()
    return words[:1].upper() + words[1:]
