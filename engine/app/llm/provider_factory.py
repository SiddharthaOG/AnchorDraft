"""Provider factory and configuration.

This module provides the factory for creating and configuring LLM providers
with support for primary/fallback selection.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.core.config import get_settings
from app.llm.provider import Provider
from app.llm.fake_provider import FakeProvider
from app.llm.groq_provider import GroqProvider
from app.llm.gemini_provider import GeminiProvider
from app.models.pipeline import (
    ProviderError,
    ProviderRequest,
    ProviderResult,
    UnavailableError,
    TimeoutError,
)

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Supported provider types."""
    FAKE = "fake"
    GROQ = "groq"
    GEMINI = "gemini"


class ProviderConfigError(ProviderError):
    """Configuration error for provider setup."""
    pass


@dataclass
class ProviderSettings:
    """Provider-specific settings loaded from environment."""
    provider_type: ProviderType = ProviderType.FAKE
    # Groq settings
    groq_api_key: Optional[str] = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_tpm_limit: int = 8000
    groq_rpm_limit: int = 30
    # Gemini settings
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_tpm_limit: int = 250000
    gemini_rpm_limit: int = 15
    # Fallback settings
    fallback_enabled: bool = True
    fallback_provider: ProviderType = ProviderType.GEMINI


def load_provider_settings() -> ProviderSettings:
    """Load provider settings from environment/configuration.

    Returns:
        ProviderSettings with all configuration values.

    Raises:
        ProviderConfigError: If provider configuration is invalid for the environment.
    """
    settings = get_settings()

    # Determine primary provider
    provider_str = getattr(settings, "LLM_PROVIDER", "fake").lower()
    try:
        provider_type = ProviderType(provider_str)
    except ValueError:
        # Unknown provider: allow in local environments (default to fake), reject in non-local
        if settings.is_local_environment:
            logger.warning(
                "unknown_provider_type",
                extra={"provider": provider_str, "defaulting_to": "fake", "environment": settings.ENVIRONMENT},
            )
            provider_type = ProviderType.FAKE
        else:
            raise ProviderConfigError(
                f"Unknown provider type: '{provider_str}'. Valid options: {[p.value for p in ProviderType]}"
            )

    # Reject fake provider in non-local environments
    if provider_type == ProviderType.FAKE and settings.requires_real_provider:
        raise ProviderConfigError(
            f"Fake provider is not allowed in {settings.ENVIRONMENT} environment. "
            f"Use a real provider (groq or gemini)."
        )

    # Determine fallback provider
    fallback_str = getattr(settings, "LLM_FALLBACK_PROVIDER", "gemini").lower()
    try:
        fallback_provider = ProviderType(fallback_str)
    except ValueError:
        # Unknown fallback: allow in local environments (default to gemini), reject in non-local
        if settings.is_local_environment:
            logger.warning(
                "unknown_fallback_provider",
                extra={"provider": fallback_str, "defaulting_to": "gemini", "environment": settings.ENVIRONMENT},
            )
            fallback_provider = ProviderType.GEMINI
        else:
            raise ProviderConfigError(
                f"Unknown fallback provider: '{fallback_str}'. Valid options: {[p.value for p in ProviderType]}"
            )

    # Reject fake fallback in non-local environments when fallback is enabled
    fallback_enabled = getattr(settings, "LLM_FALLBACK_ENABLED", True)
    if fallback_provider == ProviderType.FAKE and fallback_enabled and settings.requires_real_provider:
        raise ProviderConfigError(
            f"Fake fallback provider is not allowed in {settings.ENVIRONMENT} environment. "
            f"Use a real fallback provider (groq or gemini) or disable fallback."
        )

    # In non-local environments, require credentials only for providers
    # that will actually be used.
    if settings.requires_real_provider:
        if provider_type == ProviderType.GROQ and not getattr(settings, "GROQ_API_KEY", "").strip():
            raise ProviderConfigError(
                "GROQ_API_KEY is required for Groq primary provider in non-local environment"
            )

        if provider_type == ProviderType.GEMINI and not getattr(settings, "GEMINI_API_KEY", "").strip():
            raise ProviderConfigError(
                "GEMINI_API_KEY is required for Gemini primary provider in non-local environment"
            )

        # A disabled fallback must not require credentials.
        if fallback_enabled:
            if fallback_provider == ProviderType.GROQ and not getattr(settings, "GROQ_API_KEY", "").strip():
                raise ProviderConfigError(
                    "GROQ_API_KEY is required for Groq fallback in non-local environment"
                )

            if fallback_provider == ProviderType.GEMINI and not getattr(settings, "GEMINI_API_KEY", "").strip():
                raise ProviderConfigError(
                    "GEMINI_API_KEY is required for Gemini fallback in non-local environment"
                )

    return ProviderSettings(
        provider_type=provider_type,
        groq_api_key=getattr(settings, "GROQ_API_KEY", None),
        groq_model=getattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b"),
        groq_tpm_limit=getattr(settings, "GROQ_TPM_LIMIT", 8000),
        groq_rpm_limit=getattr(settings, "GROQ_RPM_LIMIT", 30),
        gemini_api_key=getattr(settings, "GEMINI_API_KEY", None),
        gemini_model=getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash"),
        gemini_tpm_limit=getattr(settings, "GEMINI_TPM_LIMIT", 250000),
        gemini_rpm_limit=getattr(settings, "GEMINI_RPM_LIMIT", 15),
        fallback_enabled=getattr(settings, "LLM_FALLBACK_ENABLED", True),
        fallback_provider=fallback_provider,
    )


