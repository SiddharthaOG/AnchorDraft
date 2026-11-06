"""Provider abstraction for the LLM provider adapter.

This module defines the abstract interface that all LLM providers must implement.
"""

from abc import ABC, abstractmethod
from typing import Protocol

from engine.app.models.pipeline import ProviderRequest, ProviderResult


class Provider(Protocol):
    """Abstract interface for LLM providers.

    All provider implementations must provide an async generate_findings method
    that takes a ProviderRequest and returns a ProviderResult.
    """

    @abstractmethod
    async def generate_findings(self, request: ProviderRequest) -> ProviderResult:
        """Generate findings from the provider.

        Args:
            request: The provider request containing system instruction, user content,
                     output schema, and generation parameters.

        Returns:
            ProviderResult containing the raw JSON response and metadata.

        Raises:
            ProviderError: On provider-specific errors (rate limit, timeout, etc.)
        """
        ...


__all__ = ["Provider"]