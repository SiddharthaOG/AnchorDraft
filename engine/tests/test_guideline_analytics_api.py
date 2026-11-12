import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.analytics.guideline_gaps import summarize_rule_decisions
from app.auth.dependencies import AuthUser
from app.api import guideline_analytics as api
from app.core.config import clear_settings_cache


class FakeConnection:
    def __init__(self):
        self.execute = AsyncMock()
        self.fetchrow = AsyncMock(return_value={
            "id": "00000000-0000-0000-0000-000000000010",
            "expires_at": datetime.now(timezone.utc),
        })


class FakePool:
    def __init__(self):
        self.conn = FakeConnection()
        self.pool = self
        self.fetch_calls = []
        self.fetchrow_calls = []

    @asynccontextmanager
    async def acquire(self):
        yield self.conn

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return {"id": "kit-1", "version": 3, "name": "Test Kit"}

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        if "select rule_key, category::text as category" in query:
            return [{
                "rule_key": "CLAIM-01",
                "category": "claim",
                "title": "Substantiate claims",
                "guideline_text": "Avoid unsupported claims about AcmeSecret products.",
            }]
        if "from public.guideline_suggestions" in query:
            return []
        return [
            {"rule_key": "CLAIM-01", "action": "dismiss", "reason": "Too vague for our brand", "source_version": 1},
            {"rule_key": "CLAIM-01", "action": "dismiss", "reason": "The wording is too vague", "source_version": 2},
            {"rule_key": "CLAIM-01", "action": "dismiss", "reason": "Too vague for the style guide", "source_version": 2},
            {"rule_key": "CLAIM-01", "action": "dismiss", "reason": "Wording feels too vague", "source_version": 3},
            {"rule_key": "CLAIM-01", "action": "accept", "reason": None, "source_version": 3},
        ]


class FakeSupabase:
    def get_confidentiality_policy(self, org_id):
        return {
            "org_id": org_id,
            "version": 2,
            "enabled": True,
            "custom_terms": ["AcmeSecret"],
            "redact_emails": True,
            "redact_phones": True,
            "redact_api_keys": True,
            "redact_jwts": True,
            "redact_credit_cards": True,
        }


