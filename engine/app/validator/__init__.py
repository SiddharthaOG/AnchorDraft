"""Citation validator for the review engine.

This module implements the shared citation validator that runs on all
candidate findings (both deterministic and model-generated) to ensure
they cite real rules/facts and quote real text from the revision.
"""

from engine.app.validator.validator import (
    run_citation_validator,
    ValidationContext,
    RuleRecord,
    FactRecord,
    normalize_text,
    find_quote_occurrences,
)

__all__ = [
    "run_citation_validator",
    "ValidationContext",
    "RuleRecord",
    "FactRecord",
    "normalize_text",
    "find_quote_occurrences",
]