def create_provider(settings: Optional[ProviderSettings] = None) -> Provider:
    """Create the primary provider instance.

    Args:
        settings: Optional ProviderSettings. If not provided, loads from config.

    Returns:
        Provider instance.

    Raises:
        ProviderConfigError: If required credentials are missing or fake provider used in non-local environment.
    """
    if settings is None:
        settings = load_provider_settings()

    # Defensive check: fake provider should not be created in non-local environments
    if settings.provider_type == ProviderType.FAKE:
        # Check if we're in a non-local environment by reloading settings
        from app.core.config import get_settings as _get_settings
        _settings = _get_settings()
        if _settings.requires_real_provider:
            raise ProviderConfigError(
                f"Fake provider is not allowed in {_settings.ENVIRONMENT} environment"
            )
        return FakeProvider()

    elif settings.provider_type == ProviderType.GROQ:
        if not settings.groq_api_key:
            raise ProviderConfigError(
                "GROQ_API_KEY is required for Groq provider but not configured"
            )
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            tpm_limit=settings.groq_tpm_limit,
            rpm_limit=settings.groq_rpm_limit,
        )

    elif settings.provider_type == ProviderType.GEMINI:
        if not settings.gemini_api_key:
            raise ProviderConfigError(
                "GEMINI_API_KEY is required for Gemini provider but not configured"
            )
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            tpm_limit=settings.gemini_tpm_limit,
            rpm_limit=settings.gemini_rpm_limit,
        )

    else:
        raise ProviderConfigError(f"Unknown provider type: {settings.provider_type}")


def create_fallback_provider(settings: Optional[ProviderSettings] = None) -> Optional[Provider]:
    """Create the fallback provider instance.

    Args:
        settings: Optional ProviderSettings. If not provided, loads from config.

    Returns:
        Provider instance or None if fallback is disabled or not configured.

    Raises:
        ProviderConfigError: If fake fallback is used in non-local environment.
    """
    if settings is None:
        settings = load_provider_settings()

    if not settings.fallback_enabled:
        return None

    # Don't create fallback if it's the same as primary
    if settings.fallback_provider == settings.provider_type:
        return None

    # Defensive check: fake fallback should not be created in non-local environments
    if settings.fallback_provider == ProviderType.FAKE:
        from app.core.config import get_settings as _get_settings
        _settings = _get_settings()
        if _settings.requires_real_provider:
            raise ProviderConfigError(
                f"Fake fallback provider is not allowed in {_settings.ENVIRONMENT} environment"
            )
        return FakeProvider()

    try:
        if settings.fallback_provider == ProviderType.GROQ:
            if not settings.groq_api_key:
                logger.warning("groq_fallback_not_configured", extra={"reason": "missing_api_key"})
                return None
            return GroqProvider(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                tpm_limit=settings.groq_tpm_limit,
                rpm_limit=settings.groq_rpm_limit,
            )

        elif settings.fallback_provider == ProviderType.GEMINI:
            if not settings.gemini_api_key:
                logger.warning("gemini_fallback_not_configured", extra={"reason": "missing_api_key"})
                return None
            return GeminiProvider(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                tpm_limit=settings.gemini_tpm_limit,
                rpm_limit=settings.gemini_rpm_limit,
            )

    except Exception as e:
        logger.warning(
            "fallback_provider_creation_failed",
            extra={"fallback_provider": settings.fallback_provider.value, "error_type": type(e).__name__},
        )
        return None

    return None