@pytest.mark.asyncio
async def test_suggestion_preview_redacts_sensitive_terms_before_persisting_provider_payload(monkeypatch):
    monkeypatch.setenv("PREVIEW_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    clear_settings_cache()
    monkeypatch.setattr(api, "get_supabase_client", lambda: FakeSupabase())
    pool = FakePool()
    user = AuthUser("00000000-0000-0000-0000-000000000002", "00000000-0000-0000-0000-000000000001", ["manager"])

    result = await api.create_suggestion_preview("CLAIM-01", user, pool)

    assert result["preview_id"] == "00000000-0000-0000-0000-000000000010"
    assert "AcmeSecret" not in result["user_content"]
    assert "[CUSTOM_TERM-" in result["user_content"]
    assert result["redaction_summary"]["total_matches"] >= 1

    persisted_request = json.loads(pool.conn.fetchrow.await_args.args[9])
    assert "AcmeSecret" not in persisted_request["user_content"]
    assert "[CUSTOM_TERM-" in persisted_request["user_content"]
    assert pool.conn.fetchrow.await_args.args[11]  # encrypted reverse map retained only server-side
    clear_settings_cache()


def test_manager_or_owner_authorization_rejects_reviewer():
    reviewer = AuthUser("00000000-0000-0000-0000-000000000003", "00000000-0000-0000-0000-000000000001", ["reviewer"])
    with pytest.raises(HTTPException) as exc:
        api.require_manager_or_owner(reviewer)
    assert exc.value.status_code == 403


def test_manager_or_owner_authorization_accepts_owner_and_manager():
    assert api.require_manager_or_owner(AuthUser("00000000-0000-0000-0000-000000000004", "00000000-0000-0000-0000-000000000001", ["owner"])).user_id == "00000000-0000-0000-0000-000000000004"
    assert api.require_manager_or_owner(AuthUser("00000000-0000-0000-0000-000000000005", "00000000-0000-0000-0000-000000000001", ["manager"])).user_id == "00000000-0000-0000-0000-000000000005"


def test_analytics_thresholds_require_sample_and_repeated_cluster():
    sparse = summarize_rule_decisions([
        {"action": "dismiss", "reason": "Too vague for our brand", "source_version": 1},
        {"action": "dismiss", "reason": "The wording is too vague", "source_version": 1},
        {"action": "accept", "reason": None, "source_version": 1},
    ])
    assert sparse["is_gap"] is False


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConfirmConnection:
    def __init__(self, rows):
        self.fetchrow = AsyncMock(side_effect=rows)
        self.execute = AsyncMock()
        self.transaction = lambda: FakeTransaction()


class FakeConfirmPool:
    def __init__(self, connection):
        self.pool = self
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


@pytest.mark.asyncio
async def test_confirm_consumes_preview_and_persists_typed_suggestion(monkeypatch):
    from datetime import timedelta
    from app.models.pipeline import ProviderResult
    from app.confidentiality.preview import sha256_text

    token = "one-time-confirmation-token-123456789"
    guideline = "Avoid unsupported claims about AcmeSecret products."
    now = datetime.now(timezone.utc)
    preview = {
        "id": "00000000-0000-0000-0000-000000000010",
        "org_id": "00000000-0000-0000-0000-000000000001",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "consumed_at": None,
        "expires_at": now + timedelta(minutes=5),
        "token_hash": sha256_text(token),
        "source_kit_id": "kit-1",
        "rule_key": "CLAIM-01",
        "source_guideline_hash": sha256_text(guideline),
        "policy_version": 2,
        "policy_sha256": "b" * 64,
        "provider_request": {
            "system_instruction": "Edit the guideline.",
            "user_content": "Current: [CUSTOM_TERM-12345678]",
            "output_schema": {
                "type": "object",
                "properties": {
                    "suggested_text": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["suggested_text", "explanation"],
            },
            "randomness": 0.1,
            "output_limit": 1024,
            "timeout_seconds": 45,
        },
        "evidence": {"decided": 5, "dismissed": 4, "reason_clusters": []},
        "reverse_map_ciphertext": "encrypted-map",
        "redaction_summary": {"total_matches": 1, "policy_version": 2},
        "payload_sha256": "a" * 64,
    }
    suggestion = {
        "id": "suggestion-1",
        "status": "pending",
        "rule_key": "CLAIM-01",
        "suggested_text": "Substantiate material product claims with approved evidence.",
        "explanation": "Clarifies the evidence expected.",
        "source_kit_version": 3,
        "created_at": now,
    }
    conn = FakeConfirmConnection([
        preview,
        {"id": "kit-1", "version": 3},
        {"guideline_text": guideline},
        suggestion,
    ])
    pool = FakeConfirmPool(conn)
    user = AuthUser(
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000001",
        ["manager"],
    )

    class FakePolicy:
        version = 2

    class FakePolicyStore:
        def __init__(self, _supabase):
            pass

        async def load_policy(self, _org_id):
            return FakePolicy()

    class FakeProvider:
        async def generate_findings(self, request):
            assert "[CUSTOM_TERM-12345678]" in request.user_content
            return ProviderResult(
                raw_json=json.dumps({
                    "suggested_text": "Substantiate material product claims with approved evidence.",
                    "explanation": "Clarifies the evidence expected.",
                }),
                input_tokens=10,
                output_tokens=20,
                model="fake-model",
                latency_ms=1,
                finish_reason="stop",
            )

    monkeypatch.setattr(api, "ConfidentialityPolicyStore", FakePolicyStore)
    monkeypatch.setattr(api, "confidentiality_policy_sha256", lambda _policy: "b" * 64)
    monkeypatch.setattr(api, "decrypt_reverse_map", lambda _ciphertext: {})
    monkeypatch.setattr(api, "get_provider_with_fallback", lambda: FakeProvider())
    monkeypatch.setattr(api, "get_settings", lambda: type("Settings", (), {"LLM_PROVIDER": "fake"})())

    result = await api.confirm_suggestion_preview(
        "00000000-0000-0000-0000-000000000010",
        api.PreviewConfirmRequest(confirmation_token=token),
        user,
        pool,
    )

    assert result["id"] == "suggestion-1"
    assert result["status"] == "pending"
    assert result["model"] == "fake-model"
    assert conn.fetchrow.await_count == 4
    assert any("consumed_at=now()" in call.args[0] for call in conn.execute.await_args_list)


@pytest.mark.asyncio
async def test_fake_provider_returns_explicit_placeholder_for_suggestion_schema():
    from app.llm.fake_provider import FakeProvider
    from app.models.pipeline import ProviderRequest

    request = ProviderRequest(
        system_instruction="Rewrite the rule.",
        user_content="Current guideline: be clear.",
        output_schema={
            "type": "object",
            "properties": {
                "suggested_text": {"type": "string"},
                "explanation": {"type": "string"},
            },
            "required": ["suggested_text", "explanation"],
        },
    )
    result = await FakeProvider().generate_findings(request)
    output = json.loads(result.raw_json)

    assert output["suggested_text"]
    assert "Fake-provider placeholder" in output["explanation"]


@pytest.mark.asyncio
async def test_rule_history_uses_only_completed_reviews_and_scopes_to_kit_org():
    pool = FakePool()
    await api._rule_history(pool, "kit-1")

    query, args = pool.fetch_calls[0]
    assert "review_record.status = 'done'" in query
    assert "source_kit.org_id = active_rule.org_id" in query
    assert "source_kit.org_id = (select org_id from public.brand_kits where id = $1)" in query
    assert args == ("kit-1",)


@pytest.mark.asyncio
async def test_analytics_query_is_scoped_to_authenticated_organization():
    pool = FakePool()
    user = AuthUser(
        "00000000-0000-0000-0000-000000000005",
        "00000000-0000-0000-0000-000000000099",
        ["manager"],
    )

    result = await api.list_guideline_gaps(user, pool)

    assert result["kit"]["id"] == "kit-1"
    query, args = pool.fetchrow_calls[0]
    assert "where org_id = $1 and status = 'active'" in query
    assert args == (user.org_id,)


@pytest.mark.asyncio
async def test_accept_endpoint_passes_verified_actor_to_service_rpc():
    from types import SimpleNamespace

    suggestion_id = UUID("00000000-0000-0000-0000-000000000099")
    user = AuthUser(
        "00000000-0000-0000-0000-000000000005",
        "00000000-0000-0000-0000-000000000001",
        ["manager"],
    )
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={
        "kit_id": "new-kit",
        "version": 5,
        "status": "accepted",
    }))

    result = await api.accept_suggestion(suggestion_id, user, pool)

    assert result == {"status": "accepted", "kit_id": "new-kit", "version": 5}
    query, suggestion_arg, actor_arg = pool.fetchrow.await_args.args
    assert "accept_guideline_suggestion($1, $2)" in query
    assert suggestion_arg == suggestion_id
    assert actor_arg == user.user_id


