"""Organization-scoped confidentiality policy management.

Only organization owners can read or change policy contents. The service-role
client is used after the authenticated membership/role dependency has bound
the request to exactly one organization.
"""
from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.dependencies import AuthUser, require_owner
from app.auth.supabase import get_supabase_client
from app.confidentiality import ConfidentialityPolicyStore

router = APIRouter(prefix="/organizations/me/confidentiality-policy", tags=["confidentiality"])

MAX_TERMS = 500
MAX_TERM_CHARS = 256
MAX_TOTAL_TERM_CHARS = 20_000


class ConfidentialityPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    custom_terms: list[str] = Field(default_factory=list, max_length=MAX_TERMS)
    redact_emails: bool = True
    redact_phones: bool = True
    redact_api_keys: bool = True
    redact_jwts: bool = True
    redact_credit_cards: bool = True

    @field_validator("custom_terms")
    @classmethod
    def validate_custom_terms(cls, terms: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        total = 0
        for raw in terms:
            term = raw.strip()
            if not term:
                raise ValueError("Custom terms cannot be blank")
            if len(term) > MAX_TERM_CHARS:
                raise ValueError(f"Each custom term must be at most {MAX_TERM_CHARS} characters")
            folded = term.casefold()
            if folded in seen:
                raise ValueError("Custom terms must be unique (case-insensitive)")
            seen.add(folded)
            total += len(term)
            if total > MAX_TOTAL_TERM_CHARS:
                raise ValueError("Combined custom terms exceed the size limit")
            normalized.append(term)
        return normalized


def _safe_policy(record: dict | None, org_id: str) -> dict:
    if record is None:
        return {
            "org_id": org_id, "version": 1, "enabled": True, "custom_terms": [],
            "redact_emails": True, "redact_phones": True, "redact_api_keys": True,
            "redact_jwts": True, "redact_credit_cards": True,
        }
    return {
        "org_id": str(record["org_id"]),
        "version": record["version"],
        "enabled": record["enabled"],
        "custom_terms": record["custom_terms"] or [],
        "redact_emails": record["redact_emails"],
        "redact_phones": record["redact_phones"],
        "redact_api_keys": record["redact_api_keys"],
        "redact_jwts": record["redact_jwts"],
        "redact_credit_cards": record["redact_credit_cards"],
    }


@router.get("")
async def get_confidentiality_policy(
    response: Response,
    user: Annotated[AuthUser, Depends(require_owner)],
) -> dict:
    """Return this owner's organization policy, including safe defaults."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    supabase = get_supabase_client()
    policy = await ConfidentialityPolicyStore(supabase).load_policy(user.org_id)
    return _safe_policy({
        "org_id": str(policy.org_id), "version": policy.version, "enabled": policy.enabled,
        "custom_terms": list(policy.custom_terms), "redact_emails": policy.redact_emails,
        "redact_phones": policy.redact_phones, "redact_api_keys": policy.redact_api_keys,
        "redact_jwts": policy.redact_jwts, "redact_credit_cards": policy.redact_credit_cards,
    }, user.org_id)


@router.put("")
async def update_confidentiality_policy(
    payload: ConfidentialityPolicyUpdate,
    response: Response,
    user: Annotated[AuthUser, Depends(require_owner)],
) -> dict:
    """Create or replace this organization's policy; DB trigger increments version."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    supabase = get_supabase_client()
    values = payload.model_dump()
    values.update({"org_id": user.org_id, "updated_by": user.user_id})

    def persist() -> dict:
        response = (
            supabase._get_client().table("confidentiality_policies")
            .upsert(values, on_conflict="org_id")
            .select("*")
            .single()
            .execute()
        )
        if not response.data:
            raise RuntimeError("Confidentiality policy write returned no row")
        return response.data

    record = await asyncio.to_thread(persist)
    # Audit only policy metadata; never copy custom terms into the audit log.
    await asyncio.to_thread(
        lambda: supabase._get_client().table("audit_log").insert({
            "org_id": user.org_id,
            "actor_id": user.user_id,
            "action": "confidentiality.policy_updated",
            "entity_type": "confidentiality_policy",
            "entity_id": record["id"],
            "detail": {
                "version": record["version"],
                "custom_term_count": len(record.get("custom_terms") or []),
                "enabled": record["enabled"],
            },
        }).execute()
    )
    return _safe_policy(record, user.org_id)