class ProviderWithFallback:
    """Wrapper that implements primary provider with automatic fallback.

    This class implements the Provider protocol and handles:
    - Primary provider invocation
    - Fallback on transient failures (rate limit, timeout, unavailable)
    - No fallback on auth errors, config errors, safety blocks, or bad output
    - Single overall deadline for the complete operation (primary + retry + fallback)
    """

    # Class-level constant for minimum time needed for a fallback attempt
    MIN_FALLBACK_TIME_SECONDS = 0.5

    def __init__(
        self,
        primary: Provider,
        fallback: Optional[Provider] = None,
    ):
        """Initialize with primary and optional fallback provider.

        Args:
            primary: The primary provider.
            fallback: Optional fallback provider.
        """
        self._primary = primary
        self._fallback = fallback

    @property
    def primary_model(self) -> str:
        """Return primary provider model identifier."""
        return getattr(self._primary, "model", "unknown")

    @property
    def fallback_model(self) -> Optional[str]:
        """Return fallback provider model identifier if available."""
        if self._fallback:
            return getattr(self._fallback, "model", "unknown")
        return None

    def _should_fallback(self, error: Exception) -> bool:
        """Determine if an error should trigger fallback.

        Only explicitly classified transient errors trigger fallback.
        No string matching on generic error messages.

        Args:
            error: The exception that occurred.

        Returns:
            True if fallback should be attempted, False otherwise.
        """
        from app.models.pipeline import (
            RateLimitedError,
            TimeoutError,
            UnavailableError,
            BlockedError,
            BadOutputError,
        )

        # Never fallback for these error types
        if isinstance(error, (BlockedError, BadOutputError)):
            return False

        # Never fallback for config/auth errors
        error_type_name = type(error).__name__
        if error_type_name in ("ProviderConfigError", "AuthenticationError", "PermissionError"):
            return False

        # Only fallback for explicitly classified transient errors
        if isinstance(error, (RateLimitedError, TimeoutError, UnavailableError)):
            return True

        # Generic ProviderError: only fallback if it has retry_after (explicit rate limit signal)
        if isinstance(error, ProviderError):
            if hasattr(error, "retry_after") and error.retry_after:
                return True

        return False

    def _sanitize_error_for_log(self, error: Exception) -> dict:
        """Create safe logging metadata for an exception.

        Args:
            error: The exception to sanitize.

        Returns:
            Dictionary with safe error information (type, category only).
        """
        return {
            "error_type": type(error).__name__,
            "error_category": self._categorize_error(error),
        }

    def _categorize_error(self, error: Exception) -> str:
        """Categorize an error for safe logging.

        Args:
            error: The exception to categorize.

        Returns:
            Safe category string.
        """
        from app.models.pipeline import (
            RateLimitedError,
            TimeoutError,
            UnavailableError,
            BlockedError,
            BadOutputError,
        )

        if isinstance(error, RateLimitedError):
            return "rate_limited"
        if isinstance(error, TimeoutError):
            return "timeout"
        if isinstance(error, UnavailableError):
            return "unavailable"
        if isinstance(error, BlockedError):
            return "blocked"
        if isinstance(error, BadOutputError):
            return "bad_output"
        if isinstance(error, ProviderError):
            return "provider_error"
        return "unknown"

    def _create_safe_combined_error(self, primary_error: Exception, fallback_error: Exception,
                                     primary_model: str, fallback_model: str) -> ProviderError:
        """Create a combined error without exposing raw exception details.

        Args:
            primary_error: The primary provider error.
            fallback_error: The fallback provider error.
            primary_model: Primary provider model identifier.
            fallback_model: Fallback provider model identifier.

        Returns:
            ProviderError with sanitized message.
        """
        primary_cat = self._categorize_error(primary_error)
        fallback_cat = self._categorize_error(fallback_error)

        return ProviderError(
            f"Both providers failed. Primary ({primary_model}): {primary_cat}. "
            f"Fallback ({fallback_model}): {fallback_cat}."
        )

    def _check_deadline(self, deadline: float, context: str) -> float:
        """Check remaining time before deadline.

        Args:
            deadline: Monotonic deadline timestamp.
            context: Context string for error message.

        Returns:
            Precise remaining time in seconds; request timeout fields are clamped separately.

        Raises:
            TimeoutError: If deadline has expired.
        """
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Overall deadline exceeded during {context}")
        return remaining

    async def _invoke_provider(self, provider, request: "ProviderRequest", images=None):
        """Invoke text or vision adapters without changing the approved request."""
        if images is None:
            return await provider.generate_findings(request)
        return await provider.generate_findings(request, images)

    async def generate_findings(self, request: "ProviderRequest", images=None) -> "ProviderResult":
        """Generate findings with fallback support and single overall deadline.

        The total operation (primary attempt + primary retry + fallback attempt + fallback retry)
        must complete within the request's timeout_seconds.

        Args:
            request: The provider request.

        Returns:
            ProviderResult from primary or fallback provider.

        Raises:
            ProviderError: If both primary and fallback fail.
            TimeoutError: If overall deadline expires.
        """
        # Establish single overall deadline
        overall_deadline = time.monotonic() + request.timeout_seconds

        # Try primary provider
        try:
            remaining = self._check_deadline(overall_deadline, "primary attempt")
            primary_request = ProviderRequest(
                system_instruction=request.system_instruction,
                user_content=request.user_content,
                output_schema=request.output_schema,
                randomness=request.randomness,
                output_limit=request.output_limit,
                timeout_seconds=max(1, min(request.timeout_seconds, int(remaining))),
            )
            result = await asyncio.wait_for(
                self._invoke_provider(self._primary, primary_request, images),
                timeout=remaining,
            )
            logger.info(
                "provider_primary_success",
                extra={"model": self.primary_model},
            )
            return result

        except asyncio.TimeoutError:
            primary_error = TimeoutError(f"Primary provider timed out after {remaining:.1f}s")
            logger.warning(
                "provider_primary_timeout",
                extra={"model": self.primary_model, "remaining_seconds": remaining},
            )

            # Check if we should attempt fallback
            if self._fallback and self._should_fallback(primary_error):
                # Check if there's enough time for a fallback attempt
                remaining_after_primary = overall_deadline - time.monotonic()
                if remaining_after_primary < self.MIN_FALLBACK_TIME_SECONDS:
                    logger.warning(
                        "provider_fallback_skipped_insufficient_time",
                        extra={
                            "model": self.primary_model,
                            "remaining_seconds": remaining_after_primary,
                            "min_required": self.MIN_FALLBACK_TIME_SECONDS,
                        },
                    )
                    raise TimeoutError("Overall deadline exceeded during primary attempt") from None

                logger.info(
                    "provider_fallback_attempt",
                    extra={
                        "primary_model": self.primary_model,
                        "fallback_model": self.fallback_model,
                    },
                )

                try:
                    remaining = self._check_deadline(overall_deadline, "fallback attempt")
                    fallback_request = ProviderRequest(
                        system_instruction=request.system_instruction,
                        user_content=request.user_content,
                        output_schema=request.output_schema,
                        randomness=request.randomness,
                        output_limit=request.output_limit,
                        timeout_seconds=max(1, min(request.timeout_seconds, int(remaining))),
                    )
                    result = await asyncio.wait_for(
                        self._invoke_provider(self._fallback, fallback_request, images),
                        timeout=remaining,
                    )
                    logger.info(
                        "provider_fallback_success",
                        extra={
                            "fallback_model": self.fallback_model,
                            "primary_model": self.primary_model,
                        },
                    )
                    return result

                except asyncio.TimeoutError:
                    fallback_error = TimeoutError(f"Fallback provider timed out after {remaining:.1f}s")
                    logger.error(
                        "provider_both_failed",
                        extra={
                            "primary_model": self.primary_model,
                            "fallback_model": self.fallback_model,
                            **self._sanitize_error_for_log(TimeoutError("timeout")),
                            **{f"fallback_{k}": v for k, v in self._sanitize_error_for_log(TimeoutError("timeout")).items()},
                        },
                    )
                    raise self._create_safe_combined_error(
                        TimeoutError("primary timeout"), TimeoutError("fallback timeout"),
                        self.primary_model, self.fallback_model
                    ) from None

                except Exception as fallback_error:
                    logger.error(
                        "provider_both_failed",
                        extra={
                            "primary_model": self.primary_model,
                            "fallback_model": self.fallback_model,
                            **self._sanitize_error_for_log(TimeoutError("primary timeout")),
                            **{f"fallback_{k}": v for k, v in self._sanitize_error_for_log(fallback_error).items()},
                        },
                    )
                    raise self._create_safe_combined_error(
                        TimeoutError("primary timeout"), fallback_error,
                        self.primary_model, self.fallback_model
                    ) from None

            # No fallback available or error not retryable
            raise TimeoutError("Overall deadline exceeded") from None

        except Exception as primary_error:
            logger.warning(
                "provider_primary_failed",
                extra=self._sanitize_error_for_log(primary_error) | {"model": self.primary_model},
            )

            # Check if we should attempt fallback
            if self._fallback and self._should_fallback(primary_error):
                # Check if there's enough time for a fallback attempt
                if isinstance(primary_error, TimeoutError):
                    remaining_after_primary = overall_deadline - time.monotonic()
                    if remaining_after_primary < self.MIN_FALLBACK_TIME_SECONDS:
                        logger.warning(
                            "provider_fallback_skipped_insufficient_time",
                            extra={
                                "model": self.primary_model,
                                "remaining_seconds": remaining_after_primary,
                                "min_required": self.MIN_FALLBACK_TIME_SECONDS,
                            },
                        )
                        raise TimeoutError("Overall deadline exceeded during primary attempt") from None

                logger.info(
                    "provider_fallback_attempt",
                    extra={
                        "primary_model": self.primary_model,
                        "fallback_model": self.fallback_model,
                    },
                )

                try:
                    remaining = self._check_deadline(overall_deadline, "fallback attempt")
                    fallback_request = ProviderRequest(
                        system_instruction=request.system_instruction,
                        user_content=request.user_content,
                        output_schema=request.output_schema,
                        randomness=request.randomness,
                        output_limit=request.output_limit,
                        timeout_seconds=max(1, min(request.timeout_seconds, int(remaining))),
                    )
                    result = await asyncio.wait_for(
                        self._invoke_provider(self._fallback, fallback_request, images),
                        timeout=remaining,
                    )
                    logger.info(
                        "provider_fallback_success",
                        extra={
                            "fallback_model": self.fallback_model,
                            "primary_model": self.primary_model,
                        },
                    )
                    return result

                except asyncio.TimeoutError:
                    fallback_error = TimeoutError(f"Fallback provider timed out after {remaining:.1f}s")
                    logger.error(
                        "provider_both_failed",
                        extra={
                            "primary_model": self.primary_model,
                            "fallback_model": self.fallback_model,
                            **self._sanitize_error_for_log(primary_error),
                            **{f"fallback_{k}": v for k, v in self._sanitize_error_for_log(TimeoutError("timeout")).items()},
                        },
                    )
                    raise self._create_safe_combined_error(
                        primary_error, TimeoutError("fallback timeout"),
                        self.primary_model, self.fallback_model
                    ) from primary_error

                except Exception as fallback_error:
                    logger.error(
                        "provider_both_failed",
                        extra={
                            "primary_model": self.primary_model,
                            "fallback_model": self.fallback_model,
                            **self._sanitize_error_for_log(primary_error),
                            **{f"fallback_{k}": v for k, v in self._sanitize_error_for_log(fallback_error).items()},
                        },
                    )
                    raise self._create_safe_combined_error(
                        primary_error, fallback_error,
                        self.primary_model, self.fallback_model
                    ) from primary_error

            # No fallback available or error not retryable
            raise


