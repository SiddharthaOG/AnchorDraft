"""Tests for the pipeline models."""
import pytest
from pydantic import ValidationError
from engine.app.models.pipeline import (
    ModelFindingCandidate,
    DeterministicFindingCandidate,
    ValidatedFinding,
    ValidatorOutcome,
    AggregateValidationResult,
    ProviderRequest,
    ProviderResult,
    ProviderError,
    RateLimitedError,
    TimeoutError,
    BadOutputError,
    BlockedError,
)


class TestModelFindingCandidate:
    """Tests for ModelFindingCandidate model."""

    def test_valid_model_candidate(self):
        """Test a valid model finding candidate."""
        candidate = ModelFindingCandidate(
            ref_key="TERM-01",
            issue="violation",
            quote="utilize",
            explanation="Avoid using utilize",
            suggestion="use",
            confidence=0.9,
        )
        assert candidate.ref_key == "TERM-01"
        assert candidate.issue == "violation"
        assert candidate.confidence == 0.9

    def test_valid_model_candidate_without_optional_fields(self):
        """Test a valid model finding candidate without optional fields."""
        candidate = ModelFindingCandidate(
            ref_key="TERM-01",
            issue="violation",
            quote="utilize",
            explanation="Avoid using utilize",
        )
        assert candidate.suggestion is None
        assert candidate.confidence is None

    def test_invalid_issue_value(self):
        """Test that invalid issue value raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ModelFindingCandidate(
                ref_key="TERM-01",
                issue="invalid_issue",
                quote="utilize",
                explanation="Avoid using utilize",
            )
        assert "issue" in str(exc_info.value)

    def test_missing_required_fields(self):
        """Test that missing required fields raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ModelFindingCandidate(
                ref_key="TERM-01",
                # missing issue, quote, explanation
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("issue",) for e in errors)
        assert any(e["loc"] == ("quote",) for e in errors)
        assert any(e["loc"] == ("explanation",) for e in errors)

    def test_confidence_below_zero(self):
        """Test that confidence below 0 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ModelFindingCandidate(
                ref_key="TERM-01",
                issue="violation",
                quote="utilize",
                explanation="Avoid using utilize",
                confidence=-0.1,
            )
        assert "confidence" in str(exc_info.value)

    def test_confidence_above_one(self):
        """Test that confidence above 1 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ModelFindingCandidate(
                ref_key="TERM-01",
                issue="violation",
                quote="utilize",
                explanation="Avoid using utilize",
                confidence=1.1,
            )
        assert "confidence" in str(exc_info.value)

    def test_extra_fields_rejected(self):
        """Test that extra fields are rejected (extra='forbid')."""
        with pytest.raises(ValidationError) as exc_info:
            ModelFindingCandidate(
                ref_key="TERM-01",
                issue="violation",
                quote="utilize",
                explanation="Avoid using utilize",
                extra_field="not_allowed",
            )
        assert "extra" in str(exc_info.value)

    def test_quote_preserves_whitespace(self):
        """Test that quote preserves leading/trailing whitespace."""
        candidate = ModelFindingCandidate(
            ref_key="TERM-01",
            issue="violation",
            quote="  utilize  ",
            explanation="Avoid using utilize",
        )
        assert candidate.quote == "  utilize  "


