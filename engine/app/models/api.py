"""Pydantic models for API requests and responses."""
from typing import Optional, List
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from enum import Enum


class ErrorCode(str, Enum):
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    TOO_LARGE = "too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    INTERNAL_ERROR = "internal_error"


class ConflictReason(str, Enum):
    NOT_EDITABLE = "not_editable"
    NOT_LATEST_REVISION = "not_latest_revision"
    NO_ACTIVE_KIT = "no_active_kit"
    KIT_TOO_LARGE = "kit_too_large"
    NO_EXTRACTABLE_TEXT = "no_extractable_text"
    MULTIPLE_MEMBERSHIPS = "multiple_memberships"


class APIError(BaseModel):
    """Standard error response."""
    code: ErrorCode
    reason: Optional[str] = None
    message: str
    request_id: str
    retry_after_seconds: Optional[int] = None


class ErrorResponse(BaseModel):
    """Standard error response wrapper."""
    error: APIError


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    time: str
    database: Optional[bool] = None


# Review endpoints
class ReviewStartRequest(BaseModel):
    """Request to start a review."""
    revision_id: UUID


class ReviewStartResponse(BaseModel):
    """Response from starting a review."""
    review_id: UUID
    status: str
    deduplicated: bool
    kit_id: UUID
    kit_version: int


class ReviewStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class LLMStatus(str, Enum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


# Import endpoints
class ImportTextResponse(BaseModel):
    """Response from text import."""
    text: str
    pages: int
    char_count: int
    truncated: bool
    warnings: List[str] = []


# Kit lint endpoints
class LintIssue(BaseModel):
    """Single lint issue."""
    severity: str  # "error" or "warning"
    code: str
    ref_key: Optional[str] = None
    message: str


class LintStats(BaseModel):
    """Kit lint statistics."""
    rules: int
    facts: int
    llm_rules: int
    deterministic_rules: int
    prompt_chars_estimate: int
    prompt_chars_cap: int


class KitLintResponse(BaseModel):
    """Kit lint response."""
    ok: bool
    issues: List[LintIssue]
    stats: LintStats


# Configuration constants
DAILY_REVIEW_CAP = 20
PER_USER_RATE_LIMIT = 10
REVISION_BODY_MAX_CHARS = 20000
COMMENT_MAX_CHARS = 2000
UPLOAD_MAX_MB = 5
UPLOAD_MAX_PAGES = 20
REQUEST_BODY_MAX_MB = 6


# Database function error mapping
class DBErrorCodes:
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    VALIDATION = "validation"

    CONFLICT_REASONS = {
        "not_editable",
        "not_latest_revision",
        "not_submitted",
        "findings_undecided",
        "changes_pending_apply",
        "llm_failed",
        "no_review",
        "pending_signoffs",
        "no_changes",
        "not_draft_kit",
        "empty_kit",
        "not_latest_review",
        "not_needs_reviewer",
    }