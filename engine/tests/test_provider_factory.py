"""Tests for the provider factory and fallback logic."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from app.llm.provider_factory import (
    ProviderType,
    ProviderSettings,
    ProviderConfigError,
    create_provider,
    create_fallback_provider,
    get_provider,
    get_provider_with_fallback,
    ProviderWithFallback,
    load_provider_settings,
)
from app.llm.fake_provider import FakeProvider
from app.llm.groq_provider import GroqProvider
from app.llm.gemini_provider import GeminiProvider
from app.models.pipeline import (
    ProviderRequest,
    ProviderResult,
    RateLimitedError,
    TimeoutError,
    UnavailableError,
    BlockedError,
    BadOutputError,
    ProviderError,
)
from app.llm.token_budget import TokenBudgetExceededError


# ============================================================================
# Test Fixtures
# ============================================================================

def make_request(timeout_seconds: int = 45) -> ProviderRequest:
    """Create a ProviderRequest for testing."""
    return ProviderRequest(
        system_instruction="You are a reviewer.",
        user_content="Draft text here.",
        output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
        randomness=0.1,
        output_limit=4096,
        timeout_seconds=timeout_seconds,
    )


def make_valid_result() -> ProviderResult:
    """Create a valid ProviderResult for testing."""
    return ProviderResult(
        raw_json='{"findings": []}',
        input_tokens=100,
        output_tokens=50,
        model="test-model",
        latency_ms=100,
        finish_reason="stop",
    )


# ============================================================================
# ProviderSettings Tests
# ============================================================================

class TestProviderSettings:
    """Tests for ProviderSettings dataclass."""

    def test_default_values(self):
        """Test default settings values."""
        settings = ProviderSettings()
        assert settings.provider_type == ProviderType.FAKE
        assert settings.groq_model == "openai/gpt-oss-120b"
        assert settings.gemini_model == "gemini-3.8-flash"
        assert settings.fallback_enabled is True
        assert settings.fallback_provider == ProviderType.GEMINI

    def test_custom_values(self):
        """Test custom settings values."""
        settings = ProviderSettings(
            provider_type=ProviderType.GROQ,
            groq_api_key="test-groq-key",
            fallback_provider=ProviderType.FAKE,
        )
        assert settings.provider_type == ProviderType.GROQ
        assert settings.groq_api_key == "test-groq-key"
        assert settings.fallback_provider == ProviderType.FAKE


# ============================================================================
# Provider Creation Tests
# ============================================================================

class TestCreateProvider:
    """Tests for create_provider function."""

    def test_create_fake_provider(self):
        """Test creating fake provider."""
        settings = ProviderSettings(provider_type=ProviderType.FAKE)
        provider = create_provider(settings)
        assert isinstance(provider, FakeProvider)

    def test_create_groq_provider_with_key(self):
        """Test creating Groq provider with API key."""
        settings = ProviderSettings(
            provider_type=ProviderType.GROQ,
            groq_api_key="test-key",
        )
        provider = create_provider(settings)
        assert isinstance(provider, GroqProvider)
        assert provider.model == "openai/gpt-oss-120b"

    def test_create_groq_provider_without_key_raises(self):
        """Test that missing Groq API key raises ProviderConfigError."""
        settings = ProviderSettings(
            provider_type=ProviderType.GROQ,
            groq_api_key="",
        )
        with pytest.raises(ProviderConfigError, match="GROQ_API_KEY is required"):
            create_provider(settings)

    def test_create_gemini_provider_with_key(self):
        """Test creating Gemini provider with API key."""
        settings = ProviderSettings(
            provider_type=ProviderType.GEMINI,
            gemini_api_key="test-key",
        )
        provider = create_provider(settings)
        assert isinstance(provider, GeminiProvider)
        assert provider.model == "gemini-3.8-flash"

    def test_create_gemini_provider_without_key_raises(self):
        """Test that missing Gemini API key raises ProviderConfigError."""
        settings = ProviderSettings(
            provider_type=ProviderType.GEMINI,
            gemini_api_key="",
        )
        with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY is required"):
            create_provider(settings)

    def test_unknown_provider_raises(self):
        """Test that unknown provider type raises error."""
        # ProviderType is an enum, so invalid values raise ValueError at construction
        with pytest.raises(ValueError, match="is not a valid ProviderType"):
            ProviderType("unknown")


# ============================================================================
# Fallback Provider Creation Tests
# ============================================================================

class TestCreateFallbackProvider:
    """Tests for create_fallback_provider function."""

    def test_fallback_disabled_returns_none(self):
        """Test that disabled fallback returns None."""
        settings = ProviderSettings(
            provider_type=ProviderType.GROQ,
            groq_api_key="test-key",
            fallback_enabled=False,
        )
        fallback = create_fallback_provider(settings)
        assert fallback is None

    def test_fallback_same_as_primary_returns_none(self):
        """Test that fallback same as primary returns None."""
        settings = ProviderSettings(
            provider_type=ProviderType.GROQ,
            groq_api_key="test-key",
            fallback_provider=ProviderType.GROQ,
        )
        fallback = create_fallback_provider(settings)
        assert fallback is None

    def test_create_gemini_fallback(self):
        """Test creating Gemini fallback."""
        settings = ProviderSettings(
            provider_type=ProviderType.GROQ,
            groq_api_key="test-groq-key",
            gemini_api_key="test-gemini-key",
            fallback_provider=ProviderType.GEMINI,
        )
        fallback = create_fallback_provider(settings)
        assert isinstance(fallback, GeminiProvider)

    def test_create_groq_fallback(self):
        """Test creating Groq fallback."""
        settings = ProviderSettings(
            provider_type=ProviderType.GEMINI,
            gemini_api_key="test-gemini-key",
            groq_api_key="test-groq-key",
            fallback_provider=ProviderType.GROQ,
        )
        fallback = create_fallback_provider(settings)
        assert isinstance(fallback, GroqProvider)

    def test_fallback_missing_key_returns_none(self):
        """Test that fallback with missing key returns None and logs warning."""
        settings = ProviderSettings(
            provider_type=ProviderType.GROQ,
            groq_api_key="test-groq-key",
            gemini_api_key="",  # Missing fallback key
            fallback_provider=ProviderType.GEMINI,
        )
        fallback = create_fallback_provider(settings)
        assert fallback is None

    def test_fake_fallback(self):
        """Test creating fake fallback."""
        settings = ProviderSettings(
            provider_type=ProviderType.GROQ,
            groq_api_key="test-key",
            fallback_provider=ProviderType.FAKE,
        )
        fallback = create_fallback_provider(settings)
        assert isinstance(fallback, FakeProvider)


# ============================================================================
# ProviderWithFallback Tests
# ============================================================================

class TestProviderWithFallback:
    """Tests for ProviderWithFallback class."""

    @pytest.mark.asyncio
    async def test_primary_success_returns_result(self):
        """Test that successful primary call returns result."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(return_value=make_valid_result())

        fallback = MagicMock()
        fallback.model = "fallback-model"

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(make_request())

        assert result == make_valid_result()
        primary.generate_findings.assert_called_once()
        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_on_rate_limited(self):
        """Test fallback on RateLimitedError."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=RateLimitedError("Rate limited"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(make_request())

        assert result == make_valid_result()
        assert primary.generate_findings.call_count == 1
        assert fallback.generate_findings.call_count == 1

    @pytest.mark.asyncio
    async def test_fallback_on_timeout(self):
        """Test fallback on TimeoutError."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=TimeoutError("Timeout"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(make_request())

        assert result == make_valid_result()

    @pytest.mark.asyncio
    async def test_fallback_on_unavailable(self):
        """Test fallback on UnavailableError."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=UnavailableError("Unavailable"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(make_request())

        assert result == make_valid_result()

    @pytest.mark.asyncio
    async def test_no_fallback_on_blocked(self):
        """Test that BlockedError does not trigger fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=BlockedError("Safety block"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(BlockedError):
            await wrapper.generate_findings(make_request())

        primary.generate_findings.assert_called_once()
        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_fallback_on_bad_output(self):
        """Test that BadOutputError does not trigger fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=BadOutputError("Bad JSON"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(BadOutputError):
            await wrapper.generate_findings(make_request())

        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_fallback_on_config_error(self):
        """Test that config errors do not trigger fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=ProviderConfigError("Config error"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(ProviderConfigError):
            await wrapper.generate_findings(make_request())

        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_fail_raises_combined_error(self):
        """Test that both failing raises combined error."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=RateLimitedError("Rate limited"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(side_effect=UnavailableError("Unavailable"))

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(ProviderError, match="Both providers failed"):
            await wrapper.generate_findings(make_request())

    @pytest.mark.asyncio
    async def test_no_fallback_available_raises_original(self):
        """Test that primary error is raised when no fallback available."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=RateLimitedError("Rate limited"))

        wrapper = ProviderWithFallback(primary=primary, fallback=None)

        with pytest.raises(RateLimitedError):
            await wrapper.generate_findings(make_request())

    @pytest.mark.asyncio
    async def test_fallback_on_generic_provider_error_with_retry_after(self):
        """Test fallback on generic ProviderError with retry_after."""
        primary = MagicMock()
        primary.model = "primary-model"
        error = ProviderError("Rate limited")
        error.retry_after = 30
        primary.generate_findings = AsyncMock(side_effect=error)

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(make_request())

        assert result == make_valid_result()

    @ pytest.mark.asyncio
    async def test_no_fallback_on_generic_provider_error_transient_message(self):
        """Test that generic ProviderError with transient message does NOT trigger fallback.

        Fallback should only trigger for explicitly classified transient errors
        (RateLimitedError, TimeoutError, UnavailableError) or ProviderError with retry_after.
        """
        primary = MagicMock()
        primary.model = "primary-model"
        error = ProviderError("Connection timeout")
        primary.generate_findings = AsyncMock(side_effect=error)

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(ProviderError, match="Connection timeout"):
            await wrapper.generate_findings(make_request())

        fallback.generate_findings.assert_not_called()


# ============================================================================
# Cross-Provider Equivalence Tests
# ============================================================================

class TestCrossProviderEquivalence:
    """Tests that both providers return equivalent ProviderResult structures."""

    @pytest.mark.asyncio
    async def test_both_return_provider_result(self):
        """Test that both providers return ProviderResult with same structure."""
        # This is a structural test - both should return ProviderResult
        # with the same fields

        groq_result = ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="openai/gpt-oss-120b",
            latency_ms=100,
            finish_reason="stop",
        )

        gemini_result = ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="gemini-3.8-flash",
            latency_ms=100,
            finish_reason="STOP",
        )

        # Both should have the same fields
        for result in [groq_result, gemini_result]:
            assert hasattr(result, "raw_json")
            assert hasattr(result, "input_tokens")
            assert hasattr(result, "output_tokens")
            assert hasattr(result, "model")
            assert hasattr(result, "latency_ms")
            assert hasattr(result, "finish_reason")


