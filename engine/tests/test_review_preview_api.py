"""Security tests for review preview confirmation and image-consent enforcement."""
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException, Response

from app.api.reviews import confirm_review_preview
from app.auth.dependencies import AuthUser
from app.models.api import ReviewConfirmRequest
from app.confidentiality.preview import (
    sha256_json, sha256_text, confidentiality_policy_sha256,
)
from app.confidentiality.models import ConfidentialityPolicy


class FakeConn:
    def __init__(self, preview, revision_id=None, review=None):
        self.preview = preview
        self.revision_id = revision_id
        self.review = review or {
            "id": uuid4(),
            "status": "queued",
            "kit_id": preview["kit_id"],
        }
        self.execute_calls = []
        self.fetchrow_calls = 0

    async def fetchrow(self, query, *args):
        self.fetchrow_calls += 1
        if "FROM review_previews" in query:
            return self.preview
        if "SELECT id FROM revisions" in query:
            return {"id": str(self.revision_id)}
        if "INSERT INTO reviews" in query:
            return self.review
        return None

    async def fetchval(self, query, *args):
        return 0

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        if "UPDATE review_previews" in query:
            self.preview["consumed_at"] = datetime.now(timezone.utc)
            self.preview["review_id"] = str(self.review["id"])
        return "UPDATE 1"

    @asynccontextmanager
    async def transaction(self):
        yield self


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def make_preview(user_id, org_id, revision_id, kit_id, token, *, has_images=False):
    payload = {
        "asset_manifest": ([{
            "id": str(uuid4()),
            "checksum": "a" * 64,
            "mime_type": "image/png",
            "width": 10,
            "height": 10,
        }] if has_images else []),
        "vision_provider_request": ({"system_instruction": "s", "user_content": "u"} if has_images else None),
    }
    return {
        "id": uuid4(),
        "org_id": user_id if False else org_id,
        "user_id": user_id,
        "revision_id": revision_id,
        "kit_id": kit_id,
        "policy_version": 1,
        "policy_sha256": confidentiality_policy_sha256(ConfidentialityPolicy(org_id=UUID(org_id))),
        "revision_sha256": sha256_text("draft"),
        "kit_sha256": sha256_json({
            "kit_id": str(kit_id),
            "version": 3,
            "rules": [],
            "facts": [],
            "visual_guidelines": {},
        }),
        "payload_sha256": sha256_json(payload),
        "payload": payload,
        "reverse_map_ciphertext": "encrypted",
        "redaction_summary": {"total_matches": 0},
        "asset_manifest": payload["asset_manifest"],
        "confirmation_token_sha256": sha256_text(token),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        "consumed_at": None,
        "confirmed_by": None,
        "image_consent_at": None,
        "review_id": None,
    }


@pytest.mark.asyncio
async def test_confirm_requires_explicit_consent_for_original_image_bytes():
    user_id, org_id, revision_id, kit_id = [str(uuid4()) for _ in range(4)]
    token = "x" * 48
    preview = make_preview(user_id, org_id, revision_id, kit_id, token, has_images=True)
    conn = FakeConn(preview)
    pool = SimpleNamespace(pool=FakePool(conn))
    user = AuthUser(user_id=user_id, org_id=org_id, roles=["creator"])

    with patch("app.api.reviews.get_db_pool", return_value=pool):
        with patch("app.api.reviews.get_supabase_client"):
            with patch("app.confidentiality.preview.decrypt_reverse_map", return_value={}):
                with pytest.raises(HTTPException) as exc:
                    await confirm_review_preview(
                        ReviewConfirmRequest(
                            preview_id=preview["id"],
                            confirmation_token=token,
                            consent_to_send_original_images=False,
                        ),
                        BackgroundTasks(),
                        Response(),
                        user,
                    )

    assert exc.value.status_code == 400
    assert "Explicit consent" in exc.value.detail
    assert conn.fetchrow_calls == 1
    assert conn.execute_calls == []


