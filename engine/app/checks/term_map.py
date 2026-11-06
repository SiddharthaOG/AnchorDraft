"""Term map check implementation.

Maps avoided terms to preferred alternatives. Produces a finding for each
occurrence of an avoided term with the preferred term as suggestion.
"""

from typing import List

from engine.app.checks.deterministic import (
    DeterministicCheck,
    RuleConfig,
    find_word_boundary_matches,
    match_first_letter_case,
)
from engine.app.models.pipeline import DeterministicFindingCandidate


class TermMapCheck(DeterministicCheck):
    """Check that finds avoided terms and suggests preferred alternatives.

    Config shape:
    {
        "entries": [
            {"avoid": ["utilize", "leverage"], "prefer": "use"},
            {"avoid": ["synergy"], "prefer": "collaboration"}
        ]
    }
    """

    check_name = "term_map"

    def validate_config(self) -> None:
        entries = self.rule.config.get("entries")
        if entries is None:
            raise ValueError("Missing required 'entries' field")
        if not isinstance(entries, list):
            raise ValueError("'entries' must be a list")
        if not entries:
            raise ValueError("'entries' list cannot be empty")

        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"Entry {i} must be an object")
            avoid = entry.get("avoid")
            prefer = entry.get("prefer")
            if avoid is None:
                raise ValueError(f"Entry {i} missing required 'avoid' field")
            if not isinstance(avoid, list):
                raise ValueError(f"Entry {i} 'avoid' must be a list")
            if not avoid:
                raise ValueError(f"Entry {i} 'avoid' list cannot be empty")
            for j, term in enumerate(avoid):
                if not isinstance(term, str) or not term:
                    raise ValueError(f"Entry {i} 'avoid[{j}]' must be a non-empty string")
            if prefer is None:
                raise ValueError(f"Entry {i} missing required 'prefer' field")
            if not isinstance(prefer, str) or not prefer:
                raise ValueError(f"Entry {i} 'prefer' must be a non-empty string")

    def find_matches(self, text: str) -> List[DeterministicFindingCandidate]:
        entries = self.rule.config.get("entries", [])
        candidates = []

        for entry in entries:
            avoid_terms = entry.get("avoid", [])
            prefer = entry.get("prefer", "")

            # Validation already done in validate_config, but guard anyway
            if not avoid_terms or not prefer:
                continue

            # Find all matches of avoided terms
            matches = find_word_boundary_matches(text, avoid_terms)

            for matched_text, start, end in matches:
                # Match capitalisation of the found term to the preferred term
                suggestion = match_first_letter_case(matched_text, prefer)
                candidate = self._make_candidate(
                    quote=matched_text,
                    start_offset=start,
                    end_offset=end,
                    suggestion=suggestion,
                )
                candidates.append(candidate)

        return candidates