"""Tests for the Groq provider implementation."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.groq_provider import GroqProvider
from app.llm.token_budget import TokenBudgetExceededError
from app.models.pipeline import (
    ProviderRequest,
    ProviderResult,
    ModelFindingCandidate,
    RateLimitedError,
    TimeoutError,
    UnavailableError,
    BadOutputError,
    BlockedError,
)


# ============================================================================
# Test Fixtures and Helpers
# ============================================================================

def make_request(
    system_instruction: str = "You are a reviewer.",
    user_content: str = "Draft text here.",
    output_schema: dict = None,
    randomness: float = 0.1,
    output_limit: int = 4096,
    timeout_seconds: int = 45,
) -> ProviderRequest:
    """Create a ProviderRequest for testing."""
    return ProviderRequest(
        system_instruction=system_instruction,
        user_content=user_content,
        output_schema=output_schema or {"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
        randomness=randomness,
        output_limit=output_limit,
        timeout_seconds=timeout_seconds,
    )


def make_finding_dict(
    ref_key: str = "TERM-01",
    issue: str = "violation",
    quote: str = "utilize",
    explanation: str = "Avoid using utilize",
    suggestion: str = "use",
    confidence: float = 0.9,
) -> dict:
    """Create a finding dict for testing."""
    return {
        "ref_key": ref_key,
        "issue": issue,
        "quote": quote,
        "explanation": explanation,
        "suggestion": suggestion,
        "confidence": confidence,
    }


def make_valid_response(findings: list = None) -> str:
    """Create a valid JSON response."""
    if findings is None:
        findings = [make_finding_dict()]
    return json.dumps({"findings": findings})


# ============================================================================
# GroqProvider Initialization Tests
# ============================================================================

class TestGroqProviderInit:
    """Tests for GroqProvider initialization."""

    def test_init_with_valid_api_key(self):
        """Test successful initialization with valid API key."""
        provider = GroqProvider(api_key="test-key-123")
        assert provider.model == "openai/gpt-oss-120b"
        assert provider._tpm_limit == 250000
        assert provider._rpm_limit == 30

    def test_init_with_custom_model(self):
        """Test initialization with custom model."""
        provider = GroqProvider(api_key="test-key", model="openai/gpt-oss-20b")
        assert provider.model == "openai/gpt-oss-20b"

    def test_init_with_custom_limits(self):
        """Test initialization with custom rate limits."""
        provider = GroqProvider(api_key="test-key", tpm_limit=16000, rpm_limit=60)
        assert provider._tpm_limit == 16000
        assert provider._rpm_limit == 60

    def test_init_empty_api_key_raises(self):
        """Test that empty API key raises ValueError."""
        with pytest.raises(ValueError, match="must be provided and non-empty"):
            GroqProvider(api_key="")

    def test_init_none_api_key_raises(self):
        """Test that None API key raises ValueError."""
        with pytest.raises(ValueError, match="must be provided and non-empty"):
            GroqProvider(api_key=None)


# ============================================================================
# Schema Adaptation Tests
# ============================================================================

class TestGroqSchemaAdaptation:
    """Tests for Groq strict-mode schema adaptation."""

    def test_adapt_schema_all_properties_required(self):
        """Test that all properties are added to required array."""
        provider = GroqProvider(api_key="test-key")

        schema = {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ref_key": {"type": "string"},
                            "issue": {"type": "string"},
                            "quote": {"type": "string"},
                            "explanation": {"type": "string"},
                            "suggestion": {"type": ["string", "null"]},
                            "confidence": {"type": ["number", "null"]},
                        },
                        "required": ["ref_key", "issue", "quote", "explanation"],
                    },
                },
            },
            "required": ["findings"],
        }

        adapted = provider._build_groq_schema(schema)

        findings_schema = adapted["properties"]["findings"]["items"]
        required = findings_schema["required"]

        # All properties should be in required
        assert "ref_key" in required
        assert "issue" in required
        assert "quote" in required
        assert "explanation" in required
        assert "suggestion" in required
        assert "confidence" in required

    def test_adapt_schema_additional_properties_false(self):
        """Test that additionalProperties: false is set."""
        provider = GroqProvider(api_key="test-key")

        schema = {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"ref_key": {"type": "string"}},
                        "required": ["ref_key"],
                    },
                },
            },
            "required": ["findings"],
        }

        adapted = provider._build_groq_schema(schema)

        assert adapted["additionalProperties"] is False
        findings_schema = adapted["properties"]["findings"]["items"]
        assert findings_schema["additionalProperties"] is False

    def test_adapt_schema_preserves_nullable_types(self):
        """Test that nullable type arrays are preserved."""
        provider = GroqProvider(api_key="test-key")

        schema = {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "suggestion": {"type": ["string", "null"]},
                            "confidence": {"type": ["number", "null"]},
                        },
                        "required": ["suggestion", "confidence"],
                    },
                },
            },
            "required": ["findings"],
        }

        adapted = provider._build_groq_schema(schema)

        suggestion = adapted["properties"]["findings"]["items"]["properties"]["suggestion"]
        confidence = adapted["properties"]["findings"]["items"]["properties"]["confidence"]

        assert suggestion["type"] == ["string", "null"]
        assert confidence["type"] == ["number", "null"]


# ============================================================================
# Refusal Detection Tests
# ============================================================================

class TestGroqRefusalDetection:
    """Tests for safety refusal detection."""

    def test_detect_explicit_refusal(self):
        """Test detection of explicit refusal phrases."""
        provider = GroqProvider(api_key="test-key")

        refusals = [
            "I cannot comply with this request.",
            "I can't help with that.",
            "I am unable to process this.",
            "As an AI, I must refuse.",
            "This request violates safety guidelines.",
            "Content blocked due to policy.",
        ]

        for refusal in refusals:
            assert provider._detect_refusal(refusal) is True

    def test_detect_valid_response_not_refusal(self):
        """Test that valid responses are not flagged as refusals."""
        provider = GroqProvider(api_key="test-key")

        valid_responses = [
            '{"findings": []}',
            '{"findings": [{"ref_key": "TERM-01", "issue": "violation", "quote": "test", "explanation": "test"}]}',
            "Here is the analysis you requested.",
            "The draft looks good with no issues.",
        ]

        for response in valid_responses:
            assert provider._detect_refusal(response) is False

    def test_empty_content_is_refusal(self):
        """Test that empty content is treated as refusal."""
        provider = GroqProvider(api_key="test-key")
        assert provider._detect_refusal("") is True
        assert provider._detect_refusal("   ") is True


# ============================================================================
# Truncation Detection Tests
# ============================================================================

class TestGroqTruncationDetection:
    """Tests for response truncation detection."""

    def test_detect_length_finish_reason(self):
        """Test detection via finish_reason."""
        provider = GroqProvider(api_key="test-key")
        assert provider._detect_truncation('{"findings": []}', "length") is True
        assert provider._detect_truncation('{"findings": []}', "max_tokens") is True
        assert provider._detect_truncation('{"findings": []}', "token_limit") is True

    def test_detect_incomplete_json(self):
        """Test detection of incomplete JSON."""
        provider = GroqProvider(api_key="test-key")

        # Missing closing brace
        assert provider._detect_truncation('{"findings": [', "stop") is True
        # Missing closing bracket
        assert provider._detect_truncation('{"findings": [{"ref_key": "TERM-01"}', "stop") is True

    def test_detect_unbalanced_braces(self):
        """Test detection of unbalanced braces/brackets."""
        provider = GroqProvider(api_key="test-key")

        assert provider._detect_truncation('{"findings": [{"ref_key": "TERM-01"}]}', "stop") is False
        assert provider._detect_truncation('{"findings": [{"ref_key": "TERM-01"}]}', "stop") is False

    def test_valid_complete_json_not_truncated(self):
        """Test that valid complete JSON is not flagged."""
        provider = GroqProvider(api_key="test-key")
        valid = '{"findings": [{"ref_key": "TERM-01", "issue": "violation", "quote": "test", "explanation": "test"}]}'
        assert provider._detect_truncation(valid, "stop") is False


# ============================================================================
# Response Parsing Tests
# ============================================================================

class TestGroqResponseParsing:
    """Tests for response parsing and validation."""

    def test_parse_valid_response(self):
        """Test parsing a valid response."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        # Mock completion
        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = make_valid_response()
        completion.choices[0].finish_reason = "stop"
        completion.usage = MagicMock()
        completion.usage.prompt_tokens = 100
        completion.usage.completion_tokens = 50

        result = provider._parse_response(completion, request)

        assert isinstance(result, ProviderResult)
        assert result.model == "openai/gpt-oss-120b"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.finish_reason == "stop"

    def test_parse_empty_choices_raises(self):
        """Test that empty choices raises BadOutputError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        completion = MagicMock()
        completion.choices = []

        with pytest.raises(BadOutputError, match="no choices returned"):
            provider._parse_response(completion, request)

    def test_parse_invalid_json_raises(self):
        """Test that invalid JSON raises BadOutputError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = "not valid json"
        completion.choices[0].finish_reason = "stop"
        completion.usage = MagicMock()
        completion.usage.prompt_tokens = 100
        completion.usage.completion_tokens = 50

        with pytest.raises(BadOutputError, match="Invalid JSON"):
            provider._parse_response(completion, request)

    def test_parse_missing_findings_raises(self):
        """Test that missing findings object raises BadOutputError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = '{"other": "data"}'
        completion.choices[0].finish_reason = "stop"
        completion.usage = MagicMock()

        with pytest.raises(BadOutputError, match="missing 'findings'"):
            provider._parse_response(completion, request)

    def test_parse_findings_not_array_raises(self):
        """Test that non-array findings raises BadOutputError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = '{"findings": "not an array"}'
        completion.choices[0].finish_reason = "stop"
        completion.usage = MagicMock()

        with pytest.raises(BadOutputError, match="must be an array"):
            provider._parse_response(completion, request)

    def test_parse_invalid_finding_raises(self):
        """Test that invalid finding structure raises BadOutputError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        # Missing required field (quote)
        bad_finding = {"ref_key": "TERM-01", "issue": "violation", "explanation": "test"}
        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = json.dumps({"findings": [bad_finding]})
        completion.choices[0].finish_reason = "stop"
        completion.usage = MagicMock()

        with pytest.raises(BadOutputError, match="validation failed"):
            provider._parse_response(completion, request)

    def test_parse_refusal_raises_blocked(self):
        """Test that safety refusal raises BlockedError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = "I cannot comply with this request."
        completion.choices[0].finish_reason = "stop"
        completion.usage = MagicMock()

        with pytest.raises(BlockedError):
            provider._parse_response(completion, request)

    def test_parse_truncated_raises_bad_output(self):
        """Test that truncated response raises BadOutputError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = '{"findings": ['
        completion.choices[0].finish_reason = "length"
        completion.usage = MagicMock()

        # Invalid JSON is caught first, before truncation check
        with pytest.raises(BadOutputError, match="Invalid JSON"):
            provider._parse_response(completion, request)


# ============================================================================
# Token Budget Tests
# ============================================================================

class TestGroqTokenBudget:
    """Tests for token budget checking."""

    def test_budget_check_passes_for_small_request(self):
        """Test that small requests pass budget check."""
        provider = GroqProvider(api_key="test-key", tpm_limit=8000)
        request = make_request(
            system_instruction="Short instruction",
            user_content="Short content",
            output_limit=100,
        )

        # Should not raise
        provider._build_groq_schema(request.output_schema)

    @pytest.mark.asyncio
    async def test_budget_check_fails_for_large_request(self):
        """Test that large requests fail budget check in generate_findings."""
        provider = GroqProvider(api_key="test-key", tpm_limit=100)  # Very small limit
        request = make_request(
            system_instruction="x" * 10000,
            user_content="y" * 10000,
            output_limit=4096,
        )

        with pytest.raises(TokenBudgetExceededError):
            await provider.generate_findings(request)


# ============================================================================
# Error Mapping Tests (via mocked generate_findings)
# ============================================================================

class TestGroqErrorMapping:
    """Tests for error mapping in generate_findings."""

    @pytest.mark.asyncio
    async def test_rate_limit_mapped(self):
        """Test that rate limit errors are mapped to RateLimitedError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        # Mock the client to raise a rate limit error
        with patch.object(provider._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            error = Exception("Rate limit exceeded")
            error.response = MagicMock()
            error.response.headers = {"retry-after": "30"}
            mock_create.side_effect = error

            with pytest.raises(RateLimitedError) as exc_info:
                await provider.generate_findings(request)

            assert exc_info.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_timeout_mapped(self):
        """Test that timeout errors are mapped to TimeoutError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        with patch.object(provider._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("Request timeout")

            with pytest.raises(TimeoutError):
                await provider.generate_findings(request)

    @pytest.mark.asyncio
    async def test_5xx_mapped_to_unavailable(self):
        """Test that 5xx errors are mapped to UnavailableError."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        with patch.object(provider._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("503 Service Unavailable")

            with pytest.raises(UnavailableError):
                await provider.generate_findings(request)

    @pytest.mark.asyncio
    async def test_auth_error_not_retried(self):
        """Test that authentication errors are not retried and raise ProviderError."""
        from app.models.pipeline import ProviderError
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        with patch.object(provider._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("401 Unauthorized: Invalid API key")

            with pytest.raises(ProviderError, match="authentication failed"):
                await provider.generate_findings(request)

    @pytest.mark.asyncio
    async def test_retry_once_on_rate_limit(self):
        """Test that rate limit triggers exactly one retry."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                error = Exception("Rate limit exceeded")
                error.response = MagicMock()
                error.response.headers = {"retry-after": "1"}
                raise error
            # Second call succeeds
            completion = MagicMock()
            completion.choices = [MagicMock()]
            completion.choices[0].message.content = make_valid_response()
            completion.choices[0].finish_reason = "stop"
            completion.usage = MagicMock()
            completion.usage.prompt_tokens = 100
            completion.usage.completion_tokens = 50
            return completion

        with patch.object(provider._client.chat.completions, 'create', new=mock_create):
            result = await provider.generate_findings(request)
            assert isinstance(result, ProviderResult)
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_blocked(self):
        """Test that safety blocks don't trigger retry."""
        provider = GroqProvider(api_key="test-key")
        request = make_request()

        async def mock_create(*args, **kwargs):
            completion = MagicMock()
            completion.choices = [MagicMock()]
            completion.choices[0].message.content = "I cannot comply with this request."
            completion.choices[0].finish_reason = "stop"
            completion.usage = MagicMock()
            return completion

        with patch.object(provider._client.chat.completions, 'create', new=mock_create):
            with pytest.raises(BlockedError):
                await provider.generate_findings(request)


# ============================================================================
# ModelFindingCandidate Validation Tests
# ============================================================================

class TestGroqModelFindingValidation:
    """Tests that response findings are validated against ModelFindingCandidate."""

    def test_valid_finding_passes(self):
        """Test that a valid finding passes validation."""
        finding = make_finding_dict()
        candidate = ModelFindingCandidate.model_validate(finding)
        assert candidate.ref_key == "TERM-01"
        assert candidate.issue == "violation"

    def test_nullable_suggestion(self):
        """Test that null suggestion is valid."""
        finding = make_finding_dict(suggestion=None)
        candidate = ModelFindingCandidate.model_validate(finding)
        assert candidate.suggestion is None

    def test_nullable_confidence(self):
        """Test that null confidence is valid."""
        finding = make_finding_dict(confidence=None)
        candidate = ModelFindingCandidate.model_validate(finding)
        assert candidate.confidence is None

    def test_confidence_bounds(self):
        """Test confidence bounds validation."""
        with pytest.raises(Exception):
            ModelFindingCandidate.model_validate(make_finding_dict(confidence=1.5))
        with pytest.raises(Exception):
            ModelFindingCandidate.model_validate(make_finding_dict(confidence=-0.1))

    def test_issue_enum_validation(self):
        """Test that issue must be valid enum."""
        with pytest.raises(Exception):
            ModelFindingCandidate.model_validate(make_finding_dict(issue="invalid"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])