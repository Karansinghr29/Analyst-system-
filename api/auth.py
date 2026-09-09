"""
auth.py -- Phase 11. Authenticated identity, fail-closed by default.

Authentication answers who the request is. Authorization (api/authorization.py) answers
which metrics that identity's ROLE may see. This module never reads, writes, or derives a
trust level.

The HTTP layer must not treat `x-role` as identity. A client-chosen role is not
authentication.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from api.authorization import Session, ROLE_OWNER, AuthorizationError

ENV_SECRET = "AI_ANALYTICS_AUTH_SECRET"
ENV_NAME = "AI_ANALYTICS_ENV"
ENV_AUTH_DISABLE = "AI_ANALYTICS_AUTH_DISABLE"

#
# A single-owner deployment behind an unlisted URL.
#
# The bearer machinery below is unchanged and stays enforcing: every API call still carries a
# token, the token is still HMAC-verified server-side, and the secret still never leaves the
# server. What this flag changes is only WHO TYPES THE TOKEN. With it set, the service will mint
# one for a browser that asks, instead of requiring the owner to paste a token an operator minted
# by hand.
#
# BE CLEAR ABOUT WHAT THAT MEANS: with this on, the URL is the credential. Anyone who learns the
# address can obtain a token and read the business. That is an acceptable trade only for a
# private, unlisted address held by one person, and it is why this is off unless a deployment
# explicitly turns it on -- it is never implied by anything else, and it is never a default.
#
# It is NOT the same as AI_ANALYTICS_AUTH_DISABLE: authentication still happens, tokens still
# expire, and the fail-closed path is untouched. A deployment with no secret configured cannot
# use this at all, because there is nothing to mint with.
#
ENV_OWNER_OPEN = "AI_ANALYTICS_OWNER_OPEN"
# Auth may be disabled only in these environments. Production (and unknown production-like
# values) never honour AI_ANALYTICS_AUTH_DISABLE.
LOCAL_ENV_NAMES = frozenset({"", "local", "development", "dev"})
TOKEN_TTL_SECONDS = 12 * 3600
TEST_SECRET = "phase11-test-secret-not-for-production"


class AuthenticationError(Exception):
    """The request has no acceptable identity. Maps to HTTP 401."""


@dataclass(frozen=True)
class Identity:
    """Provider-independent authenticated identity.

    `subject` is audit-only. Entitlements attach to `role_id`. Optional tenant/property
    claims cannot widen access; this export has one organization and one property.
    """
    subject: str
    role_id: str
    tenant_id: str = ""
    property_id: str = ""
    display_name: str = ""

    def session(self) -> Session:
        return Session(subject=self.subject, role_id=self.role_id,
                       display_name=self.display_name)


class IdentityVerifier:
    """The plug an IdP fills. verify(token) -> Identity or raise AuthenticationError."""

    def verify(self, token: str) -> Identity:
        raise NotImplementedError


class Authenticator:
    def authenticate(self, headers: dict) -> Identity:
        raise NotImplementedError

    def describe(self) -> dict:
        raise NotImplementedError


class FailClosedAuthenticator(Authenticator):
    """Production default when no IdP/secret is configured. Every API call is 401."""

    remaining = ("Set AI_ANALYTICS_AUTH_SECRET (HMAC bearer) or pass an IdentityVerifier "
                 "from the deployment's IdP. Client-supplied x-role is not identity.")

    def authenticate(self, headers: dict) -> Identity:
        raise AuthenticationError(self.remaining)

    def describe(self):
        return {
            "mode": "fail_closed",
            "enforced": True,
            "status": "QUARANTINED",
            "remaining_requirement": self.remaining,
        }


class DevOpenAuthenticator(Authenticator):
    """Local development only. Treats every request as the owner without a bearer token.

    Constructed only when AI_ANALYTICS_AUTH_DISABLE=true AND AI_ANALYTICS_ENV is a local
    development name. Production never receives this authenticator: authenticator_from_env()
    refuses the disable flag when the environment is production.
    """

    def authenticate(self, headers: dict) -> Identity:
        return Identity(subject="local-dev", role_id=ROLE_OWNER, display_name="Local owner")

    def describe(self):
        return {
            "mode": "dev_open",
            "enforced": False,
            "status": "LOCAL",
            "remaining_requirement": (
                "Authentication is disabled for local development only. "
                "Unset AI_ANALYTICS_AUTH_DISABLE (or set AI_ANALYTICS_ENV=production) "
                "before any shared or deployed use."
            ),
        }


class HmacVerifier(IdentityVerifier):
    """HMAC-SHA256 bearer tokens. An IdP that mints the same payload+mac is a drop-in."""

    def __init__(self, secret: str, ttl_seconds: int = TOKEN_TTL_SECONDS):
        if not secret or not str(secret).strip():
            raise AuthenticationError("HMAC verifier requires a non-empty secret.")
        self._secret = str(secret).encode("utf-8")
        self._ttl = ttl_seconds

    def verify(self, token: str) -> Identity:
        try:
            body_b64, mac_b64 = token.split(".", 1)
        except ValueError:
            raise AuthenticationError("Malformed bearer token.")
        expected = hmac.new(self._secret, body_b64.encode("ascii"), hashlib.sha256).digest()
        try:
            given = base64.urlsafe_b64decode(mac_b64 + "==")
        except Exception as e:
            raise AuthenticationError("Malformed bearer token.") from e
        if not hmac.compare_digest(expected, given):
            raise AuthenticationError("Invalid bearer token.")
        try:
            payload = json.loads(base64.urlsafe_b64decode(body_b64 + "=="))
        except Exception as e:
            raise AuthenticationError("Malformed bearer token.") from e
        exp = payload.get("exp")
        if exp is not None and float(exp) < time.time():
            raise AuthenticationError("Expired bearer token.")
        subject = str(payload.get("sub") or "").strip()
        role_id = str(payload.get("role") or "").strip()
        if not subject or not role_id:
            raise AuthenticationError("Token is missing sub or role.")
        return Identity(
            subject=subject, role_id=role_id,
            tenant_id=str(payload.get("tenant_id") or ""),
            property_id=str(payload.get("property_id") or ""),
            display_name=str(payload.get("display_name") or ""),
        )


class CallableVerifier(IdentityVerifier):
    """Wrap a deployment-supplied `fn(token) -> Identity`."""

    def __init__(self, fn):
        if fn is None:
            raise AuthenticationError("CallableVerifier requires a verify function.")
        self._fn = fn

    def verify(self, token: str) -> Identity:
        ident = self._fn(token)
        if not isinstance(ident, Identity):
            raise AuthenticationError("IdP verifier did not return an Identity.")
        return ident


class BearerAuthenticator(Authenticator):
    def __init__(self, verifier: IdentityVerifier):
        self.verifier = verifier

    def authenticate(self, headers: dict) -> Identity:
        raw = _header(headers, "authorization") or _header(headers, "Authorization")
        if not raw:
            raise AuthenticationError("Missing Authorization bearer token.")
        scheme, _, token = raw.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthenticationError("Authorization must be a Bearer token.")
        return self.verifier.verify(token.strip())

    def describe(self):
        return {
            "mode": "bearer",
            "enforced": True,
            "status": "TRUSTED",
            "remaining_requirement": "",
        }


def mint_token(secret: str, subject: str, role_id: str = ROLE_OWNER,
               ttl_seconds: int = TOKEN_TTL_SECONDS, **extra) -> str:
    """Mint an HMAC token. Used by tests and by an operator attaching a first identity.
    Not an IdP and not a login endpoint."""
    payload = {
        "sub": subject, "role": role_id,
        "exp": time.time() + ttl_seconds,
        "tenant_id": extra.get("tenant_id", ""),
        "property_id": extra.get("property_id", ""),
        "display_name": extra.get("display_name", ""),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return body.decode("ascii") + "." + base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def _env_name() -> str:
    return (os.environ.get(ENV_NAME) or "").strip().lower()


def auth_disable_requested() -> bool:
    """Exact token 'true' only. Any other value is ignored."""
    return (os.environ.get(ENV_AUTH_DISABLE) or "").strip() == "true"


def auth_disable_allowed() -> bool:
    """Disable is allowed only when the process is marked as local/development."""
    return _env_name() in LOCAL_ENV_NAMES


def authenticator_from_env() -> Authenticator:
    """Never enables a verifier at import. Empty secret → fail-closed.

    Local exception: AI_ANALYTICS_AUTH_DISABLE=true with AI_ANALYTICS_ENV in
    {unset, local, development, dev} yields DevOpenAuthenticator. That combination is
    refused when AI_ANALYTICS_ENV=production so a mis-set flag cannot open a deploy.
    """
    if auth_disable_requested():
        if auth_disable_allowed():
            return DevOpenAuthenticator()
        # Production (or any non-local env): ignore the flag and continue fail-closed /
        # bearer selection below. Never silently open the API.
    secret = os.environ.get(ENV_SECRET)
    if secret:
        return BearerAuthenticator(HmacVerifier(secret))
    return FailClosedAuthenticator()


def owner_open_requested() -> bool:
    """Exact token 'true' only, matching the disable flag's strictness."""
    return (os.environ.get(ENV_OWNER_OPEN) or "").strip() == "true"


