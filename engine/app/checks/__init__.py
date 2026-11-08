"""Deterministic checks for the review engine.

This module implements the four Tier 1 and Tier 2 deterministic check types:
- term_map: maps avoided terms to preferred alternatives
- phrase_list: matches exact phrases from a configured list
- missing_alt_text: detects missing or generic alt text in Markdown images
- required_disclosure: enforces disclosure phrases when triggers appear
"""

from app.checks.deterministic import (
    run_deterministic_checks,
    DeterministicCheck,
    DeterministicCheckResult,
    SkippedCheck,
    RuleConfig,
)

from app.checks.term_map import TermMapCheck
from app.checks.phrase_list import PhraseListCheck
from app.checks.missing_alt_text import MissingAltTextCheck
from app.checks.required_disclosure import RequiredDisclosureCheck

__all__ = [
    "run_deterministic_checks",
    "DeterministicCheck",
    "DeterministicCheckResult",
    "SkippedCheck",
    "RuleConfig",
    "TermMapCheck",
    "PhraseListCheck",
    "MissingAltTextCheck",
    "RequiredDisclosureCheck",
]