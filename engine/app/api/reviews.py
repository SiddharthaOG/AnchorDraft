"""Reviews API endpoints."""
import hmac
import json
import time
from datetime import datetime, timezone
from collections import defaultdict
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status, HTTPException

from app.auth.dependencies import (
    AuthUser,
    get_request_id,
    require_creator,
)
from app.auth.supabase import get_supabase_client
from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    RateLimitedError,
)
from app.models.api import (
    ReviewStartRequest,
    ReviewStartResponse,
    ReviewPreviewRequest,
    ReviewPreviewResponse,
    ReviewConfirmRequest,
    DAILY_REVIEW_CAP,
)
from app.store.db import get_db_pool
from app.pipeline import run_review_pipeline
from app.confidentiality.preview import (
    PreviewConfigurationError,
    build_review_preview,
    sha256_text,
    sha256_json,
    decode_jsonb,
    confidentiality_policy_sha256,
)
from app.confidentiality import ConfidentialityPolicyStore
from app.pipeline.orchestrator import SupabaseDataLoader

router = APIRouter()

# Simple in-memory rate limiter for per-user rate limiting
# Note: This is not globally reliable across multiple instances or restarts.
# In production, use a shared store (Redis, database, etc.)
_user_rate_limits: dict[str, list[float]] = defaultdict(list)