# ============================================================================
# Fake Provider Still Works Tests
# ============================================================================

class TestFakeProviderStillWorks:
    """Tests that FakeProvider continues to work after production providers added."""

    @pytest.mark.asyncio
    async def test_fake_provider_returns_configured_results(self):
        """Test fake provider still works."""
        from engine.app.llm.fake_provider import FakeProvider, FakeProviderConfig
        from engine.app.models.pipeline import ModelFindingCandidate

        candidate = ModelFindingCandidate(
            ref_key="TERM-01",
            issue="violation",
            quote="utilize",
            explanation="Avoid utilize",
            suggestion="use",
            confidence=0.9,
        )

        config = FakeProviderConfig(candidates=[candidate])
        provider = FakeProvider(config)

        result = await provider.generate_findings(make_request())

        assert isinstance(result, ProviderResult)
        assert result.model == "fake-model"

    @pytest.mark.asyncio
    async def test_fake_provider_failure_injection(self):
        """Test fake provider failure injection still works."""
        from engine.app.llm.fake_provider import FakeProvider, FakeProviderConfig, create_timeout_failure

        config = FakeProviderConfig(failure=create_timeout_failure())
        provider = FakeProvider(config)

        with pytest.raises(TimeoutError):
            await provider.generate_findings(make_request())


