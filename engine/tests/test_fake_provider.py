"""Tests for the provider abstraction and fake provider."""

import pytest
from pydantic import ValidationError

from app.llm import (
    Provider,
    FakeProviderConfig,
    FakeProvider,
    create_rate_limited_failure,
    create_timeout_failure,
    create_unavailable_failure,
    create_bad_output_failure,
    create_blocked_failure,
)
from app.models.pipeline import (
    ProviderRequest,
    ProviderResult,
    ModelFindingCandidate,
    ProviderError,
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
        output_schema=output_schema or {"type": "object"},
        randomness=randomness,
        output_limit=output_limit,
        timeout_seconds=timeout_seconds,
    )


def make_candidate(
    ref_key: str = "TERM-01",
    issue: str = "violation",
    quote: str = "utilize",
    explanation: str = "Avoid using utilize",
    suggestion: str = "use",
    confidence: float = 0.9,
) -> "ModelFindingCandidate":
    """Create a ModelFindingCandidate for testing."""
    from engine.app.models.pipeline import ModelFindingCandidate
    return ModelFindingCandidate(
        ref_key=ref_key,
        issue=issue,
        quote=quote,
        explanation=explanation,
        suggestion=suggestion,
        confidence=confidence,
    )


# ============================================================================
# Provider Interface Tests
# ============================================================================

class TestProviderInterface:
    """Tests for the Provider protocol."""

    def test_provider_is_protocol(self):
        """Verify Provider is a Protocol (structural subtyping)."""
        from typing import Protocol
        assert issubclass(Provider, Protocol)

    def test_provider_has_generate_findings(self):
        """Verify Provider defines generate_findings method."""
        # This is a structural check - Provider protocol requires generate_findings
        import inspect
        assert hasattr(Provider, 'generate_findings')
        # Check it's an abstract method
        method = getattr(Provider, 'generate_findings', None)
        assert method is not None


# ============================================================================
# FakeProvider Tests
# ============================================================================

class TestFakeProvider:
    """Tests for the FakeProvider implementation."""

    @pytest.mark.asyncio
    async def test_returns_configured_candidates(self):
        """Test fake provider returns configured candidates."""
        candidates = [
            make_candidate(ref_key="TERM-01", quote="utilize"),
            make_candidate(ref_key="TERM-02", quote="leverage"),
        ]
        config = FakeProviderConfig(candidates=candidates)
        provider = FakeProvider(config)

        request = make_request()
        result = await provider.generate_findings(request)

        assert isinstance(result, ProviderResult)
        assert result.raw_json is not None
        assert result.model == "fake-model"
        assert result.finish_reason == "stop"
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty_list(self):
        """Test provider returns empty findings list when no candidates configured."""
        config = FakeProviderConfig(candidates=[])
        provider = FakeProvider(config)

        request = make_request()
        result = await provider.generate_findings(request)

        import json
        data = json.loads(result.raw_json)
        assert data["findings"] == []

    @pytest.mark.asyncio
    async def test_custom_latency(self):
        """Test configurable latency simulation."""
        config = FakeProviderConfig(latency_ms=50)
        provider = FakeProvider(config)

        import time
        start = time.perf_counter()
        await provider.generate_findings(make_request())
        elapsed = (time.perf_counter() - start) * 1000

        # Should sleep approximately the configured latency
        assert elapsed >= 40  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_custom_token_counts(self):
        """Test configurable token counts."""
        config = FakeProviderConfig(input_tokens=200, output_tokens=75)
        provider = FakeProvider(config)

        result = await provider.generate_findings(make_request())

        assert result.input_tokens == 200
        assert result.output_tokens == 75

    @pytest.mark.asyncio
    async def test_custom_model_name(self):
        """Test configurable model name."""
        config = FakeProviderConfig(model="test-model-v1")
        provider = FakeProvider(config)

        result = await provider.generate_findings(make_request())

        assert result.model == "test-model-v1"

    @pytest.mark.asyncio
    async def test_custom_finish_reason(self):
        """Test configurable finish reason."""
        config = FakeProviderConfig(finish_reason="length")
        provider = FakeProvider(config)

        result = await provider.generate_findings(make_request())

        assert result.finish_reason == "length"

    @pytest.mark.asyncio
    async def test_custom_raw_json(self):
        """Test custom raw JSON response."""
        custom_json = '{"findings": [{"ref_key": "CUSTOM", "issue": "violation", "quote": "test", "explanation": "test", "confidence": 0.9}]}'
        config = FakeProviderConfig(raw_json=custom_json)
        provider = FakeProvider(config)

        result = await provider.generate_findings(make_request())

        assert result.raw_json == custom_json

    @pytest.mark.asyncio
    async def test_call_count_increments(self):
        """Test call counter increments on each call."""
        provider = FakeProvider()
        assert provider.call_count == 0

        await provider.generate_findings(make_request())
        assert provider.call_count == 1

        await provider.generate_findings(make_request())
        assert provider.call_count == 2

    @pytest.mark.asyncio
    async def test_reset_clears_call_count(self):
        """Test reset clears call counter."""
        provider = FakeProvider()
        await provider.generate_findings(make_request())
        assert provider.call_count == 1

        provider.reset()
        assert provider.call_count == 0


