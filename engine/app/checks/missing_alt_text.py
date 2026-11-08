"""Missing alt text check implementation.

Detects Markdown images with missing or generic alt text.
Produces a finding for each image that violates the policy.
"""

from typing import List

from app.checks.deterministic import (
    DeterministicCheck,
    RuleConfig,
    find_markdown_images,
)
from app.models.pipeline import DeterministicFindingCandidate


class MissingAltTextCheck(DeterministicCheck):
    """Check for missing or generic alt text in Markdown images.

    Config shape:
    {
        "min_length": 5,
        "generic": ["image", "photo", "picture", "screenshot"]
    }

    A finding is produced if:
    - Alt text is empty or whitespace-only
    - Alt text length is less than min_length
    - Alt text (case-insensitive) matches any generic term
    """

    check_name = "missing_alt_text"

    def validate_config(self) -> None:
        min_length = self.rule.config.get("min_length")
        if min_length is None:
            raise ValueError("Missing required 'min_length' field")
        if not isinstance(min_length, int):
            raise ValueError("'min_length' must be an integer")
        if min_length < 1:
            raise ValueError("'min_length' must be positive")

        generic = self.rule.config.get("generic")
        if generic is None:
            raise ValueError("Missing required 'generic' field")
        if not isinstance(generic, list):
            raise ValueError("'generic' must be a list")
        for i, term in enumerate(generic):
            if not isinstance(term, str) or not term:
                raise ValueError(f"'generic[{i}]' must be a non-empty string")

    def find_matches(self, text: str) -> List[DeterministicFindingCandidate]:
        min_length = self.rule.config.get("min_length", 5)
        generic_terms = set(t.lower() for t in self.rule.config.get("generic", []))

        candidates = []
        images = find_markdown_images(text)

        for full_match, alt_text, start, end in images:
            alt_text = alt_text.strip()

            # Check if alt text is missing
            if not alt_text:
                candidate = self._make_candidate(
                    quote=full_match,
                    start_offset=start,
                    end_offset=end,
                    suggestion=None,
                )
                candidates.append(candidate)
                continue

            # Check if alt text is too short
            if len(alt_text) < min_length:
                candidate = self._make_candidate(
                    quote=full_match,
                    start_offset=start,
                    end_offset=end,
                    suggestion=None,
                )
                candidates.append(candidate)
                continue

            # Check if alt text is generic
            if alt_text.lower() in generic_terms:
                candidate = self._make_candidate(
                    quote=full_match,
                    start_offset=start,
                    end_offset=end,
                    suggestion=None,
                )
                candidates.append(candidate)
                continue

        return candidates