@pytest.mark.asyncio
async def test_confirm_atomically_consumes_preview_and_creates_review():
    user_id, org_id, revision_id, kit_id, content_id = [str(uuid4()) for _ in range(5)]
    token = "t" * 48
    preview = make_preview(user_id, org_id, revision_id, kit_id, token, has_images=False)
    conn = FakeConn(preview, revision_id=revision_id)
    pool = SimpleNamespace(pool=FakePool(conn))
    user = AuthUser(user_id=user_id, org_id=org_id, roles=["creator"])
    response = Response()
    supabase = MagicMock()
    supabase.get_revision.return_value = {
        "id": revision_id,
        "content_id": content_id,
        "body": "draft",
    }
    supabase.get_content.return_value = {
        "id": content_id,
        "org_id": org_id,
        "status": "draft",
    }
    supabase.get_active_kit.return_value = {
        "id": kit_id,
        "version": 3,
        "visual_guidelines": {},
    }
    supabase.get_confidentiality_policy.return_value = None
    fake_client = MagicMock()
    fake_client.rpc.return_value.execute.return_value.data = []
    supabase._get_client.return_value = fake_client
    background = BackgroundTasks()

    with patch("app.api.reviews.get_db_pool", return_value=pool):
        with patch("app.api.reviews.get_supabase_client", return_value=supabase):
            with patch("app.api.reviews.get_settings", return_value=SimpleNamespace(
                ENGINE_VERSION="test", PER_USER_RATE_LIMIT=10
            )):
                with patch("app.api.reviews.SupabaseDataLoader") as loader_cls:
                    loader_cls.return_value.load_rules_and_facts.return_value = ([], [])
                    with patch("app.api.reviews._check_user_rate_limit", return_value=(True, 0)):
                        with patch("app.api.reviews.run_review_pipeline"):
                            with patch("app.confidentiality.preview.decrypt_reverse_map", return_value={}):
                                result = await confirm_review_preview(
                                    ReviewConfirmRequest(
                                        preview_id=preview["id"],
                                        confirmation_token=token,
                                        consent_to_send_original_images=False,
                                    ),
                                    background,
                                    response,
                                    user,
                                )

    assert result.status == "queued"
    assert result.review_id == conn.review["id"]
    assert len(background.tasks) == 1
    assert preview["consumed_at"] is not None
    assert preview["review_id"] == str(conn.review["id"])
    assert any("review.preview_confirmed" in query for query, _ in conn.execute_calls)
    audit = next(args for query, args in conn.execute_calls if "review.preview_confirmed" in query)
    detail = json.loads(audit[3])
    assert detail["original_images_consent"] is False
    assert "private" not in json.dumps(detail)
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_confirm_rejects_replayed_preview():
    user_id, org_id, revision_id, kit_id = [str(uuid4()) for _ in range(4)]
    token = "z" * 48
    preview = make_preview(user_id, org_id, revision_id, kit_id, token)
    preview["consumed_at"] = datetime.now(timezone.utc)
    conn = FakeConn(preview)
    pool = SimpleNamespace(pool=FakePool(conn))
    user = AuthUser(user_id=user_id, org_id=org_id, roles=["creator"])

    with patch("app.api.reviews.get_db_pool", return_value=pool):
        with patch("app.api.reviews.get_supabase_client"):
            with pytest.raises(Exception) as exc:
                await confirm_review_preview(
                    ReviewConfirmRequest(preview_id=preview["id"], confirmation_token=token),
                    BackgroundTasks(),
                    Response(),
                    user,
                )
    assert "already been confirmed" in str(exc.value)


@pytest.mark.asyncio
async def test_confirm_rejects_wrong_org_without_revealing_preview():
    user_id, org_id, revision_id, kit_id = [str(uuid4()) for _ in range(4)]
    token = "a" * 48
    preview = make_preview(user_id, str(uuid4()), revision_id, kit_id, token)
    conn = FakeConn(preview)
    user = AuthUser(user_id=user_id, org_id=org_id, roles=["creator"])

    with patch("app.api.reviews.get_db_pool", return_value=SimpleNamespace(pool=FakePool(conn))):
        with patch("app.api.reviews.get_supabase_client"):
            with pytest.raises(Exception) as exc:
                await confirm_review_preview(
                    ReviewConfirmRequest(preview_id=preview["id"], confirmation_token=token),
                    BackgroundTasks(), Response(), user,
                )

    assert "not found" in str(exc.value).lower()
    assert conn.execute_calls == []


@pytest.mark.asyncio
async def test_confirm_rejects_invalid_confirmation_token():
    user_id, org_id, revision_id, kit_id = [str(uuid4()) for _ in range(4)]
    preview = make_preview(user_id, org_id, revision_id, kit_id, "b" * 48)
    conn = FakeConn(preview)
    user = AuthUser(user_id=user_id, org_id=org_id, roles=["creator"])

    with patch("app.api.reviews.get_db_pool", return_value=SimpleNamespace(pool=FakePool(conn))):
        with patch("app.api.reviews.get_supabase_client"):
            with pytest.raises(HTTPException) as exc:
                await confirm_review_preview(
                    ReviewConfirmRequest(preview_id=preview["id"], confirmation_token="c" * 48),
                    BackgroundTasks(), Response(), user,
                )

    assert exc.value.status_code == 403
    assert conn.execute_calls == []