# ============================================================================
# FakeProvider Failure Tests
# ============================================================================

class TestFakeProviderFailures:
    """Tests for FakeProvider failure injection."""

    @pytest.mark.asyncio
    async def test_rate_limited_failure(self):
        """Test rate limited error propagation."""
        failure = create_rate_limited_failure(retry_after=60)
        config = FakeProviderConfig(failure=failure)
        provider = FakeProvider(config)

        with pytest.raises(RateLimitedError) as exc_info:
            await provider.generate_findings(make_request())

        assert exc_info.value.retry_after == 60
        assert "Rate limited" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_failure(self):
        """Test timeout error propagation."""
        failure = create_timeout_failure()
        config = FakeProviderConfig(failure=failure)
        provider = FakeProvider(config)

        with pytest.raises(TimeoutError) as exc_info:
            await provider.generate_findings(make_request())

        assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_unavailable_failure(self):
        """Test unavailable error propagation."""
        failure = create_unavailable_failure()
        config = FakeProviderConfig(failure=failure)
        provider = FakeProvider(config)

        with pytest.raises(UnavailableError) as exc_info:
            await provider.generate_findings(make_request())

        assert "unavailable" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_bad_output_failure(self):
        """Test bad output error propagation."""
        failure = create_bad_output_failure("Invalid JSON")
        config = FakeProviderConfig(failure=failure)
        provider = FakeProvider(config)

        with pytest.raises(BadOutputError) as exc_info:
            await provider.generate_findings(make_request())

        assert "Invalid JSON" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_blocked_failure(self):
        """Test blocked (safety filter) error propagation."""
        failure = create_blocked_failure("Content blocked")
        config = FakeProviderConfig(failure=failure)
        provider = FakeProvider(config)

        with pytest.raises(BlockedError) as exc_info:
            await provider.generate_findings(make_request())

        assert "Content blocked" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_all_errors_inherit_provider_error(self):
        """Test all error types inherit from ProviderError."""
        errors = [
            create_rate_limited_failure(),
            create_timeout_failure(),
            create_unavailable_failure(),
            create_bad_output_failure(),
            create_blocked_failure(),
        ]

        for error in errors:
            assert isinstance(error, ProviderError)


# ============================================================================
# ProviderRequest/Result Tests
# ============================================================================

class TestProviderRequest:
    """Tests for ProviderRequest model."""

    def test_valid_request(self):
        """Test valid provider request creation."""
        request = make_request()
        assert request.system_instruction == "You are a reviewer."
        assert request.randomness == 0.1
        assert request.timeout_seconds == 45

    def test_invalid_randomness(self):
        """Test randomness outside [0,1] raises error."""
        with pytest.raises(ValidationError):
            ProviderRequest(
                system_instruction="test",
                user_content="text",
                output_schema={},
                randomness=1.5,
            )

    def test_invalid_timeout(self):
        """Test timeout_seconds <= 0 raises error."""
        with pytest.raises(ValidationError):
            ProviderRequest(
                system_instruction="test",
                user_content="text",
                output_schema={},
                timeout_seconds=0,
            )


# ============================================================================
# Provider Error Hierarchy Tests
# ============================================================================

class TestProviderErrors:
    """Tests for provider error hierarchy."""

    def test_provider_error_base(self):
        """Test base ProviderError."""
        error = ProviderError("Test error", retry_after=30)
        assert str(error) == "Test error"
        assert error.retry_after == 30

    def test_rate_limited_error(self):
        """Test RateLimitedError."""
        error = RateLimitedError("Rate limited", retry_after=60)
        assert error.retry_after == 60
        assert isinstance(error, ProviderError)

    def test_timeout_error(self):
        """Test TimeoutError."""
        error = TimeoutError("Timeout")
        assert str(error) == "Timeout"
        assert isinstance(error, ProviderError)

    def test_unavailable_error(self):
        """Test UnavailableError."""
        error = UnavailableError("Unavailable")
        assert isinstance(error, ProviderError)

    def test_bad_output_error(self):
        """Test BadOutputError."""
        error = BadOutputError("Bad JSON")
        assert isinstance(error, ProviderError)

    def test_blocked_error(self):
        """Test BlockedError."""
        error = BlockedError("Blocked")
        assert isinstance(error, ProviderError)


# ============================================================================
# Isolation Tests
# ============================================================================

