"""Base classes and runner for deterministic checks.

This module provides the infrastructure for running deterministic checks
against revision text, producing DeterministicFindingCandidate objects.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.models.pipeline import DeterministicFindingCandidate


# Module-level check type registry for extensibility and testing
check_map = {
    "term_map": None,  # Will be populated after class definitions
    "phrase_list": None,
    "missing_alt_text": None,
    "required_disclosure": None,
}


@dataclass
class RuleConfig:
    """Parsed configuration for a deterministic rule."""
    check: str
    config: Dict[str, Any]
    rule_key: str
    category: str
    severity: str
    guideline_text: str
    needs_reviewer: bool = False


@dataclass
class SkippedCheck:
    """A deterministic check that was skipped due to invalid configuration or execution error."""
    rule_key: str
    check_type: str
    reason: str


class DeterministicCheck(ABC):
    """Abstract base class for a deterministic check type.

    Each check type implements the check method that finds matches
    in the given text and returns candidate findings.
    """

    check_name: str

    def __init__(self, rule: RuleConfig):
        self.rule = rule

    def validate_config(self) -> None:
        """Validate the rule configuration.
        
        Raises:
            ValueError: If configuration is invalid.
        """
        pass

    @abstractmethod
    def find_matches(self, text: str) -> List[DeterministicFindingCandidate]:
        """Find all matches in the given text.

        Args:
            text: The revision body text to search.

        Returns:
            List of DeterministicFindingCandidate objects, each with
            exact quote and correct Unicode code-point offsets.
        """
        pass

    def _make_candidate(
        self,
        quote: str,
        start_offset: int,
        end_offset: int,
        suggestion: Optional[str] = None,
    ) -> DeterministicFindingCandidate:
        """Create a DeterministicFindingCandidate with common fields."""
        # Build explanation from guideline_text + matched text
        explanation = self._build_explanation(quote)

        return DeterministicFindingCandidate(
            ref_key=self.rule.rule_key,
            quote=quote,
            start_offset=start_offset,
            end_offset=end_offset,
            explanation=explanation,
            suggestion=suggestion,
            rule_category=self.rule.category,
            severity=self.rule.severity,
            needs_reviewer=self.rule.needs_reviewer,
        )

    def _build_explanation(self, matched_text: str) -> str:
        """Build explanation from guideline_text and matched text."""
        base = self.rule.guideline_text.strip()
        return f"{base}: found '{matched_text}'"


def find_word_boundary_matches(
    text: str,
    phrases: List[str],
    case_insensitive: bool = True,
) -> List[tuple]:
    """Find all matches of phrases at word boundaries.

    Args:
        text: The text to search.
        phrases: List of phrases to find.
        case_insensitive: Whether to match case-insensitively.

    Returns:
        List of (matched_text, start_offset, end_offset) tuples.
        Offsets are Unicode code-point offsets in the original text.
    """
    matches = []
    flags = re.IGNORECASE if case_insensitive else 0

    for phrase in phrases:
        # Escape regex special characters
        escaped = re.escape(phrase)
        # Build word boundary pattern: match at word boundaries on ends that are word chars
        # A word character is [a-zA-Z0-9_]
        # We want to match only when the phrase is at a word boundary
        pattern = r"(?<!\w)" + escaped + r"(?!\w)"

        for match in re.finditer(pattern, text, flags):
            matched_text = match.group(0)
            start = match.start()
            end = match.end()
            matches.append((matched_text, start, end))

    # Sort by start offset to ensure deterministic ordering
    matches.sort(key=lambda x: x[1])

    # Deduplicate: if multiple phrases match at the same position, keep only the first
    # This handles case where avoid list has multiple case variations of same word
    deduplicated = []
    seen_positions = set()
    for matched_text, start, end in matches:
        pos_key = (start, end)
        if pos_key not in seen_positions:
            seen_positions.add(pos_key)
            deduplicated.append((matched_text, start, end))

    return deduplicated


def find_markdown_images(text: str) -> List[tuple]:
    """Find all Markdown image syntax in text.

    Args:
        text: The text to search.

    Returns:
        List of (full_match, alt_text, start_offset, end_offset) tuples.
    """
    # Pattern: ![alt_text](url) - alt_text can be empty
    pattern = r"!\[([^\]]*)\]\([^)]+\)"
    matches = []

    for match in re.finditer(pattern, text):
        full_match = match.group(0)
        alt_text = match.group(1)
        start = match.start()
        end = match.end()
        matches.append((full_match, alt_text, start, end))

    return matches


def match_first_letter_case(source: str, target: str) -> str:
    """Match the first-letter capitalisation of source to target.

    If source starts with uppercase, capitalize target.
    If source starts with lowercase, lowercase target.
    Otherwise return target as-is.
    """
    if not source or not target:
        return target

    if source[0].isupper():
        return target[0].upper() + target[1:] if len(target) > 1 else target.upper()
    else:
        return target[0].lower() + target[1:] if len(target) > 1 else target.lower()


@dataclass
class DeterministicCheckResult:
    """Result of running deterministic checks."""
    candidates: List[DeterministicFindingCandidate]
    skipped_checks: List[SkippedCheck]


def run_deterministic_checks(
    text: str,
    rules: List[RuleConfig],
) -> DeterministicCheckResult:
    """Run all deterministic checks for the given rules.

    Args:
        text: The revision body text to check.
        rules: List of RuleConfig objects for deterministic rules.

    Returns:
        DeterministicCheckResult containing candidates and skipped checks.
    """
    # Use module-level check_map for extensibility and testing
    all_candidates = []
    skipped_checks = []

    for rule in rules:
        check_class = check_map.get(rule.check)
        if check_class is None:
            skipped_checks.append(SkippedCheck(
                rule_key=rule.rule_key,
                check_type=rule.check,
                reason=f"Unknown check type: '{rule.check}'"
            ))
            continue

        # Construct checker inside exception boundary so constructor failures
        # skip only this rule, not the entire runner
        try:
            checker = check_class(rule)
        except Exception as e:
            skipped_checks.append(SkippedCheck(
                rule_key=rule.rule_key,
                check_type=rule.check,
                reason=f"Check construction error: {type(e).__name__}"
            ))
            continue

        # Validate configuration - only ValueError from validate_config() is
        # treated as a config error; other exceptions are execution errors
        try:
            checker.validate_config()
        except ValueError as e:
            skipped_checks.append(SkippedCheck(
                rule_key=rule.rule_key,
                check_type=rule.check,
                reason=str(e)
            ))
            continue
        except Exception as e:
            skipped_checks.append(SkippedCheck(
                rule_key=rule.rule_key,
                check_type=rule.check,
                reason=f"Check configuration error: {type(e).__name__}"
            ))
            continue

        # Execute the check - all exceptions are execution errors
        try:
            candidates = checker.find_matches(text)
            all_candidates.extend(candidates)
        except Exception as e:
            skipped_checks.append(SkippedCheck(
                rule_key=rule.rule_key,
                check_type=rule.check,
                reason=f"Check execution error: {type(e).__name__}"
            ))
            continue

    return DeterministicCheckResult(
        candidates=all_candidates,
        skipped_checks=skipped_checks
    )


# Import at bottom to avoid circular imports
from app.checks.term_map import TermMapCheck
from app.checks.phrase_list import PhraseListCheck
from app.checks.missing_alt_text import MissingAltTextCheck
from app.checks.required_disclosure import RequiredDisclosureCheck

# Populate module-level check_map after imports
check_map["term_map"] = TermMapCheck
check_map["phrase_list"] = PhraseListCheck
check_map["missing_alt_text"] = MissingAltTextCheck
check_map["required_disclosure"] = RequiredDisclosureCheck