@pytest.mark.asyncio
async def test_confirm_rejects_expired_preview():
    user_id, org_id, revision_id, kit_id = [str(uuid4()) for _ in range(4)]
    token = "d" * 48
    preview = make_preview(user_id, org_id, revision_id, kit_id, token)
    preview["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    conn = FakeConn(preview)
    user = AuthUser(user_id=user_id, org_id=org_id, roles=["creator"])

    with patch("app.api.reviews.get_db_pool", return_value=SimpleNamespace(pool=FakePool(conn))):
        with patch("app.api.reviews.get_supabase_client"):
            with patch("app.confidentiality.preview.decrypt_reverse_map", return_value={}):
                with pytest.raises(Exception) as exc:
                    await confirm_review_preview(
                        ReviewConfirmRequest(preview_id=preview["id"], confirmation_token=token),
                        BackgroundTasks(), Response(), user,
                    )

    assert "expired" in str(exc.value).lower()
    assert conn.execute_calls == []


@pytest.mark.asyncio
async def test_confirm_rejects_tampered_frozen_payload():
    user_id, org_id, revision_id, kit_id = [str(uuid4()) for _ in range(4)]
    token = "e" * 48
    preview = make_preview(user_id, org_id, revision_id, kit_id, token)
    preview["payload"]["text_provider_request"] = {
        "system_instruction": "tampered",
        "user_content": "not approved",
    }
    conn = FakeConn(preview)
    user = AuthUser(user_id=user_id, org_id=org_id, roles=["creator"])

    with patch("app.api.reviews.get_db_pool", return_value=SimpleNamespace(pool=FakePool(conn))):
        with patch("app.api.reviews.get_supabase_client"):
            with patch("app.confidentiality.preview.decrypt_reverse_map", return_value={}):
                with pytest.raises(Exception) as exc:
                    await confirm_review_preview(
                        ReviewConfirmRequest(preview_id=preview["id"], confirmation_token=token),
                        BackgroundTasks(), Response(), user,
                    )

    assert "integrity" in str(exc.value).lower()
    assert conn.execute_calls == []


@pytest.mark.asyncio
async def test_confirm_rejects_policy_contents_changed_without_version_bump():
    user_id, org_id, revision_id, kit_id, content_id = [str(uuid4()) for _ in range(5)]
    token = "p" * 48
    preview = make_preview(user_id, org_id, revision_id, kit_id, token)
    conn = FakeConn(preview, revision_id=revision_id)
    pool = SimpleNamespace(pool=FakePool(conn))
    user = AuthUser(user_id=user_id, org_id=org_id, roles=["creator"])
    supabase = MagicMock()
    supabase.get_revision.return_value = {
        "id": revision_id,
        "content_id": content_id,
        "body": "draft",
    }
    supabase.get_content.return_value = {
        "id": content_id,
        "org_id": org_id,
        "status": "draft",
    }
    supabase.get_active_kit.return_value = {
        "id": kit_id,
        "version": 3,
        "visual_guidelines": {},
    }
    fake_client = MagicMock()
    fake_client.rpc.return_value.execute.return_value.data = []
    supabase._get_client.return_value = fake_client

    changed_policy = ConfidentialityPolicy(
        org_id=UUID(org_id),
        version=1,
        custom_terms=("internal-only-project",),
    )

    with patch("app.api.reviews.get_db_pool", return_value=pool):
        with patch("app.api.reviews.get_supabase_client", return_value=supabase):
            with patch("app.api.reviews.get_settings", return_value=SimpleNamespace(
                ENGINE_VERSION="test", PER_USER_RATE_LIMIT=10
            )):
                with patch("app.api.reviews.SupabaseDataLoader") as loader_cls:
                    loader_cls.return_value.load_rules_and_facts.return_value = ([], [])
                    with patch("app.api.reviews.ConfidentialityPolicyStore") as policy_cls:
                        policy_cls.return_value.load_policy = AsyncMock(return_value=changed_policy)
                        with patch("app.confidentiality.preview.decrypt_reverse_map", return_value={}):
                            with pytest.raises(Exception) as exc:
                                await confirm_review_preview(
                                    ReviewConfirmRequest(
                                        preview_id=preview["id"],
                                        confirmation_token=token,
                                    ),
                                    BackgroundTasks(),
                                    Response(),
                                    user,
                                )

    assert "policy changed" in str(exc.value).lower()
    assert conn.execute_calls == []
