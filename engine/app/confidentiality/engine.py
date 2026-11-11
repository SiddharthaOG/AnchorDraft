"""Confidentiality redaction and citation-safe placeholder expansion."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from uuid import uuid4

from app.confidentiality.models import (
    ConfidentialityPolicy,
    RedactionMatch,
    RedactionResult,
    RedactionSummary,
)
from app.confidentiality.patterns import detect_sensitive_spans


@dataclass(frozen=True)
class RedactionBatchResult:
    """Redacted named fields plus one reverse map for a complete provider request."""

    fields: Mapping[str, str]
    matches: tuple[RedactionMatch, ...]
    placeholder_map: Mapping[str, str]
    summary: RedactionSummary


class ConfidentialityEngine:
    """Detect and replace confidential values before provider prompt construction."""

    def redact(self, text: str, policy: ConfidentialityPolicy) -> RedactionResult:
        if not policy.enabled or not text:
            return RedactionResult(
                redacted_text=text,
                policy_version=policy.version,
            )

        spans = detect_sensitive_spans(text, policy)
        matches: list[RedactionMatch] = []
        placeholder_map: dict[str, str] = {}
        parts: list[str] = []
        cursor = 0

        for span in spans:
            if span.start < cursor or span.end > len(text):
                continue
            original = text[span.start:span.end]
            if not original:
                continue

            # UUID suffix prevents collisions with natural text and repeated values.
            placeholder = f"[{span.match_type.upper()}-{uuid4().hex[:8]}]"
            while placeholder.casefold() in text.casefold() or placeholder in placeholder_map:
                placeholder = f"[{span.match_type.upper()}-{uuid4().hex[:8]}]"

            parts.append(text[cursor:span.start])
            parts.append(placeholder)
            placeholder_map[placeholder] = original
            matches.append(
                RedactionMatch(
                    original=original,
                    placeholder=placeholder,
                    start=span.start,
                    end=span.end,
                    match_type=span.match_type,
                    category=span.category,
                )
            )
            cursor = span.end

        parts.append(text[cursor:])
        return RedactionResult(
            redacted_text="".join(parts),
            matches=tuple(matches),
            placeholder_map=placeholder_map,
            policy_version=policy.version,
        )

    def redact_fields(
        self,
        fields: Mapping[str, str],
        policy: ConfidentialityPolicy,
    ) -> RedactionBatchResult:
        """Redact multiple prompt fields with one combined reverse map."""
        redacted_fields: dict[str, str] = {}
        all_matches: list[RedactionMatch] = []
        placeholder_map: dict[str, str] = {}
        original_chars = 0
        redacted_chars = 0

        for field_name, value in fields.items():
            if not isinstance(value, str):
                raise TypeError(f"Confidentiality field {field_name!r} must be a string")
            result = self.redact(value, policy)
            redacted_fields[field_name] = result.redacted_text
            all_matches.extend(result.matches)
            placeholder_map.update(result.placeholder_map)
            original_chars += len(value)
            redacted_chars += len(result.redacted_text)

        counts: dict[str, int] = {}
        for match in all_matches:
            counts[match.match_type] = counts.get(match.match_type, 0) + 1

        return RedactionBatchResult(
            fields=redacted_fields,
            matches=tuple(all_matches),
            placeholder_map=placeholder_map,
            summary=RedactionSummary(
                total_matches=len(all_matches),
                by_type=counts,
                original_chars=original_chars,
                redacted_chars=redacted_chars,
                policy_version=policy.version,
            ),
        )


def expand_placeholders(text: str, placeholder_map: Mapping[str, str]) -> str:
    """Restore original quote text before citation validation on the source draft."""
    expanded = text
    for placeholder in sorted(placeholder_map, key=len, reverse=True):
        expanded = expanded.replace(placeholder, placeholder_map[placeholder])
    return expanded
