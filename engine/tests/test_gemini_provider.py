"""Tests for the Gemini provider implementation."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.gemini_provider import GeminiProvider
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
# GeminiProvider Initialization Tests
# ============================================================================

class TestGeminiProviderInit:
    """Tests for GeminiProvider initialization."""

    def test_init_with_valid_api_key(self):
        """Test successful initialization with valid API key."""
        provider = GeminiProvider(api_key="test-key-123")
        assert provider.model == "gemini-3.8-flash"
        assert provider._tpm_limit == 250000
        assert provider._rpm_limit == 15

    def test_init_with_custom_model(self):
        """Test initialization with custom model."""
        provider = GeminiProvider(api_key="test-key", model="gemini-3.5-flash-lite")
        assert provider.model == "gemini-3.5-flash-lite"

    def test_init_with_custom_limits(self):
        """Test initialization with custom rate limits."""
        provider = GeminiProvider(api_key="test-key", tpm_limit=500000, rpm_limit=30)
        assert provider._tpm_limit == 500000
        assert provider._rpm_limit == 30

    def test_init_empty_api_key_raises(self):
        """Test that empty API key raises ValueError."""
        with pytest.raises(ValueError, match="must be provided and non-empty"):
            GeminiProvider(api_key="")

    def test_init_none_api_key_raises(self):
        """Test that None API key raises ValueError."""
        with pytest.raises(ValueError, match="must be provided and non-empty"):
            GeminiProvider(api_key=None)


# ============================================================================
# Schema Adaptation Tests
# ============================================================================

class TestGeminiSchemaAdaptation:
    """Tests for Gemini schema adaptation."""

    def test_adapt_schema_converts_nullable_type_unions(self):
        """Translate JSON Schema T|null unions to OpenAPI nullable fields."""
        provider = GeminiProvider(api_key="test-key")

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

        adapted = provider._build_gemini_schema(schema)

        suggestion = adapted["properties"]["findings"]["items"]["properties"]["suggestion"]
        confidence = adapted["properties"]["findings"]["items"]["properties"]["confidence"]

        assert suggestion["type"] == "STRING"
        assert suggestion["nullable"] is True
        assert confidence["type"] == "NUMBER"
        assert confidence["nullable"] is True

    def test_adapt_schema_preserves_enum(self):
        """Test that enum constraints are preserved."""
        provider = GeminiProvider(api_key="test-key")

        schema = {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "issue": {
                                "type": "string",
                                "enum": ["violation", "contradicts_fact", "outdated_fact", "unsupported_claim"],
                            },
                        },
                        "required": ["issue"],
                    },
                },
            },
            "required": ["findings"],
        }

        adapted = provider._build_gemini_schema(schema)

        issue = adapted["properties"]["findings"]["items"]["properties"]["issue"]
        assert issue["enum"] == ["violation", "contradicts_fact", "outdated_fact", "unsupported_claim"]

    def test_adapt_schema_preserves_minlength(self):
        """Test that minLength is preserved (Gemini supports it)."""
        provider = GeminiProvider(api_key="test-key")

        schema = {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "quote": {"type": "string", "minLength": 1},
                        },
                        "required": ["quote"],
                    },
                },
            },
            "required": ["findings"],
        }

        adapted = provider._build_gemini_schema(schema)

        quote = adapted["properties"]["findings"]["items"]["properties"]["quote"]
        assert quote["minLength"] == 1


# ============================================================================
# Refusal Detection Tests
# ============================================================================

class TestGeminiRefusalDetection:
    """Tests for safety refusal detection."""

    def test_detect_explicit_refusal(self):
        """Test detection of explicit refusal phrases."""
        provider = GeminiProvider(api_key="test-key")

        refusals = [
            "I cannot comply with this request.",
            "I can't help with that.",
            "I am unable to process this.",
            "As an AI, I must refuse.",
            "This request violates safety guidelines.",
            "Content blocked due to policy.",
        ]

        for refusal in refusals:
            assert provider._detect_refusal(refusal, None) is True

    def test_detect_valid_response_not_refusal(self):
        """Test that valid responses are not flagged as refusals."""
        provider = GeminiProvider(api_key="test-key")

        valid_responses = [
            '{"findings": []}',
            '{"findings": [{"ref_key": "TERM-01", "issue": "violation", "quote": "test", "explanation": "test"}]}',
            "Here is the analysis you requested.",
            "The draft looks good with no issues.",
        ]

        for response in valid_responses:
            assert provider._detect_refusal(response, None) is False

    def test_empty_content_is_refusal(self):
        """Test that empty content is treated as refusal."""
        provider = GeminiProvider(api_key="test-key")
        assert provider._detect_refusal("", None) is True
        assert provider._detect_refusal("   ", None) is True


# ============================================================================
# Truncation Detection Tests
# ============================================================================

class TestGeminiTruncationDetection:
    """Tests for response truncation detection."""

    def test_detect_max_tokens_finish_reason(self):
        """Test detection via finish_reason."""
        provider = GeminiProvider(api_key="test-key")
        assert provider._detect_truncation('{"findings": []}', "MAX_TOKENS") is True
        assert provider._detect_truncation('{"findings": []}', "TOKEN_LIMIT") is True
        assert provider._detect_truncation('{"findings": []}', "LENGTH") is True

    def test_detect_incomplete_json(self):
        """Test detection of incomplete JSON."""
        provider = GeminiProvider(api_key="test-key")

        assert provider._detect_truncation('{"findings": [', "STOP") is True
        assert provider._detect_truncation('{"findings": [{"ref_key": "TERM-01"}', "STOP") is True

    def test_detect_unbalanced_braces(self):
        """Test detection of unbalanced braces/brackets."""
        provider = GeminiProvider(api_key="test-key")

        assert provider._detect_truncation('{"findings": [{"ref_key": "TERM-01"}]}', "STOP") is False

    def test_valid_complete_json_not_truncated(self):
        """Test that valid complete JSON is not flagged."""
        provider = GeminiProvider(api_key="test-key")
        valid = '{"findings": [{"ref_key": "TERM-01", "issue": "violation", "quote": "test", "explanation": "test"}]}'
        assert provider._detect_truncation(valid, "STOP") is False


# ============================================================================
# Response Parsing Tests
# ============================================================================

class TestGeminiResponseParsing:
    """Tests for response parsing and validation."""

    def test_parse_valid_response(self):
        """Test parsing a valid response."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        # Mock response
        response = MagicMock()
        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [MagicMock(text=make_valid_response())]
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]
        response.usage_metadata = MagicMock()
        response.usage_metadata.prompt_token_count = 100
        response.usage_metadata.candidates_token_count = 50

        result = provider._parse_response(response, request)

        assert isinstance(result, ProviderResult)
        assert result.model == "gemini-3.8-flash"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.finish_reason == "STOP"

    def test_parse_empty_candidates_raises(self):
        """Test that empty candidates raises BadOutputError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        response = MagicMock()
        response.candidates = []

        with pytest.raises(BadOutputError, match="no candidates returned"):
            provider._parse_response(response, request)

    def test_parse_invalid_json_raises(self):
        """Test that invalid JSON raises BadOutputError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        response = MagicMock()
        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [MagicMock(text="not valid json")]
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]
        response.usage_metadata = MagicMock()

        with pytest.raises(BadOutputError, match="Invalid JSON"):
            provider._parse_response(response, request)

    def test_parse_missing_findings_raises(self):
        """Test that missing findings object raises BadOutputError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        response = MagicMock()
        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [MagicMock(text='{"other": "data"}')]
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]
        response.usage_metadata = MagicMock()

        with pytest.raises(BadOutputError, match="missing 'findings'"):
            provider._parse_response(response, request)

    def test_parse_findings_not_array_raises(self):
        """Test that non-array findings raises BadOutputError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        response = MagicMock()
        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [MagicMock(text='{"findings": "not an array"}')]
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]
        response.usage_metadata = MagicMock()

        with pytest.raises(BadOutputError, match="must be an array"):
            provider._parse_response(response, request)

    def test_parse_invalid_finding_raises(self):
        """Test that invalid finding structure raises BadOutputError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        bad_finding = {"ref_key": "TERM-01", "issue": "violation", "explanation": "test"}
        response = MagicMock()
        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [MagicMock(text=json.dumps({"findings": [bad_finding]}))]
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]
        response.usage_metadata = MagicMock()

        with pytest.raises(BadOutputError, match="validation failed"):
            provider._parse_response(response, request)

    def test_parse_safety_finish_reason_raises_blocked(self):
        """Test that SAFETY finish_reason raises BlockedError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        response = MagicMock()
        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [MagicMock(text='{"findings": []}')]
        candidate.finish_reason = "SAFETY"
        response.candidates = [candidate]
        response.usage_metadata = MagicMock()

        with pytest.raises(BlockedError):
            provider._parse_response(response, request)

    def test_parse_refusal_in_content_raises_blocked(self):
        """Test that refusal in content raises BlockedError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        response = MagicMock()
        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [MagicMock(text="I cannot comply with this request.")]
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]
        response.usage_metadata = MagicMock()

        with pytest.raises(BlockedError):
            provider._parse_response(response, request)

    def test_parse_truncated_raises_bad_output(self):
        """Test that truncated response raises BadOutputError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        response = MagicMock()
        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [MagicMock(text='{"findings": [')]
        candidate.finish_reason = "MAX_TOKENS"
        response.candidates = [candidate]
        response.usage_metadata = MagicMock()

        # Invalid JSON is caught first, before truncation check
        with pytest.raises(BadOutputError, match="Invalid JSON"):
            provider._parse_response(response, request)