def create_vision_provider(settings: Optional[ProviderSettings] = None):
    """Create a vision-capable primary adapter using the shared provider settings."""
    if settings is None:
        settings = load_provider_settings()

    from app.visual.vision_providers import (
        FakeVisionProvider, GeminiVisionProvider, GroqVisionProvider,
    )
    if settings.provider_type == ProviderType.FAKE:
        from app.core.config import get_settings as _get_settings
        if _get_settings().requires_real_provider:
            raise ProviderConfigError("Fake vision provider is not allowed in a non-local environment")
        return FakeVisionProvider()
    if settings.provider_type == ProviderType.GROQ:
        if not settings.groq_api_key:
            raise ProviderConfigError("GROQ_API_KEY is required for Groq vision provider")
        return GroqVisionProvider(
            api_key=settings.groq_api_key,
            tpm_limit=settings.groq_tpm_limit,
            rpm_limit=settings.groq_rpm_limit,
        )
    if settings.provider_type == ProviderType.GEMINI:
        if not settings.gemini_api_key:
            raise ProviderConfigError("GEMINI_API_KEY is required for Gemini vision provider")
        return GeminiVisionProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            tpm_limit=settings.gemini_tpm_limit,
            rpm_limit=settings.gemini_rpm_limit,
        )
    raise ProviderConfigError(f"Unknown vision provider type: {settings.provider_type}")