@pytest.mark.asyncio
async def test_reject_endpoint_passes_verified_actor_and_bounded_reason_to_service_rpc():
    from types import SimpleNamespace

    suggestion_id = UUID("00000000-0000-0000-0000-000000000098")
    user = AuthUser(
        "00000000-0000-0000-0000-000000000005",
        "00000000-0000-0000-0000-000000000001",
        ["owner"],
    )
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={"status": "rejected"}))
    body = api.RejectSuggestionRequest(reason="This changes the approved meaning.")

    result = await api.reject_suggestion(suggestion_id, body, user, pool)

    assert result == {"status": "rejected"}
    query, suggestion_arg, actor_arg, reason_arg = pool.fetchrow.await_args.args
    assert "reject_guideline_suggestion($1, $2, $3)" in query
    assert suggestion_arg == suggestion_id
    assert actor_arg == user.user_id
    assert reason_arg == body.reason


@pytest.mark.asyncio
async def test_accept_endpoint_reports_stale_suggestion_as_conflict():
    from types import SimpleNamespace

    suggestion_id = UUID("00000000-0000-0000-0000-000000000097")
    user = AuthUser(
        "00000000-0000-0000-0000-000000000005",
        "00000000-0000-0000-0000-000000000001",
        ["manager"],
    )
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={
        "kit_id": None,
        "version": None,
        "status": "stale",
    }))

    with pytest.raises(HTTPException) as exc:
        await api.accept_suggestion(suggestion_id, user, pool)
    assert exc.value.status_code == 409
    assert exc.value.detail["error"]["code"] == "suggestion_stale"