# ============================================================================
# Error Mapping Tests
# ============================================================================

class TestGeminiErrorMapping:
    """Tests for error mapping in generate_findings."""

    def test_safe_error_metadata_is_bounded_and_redacts_api_key(self):
        provider = GeminiProvider(api_key="secret-test-key")
        error = Exception("503 Service Unavailable secret-test-key " + ("x" * 700))
        error.status_code = 503

        metadata = provider._safe_error_metadata(error)

        assert metadata["error_type"] == "Exception"
        assert metadata["status_code"] == 503
        assert "secret-test-key" not in metadata["error_detail"]
        assert "[REDACTED_API_KEY]" in metadata["error_detail"]
        assert len(metadata["error_detail"]) <= 500

    @pytest.mark.asyncio
    async def test_rate_limit_mapped(self):
        """Test that rate limit errors are mapped to RateLimitedError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        with patch.object(provider._client.aio.models, 'generate_content', new_callable=AsyncMock) as mock_generate:
            error = Exception("Rate limit exceeded: 429")
            error.retry_delay = 30
            mock_generate.side_effect = error

            with pytest.raises(RateLimitedError) as exc_info:
                await provider.generate_findings(request)

            assert exc_info.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_timeout_mapped(self):
        """Test that timeout errors are mapped to TimeoutError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        with patch.object(provider._client.aio.models, 'generate_content', new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = Exception("Request timeout")

            with pytest.raises(TimeoutError):
                await provider.generate_findings(request)

    @pytest.mark.asyncio
    async def test_retry_is_skipped_when_backoff_exceeds_provider_deadline(self):
        """A retry must not begin when the shared provider deadline cannot cover its backoff."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request(timeout_seconds=1)

        error = Exception("Rate limit exceeded: 429")
        error.retry_delay = 10

        with patch.object(provider._client.aio.models, "generate_content", new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = error

            with pytest.raises(RateLimitedError):
                await provider.generate_findings(request)

            assert mock_generate.await_count == 1

    @pytest.mark.asyncio
    async def test_5xx_mapped_to_unavailable(self):
        """Test that 5xx errors are mapped to UnavailableError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        with patch.object(provider._client.aio.models, 'generate_content', new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = Exception("503 Service Unavailable")

            with pytest.raises(UnavailableError):
                await provider.generate_findings(request)

    @pytest.mark.asyncio
    async def test_auth_error_not_retried(self):
        """Test that authentication errors are not retried."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        with patch.object(provider._client.aio.models, 'generate_content', new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = Exception("401 Unauthorized: Invalid API key")

            with pytest.raises(Exception, match="authentication failed"):
                await provider.generate_findings(request)

    @pytest.mark.asyncio
    async def test_safety_permission_denied_mapped_to_blocked(self):
        """Test that safety-related permission denied is mapped to BlockedError."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        with patch.object(provider._client.aio.models, 'generate_content', new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = Exception("Permission denied: Safety filter triggered")

            with pytest.raises(BlockedError):
                await provider.generate_findings(request)

    @pytest.mark.asyncio
    async def test_retry_once_on_rate_limit(self):
        """Test that rate limit triggers exactly one retry."""
        provider = GeminiProvider(api_key="test-key")
        request = make_request()

        call_count = 0

        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                error = Exception("Rate limit exceeded")
                error.retry_delay = 1
                raise error
            # Second call succeeds
            response = MagicMock()
            candidate = MagicMock()
            candidate.content = MagicMock()
            candidate.content.parts = [MagicMock(text=make_valid_response())]
            candidate.finish_reason = "STOP"
            response.candidates = [candidate]
            response.usage_metadata = MagicMock()
            response.usage_metadata.prompt_token_count = 100
            response.usage_metadata.candidates_token_count = 50
            return response

        with patch.object(provider._client.aio.models, 'generate_content', new=mock_generate):
            result = await provider.generate_findings(request)
            assert isinstance(result, ProviderResult)
            assert call_count == 2


    @pytest.mark.asyncio
    async def test_uses_adapted_openapi_schema_field_for_shared_output_contract(self):
        provider = GeminiProvider(api_key="test-key")
        request = make_request(output_schema={
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
        })
        response = MagicMock()
        candidate = MagicMock()
        candidate.content.parts = [MagicMock(text=make_valid_response())]
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]
        response.usage_metadata = MagicMock(
            prompt_token_count=100, candidates_token_count=50
        )
        with patch.object(
            provider._client.aio.models, "generate_content", new=AsyncMock(return_value=response)
        ) as mock_generate:
            await provider.generate_findings(request)
        config = mock_generate.await_args.kwargs["config"]
        assert not hasattr(config, "response_json_schema")
        assert config.response_schema["properties"]["findings"]["items"]["properties"]["suggestion"] == {
            "type": "STRING", "nullable": True
        }


# ============================================================================
# ModelFindingCandidate Validation Tests
# ============================================================================

class TestGeminiModelFindingValidation:
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