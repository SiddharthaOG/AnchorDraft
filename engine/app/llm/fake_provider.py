"""Fake LLM provider for testing.

This provider returns predictable, configurable responses without making
any network calls. It's designed for testing the review pipeline without
requiring API keys or network access.
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Optional

from engine.app.models.pipeline import (
    ProviderRequest,
    ProviderResult,
    ProviderError,
    RateLimitedError,
    TimeoutError,
    UnavailableError,
    BadOutputError,
    BlockedError,
    ModelFindingCandidate,
)


@dataclass
class FakeProviderConfig:
    """Configuration for the fake provider.

    Allows configuring the provider's behavior for testing.
    """
    # Pre-configured candidates to return on success
    candidates: List[ModelFindingCandidate] = field(default_factory=list)

    # Optional failure to raise instead of returning candidates
    failure: Optional[Exception] = None

    # Simulated latency in milliseconds
    latency_ms: int = 10

    # Simulated token usage
    input_tokens: int = 100
    output_tokens: int = 50

    # Model name to report
    model: str = "fake-model"

    # Finish reason to report
    finish_reason: str = "stop"

    # Raw JSON response to return (for testing parsing)
    raw_json: Optional[str] = None


class FakeProvider:
    """Fake LLM provider for testing.

    Returns configurable, deterministic responses without making network calls.
    Supports configurable failures for testing error handling.
    """

    def __init__(self, config: Optional[FakeProviderConfig] = None):
        """Initialize the fake provider.

        Args:
            config: Optional configuration. If not provided, returns empty
                   candidate list on success.
        """
        self.config = config or FakeProviderConfig()
        self._call_count = 0

    async def generate_findings(self, request: "ProviderRequest") -> "ProviderResult":
        """Generate findings from the fake provider.

        Args:
            request: The provider request (not modified).

        Returns:
            ProviderResult with configured candidates or raises configured failure.

        Raises:
            ProviderError: If configured to fail.
        """
        self._call_count += 1

        # Simulate latency
        if self.config.latency_ms > 0:
            await asyncio.sleep(self.config.latency_ms / 1000.0)

        # Check for configured failure
        if self.config.failure is not None:
            raise self.config.failure

        # Build raw JSON if not explicitly provided
        raw_json = self.config.raw_json
        if raw_json is None:
            import json
            findings = [
                {
                    "ref_key": c.ref_key,
                    "issue": c.issue,
                    "quote": c.quote,
                    "explanation": c.explanation,
                    "suggestion": c.suggestion,
                    "confidence": c.confidence,
                }
                for c in self.config.candidates
            ]
            raw_json = json.dumps({"findings": findings})

        return ProviderResult(
            raw_json=raw_json,
            input_tokens=self.config.input_tokens,
            output_tokens=self.config.output_tokens,
            model=self.config.model,
            latency_ms=self.config.latency_ms,
            finish_reason=self.config.finish_reason,
        )

    @property
    def call_count(self) -> int:
        """Number of times generate_findings has been called."""
        return self._call_count

    def reset(self) -> None:
        """Reset the call counter."""
        self._call_count = 0


def create_rate_limited_failure(retry_after: int = 30) -> RateLimitedError:
    """Create a rate limited error for testing."""
    return RateLimitedError("Rate limited", retry_after=retry_after)


def create_timeout_failure() -> TimeoutError:
    """Create a timeout error for testing."""
    return TimeoutError("Request timed out")


def create_unavailable_failure() -> UnavailableError:
    """Create an unavailable error for testing."""
    return UnavailableError("Service unavailable")


def create_bad_output_failure(message: str = "Invalid JSON") -> BadOutputError:
    """Create a bad output error for testing."""
    return BadOutputError(message)


def create_blocked_failure(message: str = "Safety block") -> BlockedError:
    """Create a blocked error for testing."""
    return BlockedError(message)


__all__ = [
    "FakeProviderConfig",
    "FakeProvider",
    "create_rate_limited_failure",
    "create_timeout_failure",
    "create_unavailable_failure",
    "create_bad_output_failure",
    "create_blocked_failure",
]