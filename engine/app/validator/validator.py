"""Citation validator implementation.

This module implements the shared citation validator that runs on all
candidate findings (both deterministic and model-generated) to ensure
they cite real rules/facts and quote real text from the revision.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict, Literal
from datetime import date

from engine.app.models.pipeline import (
    ModelFindingCandidate,
    DeterministicFindingCandidate,
    ValidatedFinding,
    ValidatorOutcome,
    AggregateValidationResult,
    DropReason,
)


# ============================================================================
# Context structures
# ============================================================================

@dataclass
class RuleRecord:
    """Rule information needed for validation and finding construction."""
    rule_key: str
    category: str
    severity: str
    needs_reviewer: bool = False
    check_kind: Literal["deterministic", "llm"] = "deterministic"


@dataclass
class FactRecord:
    """Fact information needed for validation and finding construction."""
    fact_key: str
    statement: str
    valid_until: Optional[date] = None


@dataclass
class ValidationContext:
    """Context for running the citation validator."""
    # All rules in the applicable kit (both deterministic and LLM)
    all_rules: List[RuleRecord]
    # All non-expired facts in the applicable kit
    all_facts: List[FactRecord]
    # Rule keys actually offered to the model (LLM rules only)
    model_offered_rule_keys: Set[str] = field(default_factory=set)
    # Fact keys actually offered to the model (non-expired facts only)
    model_offered_fact_keys: Set[str] = field(default_factory=set)


# ============================================================================
# Normalization utilities
# ============================================================================

# Mapping of typographic characters to plain ASCII equivalents
NORMALIZATION_MAP = {
    # Typographic quotes
    '\u201c': '"',  # left double quote
    '\u201d': '"',  # right double quote
    '\u2018': "'",  # left single quote
    '\u2019': "'",  # right single quote / apostrophe
    # Dashes
    '\u2014': '-',  # em dash
    '\u2013': '-',  # en dash
}

# Pattern to collapse consecutive whitespace
WHITESPACE_PATTERN = re.compile(r'\s+')


def normalize_text(text: str) -> tuple[str, list[int]]:
    """
    Normalize text for quote matching.
    
    Returns a tuple of (normalized_text, position_map) where position_map
    maps each character index in normalized_text to the corresponding
    character index in the original text.
    """
    normalized_chars = []
    position_map = []
    
    i = 0
    while i < len(text):
        ch = text[i]
        
        # Check for typographic characters that map to ASCII
        if ch in NORMALIZATION_MAP:
            normalized_chars.append(NORMALIZATION_MAP[ch])
            position_map.append(i)
            i += 1
        # Handle whitespace runs
        elif ch.isspace():
            # Collapse consecutive whitespace to a single space
            normalized_chars.append(' ')
            position_map.append(i)
            # Skip all consecutive whitespace
            while i < len(text) and text[i].isspace():
                i += 1
        else:
            normalized_chars.append(ch)
            position_map.append(i)
            i += 1
    
    return ''.join(normalized_chars), position_map


def find_quote_occurrences(revision_text: str, quote: str) -> List[tuple[int, int, bool]]:
    """
    Find all occurrences of a quote in the revision text.
    
    First tries exact match (case-sensitive), then falls back to normalized 
    match (case-insensitive) for any occurrences not found exactly.
    Returns list of (start_offset, end_offset, is_normalized) tuples in the 
    original text, sorted by start offset.
    """
    occurrences = []  # List of (start, end, is_normalized)
    found_ranges = set()  # Track which ranges we've already found
    
    # 1. Exact search (case-sensitive)
    start = 0
    while True:
        idx = revision_text.find(quote, start)
        if idx == -1:
            break
        occurrences.append((idx, idx + len(quote), False))
        start = idx + 1
    
    # 2. Normalized search (case-insensitive)
    norm_revision, pos_map = normalize_text(revision_text)
    norm_quote, _ = normalize_text(quote)
    
    if norm_quote:
        # Case-insensitive search in normalized text
        norm_revision_lower = norm_revision.lower()
        norm_quote_lower = norm_quote.lower()
        
        start = 0
        while True:
            idx = norm_revision_lower.find(norm_quote_lower, start)
            if idx == -1:
                break
            # Map back to original text positions
            if idx < len(pos_map) and idx + len(norm_quote) <= len(pos_map):
                orig_start = pos_map[idx]
                orig_end = pos_map[idx + len(norm_quote) - 1] + 1
                # Check if we already found this exact range via exact match
                if (orig_start, orig_end) not in {(o[0], o[1]) for o in occurrences}:
                    occurrences.append((orig_start, orig_end, True))
            start = idx + 1
    
    # Sort by start offset for deterministic ordering
    occurrences.sort(key=lambda x: x[0])
    return occurrences


# ============================================================================
# Validation logic
# ============================================================================

VALID_DROP_REASONS = {
    "schema_invalid", "unknown_ref", "ref_mismatch",
    "quote_not_found", "duplicate", "too_many"
}

VALID_ISSUES = {"violation", "contradicts_fact", "outdated_fact", "unsupported_claim"}
FACT_ISSUES = {"contradicts_fact", "outdated_fact"}
CLAIM_ISSUES = {"unsupported_claim"}
RULE_ISSUES = {"violation"}


def get_candidate_issue(candidate, is_deterministic: bool) -> str:
    """Get the issue type for a candidate.
    
    For model candidates, use the explicit issue field.
    For deterministic candidates, the issue is implicitly "violation"
    since all deterministic checks are violation checks.
    """
    if is_deterministic:
        return "violation"
    return candidate.issue


def validate_schema(
    candidate,
    is_deterministic: bool,
) -> Optional[str]:
    """
    Validate schema requirements for a candidate.
    
    Returns drop reason if invalid, None if valid.
    """
    # ModelFindingCandidate and DeterministicFindingCandidate already enforce
    # required fields and basic types via Pydantic. We need to check
    # additional constraints that aren't covered by the model.
    
    # Quote length: 4-300 for model, 1-300 for deterministic (exempt from min)
    if not is_deterministic:
        if len(candidate.quote) < 4 or len(candidate.quote) > 300:
            return "schema_invalid"
    else:
        if len(candidate.quote) > 300:
            return "schema_invalid"
    
    # Explanation: 1-600 chars after trimming
    trimmed_explanation = candidate.explanation.strip()
    if len(trimmed_explanation) < 1 or len(trimmed_explanation) > 600:
        return "schema_invalid"
    
    # Suggestion: at most 600 chars if present
    if candidate.suggestion is not None:
        if len(candidate.suggestion) > 600:
            return "schema_invalid"
    
    # Confidence: 0-1 if present
    if candidate.confidence is not None:
        if not (0.0 <= candidate.confidence <= 1.0):
            return "schema_invalid"
    
    return None


def validate_reference(
    candidate,
    is_deterministic: bool,
    context: ValidationContext,
) -> tuple[Optional[str], Optional[RuleRecord], Optional[FactRecord]]:
    """
    Validate reference existence and eligibility.
    
    Returns (drop_reason, rule_record, fact_record) if invalid,
    or (None, rule_record, fact_record) if valid.
    """
    ref_key = candidate.ref_key
    
    # Check rules first
    rule_record = next((r for r in context.all_rules if r.rule_key == ref_key), None)
    fact_record = next((f for f in context.all_facts if f.fact_key == ref_key), None)
    
    # Reference must exist in the kit
    if rule_record is None and fact_record is None:
        return "unknown_ref", None, None
    
    # Check eligibility based on candidate source
    if is_deterministic:
        # Deterministic candidates must reference rules in the kit
        if fact_record is not None:
            return "unknown_ref", None, None
        # Rule must exist in the kit (already checked above)
    else:
        # Model candidates must reference only rules/facts offered to the model
        if rule_record is not None:
            if ref_key not in context.model_offered_rule_keys:
                return "unknown_ref", None, None
        elif fact_record is not None:
            if ref_key not in context.model_offered_fact_keys:
                return "unknown_ref", None, None
        else:
            return "unknown_ref", None, None
    
    return None, rule_record, fact_record


def validate_reference_fits_issue(
    candidate,
    is_deterministic: bool,
    rule_record: Optional[RuleRecord],
    fact_record: Optional[FactRecord],
) -> Optional[str]:
    """Validate that the reference type matches the issue type."""
    issue = get_candidate_issue(candidate, is_deterministic)
    
    if issue in FACT_ISSUES:
        # contradicts_fact, outdated_fact must cite a fact
        if fact_record is None:
            return "ref_mismatch"
    elif issue in CLAIM_ISSUES:
        # unsupported_claim must cite a rule of category "claim"
        if rule_record is None or rule_record.category != "claim":
            return "ref_mismatch"
    elif issue in RULE_ISSUES:
        # violation must cite a rule
        if rule_record is None:
            return "ref_mismatch"
    else:
        # Unknown issue type (should be caught by schema)
        return "ref_mismatch"
    
    return None


def clean_suggestion(quote: str, suggestion: Optional[str]) -> Optional[str]:
    """Clean suggestion: trim whitespace, set to None if equals quote."""
    if suggestion is None:
        return None
    trimmed = suggestion.strip()
    if trimmed == quote:
        return None
    return trimmed if trimmed else None


def compute_flags(
    candidate,
    rule_record: Optional[RuleRecord],
    fact_record: Optional[FactRecord],
    used_normalized_match: bool,
) -> tuple[bool, bool]:
    """Compute needs_human and needs_reviewer flags."""
    needs_human = False
    needs_reviewer = False
    
    # needs_human: confidence < 0.6 or normalized match
    if candidate.confidence is not None and candidate.confidence < 0.6:
        needs_human = True
    if used_normalized_match:
        needs_human = True
    
    # needs_reviewer: rule says so, or reference is a fact
    if fact_record is not None:
        needs_reviewer = True
    elif rule_record is not None and rule_record.needs_reviewer:
        needs_reviewer = True
    
    return needs_human, needs_reviewer


def get_category_severity(
    candidate,
    rule_record: Optional[RuleRecord],
    fact_record: Optional[FactRecord],
) -> tuple[str, str]:
    """Get category and severity from rule or fact."""
    if fact_record is not None:
        return "fact", "medium"
    elif rule_record is not None:
        return rule_record.category, rule_record.severity
    else:
        # Should not happen if reference validation passed
        return "unknown", "medium"


# ============================================================================
# Main validator function
# ============================================================================

def run_citation_validator(
    revision_text: str,
    deterministic_candidates: List[DeterministicFindingCandidate],
    model_candidates: List[ModelFindingCandidate],
    context: ValidationContext,
) -> AggregateValidationResult:
    """
    Run the citation validator on all candidates.
    
    Processes deterministic candidates first, then model candidates.
    Returns an AggregateValidationResult with validated findings and statistics.
    """
    result = AggregateValidationResult()
    
    # Track used quote occurrences per ref_key
    # Maps ref_key -> list of (start, end) tuples that have been used
    used_occurrences: Dict[str, List[tuple[int, int]]] = {}
    
    # Track kept findings for cross-layer duplicate detection
    # Maps ref_key -> list of (start, end) tuples for kept findings
    kept_spans: Dict[str, List[tuple[int, int]]] = {}
    
    def get_first_unused_occurrence(ref_key: str, occurrences: List[tuple[int, int, bool]]) -> Optional[tuple[int, int, bool]]:
        """Get the first occurrence not already used for this ref_key."""
        used = used_occurrences.get(ref_key, [])
        for occ in occurrences:
            if (occ[0], occ[1]) not in used:
                return occ
        return None
    
    def mark_occurrence_used(ref_key: str, occurrence: tuple[int, int, bool]) -> None:
        """Mark an occurrence as used for a ref_key."""
        if ref_key not in used_occurrences:
            used_occurrences[ref_key] = []
        used_occurrences[ref_key].append((occurrence[0], occurrence[1]))
    
    def check_cross_layer_duplicate(ref_key: str, start: int, end: int, is_model: bool) -> bool:
        """Check if this finding overlaps a deterministic finding with the same ref_key."""
        if not is_model:
            return False
        for kept_start, kept_end in kept_spans.get(ref_key, []):
            # Check for overlap: not (end <= kept_start or start >= kept_end)
            if not (end <= kept_start or start >= kept_end):
                return True
        return False
    
    def process_candidate(
        candidate,
        is_deterministic: bool,
        source: Literal["deterministic", "llm"],
    ) -> None:
        """Process a single candidate through all validation steps."""
        ref_key = candidate.ref_key
        
        # Step 1: Schema validation
        schema_error = validate_schema(candidate, is_deterministic)
        if schema_error:
            result.add_dropped(schema_error)
            return
        
        # Step 2: Reference existence and eligibility
        ref_error, rule_record, fact_record = validate_reference(
            candidate, is_deterministic, context
        )
        if ref_error:
            result.add_dropped(ref_error)
            return
        
        # Step 3: Reference fits issue
        ref_fit_error = validate_reference_fits_issue(candidate, is_deterministic, rule_record, fact_record)
        if ref_fit_error:
            result.add_dropped(ref_fit_error)
            return
        
        # Step 4 & 5: Quote location and offset computation
        occurrences = find_quote_occurrences(revision_text, candidate.quote)
        if not occurrences:
            result.add_dropped("quote_not_found")
            return
        
        # Find first unused occurrence
        occurrence = get_first_unused_occurrence(ref_key, occurrences)
        if occurrence is None:
            result.add_dropped("duplicate")
            return
        
        start_offset, end_offset, used_normalized = occurrence
        
        # Use the extracted original text as the stored quote (per spec)
        stored_quote = revision_text[start_offset:end_offset]
        
        # Step 6: Cross-layer duplicate check
        if check_cross_layer_duplicate(ref_key, start_offset, end_offset, not is_deterministic):
            result.add_dropped("duplicate")
            return
        
        # Step 7: Clean suggestion
        suggestion = clean_suggestion(stored_quote, candidate.suggestion)
        
        # Step 8: Compute flags
        needs_human, needs_reviewer = compute_flags(
            candidate, rule_record, fact_record, used_normalized
        )
        
        # Step 9: Get category and severity
        category, severity = get_category_severity(candidate, rule_record, fact_record)
        
        # Build validated finding with the ORIGINAL text as the quote
        validated = ValidatedFinding(
            source=source,
            ref_key=ref_key,
            category=category,
            severity=severity,
            quote=stored_quote,
            start_offset=start_offset,
            end_offset=end_offset,
            explanation=candidate.explanation.strip(),
            suggestion=suggestion,
            confidence=candidate.confidence,
            needs_human=needs_human,
            needs_reviewer=needs_reviewer,
        )
        
        # Mark occurrence as used
        mark_occurrence_used(ref_key, occurrence)
        
        # Track kept span for cross-layer duplicate detection
        if ref_key not in kept_spans:
            kept_spans[ref_key] = []
        kept_spans[ref_key].append((start_offset, end_offset))
        
        result.add_kept(validated)
    
    # Process deterministic candidates first
    for candidate in deterministic_candidates:
        process_candidate(candidate, True, "deterministic")
    
    # Then process model candidates
    for candidate in model_candidates:
        process_candidate(candidate, False, "llm")
    
    # Apply cap: keep at most 25 findings
    # Sort by: severity (high first), deterministic before model, confidence descending
    severity_order = {"high": 0, "medium": 1, "low": 2}
    
    result.validated_findings.sort(
        key=lambda f: (
            severity_order.get(f.severity, 3),
            0 if f.source == "deterministic" else 1,
            -(f.confidence or 0),
        )
    )
    
    if len(result.validated_findings) > 25:
        dropped = result.validated_findings[25:]
        result.validated_findings = result.validated_findings[:25]
        for _ in dropped:
            result.add_dropped("too_many")
    
    return result