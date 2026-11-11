"""Tests for encrypted reverse maps and frozen redacted preview construction."""
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from app.confidentiality.preview import (
    build_review_preview,
    decode_jsonb,
    decrypt_reverse_map,
    encrypt_reverse_map,
    sha256_json,
)
from app.llm.prompt_builder import RuleData, FactData


def test_reverse_map_is_encrypted_and_tampering_fails(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(
        "app.confidentiality.preview.get_settings",
        lambda: SimpleNamespace(PREVIEW_ENCRYPTION_KEY=key),
    )
    mapping = {"[EMAIL-deadbeef]": "person@example.com"}
    encrypted = encrypt_reverse_map(mapping)
    assert "person@example.com" not in encrypted
    assert decrypt_reverse_map(encrypted) == mapping
    with pytest.raises(Exception):
        decrypt_reverse_map(encrypted[:-4] + "AAAA")


def test_decode_jsonb_accepts_asyncpg_string_and_native_objects():
    assert decode_jsonb('{"ok":true}', {}) == {"ok": True}
    assert decode_jsonb({"ok": True}, {}) == {"ok": True}
    assert decode_jsonb(None, []) == []


class FakeConn:
    def __init__(self, revision_id):
        self.revision_id = revision_id
        self.insert_args = None
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        if "SELECT id FROM revisions" in query:
            return {"id": str(self.revision_id)}
        self.insert_args = args
        return {"id": uuid4(), "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)}

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "UPDATE 0"

    @asynccontextmanager
    async def transaction(self):
        yield self


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


@pytest.mark.asyncio
async def test_preview_persists_only_redacted_provider_payload_and_counts(monkeypatch):
    from app.confidentiality import preview as preview_module

    raw_email = "private.person@example.com"
    org_id = uuid4()
    user_id = uuid4()
    revision_id = uuid4()
    kit_id = uuid4()
    supabase = MagicMock()
    supabase.get_revision.return_value = {
        "id": str(revision_id),
        "content_id": str(uuid4()),
        "body": f"Contact {raw_email} for details.",
    }
    supabase.get_content.return_value = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "status": "draft",
        "purpose": f"Campaign for {raw_email}",
        "channel": "web",
    }
    supabase.get_active_kit.return_value = {
        "id": str(kit_id),
        "version": 3,
        "visual_guidelines": {},
    }
    supabase.get_confidentiality_policy.return_value = None

    rules = [
        RuleData(
            rule_key="RULE-01",
            category="tone",
            severity="medium",
            title="Protect contact " + raw_email,
            guideline_text="Never disclose " + raw_email,
            check_kind="llm",
        )
    ]
    facts = [
        FactData(
            fact_key="FACT-01",
            statement="Email " + raw_email,
            source_note="Internal source " + raw_email,
            valid_until=None,
        )
    ]

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(
        preview_module,
        "get_settings",
        lambda: SimpleNamespace(PREVIEW_ENCRYPTION_KEY=key),
    )
    monkeypatch.setattr(preview_module, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(
        preview_module,
        "SupabaseDataLoader",
        lambda: SimpleNamespace(load_rules_and_facts=lambda _kit_id: (rules, facts)),
    )
    monkeypatch.setattr(preview_module, "_load_asset_manifest", AsyncMock(return_value=[]))

    conn = FakeConn(revision_id)
    class Pool:
        pool = FakePool(conn)

    result = await build_review_preview(
        revision_id, str(user_id), str(org_id), Pool()
    )

    assert result["image_consent_required"] is False
    assert raw_email not in result["redacted_draft"]
    assert raw_email not in result["text_provider_preview"]["user_content"]
    assert result["redaction_summary"]["total_matches"] >= 5

    persisted_payload = json.loads(conn.insert_args[9])
    encrypted_reverse_map = conn.insert_args[10]
    audit_detail = json.loads(conn.execute_calls[-1][1][3])
    serialized = json.dumps(persisted_payload, sort_keys=True)
    assert raw_email not in serialized
    assert raw_email not in encrypted_reverse_map
    assert raw_email not in json.dumps(audit_detail)
    assert persisted_payload["text_provider_request"]["user_content"] == result["text_provider_preview"]["user_content"]
    assert sha256_json(persisted_payload) == result["payload_sha256"]
    assert raw_email in decrypt_reverse_map(encrypted_reverse_map).values()
