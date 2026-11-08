"""Required disclosure check implementation.

Enforces that when certain trigger phrases appear, required disclosure
phrases must also be present in the text.
"""

from typing import List, Set

from app.checks.deterministic import (
    DeterministicCheck,
    RuleConfig,
    find_word_boundary_matches,
)
from app.models.pipeline import DeterministicFindingCandidate


class RequiredDisclosureCheck(DeterministicCheck):
    """Check that required disclosures appear when trigger phrases are found.

    Config shape:
    {
        "when_any": ["sponsored", "in collaboration with"],
        "require_any": ["#ad", "paid partnership"]
    }

    If any trigger phrase from "when_any" is found, at least one
    required disclosure from "require_any" must also be present.
    If not, a finding is produced for each trigger phrase occurrence.
    """

    check_name = "required_disclosure"

    def validate_config(self) -> None:
        when_any = self.rule.config.get("when_any")
        if when_any is None:
            raise ValueError("Missing required 'when_any' field")
        if not isinstance(when_any, list):
            raise ValueError("'when_any' must be a list")
        if not when_any:
            raise ValueError("'when_any' list cannot be empty")
        for i, phrase in enumerate(when_any):
            if not isinstance(phrase, str) or not phrase:
                raise ValueError(f"'when_any[{i}]' must be a non-empty string")

        require_any = self.rule.config.get("require_any")
        if require_any is None:
            raise ValueError("Missing required 'require_any' field")
        if not isinstance(require_any, list):
            raise ValueError("'require_any' must be a list")
        if not require_any:
            raise ValueError("'require_any' list cannot be empty")
        for i, phrase in enumerate(require_any):
            if not isinstance(phrase, str) or not phrase:
                raise ValueError(f"'require_any[{i}]' must be a non-empty string")

    def find_matches(self, text: str) -> List[DeterministicFindingCandidate]:
        when_any = self.rule.config.get("when_any", [])
        require_any = self.rule.config.get("require_any", [])

        candidates = []

        if not when_any or not require_any:
            return candidates

        # First, check if any required disclosure is present
        required_matches = find_word_boundary_matches(text, require_any)
        has_required_disclosure = len(required_matches) > 0

        # If required disclosure is present, no findings needed
        if has_required_disclosure:
            return candidates

        # Check for trigger phrases
        trigger_matches = find_word_boundary_matches(text, when_any)

        for matched_text, start, end in trigger_matches:
            candidate = self._make_candidate(
                quote=matched_text,
                start_offset=start,
                end_offset=end,
                suggestion=None,
            )
            candidates.append(candidate)

        return candidates