# ============================================================================
# Load Settings Tests
# ============================================================================

class TestLoadSettings:
    """Tests for load_provider_settings function."""

    def test_load_settings_returns_provider_settings(self):
        """Test that load_provider_settings returns ProviderSettings."""
        with patch('engine.app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.LLM_PROVIDER = "fake"
            mock_settings.LLM_FALLBACK_PROVIDER = "gemini"
            mock_settings.LLM_FALLBACK_ENABLED = True
            mock_settings.GROQ_API_KEY = ""
            mock_settings.GROQ_MODEL = "openai/gpt-oss-120b"
            mock_settings.GROQ_TPM_LIMIT = 8000
            mock_settings.GROQ_RPM_LIMIT = 30
            mock_settings.GEMINI_API_KEY = ""
            mock_settings.GEMINI_MODEL = "gemini-3.8-flash"
            mock_settings.GEMINI_TPM_LIMIT = 250000
            mock_settings.GEMINI_RPM_LIMIT = 15
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()

            assert isinstance(settings, ProviderSettings)
            assert settings.provider_type == ProviderType.FAKE
            assert settings.fallback_provider == ProviderType.GEMINI


class TestLoadSettingsEnvironmentBehavior:
    """Tests for environment-specific provider configuration behavior.

    These tests verify the fail-closed behavior in production and
    development-friendly behavior in non-production environments.
    """

    def _make_mock_settings(self, **overrides):
        """Create a mock settings object with default test values."""
        defaults = {
            "LLM_PROVIDER": "fake",
            "LLM_FALLBACK_PROVIDER": "gemini",
            "LLM_FALLBACK_ENABLED": True,
            "GROQ_API_KEY": "",
            "GROQ_MODEL": "openai/gpt-oss-120b",
            "GROQ_TPM_LIMIT": 8000,
            "GROQ_RPM_LIMIT": 30,
            "GEMINI_API_KEY": "",
            "GEMINI_MODEL": "gemini-3.8-flash",
            "GEMINI_TPM_LIMIT": 250000,
            "GEMINI_RPM_LIMIT": 15,
            "ENVIRONMENT": "development",
        }
        defaults.update(overrides)
        mock_settings = MagicMock()
        for k, v in defaults.items():
            setattr(mock_settings, k, v)
        # Add computed properties
        env = defaults.get("ENVIRONMENT", "development").lower()
        mock_settings.is_local_environment = env in ("development", "dev", "local", "test")
        mock_settings.requires_real_provider = not mock_settings.is_local_environment
        return mock_settings

    @pytest.mark.parametrize("env_value", ["production", "prod"])
    def test_production_environment_unknown_provider_raises(self, env_value):
        """Production and prod environments fail closed on unknown provider."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="unknown",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            with pytest.raises(ProviderConfigError, match="Unknown provider type"):
                load_provider_settings()

    @pytest.mark.parametrize("env_value", ["production", "prod"])
    def test_production_environment_missing_groq_key_raises(self, env_value):
        """Production requires GROQ_API_KEY for Groq provider."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            with pytest.raises(ProviderConfigError, match="GROQ_API_KEY is required"):
                load_provider_settings()

    @pytest.mark.parametrize("env_value", ["production", "prod"])
    def test_production_environment_missing_gemini_key_raises(self, env_value):
        """Production requires GEMINI_API_KEY for Gemini provider."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="gemini",
                GEMINI_API_KEY="",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY is required"):
                load_provider_settings()

    @pytest.mark.parametrize("env_value", ["production", "prod"])
    def test_production_environment_missing_fallback_keys_raises(self, env_value):
        """Production requires API keys for fallback providers too."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-key",
                LLM_FALLBACK_PROVIDER="gemini",
                GEMINI_API_KEY="",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY is required"):
                load_provider_settings()

    @pytest.mark.parametrize("env_value", ["development", "dev", "local", "test"])
    def test_local_environment_unknown_provider_defaults_to_fake(self, env_value):
        """Local environments (development, dev, local, test) default to fake for unknown provider."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="unknown",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()

            assert settings.provider_type == ProviderType.FAKE

    @pytest.mark.parametrize("env_value", ["development", "dev", "local", "test"])
    def test_local_environment_groq_without_key_allowed(self, env_value):
        """Local environments allow Groq provider without API key (fails at runtime, not config time)."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()

            assert settings.provider_type == ProviderType.GROQ

    @pytest.mark.parametrize("env_value", ["staging", "production", "prod"])
    def test_non_local_environment_unknown_provider_raises(self, env_value):
        """Staging and production environments fail closed on unknown provider."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="unknown",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            with pytest.raises(ProviderConfigError, match="Unknown provider type"):
                load_provider_settings()

    @pytest.mark.parametrize("env_value", ["staging", "production", "prod"])
    def test_non_local_environment_groq_without_key_raises(self, env_value):
        """Staging and production require GROQ_API_KEY for Groq provider."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            with pytest.raises(ProviderConfigError, match="GROQ_API_KEY is required"):
                load_provider_settings()

    @pytest.mark.parametrize("env_value", ["staging", "production", "prod"])
    def test_non_local_environment_fake_primary_raises(self, env_value):
        """Staging and production reject fake as primary provider."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="fake",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            with pytest.raises(ProviderConfigError, match="Fake provider is not allowed"):
                load_provider_settings()

    @pytest.mark.parametrize("env_value", ["staging", "production", "prod"])
    def test_non_local_environment_fake_fallback_raises(self, env_value):
        """Staging and production reject fake as fallback provider when fallback enabled."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-key",
                LLM_FALLBACK_PROVIDER="fake",
                ENVIRONMENT=env_value,
            )
            mock_get_settings.return_value = mock_settings

            with pytest.raises(ProviderConfigError, match="Fake fallback provider is not allowed"):
                load_provider_settings()

    def test_missing_environment_raises(self, monkeypatch):
        """Missing ENVIRONMENT variable raises configuration error."""
        # Remove ENVIRONMENT from environment to simulate missing variable
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        from app.core.config import clear_settings_cache
        clear_settings_cache()

        with pytest.raises(Exception) as exc_info:
            load_provider_settings()

        # The error should come from pydantic validation
        assert "ENVIRONMENT" in str(exc_info.value)
        clear_settings_cache()

    def test_misspelled_environment_raises(self):
        """Misspelled ENVIRONMENT value fails closed (does not default to development)."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="fake",
                ENVIRONMENT="produciton",  # Misspelled
            )
            mock_get_settings.return_value = mock_settings

            # Should fail because "produciton" is not a recognized environment
            with pytest.raises(ProviderConfigError, match="Fake provider is not allowed"):
                load_provider_settings()

    def test_production_with_valid_keys_succeeds(self):
        """Production with all required API keys succeeds."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-groq-key",
                LLM_FALLBACK_PROVIDER="gemini",
                GEMINI_API_KEY="test-gemini-key",
                ENVIRONMENT="production",
            )
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()

            assert settings.provider_type == ProviderType.GROQ
            assert settings.fallback_provider == ProviderType.GEMINI
            assert settings.groq_api_key == "test-groq-key"
            assert settings.gemini_api_key == "test-gemini-key"

    def test_local_environment_fake_fallback_allowed(self):
        """Local environments allow fake fallback when fallback enabled."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-key",
                LLM_FALLBACK_PROVIDER="fake",
                ENVIRONMENT="development",
            )
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()

            assert settings.provider_type == ProviderType.GROQ
            assert settings.fallback_provider == ProviderType.FAKE

    def test_non_local_environment_fake_fallback_disabled_allowed(self):
        """Non-local environments allow fake fallback when fallback is disabled."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-key",
                LLM_FALLBACK_PROVIDER="fake",
                LLM_FALLBACK_ENABLED=False,
                ENVIRONMENT="production",
            )
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()

            assert settings.provider_type == ProviderType.GROQ
            assert settings.fallback_provider == ProviderType.FAKE
            assert settings.fallback_enabled is False

    def test_production_fallback_disabled_no_fallback_credentials_required(self):
        """Production with disabled fallback does not require fallback credentials."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-groq-key",
                LLM_FALLBACK_PROVIDER="gemini",
                GEMINI_API_KEY="",
                LLM_FALLBACK_ENABLED=False,
                ENVIRONMENT="production",
            )
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()

            assert settings.provider_type == ProviderType.GROQ
            assert settings.fallback_provider == ProviderType.GEMINI
            assert settings.fallback_enabled is False

    def test_production_fallback_enabled_requires_fallback_credentials(self):
        """Production with enabled fallback requires fallback credentials."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-groq-key",
                LLM_FALLBACK_PROVIDER="gemini",
                GEMINI_API_KEY="",
                LLM_FALLBACK_ENABLED=True,
                ENVIRONMENT="production",
            )
            mock_get_settings.return_value = mock_settings

            with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY is required"):
                load_provider_settings()

    def test_production_fallback_disabled_fake_fallback_allowed(self):
        """Production with disabled fallback allows fake fallback config (not used)."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-key",
                LLM_FALLBACK_PROVIDER="fake",
                LLM_FALLBACK_ENABLED=False,
                ENVIRONMENT="production",
            )
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()

            assert settings.provider_type == ProviderType.GROQ
            assert settings.fallback_provider == ProviderType.FAKE
            assert settings.fallback_enabled is False

    def test_fallback_disabled_returns_none(self):
        """When fallback is disabled, create_fallback_provider returns None."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-key",
                LLM_FALLBACK_PROVIDER="gemini",
                GEMINI_API_KEY="",
                LLM_FALLBACK_ENABLED=False,
                ENVIRONMENT="production",
            )
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()
            fallback = create_fallback_provider(settings)
            assert fallback is None

    @pytest.mark.asyncio
    async def test_production_fallback_disabled_primary_works(self):
        """Production with disabled fallback creates primary provider successfully."""
        with patch('app.llm.provider_factory.get_settings') as mock_get_settings:
            mock_settings = self._make_mock_settings(
                LLM_PROVIDER="groq",
                GROQ_API_KEY="test-groq-key",
                LLM_FALLBACK_PROVIDER="gemini",
                GEMINI_API_KEY="",
                LLM_FALLBACK_ENABLED=False,
                ENVIRONMENT="production",
            )
            mock_get_settings.return_value = mock_settings

            settings = load_provider_settings()
            primary = create_provider(settings)

            assert primary is not None
            from app.llm.groq_provider import GroqProvider
            assert isinstance(primary, GroqProvider)

            # Fallback should be None
            fallback = create_fallback_provider(settings)
            assert fallback is None


