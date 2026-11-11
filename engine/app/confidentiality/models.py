"""Typed, in-memory models for confidentiality redaction.

Original sensitive values are deliberately kept out of summary/audit models.
"""
from dataclasses import dataclass, field
from typing import Mapping
from uuid import UUID


@dataclass(frozen=True)
class ConfidentialityPolicy:
    """Organization-scoped redaction settings loaded by the trusted backend."""

    org_id: UUID
    version: int = 1
    enabled: bool = True
    custom_terms: tuple[str, ...] = ()
    redact_emails: bool = True
    redact_phones: bool = True
    redact_api_keys: bool = True
    redact_jwts: bool = True
    redact_credit_cards: bool = True


@dataclass(frozen=True)
class RedactionMatch:
    """One detected value; original is transient and must never be logged."""

    original: str
    placeholder: str
    start: int
    end: int
    match_type: str
    category: str


@dataclass(frozen=True)
class RedactionSummary:
    """Safe aggregate metadata suitable for API responses and audit logs."""

    total_matches: int
    by_type: Mapping[str, int]
    original_chars: int
    redacted_chars: int
    policy_version: int


@dataclass(frozen=True)
class RedactionResult:
    """Redacted text and private reverse map needed for citation restoration."""

    redacted_text: str
    matches: tuple[RedactionMatch, ...] = field(default_factory=tuple)
    placeholder_map: Mapping[str, str] = field(default_factory=dict)
    policy_version: int = 1

    @property
    def summary(self) -> RedactionSummary:
        counts: dict[str, int] = {}
        for match in self.matches:
            counts[match.match_type] = counts.get(match.match_type, 0) + 1
        original_chars = len(self.redacted_text) + sum(
            len(match.original) - len(match.placeholder) for match in self.matches
        )
        return RedactionSummary(
            total_matches=len(self.matches),
            by_type=counts,
            original_chars=original_chars,
            redacted_chars=len(self.redacted_text),
            policy_version=self.policy_version,
        )