def create_fallback_vision_provider(settings: Optional[ProviderSettings] = None):
    """Create the configured vision fallback, if enabled and distinct."""
    if settings is None:
        settings = load_provider_settings()
    if not settings.fallback_enabled or settings.fallback_provider == settings.provider_type:
        return None

    from app.visual.vision_providers import (
        FakeVisionProvider, GeminiVisionProvider, GroqVisionProvider,
    )
    try:
        if settings.fallback_provider == ProviderType.FAKE:
            from app.core.config import get_settings as _get_settings
            if _get_settings().requires_real_provider:
                raise ProviderConfigError("Fake vision fallback is not allowed in a non-local environment")
            return FakeVisionProvider()
        if settings.fallback_provider == ProviderType.GROQ:
            if not settings.groq_api_key:
                logger.warning("groq_vision_fallback_not_configured", extra={"reason": "missing_api_key"})
                return None
            return GroqVisionProvider(
                api_key=settings.groq_api_key,
                tpm_limit=settings.groq_tpm_limit,
                rpm_limit=settings.groq_rpm_limit,
            )
        if settings.fallback_provider == ProviderType.GEMINI:
            if not settings.gemini_api_key:
                logger.warning("gemini_vision_fallback_not_configured", extra={"reason": "missing_api_key"})
                return None
            return GeminiVisionProvider(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                tpm_limit=settings.gemini_tpm_limit,
                rpm_limit=settings.gemini_rpm_limit,
            )
    except Exception as exc:
        logger.warning(
            "vision_fallback_provider_creation_failed",
            extra={"fallback_provider": settings.fallback_provider.value, "error_type": type(exc).__name__},
        )
        return None
    return None


def get_vision_provider_with_fallback() -> ProviderWithFallback:
    """Build a vision-capable provider pair with the same fallback policy as text."""
    settings = load_provider_settings()
    primary = create_vision_provider(settings)
    fallback = create_fallback_vision_provider(settings)
    return ProviderWithFallback(primary=primary, fallback=fallback)


def get_provider_with_fallback() -> ProviderWithFallback:
    """Get a configured provider with fallback.

    This is the main entry point for getting a production-ready provider
    with automatic fallback support.

    Returns:
        ProviderWithFallback instance.

    Raises:
        ProviderConfigError: If primary provider cannot be configured.
    """
    settings = load_provider_settings()
    primary = create_provider(settings)
    fallback = create_fallback_provider(settings)

    return ProviderWithFallback(primary=primary, fallback=fallback)


# For backward compatibility and testing
def get_provider() -> Provider:
    """Get the configured provider (without fallback wrapper).

    This function maintains compatibility with existing code that expects
    a direct Provider instance.

    Returns:
        Provider instance.

    Raises:
        ProviderConfigError: If provider cannot be configured.
    """
    settings = load_provider_settings()
    return create_provider(settings)