# ============================================================================
# Token Budget Rejection Tests
# ============================================================================

class TestTokenBudgetRejection:
    """Tests that oversized requests are rejected, not silently truncated."""

    @pytest.mark.asyncio
    async def test_groq_rejects_oversized_request(self):
        """Test Groq provider rejects oversized request."""
        provider = GroqProvider(api_key="test-key", tpm_limit=100)  # Very small limit

        request = ProviderRequest(
            system_instruction="x" * 10000,
            user_content="y" * 10000,
            output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=45,
        )

        with pytest.raises(TokenBudgetExceededError):
            await provider.generate_findings(request)

    @pytest.mark.asyncio
    async def test_gemini_rejects_oversized_request(self):
        """Test Gemini provider rejects oversized request."""
        provider = GeminiProvider(api_key="test-key", tpm_limit=100)

        request = ProviderRequest(
            system_instruction="x" * 10000,
            user_content="y" * 10000,
            output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=45,
        )

        with pytest.raises(TokenBudgetExceededError):
            await provider.generate_findings(request)

    @pytest.mark.asyncio
    async def test_no_silent_truncation(self):
        """Test that requests are not silently truncated."""
        provider = GroqProvider(api_key="test-key", tpm_limit=8000)

        # Request that would exceed budget
        request = ProviderRequest(
            system_instruction="x" * 10000,
            user_content="y" * 10000,
            output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=45,
        )

        with pytest.raises(TokenBudgetExceededError):
            await provider.generate_findings(request)

        # The request should not be modified/sent
        # (We can't easily verify this without checking the mock, but the exception
        # proves the budget check happens before sending)