class TestDeterministicFindingCandidate:
    """Tests for DeterministicFindingCandidate model."""

    def test_valid_deterministic_candidate(self):
        """Test a valid deterministic finding candidate."""
        candidate = DeterministicFindingCandidate(
            ref_key="TERM-01",
            quote="utilize",
            start_offset=10,
            end_offset=17,
            explanation="Avoid using utilize",
            suggestion="use",
            rule_category="terminology",
            severity="low",
            needs_reviewer=False,
        )
        assert candidate.ref_key == "TERM-01"
        assert candidate.start_offset == 10
        assert candidate.end_offset == 17

    def test_valid_deterministic_candidate_short_quote(self):
        """Test that deterministic candidates can have quotes shorter than 4 chars."""
        candidate = DeterministicFindingCandidate(
            ref_key="TERM-01",
            quote="it",
            start_offset=5,
            end_offset=7,
            explanation="Test quote",
            suggestion="this",
            rule_category="terminology",
            severity="low",
        )
        assert candidate.quote == "it"

    def test_invalid_offsets(self):
        """Test that end_offset <= start_offset raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DeterministicFindingCandidate(
                ref_key="TERM-01",
                quote="utilize",
                start_offset=10,
                end_offset=10,  # Not greater than start_offset
                explanation="Avoid using utilize",
                suggestion="use",
                rule_category="terminology",
                severity="low",
            )
        assert "end_offset" in str(exc_info.value)

    def test_missing_required_fields(self):
        """Test that missing required fields raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DeterministicFindingCandidate(
                ref_key="TERM-01",
                # missing quote, start_offset, end_offset, etc.
            )
        errors = exc_info.value.errors()
        required_fields = {"quote", "start_offset", "end_offset", "explanation",
                          "rule_category", "severity"}
        found_fields = {e["loc"][0] for e in errors}
        assert required_fields.issubset(found_fields)

    def test_extra_fields_rejected(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            DeterministicFindingCandidate(
                ref_key="TERM-01",
                quote="utilize",
                start_offset=10,
                end_offset=17,
                explanation="Avoid using utilize",
                suggestion="use",
                rule_category="terminology",
                severity="low",
                extra_field="not_allowed",
            )
        assert "extra" in str(exc_info.value)


class TestValidatedFinding:
    """Tests for ValidatedFinding model."""

    def test_valid_validated_finding(self):
        """Test a valid validated finding."""
        finding = ValidatedFinding(
            source="deterministic",
            ref_key="TERM-01",
            category="terminology",
            severity="low",
            quote="utilize",
            start_offset=10,
            end_offset=17,
            explanation="Avoid using utilize",
            suggestion="use",
            confidence=0.9,
            needs_human=False,
            needs_reviewer=False,
        )
        assert finding.source == "deterministic"
        assert finding.confidence == 0.9

    def test_valid_validated_finding_llm(self):
        """Test a valid LLM validated finding."""
        finding = ValidatedFinding(
            source="llm",
            ref_key="CLAIM-01",
            category="claim",
            severity="high",
            quote="100% guaranteed results",
            start_offset=100,
            end_offset=120,
            explanation="Absolute claims require substantiation",
            confidence=0.95,
            needs_human=True,
            needs_reviewer=True,
        )
        assert finding.source == "llm"
        assert finding.confidence == 0.95

    def test_valid_validated_finding_without_optional_fields(self):
        """Test validated finding without optional fields."""
        finding = ValidatedFinding(
            source="deterministic",
            ref_key="TERM-01",
            category="terminology",
            severity="low",
            quote="utilize",
            start_offset=10,
            end_offset=17,
            explanation="Avoid using utilize",
        )
        assert finding.suggestion is None
        assert finding.confidence is None
        assert finding.needs_human is False
        assert finding.needs_reviewer is False

    def test_invalid_offsets(self):
        """Test that end_offset <= start_offset raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatedFinding(
                source="deterministic",
                ref_key="TERM-01",
                category="terminology",
                severity="low",
                quote="utilize",
                start_offset=10,
                end_offset=10,
                explanation="Avoid using utilize",
            )
        assert "end_offset" in str(exc_info.value)

    def test_invalid_confidence_below_zero(self):
        """Test that confidence below 0 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatedFinding(
                source="deterministic",
                ref_key="TERM-01",
                category="terminology",
                severity="low",
                quote="utilize",
                start_offset=10,
                end_offset=17,
                explanation="Avoid using utilize",
                confidence=-0.1,
            )
        assert "confidence" in str(exc_info.value)

    def test_invalid_confidence_above_one(self):
        """Test that confidence above 1 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatedFinding(
                source="deterministic",
                ref_key="TERM-01",
                category="terminology",
                severity="low",
                quote="utilize",
                start_offset=10,
                end_offset=17,
                explanation="Avoid using utilize",
                confidence=1.1,
            )
        assert "confidence" in str(exc_info.value)

    def test_invalid_source(self):
        """Test that invalid source raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatedFinding(
                source="invalid_source",
                ref_key="TERM-01",
                category="terminology",
                severity="low",
                quote="utilize",
                start_offset=10,
                end_offset=17,
                explanation="Avoid using utilize",
            )
        assert "source" in str(exc_info.value)

    def test_extra_fields_rejected(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatedFinding(
                source="deterministic",
                ref_key="TERM-01",
                category="terminology",
                severity="low",
                quote="utilize",
                start_offset=10,
                end_offset=17,
                explanation="Avoid using utilize",
                extra_field="not_allowed",
            )
        assert "extra" in str(exc_info.value)


class TestValidatorOutcome:
    """Tests for ValidatorOutcome model."""

    def test_kept_outcome_with_finding(self):
        """Test a kept validator outcome with validated_finding."""
        finding = ValidatedFinding(
            source="deterministic",
            ref_key="TERM-01",
            category="terminology",
            severity="low",
            quote="utilize",
            start_offset=10,
            end_offset=17,
            explanation="Avoid using utilize",
            suggestion="use",
        )
        outcome = ValidatorOutcome(
            candidate_ref="TERM-01",
            source="deterministic",
            kept=True,
            drop_reason=None,
            validated_finding=finding,
        )
        assert outcome.kept is True
        assert outcome.drop_reason is None
        assert outcome.validated_finding is not None

    def test_kept_outcome_without_finding_fails(self):
        """Test that kept=True without validated_finding fails."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatorOutcome(
                candidate_ref="TERM-01",
                source="deterministic",
                kept=True,
                drop_reason=None,
                validated_finding=None,
            )
        assert "validated_finding must be provided when kept is True" in str(exc_info.value)

    def test_dropped_outcome(self):
        """Test a dropped validator outcome."""
        outcome = ValidatorOutcome(
            candidate_ref="TERM-01",
            source="llm",
            kept=False,
            drop_reason="unknown_ref",
        )
        assert outcome.kept is False
        assert outcome.drop_reason == "unknown_ref"

    def test_drop_reason_required_when_dropped(self):
        """Test that drop_reason is required when kept=False."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatorOutcome(
                candidate_ref="TERM-01",
                source="llm",
                kept=False,
                drop_reason=None,
            )
        assert "drop_reason" in str(exc_info.value)

    def test_drop_reason_must_be_none_when_kept(self):
        """Test that drop_reason must be None when kept=True."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatorOutcome(
                candidate_ref="TERM-01",
                source="deterministic",
                kept=True,
                drop_reason="unknown_ref",
            )
        assert "drop_reason" in str(exc_info.value)

    def test_invalid_drop_reason(self):
        """Test that invalid drop reason raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatorOutcome(
                candidate_ref="TERM-01",
                source="llm",
                kept=False,
                drop_reason="invalid_reason",
            )
        assert "drop_reason" in str(exc_info.value)

    def test_validated_finding_must_be_none_when_dropped(self):
        """Test that validated_finding must be None when kept=False."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatorOutcome(
                candidate_ref="TERM-01",
                source="llm",
                kept=False,
                drop_reason="unknown_ref",
                validated_finding=ValidatedFinding(
                    source="llm",
                    ref_key="TERM-01",
                    category="claim",
                    severity="high",
                    quote="100% guaranteed",
                    start_offset=0,
                    end_offset=15,
                    explanation="Test",
                ),
            )
        assert "validated_finding must be None when kept is False" in str(exc_info.value)

    def test_dropped_outcome_with_validated_finding_fails(self):
        """Test that validated_finding must be None when kept=False."""
        with pytest.raises(ValidationError) as exc_info:
            ValidatorOutcome(
                candidate_ref="TERM-01",
                source="llm",
                kept=False,
                drop_reason="unknown_ref",
                validated_finding=ValidatedFinding(
                    source="llm",
                    ref_key="TERM-01",
                    category="claim",
                    severity="high",
                    quote="100% guaranteed",
                    start_offset=0,
                    end_offset=15,
                    explanation="Test",
                ),
            )
        assert "validated_finding must be None when kept is False" in str(exc_info.value)


class TestAggregateValidationResult:
    """Tests for AggregateValidationResult model."""

    def test_empty_result(self):
        """Test empty aggregate result."""
        result = AggregateValidationResult()
        assert result.validated_findings == []
        assert result.raw_candidate_count == 0
        assert result.kept_count == 0
        assert result.dropped_counts == {}

    def test_add_kept(self):
        """Test adding a kept finding."""
        result = AggregateValidationResult()
        finding = ValidatedFinding(
            source="deterministic",
            ref_key="TERM-01",
            category="terminology",
            severity="low",
            quote="utilize",
            start_offset=10,
            end_offset=17,
            explanation="Avoid using utilize",
            suggestion="use",
        )
        result.add_kept(finding)
        assert result.kept_count == 1
        assert len(result.validated_findings) == 1
        assert result.raw_candidate_count == 1
        assert result.dropped_counts == {}

    def test_add_dropped(self):
        """Test adding a dropped candidate."""
        result = AggregateValidationResult()
        result.add_dropped("unknown_ref")
        result.add_dropped("unknown_ref")
        result.add_dropped("quote_not_found")
        assert result.dropped_counts == {"unknown_ref": 2, "quote_not_found": 1}
        assert result.kept_count == 0
        assert result.raw_candidate_count == 3

    def test_mixed_kept_and_dropped(self):
        """Test mixing kept and dropped findings."""
        result = AggregateValidationResult()
        finding = ValidatedFinding(
            source="deterministic",
            ref_key="TERM-01",
            category="terminology",
            severity="low",
            quote="utilize",
            start_offset=10,
            end_offset=17,
            explanation="Avoid using utilize",
        )
        result.add_kept(finding)
        result.add_dropped("unknown_ref")
        assert result.kept_count == 1
        assert result.dropped_counts == {"unknown_ref": 1}
        assert result.raw_candidate_count == 2

    def test_invalid_drop_reason_rejected(self):
        """Test that invalid drop reason is rejected."""
        result = AggregateValidationResult()
        with pytest.raises(ValueError) as exc_info:
            result.add_dropped("invalid_reason")
        assert "Invalid drop reason" in str(exc_info.value)

    def test_negative_drop_counts_rejected(self):
        """Test that negative drop counts are not possible."""
        result = AggregateValidationResult()
        result.add_dropped("unknown_ref")
        assert result.dropped_counts["unknown_ref"] == 1
        # Cannot decrement - only increment via add_dropped


class TestProviderRequest:
    """Tests for ProviderRequest model."""

    def test_valid_provider_request(self):
        """Test a valid provider request."""
        request = ProviderRequest(
            system_instruction="You are a reviewer.",
            user_content="Draft text here.",
            output_schema={"type": "object"},
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=45,
        )
        assert request.system_instruction == "You are a reviewer."
        assert request.randomness == 0.1
        assert request.timeout_seconds == 45

    def test_invalid_randomness(self):
        """Test that randomness outside [0,1] raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ProviderRequest(
                system_instruction="test",
                user_content="text",
                output_schema={},
                randomness=1.5,
            )
        assert "randomness" in str(exc_info.value)

    def test_invalid_timeout(self):
        """Test that timeout_seconds <= 0 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ProviderRequest(
                system_instruction="test",
                user_content="text",
                output_schema={},
                timeout_seconds=0,
            )
        assert "timeout_seconds" in str(exc_info.value)

    def test_extra_fields_rejected(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ProviderRequest(
                system_instruction="test",
                user_content="text",
                output_schema={},
                extra_field="not_allowed",
            )
        assert "extra" in str(exc_info.value)


class TestProviderResult:
    """Tests for ProviderResult model."""

    def test_valid_provider_result(self):
        """Test a valid provider result."""
        result = ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="gemini-1.5-flash",
            latency_ms=500,
            finish_reason="stop",
        )
        assert result.model == "gemini-1.5-flash"
        assert result.input_tokens == 100

    def test_negative_tokens_rejected(self):
        """Test that negative token counts are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ProviderResult(
                raw_json='{"findings": []}',
                input_tokens=-1,
                output_tokens=50,
                model="gemini",
                latency_ms=100,
                finish_reason="stop",
            )
        assert "input_tokens" in str(exc_info.value)


class TestProviderExceptions:
    """Tests for provider exception classes."""

    def test_provider_error(self):
        """Test base provider error."""
        exc = ProviderError("Test error", retry_after=30)
        assert str(exc) == "Test error"
        assert exc.retry_after == 30

    def test_rate_limited_error(self):
        """Test rate limited error."""
        exc = RateLimitedError("Rate limited", retry_after=60)
        assert exc.retry_after == 60

    def test_timeout_error(self):
        """Test timeout error."""
        exc = TimeoutError("Timeout")
        assert str(exc) == "Timeout"

    def test_bad_output_error(self):
        """Test bad output error."""
        exc = BadOutputError("Invalid JSON")
        assert str(exc) == "Invalid JSON"

    def test_blocked_error(self):
        """Test blocked error."""
        exc = BlockedError("Safety block")
        assert str(exc) == "Safety block"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
