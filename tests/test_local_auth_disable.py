"""
Focused smoke: local AI_ANALYTICS_AUTH_DISABLE opens the API; production never does.

Does not touch Trust Gate, authorization metric filters, calculators, or the LLM path.
"""
import os

import pytest
from fastapi.testclient import TestClient

from api.auth import (authenticator_from_env, DevOpenAuthenticator, FailClosedAuthenticator,
                      BearerAuthenticator, ENV_AUTH_DISABLE, ENV_NAME, ENV_SECRET)
from api.service import AnalyticsService, create_app


@pytest.fixture
def clean_auth_env(monkeypatch):
    monkeypatch.delenv(ENV_SECRET, raising=False)
    monkeypatch.delenv(ENV_AUTH_DISABLE, raising=False)
    monkeypatch.delenv(ENV_NAME, raising=False)


def test_local_auth_disable_allows_unauthenticated_api(clean_auth_env, monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_AUTH_DISABLE, "true")
    monkeypatch.setenv(ENV_NAME, "local")
    auth = authenticator_from_env()
    assert isinstance(auth, DevOpenAuthenticator)
    assert auth.describe()["enforced"] is False

    svc = AnalyticsService(db_path=str(tmp_path / "local_auth.db"), authenticator=auth)
    client = TestClient(create_app(svc, authenticator=auth))
    # No Authorization header — browser UAT without a pasted token.
    r = client.get("/api/owner/home")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "business_health" in body


def test_production_ignores_auth_disable(clean_auth_env, monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_AUTH_DISABLE, "true")
    monkeypatch.setenv(ENV_NAME, "production")
    auth = authenticator_from_env()
    assert isinstance(auth, FailClosedAuthenticator)
    assert auth.describe()["enforced"] is True

    svc = AnalyticsService(db_path=str(tmp_path / "prod_auth.db"), authenticator=auth)
    client = TestClient(create_app(svc, authenticator=auth))
    r = client.get("/api/owner/home")
    assert r.status_code == 401


def test_auth_disable_requires_exact_true(clean_auth_env, monkeypatch):
    monkeypatch.setenv(ENV_NAME, "development")
    monkeypatch.setenv(ENV_AUTH_DISABLE, "True")  # not the exact token
    assert isinstance(authenticator_from_env(), FailClosedAuthenticator)
    monkeypatch.setenv(ENV_AUTH_DISABLE, "true")
    assert isinstance(authenticator_from_env(), DevOpenAuthenticator)
    monkeypatch.setenv(ENV_SECRET, "not-for-production-secret")
    monkeypatch.delenv(ENV_AUTH_DISABLE, raising=False)
    assert isinstance(authenticator_from_env(), BearerAuthenticator)
