"""Organization-scoped confidentiality policy loading."""
from __future__ import annotations

import asyncio
from uuid import UUID

from app.confidentiality.models import ConfidentialityPolicy


class ConfidentialityPolicyStore:
    """Loads policy through the trusted service-role Supabase client."""

    MAX_TERMS = 500
    MAX_TERM_CHARS = 256
    MAX_TOTAL_TERM_CHARS = 20_000

    def __init__(self, supabase_client):
        self.supabase = supabase_client

    async def load_policy(self, org_id: UUID | str) -> ConfidentialityPolicy:
        expected_org_id = UUID(str(org_id))
        # Database errors deliberately propagate: callers must fail closed rather
        # than send an unredacted prompt when policy retrieval is unavailable.
        record = await asyncio.to_thread(
            self.supabase.get_confidentiality_policy,
            str(expected_org_id),
        )
        if record is None:
            return ConfidentialityPolicy(org_id=expected_org_id)

        if str(record.get("org_id")) != str(expected_org_id):
            raise ValueError("Confidentiality policy organization mismatch")

        raw_terms = record.get("custom_terms", [])
        if not isinstance(raw_terms, list) or len(raw_terms) > self.MAX_TERMS:
            raise ValueError("Confidentiality policy custom_terms is invalid")

        terms: list[str] = []
        total_chars = 0
        for raw_term in raw_terms:
            if not isinstance(raw_term, str):
                raise ValueError("Confidentiality policy terms must be strings")
            term = raw_term.strip()
            if not term:
                continue
            if len(term) > self.MAX_TERM_CHARS:
                raise ValueError("Confidentiality policy term exceeds maximum length")
            total_chars += len(term)
            if total_chars > self.MAX_TOTAL_TERM_CHARS:
                raise ValueError("Confidentiality policy terms exceed total size limit")
            terms.append(term)

        version = record.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("Confidentiality policy version is invalid")

        toggles = {}
        for key in (
            "enabled",
            "redact_emails",
            "redact_phones",
            "redact_api_keys",
            "redact_jwts",
            "redact_credit_cards",
        ):
            value = record.get(key, True)
            if not isinstance(value, bool):
                raise ValueError(f"Confidentiality policy {key} must be boolean")
            toggles[key] = value

        return ConfidentialityPolicy(
            org_id=expected_org_id,
            version=version,
            custom_terms=tuple(terms),
            **toggles,
        )