def _check_user_rate_limit(user_id: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Check if user has exceeded rate limit. Returns (allowed, retry_after_seconds)."""
    now = time.time()
    window_start = now - window_seconds
    user_requests = _user_rate_limits[user_id]
    # Remove expired requests
    _user_rate_limits[user_id] = [t for t in user_requests if t > window_start]
    if len(_user_rate_limits[user_id]) >= limit:
        oldest = min(_user_rate_limits[user_id])
        retry_after = int(oldest + window_seconds - time.time()) + 1
        return False, max(retry_after, 1)
    _user_rate_limits[user_id].append(now)
    return True, 0



@router.post(
    "/reviews/preview",
    response_model=ReviewPreviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review_preview(
    payload: ReviewPreviewRequest,
    response: Response,
    user: AuthUser = Depends(require_creator),
) -> ReviewPreviewResponse:
    """Prepare the exact redacted provider prompts; no provider is called here."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    pool = await get_db_pool()
    try:
        result = await build_review_preview(payload.revision_id, user.user_id, user.org_id, pool)
        return ReviewPreviewResponse(**result)
    except PreviewConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LookupError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise ConflictError("preview_not_available", str(exc)) from exc


@router.post(
    "/reviews/confirm",
    response_model=ReviewStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def confirm_review_preview(
    payload: ReviewConfirmRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    user: AuthUser = Depends(require_creator),
) -> ReviewStartResponse:
    """Atomically consume a preview and enqueue exactly one review."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    pool = await get_db_pool()
    supabase = get_supabase_client()
    token_hash = sha256_text(payload.confirmation_token)

    async with pool.pool.acquire() as conn:
        async with conn.transaction():
            preview = await conn.fetchrow(
                """
                SELECT * FROM review_previews
                WHERE id=$1
                FOR UPDATE
                """,
                payload.preview_id,
            )
            if (
                not preview
                or str(preview["org_id"]) != user.org_id
                or str(preview["user_id"]) != user.user_id
            ):
                raise NotFoundError("Review preview not found")
            if not hmac.compare_digest(str(preview["confirmation_token_sha256"]), token_hash):
                raise HTTPException(status_code=403, detail="Invalid preview confirmation token")
            if preview["consumed_at"] is not None:
                raise ConflictError("preview_already_consumed", "This preview has already been confirmed")
            if preview["expires_at"] <= datetime.now(timezone.utc):
                raise ConflictError("preview_expired", "This preview has expired; create a new preview")
            preview_payload = decode_jsonb(preview["payload"], {})
            if not isinstance(preview_payload, dict) or preview["payload_sha256"] != sha256_json(preview_payload):
                raise ConflictError("preview_integrity_failed", "Preview payload integrity check failed")
            assets = decode_jsonb(preview["asset_manifest"], [])
            if assets != (preview_payload.get("asset_manifest") or []):
                raise ConflictError("preview_integrity_failed", "Preview asset manifest integrity check failed")
            from app.confidentiality.preview import decrypt_reverse_map
            try:
                decrypt_reverse_map(preview["reverse_map_ciphertext"])
            except PreviewConfigurationError as exc:
                raise HTTPException(status_code=503, detail="Preview encryption is unavailable") from exc
            needs_image_consent = preview_payload.get("vision_provider_request") is not None
            if needs_image_consent and not payload.consent_to_send_original_images:
                raise HTTPException(
                    status_code=400,
                    detail="Explicit consent is required to send attached image bytes in their stored form to the vision provider",
                )
            if not needs_image_consent and payload.consent_to_send_original_images:
                raise HTTPException(status_code=400, detail="This preview will not send images to an AI provider")

            revision = await __import__("asyncio").to_thread(
                supabase.get_revision, str(preview["revision_id"])
            )
            if not revision:
                raise NotFoundError("Revision not found")
            content = await __import__("asyncio").to_thread(
                supabase.get_content, str(revision["content_id"])
            )
            if (
                not content
                or str(content.get("org_id")) != user.org_id
                or content.get("status") not in {"draft", "changes_requested"}
            ):
                raise ConflictError("revision_not_editable", "The revision is no longer eligible for review")
            if sha256_text(str(revision.get("body") or "")) != preview["revision_sha256"]:
                raise ConflictError("revision_changed", "The revision changed after preview; create a new preview")

            latest = await conn.fetchrow(
                "SELECT id FROM revisions WHERE content_id=$1 ORDER BY version DESC LIMIT 1",
                content["id"],
            )
            if not latest or str(latest["id"]) != str(preview["revision_id"]):
                raise ConflictError("not_latest_revision", "Only the latest revision can be reviewed")

            kit = await __import__("asyncio").to_thread(supabase.get_active_kit, user.org_id)
            if not kit or str(kit["id"]) != str(preview["kit_id"]):
                raise ConflictError("active_kit_changed", "The active brand kit changed after preview")

            loader = SupabaseDataLoader()
            rules, facts = await __import__("asyncio").to_thread(
                loader.load_rules_and_facts, str(kit["id"])
            )
            kit_fingerprint = {
                "kit_id": str(kit["id"]),
                "version": kit.get("version"),
                "rules": [__import__("dataclasses").asdict(item) for item in rules],
                "facts": [__import__("dataclasses").asdict(item) for item in facts],
                "visual_guidelines": kit.get("visual_guidelines") or {},
            }
            if sha256_json(kit_fingerprint) != preview["kit_sha256"]:
                raise ConflictError("kit_changed", "The brand kit changed after preview; create a new preview")

            policy = await ConfidentialityPolicyStore(supabase).load_policy(user.org_id)
            if (
                policy.version != preview["policy_version"]
                or confidentiality_policy_sha256(policy) != preview["policy_sha256"]
            ):
                raise ConflictError("policy_changed", "Confidentiality policy changed after preview")

            # Re-query revision associations and checksums immediately before consumption.
            import asyncio
            current_rows = await asyncio.to_thread(
                lambda: supabase._get_client().rpc(
                    "get_visual_assets_for_revision",
                    {"_revision_id": str(preview["revision_id"]), "_org_id": user.org_id},
                ).execute().data or []
            )
            current_ids = {str(item.get("id")) for item in current_rows}
            if current_ids != {str(item["id"]) for item in assets}:
                raise ConflictError("assets_changed", "Attached images changed after preview")
            for item in assets:
                current_asset = await asyncio.to_thread(
                    supabase.get_visual_asset, str(item["id"]), user.org_id
                )
                if not current_asset or str(current_asset.get("checksum")) != str(item["checksum"]):
                    raise ConflictError("asset_changed", "An attached image changed after preview")

            review_count = await conn.fetchval(
                "SELECT COUNT(*) FROM reviews WHERE org_id=$1 AND created_at >= CURRENT_DATE",
                user.org_id,
            )
            if review_count and review_count >= DAILY_REVIEW_CAP:
                raise RateLimitedError(
                    f"Daily review cap ({DAILY_REVIEW_CAP}) reached",
                    retry_after_seconds=86400,
                )
            allowed, retry_after = _check_user_rate_limit(
                user.user_id, get_settings().PER_USER_RATE_LIMIT, 60
            )
            if not allowed:
                raise RateLimitedError(
                    "Per-user review rate limit exceeded",
                    retry_after_seconds=retry_after,
                )

            review = await conn.fetchrow(
                """
                INSERT INTO reviews (org_id, revision_id, kit_id, engine_version, requested_by, preview_id)
                VALUES ($1,$2,$3,$4,$5,$6)
                RETURNING id, status, kit_id
                """,
                user.org_id, preview["revision_id"], preview["kit_id"],
                get_settings().ENGINE_VERSION, user.user_id, preview["id"],
            )
            await conn.execute(
                """
                UPDATE review_previews
                SET consumed_at=now(), confirmed_by=$2, image_consent_at=$3, review_id=$4
                WHERE id=$1 AND consumed_at IS NULL
                """,
                preview["id"], user.user_id,
                datetime.now(timezone.utc) if needs_image_consent else None,
                review["id"],
            )
            await conn.execute(
                """
                INSERT INTO audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
                VALUES ($1,$2,'review.preview_confirmed','review',$3,$4::jsonb)
                """,
                user.org_id, user.user_id, review["id"],
                json.dumps({
                    "preview_id": str(preview["id"]),
                    "payload_sha256": preview["payload_sha256"],
                    "policy_version": preview["policy_version"],
                    "asset_count": len(assets),
                    "original_images_consent": needs_image_consent,
                    "redaction_count": decode_jsonb(preview["redaction_summary"], {}).get("total_matches", 0),
                }),
            )

    background_tasks.add_task(run_review_pipeline, str(review["id"]))
    return ReviewStartResponse(
        review_id=UUID(str(review["id"])),
        status=str(review["status"]),
        deduplicated=False,
        kit_id=UUID(str(review["kit_id"])),
        kit_version=kit["version"],
    )


@router.post(
    "/reviews",
    status_code=status.HTTP_409_CONFLICT,
)
async def start_review(
    background_tasks: BackgroundTasks,
    request: Request,
    payload: ReviewStartRequest,
    user: AuthUser = Depends(require_creator),
    request_id: str = Depends(get_request_id),
) -> None:
    """Legacy direct-start endpoint: callers must use preview and confirmation."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "preview_required",
            "message": "Create a review preview and confirm it before starting a review.",
        },
    )
