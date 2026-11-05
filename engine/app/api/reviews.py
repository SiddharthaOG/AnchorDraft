"""Reviews API endpoints."""
import hashlib
import time
from collections import defaultdict
from uuid import UUID
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.auth.dependencies import (
    AuthUser,
    get_current_user_single_org,
    get_request_id,
    require_creator,
)
from app.auth.supabase import get_supabase_client
from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    RateLimitedError,
    map_db_exception,
)
from app.models.api import (
    ReviewStartRequest,
    ReviewStartResponse,
    ReviewStatus,
    LLMStatus,
    DAILY_REVIEW_CAP,
    DBErrorCodes,
    ErrorCode,
)
from app.store.db import get_db_pool

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
    "/reviews",
    response_model=ReviewStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"description": "Review deduplicated, existing review returned"},
        202: {"description": "New review created"},
        401: {"description": "Unauthenticated"},
        403: {"description": "Forbidden - not a creator"},
        404: {"description": "Revision not found or not accessible"},
        409: {"description": "Conflict - not latest revision, not editable, no active kit, etc."},
        429: {"description": "Daily review cap reached"},
    },
)
async def start_review(
    request: Request,
    payload: ReviewStartRequest,
    user: AuthUser = Depends(require_creator),
    request_id: str = Depends(get_request_id),
) -> ReviewStartResponse | JSONResponse:
    """Start a review for a revision.

    Idempotent: returns existing review if one is queued, running, or completed successfully.
    """
    settings = get_settings()
    revision_id = payload.revision_id
    pool = await get_db_pool()
    supabase = get_supabase_client()

    # 1. Verify revision exists and get its content (via Supabase - read only)
    revision = supabase.get_revision(str(revision_id))
    if not revision:
        raise NotFoundError("Revision not found")

    # 2. Verify user's org matches revision's org (via content)
    content = supabase.get_content(revision["content_id"])
    if not content:
        raise NotFoundError("Content not found")

    if content["org_id"] != user.org_id:
        # Don't leak existence - return 404
        raise NotFoundError("Revision not found")

    # 3. Check content status is editable (draft or changes_requested)
    content_status = content["status"]
    if content_status not in ("draft", "changes_requested"):
        raise ConflictError("not_editable", "Content is not editable")

    # 4. Check revision is the latest revision of its content
    async with pool.pool.acquire() as conn:
        latest_revision = await conn.fetchrow(
            """
            SELECT id FROM revisions
            WHERE content_id = $1
            ORDER BY version DESC
            LIMIT 1
            """,
            content["id"],
        )

    if not latest_revision or latest_revision["id"] != str(revision_id):
        raise ConflictError("not_latest_revision", "Only the latest revision can be reviewed")

    # 5. Get active kit for the organization
    kit = supabase.get_active_kit(user.org_id)
    if not kit:
        raise ConflictError("no_active_kit", "Organization has no active brand kit")

    # 6. Idempotency check and daily cap check - all in one transaction with two advisory locks
    # Lock acquisition order: revision lock first, then org/day lock (consistent order to avoid deadlocks)
    # Use signed 64-bit for single-arg advisory lock, signed 32-bit for two-arg lock
    revision_lock_id = int.from_bytes(
        hashlib.md5(str(revision_id).encode()).digest()[:8],
        "big",
        signed=True,
    )

    # Org/day lock: use org_id hash and day number since epoch (both fit in signed 32-bit)
    from datetime import date, timezone
    org_hash = int.from_bytes(hashlib.md5(str(user.org_id).encode()).digest()[:4], "big", signed=True)

    async with pool.pool.acquire() as conn:
        async with conn.transaction():
            # 1. Acquire revision-level advisory lock (for idempotency)
            await conn.execute("SELECT pg_advisory_xact_lock($1)", revision_lock_id)

            # 2. Look up existing queued/running review
            existing_queued = await conn.fetchrow(
                """
                SELECT id, status, kit_id FROM reviews
                WHERE revision_id = $1
                  AND status IN ('queued', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                revision_id,
            )
            if existing_queued:
                return ReviewStartResponse(
                    review_id=UUID(existing_queued["id"]),
                    status=existing_queued["status"],
                    deduplicated=True,
                    kit_id=UUID(existing_queued["kit_id"]),
                    kit_version=kit["version"],
                )

            # 3. Look up existing completed review with llm_status IN ('ok', 'skipped')
            existing_completed = await conn.fetchrow(
                """
                SELECT id, status, kit_id FROM reviews
                WHERE revision_id = $1
                  AND status = 'done'
                  AND llm_status IN ('ok', 'skipped')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                revision_id,
            )
            if existing_completed:
                return ReviewStartResponse(
                    review_id=UUID(existing_completed["id"]),
                    status=existing_completed["status"],
                    deduplicated=True,
                    kit_id=UUID(existing_completed["kit_id"]),
                    kit_version=kit["version"],
                )

            # 4. Obtain PostgreSQL's current date for the org/day lock
            db_date = await conn.fetchval("SELECT CURRENT_DATE")
            epoch_day = (db_date - date(1970, 1, 1)).days
            org_hash = int.from_bytes(hashlib.md5(str(user.org_id).encode()).digest()[:4], "big", signed=True)
            day_hash = epoch_day & 0x7FFFFFFF  # fit in signed 32-bit

            # 4. Acquire organization/day-level advisory lock (for daily cap serialization)
            # Use two-int advisory lock: (org_hash, day_hash) - both signed 32-bit
            await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", org_hash, day_hash)

            # 5. Check daily review cap (uses PostgreSQL's CURRENT_DATE)
            review_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM reviews
                WHERE org_id = $1
                  AND created_at >= CURRENT_DATE
                """,
                user.org_id,
            )

            if review_count and review_count >= DAILY_REVIEW_CAP:
                raise RateLimitedError(
                    f"Daily review cap ({DAILY_REVIEW_CAP}) reached",
                    retry_after_seconds=86400,  # 24 hours
                )

            # 6. Check per-user rate limit
            allowed, retry_after = _check_user_rate_limit(
                user.user_id,
                settings.PER_USER_RATE_LIMIT,
                60,  # 1 minute window
            )
            if not allowed:
                raise RateLimitedError(
                    f"Per-user rate limit ({settings.PER_USER_RATE_LIMIT} requests per minute) exceeded",
                    retry_after_seconds=retry_after,
                )

            # 6. Insert new queued review
            review = await conn.fetchrow(
                """
                INSERT INTO reviews (org_id, revision_id, kit_id, engine_version, requested_by)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, status, kit_id
                """,
                user.org_id,
                str(revision_id),
                str(kit["id"]),
                settings.ENGINE_VERSION,
                user.user_id,
            )

            if not review:
                raise RuntimeError("Failed to create review")

            return ReviewStartResponse(
                review_id=UUID(review["id"]),
                status=review["status"],
                deduplicated=False,
                kit_id=UUID(review["kit_id"]),
                kit_version=kit["version"],
            )