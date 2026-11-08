"""LLM provider abstraction and implementations.

This module provides the provider abstraction and implementations for
interacting with LLM providers. The FakeProvider is used for testing,
while real providers (Groq, Gemini) are used in production.
"""

from app.llm.provider import Provider
from app.llm.fake_provider import (
    FakeProviderConfig,
    FakeProvider,
    create_rate_limited_failure,
    create_timeout_failure,
    create_unavailable_failure,
    create_bad_output_failure,
    create_blocked_failure,
)
from app.llm.groq_provider import GroqProvider
from app.llm.gemini_provider import GeminiProvider
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
from app.llm.token_budget import (
    estimate_tokens,
    estimate_request_tokens,
    check_token_budget,
    TokenBudgetExceededError,
    TokenEstimate,
)
from app.llm.prompt_builder import (
    PromptInput,
    RuleData,
    FactData,
    build_provider_request,
    extract_offered_references,
    generate_nonce,
    filter_rules_for_model,
    filter_valid_facts,
    render_rules_block,
    render_facts_block,
    build_user_content,
    MAX_DRAFT_CHARS,
    MAX_KIT_CHARS,
    MAX_FINDINGS_CAP,
    OUTPUT_SCHEMA,
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
    "GroqProvider",
    "GeminiProvider",
    "ProviderType",
    "ProviderSettings",
    "ProviderConfigError",
    "create_provider",
    "create_fallback_provider",
    "get_provider",
    "get_provider_with_fallback",
    "ProviderWithFallback",
    "load_provider_settings",
    "estimate_tokens",
    "estimate_request_tokens",
    "check_token_budget",
    "TokenBudgetExceededError",
    "TokenEstimate",
    "PromptInput",
    "RuleData",
    "FactData",
    "build_provider_request",
    "extract_offered_references",
    "generate_nonce",
    "filter_rules_for_model",
    "filter_valid_facts",
    "render_rules_block",
    "render_facts_block",
    "build_user_content",
    "MAX_DRAFT_CHARS",
    "MAX_KIT_CHARS",
    "MAX_FINDINGS_CAP",
    "OUTPUT_SCHEMA",
]