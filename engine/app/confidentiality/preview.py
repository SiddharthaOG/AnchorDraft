"""Preview construction and cryptographic helpers for consent-gated reviews."""
from __future__ import annotations

import hashlib
import json
import secrets
import re
from datetime import datetime, timedelta, timezone
from dataclasses import asdict, replace
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from app.auth.supabase import get_supabase_client
from app.confidentiality import ConfidentialityEngine, ConfidentialityPolicyStore
from app.core.config import get_settings
from app.llm.prompt_builder import (
    FactData, PromptInput, RuleData, build_provider_request,
)
from app.models.pipeline import ProviderRequest
from app.pipeline.orchestrator import SupabaseDataLoader
from app.visual.vision_providers import (
    VISION_SYSTEM_INSTRUCTION, VISUAL_OUTPUT_SCHEMA, build_vision_user_content,
)
from app.llm.prompt_builder import generate_nonce


class PreviewConfigurationError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().PREVIEW_ENCRYPTION_KEY
    if not key:
        raise PreviewConfigurationError("PREVIEW_ENCRYPTION_KEY is required for review previews")
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise PreviewConfigurationError("PREVIEW_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_reverse_map(mapping: dict[str, str]) -> str:
    return _fernet().encrypt(
        json.dumps(mapping, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def decrypt_reverse_map(ciphertext: str) -> dict[str, str]:
    try:
        decoded = _fernet().decrypt(ciphertext.encode("ascii"))
        value = json.loads(decoded)
    except (InvalidToken, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreviewConfigurationError("Preview reverse map cannot be decrypted") from exc
    if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise PreviewConfigurationError("Preview reverse map has an invalid structure")
    return value


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def confidentiality_policy_sha256(policy) -> str:
    """Fingerprint every policy input that can change redaction behavior."""
    return sha256_json({
        "org_id": str(policy.org_id),
        "version": policy.version,
        "enabled": policy.enabled,
        "custom_terms": list(policy.custom_terms),
        "redact_emails": policy.redact_emails,
        "redact_phones": policy.redact_phones,
        "redact_api_keys": policy.redact_api_keys,
        "redact_jwts": policy.redact_jwts,
        "redact_credit_cards": policy.redact_credit_cards,
    })


def decode_jsonb(value: Any, fallback: Any = None) -> Any:
    """Decode asyncpg JSONB values, which may be returned as serialized strings."""
    if value is None:
        return fallback
    if isinstance(value, str):
        return json.loads(value)
    return value


def _flatten_strings(value: Any, prefix: str, output: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _flatten_strings(nested, f"{prefix}.{key}", output)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _flatten_strings(nested, f"{prefix}[{index}]", output)
    elif isinstance(value, str):
        output[prefix] = value


def _restore_shape(value: Any, prefix: str, redacted: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _restore_shape(nested, f"{prefix}.{key}", redacted) for key, nested in value.items()}
    if isinstance(value, list):
        return [_restore_shape(nested, f"{prefix}[{index}]", redacted) for index, nested in enumerate(value)]
    if isinstance(value, str):
        return redacted[prefix]
    return value


async def _load_asset_manifest(supabase, revision_id: str, org_id: str) -> list[dict]:
    import asyncio

    def fetch():
        response = supabase._get_client().rpc(
            "get_visual_assets_for_revision",
            {"_revision_id": revision_id, "_org_id": org_id},
        ).execute()
        return response.data or []

    rows = await asyncio.to_thread(fetch)
    manifest = []
    for row in rows:
        asset_id = str(row.get("id") or "")
        if not asset_id:
            raise ValueError("Visual asset association returned an invalid asset")
        asset = await asyncio.to_thread(supabase.get_visual_asset, asset_id, org_id)
        if not asset:
            raise ValueError("A linked visual asset is unavailable")
        manifest.append({
            "id": asset_id,
            "checksum": str(asset.get("checksum") or ""),
            "mime_type": str(asset.get("mime_type") or ""),
            "width": int(asset.get("width") or 0),
            "height": int(asset.get("height") or 0),
        })
        if not re.fullmatch(r"[0-9a-fA-F]{64}", manifest[-1]["checksum"]) or manifest[-1]["mime_type"] not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("A linked visual asset has invalid integrity metadata")
    return manifest


async def build_review_preview(revision_id: UUID, user_id: str, org_id: str, pool) -> dict:
    """Build and persist a redacted preview. Never persist source values or image bytes."""
    _fernet()  # Fail closed before loading user data if encryption is not configured.
    supabase = get_supabase_client()
    revision = await __import__("asyncio").to_thread(supabase.get_revision, str(revision_id))
    if not revision:
        raise LookupError("Revision not found")
    content = await __import__("asyncio").to_thread(supabase.get_content, str(revision["content_id"]))
    if not content or str(content.get("org_id")) != str(org_id):
        raise LookupError("Revision not found")
    if content.get("status") not in {"draft", "changes_requested"}:
        raise ValueError("Content is not editable")

    async with pool.pool.acquire() as conn:
        latest = await conn.fetchrow(
            "SELECT id FROM revisions WHERE content_id=$1 ORDER BY version DESC LIMIT 1",
            content["id"],
        )
    if not latest or str(latest["id"]) != str(revision_id):
        raise ValueError("Only the latest revision can be previewed")

    kit = await __import__("asyncio").to_thread(supabase.get_active_kit, org_id)
    if not kit:
        raise ValueError("Organization has no active brand kit")

    loader = SupabaseDataLoader()
    rules, facts = await __import__("asyncio").to_thread(loader.load_rules_and_facts, kit["id"])
    policy = await ConfidentialityPolicyStore(supabase).load_policy(org_id)
    engine = ConfidentialityEngine()

    visual_guidelines = kit.get("visual_guidelines") or {}
    if not isinstance(visual_guidelines, dict):
        raise ValueError("Brand kit visual guidelines are invalid")

    fields: dict[str, str] = {
        "draft_text": str(revision.get("body") or ""),
        "purpose": str(content.get("purpose") or ""),
        "channel": str(content.get("channel") or ""),
    }
    for index, rule in enumerate(rules):
        fields[f"rule_{index}_key"] = rule.rule_key
        fields[f"rule_{index}_title"] = rule.title
        fields[f"rule_{index}_guideline_text"] = rule.guideline_text
    for index, fact in enumerate(facts):
        fields[f"fact_{index}_key"] = fact.fact_key
        fields[f"fact_{index}_statement"] = fact.statement
        fields[f"fact_{index}_source_note"] = fact.source_note

    guideline_fields: dict[str, str] = {}
    _flatten_strings(visual_guidelines, "visual_guidelines", guideline_fields)
    fields.update(guideline_fields)
    redaction = engine.redact_fields(fields, policy)

    redacted_rules = [
        replace(rule, rule_key=redaction.fields[f"rule_{index}_key"],
                title=redaction.fields[f"rule_{index}_title"],
                guideline_text=redaction.fields[f"rule_{index}_guideline_text"])
        for index, rule in enumerate(rules)
    ]
    redacted_facts = [
        replace(fact, fact_key=redaction.fields[f"fact_{index}_key"],
                statement=redaction.fields[f"fact_{index}_statement"],
                source_note=redaction.fields[f"fact_{index}_source_note"])
        for index, fact in enumerate(facts)
    ]
    redacted_guidelines = _restore_shape(
        visual_guidelines, "visual_guidelines", redaction.fields
    )

    text_request = build_provider_request(PromptInput(
        draft_text=redaction.fields["draft_text"],
        purpose=redaction.fields["purpose"],
        channel=redaction.fields["channel"],
        rules=redacted_rules,
        facts=redacted_facts,
        max_findings=25,
    ))
    assets = await _load_asset_manifest(supabase, str(revision_id), org_id)

    vision_request = None
    if assets and redacted_guidelines:
        nonce = generate_nonce()
        vision_request = ProviderRequest(
            system_instruction=VISION_SYSTEM_INSTRUCTION.format(max_findings=25),
            user_content=build_vision_user_content(
                draft_text=redaction.fields["draft_text"],
                purpose=redaction.fields["purpose"],
                channel=redaction.fields["channel"],
                visual_guidelines=redacted_guidelines,
                asset_ids=[item["id"] for item in assets],
                nonce=nonce,
            ),
            output_schema=VISUAL_OUTPUT_SCHEMA,
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=60,
        )

    payload = {
        "text_provider_request": text_request.model_dump(mode="json"),
        "vision_provider_request": vision_request.model_dump(mode="json") if vision_request else None,
        "redacted_fields": dict(redaction.fields),
        "redacted_rules": [asdict(rule) for rule in redacted_rules],
        "redacted_facts": [asdict(fact) for fact in redacted_facts],
        "asset_manifest": assets,
        "redacted_visual_guidelines": redacted_guidelines,
        "has_visual_provider_request": vision_request is not None,
    }
    revision_hash = sha256_text(str(revision.get("body") or ""))
    kit_fingerprint = {
        "kit_id": str(kit["id"]),
        "version": kit.get("version"),
        "rules": [asdict(item) for item in rules],
        "facts": [asdict(item) for item in facts],
        "visual_guidelines": visual_guidelines,
    }
    kit_hash = sha256_json(kit_fingerprint)
    policy_hash = confidentiality_policy_sha256(policy)
    payload_hash = sha256_json(payload)
    token = secrets.token_urlsafe(32)
    redaction_summary = {
        "total_matches": redaction.summary.total_matches,
        "by_type": dict(redaction.summary.by_type),
        "original_chars": redaction.summary.original_chars,
        "redacted_chars": redaction.summary.redacted_chars,
        "policy_version": redaction.summary.policy_version,
    }

    response_assets = []
    for item in assets:
        asset_record = await __import__("asyncio").to_thread(
            supabase.get_visual_asset, item["id"], org_id
        )
        storage_path = asset_record.get("storage_path") if asset_record else None
        signed_url = None
        if storage_path:
            signed = await __import__("asyncio").to_thread(
                lambda path=storage_path: supabase._get_client()
                .storage.from_("visual-assets").create_signed_url(path, 600)
            )
            if isinstance(signed, dict):
                signed_url = signed.get("signedURL") or signed.get("signedUrl")
        response_assets.append({**item, "preview_url": signed_url})

    # Start the 10-minute approval window only after all expensive preview work.
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    async with pool.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE review_previews
                SET reverse_map_ciphertext='', payload='{}'::jsonb, asset_manifest='[]'::jsonb
                WHERE reverse_map_ciphertext <> ''
                  AND (
                    (consumed_at IS NULL AND expires_at < now())
                    OR (consumed_at IS NOT NULL AND consumed_at < now() - interval '1 day')
                  )
                """
            )
            row = await conn.fetchrow(
                """
                INSERT INTO review_previews (
                    org_id, user_id, revision_id, kit_id, policy_version, policy_sha256,
                    revision_sha256, kit_sha256, payload_sha256, payload,
                    reverse_map_ciphertext, redaction_summary, asset_manifest,
                    confirmation_token_sha256, expires_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12::jsonb,$13::jsonb,$14,$15)
                RETURNING id, expires_at
                """,
                UUID(org_id), UUID(user_id), revision_id, UUID(kit["id"]), policy.version, policy_hash,
                revision_hash, kit_hash, payload_hash,
                json.dumps(payload, default=str), encrypt_reverse_map(dict(redaction.placeholder_map)),
                json.dumps(redaction_summary), json.dumps(assets), sha256_text(token), expires_at,
            )
            await conn.execute(
                """
                INSERT INTO audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
                VALUES ($1,$2,'review.preview_created','review_preview',$3,$4::jsonb)
                """,
                UUID(org_id), UUID(user_id), row["id"],
                json.dumps({
                    "redaction_count": redaction.summary.total_matches,
                    "redaction_by_type": dict(redaction.summary.by_type),
                    "policy_version": policy.version,
                    "asset_count": len(assets),
                    "payload_sha256": payload_hash,
                }),
            )

    return {
        "preview_id": str(row["id"]),
        "revision_id": str(revision_id),
        "confirmation_token": token,
        "expires_at": row["expires_at"].isoformat(),
        "redacted_draft": redaction.fields["draft_text"],
        "text_provider_preview": {
            "system_instruction": text_request.system_instruction,
            "user_content": text_request.user_content,
        },
        "vision_provider_preview": ({
            "system_instruction": vision_request.system_instruction,
            "user_content": vision_request.user_content,
        } if vision_request else None),
        "assets": response_assets,
        "image_consent_required": vision_request is not None,
        "redaction_summary": redaction_summary,
        "payload_sha256": payload_hash,
    }
