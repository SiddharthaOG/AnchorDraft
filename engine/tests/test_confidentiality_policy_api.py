"""Endpoint-level tests for organization confidentiality policy management."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.confidentiality import ConfidentialityPolicyUpdate, _safe_policy
from app.auth.dependencies import AuthUser, get_current_user, get_current_user_single_org
from httpx import ASGITransport, AsyncClient


def create_test_app():
    from app.main import create_app
    return create_app()


ORG_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class Query:
    def __init__(self, response, owner=None):
        self.response = response
        self.owner = owner
        self.values = None

    def upsert(self, values, on_conflict=None):
        self.values = values
        return self

    def insert(self, values):
        self.values = values
        if self.owner is not None:
            self.owner.audit = values
        return self

    def select(self, _columns):
        return self

    def single(self):
        return self

    def execute(self):
        if self.response is not None:
            self.response.data = {**self.values, "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "version": 1}
            if self.owner is not None and self.response is self.owner.policy_response:
                if self.owner.policy is not None:
                    self.response.data["version"] = self.owner.policy["version"] + 1
                self.owner.policy = dict(self.response.data)
        return self.response


class FakeSupabase:
    def __init__(self):
        self.saved = None
        self.audit = None
        self.policy = None
        self.policy_response = SimpleNamespace(data=None)
        self.audit_response = SimpleNamespace(data=[{"id": 1}])
        self.client = self

    def get_confidentiality_policy(self, org_id):
        return self.policy

    def _get_client(self):
        return self

    def table(self, name):
        if name == "confidentiality_policies":
            return Query(self.policy_response, self)
        if name == "audit_log":
            return Query(self.audit_response, self)
        raise AssertionError(f"Unexpected table: {name}")


@pytest.fixture
def fake_supabase(monkeypatch):
    from app.api import confidentiality
    client = FakeSupabase()
    monkeypatch.setattr(confidentiality, "get_supabase_client", lambda: client)
    return client


@pytest.mark.asyncio
async def test_owner_can_read_default_policy_and_update_it(fake_supabase):
    app = create_test_app()
    app.dependency_overrides[get_current_user_single_org] = lambda: AuthUser(USER_ID, ORG_ID, ["owner"])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v1/organizations/me/confidentiality-policy")
            assert response.status_code == 200
            assert response.json()["custom_terms"] == []
            assert response.json()["enabled"] is True
            assert response.headers["Cache-Control"] == "no-store"

            response = await client.put(
                "/v1/organizations/me/confidentiality-policy",
                json={"custom_terms": ["ORCHID-VAULT-ALPHA"], "enabled": True},
            )
            assert response.status_code == 200
            assert response.headers["Cache-Control"] == "no-store"
            assert response.json()["custom_terms"] == ["ORCHID-VAULT-ALPHA"]
            assert response.json()["version"] == 1
            response = await client.put(
                "/v1/organizations/me/confidentiality-policy",
                json={"custom_terms": ["ORCHID-VAULT-ALPHA", "NEVER-SEND-ORIGINAL-TEXT-7F92"]},
            )
            assert response.status_code == 200
            assert response.json()["version"] == 2
            assert fake_supabase.audit["action"] == "confidentiality.policy_updated"
            assert fake_supabase.audit["detail"]["custom_term_count"] == 2
            assert "ORCHID-VAULT-ALPHA" not in str(fake_supabase.audit)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["manager", "creator", "reviewer"])
async def test_non_owner_cannot_read_or_update_policy(fake_supabase, role):
    app = create_test_app()
    app.dependency_overrides[get_current_user_single_org] = lambda: AuthUser(USER_ID, ORG_ID, [role])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            read = await client.get("/v1/organizations/me/confidentiality-policy")
            write = await client.put("/v1/organizations/me/confidentiality-policy", json={"custom_terms": ["private"]})
            assert read.status_code == 403
            assert write.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_unauthenticated_user_cannot_read_or_update_policy(fake_supabase):
    app = create_test_app()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            read = await client.get("/v1/organizations/me/confidentiality-policy")
            write = await client.put(
                "/v1/organizations/me/confidentiality-policy",
                json={"custom_terms": ["private"]},
            )
            assert read.status_code == 401
            assert write.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_multiple_organization_memberships_are_rejected(fake_supabase):
    app = create_test_app()
    app.dependency_overrides[get_current_user] = lambda: AuthUser(USER_ID, "", [])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v1/organizations/me/confidentiality-policy")
            assert response.status_code == 400
            assert response.json()["detail"]["error"]["reason"] == "multiple_memberships"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_policy_update_rejects_unknown_org_override(fake_supabase):
    app = create_test_app()
    app.dependency_overrides[get_current_user_single_org] = lambda: AuthUser(USER_ID, ORG_ID, ["owner"])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.put(
                "/v1/organizations/me/confidentiality-policy",
                json={"custom_terms": ["private"], "org_id": "22222222-2222-2222-2222-222222222222"},
            )
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()

@pytest.mark.parametrize("terms", [
    ["", "valid"],
    ["   "],
    ["duplicate", "DUPLICATE"],
    ["x" * 257],
    [f"term-{i}" for i in range(501)],
])
def test_policy_update_rejects_invalid_custom_terms(terms):
    with pytest.raises(ValidationError):
        ConfidentialityPolicyUpdate(custom_terms=terms)


def test_policy_update_rejects_aggregate_term_limit():
    with pytest.raises(ValidationError):
        ConfidentialityPolicyUpdate(custom_terms=["x" * 256 for _ in range(79)])


def test_policy_update_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ConfidentialityPolicyUpdate(custom_terms=[], org_id="another-org")


def test_safe_policy_does_not_expose_database_metadata():
    record = {
        "id": "policy-id", "org_id": ORG_ID, "version": 3, "enabled": True,
        "custom_terms": ["Internal Project"], "redact_emails": True,
        "redact_phones": True, "redact_api_keys": True, "redact_jwts": True,
        "redact_credit_cards": True, "updated_by": USER_ID, "created_at": "now",
    }
    result = _safe_policy(record, ORG_ID)
    assert result["custom_terms"] == ["Internal Project"]
    assert "updated_by" not in result
    assert "id" not in result