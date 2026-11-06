"""LLM provider abstraction and implementations.

This module provides the provider abstraction and implementations for
interacting with LLM providers. The FakeProvider is used for testing,
while real providers (Gemini, Groq) will be implemented later.
"""

from engine.app.llm.provider import Provider
from engine.app.llm.fake_provider import (
    FakeProviderConfig,
    FakeProvider,
    create_rate_limited_failure,
    create_timeout_failure,
    create_unavailable_failure,
    create_bad_output_failure,
    create_blocked_failure,
)

__all__ = [
    "Provider",
    "FakeProviderConfig",
    "FakeProvider",
    "create_rate_limited_failure",
    "create_timeout_failure",
    "create_unavailable_failure",
    "create_bad_output_failure",
    "create_blocked_failure",
]