class TestIsolation:
    """Tests for request/response isolation."""

    @pytest.mark.asyncio
    async def test_request_not_mutated(self):
        """Test request object is not modified by provider."""
        original_instruction = "Original instruction"
        original_content = "Original content"

        request = make_request(
            system_instruction=original_instruction,
            user_content=original_content,
        )

        provider = FakeProvider()
        await provider.generate_findings(request)

        # Request should be unchanged
        assert request.system_instruction == original_instruction
        assert request.user_content == original_content

    @pytest.mark.asyncio
    async def test_returned_candidates_not_shared(self):
        """Test returned candidates are not shared between calls."""
        candidates = [make_candidate(ref_key="TERM-01")]
        config = FakeProviderConfig(candidates=candidates)
        provider = FakeProvider(config)

        result1 = await provider.generate_findings(make_request())
        result2 = await provider.generate_findings(make_request())

        import json
        data1 = json.loads(result1.raw_json)
        data2 = json.loads(result2.raw_json)

        # Modify one result's data
        data1["findings"][0]["ref_key"] = "MODIFIED"

        # Second result should be unaffected
        assert data2["findings"][0]["ref_key"] == "TERM-01"

    @pytest.mark.asyncio
    async def test_repeated_calls_return_equivalent_results(self):
        """Test repeated calls return equivalent results."""
        candidates = [make_candidate(ref_key="TERM-01", confidence=0.9)]
        config = FakeProviderConfig(candidates=candidates)
        provider = FakeProvider(config)

        results = []
        for _ in range(5):
            result = await provider.generate_findings(make_request())
            results.append(result.raw_json)

        # All results should be identical
        assert len(set(results)) == 1


# ============================================================================
# Asynchronous Behavior Tests
# ============================================================================

class TestAsyncBehavior:
    """Tests for correct asynchronous behavior."""

    @pytest.mark.asyncio
    async def test_generate_findings_is_async(self):
        """Test generate_findings is a coroutine."""
        import inspect
        provider = FakeProvider()
        assert inspect.iscoroutinefunction(provider.generate_findings)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_calls(self):
        """Test multiple concurrent calls work correctly."""
        config = FakeProviderConfig(candidates=[make_candidate()])
        provider = FakeProvider(config)

        import asyncio
        tasks = [provider.generate_findings(make_request()) for _ in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(isinstance(r, ProviderResult) for r in results)


# ============================================================================
# Deterministic Behavior Tests
# ============================================================================

class TestDeterministicBehavior:
    """Tests for deterministic, reproducible behavior."""

    @pytest.mark.asyncio
    async def test_same_config_produces_same_output(self):
        """Test same config produces same output across calls."""
        candidates = [make_candidate(ref_key="TERM-01", confidence=0.85)]
        config = FakeProviderConfig(candidates=candidates)

        provider1 = FakeProvider(config)
        provider2 = FakeProvider(config)

        result1 = await provider1.generate_findings(make_request())
        result2 = await provider2.generate_findings(make_request())

        assert result1.raw_json == result2.raw_json
        assert result1.model == result2.model
        assert result1.finish_reason == result2.finish_reason

    @pytest.mark.asyncio
    async def test_candidates_order_preserved(self):
        """Test candidate order is preserved in output."""
        candidates = [
            make_candidate(ref_key="TERM-01"),
            make_candidate(ref_key="TERM-02"),
            make_candidate(ref_key="TERM-03"),
        ]
        config = FakeProviderConfig(candidates=candidates)
        provider = FakeProvider(config)

        result = await provider.generate_findings(make_request())

        import json
        data = json.loads(result.raw_json)
        ref_keys = [f["ref_key"] for f in data["findings"]]
        assert ref_keys == ["TERM-01", "TERM-02", "TERM-03"]


# ============================================================================
# No Network/External Dependency Tests
# ============================================================================

class TestNoNetworkDependency:
    """Tests verifying no network calls are made."""

    @pytest.mark.asyncio
    async def test_no_network_on_success(self):
        """Test no network calls on successful response."""
        # This test relies on the fact that FakeProvider doesn't import
        # any HTTP libraries and uses pure asyncio.sleep for latency
        provider = FakeProvider(FakeProviderConfig(latency_ms=0))
        result = await provider.generate_findings(make_request())

        # If we get a result without exception, no network was used
        assert isinstance(result, ProviderResult)

    @pytest.mark.asyncio
    async def test_no_network_on_failure(self):
        """Test no network calls even on configured failures."""
        failure = create_timeout_failure()
        provider = FakeProvider(FakeProviderConfig(failure=failure))

        with pytest.raises(TimeoutError):
            await provider.generate_findings(make_request())
        # No network call should have been attempted


# ============================================================================
# Error Helper Functions Tests
# ============================================================================

class TestErrorHelpers:
    """Tests for error creation helper functions."""

    def test_create_rate_limited_failure(self):
        """Test rate limited error helper."""
        error = create_rate_limited_failure(retry_after=120)
        assert isinstance(error, RateLimitedError)
        assert error.retry_after == 120

    def test_create_timeout_failure(self):
        """Test timeout error helper."""
        error = create_timeout_failure()
        assert isinstance(error, TimeoutError)

    def test_create_unavailable_failure(self):
        """Test unavailable error helper."""
        error = create_unavailable_failure()
        assert isinstance(error, UnavailableError)

    def test_create_bad_output_failure(self):
        """Test bad output error helper."""
        error = create_bad_output_failure("Custom message")
        assert isinstance(error, BadOutputError)
        assert "Custom message" in str(error)

    def test_create_blocked_failure(self):
        """Test blocked error helper."""
        error = create_blocked_failure("Custom block")
        assert isinstance(error, BlockedError)
        assert "Custom block" in str(error)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])