def owner_session_token() -> str:
    """A token for the owner's browser, minted server-side.

    Returns "" unless the deployment has BOTH asked for an open owner session and configured a
    secret to sign with -- so this can never hand out a token on a service that was not
    deliberately set up to do so, and never on one with no verification behind it.

    The secret does not leave the server. What crosses to the browser is an ordinary bearer
    token with the ordinary TTL, verified on every subsequent call by the same verifier that
    checks an operator-minted one.
    """
    secret = os.environ.get(ENV_SECRET)
    if not owner_open_requested() or not secret:
        return ""
    return mint_token(secret, subject="owner", role_id=ROLE_OWNER, display_name="Owner")


def hmac_authenticator(secret: str) -> BearerAuthenticator:
    return BearerAuthenticator(HmacVerifier(secret))


def suite_authenticator() -> BearerAuthenticator:
    """HMAC authenticator for automated tests. Never used as a production default."""
    return hmac_authenticator(TEST_SECRET)


def bearer_headers(role_id: str = ROLE_OWNER, subject: str = "owner") -> dict:
    return {"Authorization": f"Bearer {mint_token(TEST_SECRET, subject, role_id)}"}


def _header(headers, name):
    if headers is None:
        return None
    # Starlette/FastAPI headers are case-insensitive mappings; dicts from tests may not be.
    if hasattr(headers, "get"):
        v = headers.get(name)
        if v:
            return v
        lower = {str(k).lower(): v for k, v in (headers.items() if hasattr(headers, "items") else [])}
        return lower.get(name.lower())
    return None
