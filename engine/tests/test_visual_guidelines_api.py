"""Owner-only visual guideline configuration API tests."""
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.kits import (
    UpdateKitNameRequest,
    UpdateVisualGuidelinesRequest,
    update_kit_name,
    update_visual_guidelines,
)
from app.auth.dependencies import AuthUser, require_owner


KIT_ID = UUID("11111111-1111-1111-1111-111111111111")
ORG_ID = "22222222-2222-2222-2222-222222222222"
USER_ID = "33333333-3333-3333-3333-333333333333"


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, rows):
        self.fetchrow = AsyncMock(side_effect=rows)
        self.execute = AsyncMock(return_value="INSERT 0 1")
        self.transaction = lambda: FakeTransaction()


class FakePool:
    def __init__(self, connection):
        self.pool = self
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def valid_guidelines():
    return {
        "logo": {
            "required": True,
            "clear_space_ratio": 0.12,
            "min_size_px": 48,
            "description": "White wordmark with a leaf icon",
            "variants": ["primary", "monochrome"],
        },
        "palette": {
            "colors": [{"name": "Primary", "hex": "#123456"}],
            "tolerance": 12,
            "allow_neutrals": True,
        },
        "contrast": {
            "min_ratio": 4.5,
            "level": "AA",
            "ignore_backgrounds": ["#FFFFFF"],
        },
    }


@pytest.mark.asyncio
async def test_owner_updates_draft_visual_guidelines_and_audits_metadata_only():
    saved = valid_guidelines()
    conn = FakeConnection([
        {"id": str(KIT_ID), "status": "draft"},
        {"visual_guidelines": saved},
    ])
    pool = FakePool(conn)
    user = AuthUser(USER_ID, ORG_ID, ["owner"])

    result = await update_visual_guidelines(
        KIT_ID,
        UpdateVisualGuidelinesRequest(visual_guidelines=saved),
        user,
        pool,
    )

    assert result == {"kit_id": str(KIT_ID), "visual_guidelines": saved}
    assert conn.fetchrow.await_count == 2
    assert conn.fetchrow.await_args_list[0].args[1:] == (KIT_ID, ORG_ID)
    update_args = conn.fetchrow.await_args_list[1].args
    assert update_args[1:3] == (KIT_ID, ORG_ID)
    assert json.loads(update_args[3]) == saved
    audit_args = conn.execute.await_args.args
    audit_metadata = json.loads(audit_args[4])
    assert audit_metadata == {
        "logo_configured": True,
        "palette_color_count": 1,
        "contrast_configured": True,
    }
    assert "0123456789abcdef" not in audit_args[4]
    assert "#123456" not in audit_args[4]


@pytest.mark.asyncio
async def test_visual_guideline_update_cannot_cross_organization_boundary():
    conn = FakeConnection([None])
    pool = FakePool(conn)
    user = AuthUser(USER_ID, ORG_ID, ["owner"])

    with pytest.raises(HTTPException) as exc:
        await update_visual_guidelines(
            KIT_ID,
            UpdateVisualGuidelinesRequest(visual_guidelines=valid_guidelines()),
            user,
            pool,
        )

    assert exc.value.status_code == 404
    assert conn.fetchrow.await_args.args[1:] == (KIT_ID, ORG_ID)
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_kit_visual_guidelines_are_immutable():
    conn = FakeConnection([{"id": str(KIT_ID), "status": "active"}])
    pool = FakePool(conn)
    user = AuthUser(USER_ID, ORG_ID, ["owner"])

    with pytest.raises(HTTPException) as exc:
        await update_visual_guidelines(
            KIT_ID,
            UpdateVisualGuidelinesRequest(visual_guidelines=valid_guidelines()),
            user,
            pool,
        )

    assert exc.value.status_code == 409
    conn.execute.assert_not_awaited()
    assert conn.fetchrow.await_count == 1


def test_non_owner_cannot_use_visual_guideline_update_dependency():
    with pytest.raises(HTTPException) as exc:
        require_owner(AuthUser(USER_ID, ORG_ID, ["manager"]))
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"visual_guidelines": {"logo": {"approved_hashes": ["0123456789abcdef"]}}},
        {"visual_guidelines": {"palette": {"colors": [{"name": "Primary", "hex": "blue"}]}}},
        {"visual_guidelines": {"contrast": {"min_ratio": 22}}},
        {"visual_guidelines": {"unknown": {"enabled": True}}},
        {"visual_guidelines": {"logo": {"required": True, "unexpected": "field"}}},
    ],
)
def test_invalid_visual_guideline_payloads_are_rejected(payload):
    with pytest.raises(ValidationError):
        UpdateVisualGuidelinesRequest.model_validate(payload)


def test_empty_visual_guidelines_can_clear_optional_visual_checks():
    result = UpdateVisualGuidelinesRequest.model_validate({"visual_guidelines": {}})
    assert result.visual_guidelines.model_dump(exclude_none=True) == {}


@pytest.mark.asyncio
async def test_owner_can_rename_draft_kit_and_audit_change():
    conn = FakeConnection([
        {"id": str(KIT_ID), "status": "draft", "name": "Original Kit"},
        {"name": "Campaign Brand Kit"},
    ])
    user = AuthUser(USER_ID, ORG_ID, ["owner"])

    result = await update_kit_name(
        KIT_ID,
        UpdateKitNameRequest(name="  Campaign Brand Kit  "),
        user,
        FakePool(conn),
    )

    assert result == {"kit_id": str(KIT_ID), "name": "Campaign Brand Kit"}
    assert conn.fetchrow.await_count == 2
    assert conn.fetchrow.await_args_list[1].args[1:4] == (KIT_ID, ORG_ID, "Campaign Brand Kit")
    assert conn.execute.await_args.args[3:5] == (KIT_ID, json.dumps(
        {"previous_name": "Original Kit", "name": "Campaign Brand Kit"},
        separators=(",", ":"),
    ))


@pytest.mark.asyncio
async def test_kit_rename_cannot_cross_organization_boundary():
    conn = FakeConnection([None])
    user = AuthUser(USER_ID, ORG_ID, ["owner"])

    with pytest.raises(HTTPException) as exc:
        await update_kit_name(KIT_ID, UpdateKitNameRequest(name="Renamed"), user, FakePool(conn))

    assert exc.value.status_code == 404
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_kit_cannot_be_renamed():
    conn = FakeConnection([{"id": str(KIT_ID), "status": "active", "name": "Active Kit"}])
    user = AuthUser(USER_ID, ORG_ID, ["owner"])

    with pytest.raises(HTTPException) as exc:
        await update_kit_name(KIT_ID, UpdateKitNameRequest(name="Changed"), user, FakePool(conn))

    assert exc.value.status_code == 409
    conn.execute.assert_not_awaited()
    assert conn.fetchrow.await_count == 1


def test_kit_name_is_trimmed_and_rejects_blank_or_oversized_values():
    assert UpdateKitNameRequest(name="  Brand Kit  ").name == "Brand Kit"
    with pytest.raises(ValidationError):
        UpdateKitNameRequest(name="   ")
    with pytest.raises(ValidationError):
        UpdateKitNameRequest(name="x" * 121)
