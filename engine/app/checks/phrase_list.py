"""Phrase list check implementation.

Matches exact phrases from a configured list. Produces a finding for each
occurrence of any phrase in the list.
"""

from typing import List

from app.checks.deterministic import (
    DeterministicCheck,
    RuleConfig,
    find_word_boundary_matches,
)
from app.models.pipeline import DeterministicFindingCandidate


class PhraseListCheck(DeterministicCheck):
    """Check that finds phrases from a configured list.

    Config shape:
    {
        "phrases": ["guaranteed", "100% secure", "best in class", "#1"]
    }
    """

    check_name = "phrase_list"

    def validate_config(self) -> None:
        phrases = self.rule.config.get("phrases")
        if phrases is None:
            raise ValueError("Missing required 'phrases' field")
        if not isinstance(phrases, list):
            raise ValueError("'phrases' must be a list")
        if not phrases:
            raise ValueError("'phrases' list cannot be empty")
        for i, phrase in enumerate(phrases):
            if not isinstance(phrase, str) or not phrase:
                raise ValueError(f"'phrases[{i}]' must be a non-empty string")

    def find_matches(self, text: str) -> List[DeterministicFindingCandidate]:
        phrases = self.rule.config.get("phrases", [])
        candidates = []

        if not phrases:
            return candidates

        matches = find_word_boundary_matches(text, phrases)

        for matched_text, start, end in matches:
            candidate = self._make_candidate(
                quote=matched_text,
                start_offset=start,
                end_offset=end,
                suggestion=None,  # No suggestion for phrase_list
            )
            candidates.append(candidate)

        return candidates