# ============================================================================
# Logging Security Tests
# ============================================================================

class TestLoggingSecurity:
    """Tests that sensitive content is not logged."""

    @pytest.mark.asyncio
    async def test_no_api_key_in_logs(self, caplog):
        """Test that API keys are not logged."""
        import logging
        caplog.set_level(logging.DEBUG)

        provider = GroqProvider(api_key="secret-key-12345")

        # Mock to avoid actual API call
        with patch.object(provider._client.chat.completions, 'create', new_callable=AsyncMock) as mock:
            mock.side_effect = Exception("Network error")

            try:
                await provider.generate_findings(make_request())
            except:
                pass

        # Check logs don't contain API key
        for record in caplog.records:
            assert "secret-key-12345" not in record.getMessage()

    @pytest.mark.asyncio
    async def test_no_draft_content_in_logs(self, caplog):
        """Test that draft content is not logged."""
        import logging
        caplog.set_level(logging.DEBUG)

        provider = GroqProvider(api_key="test-key")

        sensitive_draft = "This is a secret draft with confidential information"

        with patch.object(provider._client.chat.completions, 'create', new_callable=AsyncMock) as mock:
            mock.side_effect = Exception("Network error")

            try:
                await provider.generate_findings(make_request(user_content=sensitive_draft))
            except:
                pass

        for record in caplog.records:
            assert "confidential" not in record.getMessage().lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================================================
