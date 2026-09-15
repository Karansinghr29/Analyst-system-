"""
authorization.py -- Phase 9 (W3). The authorization boundary.

The single rule that shapes this module, and the reason it is small:

    Authorization decides WHICH metrics a role may see.
    It never decides HOW those metrics are gated.

Trust is a property of the evidence, not of the viewer. A senior role does not get a looser
posture on a conflicted metric; it gets the same conflict, disclosed the same way. An
authorization layer that could relax a BLOCK for an executive would defeat the entire trust gate
-- and it would do so invisibly, because the answer would look authoritative.

`filter_metrics()` therefore returns a SUBSET of metric ids and nothing else. There is no code
path here that reads, writes, or derives a trust level.

NOT built here, deliberately: credential storage, password handling, token issuance, or an
identity-provider integration. Those require an IdP and real secret management; faking them would
produce something that looks like authentication and is not. `Session` accepts an already-
authenticated identity from whatever IdP a deployment uses.
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry
from engine import analyst_roles

# The owner sees the curated cockpit; every analyst role sees its registry domains. `owner` is a
# presentation role, not a tenth analyst lens -- it maps onto the management-reporting lens.
ROLE_OWNER = "owner"

PRESENTATION_ROLES = {
    ROLE_OWNER: analyst_roles.MANAGEMENT_REPORTING,
}


class AuthorizationError(Exception):
    """Raised when a request names a role that does not exist. Never raised to hide a metric --
    an unauthorized metric is absent from the listing, not an error, so a client cannot probe
    for what exists by reading error codes."""


@dataclass(frozen=True)
class Session:
    """An already-authenticated identity. This module does not authenticate; it authorizes.

    `subject` is whatever the deployment's IdP established. It is carried for audit only -- no
    authorization decision reads it, because entitlements attach to the ROLE, not the person.
    """
    subject: str
    role_id: str
    display_name: str = ""

    @property
    def analyst_role(self):
        return PRESENTATION_ROLES.get(self.role_id, self.role_id)


class Authorizer:
    def __init__(self, registry: SemanticRegistry = None):
        self.registry = registry or SemanticRegistry()

    # -- roles -----------------------------------------------------------------------------------

    def known_roles(self):
        """Every role id a REQUEST may name. `owner` is one of them, so it must stay here."""
        out = [ROLE_OWNER] + [r.role_id for r in analyst_roles.all_roles()]
        return tuple(dict.fromkeys(out))

    def workspace_roles(self):
        """The analyst lenses that exist, in the order the role registry defines them.

        `owner` is deliberately absent. It is an identity, not a tenth lens: `PRESENTATION_ROLES`
        presents it THROUGH the management-reporting lens, so describing it produces a record
        identical to that lens in every field a workspace card shows -- same name, same focus,
        same visible-measure count, same "never" policy -- and the page rendered the same
        workspace twice, both cards opening the same one.

        Listing the lenses themselves is the fix: each appears once because each IS its own
        lens. Nothing about authorization changes -- `known_roles` still admits `owner`, and
        `resolve` still maps it to the same lens it always did.
        """
        return tuple(r.role_id for r in analyst_roles.all_roles())

    def resolve(self, role_id):
        if role_id not in self.known_roles():
            raise AuthorizationError(
                f"{role_id!r} is not a known role. Known roles: "
                f"{', '.join(self.known_roles())}")
        return analyst_roles.role(PRESENTATION_ROLES.get(role_id, role_id))

    # -- the only authorization decision ------------------------------------------------------------

    def filter_metrics(self, role_id, metric_ids=None):
        """Which of these metrics may this role see?

        Returns a subset. Never a trust level, never a modified payload -- so there is no
        mechanism by which this function could change how a visible metric is gated.
        """
        role = self.resolve(role_id)
        candidates = list(metric_ids if metric_ids is not None else self.registry.all_ids())
        return tuple(m for m in candidates
                     if m in self.registry
                     and self.registry.get(m).domain in role.domains)

    def may_see(self, role_id, metric_id):
        return metric_id in self.filter_metrics(role_id, [metric_id])

    def describe(self, role_id):
        role = self.resolve(role_id)
        visible = self.filter_metrics(role_id)
        # What the workspace is about, by the same rule `role_workspace` applies. `visible` is
        # what the role may open; the workspace count is what its page is scoped to.
        from engine import role_scope
        scope = role_scope.workspace_scope(role, tuple(visible))
        return {
            "role_id": role_id,
            "analyst_role": role.role_id,
            "display_name": role.display_name,
            "focus": role.owner_focus or role.semantic_scope,
            "domains": list(role.domains),
            "visible_metric_count": len(visible),
            "workspace_metric_count": len(scope.scope_ids),
            "capabilities": list(role.capabilities),
            "never_does": role.never_does,
            "trust_note": ("Authorization determines which metrics are visible. It never "
                           "changes how a visible metric is gated: trust is a property of the "
                           "evidence, not of the viewer."),
        }