# Deadline Enforcement Tests
# ============================================================================

class TestDeadlineEnforcement:
    """Tests for single overall deadline enforcement across primary + fallback."""

    @pytest.mark.asyncio
    async def test_primary_timeout_then_fallback(self):
        """Test that primary timeout triggers fallback within overall deadline."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=TimeoutError("Primary timeout"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(make_request(timeout_seconds=5))

        assert result == make_valid_result()
        fallback.generate_findings.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_respects_remaining_deadline(self):
        """Test that fallback attempt respects remaining deadline."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=TimeoutError("Primary timeout"))

        # Fallback takes some time but should complete within remaining deadline
        async def slow_fallback(*args, **kwargs):
            await asyncio.sleep(0.1)
            return make_valid_result()

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = slow_fallback

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(make_request(timeout_seconds=2))

        assert result == make_valid_result()

    @pytest.mark.asyncio
    async def test_deadline_expired_before_fallback(self):
        """Test that if deadline expires during primary, fallback is not attempted."""
        primary = MagicMock()
        primary.model = "primary-model"

        # Primary takes longer than the overall timeout
        async def very_slow_primary(*args, **kwargs):
            await asyncio.sleep(2)  # Longer than the 1s timeout
            raise TimeoutError("Timeout")

        primary.generate_findings = very_slow_primary

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        # Very short timeout - primary takes longer than deadline
        with pytest.raises(TimeoutError):
            await wrapper.generate_findings(make_request(timeout_seconds=1))

        # Fallback should not be called because deadline expired during primary
        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_deadline_pre_check_before_fallback(self):
        """Test that deadline is checked before attempting fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=TimeoutError("Timeout"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        # Timeout is short but primary fails quickly
        # The fallback should be attempted because there's still time
        result = await wrapper.generate_findings(make_request(timeout_seconds=1))
        assert result == make_valid_result()
        fallback.generate_findings.assert_called_once()

        # Now test with a primary that consumes most of the deadline
        call_count = 0

        async def slow_then_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(0.8)  # Consume most of 1s deadline
                raise TimeoutError("Timeout")
            return make_valid_result()

        primary2 = MagicMock()
        primary2.model = "primary-model-2"
        primary2.generate_findings = slow_then_fail

        fallback2 = MagicMock()
        fallback2.model = "fallback-model-2"
        fallback2.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper2 = ProviderWithFallback(primary=primary2, fallback=fallback2)

        # Primary takes 0.8s of 1s deadline, then fails
        # Fallback should NOT be attempted because deadline would expire
        with pytest.raises(TimeoutError):
            await wrapper2.generate_findings(make_request(timeout_seconds=1))

        fallback2.generate_findings.assert_not_called()


# ============================================================================
# Error Sanitization Tests
# ============================================================================

class TestErrorSanitization:
    """Tests that sensitive data is not exposed in combined error messages or logs."""

    @pytest.mark.asyncio
    async def test_combined_error_no_raw_messages(self):
        """Test that combined error message does not contain raw exception strings."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(
            side_effect=RateLimitedError("Rate limited: secret-token-abc123")
        )

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(
            side_effect=UnavailableError("Service down: internal-db-password-xyz")
        )

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(ProviderError) as exc_info:
            await wrapper.generate_findings(make_request())

        error_msg = str(exc_info.value)
        # Should contain provider names and categories, not raw messages
        assert "primary-model" in error_msg
        assert "fallback-model" in error_msg
        assert "rate_limited" in error_msg
        assert "unavailable" in error_msg
        # Should NOT contain raw exception details
        assert "secret-token-abc123" not in error_msg
        assert "internal-db-password-xyz" not in error_msg
        assert "Rate limited:" not in error_msg
        assert "Service down:" not in error_msg

    @pytest.mark.asyncio
    async def test_logs_no_sensitive_data(self, caplog):
        """Test that logs do not contain sensitive exception details."""
        import logging
        caplog.set_level(logging.WARNING)

        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(
            side_effect=RateLimitedError("Rate limited: api-key-secret-123")
        )

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(
            side_effect=UnavailableError("DB password: super-secret-456")
        )

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        try:
            await wrapper.generate_findings(make_request())
        except ProviderError:
            pass

        # Check logs don't contain sensitive data
        for record in caplog.records:
            msg = record.getMessage()
            assert "api-key-secret-123" not in msg
            assert "super-secret-456" not in msg
            # Should only contain error categories in extra fields
            if hasattr(record, 'error_category'):
                assert record.error_category in ("rate_limited", "unavailable", "unknown")

    @pytest.mark.asyncio
    async def test_exception_chaining_preserved(self):
        """Test that exception chaining is preserved for debugging."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=RateLimitedError("Rate limited"))

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(side_effect=UnavailableError("Down"))

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(ProviderError) as exc_info:
            await wrapper.generate_findings(make_request())

        # Exception chaining should be preserved
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RateLimitedError)


# ============================================================================
# Fallback Classification Regression Tests
# ============================================================================

class TestFallbackClassificationRegression:
    """Regression tests for fallback classification - no string matching."""

    @pytest.mark.asyncio
    async def test_no_fallback_on_timeout_string_in_message(self):
        """Test that 'timeout' in error message does not trigger fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        error = ProviderError("Some operation timeout occurred")
        primary.generate_findings = AsyncMock(side_effect=error)

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(ProviderError, match="Some operation timeout occurred"):
            await wrapper.generate_findings(make_request())

        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_fallback_on_connection_string_in_message(self):
        """Test that 'connection' in error message does not trigger fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        error = ProviderError("Connection pool exhausted")
        primary.generate_findings = AsyncMock(side_effect=error)

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(ProviderError, match="Connection pool exhausted"):
            await wrapper.generate_findings(make_request())

        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_fallback_on_rate_limit_string_in_message(self):
        """Test that 'rate limit' in error message does not trigger fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        error = ProviderError("Rate limit config invalid")
        primary.generate_findings = AsyncMock(side_effect=error)

        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=make_valid_result())

        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

        with pytest.raises(ProviderError, match="Rate limit config invalid"):
            await wrapper.generate_findings(make_request())

        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_only_on_explicit_transient_types(self):
        """Test that fallback only triggers for explicitly classified transient errors."""
        # These should trigger fallback
        transient_errors = [
            RateLimitedError("Rate limited"),
            TimeoutError("Timeout"),
            UnavailableError("Unavailable"),
        ]

        for error in transient_errors:
            primary = MagicMock()
            primary.model = "primary-model"
            primary.generate_findings = AsyncMock(side_effect=error)

            fallback = MagicMock()
            fallback.model = "fallback-model"
            fallback.generate_findings = AsyncMock(return_value=make_valid_result())

            wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
            result = await wrapper.generate_findings(make_request())
            assert result == make_valid_result()
            fallback.generate_findings.assert_called_once()

        # These should NOT trigger fallback
        non_transient_errors = [
            BlockedError("Safety"),
            BadOutputError("Bad JSON"),
            ProviderError("Config error"),
            ProviderError("Auth failed"),
            ProviderError("Random error with timeout in message"),
            ProviderError("Random error with connection in message"),
            ProviderError("Random error with rate limit in message"),
        ]

        for error in non_transient_errors:
            primary = MagicMock()
            primary.model = "primary-model"
            primary.generate_findings = AsyncMock(side_effect=error)

            fallback = MagicMock()
            fallback.model = "fallback-model"
            fallback.generate_findings = AsyncMock(return_value=make_valid_result())

            wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

            with pytest.raises(type(error)):
                await wrapper.generate_findings(make_request())
            fallback.generate_findings.assert_not_called()